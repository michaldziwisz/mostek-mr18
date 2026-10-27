"""Zgłoszenia /xremote spoza torów mostka (Michał, 23.10.2026).

Sonda strażnika ruszała co sekundę suwakiem nieużywanego kanału 16. Mikser
zgłaszał każdą zmianę, a mostek przy nieświeżym odczycie robił na każde
zgłoszenie pełny odczyt krytyczny: odczytów z 12 do 40 na minutę.
"""
from __future__ import annotations

import unittest

from pomoc import TestZSymulatorem, sciezki


class TestZgloszeniaSpozaTorow(TestZSymulatorem):
    def test_obcy_kanal_nie_wywoluje_odczytu(self):
        self.zegar.przesun(5.0)                     # odczyt nieświeży
        self.assertFalse(self.r._swiezy())
        przed = len(self.sym.zapytania)
        for i in range(10):
            self.inny(sciezki.fader(16), 0.1 * (i % 2))
            self.zegar.przesun(1.0)
        self.assertEqual(len(self.sym.zapytania) - przed, 0, "zgłoszenie ch16 nie wywołuje odczytu")
        self.assertEqual(self.slowa(), [])

    def test_kanal_mostka_dalej_czyta_i_odswieza(self):
        """Kontrola pozytywna: zgłoszenie toru mostka przy nieświeżym odczycie
        nadal daje pełny odczyt krytyczny (L02) i komunikat o zmianie."""
        self.zegar.przesun(5.0)
        przed = len(self.sym.zapytania)
        self.inny(sciezki.lr(9), 1)
        self.assertGreater(len(self.sym.zapytania) - przed, 10)
        self.assertTrue(self.r._swiezy())
        self.assertTrue(any("innego urządzenia" in s for s in self.slowa()))

    def test_mieszane_zgloszenia_czytaja_tor_mostka(self):
        self.zegar.przesun(5.0)
        self.transport.rozeslij(self.sym.zmien_z_innego(sciezki.fader(16), 0.3))
        self.inny(sciezki.lr(9), 1)
        self.assertTrue(self.r._swiezy())
        self.assertEqual(self.r.stan.wartosc(sciezki.lr(9)), 1)


if __name__ == "__main__":
    unittest.main()
