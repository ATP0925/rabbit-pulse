@echo off
set VBS_TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RabbitPulse.vbs

if exist "%VBS_TARGET%" (
    del "%VBS_TARGET%"
    echo RabbitPulse startup entry removed.
) else (
    echo No startup entry found.
)
pause
