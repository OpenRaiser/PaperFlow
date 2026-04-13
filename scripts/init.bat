@echo off
setlocal

cd /d "%~dp0.."

echo =========================================
echo   SciTaste Initialization
echo =========================================
echo.

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [1/5] Created .env from .env.example
) else (
    echo [1/5] .env already exists
)

if not exist "data\\roles.json" (
    if exist "config\\roles.example.json" (
        copy "config\\roles.example.json" "data\\roles.json" >nul
        echo [2/5] Created data\\roles.json from config\\roles.example.json
    )
 ) else (
    echo [2/5] data\\roles.json already exists
)

echo [3/5] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [4/5] Initializing runtime folders and database...
python scripts\init_db.py

echo [5/5] Verifying required Feishu environment variables...
python services\webhook-server\start.py --verify

echo.
echo =========================================
echo   Initialization Complete
echo =========================================
echo.
echo Next steps:
echo 1. Edit .env and fill in your Feishu / ngrok / model config
echo 2. Start the webhook locally: start.bat
echo 3. Copy data\feishu_request_url.txt into Feishu Event Subscription
echo.
pause
