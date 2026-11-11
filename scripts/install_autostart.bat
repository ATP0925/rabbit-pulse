@echo off
echo Installing RabbitPulse Windows startup launcher...
where rabbitpulse >nul 2>nul
if %errorlevel%==0 (
    rabbitpulse autostart install
) else (
    python -m rabbitpulse.cli autostart install
)
if "%~1"=="" pause

