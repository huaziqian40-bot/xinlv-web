"""后台管理页面渲染冒烟测试：防止模板标签/静态引用错误导致 500。"""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings

MANAGE_PAGES = [
    "/manage/",
    "/manage/videos/",
    "/manage/activities/",
    "/manage/songs/",
    "/manage/tips/",
    "/manage/site/",
    "/manage/game-config/",
    "/manage/users/",
    "/manage/review/",
]


class ManagePagesRenderTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_all_manage_pages_render_for_staff(self):
        user = get_user_model().objects.create_user(
            username="staff1", password="x1234567", is_staff=True)
        client = Client()
        self.assertTrue(client.login(username="staff1", password="x1234567"))
        for path in MANAGE_PAGES:
            resp = client.get(path)
            self.assertEqual(resp.status_code, 200, f"{path} 应返回 200，实际 {resp.status_code}")
