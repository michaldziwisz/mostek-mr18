@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist "wyniki" mkdir "wyniki"
echo UWAGA: to nie jest narzędzie tylko do odczytu.
echo Badanie MR18 i podsłuch MIDI nie zmieniają ustawień miksera.
echo Mostek ZAPISUJE wysyłki, Main LR, mute, Bus 5 i 6 oraz solo.
echo Może wykonać ochronne zamknięcia już podczas odczytu niezgodnego profilu.
echo Używa układu Michała: muzyka 1 do 6, Zoom 7 i 8, mikrofon 9, telefon 10.
echo Najpierw zapisz własną scenę w M-AIR Edit.
echo Nie testuj na żywo ani z głośnikami ustawionymi głośno.
echo Po zakończeniu zamknij mostek i wczytaj swoją scenę.
echo Inny profil oznacza blokadę otwarć. To oczekiwany wynik.
set "ZGODA="
set /p "ZGODA=Po zabezpieczeniu stanowiska wpisz TAK, aby kontynuować: "
if not "%ZGODA%"=="TAK" goto anuluj
set "ADRES="
set /p "ADRES=Adres IP MR18: "
if not defined ADRES goto anuluj
"mostek.exe" --mr18 "%ADRES%" --midi winmm --mowa konsola --dziennik "wyniki\mostek.log"
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
