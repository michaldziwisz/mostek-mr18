@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist "wyniki" mkdir "wyniki"
echo Symulator nie łączy się ze sprzętem. Dźwięki są tutaj wypisywane jako tekst.
"mostek.exe" --symulator --mowa konsola --dzwieki-konsola --dziennik "wyniki\symulator.log"
set "KOD=%errorlevel%"
echo.
echo Kod zakończenia: %KOD%
:koniec
echo.
pause
popd
endlocal & exit /b %KOD%
