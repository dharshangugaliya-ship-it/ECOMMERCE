@echo off
set "ROOT=%~dp0"
cd /d "%ROOT%backend"
call .venv\Scripts\activate.bat
python app.py > "%ROOT%api.log" 2>&1
