"""Samowystarczalna paczka konsolowa Windows. Bez --zapisz wyłącznie plan.

Uruchamiać Pythonem Windows 64 bit z zainstalowanym PyInstallerem.
Nie instaluje zależności, nie uruchamia sprzętu ani NVDA. Buduje na dysku
Windows, nie na UNC. Katalogi pracy i wyjścia muszą być nowe.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parent.parent
NAZWA_ZIP = "mostek-mr18-test-eaaacc4.zip"
PROGRAMY = {
    "mostek": "from mostek.glowny import main\nraise SystemExit(main())\n",
    "badanie_mr18": "from narzedzia.badanie_mr18 import main\nraise SystemExit(main())\n",
    "podsluch_midi": "from narzedzia.podsluch_midi import main\nraise SystemExit(main())\n",
    "scena_mr18": "from narzedzia.scena_mr18 import main\nraise SystemExit(main())\n",
    "prosty_start": "from narzedzia.prosty_start import main\nraise SystemExit(main())\n",
}


def md5(plik):
    return hashlib.md5(Path(plik).read_bytes()).hexdigest()


def instrukcja(zrodlo: Path) -> tuple[str, str]:
    """Jeden materiał źródłowy, identyczna treść TXT i semantycznego HTML."""
    bloki = json.loads(zrodlo.read_text(encoding="utf-8"))
    tekst, kod = [], []
    for tag, tresc in bloki:
        if tag in ("h1", "h2", "p"):
            tekst.append(tresc)
            kod.append(f"<{tag}>{html.escape(tresc)}</{tag}>")
        elif tag in ("ol", "ul"):
            tekst.append("\n".join(f"{i}. {s}" for i, s in enumerate(tresc, 1)))
            kod.append(f"<{tag}>" + "".join(f"<li>{html.escape(s)}</li>" for s in tresc) + f"</{tag}>")
        else:
            raise ValueError(f"Nieznany blok instrukcji: {tag}")
    dokument = ('<!doctype html>\n<html lang="pl"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Mostek MR18 i X-TOUCH. Instrukcja testów</title>'
                '<style>body{font:1.125rem/1.6 system-ui,sans-serif;max-width:75ch;margin:2rem auto;'
                'padding:0 1rem;color:#171717;background:#fff}li{margin:.6em 0}p,li{overflow-wrap:anywhere}'
                'h1,h2{line-height:1.25}</style></head><body><main>\n'
                + "\n".join(kod) + "\n</main></body></html>\n")
    return "\n\n".join(tekst) + "\n", dokument


def polacz(katalog: Path, cel: Path) -> None:
    """Scal runtime trzech onedir, odrzucając kolizję zamiast ją nadpisać."""
    for plik in sorted(katalog.rglob("*")):
        if not plik.is_file():
            continue
        docelowy = cel / plik.relative_to(katalog)
        if docelowy.exists():
            if plik.read_bytes() != docelowy.read_bytes():
                raise ValueError(f"Kolizja plików runtime: {docelowy}")
        else:
            docelowy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(plik, docelowy)


def przygotuj_dane(repo: Path, paczka: Path, scena: Path | None = None) -> None:
    (paczka / "ustawienia").mkdir(parents=True)
    for nazwa in ("stanowisko.json", "poziomy_bazowe.json"):
        shutil.copy2(repo / "ustawienia" / nazwa, paczka / "ustawienia" / nazwa)
    for nazwa in ("dzwieki", "biblioteki"):
        shutil.copytree(repo / nazwa, paczka / nazwa,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (paczka / "scena").mkdir()
    pliki_sceny = ("BAZA.scn", "WCZYTANIE-BAZY.txt", "WCZYTANIE-BAZY.html")
    if scena is not None:
        if not all((scena / n).is_file() for n in pliki_sceny):
            raise FileNotFoundError("Scena musi zawierać BAZA.scn i obie instrukcje WCZYTANIE-BAZY")
        for nazwa in pliki_sceny:
            shutil.copy2(scena / nazwa, paczka / "scena" / nazwa)
    else:
        info = ("Scena BAZA nie została jeszcze dołączona. Wykonaj tylko kroki 1 do 4.\n"
                "Przed krokami 5 i 6 potrzebne są BAZA.scn i WCZYTANIE-BAZY.txt oraz HTML od Michała.\n")
        (paczka / "scena/CZYTAJ.txt").write_text(info, encoding="utf-8-sig")
    (paczka / "wyniki").mkdir()
    (paczka / "wyniki" / "O_WYNIKACH.txt").write_text(
        "Tu powstaną wyniki badań i dzienniki z plików BAT. Odesłać cały katalog Michałowi.\n",
        encoding="utf-8-sig")
    for plik in sorted((repo / "narzedzia/windows").glob("[1-6]_*.bat")):
        # BAT: UTF-8 bez BOM i CRLF. chcp 65001 występuje przed polskim tekstem.
        tresc = plik.read_text(encoding="utf-8")
        (paczka / plik.name).write_bytes(tresc.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    txt, kod = instrukcja(repo / "narzedzia/windows/instrukcja.json")
    (paczka / "INSTRUKCJA.txt").write_text(txt, encoding="utf-8-sig")
    (paczka / "INSTRUKCJA.html").write_text(kod, encoding="utf-8")


def przygotuj_prosty_start(repo: Path, paczka: Path, scena: Path) -> None:
    program = paczka / 'program'
    przygotuj_dane(repo, program, scena)
    for n in ('schemat-mr18.json',):
        shutil.copy2(repo / 'dane_sceny' / n, program / 'scena' / n)
    if md5(program / 'scena/BAZA.scn') != md5(repo / 'dane_sceny/BAZA.scn'):
        raise ValueError('Scena dołączana do paczki jest inna niż testowana BAZA')
    dodatki = program / 'dodatki'
    dodatki.mkdir()
    for plik in list(program.glob('*.bat')) + list(program.glob('INSTRUKCJA.*')):
        if plik.suffix == '.bat':
            tekst = plik.read_text(encoding='utf-8').replace('pushd "%~dp0"', 'pushd "%~dp0.."')
            (dodatki / plik.name).write_bytes(tekst.replace('\n', '\r\n').encode('utf-8'))
            plik.unlink()
        else:
            plik.rename(dodatki / plik.name)
    for n in ('START.bat', 'RESTART.bat', 'PRZYWROC.bat'):
        tekst = (repo / 'narzedzia/windows' / n).read_text(encoding='utf-8')
        (paczka / n).write_bytes(tekst.replace('\n', '\r\n').encode('utf-8'))
    txt, kod = instrukcja(repo / 'narzedzia/windows/prosty_start.json')
    kod = kod.replace('</style>', '@media print{@page{size:A4;margin:12mm}body{font:10pt/1.15 sans-serif;max-width:none;margin:0;padding:0}h1{font-size:16pt}h2{font-size:12pt;margin:.6em 0 .2em}p,li{margin:.35em 0}ol{padding-left:1.5em}}</style>')
    (paczka / 'CZYTAJ-NAJPIERW.txt').write_text(txt, encoding='utf-8-sig')
    (paczka / 'CZYTAJ-NAJPIERW.html').write_text(kod, encoding='utf-8-sig')


def zbuduj(repo: Path, praca: Path, wyjscie: Path, commit: str, scena: Path | None = None,
           prosty_start: bool = False) -> dict:
    if prosty_start and scena is None:
        raise ValueError("Prosty start wymaga kompletnej sceny BAZA")
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("Budowę wykonuje wyłącznie Python Windows 64 bit")
    if not praca.drive or str(praca).startswith("\\\\"):
        raise ValueError("Katalog pracy musi leżeć na natywnym dysku Windows, nie na UNC")
    if praca.exists() or wyjscie.exists():
        raise FileExistsError("Katalog pracy i wyjścia muszą być nowe; nie nadpisuję istniejących plików")
    if praca == wyjscie or praca in wyjscie.parents or wyjscie in praca.parents:
        raise ValueError("Katalog pracy i wyjścia muszą być rozłączne")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Podaj pełny hash commitu źródeł przez --commit")
    import PyInstaller  # import dopiero po --zapisz, bez instalowania pakietów
    if shutil.disk_usage(praca.parent).free < 700 * 1024 * 1024:
        raise RuntimeError("Potrzeba przynajmniej 700 MiB wolnego na dysku budowy")
    praca.mkdir(parents=True)
    wyjscie.mkdir(parents=True)
    dowody = wyjscie / "odbior"
    dowody.mkdir()
    paczka = wyjscie / "paczka"
    paczka.mkdir()
    katalog_programu = paczka / "program" if prosty_start else paczka
    katalog_programu.mkdir(exist_ok=True)
    raport = {"commit": commit, "prosty_start": prosty_start, "baza": "eaaacc4", "python": sys.version,
              "pyinstaller": PyInstaller.__version__, "platforma": sys.platform,
              "bity": struct.calcsize("P") * 8, "procesy": []}
    try:
        zrodla = praca / "zrodla"
        for nazwa in ("mostek", "narzedzia"):
            katalog = zrodla / nazwa
            katalog.mkdir(parents=True)
            for plik in (repo / nazwa).glob("*.py"):
                shutil.copy2(plik, katalog / plik.name)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
                   PYTHONDONTWRITEBYTECODE="1", PYINSTALLER_CONFIG_DIR=str(praca / "cache"))
        # Jeden graf importów i jeden runtime. Osobne analizy PyInstallera
        # tworzą różne base_library.zip, których nie wolno nadpisywać przy scalaniu.
        kod = ('from pathlib import Path\n'
               'from mostek.glowny import main as mostek\n'
               'from narzedzia.badanie_mr18 import main as badanie_mr18\n'
               'from narzedzia.podsluch_midi import main as podsluch_midi\n'
               'from narzedzia.scena_mr18 import main as scena_mr18\n'
               'from narzedzia.prosty_start import main as prosty_start\n'
               'programy = {"mostek": mostek, "badanie_mr18": badanie_mr18, "podsluch_midi": podsluch_midi, "scena_mr18": scena_mr18, "prosty_start": prosty_start}\n'
               'raise SystemExit(programy[Path(sys.executable).stem.lower()]())\n')
        for nazwa in ("mostek",):
            start = praca / ("start_" + nazwa + ".py")
            # Wymuszenie UTF-8 również dla przekierowanego stdout/stderr EXE.
            start.write_text('import sys\nfor s in (sys.stdin, sys.stdout, sys.stderr):\n'
                             '    if s is not None and hasattr(s, "reconfigure"):\n'
                             '        s.reconfigure(encoding="utf-8")\n' + kod, encoding="utf-8")
            polecenie = [sys.executable, "-B", "-m", "PyInstaller", "--noconfirm", "--clean",
                         "--onedir", "--console", "--contents-directory", "_internal", "--name", nazwa,
                         "--paths", str(zrodla), "--distpath", str(praca / "dist"),
                         "--workpath", str(praca / "build"), "--specpath", str(praca), str(start)]
            wynik = subprocess.run(polecenie, cwd=praca, env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=900)
            dane = dict(polecenie=polecenie, rc=wynik.returncode, stdout=wynik.stdout, stderr=wynik.stderr)
            (dowody / f"budowa_{nazwa}.json").write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")
            raport["procesy"].append({"program": nazwa, "rc": wynik.returncode})
            if wynik.returncode:
                raise RuntimeError(f"Budowa {nazwa} nie powiodła się, kod {wynik.returncode}")
            polacz(praca / "dist" / nazwa, katalog_programu)
        for nazwa in PROGRAMY:
            if nazwa != "mostek":
                shutil.copy2(katalog_programu / "mostek.exe", katalog_programu / (nazwa + ".exe"))
        raport["programy"] = list(PROGRAMY)
        if prosty_start:
            przygotuj_prosty_start(repo, paczka, scena)
        else:
            przygotuj_dane(repo, paczka, scena)
        wiersze = ["Mostek MR18, wydanie testowe Windows x64", f"Commit źródeł: {commit}",
                   f"Wydanie: {'prosty-start-' + commit[:7] if prosty_start else 'test-eaaacc4'}",
                   f"Python: {sys.version}", f"PyInstaller: {PyInstaller.__version__}",
                   "Lista plików paczki przed odbiorem. MD5, rozmiar w bajtach, ścieżka.",
                   "MANIFEST.txt wyłączony z własnej listy, aby uniknąć samoodniesienia.", ""]
        for plik in sorted(paczka.rglob("*")):
            if plik.is_file():
                wiersze.append(f"{md5(plik)}  {plik.stat().st_size}  {plik.relative_to(paczka).as_posix()}")
        manifest = "\n".join(wiersze) + "\n"
        (katalog_programu / "MANIFEST.txt").write_text(manifest, encoding="utf-8-sig")
        zip_path = wyjscie / (f"mostek-mr18-prosty-start-{commit[:7]}.zip" if prosty_start else NAZWA_ZIP)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for plik in sorted(paczka.rglob("*")):
                if plik.is_file():
                    z.write(plik, plik.relative_to(paczka).as_posix())
        raport.update(zip=zip_path.name, md5=md5(zip_path), bajty=zip_path.stat().st_size)
        (wyjscie / "MANIFEST.txt").write_text(
            manifest + f"\nArchiwum: {raport['md5']}  {raport['bajty']}  {zip_path.name}\n", encoding="utf-8-sig")
        instrukcje = ("CZYTAJ-NAJPIERW.txt", "CZYTAJ-NAJPIERW.html") if prosty_start else ("INSTRUKCJA.txt", "INSTRUKCJA.html")
        for nazwa in instrukcje:
            shutil.copy2(paczka / nazwa, wyjscie / nazwa)
        return raport
    finally:
        # Usuwamy tylko własny, wcześniej nieistniejący katalog, także po błędzie.
        shutil.rmtree(praca)
        raport["katalog_pracy_usuniety"] = not praca.exists()
        (dowody / "budowa.json").write_text(json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zapisz", action="store_true", help="wykonaj budowę; bez tego wyłącznie plan")
    p.add_argument("--katalog-pracy", type=Path, default=Path.home() / "mostek-mr18-budowa")
    p.add_argument("--wyjscie", type=Path, default=REPO.parent / "wydanie-test")
    p.add_argument("--commit", default="", help="pełny hash commitu źródeł")
    p.add_argument("--scena", type=Path, help="opcjonalny katalog kompletnej sceny BAZA z instrukcjami")
    p.add_argument("--prosty-start", action="store_true", help="START i PRZYWROC na wierzchu paczki")
    a = p.parse_args(argv)
    if not a.zapisz:
        print(json.dumps({"tryb": "plan, bez zapisu", "zrodla": str(REPO),
                          "katalog_pracy": str(a.katalog_pracy), "wyjscie": str(a.wyjscie),
                          "commit": a.commit, "programy": list(PROGRAMY), "scena": str(a.scena) if a.scena else None,
                          "zip": f"mostek-mr18-prosty-start-{a.commit[:7]}.zip" if a.prosty_start else NAZWA_ZIP,
                          "prosty_start": a.prosty_start, "format": "onedir, konsola, wspólny _internal",
                          "wymagania": "Python Windows x64 i PyInstaller; bez instalacji"},
                         ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(zbuduj(REPO, a.katalog_pracy.resolve(), a.wyjscie.resolve(), a.commit, a.scena, a.prosty_start),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
