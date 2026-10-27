"""Mutanty Hold uruchamiane w pamięci, z kontrolą pozytywną, bez edycji repo."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MUTACJE = [
    ('hold_fifo', 'playout', [
        ('self._kolejka.appendleft(zadanie)  # HOLD_PIERWSZENSTWO',
         'self._kolejka.append(zadanie)  # mutant FIFO')],
     'test_hold.TestHold.test_f1_wyprzedza_20_ruchow_i_dociera_przed_potwierdzeniem'),
    ('kaszel_zwalnia', 'rdzen', [
        ('if stan is False and self._mikrofon_sprzed is not None:  # HOLD_KASZEL',
         'if False:  # mutant zwolnienia przy kaszlu')],
     'test_hold.TestHold.test_kaszel_nie_zwalnia_ale_przelacznik_w_kaszlu_tak'),
    ('hold_do_spl', 'emisja', [
        ('if not self.sara:  # HOLD_TYLKO_SARA', 'if False:  # mutant ignoruje Helo SPL'),
        ('if p in {"hold", "hold=0", "hold=1"}:\n        return sara',
         'if p in {"hold", "hold=0", "hold=1"}:\n        return True')],
     'test_playout_tcp.TestProtokolHold.test_sesja_spl_nigdy_hold'),
    ('bez_zamiaru', 'rdzen', [
        ('self._zlec_hold(True)  # HOLD_ZAMIAR: przed potwierdzeniami miksera',
         'pass  # mutant bez zamiaru')],
     'test_hold.TestHold.test_f1_wyprzedza_20_ruchow_i_dociera_przed_potwierdzeniem'),
    ('rozmowcy_pominieci', 'rdzen', [
        ('if z.odbiorca is not None]  # HOLD_ROZMOWCY',
         'if False]  # mutant pomija rozmówców')],
     'test_hold.TestHoldRozmowcow.test_telefon_z_innego_urzadzenia_bez_mikrofonu'),
    ('nieznany_rozmowca_zwalnia', 'rdzen', [
        ('elif all(s is False for s in stany):  # HOLD_ZNANE_ZAMKNIECIE',
         'else:  # mutant myli NIEZNANY z zamknięciem')],
     'test_hold.TestHoldRozmowcow.test_nieznane_pola_rozmowcow_nie_zwalniaja'),
]


def main():
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'tests') + os.pathsep + str(ROOT))
    wyniki = []
    for nazwa, modul, zamiany, test in MUTACJE:
        plik = ROOT / 'mostek' / f'{modul}.py'
        kod = plik.read_text(encoding='utf-8')
        for stare, nowe in zamiany:
            assert kod.count(stare) == 1, (nazwa, stare)
            kod = kod.replace(stare, nowe)
        kontrola = subprocess.run([sys.executable, '-m', 'unittest', test, '-v'], cwd=ROOT,
                                  env=env, capture_output=True, text=True, timeout=20)
        skrypt = (f'import mostek.{modul} as m, unittest\n'
                  f'exec(compile({kod!r}, {str(plik)!r}, "exec"), m.__dict__)\n'
                  f's=unittest.defaultTestLoader.loadTestsFromName({test!r})\n'
                  'r=unittest.TextTestRunner(verbosity=2).run(s)\n'
                  'raise SystemExit(0 if r.wasSuccessful() else 1)\n')
        # Rozbudowany rdzeń przekracza limit pojedynczego argumentu systemu.
        # Kod nadal tylko w pamięci procesu, ale przez stdin zamiast python -c.
        mutant = subprocess.run([sys.executable, '-'], input=skrypt, cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=20)
        wyniki.append(dict(mutant=nazwa, test=test, kontrola_rc=kontrola.returncode,
                           mutant_rc=mutant.returncode,
                           zabity=kontrola.returncode == 0 and mutant.returncode == 1 and
                           'FAIL:' in mutant.stderr and 'ERROR:' not in mutant.stderr,
                           kontrola=kontrola.stdout + kontrola.stderr,
                           wynik_mutanta=mutant.stdout + mutant.stderr))
    print(json.dumps(wyniki, ensure_ascii=False, indent=2))
    return 0 if all(w['zabity'] for w in wyniki) else 1


if __name__ == '__main__':
    raise SystemExit(main())
