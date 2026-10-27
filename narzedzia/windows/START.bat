@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 exit /b 1
"program\prosty_start.exe" start
set "KOD=%errorlevel%"
if not "%MOSTEK_TEST_SYMULATOR%"=="1" pause
popd
endlocal & exit /b %KOD%
