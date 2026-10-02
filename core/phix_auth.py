"""phix 统一账号接入（心履侧 · 认证委托）。

## 为什么是"认证委托"而不是"合并用户表"

心履在**第一台服务器**（192.168.5.35）上跑着自己的 Django 用户表，phix 在**第二台服务器**
（192.168.5.41）上是统一账号中心。两边数据库不在一起，也不该合——合了就要动生产数据。
所以做法是：**心履把"这个人是不是合法用户"这一个判断委托给 phix**，本地仍然保留自己的用户行。

## 心履在这里的角色：尽量只当"信使"

按 `加密链路思路.md` §4，第 1 台服务器应该**能拿到的最少越好**。所以：

1. **不再把口令原文发给 phix**：本地算出 `AuthHash = HKDF(scrypt(P, auth_salt), ...)`
   （见 `core/phix_e2e.py`），只发这一串。phix 反推不出口令，也算不出用户的 KEK。
   —— 心履自己**不存**这个值，用完就丢。
2. **应用层加密**：请求套 X25519 密封盒信封（与 PLL/PHL 同一套协议，规范 §10）。
   即使 phix 没接 HTTPS，内网线上也只有密文。
3. **公钥固定**：phix 的公钥首次信任后记在 `.phix_pubkey`，以后对不上就拒绝连接。

> 更彻底的"纯信使"（连心履的 Django 都看不到口令）需要**在浏览器里**算 AuthHash。
> 浏览器 WebCrypto **没有 scrypt**，得自带 JS/WASM 实现；这一步留作后续。

## 行为（默认完全不影响现有用户）

``PHIX_AUTH_ENABLED`` 未打开时，本后端**直接返回 None**（等于不存在），心履行为与从前一模一样。

打开后，认证是**三段式**（老用户登录时自动迁移到 phix 账号）：

1. **先问 phix**：本地算 AuthHash → `POST /auth/verify`。通过 = 已是 phix 用户，
   直接登录（本地没有同名账号就建影子账号，有就把本地账号关联到 phix user_id）。
2. **phix 明确拒绝**（账号不存在 / 凭据不对，`error.code` 401/400）→ 回落到本地
   `check_password`。本地不通过 → 返回 None（登录失败，不泄露是哪种失败）；
   本地通过 → 说明这是**还没迁移的老用户，且此刻手里有明文口令** → 进入第 3 步。
3. **按需迁移**：用 `phix_e2e.new_material(username, password)` 生成整套 v2 密钥材料，
   调 `POST /auth/register`（用户名同名、`agree:true`、`device:"心履迁移"`）。
   注册成功 → 关联到新 phix user_id，并**在注册确实成功后才**作废本地口令
   （`set_unusable_password`）；恢复码写进 session，登录后页面展示一次即清除。
   若返回「账号已被注册」→ 别人已迁过，**不覆盖**，改用这个口令再走一次第 1 步
   （verify；口令对就登录，不对就失败）。

## 兜底（phix 不可达时的取舍，刻意记录）

phix 连不上（超时/连接失败/502）**绝不误判成"账号不存在"去建号**——"连不上"和
"401/400 明确拒绝"在 `phix_verify_status` 里分开返回。连不上时按现有策略：

- 已关联 phix 的账号 → **拒绝登录**（fail closed：改了 phix 密码必须立刻生效，
  不能因为服务器挂了就放行）；
- 未关联的老账号 → 仍可用本地口令登录；其 `phix_user_id` 保持为空，等于天然
  "待迁移"，下次 phix 可连时用本地口令登录即走第 3 步迁移。

## 已知取舍

- **恢复码只走 session**（登录后展示一次即清除），不写日志、不进 URL 查询串、
  不落数据库。网页登录能展示；API 客户端（安卓/桌面）登录没有可渲染页面，
  恢复码会随其 session 失效而丢弃——账号仍已迁移、仍可登录，只是那条恢复码
  没送达（这类客户端本就不走恢复码流程）。
- 迁移建号用的密钥材料在**服务端进程内存里**生成、用完即丢，绝不落盘。
- 心履的浏览器端还没算 AuthHash（见上文）；迁移时的心履服务端仍会短暂经手
  明文口令（本地 `check_password` 需要它）——这正是"手里有明文口令"这一前提的代价。

## 配置（环境变量，见 moodsite/settings.py）

``PHIX_AUTH_ENABLED``  1/true 打开；默认关
``PHIX_SERVER``        phix 服务地址，默认 http://127.0.0.1:8931
``PHIX_SERVICE_KEY``   服务端到服务端的共享密钥（**必填**，否则后端不启用）
"""
from __future__ import annotations

