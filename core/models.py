from django.conf import settings
from django.db import models
from django.db.models import Q

import uuid as _uuid


# ---- 心情定义 ----
# valence: 1 = 正面, 0 = 中性, -1 = 负面
MOODS = [
    ("happy",    "开心",  "😄", "#FFD56B",  1),
    ("calm",     "平静",  "🙂", "#9BD1C6",  1),
    ("excited",  "兴奋",  "🤩", "#FF9F68",  1),
    ("grateful", "感恩",  "🥰", "#F7A6C4",  1),
    ("tired",    "疲惫",  "😪", "#A6A6C9", -1),
    ("anxious",  "焦虑",  "😟", "#7FA6E8", -1),
    ("sad",      "难过",  "😢", "#6D8FB8", -1),
    ("angry",    "愤怒",  "😠", "#E8736B", -1),
    ("lonely",   "孤独",  "🌧️", "#8E94B8", -1),
    ("numb",     "麻木",  "😶", "#B0B0B0",  0),
]
MOOD_KEYS = [m[0] for m in MOODS]
MOOD_MAP = {m[0]: {"label": m[1], "emoji": m[2], "color": m[3], "valence": m[4]} for m in MOODS}


class AliveManager(models.Manager):
    """默认管理器：自动排除已软删除（墓碑）的记录。
    网页端所有现有查询都不用改；API 同步需要看墓碑时用 all_objects。"""
    def get_queryset(self):
        return super().get_queryset().filter(deleted=False)


class MoodEntry(models.Model):
    """一条心情记录。
    登录用户：按 user 存（可跨设备同步）。
    未登录访客：不存这里，存在浏览器 localStorage。
    session_key 字段保留作历史兼容，新数据一般为空。
    uuid：客户端离线创建时生成，全端同步去重的依据（追加型数据，无冲突合并）。
    deleted：软删除墓碑。客户端删记录不真删，置位后参与同步，防止同步复活。
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.CASCADE, related_name="moods")
    session_key = models.CharField(max_length=40, blank=True, default="", db_index=True)
    uuid = models.CharField(max_length=36, unique=True, default=_uuid.uuid4, db_index=True)
    date = models.DateField(db_index=True)
    at = models.DateTimeField(null=True, blank=True, db_index=True,
                              help_text="这条情绪的记录时刻（用于一天内多条排序）")
    mood = models.CharField(max_length=20, choices=[(m[0], m[1]) for m in MOODS])
    note = models.TextField(blank=True, default="")
    deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AliveManager()
    all_objects = models.Manager()   # 含墓碑，仅供 API 同步使用

    class Meta:
        # 一天可记录多条；按日期倒序、同日内按记录时刻正序
        ordering = ["-date", "at"]

    @property
    def info(self):
        return MOOD_MAP.get(self.mood, {})

    def __str__(self):
        return f"{self.date} {self.mood}"


class ApiToken(models.Model):
    """客户端（安卓/桌面）登录令牌。一个用户可有多个（多设备），互不踢出。"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="api_tokens")
    key = models.CharField(max_length=40, unique=True, db_index=True)
    device = models.CharField(max_length=100, blank=True, default="",
                              help_text="设备备注，如 xiaomi-14 / windows-pc，便于用户管理")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def mint(cls, user, device=""):
        import secrets
        return cls.objects.create(user=user, key=secrets.token_hex(20), device=device)

    def __str__(self):
        return f"token:{self.user.username}:{self.device or self.key[:6]}"


class Song(models.Model):
    """本地音乐。文件放在 media/music/ 下，用 scan_music 命令自动导入。"""
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=200, blank=True, default="")
    audio = models.FileField(upload_to="music/")
    moods = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def mood_list(self):
        return [m.strip() for m in self.moods.split(",") if m.strip()]

    def __str__(self):
        return f"{self.title} - {self.artist}" if self.artist else self.title


class Activity(models.Model):
    """舒缓行为 / 建议动作。"""
    text = models.CharField(max_length=300)
    moods = models.CharField(max_length=200, blank=True, default="")

    def mood_list(self):
        return [m.strip() for m in self.moods.split(",") if m.strip()]

    def __str__(self):
        return self.text


