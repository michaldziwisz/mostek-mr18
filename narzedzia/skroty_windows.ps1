# Skróty Windows dla mostka MR18: autostart z nadzorcą i awaryjne „mikrofon poza anteną”.
#
# Bez -Zapisz skrypt tylko pokazuje, co by utworzył. Niczego nie zmienia.
#
#   powershell -ExecutionPolicy Bypass -File narzedzia\skroty_windows.ps1 -Mr18 192.168.1.50
#   powershell -ExecutionPolicy Bypass -File narzedzia\skroty_windows.ps1 -Mr18 192.168.1.50 -Zapisz
#   powershell -ExecutionPolicy Bypass -File narzedzia\skroty_windows.ps1 -Usun -Zapisz
#
# Tworzy dwa skróty:
#  1. „Mostek MR18” w folderze Autostart: nadzorca uruchamia mostek po zalogowaniu.
#  2. „Mikrofon poza anteną” w menu Start z klawiszem skrótu (domyślnie Ctrl+Alt+M).
#     Windows obsługuje klawisz skrótu tylko dla skrótów w menu Start i na pulpicie.
#     To osobny proces: działa także wtedy, gdy mostek się zawiesił.
#
# Włączamy dopiero po etapach 1-3 planu (sprawdzony MR18 i X-TOUCH).
# NIE SPRAWDZONO na stanowisku: czy Ctrl+Alt+M nie koliduje z NVDA, Zoomem
# i StationPlaylist oraz po jakim czasie od naciśnięcia mikrofon schodzi z anteny.

param(
    [string]$Mr18 = "",
    [string]$Klawisz = "CTRL+ALT+M",
    [switch]$Usun,
    [switch]$Zapisz
)

$ErrorActionPreference = "Stop"
$katalog = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($python) { $pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe" }
}
$autostart = [Environment]::GetFolderPath("Startup")
$menuStart = Join-Path ([Environment]::GetFolderPath("Programs")) "Mostek MR18"
$skrotMostka = Join-Path $autostart "Mostek MR18.lnk"
$skrotMikrofonu = Join-Path $menuStart "Mikrofon poza anteną.lnk"

if ($Usun) {
    foreach ($s in @($skrotMostka, $skrotMikrofonu)) {
        if (Test-Path $s) {
            if ($Zapisz) { Remove-Item $s; Write-Output "Usunięto: $s" }
            else { Write-Output "Do usunięcia: $s" }
        } else { Write-Output "Nie ma: $s" }
    }
    if (-not $Zapisz) { Write-Output "Podgląd. Nic nie usunięto; dodaj -Zapisz." }
    exit 0
}

if (-not $Mr18) { Write-Output "Podaj adres miksera: -Mr18 ADRES (mostek nie szuka MR18 w sieci)."; exit 2 }
if (-not $pythonw -or -not (Test-Path $pythonw)) { Write-Output "Nie znaleziono pythonw.exe."; exit 2 }

$argMostka = "-m mostek.nadzorca --mowa nvda -- --mr18 $Mr18 --mowa nvda --midi winmm --emisja stationplaylist --bez-konsoli"
$argMikrofonu = "`"$katalog\narzedzia\mikrofon_poza_antena.py`" --mr18 $Mr18 --mowa nvda"

Write-Output "Python: $pythonw"
Write-Output "Katalog mostka: $katalog"
Write-Output "1. $skrotMostka"
Write-Output "   $pythonw $argMostka"
Write-Output "2. $skrotMikrofonu, klawisz $Klawisz"
Write-Output "   $pythonw $argMikrofonu"

if (-not $Zapisz) { Write-Output "Podgląd. Nic nie zapisano; dodaj -Zapisz."; exit 0 }

$powloka = New-Object -ComObject WScript.Shell
New-Item -ItemType Directory -Force -Path $menuStart | Out-Null

$s = $powloka.CreateShortcut($skrotMostka)
$s.TargetPath = $pythonw
$s.Arguments = $argMostka
$s.WorkingDirectory = $katalog
$s.Description = "Mostek MR18 i X-TOUCH pod nadzorcą"
$s.Save()

$s = $powloka.CreateShortcut($skrotMikrofonu)
$s.TargetPath = $pythonw
$s.Arguments = $argMikrofonu
$s.WorkingDirectory = $katalog
$s.Hotkey = $Klawisz
$s.Description = "Awaryjnie zdejmuje mikrofon z anteny i mówi wynik przez NVDA"
$s.Save()

foreach ($p in @($skrotMostka, $skrotMikrofonu)) {
    $o = $powloka.CreateShortcut($p)
    Write-Output "Zapisano: $p -> $($o.TargetPath) $($o.Arguments) [klawisz: $($o.Hotkey)]"
}
