import calendar
import datetime as dt
import json
from collections import Counter

import markdown as md
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from .models import MoodEntry, ChatMessage, SiteSettings, MOODS, MOOD_MAP, MOOD_KEYS
from . import recommendations, deepseek, crisis, tts, ratelimit


def _sid(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _representative_mood(entries):
    """从一天的多条记录里挑出"代表情绪"对象（用于月历/年历显示）。
    规则（按 PDF）：若有心情被重复记录，取被重复最多的那个；否则取最新一条。
    entries 需按时间升序传入。"""
    if not entries:
        return None
    counts = Counter(e.mood for e in entries)
    top_mood, top_n = counts.most_common(1)[0]
    if top_n >= 2:
        # 有重复：返回该心情中最新的那条对象
        for e in reversed(entries):
            if e.mood == top_mood:
                return e
    return entries[-1]  # 无重复：最新一条


def home(request):
    """带月历的首页。登录用户从服务器取记录；访客的记录在浏览器本地（见模板 JS）。"""
    today = dt.date.today()
    try:
        year = int(request.GET.get("y", today.year))
        month = int(request.GET.get("m", today.month))
        dt.date(year, month, 1)
    except (ValueError, TypeError):
        year, month = today.year, today.month

    entries, recent = {}, []
    if request.user.is_authenticated:
        # 取当月全部记录（一天可能多条），按规则归并出每天的"代表情绪"
        qs = MoodEntry.objects.filter(
            user=request.user, date__year=year, date__month=month).order_by("at", "created_at")
        by_day = {}
        for e in qs:
            by_day.setdefault(e.date.day, []).append(e)
        entries = {day: _representative_mood(lst) for day, lst in by_day.items()}
        recent = list(MoodEntry.objects.filter(user=request.user).order_by("-date", "-at")[:7])

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            cell = {"day": day, "entry": None, "is_today": False, "in_future": False, "iso": ""}
            if day:
                d = dt.date(year, month, day)
                cell["entry"] = entries.get(day)
                cell["is_today"] = (d == today)
                cell["in_future"] = (d > today)
                cell["iso"] = d.isoformat()
            row.append(cell)
        weeks.append(row)

    prev_m = dt.date(year, month, 1) - dt.timedelta(days=1)
    next_first = (dt.date(year, month, 28) + dt.timedelta(days=10)).replace(day=1)

    return render(request, "home.html", {
        "year": year, "month": month, "month_name": f"{year}年{month}月",
        "weeks": weeks, "weekday_labels": ["一", "二", "三", "四", "五", "六", "日"],
        "moods": MOODS, "mood_map": MOOD_MAP,
        "prev": {"y": prev_m.year, "m": prev_m.month},
        "next": {"y": next_first.year, "m": next_first.month},
        "recent": recent,
    })


@login_required
def day_entries(request):
    """返回登录用户某天的全部情绪记录（由新到旧），用于"点进某天看多条"。"""
    date_str = request.GET.get("date", "")
    try:
        date = dt.date.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({"error": "日期格式错误"}, status=400)
    qs = MoodEntry.objects.filter(user=request.user, date=date).order_by("-at", "-created_at")
    items = []
    for e in qs:
        info = MOOD_MAP.get(e.mood, {})
        t = e.at or e.created_at
        items.append({
            "mood": e.mood,
            "label": info.get("label", e.mood),
            "emoji": info.get("emoji", ""),
            "image": info.get("image", ""),
            "color": info.get("color", "#ccc"),
            "note": e.note,
            "time": timezone.localtime(t).strftime("%H:%M") if t else "",
        })
    return JsonResponse({"date": date_str, "entries": items})


@login_required
def calendar_data(request):
    """供前端月/周/年视图切换用。
    ?scope=year&y=2026        -> 返回整年每天的代表情绪（颜色点）
    ?scope=week&date=2026-06-22 -> 返回该周每天的全部记录（带时刻，供纵向排布）
    ?scope=month&y=&m=        -> 返回该月每天的代表情绪
    """
    scope = request.GET.get("scope", "month")
    u = request.user

    def rep_of(entries):
        e = _representative_mood(entries)
        if not e:
            return None
        info = MOOD_MAP.get(e.mood, {})
        return {"mood": e.mood, "emoji": info.get("emoji", ""),
                "image": info.get("image", ""),
                "color": info.get("color", "#ccc"), "label": info.get("label", e.mood)}

    if scope == "year":
        try:
            year = int(request.GET.get("y"))
        except (TypeError, ValueError):
            year = dt.date.today().year
        qs = MoodEntry.objects.filter(user=u, date__year=year).order_by("at", "created_at")
        by_day = {}
        for e in qs:
            by_day.setdefault(e.date.isoformat(), []).append(e)
        days = {iso: rep_of(lst) for iso, lst in by_day.items()}
        return JsonResponse({"scope": "year", "year": year, "days": days})

    if scope == "week":
        try:
            anchor = dt.date.fromisoformat(request.GET.get("date"))
        except (TypeError, ValueError):
            anchor = dt.date.today()
        monday = anchor - dt.timedelta(days=anchor.weekday())
        week = [monday + dt.timedelta(days=i) for i in range(7)]
        qs = MoodEntry.objects.filter(user=u, date__range=(week[0], week[6])).order_by("at", "created_at")
        by_day = {d.isoformat(): [] for d in week}
        for e in qs:
            info = MOOD_MAP.get(e.mood, {})
            t = e.at or e.created_at
            by_day.setdefault(e.date.isoformat(), []).append({
                "mood": e.mood, "emoji": info.get("emoji", ""), "image": info.get("image", ""),
                "color": info.get("color", "#ccc"),
                "label": info.get("label", e.mood), "note": e.note,
                "time": timezone.localtime(t).strftime("%H:%M") if t else "",
                "minutes": (timezone.localtime(t).hour * 60 + timezone.localtime(t).minute) if t else 0,
            })
        return JsonResponse({"scope": "week",
                             "monday": monday.isoformat(),
                             "days": [d.isoformat() for d in week],
                             "entries": by_day})

    # month
    try:
        year = int(request.GET.get("y")); month = int(request.GET.get("m"))
    except (TypeError, ValueError):
        today = dt.date.today(); year, month = today.year, today.month
    qs = MoodEntry.objects.filter(user=u, date__year=year, date__month=month).order_by("at", "created_at")
    by_day = {}
    for e in qs:
        by_day.setdefault(e.date.isoformat(), []).append(e)
    days = {iso: rep_of(lst) for iso, lst in by_day.items()}
    return JsonResponse({"scope": "month", "year": year, "month": month, "days": days})


@require_POST
@login_required
def save_mood(request):
    """登录用户保存心情到服务器（访客不会走这里，由前端 localStorage 处理）。"""
    date_str = request.POST.get("date", "")
    mood = request.POST.get("mood", "")
    note = request.POST.get("note", "").strip()[:2000]
    try:
        date = dt.date.fromisoformat(date_str)
    except ValueError:
        return HttpResponseBadRequest("日期格式错误")
    if mood not in MOOD_KEYS:
        return HttpResponseBadRequest("未知心情")
    if date > dt.date.today():
        return HttpResponseBadRequest("不能记录未来的日期")

    # 情绪强度：默认"有点"(2) / 50%
    try:
        intensity_level = int(request.POST.get("intensity_level", 2))
        intensity_level = max(1, min(4, intensity_level))
    except (ValueError, TypeError):
        intensity_level = 2
    try:
        intensity_percent = int(request.POST.get("intensity_percent", 50))
        intensity_percent = max(0, min(100, intensity_percent))
    except (ValueError, TypeError):
        intensity_percent = 50

    # 一天可记录多条，不覆盖；记录当前时刻用于排序
    MoodEntry.objects.create(
        user=request.user, date=date, mood=mood, note=note, at=timezone.now(),
        intensity_level=intensity_level, intensity_percent=intensity_percent)
    return redirect(f"/result/?mood={mood}&date={date_str}&intensity_level={intensity_level}&intensity_percent={intensity_percent}")


@require_POST
@login_required
def import_local(request):
    """把访客在本地记录的心情导入到刚登录的账号。body: {"moods": {"2026-06-18": {"mood":"sad","note":""}}}"""
    try:
        data = json.loads(request.body).get("moods", {})
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "格式错误"}, status=400)
    n = 0
    for date_str, item in data.items():
        try:
            date = dt.date.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue
        mood = (item or {}).get("mood")
        if mood not in MOOD_KEYS or date > dt.date.today():
            continue
        MoodEntry.objects.create(
            user=request.user, date=date, mood=mood,
            note=(str(item.get("note") or "").strip())[:2000],
            intensity_level=max(1, min(4, _int(item.get("intensity_level"), 2))),
            intensity_percent=max(0, min(100, _int(item.get("intensity_percent"), 50))))
        n += 1
    return JsonResponse({"imported": n})


