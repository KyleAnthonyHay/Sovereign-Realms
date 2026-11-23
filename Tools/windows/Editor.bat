@echo off
rem Double-click: builds the editor target if needed and opens the project (see the top of editor.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0editor.ps1" %*
if errorlevel 1 (
    echo.
    pause
)
