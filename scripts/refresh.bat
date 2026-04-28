@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh.ps1" %*
exit /b %ERRORLEVEL%
