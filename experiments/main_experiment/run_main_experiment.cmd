@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_main_experiment.ps1" %*
exit /b %errorlevel%
