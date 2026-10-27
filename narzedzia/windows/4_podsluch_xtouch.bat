@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist "wyniki" mkdir "wyniki"
echo Zamknij mostek i inne programy korzystające z MIDI.
echo Przed każdym elementem wpisz opis, na przykład: opis F1
set "URZADZENIE=X-TOUCH"
set /p "URZADZENIE=Nazwa wejścia z listy MIDI, Enter zostawia X-TOUCH: "
"podsluch_midi.exe" --urzadzenie "%URZADZENIE%" --plik "wyniki\podsluch_xtouch.jsonl"
set "KOD=%errorlevel%"
echo.
echo Kod zakończenia: %KOD%
:koniec
echo.
pause
popd
endlocal & exit /b %KOD%
