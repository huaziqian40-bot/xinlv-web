"""数据库 + 用户上传文件 自动备份脚本。
SQLite 最怕文件损坏，定期备份能救命。
用法：
    python backup_db.py                 # 立即备份一次
    可用 Windows 任务计划程序每天定时运行（见 运维手册.md）。
备份放在 backups/ 下，带时间戳；自动保留最近 KEEP 份，清理更早的。
"""
import os
import shutil
import sqlite3
import datetime
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "db.sqlite3")
MEDIA = os.path.join(BASE, "media")
BACKUP_DIR = os.path.join(BASE, "backups")
KEEP = 30  # 保留最近 30 份

os.makedirs(BACKUP_DIR, exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# 1) 用 SQLite 官方 backup API 做一致性备份（比直接复制文件安全，能避开写入中途）
if os.path.exists(DB):
    dst = os.path.join(BACKUP_DIR, f"db_{stamp}.sqlite3")
    src_conn = sqlite3.connect(DB)
    dst_conn = sqlite3.connect(dst)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close(); dst_conn.close()
    print(f"[OK] 数据库已备份：{dst}")
else:
    print("[跳过] 未找到 db.sqlite3")

# 2) 打包 media（用户上传的音乐/头像）
if os.path.isdir(MEDIA):
    media_zip = os.path.join(BACKUP_DIR, f"media_{stamp}")
    shutil.make_archive(media_zip, "zip", MEDIA)
    print(f"[OK] 媒体文件已备份：{media_zip}.zip")

# 3) 清理旧备份，各类型只保留最近 KEEP 份
for pattern in ["db_*.sqlite3", "media_*.zip"]:
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, pattern)))
    for old in files[:-KEEP]:
        os.remove(old)
        print(f"[清理] 删除旧备份：{os.path.basename(old)}")

print("备份完成。")
