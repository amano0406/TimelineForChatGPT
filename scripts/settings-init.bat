@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0settings-init.ps1" %*
exit /b %ERRORLEVEL%
