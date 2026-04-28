@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh-force.ps1" %*
exit /b %ERRORLEVEL%
