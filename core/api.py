"""客户端（安卓/桌面）REST API，前缀 /api/v1/。

设计要点：
- 认证：Authorization: Bearer <ApiToken.key>。不用 session/cookie，因此全部 csrf_exempt。
- 同步模型：心情记录是追加型数据，客户端离线创建时生成 uuid，按 uuid 去重互传；
  更新/删除按 updated_at 最新者赢（last-write-wins）；删除是墓碑（deleted=True），
  不真删，防止同步复活。网页端默认管理器 AliveManager 自动排除墓碑。
- 复用网页端现有逻辑：危机拦截 crisis、AI 对话 deepseek、推荐 recommendations、
  连胜徽章 compute_streak_and_badges，客户端行为与网页端保持一致。
- 时间一律 ISO8601（带时区）；客户端自行转本地时区显示。
"""
import datetime as dt
import json
from functools import wraps

from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (MoodEntry, ChatMessage, Song, Activity, PsychologyTip,
                     BilibiliVideo, SiteSettings, ApiToken, MOODS, MOOD_KEYS,
                     compute_streak_and_badges)
from . import recommendations, deepseek, crisis, ratelimit

API_VERSION = "v1"
PUSH_BATCH_LIMIT = 500        # 单次推送最多条数，防恶意大包


# ---------- 基础工具 ----------
def _json_body(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return None


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


def _iso(z):
    return z.isoformat() if z else None


def _parse_dt(s):
    """解析 ISO8601 时间；不带时区按 UTC 处理；失败返回 None。"""
    if not s:
        return None
    try:
        z = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if timezone.is_naive(z):
        z = timezone.make_aware(z, dt.timezone.utc)
    return z


def _entry_dict(e):
    return {
        "uuid": e.uuid, "date": e.date.isoformat(), "at": _iso(e.at),
        "mood": e.mood, "note": e.note, "deleted": e.deleted,
        "created_at": _iso(e.created_at), "updated_at": _iso(e.updated_at),
    }


def api_login_required(view):
    """Bearer Token 认证装饰器。通过后 request.api_user / request.api_token 可用。"""
    @wraps(view)
    @csrf_exempt          # token 认证不用 cookie，天然免疫 CSRF
    def wrapper(request, *args, **kwargs):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return _err("未登录或令牌缺失", 401)
        token = (ApiToken.objects.select_related("user")
                 .filter(key=auth[7:].strip()).first())
        if not token:
            return _err("令牌无效或已注销", 401)
        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])
        request.api_token = token
        request.api_user = token.user
        # 网页端限流工具按 request.user 识别用户，这里兼容复用
        request.user = token.user
        return view(request, *args, **kwargs)
    return wrapper


# ---------- 连通性探测（免认证，客户端用来判断在线/离线）----------
def ping(request):
    return JsonResponse({
        "ok": True, "version": API_VERSION,
        "server_time": timezone.now().isoformat(),
    })


# ---------- 登录 / 注销 ----------
@csrf_exempt
@require_POST
def login(request):
    """{username, password, device?} -> {token, username, streak}
    令牌长期有效（除非注销），客户端本地保存即可。"""
    if ratelimit.is_limited(request, "api_login"):
        return _err("尝试太频繁了，过几分钟再试。", 429)
    data = _json_body(request)
    if not data:
        return _err("请求格式错误")
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    device = (data.get("device") or "")[:100]
    if not username or not password:
        return _err("请输入账号和密码")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return _err("账号或密码不对", 401)
    token = ApiToken.mint(user, device)
    streak, _ = compute_streak_and_badges(user)
    return JsonResponse({"token": token.key, "username": user.username,
                         "streak": streak})


@require_POST
@api_login_required
def logout(request):
    """注销当前设备令牌（不影响其他设备）。"""
    request.api_token.delete()
    return JsonResponse({"ok": True})


