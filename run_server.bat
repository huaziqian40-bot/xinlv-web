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
python -m waitress --listen=0.0.0.0:8000 moodsite.wsgi:application
pause
