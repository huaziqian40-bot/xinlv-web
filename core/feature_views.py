"""第三/四条功能：用户主页+徽章、用户上传内容+AI审核、管理员复审。"""
import json
import datetime as dt

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import (MoodEntry, UserProfile, UserContribution,
                     Song, Activity, PsychologyTip, BilibiliVideo,
                     MOODS, MOOD_KEYS, MOOD_MAP, compute_streak_and_badges)
from . import ratelimit, limits

User = get_user_model()


def get_profile(user):
    prof, _ = UserProfile.objects.get_or_create(user=user)
    return prof


# ---------------- 用户主页 + 徽章 ----------------
@login_required
def profile(request):
    return _render_profile(request, request.user, own=True)


def profile_public(request, username):
    target = get_object_or_404(User, username=username)
    return _render_profile(request, target, own=(request.user == target))


def _render_profile(request, target, own):
    prof = get_profile(target)
    streak, badges = compute_streak_and_badges(target)
    # 情绪记录仅本人可见，其他人看不到具体记录
    entries = []
    if own:
        entries = list(MoodEntry.objects.filter(user=target).order_by("-date", "-at")[:50])
        for e in entries:
            e.meta = MOOD_MAP.get(e.mood, {})
    total = MoodEntry.objects.filter(user=target).count()
    return render(request, "profile.html", {
        "target": target, "prof": prof, "own": own,
        "streak": streak, "badges": badges, "entries": entries, "total": total,
    })


@login_required
@require_POST
def profile_edit(request):
    prof = get_profile(request.user)
    prof.bio = request.POST.get("bio", "").strip()[:200]
    f = request.FILES.get("avatar")
    if f:
        err = limits.check_image(f)
        if err:
            messages.error(request, err)
            return redirect("profile")
        prof.avatar = f
    prof.save()
    messages.success(request, "资料已更新。")
    return redirect("profile")


# ---------------- 用户上传内容 + AI 审核 ----------------
AI_REVIEW_PROMPT = """你是内容审核助手。判断用户投稿到"心情舒缓网站"的内容是否可以发布。
通过标准：内容健康、无害、与情绪疗愈/心理相关，且与投稿者选择的情绪标签相符。
拒绝标准：含有害、危险、色情、广告、辱骂、与心理疗愈无关，或与所选情绪明显不符的内容。
只输出一个 JSON：{"pass": true/false, "reason": "简短中文理由"}，不要输出别的。"""


def ai_review(kind, title, content, moods):
    """返回 (verdict, reason)。verdict ∈ {'pass','fail','uncertain'}。
    未配置 key 或出错时返回 uncertain -> 转管理员复审。"""
    if not settings.DEEPSEEK_API_KEY:
        return "uncertain", "未配置AI审核，转人工"
    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": AI_REVIEW_PROMPT},
            {"role": "user", "content": f"类型：{kind}\n标题：{title}\n内容：{content}\n情绪标签：{moods}"},
        ],
        "temperature": 0,
        "max_tokens": 200,
        "thinking": {"type": "disabled"},
    }
    try:
        r = requests.post(f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                          headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                                   "Content-Type": "application/json"},
                          json=payload, timeout=30)
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"].strip()
        txt = txt.replace("```json", "").replace("```", "").strip()
        data = json.loads(txt)
        return ("pass" if data.get("pass") else "fail"), (data.get("reason") or "")[:300]
    except Exception as e:
        return "uncertain", f"AI审核异常，转人工：{e}"


