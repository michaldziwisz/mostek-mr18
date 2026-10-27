@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist "wyniki" mkdir "wyniki"
"podsluch_midi.exe" --lista > "wyniki\lista_midi.txt" 2>&1
set "KOD=%errorlevel%"
type "wyniki\lista_midi.txt"
goto koniec
set "KOD=%errorlevel%"
echo.
echo Kod zakończenia: %KOD%
:koniec
echo.
pause
popd
endlocal & exit /b %KOD%
