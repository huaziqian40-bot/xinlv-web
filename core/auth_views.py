"""极简用户认证：只要账号+密码，无验证码、无邮箱验证。密码由 Django 自动哈希存储。"""
from django.contrib.auth import login, get_user_model
from django.shortcuts import redirect, render

from . import ratelimit

User = get_user_model()


def _safe_next(request):
    nxt = request.GET.get("next") or request.POST.get("next") or "/"
    return nxt if nxt.startswith("/") else "/"


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
        error = None
        if not username or not pw1:
            error = "账号和密码都要填。"
        elif len(username) > 150:
            error = "账号太长了。"
        elif User.objects.filter(username=username).exists():
            error = "这个账号已经被注册了，换一个吧。"
        elif len(pw1) < 6:
            error = "密码至少 6 位。"
        elif pw1 != pw2:
            error = "两次输入的密码不一样。"
        elif not agreed:
            error = "请先阅读并勾选同意《免责声明》。"
        if error:
            return render(request, "register.html", {"error": error, "username": username, "next": nxt})
        user = User.objects.create_user(username=username, password=pw1)  # 自动哈希
        login(request, user)
        return redirect(nxt)
    return render(request, "register.html", {"next": nxt})
