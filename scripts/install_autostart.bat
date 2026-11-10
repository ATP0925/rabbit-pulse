@echo off
set SCRIPT_DIR=%~dp0
set VBS_TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RabbitPulse.vbs

echo Setting up RabbitPulse auto-start on boot...
(
  echo Set WshShell = CreateObject^("WScript.Shell"^)
  echo WshShell.Run """C:\Program Files\Python314\pythonw.exe"" -m rabbitpulse.cli start", 0, False
) > "%VBS_TARGET%"

echo RabbitPulse auto-start successfully installed at:
echo %VBS_TARGET%
pause
