"""Narzędzia przy mostku: zakres scen AOSC bez routingu."""

import sys
import unittest
from pathlib import Path

from pomoc import KATALOG, sciezki

sys.path.insert(0, str(KATALOG / "narzedzia"))
import zakres_scen_aosc as z  # noqa: E402

import json  # noqa: E402

# Pełna lista węzłów sceny MR18 z własnego schematu (jedna ścieżka w wierszu, jak x.sct).
PELNY_ZAKRES = "\n".join(json.loads((KATALOG / "dane_sceny" / "schemat-mr18.json").read_text(encoding="utf-8"))["wezly"]) + "\n"

PROBKA = (
    "/config/chlink OFF OFF OFF OFF OFF OFF OFF OFF\r\n"
    "/config/solo   0.0 LRAFL 0.0 PFL PFL -20 OFF OFF OFF OFF\r\n"
    "/ch/09/config \"\" 0 In09 U09\r\n"
    "/ch/09/preamp +0.0 OFF OFF OFF  20\r\n"
    "/ch/09/eq ON\r\n"
    "/ch/09/mix ON   -oo ON +0\r\n"
    "/ch/09/mix/01   -oo OFF POSTEQ +0\r\n"
    "/ch/10/dyn ON COMP PEAK LIN -20.0 3.0 1 0.00 10 10.0 100 POST 0 100 OFF\r\n"
    "/bus/5/mix ON   0.0 OFF +0\r\n"
    "/bus/5/eq ON\r\n"
    "/lr/mix ON   -oo +0\r\n"
    "/lr/eq ON\r\n"
    "/routing/usb/03 Ch03 AIN\r\n"
    "/headamp/09 +20.0 ON\r\n"
)