def _int(v, default):
    """安全解析整数，失败返回默认值。"""
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def result(request):
    """推荐页。?mood=anxious 即可工作（访客也能用）；登录用户带 ?date= 时还会显示当时的备注。"""
    mood = request.GET.get("mood", "")
    date_str = request.GET.get("date", "")
    note = ""

    # 读取情绪强度参数
    try:
        intensity_level = int(request.GET.get("intensity_level", 2))
        intensity_level = max(1, min(4, intensity_level))
    except (ValueError, TypeError):
        intensity_level = 2
    try:
        intensity_percent = int(request.GET.get("intensity_percent", 50))
        intensity_percent = max(0, min(100, intensity_percent))
    except (ValueError, TypeError):
        intensity_percent = 50

    if mood not in MOOD_KEYS:
        # 兜底：登录用户只给了日期时，按账号查当天心情
        if request.user.is_authenticated and date_str:
            try:
                e = MoodEntry.objects.filter(
                    user=request.user, date=dt.date.fromisoformat(date_str)).order_by('-at', '-created_at').first()
                if e:
                    mood, note = e.mood, e.note
                    intensity_level = e.intensity_level
                    intensity_percent = e.intensity_percent
            except ValueError:
                pass
    if mood not in MOOD_KEYS:
        return redirect("/")

    if request.user.is_authenticated and date_str and not note:
        try:
            e = MoodEntry.objects.filter(
                user=request.user, date=dt.date.fromisoformat(date_str)).order_by('-at', '-created_at').first()
            if e:
                note = e.note
                intensity_level = e.intensity_level
                intensity_percent = e.intensity_percent
        except ValueError:
            pass

    date_label = ""
    if date_str:
        try:
            d = dt.date.fromisoformat(date_str)
            date_label = f"{d.month}月{d.day}日"
        except ValueError:
            pass

    rec = recommendations.build(mood)
    return render(request, "result.html", {"rec": rec, "note": note, "date_label": date_label,
                                           "intensity_level": intensity_level,
                                           "intensity_percent": intensity_percent})


