"""根据心情生成推荐：负面情绪 -> 舒缓歌曲 + 行为；正面情绪 -> 心理学小知识。"""
import random
from .models import Song, Activity, PsychologyTip, BilibiliVideo, MOOD_MAP

# 不同心情对应的呼吸 / 即时小练习（兜底，数据库为空也有内容）
QUICK_PRACTICE = {
    "anxious": "试试 4-7-8 呼吸：吸气 4 秒，屏息 7 秒，缓缓呼气 8 秒，重复 4 轮。",
    "angry":  "找个没人的地方，把想说的话写下来或大声说出来，先让情绪流动，再决定怎么做。",
    "sad":    "允许自己难过一会儿，给信任的人发条消息，哪怕只是说一句「我今天不太好」。",
    "tired":  "放下手机，闭眼休息 10 分钟，或者去窗边看看远处，让眼睛和大脑都松一下。",
    "lonely": "给一个久未联系的人发条消息，或出门走到有人的地方，孤独常常因连接而缓解。",
    "numb":   "做一件具体的小事：喝口水、洗把脸、整理桌面，用身体的动作把自己拉回当下。",
}


def _pick_for_mood(queryset, mood, limit):
    """优先选标了该心情的，再用未标心情（通用）的补齐。"""
    tagged = [o for o in queryset if mood in o.mood_list()]
    generic = [o for o in queryset if not o.mood_list()]
    random.shuffle(tagged)
    random.shuffle(generic)
    return (tagged + generic)[:limit]


def build(mood):
    info = MOOD_MAP.get(mood, {})
    valence = info.get("valence", 0)
    rec = {"mood": mood, "info": info, "valence": valence,
           "songs": [], "activities": [], "tips": [], "practice": "", "video": None}

    # 歌曲对所有心情都给
    rec["songs"] = _pick_for_mood(list(Song.objects.all()), mood, 3)

    # 推荐一个 B 站视频（优先匹配心情）
    videos = _pick_for_mood(list(BilibiliVideo.objects.all()), mood, 1)
    rec["video"] = videos[0] if videos else None

    if valence <= 0:
        # 负面 / 中性：舒缓行为 + 即时练习
        rec["activities"] = _pick_for_mood(list(Activity.objects.all()), mood, 3)
        rec["practice"] = QUICK_PRACTICE.get(mood, "")
    else:
        # 正面：心理学小知识
        tips = list(PsychologyTip.objects.all())
        random.shuffle(tips)
        rec["tips"] = tips[:2]
        rec["activities"] = _pick_for_mood(list(Activity.objects.all()), mood, 2)

    return rec