class TestZakresScen(unittest.TestCase):
    def test_usuwa_tory_anteny_i_rozmowcow(self):
        nowy, usuniete, _ = z.filtruj(PROBKA)
        sciezki = {s for s, _p in usuniete}
        for s in ("/ch/09/mix", "/ch/09/mix/01", "/bus/5/mix", "/lr/mix", "/routing/usb/03",
                  "/config/solo", "/config/chlink", "/ch/09/config"):
            self.assertIn(s, sciezki)
            self.assertNotIn(s + " ", nowy)

    def test_zostawia_brzmienie(self):
        nowy, _, zostawione = z.filtruj(PROBKA)
        for s in ("/ch/09/preamp", "/ch/09/eq", "/ch/10/dyn", "/bus/5/eq", "/lr/eq", "/headamp/09"):
            self.assertIn(s + " ", nowy)
        self.assertEqual(zostawione, 6)

    def test_zachowuje_konce_wierszy_i_kolejnosc(self):
        nowy, _, _ = z.filtruj(PROBKA)
        self.assertTrue(all(w.endswith("\r\n") for w in nowy.splitlines(keepends=True)))
        kolejnosc = [w.split()[0] for w in nowy.splitlines()]
        self.assertEqual(kolejnosc, ["/ch/09/preamp", "/ch/09/eq", "/ch/10/dyn", "/bus/5/eq",
                                     "/lr/eq", "/headamp/09"])

    def test_nie_myli_podobnych_sciezek(self):
        # /fxsend/N/mix to poziom wyjściowy szyny FX; wysyłki do FX znikają razem z /ch/NN/mix/NN.
        self.assertIsNone(z.powod_usuniecia("/fxsend/1/mix"))
        self.assertIsNone(z.powod_usuniecia("/ch/09/mixer"))
        self.assertIsNotNone(z.powod_usuniecia("/ch/09/mix/10"))

    def test_pelny_zakres_sceny(self):
        nowy, usuniete, zostawione = z.filtruj(PELNY_ZAKRES)
        self.assertEqual(z.sprawdz_wynik(nowy), [])
        self.assertEqual(zostawione + len(usuniete), 693)
        sciezki = [w.split()[0] for w in nowy.splitlines() if w.startswith("/")]
        self.assertFalse(any(s.startswith(("/routing", "/lr/mix")) for s in sciezki))
        self.assertFalse(any(s.startswith("/ch/") and "/mix" in s for s in sciezki))
        self.assertIn("/ch/09/eq", sciezki)
        self.assertIn("/headamp/10", sciezki)

    def test_bez_zapisz_nic_nie_zapisuje(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            wej = Path(d) / "x.sct"
            wej.write_text(PROBKA, encoding="utf-8", newline="")
            wyj = Path(d) / "y.sct"
            self.assertEqual(z.main([str(wej), "--wyjscie", str(wyj)]), 0)
            self.assertFalse(wyj.exists())
            self.assertEqual(z.main([str(wej), "--wyjscie", str(wej), "--zapisz"]), 2)
            self.assertEqual(wej.read_text(encoding="utf-8"), PROBKA.replace("\r\n", "\n"))
            self.assertEqual(z.main([str(wej), "--wyjscie", str(wyj), "--zapisz"]), 0)
            self.assertTrue(wyj.exists())


class TestBadanieMR18(unittest.TestCase):
    def setUp(self):
        import badanie_mr18 as b
        from mostek.symulator import SerwerSymulatora
        from mostek.transport import TransportUDP
        self.b = b
        self.s = SerwerSymulatora(port=0).start()
        self.transport = TransportUDP(*self.s.adres)
        self.adresy = [sciezki.lr(9), sciezki.wysylka(9, 1), sciezki.MONITOR_ZRODLO]

    def tearDown(self):
        self.s.stop()

    def test_tylko_odczyt(self):
        przed = dict(self.s.rdzen.wartosci)
        r = self.b.zbadaj(self.transport, self.adresy, limit_s=0.05)
        self.assertEqual(self.s.rdzen.dziennik, [], "badanie nie może niczego zapisać")
        self.assertEqual(self.s.rdzen.wartosci, przed)
        self.assertEqual(self.s.rdzen.subskrybenci, {}, "badanie nie wysyła /xremote")
        self.assertEqual(r["bez_odpowiedzi"], [])
        self.assertEqual(r["typ_niezgodny"], [])
        self.assertIn("/xinfo", r["identyfikacja"])

    def test_brak_sciezki_i_zly_typ_wykryte(self):
        del self.s.rdzen.wartosci[sciezki.MONITOR_ZRODLO]
        self.s.rdzen.wartosci[sciezki.lr(9)] = 0.5      # symulator odda float zamiast int
        orig = self.s.rdzen._typ
        self.s.rdzen._typ = lambda a: "f" if a == sciezki.lr(9) else orig(a)
        r = self.b.zbadaj(self.transport, self.adresy, limit_s=0.05, proby=2)
        self.assertEqual(r["bez_odpowiedzi"], [sciezki.MONITOR_ZRODLO])
        self.assertEqual(r["typ_niezgodny"], [sciezki.lr(9)])

    def test_mierniki_bez_zapisu(self):
        przed = dict(self.s.rdzen.wartosci)
        m = self.b.zbadaj_mierniki(self.transport, limit_s=1.0)
        self.assertTrue(m["odpowiedz"])
        self.assertEqual(m["kolejnosci"]["little"]["liczba_wartosci"], 44)
        self.assertEqual(m["kolejnosci"]["little"]["main_lr_db"], [-18.0, -18.0])
        self.assertEqual(self.s.rdzen.dziennik, [], "subskrypcja mierników niczego nie zapisuje")
        self.assertEqual(self.s.rdzen.wartosci, przed)
        self.assertEqual(self.s.rdzen.subskrybenci, {}, "bez /xremote")

    def test_lista_obejmuje_klucz_i_glosniki_v22(self):
        from mostek import ustawienia
        from mostek.logika import wszystkie_adresy_odczytu
        lista = set(wszystkie_adresy_odczytu(ustawienia.wczytaj()))
        for a in (sciezki.mute_szyny(5), sciezki.mute_szyny(6), sciezki.fader_szyny(5), sciezki.szyna_lr(5),
                  sciezki.buslink(5), sciezki.wysylka(9, 5), sciezki.wysylka(7, 5), sciezki.wysylka(8, 5),
                  sciezki.tap(9, 5), sciezki.tap(7, 5), sciezki.keysrc(10), sciezki.dyn_on(10),
                  sciezki.insert_fxslot(9), sciezki.insert_fxslot(10), sciezki.insert_on(10)):
            self.assertIn(a, lista)

    def test_milczacy_mikser(self):
        self.s.rdzen.awarie.rozlaczony = True
        r = self.b.zbadaj(self.transport, self.adresy, limit_s=0.02, proby=1)
        self.assertEqual(r["identyfikacja"], {})
        self.assertEqual(len(r["bez_odpowiedzi"]), 3)

    def test_lista_badania_obejmuje_sciezki_modelu_cue(self):
        """Badanie czyta każdą ścieżkę, którą mostek odczytuje albo zapisuje."""
        from mostek import ustawienia
        from mostek.logika import adresy_krytyczne, wszystkie_adresy_odczytu
        u = ustawienia.wczytaj()
        lista = set(wszystkie_adresy_odczytu(u))
        self.assertTrue(set(adresy_krytyczne(u)) <= lista)
        for a in (sciezki.tap(9, 1), sciezki.tap(9, 3), sciezki.tap(9, 4), sciezki.tap(10, 2),
                  sciezki.tap(7, 1), sciezki.tap(10, 3), sciezki.MONITOR_DIMPFL, sciezki.MONITOR_DIMATT,
                  sciezki.fader(7), sciezki.fader(10), sciezki.solo(9)):
            self.assertIn(a, lista)


class TestBadanieObejmujeZapisy(unittest.TestCase):
    def test_kazdy_zapis_mostka_jest_na_liscie_badania(self):
        """Ciąg CUE, suwaków, gałek i odsłuchu na symulatorze: każdy adres zapisany
        przez mostek jest też na liście badania (badanie_mr18.py)."""
        import random
        from mostek.logika import wszystkie_adresy_odczytu
        import test_losowe
        t = test_losowe.TestLosoweCiagi("test_losowe_ciagi_nie_lamia_niezmiennikow")
        t.setUp()
        try:
            los = random.Random(7)
            for _ in range(200):
                t.wykonaj(t.losuj_krok(los))
            zapisane = {d[2] for d in t.sym.dziennik if d[1] != "inny-klient"}
            lista = set(wszystkie_adresy_odczytu(t.u))
        finally:
            t.tearDown()
        self.assertTrue(zapisane, "ciąg coś zapisał")
        self.assertEqual(sorted(zapisane - lista), [])


