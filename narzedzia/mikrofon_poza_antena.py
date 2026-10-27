"""Awaryjne „mikrofon poza anteną”: osobny, jednorazowy program (plan, rozdz. 13, pkt 2).

Nie dzieli procesu z mostkiem: przypisany do globalnego skrótu Windows
działa także wtedy, gdy mostek się zawiesił. Wysyła do MR18 jawne
Main On mikrofonu = 0, czeka na odczyt i mówi wynik przez NVDA (albo w
konsoli). Kanał mikrofonu bierze z pliku ustawień.

    python narzedzia\\mikrofon_poza_antena.py --mr18 192.168.1.50 --mowa nvda

Opcja --wycisz dodatkowo ustawia zwykłe Mute kanału (ostateczność: odcina
też rozmowę z telefonem i Zoomem).
NIE SPRAWDZONO na MR18. Sprawdzone tylko wobec symulatora.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KATALOG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KATALOG))

from mostek import mowa as mowa_mod  # noqa: E402
from mostek import sciezki, ustawienia  # noqa: E402
from mostek.klient import BrakOdpowiedzi, KlientMR18  # noqa: E402
from mostek.transport import TransportUDP  # noqa: E402


def wykonaj(klient: KlientMR18, kanaly, wycisz: bool = False) -> tuple[bool, str]:
    try:
        ok = all(klient.ustaw(sciezki.lr(k), 0).potwierdzony for k in kanaly)
        if wycisz:
            ok = all(klient.ustaw(sciezki.mute_kanalu(k), 0).potwierdzony for k in kanaly) and ok
    except BrakOdpowiedzi:
        return False, "Brak łączności z mikserem, mikrofon może być na antenie"
    if ok:
        return True, "Mikrofon poza anteną, potwierdzone przez mikser" + (", wyciszony wszędzie" if wycisz else "")
    return False, "Uwaga, mikser nie potwierdził, mikrofon może być na antenie"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Awaryjne zdjęcie mikrofonu z anteny")
    p.add_argument("--mr18", required=True)
    p.add_argument("--port", type=int, default=10024)
    p.add_argument("--mowa", choices=("konsola", "nvda"), default="konsola")
    p.add_argument("--wycisz", action="store_true")
    a = p.parse_args(argv)
    u = ustawienia.wczytaj()
    try:
        wyjscie = mowa_mod.utworz_wyjscie(a.mowa)
    except mowa_mod.BrakNVDA:
        wyjscie = mowa_mod.MowaKonsola()
    klient = KlientMR18(TransportUDP(a.mr18, a.port), limit_odpowiedzi_s=0.3, dodatkowe_proby=2)
    try:
        ok, tekst = wykonaj(klient, u.zrodla["mikrofon"].kanaly, a.wycisz)
    finally:
        klient.zamknij()
    try:
        wyjscie.mow(tekst)
    except Exception:  # noqa: BLE001
        print(tekst)
        mowa_mod.dzwiek_alarmu()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
