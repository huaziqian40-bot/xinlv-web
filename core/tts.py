"""语音合成：用 edge-tts（白嫖微软在线语音，免费、无需 API Key、无需实名/付费）。
把文字转成自然人声 MP3，base64 返回前端播放。长文本自动按标点分句合成再拼接。
音色/语速从 .env 配置。"""
import asyncio
import base64
import re

from django.conf import settings

try:
    import edge_tts
    _HAS_EDGE = True
except Exception:
    _HAS_EDGE = False


def _split(text, limit=200):
    """按中文标点分句，避免单段过长。"""
    parts = re.split(r"(?<=[。！？!?；;\n])", text)
    chunks, buf = [], ""
    for p in parts:
        if len(buf) + len(p) > limit and buf:
            chunks.append(buf); buf = p
        else:
            buf += p
    if buf.strip():
        chunks.append(buf)
    return chunks or [text]


async def _synth(text, voice, rate):
    audio = bytearray()
    for chunk in _split(text):
        if not chunk.strip():
            continue
        comm = edge_tts.Communicate(chunk, voice, rate=rate)
        async for msg in comm.stream():
            if msg["type"] == "audio":
                audio.extend(msg["data"])
    return bytes(audio)


def synthesize(text):
    """返回 (base64_mp3, None) 或 (None, 错误信息)。"""
    if not _HAS_EDGE:
        return None, "服务器未安装 edge-tts（pip install edge-tts）"
    text = (text or "").strip()
    if not text:
        return None, "空文本"
    if len(text) > 600:
        text = text[:600]

    voice = settings.TTS_VOICE
    rate = settings.TTS_RATE
    try:
        data = asyncio.run(_synth(text, voice, rate))
        if not data:
            return None, "合成结果为空"
        return base64.b64encode(data).decode(), None
    except Exception as e:
        # 服务器联网受限 / 微软接口异常时，前端会自动退回浏览器自带声音
        return None, f"语音合成失败：{e}"
