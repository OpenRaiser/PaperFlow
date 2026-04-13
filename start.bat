@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" services\webhook-server\start-with-ngrok.py
) else (
    python services\webhook-server\start-with-ngrok.py
)
