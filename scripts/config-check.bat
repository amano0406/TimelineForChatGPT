@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0config-check.ps1" %*
exit /b %ERRORLEVEL%
