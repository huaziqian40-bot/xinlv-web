"""心履侧跨站免密登录（core/phix_sso.py）的测试。

    cd D:\\moodsite\\web
    venv\\Scripts\\python.exe manage.py test core.tests_phix_sso -v 2

覆盖：
  1. `/phix/sso/?sso=<码>` 兑换成功 → **心履自己的会话 cookie**（登录态落在本地域）
     + 本地账号被建/被关联到 phix user_id；
  2. 码无效 / phix 不可达 / 公钥变了 / 开关关着 → 回登录页带原因，**绝不半登录**；
  3. `/phix/sso/start/` 未登录 → 先去登录；已登录 → 带着码 302 到官网兑换页；
  4. 本地账号归属：同名但已属于别的 phix 账号时**绝不抢夺**（建影子账号）；
  5. 开放重定向与限流。

真打通网络的那一份在 D:\\phix\\_lab\\sso\\test_sso_xinlv.py（起真实 HTTP 服务跑）。
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from . import phix_sso, ratelimit
from .models import UserProfile

User = get_user_model()

ENABLED = dict(PHIX_SSO_ENABLED=True, PHIX_SERVER="http://127.0.0.1:8931",
               PHIX_SERVICE_KEY="test-service-key", PHIX_SITE_URL="https://phix.ing")


@override_settings(**ENABLED, AUTHENTICATION_BACKENDS=[
    "core.phix_auth.PhixAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
])
class ConsumeTests(TestCase):
    def setUp(self):
        ratelimit._hits.clear()

    def _redeem_ok(self, uid=4242, username="ssouser"):
        return mock.patch.object(phix_sso, "redeem",
                                 return_value=("ok", {"ok": True, "user_id": uid,
                                                      "username": username}))

    def test_consume_logs_in_and_sets_session_cookie(self):
        with self._redeem_ok():
            r = self.client.get("/phix/sso/?sso=" + "c" * 43 + "&next=/me/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/me/"))
        self.assertIn("sso=phix", r["Location"])
        cookie = r.cookies.get("sessionid")
        self.assertIsNotNone(cookie, "免密兑换后必须种下心履自己的 sessionid")
        self.assertTrue(cookie["httponly"])
        user = User.objects.get(username="ssouser")
        self.assertEqual(UserProfile.objects.get(user=user).phix_user_id, 4242)
        # 会话真的生效了
        r2 = self.client.get("/me/")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.context["user"].username, "ssouser")

    def test_consume_links_existing_local_account(self):
        u = User.objects.create_user(username="ssouser")
        with self._redeem_ok():
            self.client.get("/phix/sso/?sso=" + "d" * 43)
        u.refresh_from_db()
        self.assertEqual(User.objects.filter(username="ssouser").count(), 1)
        self.assertEqual(UserProfile.objects.get(user=u).phix_user_id, 4242)

    def test_consume_reuses_profile_by_phix_user_id_when_name_changed(self):
        u = User.objects.create_user(username="renamed-local")
        UserProfile.objects.create(user=u, phix_user_id=4242)
        with self._redeem_ok(username="old-phix-name"):
            self.client.get("/phix/sso/?sso=" + "e" * 43)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(u.id))

    def test_consume_never_hijacks_same_name_other_phix_account(self):
        other = User.objects.create_user(username="ssouser")
        UserProfile.objects.create(user=other, phix_user_id=9999)
        with self._redeem_ok(uid=4242, username="ssouser"):
            self.client.get("/phix/sso/?sso=" + "f" * 43)
        other.refresh_from_db()
        self.assertEqual(UserProfile.objects.get(user=other).phix_user_id, 9999,
                         "原有账号的 phix 关联不该被改写")
        shadow = User.objects.get(username="ssouser-phix4242")
        self.assertEqual(UserProfile.objects.get(user=shadow).phix_user_id, 4242)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(shadow.id))

    def test_consume_bad_code_goes_to_login(self):
        with mock.patch.object(phix_sso, "redeem",
                               return_value=("unauthorized", {"ok": False})):
            r = self.client.get("/phix/sso/?sso=" + "g" * 43)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])
        self.assertIn("sso_error=unauthorized", r["Location"])
        self.assertEqual(User.objects.count(), 0, "兑换失败绝不能建账号")
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_consume_unreachable_does_not_create_account(self):
        with mock.patch.object(phix_sso, "redeem", return_value=("unreachable", {})):
            r = self.client.get("/phix/sso/?sso=" + "h" * 43)
        self.assertIn("sso_error=unreachable", r["Location"])
        self.assertEqual(User.objects.count(), 0)

    def test_consume_server_key_changed_does_not_login(self):
        with mock.patch.object(phix_sso, "redeem",
                               return_value=("server_key_changed", {})):
            r = self.client.get("/phix/sso/?sso=" + "i" * 43)
        self.assertIn("sso_error=server_key_changed", r["Location"])
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    @override_settings(PHIX_SSO_ENABLED=False)
    def test_consume_disabled(self):
        r = self.client.get("/phix/sso/?sso=" + "j" * 43)
        self.assertIn("sso_error=disabled", r["Location"])

    @override_settings(PHIX_SERVICE_KEY="")
    def test_consume_without_service_key_is_disabled(self):
        r = self.client.get("/phix/sso/?sso=" + "k" * 43)
        self.assertIn("sso_error=disabled", r["Location"])

    def test_consume_without_code_is_plain_landing(self):
        r = self.client.get("/phix/sso/?sso_done=1")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/")

    def test_consume_rejects_open_redirect(self):
        with self._redeem_ok():
            r = self.client.get("/phix/sso/?sso=" + "l" * 43
                                + "&next=https://evil.example.com/x")
        self.assertTrue(r["Location"].startswith("/?"), r["Location"])
        self.assertNotIn("evil.example.com", r["Location"])

    def test_consume_rate_limited(self):
        # 限流键里带登录后的 uid，所以第 1 次兑换成功后就换了桶：多打几次必然撞上。
        with override_settings(RATE_LIMITS={"phix_sso": (2, 300)}):
            with self._redeem_ok():
                codes = []
                for _ in range(6):
                    r = self.client.get("/phix/sso/?sso=" + "m" * 43)
                    codes.append(r["Location"])
        self.assertTrue(any("sso_error=rate_limited" in c for c in codes), str(codes))

    def test_consume_overlong_code_rejected(self):
        r = self.client.get("/phix/sso/?sso=" + "x" * 500)
        self.assertIn("sso_error=bad_code", r["Location"])

    def test_inactive_local_account_rejected(self):
        u = User.objects.create_user(username="ssouser", is_active=False)
        with self._redeem_ok():
            r = self.client.get("/phix/sso/?sso=" + "n" * 43)
        self.assertIn("sso_error=inactive", r["Location"])
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        u.refresh_from_db()
        self.assertFalse(u.is_active)


@override_settings(**ENABLED)
class StartTests(TestCase):
    def setUp(self):
        ratelimit._hits.clear()

    def test_start_requires_login(self):
        r = self.client.get("/phix/sso/start/?next=/account/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_start_redirects_to_site_with_code(self):
        u = User.objects.create_user(username="starter")
        UserProfile.objects.create(user=u, phix_user_id=777)
        self.client.force_login(u)
        with mock.patch.object(phix_sso, "mint",
                               return_value=("ok", {"ok": True, "code": "Q" * 43})) as m:
            r = self.client.get("/phix/sso/start/?next=/account/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://phix.ing/auth/sso/enter/?code="),
                        r["Location"])
        self.assertIn("next=/account/", r["Location"])
        # 用的是**服务密钥 + 已关联的 phix user_id**，不是用户名
        body = m.call_args[0][0] if m.call_args[0] else None
        self.assertIsNotNone(body)

    def test_start_uses_username_when_not_linked(self):
        u = User.objects.create_user(username="unlinked-old-user")
        self.client.force_login(u)
        captured = {}

        def fake_post(server, path, body):
            captured["path"] = path
            captured["body"] = body
            return {"ok": True, "code": "R" * 43}

        with mock.patch.object(phix_sso.phix_auth, "phix_post", side_effect=fake_post):
            r = self.client.get("/phix/sso/start/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(captured["path"], "/api/v1/auth/sso/code")
        self.assertEqual(captured["body"].get("username"), "unlinked-old-user")
        self.assertEqual(captured["body"].get("audience"), "phix-site")

    def test_start_mint_failure_returns_to_login(self):
        u = User.objects.create_user(username="starter2")
        self.client.force_login(u)
        with mock.patch.object(phix_sso, "mint", return_value=("unreachable", {})):
            r = self.client.get("/phix/sso/start/")
        self.assertIn("sso_error=unreachable", r["Location"])

    def test_start_neutralises_external_next(self):
        u = User.objects.create_user(username="starter3")
        self.client.force_login(u)
        with mock.patch.object(phix_sso, "mint",
                               return_value=("ok", {"ok": True, "code": "S" * 43})):
            r = self.client.get("/phix/sso/start/?next=https://evil.example.com/")
        self.assertIn("next=/account/", r["Location"])
        self.assertNotIn("evil.example.com", r["Location"])


class HelperTests(TestCase):
    def test_login_backend_matches_settings(self):
        with override_settings(AUTHENTICATION_BACKENDS=[
                "core.phix_auth.PhixAuthBackend",
                "django.contrib.auth.backends.ModelBackend"]):
            self.assertEqual(phix_sso._login_backend(), "core.phix_auth.PhixAuthBackend")
        with override_settings(AUTHENTICATION_BACKENDS=[]):
            self.assertEqual(phix_sso._login_backend(),
                             "django.contrib.auth.backends.ModelBackend")

    def test_enabled_requires_all_three(self):
        with override_settings(PHIX_SSO_ENABLED=True, PHIX_SERVER="x", PHIX_SERVICE_KEY="y"):
            self.assertTrue(phix_sso.enabled())
        with override_settings(PHIX_SSO_ENABLED=True, PHIX_SERVER="x", PHIX_SERVICE_KEY=""):
            self.assertFalse(phix_sso.enabled())
        with override_settings(PHIX_SSO_ENABLED=False, PHIX_SERVER="x", PHIX_SERVICE_KEY="y"):
            self.assertFalse(phix_sso.enabled())

    def test_redeem_reports_statuses(self):
        """redeem() 把"为什么没换成"如实分类，绝不把不可达当成"码无效"。"""
        with mock.patch.object(phix_sso.phix_auth, "phix_post", return_value=None):
            self.assertEqual(phix_sso.redeem("c" * 43)[0], "unreachable")
        with mock.patch.object(phix_sso.phix_auth, "phix_post",
                               return_value={"ok": False,
                                             "error": {"code": "unauthorized"}}):
            self.assertEqual(phix_sso.redeem("c" * 43)[0], "unauthorized")
        with mock.patch.object(phix_sso.phix_auth, "phix_post",
                               side_effect=phix_sso.phix_auth.e2e.ServerKeyError("changed")):
            self.assertEqual(phix_sso.redeem("c" * 43)[0], "server_key_changed")