import json
import logging

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from .models import UserProfile
from . import phix_e2e as e2e

log = logging.getLogger("core.phix_auth")

VERIFY_PATH = "/api/v1/auth/verify"
KEYMATERIAL_PATH = "/api/v1/auth/keymaterial"
REGISTER_PATH = "/api/v1/auth/register"
PING_PATH = "/api/v1/ping"
TIMEOUT = 8

#: 迁移建号时给 phix 登记的"设备名"（客户端 `device` 字段，纯备注）。
MIGRATE_DEVICE = "心履迁移"

#: session 里临时存恢复码的键（登录后展示一次即清除，不落库、不写日志）。
RECOVERY_SESSION_KEY = "phix_recovery_code"


def enabled() -> bool:
    """后端是否启用（开关 + 服务地址 + 服务密钥都齐了才算）。"""
    return bool(getattr(settings, "PHIX_AUTH_ENABLED", False)
                and getattr(settings, "PHIX_SERVER", "")
                and getattr(settings, "PHIX_SERVICE_KEY", ""))


def base_dir():
    return getattr(settings, "BASE_DIR", None) or "."


def _service_headers() -> dict:
    return {
        "X-Phix-Service-Key": getattr(settings, "PHIX_SERVICE_KEY", ""),
        "Accept": "application/json",
    }


# ---------------- 与 phix 说话（全部走加密信封） ----------------

def _server_public_key(server: str) -> bytes | None:
    """拿 phix 的 X25519 公钥并固定下来。服务器不支持加密就返回 None。"""
    try:
        r = requests.get(server.rstrip("/") + PING_PATH, timeout=TIMEOUT)
        info = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("phix ping 失败 %s：%s", server, exc)
        return None
    if int(info.get("enc") or 0) != 1 or not info.get("pk"):
        return None
    try:
        pk = e2e.b64d(info["pk"])
    except Exception:  # noqa: BLE001
        return None
    if len(pk) != 32:
        return None
    try:
        e2e.pin_key(base_dir(), server, pk.hex())
    except e2e.ServerKeyError as exc:
        # **公钥变了**：宁可登录失败也不要连到可能是冒充者的服务器上
        log.error("phix 服务器公钥校验失败：%s", exc)
        raise
    return pk

def phix_post(server: str, path: str, body: dict) -> dict | None:
    """向 phix POST 一个 JSON，**带上应用层加密信封**。失败返回 None。"""
    server = server.rstrip("/")
    pk = _server_public_key(server)
    headers = _service_headers()
    try:
        if pk is not None:
            headers["X-Phix-Enc"] = "1"
            envelope, sk = e2e.make_envelope(pk, "POST", path, body)
            r = requests.post(server + path, json=envelope, headers=headers,
                              timeout=TIMEOUT)
            data = r.json() if "json" in (r.headers.get("Content-Type") or "") else {}
            if isinstance(data, dict) and "iv" in data and "ct" in data:
                data = json.loads(e2e.open_envelope_response(sk, "POST", path,
                                                             data).decode("utf-8"))
        else:
            # 服务器不支持加密 —— 仍然照常工作（只是没有那一层保护）
            r = requests.post(server + path, json=body, headers=headers, timeout=TIMEOUT)
            data = r.json() if "json" in (r.headers.get("Content-Type") or "") else {}
    except e2e.ServerKeyError:
        raise
    except (requests.RequestException, ValueError) as exc:
        log.warning("phix 请求失败 %s%s：%s", server, path, exc)
        return None
    return data if isinstance(data, dict) else None


