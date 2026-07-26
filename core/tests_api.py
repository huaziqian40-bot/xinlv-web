"""客户端 API（/api/v1/）全流程测试。独立测试库，不碰生产数据。
运行：python manage.py test core.tests_api -v 1
deepseek.chat 一律 mock，不依赖外部网络和 API Key。"""
import datetime as dt
import json
import uuid as _uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import MoodEntry, ChatMessage, ApiToken
from . import ratelimit

User = get_user_model()


def _future_iso(minutes=1):
    return (timezone.now() + dt.timedelta(minutes=minutes)).isoformat()


class ApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="apiuser", password="pw123456")
        # 一条存量记录（模拟网页端记的）
        cls.old = MoodEntry.objects.create(
            user=cls.user, date=dt.date(2026, 7, 20), mood="happy", note="旧的")

    # ---- 工具 ----
    def setUp(self):
        # 限流计数是进程内存全局的，每个用例前清零，避免互相干扰（api_login 桶 10次/10分钟）
        ratelimit._hits.clear()

    def login(self):
        r = self.client.post("/api/v1/login/", data=json.dumps({
            "username": "apiuser", "password": "pw123456",
            "device": "test"}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["token"]

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def push(self, token, entries):
        return self.client.post("/api/v1/sync/push/", data=json.dumps(
            {"entries": entries}), content_type="application/json",
            **self.auth(token))

    # ---- 认证 ----
    def test_ping_no_auth(self):
        r = self.client.get("/api/v1/ping/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_login_wrong_password(self):
        r = self.client.post("/api/v1/login/", data=json.dumps(
            {"username": "apiuser", "password": "wrong"}),
            content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_no_token_401(self):
        r = self.client.get("/api/v1/sync/pull/")
        self.assertEqual(r.status_code, 401)

    # ---- 注册 ----
    def register(self, username="newbie", password="pw123456", agree=True):
        return self.client.post("/api/v1/register/", data=json.dumps({
            "username": username, "password": password,
            "agree": agree, "device": "test"}), content_type="application/json")

    def test_register_ok_auto_token(self):
        r = self.register()
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["username"], "newbie")
        # 注册即登录：令牌可直接用
        r = self.client.get("/api/v1/profile/", **self.auth(body["token"]))
        self.assertEqual(r.status_code, 200)

    def test_register_duplicate_username(self):
        r = self.register(username="apiuser")   # setUpTestData 里已存在
        self.assertEqual(r.status_code, 400)
        self.assertIn("已经被注册", r.json()["error"])

    def test_register_short_password(self):
        r = self.register(password="123")
        self.assertEqual(r.status_code, 400)
        self.assertIn("6", r.json()["error"])

    def test_register_must_agree(self):
        r = self.register(agree=False)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_logout_invalidates_token(self):
        token = self.login()
        r = self.client.post("/api/v1/logout/", **self.auth(token))
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/v1/sync/pull/", **self.auth(token))
        self.assertEqual(r.status_code, 401)

    # ---- 同步 ----
    def test_push_new_and_dedup(self):
        token = self.login()
        uid = str(_uuid.uuid4())
        # 时间戳用过去固定值：服务端创建时 updated_at=现在，重推同一条必被跳过
        entry = {"uuid": uid, "date": "2026-07-25", "mood": "calm",
                 "note": "客户端记的", "updated_at": "2026-07-25T12:00:00+08:00"}
        r = self.push(token, [entry]).json()
        self.assertEqual((r["saved"], r["updated"], r["skipped"]), (1, 0, 0))
        # 相同内容再推一次 -> skipped（时间戳不更新时）
        r = self.push(token, [entry]).json()
        self.assertEqual((r["saved"], r["updated"], r["skipped"]), (0, 0, 1))
        self.assertEqual(MoodEntry.all_objects.filter(user=self.user, uuid=uid).count(), 1)

    def test_push_newer_wins(self):
        token = self.login()
        uid = str(_uuid.uuid4())
        self.push(token, [{"uuid": uid, "date": "2026-07-25", "mood": "sad",
                           "note": "旧版本", "updated_at": _future_iso(1)}])
        r = self.push(token, [{"uuid": uid, "date": "2026-07-25", "mood": "happy",
                               "note": "新版本", "updated_at": _future_iso(10)}]).json()
        self.assertEqual(r["updated"], 1)
        e = MoodEntry.all_objects.get(user=self.user, uuid=uid)
        self.assertEqual((e.mood, e.note), ("happy", "新版本"))

    def test_tombstone_delete(self):
        token = self.login()
        uid = str(_uuid.uuid4())
        self.push(token, [{"uuid": uid, "date": "2026-07-25", "mood": "sad",
                           "updated_at": _future_iso(1)}])
        # 软删：deleted=True + 更新的时间戳
        r = self.push(token, [{"uuid": uid, "date": "2026-07-25", "mood": "sad",
                               "deleted": True, "updated_at": _future_iso(10)}]).json()
        self.assertEqual(r["updated"], 1)
        # 网页端默认管理器看不到墓碑
        self.assertFalse(MoodEntry.objects.filter(user=self.user, uuid=uid).exists())
        self.assertTrue(MoodEntry.all_objects.get(user=self.user, uuid=uid).deleted)
        # 增量拉取能拉到墓碑
        r = self.client.get("/api/v1/sync/pull/", **self.auth(token)).json()
        tombs = [e for e in r["entries"] if e["uuid"] == uid]
        self.assertTrue(tombs and tombs[0]["deleted"])

    def test_pull_incremental(self):
        token = self.login()
        r = self.client.get("/api/v1/sync/pull/", **self.auth(token)).json()
        self.assertEqual(len(r["entries"]), 1)   # 只有存量那条
        since = r["server_time"]
        self.push(token, [{"uuid": str(_uuid.uuid4()), "date": "2026-07-26",
                           "mood": "excited", "updated_at": _future_iso()}])
        r = self.client.get("/api/v1/sync/pull/", {"since": since},
                            **self.auth(token)).json()
        self.assertEqual(len(r["entries"]), 1)
        self.assertEqual(r["entries"][0]["mood"], "excited")

    def test_push_validates(self):
        token = self.login()
        r = self.push(token, [
            {"uuid": "", "date": "2026-07-25", "mood": "sad"},          # 缺uuid
            {"uuid": str(_uuid.uuid4()), "date": "bad", "mood": "sad"},  # 坏日期
            {"uuid": str(_uuid.uuid4()), "date": "2026-07-25", "mood": "xx"},  # 坏心情
            {"uuid": str(_uuid.uuid4()), "date": "2999-01-01", "mood": "sad"},  # 未来
        ]).json()
        self.assertEqual(r["saved"], 0)
        self.assertEqual(len(r["errors"]), 4)

    def test_isolation_between_users(self):
        """A 的记录不会被 B 拉到。"""
        other = User.objects.create_user(username="other", password="pw123456")
        MoodEntry.objects.create(user=other, date=dt.date(2026, 7, 21), mood="sad")
        token = self.login()
        r = self.client.get("/api/v1/sync/pull/", **self.auth(token)).json()
        self.assertEqual(len(r["entries"]), 1)   # 只有自己的存量记录

    # ---- 目录与推荐 ----
    def test_catalog(self):
        token = self.login()
        r = self.client.get("/api/v1/catalog/", **self.auth(token))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["moods"]), 10)
        self.assertIn("songs", data)

    def test_recommend(self):
        token = self.login()
        r = self.client.get("/api/v1/recommend/?mood=sad", **self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["mood"], "sad")
        r = self.client.get("/api/v1/recommend/?mood=nope", **self.auth(token))
        self.assertEqual(r.status_code, 400)

    # ---- AI 树洞 ----
    @mock.patch("core.api.deepseek.chat", return_value=("你好呀", None))
    def test_chat_normal(self, _m):
        token = self.login()
        r = self.client.post("/api/v1/chat/", data=json.dumps(
            {"message": "今天有点累"}), content_type="application/json",
            **self.auth(token))
        self.assertEqual(r.json()["reply"], "你好呀")
        self.assertEqual(ChatMessage.objects.filter(user=self.user).count(), 2)

    @mock.patch("core.api.deepseek.chat")   # 危机词绝不应到达 AI
    def test_chat_crisis_intercepted(self, m):
        token = self.login()
        r = self.client.post("/api/v1/chat/", data=json.dumps(
            {"message": "我不想活了"}), content_type="application/json",
            **self.auth(token))
        data = r.json()
        self.assertTrue(data["crisis"])
        self.assertIn("hotline", data)
        m.assert_not_called()

    def test_chat_history(self):
        ChatMessage.objects.create(user=self.user, role="user", content="问")
        ChatMessage.objects.create(user=self.user, role="assistant", content="答")
        token = self.login()
        r = self.client.get("/api/v1/chat/history/", **self.auth(token)).json()
        self.assertEqual([m["content"] for m in r["messages"]], ["问", "答"])

    # ---- 个人数据 ----
    def test_profile(self):
        token = self.login()
        r = self.client.get("/api/v1/profile/", **self.auth(token)).json()
        self.assertEqual(r["username"], "apiuser")
        self.assertEqual(r["total_entries"], 1)
        self.assertIn("streak", r)