@login_required
def contribute(request):
    if request.method == "POST":
        if ratelimit.is_limited(request, "contribute"):
            messages.error(request, "提交太频繁了，请过几分钟再试。")
            return redirect("contribute")
        kind = request.POST.get("kind")
        title = request.POST.get("title", "").strip()[:200]
        content = request.POST.get("content", "").strip()[:4000]
        source = request.POST.get("source", "").strip()[:200]
        audio = request.FILES.get("audio")

        # 小知识默认在正面情绪展示，不需要选情绪；出处栏仅小知识有
        if kind == "tip":
            moods = ""
            source = request.POST.get("source", "").strip()[:200]
        else:
            source = ""
            # 只收白名单内的合法情绪键，防任意字段注入
            moods = ",".join(m for m in request.POST.getlist("moods") if m in MOOD_KEYS)

        if kind not in dict(UserContribution.KIND_CHOICES):
            messages.error(request, "请选择类型。")
            return redirect("contribute")
        # music 需要音频文件；其它类型需要文字内容/链接
        if kind == "music":
            if not audio:
                messages.error(request, "请选择要上传的音频文件。")
                return redirect("contribute")
            err = limits.check_audio(audio)
            if err:
                messages.error(request, err)
                return redirect("contribute")
        elif kind == "video":
            if not content:
                messages.error(request, "请填写视频链接。")
                return redirect("contribute")
            err = limits.check_http_url(content)
            if err:
                messages.error(request, err)
                return redirect("contribute")
        elif not content:
            messages.error(request, "请填写内容。")
            return redirect("contribute")

        c = UserContribution.objects.create(
            user=request.user, kind=kind, title=title, content=content,
            moods=moods, source=source)
        if audio:
            c.audio = audio
            c.save()

        review_text = content or title or (audio.name if audio else "")
        verdict, reason = ai_review(c.get_kind_display(), title, review_text, moods)
        c.ai_reason = reason
        if verdict == "pass":
            c.status = "approved"
            _publish_contribution(c)
            messages.success(request, "AI 审核通过，已发布，谢谢你的分享！")
        elif verdict == "fail":
            c.status = "pending_admin"   # 未过也给人工兜底
            messages.error(request, f"AI 审核未通过：{reason}。已转管理员复审。")
        else:
            c.status = "pending_admin"
            messages.info(request, "已提交，等待管理员审核。")
        c.save()
        return redirect("contribute")

    mine = UserContribution.objects.filter(user=request.user)[:30]
    return render(request, "contribute.html",
                  {"moods": MOODS, "kinds": UserContribution.KIND_CHOICES, "mine": mine})


def _publish_contribution(c):
    """审核通过后，把投稿并入正式内容库。"""
    if c.kind == "tip":
        PsychologyTip.objects.create(
            title=c.title or "用户分享", content=c.content,
            source=c.source or f"用户 {c.user.username}")
    elif c.kind == "activity":
        Activity.objects.create(text=c.content, moods=c.moods)
    elif c.kind == "video":
        BilibiliVideo.objects.create(title=c.title or "用户分享", url=c.content, moods=c.moods)
    elif c.kind == "music" and c.audio:
        Song.objects.create(title=c.title or "用户分享", artist=c.user.username,
                            audio=c.audio.name, moods=c.moods)


# ---------------- 管理员复审 ----------------
def _staff_required(view):
    from functools import wraps
    @wraps(view)
    def w(request, *a, **k):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if not request.user.is_staff:
            return redirect("/")
        return view(request, *a, **k)
    return w


@_staff_required
def review_queue(request):
    if request.method == "POST":
        c = get_object_or_404(UserContribution, pk=request.POST.get("id"))
        action = request.POST.get("action")
        if action == "approve":
            c.status = "approved"; c.save(); _publish_contribution(c)
            messages.success(request, "已通过并发布。")
        elif action == "reject":
            c.status = "rejected"; c.save()
            messages.success(request, "已拒绝。")
        return redirect("review_queue")
    pending = UserContribution.objects.filter(status="pending_admin")
    return render(request, "manage/review.html", {"pending": pending})


# ---------------- 多语言切换 ----------------
@require_POST
def set_language(request):
    lang = request.POST.get("lang", "zh")
    lang = "en" if lang == "en" else "zh"
    request.session["lang"] = lang
    if request.user.is_authenticated:
        prof = get_profile(request.user); prof.language = lang; prof.save()
    # 防 Referer 开放重定向：只允许站内跳转
    ref = request.META.get("HTTP_REFERER", "/")
    if not ref.startswith("/") and not url_has_allowed_host_and_scheme(ref, allowed_hosts=None):
        ref = "/"
    return redirect(ref or "/")


def badges_page(request):
    from .models import BADGES, compute_streak_and_badges
    my_streak = 0
    if request.user.is_authenticated:
        my_streak, _ = compute_streak_and_badges(request.user)
    badge_list = [{"days": t, "emoji": e, "name": n, "image": img,
                   "remain": max(0, t - my_streak)} for (t, e, n, img, _d) in BADGES]
    return render(request, "badges.html", {"badge_list": badge_list, "my_streak": my_streak})
