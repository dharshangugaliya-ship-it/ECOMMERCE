@echo off
REM %~dp0 = folder this script lives in, so it works regardless of where the project is checked out
set "ROOT=%~dp0"

REM Start backend in a new window
start "ecommerce-backend" cmd /k "cd /d "%ROOT%backend" && call .venv\Scripts\activate.bat && python app.py"

REM Start frontend in a new window
start "ecommerce-frontend" cmd /k "cd /d "%ROOT%frontend" && python -m http.server 8080"

echo.
echo Both servers are starting in separate windows.
echo Backend:  http://localhost:5000
echo Frontend: http://localhost:8080
echo Close each window (or press Ctrl+C) to stop the servers.
