from .models import SiteSettings, MoodEntry, MOOD_MAP


def site_globals(request):
    """把网站设置（联系方式、危机热线）以及用户最近情绪注入所有模板。"""
    ctx = {"site": SiteSettings.load()}

    # 注入最近一条情绪（用于全站视觉风格）
    if request.user.is_authenticated:
        latest = MoodEntry.objects.filter(user=request.user).order_by("-date", "-at").first()
    else:
        latest = None

    if latest:
        info = MOOD_MAP.get(latest.mood, {})
        ctx["latest_mood"] = {
            "key": latest.mood,
            "label": info.get("label", latest.mood),
            "emoji": info.get("emoji", ""),
            "image": info.get("image", ""),
            "color": info.get("color", "#ccc"),
            "valence": info.get("valence", 0),
            "intensity_level": latest.intensity_level,
            "intensity_percent": latest.intensity_percent,
        }
    else:
        ctx["latest_mood"] = None

    return ctx
