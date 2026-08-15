@echo off
cd /d D:\ecommerce\backend
call .venv\Scripts\activate.bat
python app.py > D:\ecommerce\api.log 2>&1
