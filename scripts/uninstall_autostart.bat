@echo off
echo Removing RabbitPulse Windows startup launcher...
where rabbitpulse >nul 2>nul
if %errorlevel%==0 (
    rabbitpulse autostart remove
) else (
    python -m rabbitpulse.cli autostart remove
)
if "%~1"=="" pause

