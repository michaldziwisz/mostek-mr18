"""Mutanty reakcji suwaka: oryginał i mutant w osobnych procesach, kod w pamięci."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'narzedzia'))
from mutacje_zapory import MUTANTY_POPRAWEK, MODUL_TESTU

MUTACJE = [
    (n, v[1], v[2], 'test_reakcja_suwaka.TestReakcjaSuwaka.' + v[3])
    for n, v in MUTANTY_POPRAWEK.items() if n.startswith('suwak_natychmiast_')
] + [
    ('dol_czeka_na_bezruch', 'if wartosc == 0.0 or (wartosc > 0 and (',
     'if wartosc > 0 and (wartosc > 0 and (',
     'test_reakcja_suwaka.TestReakcjaSuwaka.test_dol_natychmiast_i_powrot_po_potwierdzonym_main_off'),
    ('regulacja_zamiast_zapisu_tylko_odczyt',
     'if wartosc == 0.0 or (wartosc > 0 and (',
     'if True or (wartosc > 0 and (',
     'test_reakcja_suwaka.TestReakcjaSuwaka.test_ciagly_ruch_otwiera_od_pierwszego_zdarzenia'),
    ('zamkniecia_bez_dwoch_potwierdzen',
     '            oczek = {k.adres: k.wartosc for k in zamk}\n'
     '            zle = self._dwa_odczyty(oczek) if self.stan.polaczony else list(oczek)',
     '            oczek = {k.adres: k.wartosc for k in zamk}\n'
     '            zle = []  # MUTANT: pominięta weryfikacja zamknięć',
     'test_reakcja_suwaka.TestReakcjaSuwaka.test_potwierdzenia_prywatnych_i_glosnikow_przed_kazdym_otwarciem'),
]

MUTACJE += [(n, v[1], v[2], MODUL_TESTU[n] + '.' + v[3])
            for n, v in MUTANTY_POPRAWEK.items()
            if n.startswith('rozmowca_') and v[0] == 'mostek/rdzen.py']
for _zr, _klasa in (('telefon', 'TestTelefon'), ('zoom', 'TestZoom')):
    _test = 'test_reakcja_suwaka_rozmowcow.' + _klasa + '.'
    MUTACJE += [
        (_zr + '_decyzja_po_bezruchu',
         '        if zmiana_rozmowcy is not None:',
         f'        if zmiana_rozmowcy is not None and zr != {_zr!r}:',
         _test + 'test_ciagly_ruch_jeden_komunikat_i_przejscie'),
        (_zr + '_dol_po_bezruchu',
         '                if (wartosc > 0) != byl_w_gorze:',
         f'                if (wartosc > 0) != byl_w_gorze and not (zr == {_zr!r} and wartosc == 0):',
         _test + 'test_dol_zamyka_powrot_do_drugiego_natychmiast'),
        (_zr + '_powtorzone_przejscie_po_regulacji',
         '        if po_w_gorze != byl_w_gorze:',
         f'        if zr == {_zr!r} or po_w_gorze != byl_w_gorze:',
         _test + 'test_ciagly_ruch_jeden_komunikat_i_przejscie'),
    ]


MUTACJE += [(n, v[1], v[2], MODUL_TESTU[n] + '.TestKwantyzacjaMikrofonu.' + v[3])
            for n, v in MUTANTY_POPRAWEK.items() if n.startswith('kwantyzacja_')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.parse_args()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(ROOT / 'tests') + os.pathsep + str(ROOT))
    plik = ROOT / 'mostek' / 'rdzen.py'
    oryginal = plik.read_text(encoding='utf-8')
    wyniki = []
    for nazwa, stare, nowe, test in MUTACJE:
        if oryginal.count(stare) != 1:
            raise ValueError(f'{nazwa}: fragment nie występuje dokładnie raz')
        kod = oryginal.replace(stare, nowe)
        compile(kod, str(plik), 'exec')
        kontrola = subprocess.run([sys.executable, '-B', '-m', 'unittest', test, '-v'],
                                  cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        skrypt = (f'import mostek.rdzen as m, unittest\n'
                  f'exec(compile({kod!r}, {str(plik)!r}, "exec"), m.__dict__)\n'
                  f's=unittest.defaultTestLoader.loadTestsFromName({test!r})\n'
                  'r=unittest.TextTestRunner(verbosity=2).run(s)\n'
                  'raise SystemExit(0 if r.wasSuccessful() else 1)\n')
        mutant = subprocess.run([sys.executable, '-B', '-'], input=skrypt,
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        wyniki.append(dict(mutant=nazwa, test=test, kontrola_rc=kontrola.returncode,
                           mutant_rc=mutant.returncode,
                           zabity=kontrola.returncode == 0 and mutant.returncode == 1 and
                           'FAIL:' in mutant.stderr and 'ERROR:' not in mutant.stderr,
                           kontrola=kontrola.stdout + kontrola.stderr,
                           wynik_mutanta=mutant.stdout + mutant.stderr))
    print(json.dumps(wyniki, ensure_ascii=False, indent=2))
    return 0 if wyniki and all(w['zabity'] for w in wyniki) else 1


if __name__ == '__main__':
    raise SystemExit(main())