def phix_verify_detailed(username: str, password: str) -> dict:
    """给**诊断命令**用的版本：把"为什么没通过"如实带回来。

    为什么要有它：`phix_verify()` 一律返回 `None`（**故意的** —— 认证后端对外必须
    含糊，否则就成了账号枚举工具）。但本机跑诊断时，含糊是有害的：服务密钥没配对
    （403）和"口令真的不对"（401）看起来一模一样，上一次就是因此把
    「服务密钥没设」误判成「账号密码不对」。

    返回 `{ok, code, message, user_id, username, kdf_algo}`，**绝不返回密钥材料**。
    """
    server = getattr(settings, "PHIX_SERVER", "")
    out = {"ok": False, "code": "", "message": "", "user_id": None,
           "username": None, "kdf_algo": None}
    km = phix_post(server, KEYMATERIAL_PATH, {"username": username})
    if km is None:
        out.update(code="unreachable", message="取密钥材料失败（服务不可达或信封打不开）")
        return out
    algo = km.get("kdf_algo") or e2e.KDF_ALGO_V1
    out["kdf_algo"] = algo
    body = {"username": username}
    if e2e.uses_auth_hash(algo) and km.get("auth_salt"):
        body["auth_hash"] = e2e.auth_hash_hex(password, km["auth_salt"], algo)
    else:
        body["password"] = password
    data = phix_post(server, VERIFY_PATH, body)
    if data is None:
        out.update(code="unreachable", message="校验请求失败（服务不可达或信封打不开）")
        return out
    if data.get("ok"):
        out.update(ok=True, user_id=data.get("user_id"), username=data.get("username"))
        return out
    err = data.get("error") or {}
    out.update(code=err.get("code") or "unknown", message=err.get("message") or "")
    return out


def phix_verify_status(username: str, password: str) -> tuple[str, dict | None]:
    """让 phix 校验一次账号密码，**把"为什么没通过"如实带回**（供认证后端决策）。

    返回 ``(status, info)``：

    - ``("ok", {user_id, username})``  —— 通过；
    - ``("unreachable", None)``        —— 服务不可达 / 信封打不开（**不是**"账号不存在"）；
    - ``("server_key_changed", None)`` —— 服务器公钥变了，拒绝连接；
    - ``(code, None)``                 —— 其它为 phix 明确拒绝的 ``error.code``
      （如 ``bad_credentials`` / ``forbidden`` / ``rate_limited``）。

    **这里发的是 AuthHash（v2）或口令原文（v1），绝不含密钥材料。**
    """
    server = getattr(settings, "PHIX_SERVER", "")
    try:
        km = phix_post(server, KEYMATERIAL_PATH, {"username": username})
        if km is None:
            return "unreachable", None
        algo = km.get("kdf_algo") or e2e.KDF_ALGO_V1
        body = {"username": username}
        if e2e.uses_auth_hash(algo) and km.get("auth_salt"):
            body["auth_hash"] = e2e.auth_hash_hex(password, km["auth_salt"], algo)
        else:
            # v1 老账号：phix 那边存的就是口令的哈希，只能发口令原文
            body["password"] = password
        data = phix_post(server, VERIFY_PATH, body)
    except e2e.ServerKeyError:
        return "server_key_changed", None
    if data is None:
        return "unreachable", None
    if data.get("ok"):
        return "ok", {"user_id": data.get("user_id"),
                      "username": data.get("username")}
    err = data.get("error") or {}
    return err.get("code") or "unknown", None


def phix_verify(username: str, password: str) -> dict | None:
    """让 phix 校验一次账号密码。成功返回 {user_id, username}；失败/连不上返回 None。

    **注意这里发的是 AuthHash，不是口令。** 心履自己算、自己不留。
    （认证后端用 `phix_verify_status` 拿更细的原因；本函数保持旧的含糊语义。）
    """
    status, info = phix_verify_status(username, password)
    return info if status == "ok" else None


