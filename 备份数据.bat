@echo off
cd /d %~dp0
call venv\Scripts\activate 2>nul
python backup_db.py
pause