def disclaimer(request):
    s = SiteSettings.load()
    custom_html = ""
    if s.disclaimer_content.strip():
        custom_html = mark_safe(md.markdown(
            s.disclaimer_content, extensions=["extra", "nl2br", "sane_lists"]))
    return render(request, "disclaimer.html", {"custom_html": custom_html})


def download(request):
    """下载页面：展示各平台客户端下载链接。"""
    android_versions = [
        ("1.2.31", "download/android/xinlv-1.2.31.apk"),
        ("1.2.30", "download/android/xinlv-1.2.30.apk"),
        ("1.2.29", "download/android/xinlv-1.2.29.apk"),
        ("1.2.28", "download/android/xinlv-1.2.28.apk"),
        ("1.2.27", "download/android/xinlv-1.2.27.apk"),
        ("1.2.26", "download/android/xinlv-1.2.26.apk"),
        ("1.2.24", "download/android/xinlv-1.2.24.apk"),
        ("1.2.23", "download/android/xinlv-1.2.23.apk"),
        ("1.2.22", "download/android/xinlv-1.2.22.apk"),
        ("1.2.21", "download/android/xinlv-1.2.21.apk"),
        ("1.2.20", "download/android/xinlv-1.2.20.apk"),
        ("1.2.19", "download/android/xinlv-1.2.19.apk"),
        ("1.2.18", "download/android/xinlv-1.2.18.apk"),
        ("1.2.17", "download/android/xinlv-1.2.17.apk"),
        ("1.2.11", "download/android/xinlv-1.2.11.apk"),
        ("1.2.10", "download/android/xinlv-1.2.10.apk"),
    ]
    windows_versions = [
        ("1.1.5", "download/windows/xinlv-1.1.5.exe"),
        ("1.1.4", "download/windows/xinlv-1.1.4.exe"),
        ("1.1.3", "download/windows/xinlv-1.1.3.exe"),
        ("1.1.2", "download/windows/xinlv-1.1.2.exe"),
        ("1.0.4", "download/windows/xinlv-1.0.4.exe"),
        ("1.0.3", "download/windows/xinlv-1.0.3.exe"),
        ("1.0.2", "download/windows/xinlv-1.0.2.exe"),
    ]
    macos_versions = [
        ("1.1.5", "download/macos/心履-1.1.5.dmg"),
        ("1.1.4", "download/macos/心履-1.1.4.dmg"),
        ("1.1.3", "download/macos/心履-1.1.3.dmg"),
        ("1.1.2", "download/macos/心履-1.1.2.dmg"),
        ("1.0.9", "download/macos/心履-1.0.9.dmg"),
        ("1.0.7", "download/macos/心履-1.0.7.dmg"),
    ]
    return render(request, "download.html", {
        "android_versions": android_versions,
        "windows_versions": windows_versions,
        "macos_versions": macos_versions,
    })


