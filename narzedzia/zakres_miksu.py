"""Porównanie chronionego kodu i dźwięków z bazą karty, bez modyfikacji repo."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BAZA = '805a96f14aac362809b19e8012d53a588300149a'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def funkcje(kod):
    modul = ast.parse(kod)
    # Docstring nie zmienia zachowania; porównujemy instrukcje wykonywalne.
    for f in ast.walk(modul):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(f):
            f.body = f.body[1:]
    wynik = {}
    for wezel in modul.body:
        if isinstance(wezel, ast.ClassDef):
            for f in wezel.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    wynik[wezel.name + '.' + f.name] = ast.dump(f, include_attributes=False)
        elif isinstance(wezel, ast.FunctionDef):
            wynik[wezel.name] = ast.dump(wezel, include_attributes=False)
    return wynik


def main():
    pliki = git('ls-tree', '-r', '--name-only', BAZA).decode().splitlines()
    chronione = [p for p in pliki if p.startswith(('dzwieki/', 'dane_sceny/')) or p in (
        'mostek/logika.py', 'mostek/klient.py', 'mostek/sciezki.py', 'mostek/stan.py', 'mostek/transport.py')]
    hashe = []
    for p in chronione:
        stare = hashlib.sha256(git('show', f'{BAZA}:{p}')).hexdigest()
        nowe = hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        hashe.append(dict(plik=p, baza_sha256=stare, teraz_sha256=nowe, zgodny=stare == nowe))
    funkcje_chronione = {}
    for p, dopuszczone in (
        ('mostek/rdzen.py', {'Rdzen.zglos'}),
        ('mostek/emisja.py', {'dozwolone_polecenie'}),
        ('mostek/playout.py', {'TorEmisji.__init__', 'TorEmisji.zlec', 'TorEmisji._petla',
                              'TorEmisji.czekaj', 'TorEmisji.zamknij'})):
        stare = funkcje(git('show', f'{BAZA}:{p}'))
        nowe = funkcje((ROOT / p).read_bytes())
        roznice = [n for n in stare if stare[n] != nowe.get(n)]
        funkcje_chronione[p] = dict(zmienione=roznice, niedozwolone=sorted(set(roznice) - dopuszczone))
    wynik = dict(baza=BAZA, pliki=hashe, funkcje=funkcje_chronione,
                 zgodne=all(h['zgodny'] for h in hashe) and
                        all(not f['niedozwolone'] for f in funkcje_chronione.values()))
    print(json.dumps(wynik, ensure_ascii=False, indent=2))
    return 0 if wynik['zgodne'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