# ---------- 心情记录同步 ----------
@api_login_required
def sync_pull(request):
    """?since=<ISO8601> 增量拉取（含墓碑）；不带 since 为全量。
    返回 {server_time, entries:[...]}。客户端应保存 server_time 作为下次的 since。"""
    since = _parse_dt(request.GET.get("since"))
    qs = MoodEntry.all_objects.filter(user=request.api_user)
    if since:
        qs = qs.filter(updated_at__gt=since)
    qs = qs.order_by("updated_at")[:2000]
    return JsonResponse({
        "server_time": timezone.now().isoformat(),
        "entries": [_entry_dict(e) for e in qs],
    })


@require_POST
@api_login_required
def sync_push(request):
    """{entries:[{uuid, date, at?, mood, note?, updated_at?, deleted?}]}
    按 uuid upsert；已存在时 updated_at 较新者赢。逐条处理，单条失败不影响其他。
    返回 {saved, updated, skipped, errors, server_time}。"""
    data = _json_body(request)
    if not data or not isinstance(data.get("entries"), list):
        return _err("请求格式错误：需要 entries 数组")
    items = data["entries"][:PUSH_BATCH_LIMIT]
    u = request.api_user
    saved = updated = skipped = 0
    errors = []
    today = dt.date.today()

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": i, "error": "条目格式错误"})
            continue
        uid = str(item.get("uuid") or "")[:36]
        if not uid:
            errors.append({"index": i, "error": "缺少 uuid"})
            continue
        try:
            date = dt.date.fromisoformat(str(item.get("date") or ""))
        except ValueError:
            errors.append({"index": i, "uuid": uid, "error": "日期格式错误"})
            continue
        mood = item.get("mood") or ""
        deleted = bool(item.get("deleted"))
        if not deleted:     # 墓碑之外的记录必须字段合法
            if mood not in MOOD_KEYS:
                errors.append({"index": i, "uuid": uid, "error": "未知心情"})
                continue
            if date > today:
                errors.append({"index": i, "uuid": uid, "error": "不能记录未来的日期"})
                continue
        note = (item.get("note") or "").strip()
        at = _parse_dt(item.get("at"))
        incoming_ts = _parse_dt(item.get("updated_at")) or timezone.now()

        existing = MoodEntry.all_objects.filter(user=u, uuid=uid).first()
        if existing:
            if incoming_ts <= existing.updated_at:
                skipped += 1      # 服务器上的更新或相同，客户端这条是旧的
                continue
            existing.date = date
            existing.at = at or existing.at
            existing.mood = mood if mood in MOOD_KEYS else existing.mood
            existing.note = note
            existing.deleted = deleted
            existing.save()       # auto_now 会把 updated_at 刷成现在
            updated += 1
        else:
            if deleted:
                skipped += 1      # 删除一条服务器上没有的记录，无需建墓碑
                continue
            MoodEntry.all_objects.create(
                user=u, uuid=uid, date=date, at=at or timezone.now(),
                mood=mood, note=note)
            saved += 1

    return JsonResponse({
        "saved": saved, "updated": updated, "skipped": skipped,
        "errors": errors, "server_time": timezone.now().isoformat(),
    })


# ---------- 推荐内容目录（客户端离线缓存用）----------
@api_login_required
def catalog(request):
    """全量目录：心情定义 + 音乐/建议/小知识/视频。数据量小（站长手工维护），
    客户端登录后拉一次缓存到本地，离线也能给推荐。"""
    def abs_url(f):
        try:
            return request.build_absolute_uri(f.url)
        except Exception:
            return ""
    return JsonResponse({
        "moods": [{"key": m[0], "label": m[1], "emoji": m[2],
                   "color": m[3], "valence": m[4]} for m in MOODS],
        "songs": [{"id": s.id, "title": s.title, "artist": s.artist,
                   "url": abs_url(s.audio), "moods": s.mood_list()}
                  for s in Song.objects.all()],
        "activities": [{"id": a.id, "text": a.text, "moods": a.mood_list()}
                       for a in Activity.objects.all()],
        "tips": [{"id": t.id, "title": t.title, "content": t.content,
                  "source": t.source} for t in PsychologyTip.objects.all()],
        "videos": [{"id": v.id, "title": v.title, "url": v.url,
                    "moods": v.mood_list()} for v in BilibiliVideo.objects.all()],
    })


