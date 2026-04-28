@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0daemon.ps1" %*
exit /b %ERRORLEVEL%
