"""极简内存限流：无需 Redis/额外依赖，适合单机小站。
按 (键前缀 + 客户端标识) 在时间窗内计数，超限返回 True。
进程重启计数清零；对本站的防刷场景足够。"""
import time
from collections import defaultdict, deque
from django.conf import settings

_hits = defaultdict(deque)


def _client_id(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "?")
    uid = request.user.id if getattr(request, "user", None) and request.user.is_authenticated else "anon"
    return f"{ip}:{uid}"


def is_limited(request, bucket):
    """bucket 对应 settings.RATE_LIMITS 的键。超限返回 True。"""
    cfg = getattr(settings, "RATE_LIMITS", {}).get(bucket)
    if not cfg:
        return False
    limit, window = cfg
    key = f"{bucket}:{_client_id(request)}"
    now = time.time()
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