@api_login_required
def recommend(request):
    """?mood=xxx -> 与网页端结果页同一套推荐逻辑（recommendations.build）。"""
    mood = request.GET.get("mood", "")
    if mood not in MOOD_KEYS:
        return _err("未知心情")
    rec = recommendations.build(mood)
    v = rec["video"]
    return JsonResponse({
        "mood": mood, "info": rec["info"], "valence": rec["valence"],
        "songs": [{"title": s.title, "artist": s.artist,
                   "url": request.build_absolute_uri(s.audio.url)}
                  for s in rec["songs"]],
        "activities": [a.text for a in rec["activities"]],
        "tips": [{"title": t.title, "content": t.content, "source": t.source}
                 for t in rec["tips"]],
        "practice": rec["practice"],
        "video": ({"title": v.title, "url": v.url, "embed_url": v.embed_url}
                  if v else None),
    })


# ---------- AI 树洞（仅联网；危机硬拦截与网页端一致）----------
@require_POST
@api_login_required
def chat(request):
    """{message} -> {reply}；命中危机词 -> {crisis:true, reply, hotline}，不发 AI。"""
    if ratelimit.is_limited(request, "confidant"):
        return JsonResponse({"reply": "你发得有点快啦，休息一下下再聊好吗？"})
    data = _json_body(request)
    text = ((data or {}).get("message") or "").strip()
    if not text:
        return _err("空消息")

    u = request.api_user
    ChatMessage.objects.create(user=u, role="user", content=text)

    # 安全网：检测到自我伤害/自杀风险 -> 强制停止 AI 咨询，改为提供求助资源
    if crisis.is_crisis(text):
        ChatMessage.objects.create(user=u, role="assistant",
                                   content=crisis.SUPPORT_MESSAGE)
        return JsonResponse({
            "crisis": True,
            "reply": crisis.SUPPORT_MESSAGE,
            "hotline": SiteSettings.load().crisis_hotline or "12356",
        })

    recent = list(ChatMessage.objects.filter(user=u)
                  .order_by("-created_at")[:20])
    recent.reverse()
    history = [{"role": m.role, "content": m.content} for m in recent]
    reply, err = deepseek.chat(history)
    if reply is None:
        reply = err      # 错误提示语直接当回复返回，客户端无感
    else:
        ChatMessage.objects.create(user=u, role="assistant", content=reply)
    return JsonResponse({"reply": reply})


@api_login_required
def chat_history(request):
    """最近 50 条对话（升序），客户端进入聊天页时拉取。"""
    qs = ChatMessage.objects.filter(user=request.api_user)
    msgs = list(qs.order_by("-created_at")[:50])
    msgs.reverse()
    return JsonResponse({"messages": [
        {"role": m.role, "content": m.content,
         "created_at": _iso(m.created_at)} for m in msgs]})


@require_POST
@api_login_required
def chat_clear(request):
    ChatMessage.objects.filter(user=request.api_user).delete()
    return JsonResponse({"ok": True})


# ---------- 个人数据 ----------
@api_login_required
def profile(request):
    """{username, bio, avatar_url, streak, badges, total_entries, date_joined}"""
    u = request.api_user
    streak, badges = compute_streak_and_badges(u)
    prof = getattr(u, "profile", None)
    avatar_url = ""
    if prof and prof.avatar:
        try:
            avatar_url = request.build_absolute_uri(prof.avatar.url)
        except Exception:
            avatar_url = ""
    return JsonResponse({
        "username": u.username,
        "bio": prof.bio if prof else "",
        "language": prof.language if prof else "zh",
        "avatar_url": avatar_url,
        "streak": streak,
        "badges": badges,
        "total_entries": MoodEntry.objects.filter(user=u).count(),
        "date_joined": _iso(u.date_joined),
    })
