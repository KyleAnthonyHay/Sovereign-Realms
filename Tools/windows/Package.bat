@echo off
rem Double-click: packages the Shipping build to Builds\Windows\SovereignRealms (see the top of package.ps1).
rem Package.bat Development packages the test build.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0package.ps1" %*
echo.
pause
