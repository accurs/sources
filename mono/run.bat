@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Create .venv and install requirements first.
    pause
    exit /b 1
)

:run
set "BOT_RUNNER=run.bat"
".venv\Scripts\python.exe" -m src.main
set "bot_exit_code=%errorlevel%"

if "%bot_exit_code%"=="75" goto run
if not "%bot_exit_code%"=="0" pause
