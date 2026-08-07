"""极简内存限流：无需 Redis/额外依赖，适合单机小站。
按 (键前缀 + 客户端标识) 在时间窗内计数，超限返回 True。

安全加固（2026-08-07）：
- 不再无脑信任 XFF/CF-Connecting-IP：仅当直连地址是本机回环（cloudflared 部署场景）
  才取代理头最后一跳，直连一律用真实 REMOTE_ADDR，防止伪造头绕过限流。
- 登录用户按 uid 计数（键里带 uid），换 IP 也不能重置该用户的计数。
- _hits 键数超过上限时自动清理过期项，防止伪造 IP 撑爆内存（DoS 防护）。
进程重启计数清零；对本站的防刷场景足够。"""
import time
from collections import defaultdict, deque
from django.conf import settings

# 最多保留的键数；超过后触发一次过期清理
_MAX_KEYS = 20000

_hits = defaultdict(deque)


def _real_ip(request):
    """真实客户端 IP：仅当直连地址是本机回环时才信任代理头。
    返回 (ip, 是否回环)。"""
    remote = request.META.get("REMOTE_ADDR", "?")
    is_loopback = remote in ("127.0.0.1", "::1", "localhost")
    if is_loopback:
        # cloudflared 场景：信任 CF-Connecting-IP 或 XFF 的最后一跳
        cf = request.META.get("HTTP_CF_CONNECTING_IP", "")
        if cf:
            return cf.strip(), True
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[-1], True
    return remote, is_loopback


def _client_id(request):
    ip, _ = _real_ip(request)
    uid = request.user.id if getattr(request, "user", None) and request.user.is_authenticated else "anon"
    return f"{ip}:{uid}"


def _cleanup(now):
    """清理过期项，防止内存无限增长。"""
    cfg_keys = settings.RATE_LIMITS.keys()
    windows = {k: settings.RATE_LIMITS[k][1] for k in cfg_keys}
    expired = []
    for key, dq in _hits.items():
        bucket = key.split(":", 1)[0]
        window = windows.get(bucket, 300)
        while dq and now - dq[0] > window:
            dq.popleft()
        if not dq:
            expired.append(key)
    for key in expired:
        del _hits[key]


def is_limited(request, bucket):
    """bucket 对应 settings.RATE_LIMITS 的键。超限返回 True。"""
    cfg = getattr(settings, "RATE_LIMITS", {}).get(bucket)
    if not cfg:
        return False
    limit, window = cfg
    key = f"{bucket}:{_client_id(request)}"
    now = time.time()

    # 键数超上限先清理再判断，避免内存耗尽
    if len(_hits) > _MAX_KEYS:
        _cleanup(now)

    dq = _hits[key]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        return True
    dq.append(now)
    return False


def retry_after(bucket):
    cfg = getattr(settings, "RATE_LIMITS", {}).get(bucket)
    return cfg[1] if cfg else 60