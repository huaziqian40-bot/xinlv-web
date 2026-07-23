"""上传文件大小/类型校验。"""
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
    return None
