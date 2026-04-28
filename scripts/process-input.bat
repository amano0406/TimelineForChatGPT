@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0process-input.ps1" %*
exit /b %ERRORLEVEL%
