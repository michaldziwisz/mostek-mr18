"""Tryb nauki klawiszy (Michał, 24.10.2026): stół się przedstawia i nic nie robi."""
import logging
import unittest

from mostek import emisja, sciezki
from mostek.xtouch import MapaMC
from tests.atrapa_playoutu import SerwerPlayoutu
from tests.pomoc import TestZSymulatorem

START = ("Nauka klawiszy. Każdy klawisz mówi swoją nazwę i nic nie robi. "
         "Suwaki działają. Koniec: ten sam klawisz")


class TestNaukaKlawiszy(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.s = SerwerPlayoutu(True)
        self.addCleanup(self.s.zamknij)
        self.r.emisja = emisja.SARA(self.s.port, limit_s=0.1)
        self.mapa = MapaMC(self.u.xtouch)

    def midi(self, *bajty):
        self.zegar.przesun(0.2)
        z = self.mapa.zdarzenie(list(bajty))
        for zd in (z if isinstance(z, list) else [z]):
            self.r.zglos(zd)

    def nuta(self, n):
        self.midi(0x90, n, 127)

    def wlacz(self):
        self.nuta(91)
        self.assertEqual(self.slowa(), [START])

    def test_rewind_wlacza_i_wylacza(self):
        self.wlacz()
        self.nuta(91)
        self.assertEqual(self.slowa(), ["Koniec nauki klawiszy"])
        self.assertIsNone(self.r._nauka_od)

    def test_klawisze_mowia_nazwy_mackie_i_funkcje(self):
        self.wlacz()
        oczekiwane = {
            0x50: "Save, wolny", 0x51: "Undo, wolny", 0x52: "Cancel, wolny", 0x53: "Enter, wolny",
            0x54: "Marker, wolny", 0x55: "Nudge, wolny", 0x56: "Cycle, wolny",
            0x65: "Scrub, punkty miksu", 0x64: "Zoom, w punktach miksu ustaw punkt, poza nimi znacznik do emisji", 0x5E: "Play, Play w programie",
            0x36: "F1, mikrofon", 0x5C: "Przewijanie do przodu, wolny",
            0x60: "Strzałka w górę, w górę po playliście",
        }
        for n, tekst in oczekiwane.items():
            self.nuta(n)
            self.assertEqual(self.slowa(), [tekst], hex(n))

    def test_nic_nie_robi_mikser_ani_program(self):
        self.wlacz()
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        mikrofon = [self.m(a) for a in self.r.widok.adresy_sumy("mikrofon")]
        for n in (0x36, 0x37, 0x38, 0x3B, 0x3C, 0x3D, 0x5D, 0x5E, 0x5F, 0x60, 0x61, 0x64, 0x44, 0x45):
            self.nuta(n)
        self.midi(0x90, 0x18, 127)      # SELECT paska 1: mikrofon na antenę
        self.midi(0x90, 0x00, 127)      # REC paska 1: alarm ciszy
        self.midi(0x90, 0x19, 127)      # SELECT paska 2: CUE telefonu
        self.midi(0x90, 0x10, 127)      # MUTE paska 1: kaszel
        self.midi(0x90, 0x20, 127)      # wciśnięcie gałki 1
        self.midi(0xB0, 0x10, 0x03)     # gałka 1 o trzy ząbki w prawo
        self.midi(0xB0, 60, 0x41)       # kółko w lewo
        self.slowa()
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania, "bez odczytu miksera")
        self.assertEqual(self.s.polecenia, [], "bez poleceń do SARY")
        self.assertEqual([self.m(a) for a in self.r.widok.adresy_sumy("mikrofon")], mikrofon)
        self.assertTrue(self.r.alarm_wlaczony)
        # Puszczenie MUTE idzie zwykłą drogą (koniec kaszlu): bez kaszlu nic nie zapisuje.
        self.midi(0x80, 0x10, 0)
        self.slowa()
        self.assertEqual(self.zapisy(od), [])

    def test_paski_galki_i_kolko(self):
        self.wlacz()
        self.midi(0x90, 0x18, 127)
        self.assertEqual(self.slowa(), ["Pasek 1, Select, mikrofon"])
        self.midi(0x90, 0x19, 127)
        self.assertEqual(self.slowa(), ["Pasek 2, Select, CUE telefonu"])
        self.midi(0x90, 0x1B, 127)
        self.assertEqual(self.slowa(), ["Pasek 4, Select, odsłuch kontrolny muzyki 1"])
        self.midi(0x90, 0x10, 127)
        self.assertEqual(self.slowa(), ["Pasek 1, Mute, kaszel"])
        self.midi(0x90, 0x08, 127)
        self.assertEqual(self.slowa(), ["Pasek 1, Solo"])
        self.midi(0x90, 0x21, 127)
        self.assertEqual(self.slowa(), ["Wciśnięcie gałki 2"])
        self.midi(0xB0, 0x12, 0x41)
        self.assertEqual(self.slowa(), ["Gałka 3, w lewo"])
        self.midi(0xB0, 60, 0x01)
        self.assertEqual(self.slowa(), ["Kółko, w prawo"])

    def test_nieznana_nuta_mowi_numer(self):
        self.wlacz()
        self.nuta(0x7E)
        self.assertEqual(self.slowa(), ["Klawisz numer 126, wolny"])

    def test_dziennik_zapisuje_numer_midi(self):
        self.wlacz()
        with self.assertLogs("mostek.rdzen", logging.INFO) as dz:
            self.nuta(0x54)
            self.midi(0x90, 0x19, 127)
        tekst = "\n".join(dz.output)
        self.assertIn("nuta 84 (0x54) nuta_84, mówi: Marker, wolny", tekst)
        self.assertIn("nuta 25 (0x19) pasek 2 select", tekst)

    def test_suwak_dziala_w_nauce(self):
        """Ściągnięcie suwaka nadal zdejmuje telefon z anteny."""
        self.klawisz("F3_koniec_rozmowy"); self.slowa()
        self.nacisnij("dotyk", 2, True)
        self.nacisnij("suwak", 2, 1.0)
        self.nacisnij("dotyk", 2, False)
        self.tick(0.6)
        self.slowa()
        self.assertIn("telefon", self.antena())
        self.wlacz()
        self.nacisnij("dotyk", 2, True)
        self.nacisnij("suwak", 2, 0.0)
        self.nacisnij("dotyk", 2, False)
        self.tick(0.6)
        self.slowa()
        self.assertNotIn("telefon", self.antena())
        self.assertIsNotNone(self.r._nauka_od, "suwak nie kończy nauki")

    def test_koniec_po_minucie_bez_nacisniecia(self):
        self.wlacz()
        koniec = "Koniec nauki klawiszy, minuta bez naciśnięcia"
        self.czekaj(50); self.nuta(0x54); self.slowa()
        self.assertNotIn(koniec, self.czekaj(55))
        self.assertIn(koniec, self.czekaj(10))
        self.nuta(0x5E)
        self.assertEqual(self.slowa(), ["Gra"])

    def test_po_nauce_klawisze_dzialaja(self):
        self.wlacz()
        self.nuta(0x5E); self.slowa()
        self.assertEqual(self.s.polecenia, [])
        self.nuta(91); self.slowa()
        self.nuta(0x5E)
        self.assertEqual(self.slowa(), ["Gra"])
        self.assertIn("Play", self.s.polecenia)

    def test_drganie_styku_jeden_komunikat(self):
        self.wlacz()
        self.zegar.przesun(0.2)
        z = self.mapa.zdarzenie([0x90, 0x54, 127])
        self.r.zglos(z)
        self.zegar.przesun(0.01)
        self.r.zglos(z)
        self.assertEqual(self.slowa(), ["Marker, wolny"])

    def test_nauka_z_konsoli(self):
        from mostek.glowny import polecenie_konsoli
        self.assertEqual(polecenie_konsoli("nauka"), ("klawisz", "nauka_klawiszy"))

    def test_mowa_nauki_przerywalna(self):
        from mostek.mowa import KolejkaMowy
        self.assertIn("nauka", KolejkaMowy.PRZERYWALNE)


if __name__ == "__main__":
    unittest.main()
