@echo off
REM ===== Windows 一键启动（生产用 waitress）=====
REM 第一次运行前请先看 README：建虚拟环境、装依赖、初始化数据库
chcp 65001 >nul
cd /d %~dp0

echo 正在检查数据库迁移和静态文件（每次启动自动补跑，忘了手动跑也不怕）...
python manage.py migrate --noinput
python manage.py collectstatic --noinput
if errorlevel 1 (
  echo.
  echo [!] 上面如果有报错，请先解决报错再继续，否则网站可能打不开或样式丢失。
  pause
)

echo.
echo 正在启动心情树洞服务器（端口 8000）...
REM 线程数从 waitress 默认的 4 提到 32，给长轮询（/api/v1/sync/watch/）留出余量：
REM 该接口会占住线程最多 25 秒，线程太少会被饿死（8 条挂起 vs 4 个线程 = 整站卡死）。
REM **线程数和 MOODTREE_WATCH_SLOTS 必须成对改**：这里给 32，才好在生产环境里
REM 把它设成 8。代码里的默认值是 2（按 waitress 默认的 4 线程算的），
REM 不改这里就直接把 MOODTREE_WATCH_SLOTS 提到 8 会把线程池占满。
python -m waitress --listen=0.0.0.0:8000 --threads=32 moodsite.wsgi:application
pause
