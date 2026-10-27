"""Ruch mostka do MR18 na wartościach ze stanowiska (Michał, 22.10.2026).

Po wielu godzinach pracy MR18V2 fw 1.19 przestawał odpowiadać na sterowanie,
restart pomagał. Odczyt okresowy wszystkich torów krytycznych co 0,5 s dawał
ok. 140 zapytań na sekundę bez przerwy. Zmiany z innych urządzeń zgłasza
/xremote, więc pełny odczyt okresowy może iść rzadko. Bezpieczeństwo bez
zmian: przed każdym otwarciem świeży odczyt (limit_swiezosci_s)."""
import tempfile
import unittest
from pathlib import Path

import pomoc
from mostek import ustawienia
from mostek.logika import adresy_krytyczne
from mostek.rdzen import Rdzen
from mostek.klient import KlientMR18
from mostek.symulator import RdzenSymulatora
from mostek.transport import TransportPamieciowy
from mostek.mowa import KolejkaMowy


class LicznikTransport(TransportPamieciowy):
    def __init__(self, sym):
        super().__init__(sym)
        self.pytania = 0

    def _wyslij(self, ident, dane):
        self.pytania += 1
        return super()._wyslij(ident, dane)


class TestRuchDoMiksera(unittest.TestCase):
    def test_plik_stanowiska_ma_rzadki_odczyt_okresowy(self):
        u = ustawienia.wczytaj()
        self.assertGreaterEqual(float(u.mikser["okres_odczytu_krytycznego_s"]), 5.0)
        self.assertLessEqual(float(u.mikser["limit_swiezosci_s"]), 1.0,
                             "otwarcia dalej tylko na świeżym odczycie")

    def test_minuta_bez_zdarzen_to_kilkanascie_odczytow(self):
        with tempfile.TemporaryDirectory() as tmp:
            u = ustawienia.wczytaj()
            u.plik_trybu = Path(tmp) / "tryb_informacji.json"
            zegar = pomoc.Zegar()
            sym = RdzenSymulatora(zegar=zegar)
            tr = LicznikTransport(sym)
            k = KlientMR18(tr, limit_odpowiedzi_s=0.01, dodatkowe_proby=2)
            mowa = KolejkaMowy(pomoc.AtrapaMowy(), alarm=None, dzwieki=None)
            r = Rdzen(u, k, mowa, powierzchnia=pomoc.AtrapaPowierzchni(), zegar=zegar, sen=zegar.sen)
            try:
                self.assertTrue(r.synchronizuj(nowa_baza_galek=True))
                start = tr.pytania
                for _ in range(600):              # 60 s co 0,1 s
                    zegar.przesun(0.1)
                    r._tick()
                na_minute = tr.pytania - start
            finally:
                k.zamknij()
        n = len(adresy_krytyczne(u))
        # 12 pełnych odczytów w minucie plus odnowienia /xremote i mierników.
        self.assertLess(na_minute, n * 15, f"{na_minute} zapytań na minutę")
        self.assertGreater(na_minute, n * 10)


if __name__ == "__main__":
    unittest.main()
