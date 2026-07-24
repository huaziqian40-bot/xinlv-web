"""
心情日历 + AI 电子树洞 —— Django 配置
所有可变项都从 .env 读取，方便在 Windows 服务器 / 内网穿透环境下部署。
"""
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(key, default="False"):
    return os.environ.get(key, default).strip().lower() in ("1", "true", "yes", "on")


def env_list(key, default=""):
    raw = os.environ.get(key, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


# ---- 安全相关 ----
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-key-please-change-me-in-production",
)
DEBUG = env_bool("DJANGO_DEBUG", "True")

# 内网穿透时必须把你的公网域名/IP 加进来。默认放开方便本地调试。
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "*") or ["*"]

# Django 4+ 通过公网域名提交 POST(树洞聊天、记录心情)需要这一项，
# 否则会报 CSRF 403。把你的穿透域名写进 .env 的 CSRF_TRUSTED_ORIGINS。
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# ---- 应用 ----
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # whitenoise：让服务器自己托管 CSS 等静态文件，DEBUG=False 时也不用额外配置
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "moodsite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_globals",
                "core.i18n.i18n_context",
            ],
        },
    },
]

WSGI_APPLICATION = "moodsite.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- 区域 ----
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ---- 静态 / 媒体 ----
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"   # 本地音乐文件放在 media/music/

# whitenoise：压缩并加缓存指纹托管静态文件
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# 简易管理后台的登录跳转
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 允许被同源 iframe 嵌入（桌面/安卓客户端的壳用 iframe 加载本站；
# 默认 DENY 会导致客户端白屏）。仍禁止被外部站点嵌入，保留防点击劫持保护。
X_FRAME_OPTIONS = "SAMEORIGIN"

# ---- DeepSeek（AI 树洞）----
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# ---- 语音合成 TTS（edge-tts，免费、无需 key/实名/付费）----
# 音色列表可运行：edge-tts --list-voices | findstr zh-CN
# 常用中文音色：
#   zh-CN-XiaoxiaoNeural  晓晓 温柔女声（默认）
#   zh-CN-XiaoyiNeural    晓伊 活泼女声
#   zh-CN-YunxiNeural     云希 年轻男声
#   zh-CN-YunyangNeural   云扬 沉稳男声
#   zh-CN-liaoning-XiaobeiNeural 辽宁口音女声
TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
TTS_RATE = os.environ.get("TTS_RATE", "+0%")   # 语速，如 "-10%" 慢一点、"+10%" 快一点


# ==================== 安全加固 & 稳定性（默认对本地开发无影响） ====================
# 生产环境请在 .env 设 DJANGO_DEBUG=False，以下开关随之启用。
_PROD = not DEBUG

# --- 安全响应头 ---
SECURE_CONTENT_TYPE_NOSNIFF = True          # 禁止浏览器 MIME 嗅探
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"              # 允许自家客户端 iframe，禁止外站嵌入

# --- Cookie 安全 ---
SESSION_COOKIE_HTTPONLY = True             # JS 读不到会话 cookie，防 XSS 窃取
CSRF_COOKIE_HTTPONLY = False               # 前端需读取 csrftoken，保持 False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# 仅当你启用了 HTTPS 时，把下面两项在 .env 设为 True，cookie 只走加密连接
SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", "False")
CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", "False")

# --- HTTPS 相关（有 HTTPS 时在 .env 打开；没有则保持关闭，避免把自己锁在门外） ---
if env_bool("ENABLE_HTTPS", "False"):
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- 上传大小限制（防止有人塞爆硬盘 / 内存） ---
# 请求体（非文件字段）上限 5MB；单个上传文件默认走 FileField，本项限制表单整体
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
# 业务级：音频/头像大小上限（在视图里校验，见 core/limits.py）
MAX_AUDIO_MB = int(os.environ.get("MAX_AUDIO_MB", "20"))
MAX_IMAGE_MB = int(os.environ.get("MAX_IMAGE_MB", "5"))

# --- 简易限流阈值（见 core/ratelimit.py，基于内存计数，无需额外依赖） ---
RATE_LIMITS = {
    "confidant": (int(os.environ.get("RL_CHAT_N", "20")), 60),    # 树洞：60秒内最多20条
    "contribute": (int(os.environ.get("RL_UPLOAD_N", "10")), 300), # 投稿：5分钟内最多10次
    "login": (int(os.environ.get("RL_LOGIN_N", "8")), 300),       # 登录：5分钟内最多8次失败
    "tts": (int(os.environ.get("RL_TTS_N", "30")), 60),           # 语音合成：60秒最多30次
}

# --- 日志：错误写到文件，方便排查崩溃 ---
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "site.log"),
            "maxBytes": 5 * 1024 * 1024,   # 单文件5MB
            "backupCount": 5,               # 保留5个历史
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "console": {"level": "INFO", "class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["file", "console"], "level": "WARNING"},
    "loggers": {
        "django.request": {"handlers": ["file"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["file"], "level": "WARNING", "propagate": False},
    },
}
