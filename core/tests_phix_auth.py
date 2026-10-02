"""phix 认证委托的测试（见 core/phix_auth.py）。

默认**全用 mock**，不联网、不依赖 phix 服务在不在——这样它能进日常测试套件。
想连真实 phix 服务跑一遍端到端，设环境变量后运行（见文件末尾的说明）：

    set PHIX_LIVE_TEST=1
    set PHIX_SERVER=http://127.0.0.1:8931
    set PHIX_SERVICE_KEY=<与 phix 服务端一致>
    venv\\Scripts\\python.exe -X utf8 manage.py test core.tests_phix_auth
"""
import json
import os
import shutil
import tempfile
from unittest import mock, skipUnless

from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase, override_settings

from .models import UserProfile
from . import phix_auth
from . import phix_e2e as e2e

User = get_user_model()

ON = dict(PHIX_AUTH_ENABLED=True, PHIX_SERVER="http://phix.test:8931",
          PHIX_SERVICE_KEY="k" * 24)
OFF = dict(PHIX_AUTH_ENABLED=False, PHIX_SERVER="", PHIX_SERVICE_KEY="")


class PhixAuthBackendTests(TestCase):
    """全部路径都用 mock 的 phix_verify_status / phix_register，专注后端决策逻辑。

    三段式：① 先问 phix → ② 明确拒绝回落本地 → ③ 本地口令通过（老用户）现场迁移。
    """

    def setUp(self):
        self.backend = phix_auth.PhixAuthBackend()

    # ---------- 开关 ----------
    @override_settings(**OFF)
    def test_disabled_backend_is_inert(self):
        """没开开关时后端形同不存在，绝不能影响现有登录。"""
        User.objects.create_user(username="plain", password="localpass1")
        with mock.patch("core.phix_auth.phix_verify_status") as m:
            self.assertIsNone(self.backend.authenticate(None, "plain", "localpass1"))
            m.assert_not_called()

    @override_settings(PHIX_AUTH_ENABLED=True, PHIX_SERVER="http://x", PHIX_SERVICE_KEY="")
    def test_missing_service_key_is_inert(self):
        """开了开关但没给服务密钥 → 仍然不启用（防止误配后变成一个放行后门）。"""
        self.assertFalse(phix_auth.enabled())
        self.assertIsNone(self.backend.authenticate(None, "whoever", "whatever"))

    # ---------- 老用户自动迁移 ----------
    @override_settings(**ON)
    def test_legacy_user_migrates_on_login(self):
        """老用户（本地口令可用、phix 无账号）首次登录：
        phix 拒绝 → 本地通过 → 现场建号 → 关联 phix user_id → 本地口令作废。"""
        u = User.objects.create_user(username="legacy", password="localpass1")
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("bad_credentials", None)) as v, \
             mock.patch("core.phix_auth.phix_register",
                        return_value=("ok", {"user_id": 42,
                                             "recovery_code": "ABCD-EFGH-JKLM-NPQR-STUV-WXYZ"})) as r:
            got = self.backend.authenticate(None, "legacy", "localpass1")
        self.assertEqual(got, u)
        v.assert_called_once()
        r.assert_called_once()
        u.refresh_from_db()
        self.assertEqual(phix_auth.phix_user_id_of(u), 42)
        self.assertFalse(u.has_usable_password())     # 迁移成功后只认 phix

    @override_settings(**ON)
    def test_legacy_user_wrong_password_fails_without_migration(self):
        """本地口令错 → 不迁移、不在 phix 建任何账号，登录失败。"""
        User.objects.create_user(username="legacy2", password="localpass1")
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("bad_credentials", None)) as v, \
             mock.patch("core.phix_auth.phix_register") as r:
            self.assertIsNone(self.backend.authenticate(None, "legacy2", "wrong"))
        v.assert_called_once()
        r.assert_not_called()

    @override_settings(**ON)
    def test_phix_ok_links_existing_local_user(self):
        """phix 认了（同名账号已在 phix）→ 直接关联本地账号并作废本地口令。"""
        u = User.objects.create_user(username="legacy3", password="localpass1")
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("ok", {"user_id": 7, "username": "legacy3"})) as v:
            got = self.backend.authenticate(None, "legacy3", "phix-password")
        v.assert_called_once()
        self.assertEqual(got.pk, u.pk)
        u.refresh_from_db()
        self.assertEqual(phix_auth.phix_user_id_of(u), 7)
        self.assertFalse(u.has_usable_password())

    # ---------- 影子账号 ----------
    @override_settings(**ON)
    def test_creates_shadow_account_for_unknown_user(self):
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("ok", {"user_id": 7, "username": "brandnew"})):
            got = self.backend.authenticate(None, "brandnew", "phix-password")
        self.assertIsNotNone(got)
        self.assertEqual(got.username, "brandnew")
        self.assertFalse(got.has_usable_password())
        self.assertEqual(phix_auth.phix_user_id_of(got), 7)

    # ---------- 已关联的账号只认 phix ----------
    @override_settings(**ON)
    def test_linked_account_ignores_local_password(self):
        """已关联 phix 之后，本地密码作废；给对本地密码也进不去。"""
        u = User.objects.create_user(username="linked", password="localpass1")
        UserProfile.objects.update_or_create(
            user=u, defaults={"phix_user_id": 99})
        u.set_unusable_password()
        u.save()

        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("bad_credentials", None)) as m:
            self.assertIsNone(self.backend.authenticate(None, "linked", "localpass1"))
            m.assert_called_once()                    # 必须去问 phix，不能本地放行

        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("ok", {"user_id": 99, "username": "linked"})):
            self.assertEqual(self.backend.authenticate(None, "linked", "realphixpw").pk,
                             u.pk)

    # ---------- phix 拒绝 / 连不上 ----------
    @override_settings(**ON)
    def test_phix_rejects(self):
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("bad_credentials", None)):
            self.assertIsNone(self.backend.authenticate(None, "nobody", "whatever"))

    @override_settings(**ON)
    def test_phix_unreachable_is_fail_closed_for_linked(self):
        """phix 挂了：已关联账号必须**拒绝**登录，绝不能因为服务器不可用就放行。"""
        u = User.objects.create_user(username="linked2", password="x")
        UserProfile.objects.update_or_create(user=u, defaults={"phix_user_id": 5})
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("unreachable", None)):
            self.assertIsNone(self.backend.authenticate(None, "linked2", "x"))

    @override_settings(**ON)
    def test_phix_unreachable_still_allows_local_password(self):
        """phix 挂了但不影响老用户：本地密码照常能登，且**绝不建号**。"""
        u = User.objects.create_user(username="legacy4", password="localpass1")
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("unreachable", None)) as v, \
             mock.patch("core.phix_auth.phix_register") as r:
            self.assertEqual(self.backend.authenticate(None, "legacy4", "localpass1").pk,
                             u.pk)
        v.assert_called_once()
        r.assert_not_called()
        self.assertIsNone(phix_auth.phix_user_id_of(u))

    # ---------- 迁移时 phix 已有同名账号（不覆盖） ----------
    @override_settings(**ON)
    def test_migrate_when_account_already_exists_reverifies(self):
        """注册返回「已被注册」→ 不覆盖，改再走一次 phix 校验；口令对就登录。"""
        u = User.objects.create_user(username="legacy5", password="localpass1")
        with mock.patch("core.phix_auth.phix_verify_status",
                        side_effect=[("bad_credentials", None),
                                     ("ok", {"user_id": 9, "username": "legacy5"})]) as v, \
             mock.patch("core.phix_auth.phix_register",
                        return_value=("exists", None)) as r:
            got = self.backend.authenticate(None, "legacy5", "localpass1")
        self.assertEqual(got.pk, u.pk)
        r.assert_called_once()
        self.assertEqual(v.call_count, 2)
        u.refresh_from_db()
        self.assertEqual(phix_auth.phix_user_id_of(u), 9)
        self.assertFalse(u.has_usable_password())

    # ---------- 输入边界 ----------
    @override_settings(**ON)
    def test_missing_credentials_return_none(self):
        self.assertIsNone(self.backend.authenticate(None, "", "x"))
        self.assertIsNone(self.backend.authenticate(None, "someone", ""))
        self.assertIsNone(self.backend.authenticate(None, None, None))

    @override_settings(**ON)
    def test_inactive_user_cannot_authenticate(self):
        u = User.objects.create_user(username="frozen", password="localpass1")
        u.is_active = False
        u.save()
        with mock.patch("core.phix_auth.phix_verify_status",
                        return_value=("bad_credentials", None)), \
             mock.patch("core.phix_auth.phix_register") as r:
            self.assertIsNone(self.backend.authenticate(None, "frozen", "localpass1"))
        r.assert_not_called()

    @override_settings(**ON)
    def test_get_user(self):
        u = User.objects.create_user(username="getme", password="x")
        self.assertEqual(self.backend.get_user(u.pk).pk, u.pk)
        self.assertIsNone(self.backend.get_user(999999))

    # ---------- view 层：登录真的能走通 ----------
    @override_settings(**ON)
    @mock.patch("core.phix_auth.phix_verify_status",
                return_value=("ok", {"user_id": 123, "username": "viaphix"}))
    def test_django_authenticate_helper_uses_backend(self, _m):
        """把后端接进 AUTHENTICATION_BACKENDS 之后，django 的 authenticate() 能认它。"""
        with self.settings(AUTHENTICATION_BACKENDS=[
                "core.phix_auth.PhixAuthBackend",
                "django.contrib.auth.backends.ModelBackend"]):
            u = authenticate(username="viaphix", password="pw-from-phix")
        self.assertIsNotNone(u)
        self.assertEqual(u.username, "viaphix")
        self.assertEqual(phix_auth.phix_user_id_of(u), 123)


