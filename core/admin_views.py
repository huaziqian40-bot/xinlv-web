"""给站长用的极简管理后台（/manage/）。仅限管理员（is_staff）访问。"""
import os
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render

from .models import (Song, Activity, PsychologyTip, MoodEntry, ChatMessage, SiteSettings,
                     BilibiliVideo, UserContribution, MOODS, GameConfig)
from . import limits

User = get_user_model()
AUDIO_EXT = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".aac"}


def staff_required(view):
    """未登录 -> 去登录；已登录但非管理员 -> 回首页。"""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if not request.user.is_staff:
            messages.error(request, "你没有管理员权限。")
            return redirect("/")
        return view(request, *args, **kwargs)
    return wrapper


@staff_required
def dashboard(request):
    return render(request, "manage/dashboard.html", {
        "n_songs": Song.objects.count(),
        "n_tips": PsychologyTip.objects.count(),
        "n_acts": Activity.objects.count(),
        "n_moods": MoodEntry.objects.count(),
        "n_chats": ChatMessage.objects.filter(role="user").count(),
        "n_users": User.objects.count(),
        "n_review": UserContribution.objects.filter(status="pending_admin").count(),
        "n_videos": BilibiliVideo.objects.count(),
    })


@staff_required
def videos(request):
    """管理记录心情后推送的 B 站视频。"""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            title = request.POST.get("title", "").strip()[:200]
            url = request.POST.get("url", "").strip()[:400]
            if title and url:
                err = limits.check_http_url(url)
                if err:
                    messages.error(request, err)
                else:
                    BilibiliVideo.objects.create(
                        title=title, url=url, moods=",".join(request.POST.getlist("moods")))
                    messages.success(request, f"已添加视频：{title}")
            else:
                messages.error(request, "标题和链接都要填。")
        elif action == "delete":
            get_object_or_404(BilibiliVideo, pk=request.POST.get("id")).delete()
            messages.success(request, "已删除。")
        return redirect("manage_videos")
    return render(request, "manage/videos.html",
                  {"videos": BilibiliVideo.objects.all(), "moods": MOODS})


