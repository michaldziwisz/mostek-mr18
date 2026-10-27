@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist "wyniki" mkdir "wyniki"
echo Tylko odczyt. Badanie potrwa zwykle kilkadziesiąt sekund.
set "ADRES="
set /p "ADRES=Adres IP MR18: "
if not defined ADRES goto anuluj
"badanie_mr18.exe" --mr18 "%ADRES%" --mierniki --plik "wyniki\badanie_mr18.json"
set "KOD=%errorlevel%"
echo.
echo Kod zakończenia: %KOD%
goto koniec
:anuluj
echo Nie uruchomiono programu.
set "KOD=2"
:koniec
echo.
pause
popd
endlocal & exit /b %KOD%
