"""上传文件大小/类型校验 + 用户输入 URL 校验。

安全加固（2026-08-07）：
- check_image 用 Pillow Image.open().verify() 校验文件内容确为图片，防伪装成 .jpg 的任意文件；
- 新增 check_http_url：只允许 http/https 且限长 400，堵住 javascript: 等伪协议注入。"""
from urllib.parse import urlsplit

from django.conf import settings

AUDIO_EXT = {"mp3", "m4a", "flac", "ogg", "wav", "aac"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}


def _ext(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_audio(f):
    """返回错误信息字符串；无错误返回 None。"""
    if _ext(f.name) not in AUDIO_EXT:
        return "音频格式仅支持 mp3 / m4a / flac / ogg / wav / aac。"
    if f.size > settings.MAX_AUDIO_MB * 1024 * 1024:
        return f"音频文件不能超过 {settings.MAX_AUDIO_MB} MB。"
    return None


def check_image(f):
    if _ext(f.name) not in IMAGE_EXT:
        return "图片格式仅支持 jpg / png / webp / gif。"
    if f.size > settings.MAX_IMAGE_MB * 1024 * 1024:
        return f"图片不能超过 {settings.MAX_IMAGE_MB} MB。"
    # 用 Pillow 校验文件内容确为图片，防伪装成合法扩展名的任意文件
    try:
        from PIL import Image
        img = Image.open(f)
        img.verify()
        f.seek(0)  # verify() 会读到文件末尾，须复位供后续保存
    except Exception:
        return "文件内容不是有效的图片。"
    return None


def check_http_url(url):
    """只允许 http/https 且限长 400 的 URL；返回错误信息字符串，合法返回 None。
    用于投稿/后台的站外链接，堵住 javascript: 等伪协议注入。"""
    if not url:
        return "链接不能为空。"
    if len(url) > 400:
        return "链接太长了。"
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "链接格式不正确。"
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "链接必须是有效的 http:// 或 https:// 地址。"
    if parsed.username or parsed.password:
        return "链接不能包含账号或密码。"
    return None