# ==================== 心履发出的到底是什么（P4：口令不出本机） ====================
#
# 这一组**不联网**：假扮一台 phix 服务器，把信封解开看里面到底装了什么。
# 要钉死两件事：
#   ① 对 v2 账号，心履发的是 **AuthHash**，不是口令；
#   2 整个请求体是**密文**（信封），线上抓不到明文。


class PhixVerifyPayloadTests(TestCase):
    """假扮 phix 服务器，解开信封检查心履到底发了什么。"""

    def setUp(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        self.sk = X25519PrivateKey.generate()
        self.pk = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.sk_raw = e2e.raw_private_bytes(self.sk)
        self.seen = []          # 收到的**明文**请求体
        self.raw = []           # 收到的**线上原文**
        self.keymaterial = {}

        self._pin = tempfile.mkdtemp(prefix="phixpin-")
        self.addCleanup(shutil.rmtree, self._pin, ignore_errors=True)

    # ---- 假服务器 ----
    def _fake_get(self, url, timeout=None):
        return _FakeResp({"ok": True, "enc": 1, "pk": e2e.b64e(self.pk),
                          "version": 1, "service_verify_enabled": True,
                          "kdf_algos": [e2e.KDF_ALGO_V1, e2e.KDF_ALGO_V2]})

    def _fake_post(self, url, **kwargs):
        # 注意：形参不能叫 `json`，那会把 json 模块遮蔽掉（踩过）
        payload = kwargs.get("json")
        headers = kwargs.get("headers") or {}
        self.raw.append(payload)
        path = url[url.index("/api/v1"):]
        if headers.get("X-Phix-Enc") == "1":
            sk = e2e.open_box(e2e.b64d(payload["sealed_sk"]), self.sk_raw, self.pk)
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            inner = json.loads(AESGCM(sk).decrypt(
                e2e.b64d(payload["iv"]), e2e.b64d(payload["ct"]),
                e2e.env_aad("POST", path)).decode("utf-8"))
            body = inner["b"]
            assert inner["p"] == path and inner["m"] == "POST"
        else:
            body = payload
        self.seen.append((path, body, headers))
        if path.endswith("/auth/keymaterial"):
            return _FakeResp({"ok": True, **self.keymaterial})
        if path.endswith("/auth/verify"):
            return _FakeResp({"ok": True, "user_id": 42, "username": body.get("username")})
        return _FakeResp({"ok": False, "error": {"code": "not_found", "message": "?"}})

    def _run_verify(self, username, password):
        with mock.patch("requests.get", side_effect=self._fake_get), \
             mock.patch("requests.post", side_effect=self._fake_post), \
             mock.patch.object(phix_auth, "base_dir", lambda: self._pin):
            with override_settings(PHIX_AUTH_ENABLED=True,
                                   PHIX_SERVER="http://phix.test:8931",
                                   PHIX_SERVICE_KEY="k" * 24):
                return phix_auth.phix_verify(username, password)

    # ---- 用例 ----
    def test_v2_sends_auth_hash_not_password(self):
        """v2 账号：发出去的是 AuthHash，**口令一个字都不在**。"""
        password = "My-Secret-Pw-9876"
        auth_salt = "ab" * 16
        self.keymaterial = {"kdf_algo": e2e.KDF_ALGO_V2, "auth_salt": auth_salt,
                            "kdf_salt": "cd" * 16}
        got = self._run_verify("someone", password)
        self.assertIsNotNone(got)
        paths = [p for p, _b, _h in self.seen]
        self.assertIn("/api/v1/auth/keymaterial", paths)
        self.assertIn("/api/v1/auth/verify", paths)

        verify_body = [b for p, b, _h in self.seen if p.endswith("/auth/verify")][0]
        self.assertIn("auth_hash", verify_body)
        self.assertNotIn("password", verify_body)
        self.assertNotEqual(verify_body["auth_hash"], password)
        self.assertNotIn(password, json.dumps(verify_body))
        self.assertEqual(verify_body["auth_hash"],
                         e2e.auth_hash_hex(password, auth_salt, e2e.KDF_ALGO_V2))

    def test_whole_request_is_ciphertext(self):
        """整个请求体是密文：线上抓到的原文里找不到口令、AuthHash、用户名。"""
        password = "Another-Secret-1234"
        self.keymaterial = {"kdf_algo": e2e.KDF_ALGO_V2, "auth_salt": "ef" * 16,
                            "kdf_salt": "12" * 16}
        self._run_verify("someone", password)
        for raw in self.raw:
            blob = json.dumps(raw, ensure_ascii=False)
            self.assertNotIn(password, blob)
            self.assertNotIn("someone", blob)
            self.assertEqual(set(raw.keys()), {"sealed_sk", "iv", "ct"})

    def test_v1_falls_back_to_password(self):
        """v1 老账号：phix 存的就是口令的哈希，只能发口令原文（保持兼容）。"""
        self.keymaterial = {"kdf_algo": e2e.KDF_ALGO_V1, "auth_salt": "",
                            "kdf_salt": "34" * 16}
        self._run_verify("legacy", "Legacy-Pass-1")
        body = [b for p, b, _h in self.seen if p.endswith("/auth/verify")][0]
        self.assertIn("password", body)
        self.assertNotIn("auth_hash", body)

    def test_sends_service_key(self):
        """服务密钥必须在请求头里（phix 靠它区分"是心履在调"）。"""
        self.keymaterial = {"kdf_algo": e2e.KDF_ALGO_V2, "auth_salt": "55" * 16}
        self._run_verify("someone", "Whatever-123")
        headers = [h for p, _b, h in self.seen if p.endswith("/auth/verify")][0]
        self.assertEqual(headers.get("X-Phix-Service-Key"), "k" * 24)
        self.assertEqual(headers.get("X-Phix-Enc"), "1")

    def test_register_sends_no_plaintext_password(self):
        """迁移注册**绝不把明文口令发给 phix**：只有 auth_hash 等派生值，整包还是密文。

        这是老用户迁移的关键约束——phix 只该收到 `auth_hash`/`key_wrap`/`key_check`
        等派生材料，口令原文一个字节都不能出现（线上原文更是纯密文）。
        """
        password = "Legacy-Secret-Pass-99"
        username = "legacy-migrate"
        with mock.patch("requests.get", side_effect=self._fake_get), \
             mock.patch("requests.post", side_effect=self._fake_post), \
             mock.patch.object(phix_auth, "base_dir", lambda: self._pin):
            with override_settings(PHIX_AUTH_ENABLED=True,
                                   PHIX_SERVER="http://phix.test:8931",
                                   PHIX_SERVICE_KEY="k" * 24):
                status, _data = phix_auth.phix_register(username, password)
        # 假服务器对 register 只回 not_found（没建号），但请求体已被解开捕获
        self.assertEqual(status, "rejected")
        bodies = [b for p, b, _h in self.seen if p.endswith("/auth/register")]
        self.assertEqual(len(bodies), 1)
        body = bodies[0]
        # 明文口令绝不能出现；只发派生值
        self.assertIn("auth_hash", body)
        self.assertNotIn("password", body)
        self.assertNotEqual(body.get("auth_hash"), password)
        self.assertNotIn(password, json.dumps(body, ensure_ascii=False))
        # 线上原文是密文信封，口令与用户名都不在
        for raw in self.raw:
            blob = json.dumps(raw, ensure_ascii=False)
            self.assertNotIn(password, blob)
            self.assertNotIn(username, blob)

    def test_server_key_change_refuses(self):
        """公钥被换掉时要**拒绝**（返回 None = 不放行），而不是照常连上去。"""
        self.keymaterial = {"kdf_algo": e2e.KDF_ALGO_V2, "auth_salt": "66" * 16}
        self.assertIsNotNone(self._run_verify("someone", "Pass-1234"))
        # 把固定的公钥改成别的
        pin = e2e.pin_file(self._pin)
        doc = json.loads(pin.read_text(encoding="utf-8"))
        doc["http://phix.test:8931"] = "ff" * 32
        pin.write_text(json.dumps(doc), encoding="utf-8")
        self.seen.clear()
        self.assertIsNone(self._run_verify("someone", "Pass-1234"))
        self.assertEqual([p for p, _b, _h in self.seen if p.endswith("/auth/verify")], [])


class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.headers = {"Content-Type": "application/json"}
        self.text = json.dumps(data, ensure_ascii=False)

    def json(self):
        return self._data


# ==================== 连真实 phix 服务的活体测试 ====================
#
# 需要 phix 服务在跑、且 PHIX_SERVICE_KEY 与服务端一致；平时自动跳过。
LIVE = os.environ.get("PHIX_LIVE_TEST") == "1"


@skipUnless(LIVE, "设 PHIX_LIVE_TEST=1 且 phix 服务在跑时才跑真正的端到端")
class PhixLiveTests(TestCase):
    """对着真的 phix 服务跑一遍：注册 → 心履登录 → 关联 → 回登录。"""

    def _live_settings(self):
        return dict(
            PHIX_AUTH_ENABLED=True,
            PHIX_SERVER=os.environ.get("PHIX_SERVER", "http://127.0.0.1:8931"),
            PHIX_SERVICE_KEY=os.environ.get("PHIX_SERVICE_KEY", ""),
        )

    def test_end_to_end_with_real_phix(self):
        import json
        import secrets
        import urllib.request

        cfg = self._live_settings()
        self.assertTrue(cfg["PHIX_SERVICE_KEY"], "缺少 PHIX_SERVICE_KEY")
        username = "xinlv_" + secrets.token_hex(4)
        password = "Live-Test-123"

        # 1. 用一个"客户端"注册 phix 账号（密码材料的生成在客户端侧，这里只需要能过注册）
        import sys

        sys.path.insert(0, r"D:\phl-lite-dev")
        from hellopinghe import phixcrypto as pc

        mat = pc.new_material(username, password)
        body = json.dumps({
            "username": username, "agree": True,
            "device": "心履端到端测试",
            "kdf_algo": mat["kdf_algo"], "kdf_salt": mat["kdf_salt"],
            # v2：注册发的是 AuthHash，不是口令；auth_salt 是登录凭证的盐
            "auth_salt": mat["auth_salt"], "auth_hash": mat["auth_hash"],
            "key_wrap": mat["key_wrap"], "key_mode": mat["key_mode"],
            "key_check": mat["key_check"],
            "key_check_plain": mat["key_check_plain"],
            "recovery_salt": mat["recovery_salt"],
            "recovery_wrap": mat["recovery_wrap"],
        }).encode("utf-8")
        req = urllib.request.Request(
            cfg["PHIX_SERVER"].rstrip("/") + "/api/v1/auth/register", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            reg = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(reg.get("ok"), reg)
        phix_uid = reg["user_id"]

        # 2. 心履这边用同一套账号密码登录 → 自动建影子账号并关联
        with self.settings(**cfg):
            with self.settings(AUTHENTICATION_BACKENDS=[
                    "core.phix_auth.PhixAuthBackend",
                    "django.contrib.auth.backends.ModelBackend"]):
                u = authenticate(username=username, password=password)
        self.assertIsNotNone(u, "心履没能用 phix 账号登录")
        self.assertEqual(phix_auth.phix_user_id_of(u), phix_uid)
        self.assertFalse(u.has_usable_password())

        # 3. 错密码进不来
        with self.settings(**cfg):
            self.assertIsNone(phix_auth.PhixAuthBackend().authenticate(
                None, username, "wrong-password"))
