"""Dźwięk na włączenie i wyłączenie odsłuchu kontrolnego (Michał, 23.10.2026).

Oracle: lista dźwięków odtworzonych przez atrapę, słowa atrapy NVDA i stan
PFL w symulatorze („mikser”).
"""
from __future__ import annotations

import unittest

from pomoc import TestZSymulatorem
from mostek.informacja import AtrapaDzwiekow, InformacjaZwrotna, Tryb
from mostek.mowa import KolejkaMowy
from mostek.rdzen import Rdzen


class ZDzwiekami(TestZSymulatorem):
    tryb = Tryb.DZWIEKI_Z_MOWA

    def setUp(self):
        super().setUp()
        self.dzwieki = AtrapaDzwiekow()
        self.info = InformacjaZwrotna(self.u, self.dzwieki)
        self.info.tryb = self.tryb
        self.mowa = KolejkaMowy(self.wyjscie, alarm=None, dzwieki=self.info)
        self.r = Rdzen(self.u, self.klient, self.mowa, powierzchnia=self.pow, zegar=self.zegar, sen=self.zegar.sen)
        self.assertTrue(self.r.synchronizuj(nowa_baza_galek=True))
        self.mowa.oproznij()
        self.slowa()
        self.dzwieki.odtworzone.clear()

    def dz(self):
        self.mowa.oproznij()
        d = list(self.dzwieki.odtworzone)
        self.dzwieki.odtworzone.clear()
        return d


class TestDzwiekOdsluchu(ZDzwiekami):
    def test_pfl_muzyki_wlacz_i_wylacz(self):
        self.r.przelacz_pfl("muzyka1")
        self.assertTrue(self.pfl("muzyka1"))
        self.assertEqual(self.dz(), ["odsluch_wlaczony"])
        self.assertTrue(any("Odsłuch kontrolny" in s and "włączony" in s for s in self.slowa()))
        self.r.przelacz_pfl("muzyka1")
        self.assertFalse(self.pfl("muzyka1"))
        self.assertEqual(self.dz(), ["odsluch_wylaczony"])

    def test_koniec_pfl_dzwiek_wylaczenia(self):
        self.r.przelacz_pfl("muzyka2")
        self.dz()
        self.slowa()
        self.klawisz("koniec_pfl")
        self.assertFalse(self.pfl("muzyka2"))
        self.assertEqual(self.dz(), ["odsluch_wylaczony"])
        self.assertEqual(self.slowa(), ["Koniec odsłuchu kontrolnego"])

    def test_tryb_mowa_bez_dzwieku(self):
        self.info.tryb = Tryb.MOWA
        self.r.przelacz_pfl("muzyka1")
        self.assertEqual(self.dz(), [])
        self.assertTrue(self.slowa())

    def test_tryb_dzwieki_bez_mowy(self):
        self.info.tryb = Tryb.DZWIEKI
        self.r.przelacz_pfl("muzyka1")
        self.assertEqual(self.dz(), ["odsluch_wlaczony"])
        self.assertEqual(self.slowa(), [])

    def test_niepotwierdzony_bez_dzwieku_stanu(self):
        """Stan PFL nieznany po awarii: komunikat mową, bez dźwięku włączenia."""
        self.sym.awarie.rozlaczony = True
        self.r.przelacz_pfl("muzyka1")
        self.sym.awarie.rozlaczony = False
        self.assertNotIn("odsluch_wlaczony", self.dz())


if __name__ == "__main__":
    unittest.main()
