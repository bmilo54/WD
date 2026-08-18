@echo off
REM Weekly SMS-provider country sync. Point Windows Task Scheduler at this
REM file and run it every Monday.
REM
REM Replace YOUR_CLAUDEOTP_API_KEY below with your real ClaudeOTP key.
REM Do not commit a real key to git.

cd /d "%~dp0pull_data"

set "PYTHON=%USERPROFILE%\Envs\pull_data\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Could not find virtualenv python at %PYTHON%
    echo Create it first with: mkvirtualenv pull_data
    exit /b 1
)

echo [%DATE% %TIME%] Syncing Hero SMS countries...
"%PYTHON%" manage.py sync_countries --provider hero-sms
if errorlevel 1 (
    echo Hero SMS sync failed.
    exit /b 1
)

echo [%DATE% %TIME%] Syncing ClaudeOTP countries...
"%PYTHON%" manage.py sync_countries --provider claude-otp --api-key YOUR_CLAUDEOTP_API_KEY
if errorlevel 1 (
    echo ClaudeOTP sync failed.
    exit /b 1
)

echo [%DATE% %TIME%] Country sync finished.
