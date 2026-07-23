"""扫描 media/music/ 目录，把音频文件登记进数据库。
用法：python manage.py scan_music
       python manage.py scan_music --moods anxious,sad   # 给新导入的曲子打默认心情标签
"""
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from core.models import Song

AUDIO_EXT = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".aac"}


class Command(BaseCommand):
    help = "扫描 media/music/ 下的音频文件并导入 Song 表"

    def add_arguments(self, parser):
        parser.add_argument("--moods", default="", help="给新曲子设置默认心情标签，逗号分隔")

    def handle(self, *args, **opts):
        music_dir = os.path.join(settings.MEDIA_ROOT, "music")
        os.makedirs(music_dir, exist_ok=True)
        default_moods = opts["moods"].strip()
        added = 0
        for name in sorted(os.listdir(music_dir)):
            ext = os.path.splitext(name)[1].lower()
            if ext not in AUDIO_EXT:
                continue
            rel = f"music/{name}"
            if Song.objects.filter(audio=rel).exists():
                continue
            title = os.path.splitext(name)[0]
            artist = ""
            if " - " in title:  # 文件名形如 "歌手 - 歌名"
                artist, title = (p.strip() for p in title.split(" - ", 1))
            Song.objects.create(title=title, artist=artist, audio=rel, moods=default_moods)
            added += 1
            self.stdout.write(f"  + {name}")
        self.stdout.write(self.style.SUCCESS(f"完成，新增 {added} 首。可在 /admin/ 里调整心情标签。"))
