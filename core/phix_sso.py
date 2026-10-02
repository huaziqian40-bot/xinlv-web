"""跨站免密登录 · 心履侧（对应 phix 的 `api/sso.py`）。

## 它解决什么

需求：「登录心履、Pinghe Launcher 网页端、phix 官网中的任何一个，其它两个都自动登录」。
官网与 PHL 网页端同域同 cookie，天生互通；心履在**另一个注册域**（xin-lv.com），
浏览器绝不会把 `phix.ing` 的 cookie 发给它。于是两个方向各要一步"搬登录态"：

```text
③ 官网 → 心履   官网 /sso/to-xinlv/ ──签码(带 DEK? 不，码里没有凭据)──▶ 本模块 consume()
                心履拿码 + 服务密钥去 phix /auth/sso/redeem 换成 phix 身份
                → 找到/创建本地账号 → django.contrib.auth.login()
                → **在 xin-lv.com 上种下心履自己的 sessionid cookie**（见下）

② 心履 → 官网   本模块 start() 用服务密钥让 phix 签一枚发给官网的码
                → 302 到 https://phix.ing/auth/sso/enter/?code=…&next=…
                → 官网后端兑换 → 官网自己的 cookie 落地 → 跳回 ?sso=phix
```

## 登录态放在哪里（用户要求"cookie 存本地"）

- **phix 侧**：签名 cookie `phix_access` / `phix_refresh`（httpOnly），里面装着
  access/refresh 令牌与 DEK；服务端不存任何会话状态（见官网 `server.py` 顶部注释）。
- **心履侧**：Django 自带 `sessionid` cookie（httpOnly、SameSite=Lax），
  它是**心履自己的**会话键，存在心履自己的库里（`django_session` 表）。
  两者互不引用：心履不拿 phix 的令牌，phix 也不知道心履的会话。
  这就是"认证委托"（见 `core/phix_auth.py` 模块 docstring）的延续。

## 安全

- 调 phix 走**应用层信封**（`phix_auth.phix_post`，公钥固定），内网线上也不裸奔。
- 一次性码由 phix 侧保证：256 位随机、120 秒、单次、绑站点；**码里没有凭据**，
  兑换还必须带服务密钥 —— 光拿到码换不走任何东西。
- 心履这边：`?sso=` 的码**只走一次**（本视图），不写日志、不进 session、不进 Referer
  （用 302 立即跳走，落地页不再带 code）。
- 交换来的 phix 身份要落到**本地账号**上：优先按 `phix_user_id` 关联；
  没有同名账号就建一个**影子账号**（与 `phix_auth.PhixAuthBackend` 同一套做法）。
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from . import phix_auth
from . import ratelimit
from .models import UserProfile

log = logging.getLogger("core.phix_sso")

CODE_PATH = "/api/v1/auth/sso/code"
REDEEM_PATH = "/api/v1/auth/sso/redeem"
#: **别人发给本地的**码该写哪个站点标识 —— 官网签的码是发给心履的
SELF_AUDIENCE = "xinlv"
#: **本地发给别处的**码该写哪个站点标识 —— 心履签的码是发给官网的
SITE_AUDIENCE = "phix-site"
RATE_BUCKET = "phix_sso"


def enabled() -> bool:
    """SSO 开关：与 phix 认证委托同一组配置（服务地址 + 服务密钥都要有）。"""
    return bool(getattr(settings, "PHIX_SSO_ENABLED", True)
                and getattr(settings, "PHIX_SERVER", "")
                and getattr(settings, "PHIX_SERVICE_KEY", ""))


def site_url() -> str:
    return (getattr(settings, "PHIX_SITE_URL", "https://phix.ing") or "").rstrip("/")


def _service_key_ok() -> bool:
    return bool(getattr(settings, "PHIX_SERVICE_KEY", ""))


# ---------------- 与 phix 说话 ----------------

def redeem(code: str) -> tuple[str, dict]:
    """用一次性码换 phix 身份。返回 ``(status, data)``。

    status：``ok`` / ``unreachable``（服务不可达/信封打不开）/ ``server_key_changed``
    （phix 公钥变了，拒绝连接）/ 其它 = phix 明确拒绝的 ``error.code``。
    """
    server = getattr(settings, "PHIX_SERVER", "")
    try:
        data = phix_auth.phix_post(server, REDEEM_PATH,
                                   {"code": code, "site": SELF_AUDIENCE,
                                    "device": "心履网页端"})
    except phix_auth.e2e.ServerKeyError:
        log.error("phix 服务器公钥校验失败，拒绝兑换")
        return "server_key_changed", {}
    if data is None:
        return "unreachable", {}
    if data.get("ok"):
        return "ok", data
    err = data.get("error") or {}
    return (err.get("code") or "unknown"), data


def mint(user) -> tuple[str, dict]:
    """让 phix 签一枚**发给官网**的一次性码（心履 → 官网方向）。"""
    server = getattr(settings, "PHIX_SERVER", "")
    body = {"audience": SITE_AUDIENCE, "device": "心履 → 官网"}
    phix_uid = phix_auth.phix_user_id_of(user)
    if phix_uid:
        body["user_id"] = int(phix_uid)
    else:
        # 还没关联过 phix 的老账号：用用户名让 phix 自己找（同名即同一人）
        body["username"] = user.username
    try:
        data = phix_auth.phix_post(server, CODE_PATH, body)
    except phix_auth.e2e.ServerKeyError:
        return "server_key_changed", {}
    if data is None:
        return "unreachable", {}
    if data.get("ok"):
        return "ok", data
    err = data.get("error") or {}
    return (err.get("code") or "unknown"), data


# ---------------- 本地账号 ----------------

def local_user_for(phix_user_id: int, username: str):
    """把 phix 身份落到**本地**账号上：已关联 → 用它；同名未关联 → 关联；否则建影子账号。

    绝不"抢"一个已经关联到别的 phix 账号的同名本地账号（那会把别人的数据交出去）。
    """
    User = get_user_model()
    uid = int(phix_user_id)
    prof = UserProfile.objects.filter(phix_user_id=uid).select_related("user").first()
    if prof is not None:
        return prof.user

    name = (username or "").strip() or f"phix{uid}"
    user = User.objects.filter(username=name).first()
    if user is not None:
        other = UserProfile.objects.filter(user=user).exclude(
            phix_user_id__isnull=True).exclude(phix_user_id=uid).first()
        if other is None:
            phix_auth.link_user(user, uid)
            return user
        # 同名但已属于另一个 phix 账号 → 换一个不冲突的本地用户名（影子账号）
        name = f"{name}-phix{uid}"
        user = User.objects.filter(username=name).first()
        if user is not None:
            phix_auth.link_user(user, uid)
            return user

    try:
        user = User.objects.create_user(username=name[:150])
    except IntegrityError:
        user = User.objects.filter(username=name[:150]).first()
        if user is None:
            raise
    phix_auth.link_user(user, uid)
    log.info("SSO 建影子账号：%s ↔ phix#%s", user.username, uid)
    return user


def _login_backend() -> str:
    """用哪个后端把用户塞进 session —— 必须与 AUTHENTICATION_BACKENDS 一致，否则
    下次请求 Django 会因为"后端不在列表里"直接把用户踢掉。"""
    backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", []))
    phix_backend = "core.phix_auth.PhixAuthBackend"
    if phix_backend in backends:
        return phix_backend
    if backends:
        return backends[0]
    return "django.contrib.auth.backends.ModelBackend"


def _safe_next(request, default="/"):
    """只允许站内跳转（堵开放重定向）。"""
    nxt = request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts=None):
        return nxt
    return default


def _fail(request, reason: str):
    """失败一律回登录页，只带一个不含细节的原因码（不泄露"码是否存在"）。"""
    log.warning("SSO 兑换失败 reason=%s ip=%s", reason, request.META.get("REMOTE_ADDR"))
    return redirect(f"{reverse('login')}?sso_error={reason}")


# ---------------- 视图 ----------------

def consume(request):
    """`/phix/sso/?sso=<一次性码>&next=` —— 官网跳过来时落地在这里。

    成功后：本地账号 + **心履自己的 sessionid cookie**（在 xin-lv.com 上），
    然后 302 跳走，URL 里不再留那个码。
    """
    if not enabled():
        return _fail(request, "disabled")
    if ratelimit.is_limited(request, RATE_BUCKET):
        return _fail(request, "rate_limited")
    code = (request.GET.get("sso") or "").strip()
    if not code:
        # 只带 ?sso_done=1 回来（"官网 → 心履"走完一圈）→ 当普通落地页
        return redirect(_safe_next(request, "/"))
    if len(code) > 200:
        return _fail(request, "bad_code")

    status, data = redeem(code)
    if status != "ok":
        return _fail(request, status)

    try:
        user = local_user_for(data.get("user_id"), data.get("username", ""))
    except Exception as exc:  # noqa: BLE001  建号/关联失败不该 500
        log.warning("SSO 落地本地账号失败：%s", exc)
        return _fail(request, "local_account")

    if not getattr(user, "is_active", True):
        return _fail(request, "inactive")

    login(request, user, backend=_login_backend())
    log.info("SSO 登录成功 user=%s phix#%s", user.username, data.get("user_id"))
    target = _safe_next(request, "/")
    sep = "&" if "?" in target else "?"
    return HttpResponseRedirect(f"{target}{sep}sso=phix")


def start(request):
    """`/phix/sso/start/?next=/account/` —— 心履已登录 → 带着一次性码跳去官网兑换。

    这里 `next` 是**官网侧**的站内路径（官网会再校验一次，只接受站内相对路径）。
    """
    if not enabled() or not site_url():
        return redirect(reverse("login"))
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={request.get_full_path()}")
    if ratelimit.is_limited(request, RATE_BUCKET):
        return redirect(f"{site_url()}/login/?sso_error=rate_limited")

    status, data = mint(request.user)
    if status != "ok":
        log.warning("换码失败 status=%s", status)
        return redirect(f"{reverse('login')}?sso_error={status}")

    nxt = request.GET.get("next") or "/account/"
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/account/"
    code = data.get("code", "")
    from urllib.parse import quote

    return redirect(f"{site_url()}/auth/sso/enter/?code={quote(code)}&next={quote(nxt)}")
