@echo off
chcp 65001 > nul
REM 一键启动：后端 + 前端
cd /d "%~dp0backend"
start "backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
cd /d "%~dp0frontend"
start "frontend" cmd /k "npm run dev"
timeout /t 3 > nul
start http://localhost:5173
