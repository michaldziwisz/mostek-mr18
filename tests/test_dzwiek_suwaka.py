"""Zgłoszenie Michała 22.10.2026: przy szybkich ruchach suwaka Zooma albo
słuchacza część przejść nie daje dźwięku, choć kanał wchodzi na antenę."""
import unittest

from pomoc import TestZSymulatorem


class TestDzwiekPrzySzybkimSuwaku(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.r.okres_krytyczny = 5.0          # jak na stanowisku od 7e7e465

    def _seria(self, zr, odstep):
        wyniki = []
        for i in range(8):
            poz = 1.0 if i % 2 == 0 else 0.0
            self.ruch(zr, poz)                 # dotyk, ruch, puszczenie, tick 0,6 s
            self.tick(odstep)
            wyniki.append((poz, self.slowa()))
        return wyniki

    def _plynny_ruch(self, zr, cel, czas=0.8):
        """Ręka prowadzi suwak płynnie przez `czas` sekund (zdarzenie co 50 ms,
        pętla mostka między nimi), puszcza, potem 1,5 s pracy pętli."""
        p = self.pasek(zr)
        start = 0.0 if cel else 1.0
        self.nacisnij("dotyk", p, True)
        kroki = int(czas / 0.05)
        for k in range(1, kroki + 1):
            self.zegar.przesun(0.05)
            self.r.zglos(("suwak", p, start + (cel - start) * k / kroki))
            self.r.tick()
        self.zegar.przesun(0.02)
        self.r.zglos(("dotyk", p, False))
        for _ in range(30):
            self.zegar.przesun(0.05)
            self.r.tick()
        return self.slowa()

    def test_plynny_ruch_zooma_ma_komunikat(self):
        """Ruch dłuższy niż ok. 0,7 s: odczyt sprzed ruchu jest za stary na
        decyzję (limit_swiezosci_s), a odczyt okresowy idzie co 5 s."""
        self.zegar.przesun(6)
        for cel, opis in ((1.0, "wejściu"), (0.0, "zejściu"), (1.0, "wejściu"), (0.0, "zejściu")):
            self.assertTrue(self._plynny_ruch("zoom", cel), f"brak komunikatu po {opis} Zooma")

    def test_plynny_ruch_sluchacza_ma_komunikat(self):
        self.zegar.przesun(6)
        for cel, opis in ((1.0, "wejściu"), (0.0, "zejściu"), (1.0, "wejściu"), (0.0, "zejściu")):
            self.assertTrue(self._plynny_ruch("telefon", cel), f"brak komunikatu po {opis} słuchacza")

    def _ruch_przy_wieku_odczytu(self, zr, cel, wiek):
        """Krótki ruch, a w chwili potwierdzenia odczyt krytyczny ma `wiek`
        sekund. Każdy odczyt miksera trwa 15 ms jak na stanowisku (dziennik
        z 26.10.2026: mediana 0 ms, 90% 16 ms), symulator odpowiada od razu."""
        p = self.pasek(zr)
        self.nacisnij("dotyk", p, True)
        self.nacisnij("suwak", p, cel)
        self.nacisnij("dotyk", p, False)
        self.zegar.przesun(self.r.zwloka_suwaka + 0.05)
        self.r._ost_swiezy = self.zegar() - wiek
        self.r.tick()
        return self.slowa()

    def test_komunikat_gdy_odczyt_tuz_przed_limitem(self):
        """Michał, 26.10.2026: przy ruchach suwaka czasem brak dźwięku. Dziennik
        z 25 i 26.10: 3 z 296 przejść rozmówców bez komunikatu, zapisy poszły.
        Odczyt sprzed ponad 0,5 s, ale jeszcze w limicie 1 s, nie był
        odświeżany, a trzy odczyty przejścia wypychały go za limit, więc
        _po_zmianie_suwaka milczał."""
        oryg = self.klient.odczytaj_wiele

        def z_czasem(adresy, _o=oryg):
            self.zegar.przesun(0.015)
            return _o(adresy)
        self.klient.odczytaj_wiele = z_czasem
        self.zegar.przesun(6)
        for wiek in (0.5, 0.8, 0.9, 0.95, 0.97, 0.99, 1.5):
            for cel, opis in ((1.0, "wejściu"), (0.0, "zejściu")):
                self.assertTrue(self._ruch_przy_wieku_odczytu("zoom", cel, wiek),
                                f"brak komunikatu po {opis} Zooma, odczyt sprzed {wiek} s")
                self.tick(2.0)
                self.slowa()

    def test_kazde_przejscie_zooma_ma_komunikat(self):
        for poz, slowa in self._seria("zoom", 1.0):
            self.assertTrue(slowa, f"brak komunikatu po suwaku Zooma na {poz}")

    def test_kazde_przejscie_sluchacza_ma_komunikat(self):
        for poz, slowa in self._seria("telefon", 1.5):
            self.assertTrue(slowa, f"brak komunikatu po suwaku słuchacza na {poz}")


if __name__ == "__main__":
    unittest.main()
