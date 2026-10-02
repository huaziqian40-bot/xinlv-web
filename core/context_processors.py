from .models import SiteSettings, MoodEntry, MOOD_MAP


def site_globals(request):
    """把网站设置（联系方式、危机热线）以及用户最近情绪注入所有模板。"""
    ctx = {"site": SiteSettings.load()}

    # 跨站免密登录（core/phix_sso.py）留下的两个查询串标记：
    #   ?sso_error=<原因>  免密没成功 → 登录页给一句提示（原因码不含敏感信息）
    #   ?sso=phix          刚从官网/PHL 网页端免密过来 → 顶栏说一句"已自动登录"
    get = getattr(request, "GET", None) or {}
    sso_error = (get.get("sso_error") or "").strip()[:40]
    ctx["sso_error"] = sso_error
    ctx["sso_landed"] = (get.get("sso") or "").strip() == "phix"

    # 迁移恢复码：登录后展示一次，展示完即从 session 清除（不落库、不写日志）。
    try:
        code = request.session.pop("phix_recovery_code", None)
    except Exception:  # noqa: BLE001  无 session / 已失效都当没有
        code = None
    if code:
        ctx["migration_recovery_code"] = code

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
