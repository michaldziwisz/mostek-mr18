"""Mutanty walidatora w pamięci procesu, bez zmiany plików źródeł.

Każdy mutant wymaga zielonej kontroli i porażki asercji, nie błędu importu.
"""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MUTACJE = [
    ('wspolne_szyny', 'walidator',
     [('if bus in zajete_szyny:  # WAL_ROZLACZNOSC', 'if False:  # mutant wspólnych szyn')],
     'test_rozlacznosc_szyn'),
    ('duplikat_paska', 'walidator',
     [('if numer in paski:  # WAL_PASKI', 'if False:  # mutant duplikatu paska')],
     'test_unikalnosc_paska'),
    ('kanal_poza_zakresem', 'walidator',
     [("'kanaly': lista(calkowita(1, PROFIL_V1['wejscia']),", "'kanaly': lista(calkowita(1, 99),")],
     'test_zakres_kanalu'),
    ('typ_przed_konwersja', 'walidator',
     [("self.dodaj(path, f'niewłaściwy typ; wymagany: {s.typ}' + (' albo null' if s.null else ''))", 'pass  # mutant ignoruje niezgodny typ')],
     'test_typy_przed_konwersja'),
    ('powiazanie_odwrotne', 'walidator',
     [("elif zrodla[wlasne].get('odbiorca') != n:  # WAL_POWIAZANIE", 'elif False:  # mutant powiązania')],
     'test_powiazanie_w_obie_strony'),
    ('pierwszy_problem', 'walidator',
     [('return k.problemy  # WAL_ZBIERANIE', 'return k.problemy[:1]  # mutant pierwszego problemu')],
     'test_zbiera_wiele_i_nie_mutuje'),
    ('sprawdz_otwiera_osc', 'glowny',
     [('if a.sprawdz:  # WAL_OFFLINE: przed dziennikiem i każdym urządzeniem',
       'if a.sprawdz:\n        TransportUDP("127.0.0.1", 10024).otworz_kanal(lambda *a: None)  # mutant OSC')],
     'test_cli_bez_sprzetu_i_zapisow'),
    ('zla_sciezka_indeksu', 'walidator',
     [("self.sprawdz(x, s.element, f'{path}[{i}]')", "self.sprawdz(x, s.element, f'{path}.{i}')")],
     'test_zakres_kanalu'),
]


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='wynik JSON (również domyślnie)')
    parser.parse_args(argv)
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'tests') + os.pathsep + str(ROOT),
               PYTHONDONTWRITEBYTECODE='1')
    wyniki = []
    for nazwa, modul, zamiany, metoda in MUTACJE:
        plik = ROOT / 'mostek' / f'{modul}.py'
        kod = plik.read_text(encoding='utf-8')
        for stare, nowe in zamiany:
            assert kod.count(stare) == 1, (nazwa, stare)
            kod = kod.replace(stare, nowe)
        test = 'test_walidator.TestWalidator.' + metoda
        kontrola = subprocess.run([sys.executable, '-B', '-m', 'unittest', test, '-v'],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        skrypt = (f'import mostek.{modul} as m, unittest\n'
                  f'exec(compile({kod!r}, {str(plik)!r}, "exec"), m.__dict__)\n'
                  f's = unittest.defaultTestLoader.loadTestsFromName({test!r})\n'
                  'r = unittest.TextTestRunner(verbosity=2).run(s)\n'
                  'raise SystemExit(0 if r.wasSuccessful() else 1)\n')
        mutant = subprocess.run([sys.executable, '-B', '-'], input=skrypt, cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30)
        wyniki.append(dict(mutant=nazwa, test=test, kontrola_rc=kontrola.returncode,
            mutant_rc=mutant.returncode,
            zabity=kontrola.returncode == 0 and mutant.returncode == 1 and
                   'FAIL:' in mutant.stderr and 'ERROR:' not in mutant.stderr,
            kontrola=kontrola.stdout + kontrola.stderr,
            wynik_mutanta=mutant.stdout + mutant.stderr))
    print(json.dumps({'oryginal_ok': all(w['kontrola_rc'] == 0 for w in wyniki),
        'zabite': sum(w['zabity'] for w in wyniki), 'wszystkie': len(wyniki),
        'wyniki': wyniki}, ensure_ascii=False, indent=2))
    return 0 if all(w['zabity'] for w in wyniki) else 1


if __name__ == '__main__':
    raise SystemExit(main())
