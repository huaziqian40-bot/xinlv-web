"""按预定义歌单，给 media/music/ 里的音乐文件打情绪标签并导入 Song 表。

用法：
    把本文件放到  core/management/commands/import_moodlist.py
    确保音乐文件已放进  media/music/  ，文件名格式：  歌手 - 歌曲名.mp3
    然后运行：
        python manage.py import_moodlist              # 正式导入
        python manage.py import_moodlist --dry-run     # 只预览匹配结果，不写库
        python manage.py import_moodlist --replace     # 覆盖已存在歌曲的情绪标签

匹配以「歌曲名」为准，忽略大小写、书名号《》、空格和标点差异，
所以即使文件里的歌手写法和歌单略有出入也能对上。
"""
import os
import re
from django.conf import settings
from django.core.management.base import BaseCommand
from core.models import Song

AUDIO_EXT = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".aac"}

# 情绪 key 见 models.MOODS：
# happy 开心 / calm 平静 / excited 兴奋 / grateful 感恩 / tired 疲惫
# anxious 焦虑 / sad 难过 / angry 愤怒 / lonely 孤独 / numb 麻木

# 歌单：歌曲名 -> 情绪。一首歌可属多个情绪就写成列表。
MOOD_LIST = {
    # 1. 开心 happy
    "Sunny Day": "happy", "Good Life": "happy", "Walking On Sunshine": "happy",
    "Best Day Of My Life": "happy", "Happy": "happy", "On Top Of The World": "happy",
    # 2. 平静 calm
    "Golden Hour": "calm", "River Flows In You": "calm", "A Little Story": "calm",
    "Fragile": "calm", "Beyond The Memory": "calm",
    # 3. 兴奋 excited
    "Starboy": "excited", "Titanium": "excited", "Can't Hold Us": "excited",
    "Believer": "excited", "Centuries": "excited", "Hall Of Fame": "excited",
    # 4. 感恩 grateful
    "Count On Me": "grateful", "You Raise Me Up": "grateful", "Thank You": "grateful",
    "Hero": "grateful",
    # 5. 疲惫 tired
    "起风了": "tired", "星茶会": "tired", "城南花已开": "tired", "那一天的河川": "tired",
    # 6. 焦虑 anxious
    "Weightless": "anxious", "Electric Indigo": "anxious", "Holocene": "anxious",
    "To Build A Home": "anxious", "Breathe Me": "anxious", "Skinny Love": "anxious",
    # 7. 难过 sad
    "Let Her Go": "sad", "Say Something": "sad", "Someone Like You": "sad",
    "All I Want": "sad", "Fix You": "sad", "The Night We Met": "sad",
    # 8. 愤怒 angry
    "Break My Heart Myself": "angry", "Natural": "angry", "The Phoenix": "angry",
    "Animals": "angry", "In The End": "angry", "Lose Yourself": "angry",
    # 9. 孤独 lonely
    "Flowers": "lonely", "The Sound Of Silence": "lonely", "Mad World": "lonely",
    "Youth": "lonely", "Skin": "lonely", "Empty": "lonely",
    # 10. 麻木 numb
    "Numb": "numb", "Creep": "numb", "Hurt": "numb", "Everybody Hurts": "numb",
    "No Surprises": "numb", "Asleep": "numb", "Numb Little Bug": "numb",
}


def _norm(s):
    """归一化：小写、去书名号/括号内容/标点/空格，便于宽松匹配。"""
    s = s.lower()
    s = re.sub(r"[《》()（）\[\]]", "", s)
    s = re.sub(r"[\s\-–—_·.,'’\"]+", "", s)
    return s


# 预先把歌单键归一化，方便查找
NORM_LIST = {_norm(name): (name, mood) for name, mood in MOOD_LIST.items()}


def _split_filename(stem):
    """从 '歌手 - 歌曲名' 拆出 (歌手, 歌曲名)。没有分隔符则整体当歌曲名。"""
    for sep in [" - ", " – ", " — ", "-", "–", "—"]:
        if sep in stem:
            artist, title = stem.split(sep, 1)
            return artist.strip(), title.strip()
    return "", stem.strip()


def _match_mood(title):
    """用歌曲名匹配情绪。先精确归一化匹配，再尝试包含匹配。"""
    nt = _norm(title)
    if nt in NORM_LIST:
        return NORM_LIST[nt]
    # 包含匹配（处理 “Let Her Go（不插电版）” 这类带后缀的文件名）
    for norm_key, (orig, mood) in NORM_LIST.items():
        if norm_key and (norm_key in nt or nt in norm_key):
            return orig, mood
    return None, None


class Command(BaseCommand):
    help = "按内置歌单给 media/music/ 里的音乐打情绪标签并导入"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只预览，不写数据库")
        parser.add_argument("--replace", action="store_true", help="覆盖已存在歌曲的情绪标签")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        replace = opts["replace"]
        music_dir = os.path.join(settings.MEDIA_ROOT, "music")
        if not os.path.isdir(music_dir):
            self.stderr.write(self.style.ERROR(f"找不到目录：{music_dir}"))
            return

        added = updated = skipped = unmatched = 0
        unmatched_files = []

        for name in sorted(os.listdir(music_dir)):
            ext = os.path.splitext(name)[1].lower()
            if ext not in AUDIO_EXT:
                continue
            stem = os.path.splitext(name)[0]
            artist, title = _split_filename(stem)
            matched_name, mood = _match_mood(title)

            if not mood:
                unmatched += 1
                unmatched_files.append(name)
                continue

            rel = f"music/{name}"
            existing = Song.objects.filter(audio=rel).first()

            if existing:
                if replace and existing.moods != mood:
                    if not dry:
                        existing.moods = mood
                        existing.save()
                    updated += 1
                    self.stdout.write(f"  ~ 更新标签 [{mood}] {name}")
                else:
                    skipped += 1
                continue

            if not dry:
                Song.objects.create(
                    title=title, artist=artist, audio=rel, moods=mood)
            added += 1
            self.stdout.write(f"  + [{mood}] {artist} - {title}")

        self.stdout.write("")
        tag = "（预览，未写库）" if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"完成{tag}：新增 {added}，更新 {updated}，跳过 {skipped}，未匹配 {unmatched}"))
        if unmatched_files:
            self.stdout.write(self.style.WARNING("以下文件没匹配到歌单（检查文件名/歌曲名是否一致）："))
            for f in unmatched_files:
                self.stdout.write(f"    ? {f}")
