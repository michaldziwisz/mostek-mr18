"""Ręcznie zdefiniowane mutanty granic TCP; oryginalne pliki nietknięte.

Uruchom: python3 narzedzia/mutacje_emisji.py
Każdy mutant wykonuje się w świeżym procesie przez kompilację zmienionego
źródła w pamięci. Najpierw te same testy na oryginale (kontrola pozytywna).
"""
from pathlib import Path
import json
import os
import subprocess
import sys

KATALOG = Path(__file__).resolve().parents[1]
PLIK = KATALOG / "mostek" / "emisja.py"
MUTACJE = [
    ("limit_odpowiedzi", "self.g.settimeout(zostalo)  # ZAPORA_EMISJI_LIMIT",
     "self.g.settimeout(2.0)  # MUTANT: odpowiedź może przekroczyć limit",
     "test_playout_tcp.TestTCP.test_limit_odpowiedzi_i_ponowne_polaczenie"),
    ("filtr_polecen_spl", "if not dozwolone_polecenie(polecenie, self.sara):  # ZAPORA_EMISJI_POLECENIA",
     "if False:  # MUTANT: dowolny tekst trafia na TCP",
     "test_playout_tcp.TestTCP.test_filtr_polecen_nic_nie_wychodzi_do_spl"),
]


def main():
    env = dict(os.environ, PYTHONPATH=str(KATALOG / "tests") + os.pathsep + str(KATALOG))
    zrodlo = PLIK.read_text(encoding="utf-8")
    wyniki = []
    for nazwa, stare, nowe, test in MUTACJE:
        assert zrodlo.count(stare) == 1, (nazwa, "kotwica nie jest jednoznaczna")
        kontrola = subprocess.run([sys.executable, "-m", "unittest", test, "-v"],
                                  cwd=KATALOG, env=env, capture_output=True, text=True, timeout=10)
        kod = ("import mostek.emisja as m, unittest\n"
               f"exec(compile({zrodlo.replace(stare, nowe)!r}, {str(PLIK)!r}, 'exec'), m.__dict__)\n"
               f"suite=unittest.defaultTestLoader.loadTestsFromName({test!r})\n"
               "r=unittest.TextTestRunner(verbosity=2).run(suite)\n"
               "raise SystemExit(0 if r.wasSuccessful() else 1)\n")
        mutant = subprocess.run([sys.executable, "-c", kod], cwd=KATALOG, env=env,
                                capture_output=True, text=True, timeout=10)
        zabity = kontrola.returncode == 0 and mutant.returncode == 1 and "FAIL:" in mutant.stderr
        wyniki.append({"mutant": nazwa, "test": test, "kontrola_rc": kontrola.returncode,
                       "mutant_rc": mutant.returncode, "zabity": zabity,
                       "kontrola": kontrola.stdout + kontrola.stderr,
                       "wynik_mutanta": mutant.stdout + mutant.stderr})
    print(json.dumps(wyniki, ensure_ascii=False, indent=2))
    return 0 if all(w["zabity"] for w in wyniki) else 1


if __name__ == "__main__":
    raise SystemExit(main())