def game(request):
    """情绪小西瓜：仿合成大西瓜的放松小游戏，纯前端 Canvas 实现，不涉及数据存储。"""
    return render(request, "game.html")


def about(request):
    s = SiteSettings.load()
    html = md.markdown(s.about_content or "", extensions=["extra", "nl2br", "sane_lists"])
    return render(request, "about.html", {"about_html": mark_safe(html)})


# ---------- AI 树洞 ----------
def _build_mood_context(request):
    """构建用户最近心情的上下文信息，供 AI 树洞感知。
    返回一段自然语言描述，或 None（无记录时）。"""
    if not request.user.is_authenticated:
        return None
    recent = list(MoodEntry.objects.filter(user=request.user)
                  .order_by("-date", "-at")[:5])
    if not recent:
        return None
    parts = []
    for e in reversed(recent):
        info = MOOD_MAP.get(e.mood, {})
        label = info.get("label", e.mood)
        level_names = {1: "略微", 2: "有点", 3: "相当", 4: "十分"}
        level_str = level_names.get(e.intensity_level, "")
        d = e.date.strftime("%m月%d日")
        note = f"，备注：{e.note[:60]}" if e.note else ""
        parts.append(f"{d} 记录了「{label}」{level_str}{note}")
    return "以下是用户最近的心情记录，供你在陪伴时自然、轻描淡写地提起，不要罗列或逐条分析：" + "；".join(parts)


def _chat_qs(request):
    if request.user.is_authenticated:
        return ChatMessage.objects.filter(user=request.user)
    return ChatMessage.objects.filter(session_key=_sid(request), user__isnull=True)


def confidant(request):
    return render(request, "confidant.html", {"history": _chat_qs(request)})


@require_POST
def confidant_send(request):
    if ratelimit.is_limited(request, "confidant"):
        return JsonResponse({"reply": "你发得有点快啦，休息一下下再聊好吗？"}, status=200)
    try:
        text = json.loads(request.body).get("message", "").strip()
    except (json.JSONDecodeError, AttributeError):
        text = request.POST.get("message", "").strip()
    if not text:
        return JsonResponse({"error": "空消息"}, status=400)
    # 消息长度上限 4000 字，防费用 DoS
    text = text[:4000]

    owner = {"user": request.user} if request.user.is_authenticated else {"session_key": _sid(request)}
    ChatMessage.objects.create(role="user", content=text, **owner)

    # 安全网：检测到自我伤害/自杀风险 -> 强制停止 AI 咨询，改为提供求助资源
    if crisis.is_crisis(text):
        ChatMessage.objects.create(role="assistant", content=crisis.SUPPORT_MESSAGE, **owner)
        return JsonResponse({
            "crisis": True,
            "reply": crisis.SUPPORT_MESSAGE,
            "hotline": SiteSettings.load().crisis_hotline or "12356",
        })

    recent = list(_chat_qs(request).order_by("-created_at")[:20])
    recent.reverse()
    history = [{"role": m.role, "content": m.content} for m in recent]

    # 注入用户最近心情上下文，让 AI 知道用户今天/最近的心情
    mood_context = _build_mood_context(request)
    if mood_context:
        # 插入到历史最前面（但放在 system prompt 之后），作为用户状态参考
        history.insert(0, {"role": "system", "content": mood_context})

    reply, err = deepseek.chat(history)
    if reply is None:
        reply = err
    else:
        ChatMessage.objects.create(role="assistant", content=reply, **owner)
    return JsonResponse({"reply": reply})


@require_POST
def confidant_clear(request):
    _chat_qs(request).delete()
    return JsonResponse({"ok": True})


@require_POST
def tts_speak(request):
    """把一段文字合成为自然人声，返回 base64 mp3 给前端播放。"""
    if ratelimit.is_limited(request, "tts"):
        return JsonResponse({"error": "请求太频繁，请稍候再试。"}, status=200)
    try:
        text = json.loads(request.body).get("text", "")
    except (json.JSONDecodeError, AttributeError):
        text = request.POST.get("text", "")
    # 类型安全防护：非字符串不处理
    if not isinstance(text, str):
        return JsonResponse({"error": "文字格式不正确。"}, status=200)
    audio, err = tts.synthesize(text)
    if err:
        return JsonResponse({"error": err}, status=200)
    return JsonResponse({"audio": audio})
