@echo off
REM ===== Windows 一键启动（生产用 waitress）=====
REM 第一次运行前请先看 README：建虚拟环境、装依赖、初始化数据库
chcp 65001 >nul
cd /d %~dp0
echo 正在启动心情树洞服务器（端口 8000）...
python -m waitress --listen=0.0.0.0:8000 moodsite.wsgi:application
pause
