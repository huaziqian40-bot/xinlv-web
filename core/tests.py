"""用户主页（/me/）渲染冒烟测试：防止模板标签/静态引用错误导致 500，
并确认「关于软件」区块的关键内容被正确渲染。"""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client


class ProfileAboutSoftwareTests(TestCase):
    def test_profile_page_renders_about_software_block(self):
        user = get_user_model().objects.create_user(username="aboutuser", password="x1234567")
        client = Client()
        self.assertTrue(client.login(username="aboutuser", password="x1234567"))
        resp = client.get("/me/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        # 关于软件区块的关键内容
        self.assertIn("关于软件", html)
        self.assertIn("网页端始终是最新版本", html)
        self.assertIn("访问官网", html)
        self.assertIn("https://phix.ing/download/", html)
        # 联系方式应渲染为 mailto 链接（测试库中无站点设置，回退到内置邮箱）
        self.assertIn("mailto:norine.liu@icloud.com", html)