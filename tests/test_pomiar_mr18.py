"""Zachowania prawdziwego MR18V2 fw 1.19 zmierzone w pomiarze 18.10.2026.

Dziennik mostka: co ok. 3 s „Brak łączności z mikserem” mimo działającej
sieci. Mikser nie odpowiadał na /ch/09/insert/fxslot, a każda nieudana próba
pełnego odczytu ogłaszała utratę od nowa. Właściwa ścieżka to /insert/sel.
"""
from __future__ import annotations

import unittest

from mostek import sciezki
from tests.pomoc import TestZSymulatorem


class TestPomiarMR18(TestZSymulatorem):
    def test_insert_to_sel(self):
        self.assertEqual(sciezki.insert_fxslot(9), "/ch/09/insert/sel")
        self.assertTrue(sciezki.znana(sciezki.insert_fxslot(9)) if hasattr(sciezki, "znana") else True)

    def test_utrata_ogloszona_raz_mimo_ponowien(self):
        """Mikser odpowiada na /xinfo, ale nie na jedną ścieżkę pełnego odczytu."""
        brak = sciezki.insert_fxslot(9)
        oryginal = self.sym._obsluz

        def obsluz(k, nadawca):
            if k.adres == brak:
                return []
            return oryginal(k, nadawca)
        self.sym._obsluz = obsluz
        self.zegar.przesun(1.0)
        self.assertFalse(self.r.synchronizuj())
        mowa = self.czekaj(20.0, krok=1.0) + self.slowa()
        utraty = [m for m in mowa if "Brak łączności z mikserem" in m]
        self.assertLessEqual(len(utraty), 1, mowa)

    def test_powrot_po_utracie_nadal_ogloszony(self):
        self.sym.awarie.rozlaczony = True
        self.czekaj(6.0, krok=1.0)
        self.slowa()
        self.sym.awarie.rozlaczony = False
        mowa = self.czekaj(6.0, krok=1.0) + self.slowa()
        self.assertTrue(any("łączność" in m.lower() or "lacznosc" in m.lower() or "Łączność" in m for m in mowa), mowa)


class TestWyborPortuXTouch(unittest.TestCase):
    """Pomiar 18.10.2026: mostek bez reakcji na klawisze i suwaki, w dzienniku
    zero zdarzeń z kontrolera, port otwarty bez błędu."""

    def test_port_sterujacy_przed_przelotka(self):
        from mostek.xtouch import wybierz_port
        self.assertEqual(wybierz_port(["MIDIIN2 (X-TOUCH)", "X-TOUCH"]), 1)
        self.assertEqual(wybierz_port(["MIDIOUT2 (X-TOUCH)", "Microsoft GS", "X-TOUCH"]), 2)
        self.assertEqual(wybierz_port(["X-Touch EXT", "X-Touch INT"]), 1)
        self.assertEqual(wybierz_port(["X-Touch_EXT", "X-Touch_INT"]), 1)
        self.assertEqual(wybierz_port(["X-TOUCH"]), 0)
        self.assertEqual(wybierz_port(["2- X-TOUCH", "MIDIIN2 (2- X-TOUCH)"]), 0)
        self.assertIsNone(wybierz_port(["Microsoft GS Wavetable Synth"]))


class TestSuwakiWracaja(unittest.TestCase):
    """Pomiar 18.10.2026: suwak po puszczeniu wraca na górę bez komunikatu."""

    def test_echo_pozycji_suwaka_do_stolu(self):
        from mostek import ustawienia as ust
        from mostek.xtouch import AtrapaPortuMIDI, MapaMC, PowierzchniaXTouch
        import tempfile
        from pathlib import Path
        u = ust.wczytaj()
        port = AtrapaPortuMIDI()
        zdarzenia = []
        p = PowierzchniaXTouch(MapaMC(u.xtouch), port, zdarzenia.append)
        port.wstrzyknij(0x90, 0x68, 0x7F)          # dotyk paska 1
        port.wstrzyknij(0xE0, 0x10, 0x20)          # pozycja suwaka
        self.assertIn(bytes((0xE0, 0x10, 0x20)), port.wyslane, "brak echa pozycji")
        port.wyslane.clear()
        p.ustaw_suwak(1, 0.0)                      # odczyt miksera: dół
        self.assertIn(bytes((0xE0, 0x00, 0x00)), port.wyslane)
        port.wstrzyknij(0x90, 0x68, 0x00)          # puszczenie paska 1
        port.wyslane.clear()
        port.wstrzyknij(0xE0, 0x7F, 0x7F)          # bez dotyku (silnik): bez echa
        self.assertEqual(port.wyslane, [])


class TestSilnikPoPotwierdzeniu(TestZSymulatorem):
    def test_silnik_wg_miksera_po_puszczeniu(self):
        p = self.pasek("telefon")
        self.nacisnij("dotyk", p, True)
        self.nacisnij("suwak", p, 0.5)
        self.nacisnij("dotyk", p, False)
        self.pow.suwaki.pop(p, None)
        self.tick(0.6)
        self.assertIn(p, self.pow.suwaki, "po potwierdzeniu silnik nie dostał pozycji")
        from mostek.konwersje import poziom_db_na_float  # noqa: F401
        self.assertAlmostEqual(self.pow.suwaki[p], 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
