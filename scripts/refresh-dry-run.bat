@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh-dry-run.ps1" %*
exit /b %ERRORLEVEL%