class PsychologyTip(models.Model):
    """心理学小知识，正面心情时推送。"""
    title = models.CharField(max_length=200)
    content = models.TextField()
    source = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    """AI 树洞的对话记录。登录用户按 user 存，访客按 session 存。"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.CASCADE, related_name="chats")
    session_key = models.CharField(max_length=40, blank=True, default="", db_index=True)
    role = models.CharField(max_length=12)  # user / assistant
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class SiteSettings(models.Model):
    """全站设置的单例：关于我们 + 联系方式 + 危机热线。pk 固定为 1。"""
    about_content = models.TextField(
        blank=True, default="# 关于我们\n\n在这里写点关于你和这个网站的故事吧。支持 **Markdown** 语法。",
        help_text="支持 Markdown",
    )
    contact_email = models.CharField(max_length=200, blank=True, default="")
    contact_phone = models.CharField(max_length=50, blank=True, default="")
    contact_wechat = models.CharField(max_length=100, blank=True, default="")
    contact_bilibili = models.CharField(max_length=300, blank=True, default="",
                                        help_text="B站主页完整链接，如 https://space.bilibili.com/xxxxx")
    crisis_hotline = models.CharField(max_length=100, blank=True, default="12356")
    disclaimer_content = models.TextField(
        blank=True, default="",
        help_text="免责声明正文，支持 Markdown。留空则用内置默认版本。")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "网站设置"

    def __str__(self):
        return "网站设置"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BilibiliVideo(models.Model):
    """记录心情后推荐的 B 站视频。可按心情打标签，留空则对所有心情可推。"""
    title = models.CharField(max_length=200)
    url = models.CharField(max_length=400, help_text="B站视频完整链接")
    moods = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def mood_list(self):
        return [m.strip() for m in self.moods.split(",") if m.strip()]

    @property
    def bvid(self):
        import re
        m = re.search(r"(BV[0-9A-Za-z]+)", self.url or "")
        return m.group(1) if m else ""

    @property
    def embed_url(self):
        bv = self.bvid
        return f"https://player.bilibili.com/player.html?bvid={bv}&autoplay=0&high_quality=1" if bv else ""

    def __str__(self):
        return self.title


class UserProfile(models.Model):
    """用户扩展资料：头像、简介。徽章按连续记录天数实时计算，不入库。"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.CharField(max_length=200, blank=True, default="")
    language = models.CharField(max_length=8, blank=True, default="zh")  # zh / en

    def __str__(self):
        return f"profile:{self.user.username}"


# 连胜徽章阈值（天）
BADGES = [
    (5,    "🌱", "初心"),
    (30,   "🌿", "坚持"),
    (100,  "🌳", "百日"),
    (365,  "🏆", "一年"),
    (1000, "👑", "千日"),
]


class UserContribution(models.Model):
    """用户上传的内容（心理建议/小知识/音乐/视频链接），需 AI + 管理员审核。"""
    KIND_CHOICES = [
        ("tip", "心理学小知识"),
        ("activity", "舒缓建议"),
        ("music", "音乐链接"),
        ("video", "视频链接"),
    ]
    STATUS_CHOICES = [
        ("pending_ai", "待AI审核"),
        ("pending_admin", "待管理员复审"),
        ("approved", "已通过"),
        ("rejected", "已拒绝"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="contributions")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    title = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField(blank=True, default="", help_text="小知识/建议的正文，或视频链接")
    source = models.CharField(max_length=200, blank=True, default="", help_text="小知识的出处/作者")
    audio = models.FileField(upload_to="user_music/", blank=True, null=True, help_text="音乐投稿的音频文件")
    moods = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending_ai")
    ai_reason = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def mood_list(self):
        return [m.strip() for m in self.moods.split(",") if m.strip()]

    def __str__(self):
        return f"{self.get_kind_display()}:{self.title or self.content[:20]}"


def compute_streak_and_badges(user):
    """计算用户的当前连续记录天数 + 已获得的徽章。
    连续 = 从今天(或最近有记录的一天)往前，逐日都有记录的最长连续段。"""
    import datetime as _dt
    dates = set(MoodEntry.objects.filter(user=user).values_list("date", flat=True))
    if not dates:
        return 0, []
    today = _dt.date.today()
    # 若今天没记，从昨天算起（不因为今天还没记就断streak）
    start = today if today in dates else today - _dt.timedelta(days=1)
    streak = 0
    d = start
    while d in dates:
        streak += 1
        d -= _dt.timedelta(days=1)
    earned = [{"emoji": e, "name": n, "days": t} for (t, e, n) in BADGES if streak >= t]
    # 也计算历史最高连续（用于即使当前断了也保留徽章）
    best = 0; cur = 0; prev = None
    for dd in sorted(dates):
        if prev is not None and (dd - prev).days == 1:
            cur += 1
        else:
            cur = 1
        best = max(best, cur); prev = dd
    earned_best = [{"emoji": e, "name": n, "days": t} for (t, e, n) in BADGES if best >= t]
    return streak, earned_best