@staff_required
def songs(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            f = request.FILES.get("audio")
            if not f:
                messages.error(request, "请先选择一个音频文件。")
            elif os.path.splitext(f.name)[1].lower() not in AUDIO_EXT:
                messages.error(request, "只支持 mp3 / m4a / flac / ogg / wav / aac 格式。")
            else:
                title = request.POST.get("title", "").strip() or os.path.splitext(f.name)[0]
                Song.objects.create(
                    title=title, artist=request.POST.get("artist", "").strip(),
                    audio=f, moods=",".join(request.POST.getlist("moods")))
                messages.success(request, f"已添加歌曲：{title}")
        elif action == "update":
            s = get_object_or_404(Song, pk=request.POST.get("id"))
            s.title = request.POST.get("title", "").strip() or s.title
            s.artist = request.POST.get("artist", "").strip()
            s.moods = ",".join(request.POST.getlist("moods"))
            s.save()
            messages.success(request, f"已更新：{s.title}")
        elif action == "delete":
            s = get_object_or_404(Song, pk=request.POST.get("id"))
            name = s.title
            if s.audio:
                s.audio.delete(save=False)
            s.delete()
            messages.success(request, f"已删除：{name}")
        return redirect("manage_songs")
    return render(request, "manage/songs.html", {"songs": Song.objects.all(), "moods": MOODS})


@staff_required
def tips(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            title = request.POST.get("title", "").strip()
            content = request.POST.get("content", "").strip()
            if title and content:
                PsychologyTip.objects.create(
                    title=title, content=content, source=request.POST.get("source", "").strip())
                messages.success(request, "已添加一条小知识。")
            else:
                messages.error(request, "标题和内容都要填哦。")
        elif action == "delete":
            get_object_or_404(PsychologyTip, pk=request.POST.get("id")).delete()
            messages.success(request, "已删除。")
        return redirect("manage_tips")
    return render(request, "manage/tips.html", {"tips": PsychologyTip.objects.all()})


@staff_required
def activities(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            text = request.POST.get("text", "").strip()
            if text:
                Activity.objects.create(text=text, moods=",".join(request.POST.getlist("moods")))
                messages.success(request, "已添加一条建议。")
            else:
                messages.error(request, "请先填写内容。")
        elif action == "delete":
            get_object_or_404(Activity, pk=request.POST.get("id")).delete()
            messages.success(request, "已删除。")
        return redirect("manage_activities")
    return render(request, "manage/activities.html",
                  {"activities": Activity.objects.all(), "moods": MOODS})


@staff_required
def site(request):
    """编辑「关于我们」（Markdown）+ 联系方式 + 危机热线 + AI 树洞提示词。"""
    s = SiteSettings.load()
    if request.method == "POST":
        s.about_content = request.POST.get("about_content", "")
        s.contact_email = request.POST.get("contact_email", "").strip()
        s.contact_phone = request.POST.get("contact_phone", "").strip()
        s.contact_wechat = request.POST.get("contact_wechat", "").strip()
        s.contact_bilibili = request.POST.get("contact_bilibili", "").strip()
        s.crisis_hotline = request.POST.get("crisis_hotline", "").strip()
        s.disclaimer_content = request.POST.get("disclaimer_content", "")
        s.ai_prompt = request.POST.get("ai_prompt", "")
        s.save()
        messages.success(request, "已保存。访客刷新页面即可看到。")
        return redirect("manage_site")
    return render(request, "manage/site.html", {"s": s})


@staff_required
def game_config(request):
    """编辑小游戏物理参数，保存后客户端下次轮询即可生效。"""
    config = GameConfig.load()
    defaults = {"gravity": 0.45, "damping": 0.994,
                "wall_bounce": 0.35, "merge_boost": 1.06}
    ranges = {
        "gravity": (0.05, 1.5),
        "damping": (0.90, 1.0),
        "wall_bounce": (0.0, 1.0),
        "merge_boost": (0.5, 2.0),
    }
    labels = {
        "gravity": "重力（下落加速度）",
        "damping": "空气阻尼",
        "wall_bounce": "墙壁和地板反弹",
        "merge_boost": "合成弹力增强",
    }
    values = {
        "gravity": request.POST.get("gravity", config.gravity),
        "damping": request.POST.get("damping", config.damping),
        "wall_bounce": request.POST.get("wall_bounce", config.wall_bounce),
        "merge_boost": request.POST.get("merge_boost", config.merge_boost),
    }
    if request.method == "POST":
        parsed = {}
        errors = []
        for key, raw in values.items():
            if not isinstance(raw, str) or not raw.strip():
                errors.append(f"{labels[key]}不能为空。")
                continue
            try:
                value = float(raw.strip())
            except (TypeError, ValueError):
                errors.append(f"{labels[key]}必须是数字。")
                continue
            import math
            if not math.isfinite(value):
                errors.append(f"{labels[key]}必须是有限数字。")
                continue
            low, high = ranges[key]
            if not low <= value <= high:
                errors.append(f"{labels[key]}必须在 {low:g} 到 {high:g} 之间。")
                continue
            parsed[key] = value
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            config.gravity = parsed["gravity"]
            config.damping = parsed["damping"]
            config.wall_bounce = parsed["wall_bounce"]
            config.merge_boost = parsed["merge_boost"]
            config.save()
            messages.success(request, "小游戏参数已保存，网页和客户端会在下次刷新配置时生效。")
            return redirect("manage_game_config")
    return render(request, "manage/game_config.html", {
        "config": config, "values": values, "defaults": defaults, "ranges": ranges,
    })


@staff_required
def users(request):
    """用户管理：封禁/解封、授予/取消管理员、查看使用记录。"""
    me = request.user
    if request.method == "POST":
        action = request.POST.get("action")
        target = get_object_or_404(User, pk=request.POST.get("id"))
        # 安全限制：不能操作自己；非超级管理员不能操作超级管理员
        if target.pk == me.pk:
            messages.error(request, "不能对自己执行此操作。")
        elif target.is_superuser and not me.is_superuser:
            messages.error(request, "无权操作超级管理员。")
        else:
            if action == "ban":
                target.is_active = False; target.save()
                messages.success(request, f"已封禁：{target.username}（该用户将无法登录）")
            elif action == "unban":
                target.is_active = True; target.save()
                messages.success(request, f"已解封：{target.username}")
            elif action == "make_admin":
                target.is_staff = True; target.save()
                messages.success(request, f"已授予管理员：{target.username}")
            elif action == "remove_admin":
                target.is_staff = False; target.save()
                messages.success(request, f"已取消管理员：{target.username}")
        return redirect("manage_users")

    rows = []
    for u in User.objects.order_by("-date_joined"):
        rows.append({
            "u": u,
            "moods": MoodEntry.objects.filter(user=u).count(),
            "chats": ChatMessage.objects.filter(user=u, role="user").count(),
        })
    return render(request, "manage/users.html", {"rows": rows, "me": me})


@staff_required
def user_moods(request, user_id):
    """查看指定用户的心情记录"""
    target = get_object_or_404(User, pk=user_id)
    moods = MoodEntry.objects.filter(user=target).order_by("-created_at")
    return render(request, "manage/user_moods.html", {
        "target": target, "moods": moods,
    })


@staff_required
def user_chats(request, user_id):
    """查看指定用户的AI树洞聊天记录"""
    target = get_object_or_404(User, pk=user_id)
    chats = ChatMessage.objects.filter(user=target).order_by("-created_at")
    return render(request, "manage/user_chats.html", {
        "target": target, "chats": chats,
    })