def phix_register(username: str, password: str) -> tuple[str, dict | None]:
    """现场为老用户建 phix 账号（迁移）。返回 ``(status, data)``：

    - ``("ok", {user_id, recovery_code})`` —— 注册成功（recovery_code 只在这里回传，不落盘）；
    - ``("exists", None)`` —— 账号已被注册（别人已迁过），**不要覆盖**；
    - ``("unreachable", None)`` / ``("server_key_changed", None)`` —— 连不上/公钥变了；
    - ``("rejected", body)`` —— phix 明确拒绝（参数/限流等），body 为响应体。

    生成整套 v2 密钥材料（与客户端逐字节一致，见 `phix_e2e.new_material`），
    走应用层信封（`phix_post`），与现有 verify 同一条通道。
    """
    server = getattr(settings, "PHIX_SERVER", "")
    mat = e2e.new_material(username, password)
    body = {
        "username": username, "agree": True, "device": MIGRATE_DEVICE,
        "auth_hash": mat["auth_hash"], "auth_salt": mat["auth_salt"],
        "kdf_salt": mat["kdf_salt"], "key_wrap": mat["key_wrap"],
        "key_mode": mat["key_mode"], "key_check": mat["key_check"],
        "key_check_plain": mat["key_check_plain"],
        "recovery_salt": mat["recovery_salt"],
        "recovery_wrap": mat["recovery_wrap"],
        "kdf_algo": mat["kdf_algo"],
    }
    try:
        data = phix_post(server, REGISTER_PATH, body)
    except e2e.ServerKeyError:
        return "server_key_changed", None
    if data is None:
        return "unreachable", None
    if data.get("ok"):
        return "ok", {"user_id": data.get("user_id"),
                      "recovery_code": mat["recovery_code"]}
    err = data.get("error") or {}
    msg = err.get("message") or ""
    if "已经被注册" in msg or "已经注册" in msg:
        return "exists", None
    return "rejected", data


def phix_user_id_of(user) -> int | None:
    prof = UserProfile.objects.filter(user=user).only("phix_user_id").first()
    return getattr(prof, "phix_user_id", None) if prof else None


def link_user(user, phix_user_id: int) -> None:
    """把本地账号关联到 phix 账号，并作废本地密码（之后只认 phix）。"""
    prof, _ = UserProfile.objects.get_or_create(user=user)
    prof.phix_user_id = int(phix_user_id)
    prof.save(update_fields=["phix_user_id"])
    if user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=["password"])


