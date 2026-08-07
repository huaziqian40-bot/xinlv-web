"""极简用户认证：只要账号+密码，无验证码、无邮箱验证。密码由 Django 自动哈希存储。

安全加固（2026-08-07）：
- _safe_next 改用 Django 官方 url_has_allowed_host_and_scheme 校验，堵住 //evil.com 开放重定向；
- 网页注册加 UnicodeUsernameValidator 校验 + IntegrityError 兜底，防非法用户名与并发重名 500；
- RateLimitedLoginView 给网页登录加防爆破限流（复用 login 桶），超限返回 429。"""
from django.contrib.auth import login, get_user_model
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from . import ratelimit

User = get_user_model()

_username_validator = UnicodeUsernameValidator()


class RateLimitedLoginView(LoginView):
    """网页登录：复用 login 限流桶（5 分钟 8 次），超限返回 429 并提示。"""

    def post(self, request, *args, **kwargs):
        if ratelimit.is_limited(request, "login"):
            return render(request, self.get_template_names(),
                          {"form": self.get_form(), "rate_limited": True}, status=429)
        return super().post(request, *args, **kwargs)


def _safe_next(request):
    nxt = request.GET.get("next") or request.POST.get("next") or "/"
    # 只允许站内相对路径或同源绝对地址，堵住 //evil.com 开放重定向
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts=None):
        return "/"
    return nxt


def _validate_username(username):
    """返回错误信息字符串；合法返回 None。"""
    if not username:
        return "账号不能为空。"
    if len(username) > 150:
        return "账号太长了。"
    try:
        _username_validator(username)
    except ValidationError:
        return "账号只能包含字母、数字、下划线、点、@、+、- 和中文。"
    return None


def register(request):
    if request.user.is_authenticated:
        return redirect("/")
    nxt = _safe_next(request)
    if request.method == "POST":
        if ratelimit.is_limited(request, "login"):
            return render(request, "register.html",
                          {"error": "操作太频繁了，请过几分钟再试。", "next": nxt})
        username = request.POST.get("username", "").strip()
        pw1 = request.POST.get("password1", "")
        pw2 = request.POST.get("password2", "")
        agreed = request.POST.get("agree") == "on"
        error = _validate_username(username)
        if not pw1:
            error = error or "账号和密码都要填。"
        elif len(pw1) < 6:
            error = error or "密码至少 6 位。"
        elif pw1 != pw2:
            error = error or "两次输入的密码不一样。"
        if not agreed:
            error = error or "请先阅读并勾选同意《免责声明》。"
        if error:
            return render(request, "register.html", {"error": error, "username": username, "next": nxt})
        try:
            user = User.objects.create_user(username=username, password=pw1)  # 自动哈希
        except IntegrityError:
            # 并发下两个请求同时注册同名账号，exists() 检查有竞态，兜底返回友好错误
            return render(request, "register.html",
                          {"error": "这个账号已经被注册了，换一个吧。", "username": username, "next": nxt})
        login(request, user)
        return redirect(nxt)
    return render(request, "register.html", {"next": nxt})