class PhixAuthBackend(BaseBackend):
    """见模块 docstring。放在 ``AUTHENTICATION_BACKENDS`` 的**第一位**。

    认证三段式（详见模块 docstring）：① 先问 phix → ② 明确拒绝后回落本地 →
    ③ 本地口令通过（老用户）就现场建 phix 账号完成迁移。
    """

    @staticmethod
    def user_can_authenticate(user) -> bool:
        """与 ``ModelBackend`` 同语义：被停用的账号一律拒绝。"""
        return bool(user is not None and getattr(user, "is_active", True))

    # ---------------- 内部：登录收尾 / 迁移 / 兜底 ----------------

    def _finish_phix_login(self, user, info: dict, username: str):
        """phix 认了 → 关联本地账号（没有同名账号就建影子账号）。"""
        User = get_user_model()
        if user is None:
            try:
                user = User.objects.create_user(username=username)
            except Exception as exc:  # noqa: BLE001  并发下可能撞名
                log.warning("建影子账号失败 %s：%s", username, exc)
                user = User.objects.filter(username=username).first()
                if user is None:
                    return None
        try:
            link_user(user, info["user_id"])
        except Exception as exc:  # noqa: BLE001  关联失败不该挡住登录
            log.warning("关联 phix 账号失败 %s：%s", username, exc)
        log.info("phix 登录成功并已关联：%s ↔ phix#%s", username, info["user_id"])
        return user if self.user_can_authenticate(user) else None

    def _fallback_unreachable(self, user, password: str):
        """phix **连不上**（不是"账号不存在"）时的兜底。

        **取舍（刻意记录）**：绝不把"连不上"误判成"账号不存在"去建号。
        - 已关联 phix 的账号：fail closed，拒绝登录（改了 phix 密码必须立刻生效，
          不能因为服务器挂了就放行）；
        - 未关联的老账号：仍可用本地口令登录（等同现有策略）。他们 ``phix_user_id``
          仍是空，等于天然"待迁移"——下次 phix 可连时，用本地口令登录即可走迁移。
        """
        if user is None or phix_user_id_of(user) is not None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def _stash_recovery_code(self, request, code: str | None) -> None:
        """把恢复码安全地交给用户：写进 session，登录后由页面展示一次即清除。

        **绝不**写日志、**绝不**进 URL 查询串；API 客户端（机器）登录没有可渲染的
        页面，恢复码会随其 session 失效而丢弃——这是已知取舍，见模块 docstring。
        """
        if not code:
            return
        try:
            session = getattr(request, "session", None)
        except Exception:  # noqa: BLE001  request 可能没有 session
            session = None
        if session is None:
            return
        try:
            session[RECOVERY_SESSION_KEY] = code
        except Exception as exc:  # noqa: BLE001  写不进就别挡住登录
            log.warning("恢复码写 session 失败：%s", exc)

    def _migrate_local_user(self, request, user, username: str, password: str):
        """老用户（本地口令通过、phix 无账号）→ 现场建 phix 账号并关联。

        只在注册**确实成功**后才作废本地口令；任何失败都不动本地口令。
        """
        status, data = phix_register(username, password)

        if status in ("unreachable", "server_key_changed"):
            # 连不上：不建号、不作废口令；按兜底策略允许本地口令登录。
            log.warning("迁移注册不可达，暂不迁移（保留本地口令）：%s", username)
            return user if self.user_can_authenticate(user) else None

        if status == "exists":
            # 别人已经迁过 → **不要覆盖**，改用这个口令再走一次第 1 步（verify）。
            log.info("迁移时发现 phix 已有同名账号，回退 phix 校验：%s", username)
            vstatus, info = phix_verify_status(username, password)
            if vstatus == "ok":
                return self._finish_phix_login(user, info, username)
            return None

        if status == "ok":
            try:
                link_user(user, data["user_id"])
            except Exception as exc:  # noqa: BLE001  关联失败不该挡住登录
                log.warning("迁移后关联 phix 失败 %s：%s", username, exc)
            self._stash_recovery_code(request, data.get("recovery_code"))
            log.info("老用户已迁移：%s → phix#%s", username, data["user_id"])
            return user if self.user_can_authenticate(user) else None

        # rejected：注册被拒（参数/限流等）→ 登录失败，**不动本地口令**。
        log.warning("迁移注册被拒（未建号，本地口令保留）：%s", username)
        return None

    # ---------------- 认证入口 ----------------

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not enabled():
            return None
        if not username or not password:
            return None

        User = get_user_model()
        user = User.objects.filter(username=username).first()

        # ① 先走 phix（已是 phix 用户 / 已关联账号的唯一判断依据）
        status, info = phix_verify_status(username, password)
        if status == "ok":
            return self._finish_phix_login(user, info, username)

        # phix 连不上 → 兜底（绝不误判成"账号不存在"去建号）
        if status in ("unreachable", "server_key_changed"):
            return self._fallback_unreachable(user, password)

        # ② phix 明确拒绝（账号不存在 / 凭据不对）→ 回落本地校验
        if user is None or not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None

        # ③ 本地口令通过 = 还没迁移的老用户，且手里有明文口令 → 现场迁移
        return self._migrate_local_user(request, user, username, password)

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
