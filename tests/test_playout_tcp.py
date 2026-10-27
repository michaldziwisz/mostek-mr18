"""Regresje playoutu: prawdziwe TCP, granica MR18, mapa MC i limity czasu."""
import threading
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

from mostek import emisja
from mostek.glowny import polecenie_konsoli
from mostek.informacja import Tryb
from mostek.xtouch import MapaMC
from tests.atrapa_playoutu import SerwerPlayoutu, zamkniety_port
from tests.pomoc import TestZSymulatorem, wczytaj_ustawienia


class TestTCP(unittest.TestCase):
    def serwer(self, sara=False):
        s = SerwerPlayoutu(sara)
        self.addCleanup(s.zamknij)
        return s

    def test_metadata_zaczynajace_sie_od_err_to_nie_blad(self):
        s = self.serwer()
        s.this, s.next, s.gra = "ERRA - Snowblood", "ERR unknown", True
        w = emisja.StationPlaylistTCP(s.port).wykonaj("co_gra")
        self.assertEqual((w.teraz,w.nastepny), ("ERRA - Snowblood", "ERR unknown"))
        s.ack = "ERR rejected"
        with self.assertRaises(emisja.BladEmisji):
            emisja.StationPlaylistTCP(s.port).wykonaj("play")

    def test_spl_play_stop_stat_7_bitow_i_f6(self):
        s = self.serwer()
        a = emisja.StationPlaylistTCP(s.port)
        self.assertEqual(a.wykonaj("play").stan, "gra")
        w = a.wykonaj("co_gra")
        self.assertEqual((w.teraz, w.pozostalo_ms, w.nastepny), ("Artysta - Tytuł", 135000, "Inny - Następny"))
        self.assertEqual(a.wykonaj("stop").stan, "stop")
        self.assertEqual(a.wykonaj("instant").stan, "stop")
        self.assertIn("Play", s.polecenia)
        self.assertNotIn("Skip", s.polecenia)

    def test_spl_bez_ack_i_z_ack(self):
        for ack in (None, "", "OK", "1"):
            with self.subTest(ack=ack):
                s = self.serwer()
                s.ack = ack
                a = emisja.StationPlaylistTCP(s.port)
                self.assertEqual(a.wykonaj("play").stan, "gra")
                self.assertEqual(a.wykonaj("ruch", 1).utwor.indeks, 2)

    def test_spl_hour_marker_csv_i_nieznany_checkbox(self):
        s = self.serwer()
        a = emisja.StationPlaylistTCP(s.port)
        u = a.wykonaj("ruch", -1).utwor
        self.assertEqual((u.indeks, u.artysta, u.tytul), (0, "", "0200 (2am 24.10.2026)"))
        u = a.wykonaj("ruch", 1).utwor
        self.assertEqual((u.indeks, u.artysta, u.czas), (1, "Artysta, Zespół", "3:45"))
        self.assertIsNone(u.zaznaczony)
        w = a.wykonaj("znacznik")
        self.assertTrue(w.znacznik_przelaczony)
        self.assertIsNone(w.utwor.zaznaczony)
        self.assertFalse(any(p.startswith("TrackInfoEx") for p in s.polecenia))

    def test_sara_trackinfoex_checkbox_i_status(self):
        s = self.serwer(True)
        a = emisja.SARA(s.port)
        u = a.wykonaj("utwor").utwor
        self.assertEqual((u.indeks, u.artysta, u.czas, u.zaznaczony), (0, "Żółć", "3:45", True))
        self.assertFalse(a.wykonaj("znacznik").utwor.zaznaczony)
        self.assertTrue(a.wykonaj("znacznik").utwor.zaznaczony)
        s.statusy[0] = "played"
        self.assertEqual(a.wykonaj("utwor").utwor.status, "played")
        self.assertIn("TrackInfoEx=0-0", s.polecenia)
        self.assertFalse(any(p.startswith("TrackInfo=") for p in s.polecenia))

    def test_automat_z_odczytu_nie_z_lokalnego_przelacznika(self):
        for sara in (False, True):
            s = self.serwer(sara)
            a = emisja.SARA(s.port) if sara else emisja.StationPlaylistTCP(s.port)
            self.assertTrue(a.wykonaj("automat").automat)
            s.auto = False  # obcy klient
            self.assertTrue(a.wykonaj("automat").automat)
            self.assertFalse(a.wykonaj("automat").automat)

    def test_skip_odrebny_od_play(self):
        s = self.serwer()
        a = emisja.StationPlaylistTCP(s.port)
        a.wykonaj("play")
        w = a.wykonaj("nastepny")
        self.assertEqual((w.stan, w.teraz), ("gra", "Drugi - Kolejny"))
        self.assertEqual(s.polecenia.count("Skip"), 1)

    def test_stat_zly_lub_sprzeczny_nie_potwierdza_grania(self):
        s = self.serwer(True)
        a = emisja.SARA(s.port)
        for stat in ("100000", "100x000", "", "OK", "1" * 17):
            s.odpowiedzi["stat"] = stat
            with self.assertRaises(emisja.BladEmisji):
                a.wykonaj("play")
        # Prawdziwy SPL Studio 6.20 (pomiar 24.10.2026) odpowiada na Stat
        # ośmioma cyframi „00000010”, choć pomoc opisuje siedem.
        s.odpowiedzi["stat"] = "10000010"
        self.assertEqual(a.wykonaj("stan").stan, "gra")
        s.odpowiedzi["stat"] = "0000000"
        s.statusy[0] = "playing"
        w = a.wykonaj("utwor")
        self.assertEqual(w.stan, "stop")
        self.assertNotEqual(w.utwor.status, "playing")
        s.odpowiedzi["stat"] = "1000100"
        self.assertEqual(a.wykonaj("stan").stan, "pauza")

    def test_pusta_playlista(self):
        s = self.serwer(True)
        s.indeks = -1
        a = emisja.SARA(s.port)
        self.assertIsNone(a.wykonaj("znacznik").utwor)
        self.assertNotIn("CheckToggle", s.polecenia)

    def test_filtr_polecen_nic_nie_wychodzi_do_spl(self):
        s = self.serwer()
        sesja = emisja.StationPlaylistTCP(s.port).polacz()
        self.addCleanup(sesja.zamknij)
        before = list(s.polecenia)
        for zle in ("TrackInfoEx=0-0", "Skrypt", "Run notepad", "Play\nSkrypt", "Play,Stop", "SelectIndex=1\rSkrypt",
                    "SelectIndex=-1", "TrackInfo=1-0", "TrackInfo=all", "Helo ", "", "SelectIndex=+\n"):
            with self.subTest(p=zle), self.assertRaises(ValueError):
                sesja.wyslij(zle)
        # Bariera na tym samym strumieniu dowodzi, że nie ukryto wysłanych bajtów.
        self.assertEqual(sesja.pytaj("Helo"), s.helo)
        self.assertEqual(s.polecenia, before + ["Helo"])

    def test_trackinfoex_dopiero_po_helo_sary_nawet_na_porcie_sary(self):
        s = self.serwer()
        with self.assertRaises(emisja.BladEmisji):
            emisja.SARA(s.port).wykonaj("utwor")
        self.assertEqual(s.polecenia, ["Helo"])

    def test_limit_odpowiedzi_i_ponowne_polaczenie(self):
        s = self.serwer()
        s.opoznienie["stat"] = 0.35
        a = emisja.StationPlaylistTCP(s.port, limit_s=0.05)
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            a.wykonaj("stan")
        self.assertLess(time.monotonic() - start, 0.25)
        s.opoznienie.clear()
        self.assertEqual(a.wykonaj("stan").stan, "stop")
        self.assertEqual(s.polecenia.count("Helo"), 2)

    def test_cisza_i_zerwane_polaczenie(self):
        s = self.serwer()
        a = emisja.StationPlaylistTCP(s.port, limit_s=0.05)
        s.milcz.add("helo")
        with self.assertRaises(TimeoutError):
            a.wykonaj("play")
        s.milcz.clear()
        s.zerwij.add("stat")
        with self.assertRaises(emisja.BladEmisji):
            a.wykonaj("stan")
        s.zerwij.clear()
        self.assertEqual(a.wykonaj("stan").stan, "stop")
        self.assertNotIn("Play", s.polecenia)

    def test_fragmentacja_i_limit_calej_linii(self):
        s = self.serwer(True)
        s.fragmentuj = True
        a = emisja.SARA(s.port, limit_s=0.08)
        self.assertEqual(a.wykonaj("utwor").utwor.artysta, "Żółć")
        s.podawaj_bajty_s = 0.02
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            a.wykonaj("stan")
        self.assertLess(time.monotonic() - start, 0.25)

    def test_ograniczenie_rozmiaru_i_bledne_dane(self):
        s = self.serwer(True)
        a = emisja.SARA(s.port)
        for p, val in (("helo", "x" * 70000), ("trackinfoex=0-0", "0|2|pending|A|B|1000|0"),
                       ("selectindex", "1.2"), ("rem", "nie wiem")):
            s.odpowiedzi[p] = val
            with self.subTest(p=p), self.assertRaises(emisja.BladEmisji):
                a.wykonaj("co_gra" if p == "rem" else "utwor")
            s.odpowiedzi.clear()

    def test_spl_kodowanie_jawne(self):
        s = self.serwer()
        s.kodowanie = "cp1250"
        a = emisja.StationPlaylistTCP(s.port, kodowanie="cp1250")
        self.assertEqual(a.wykonaj("utwor").utwor.artysta, "Artysta, Zespół")

    def test_auto_wybor_preferencja_i_zmiana_dostepnosci(self):
        spl, sara = self.serwer(), self.serwer(True)
        u = {"spl_port": spl.port, "sara_port": sara.port, "limit_odpowiedzi_s": 0.05}
        a = emisja.WyborProgramu("auto", u)
        a.wykonaj("play")
        self.assertEqual(a.nazwa, "StationPlaylist")
        self.assertEqual(sara.polecenia, [])
        a = emisja.WyborProgramu("auto", dict(u, preferowany="SARA"))
        a.wykonaj("play")
        self.assertEqual(a.nazwa, "SARA")
        sara.zerwij.add("helo")
        a.wykonaj("play")
        self.assertEqual(a.nazwa, "StationPlaylist")
        spl.zerwij.add("helo")
        with self.assertRaises(emisja.BrakProgramu):
            a.wykonaj("play")
        sara.zerwij.clear()
        a.wykonaj("play")
        self.assertEqual(a.nazwa, "SARA")

    def test_sendmessage_zapas_i_ograniczenie_funkcji(self):
        calls = []
        def api(w, l):
            calls.append((w, l))
            return 1
        port = zamkniety_port()
        a = emisja.WyborProgramu("StationPlaylist", {"spl_port": port}, emisja.StationPlaylist(api))
        for akcja in ("play", "stop", "instant", "stan"):
            self.assertEqual(a.wykonaj(akcja).stan, "gra")
        self.assertIn((0, 12), calls)
        self.assertIn((0, 13), calls)
        self.assertIn((1, 13), calls)
        for akcja in ("co_gra", "ruch", "znacznik", "automat", "nastepny"):
            with self.assertRaises(emisja.WymagaTCP):
                a.wykonaj(akcja, 1)
        self.assertNotIn((0, 14), calls)
        b = emisja.WyborProgramu("SARA", {"sara_port": port}, emisja.StationPlaylist(api))
        with self.assertRaises(emisja.BrakProgramu):
            b.wykonaj("play")

    def test_po_wyslaniu_nie_powtarza_akcji_zapasem_ani_w_sarze(self):
        spl, sara = self.serwer(), self.serwer(True)
        spl.zerwij.add("stat")
        calls = []
        a = emisja.WyborProgramu("auto", {"spl_port": spl.port, "sara_port": sara.port},
                                emisja.StationPlaylist(lambda w, l: calls.append((w, l)) or 1))
        with self.assertRaises(emisja.BladEmisji):
            a.wykonaj("play")
        self.assertEqual(spl.polecenia.count("Play"), 1)
        self.assertEqual(calls, [])
        self.assertEqual(sara.polecenia, [])

    def test_wszystkie_akcje_spl_maja_tylko_udokumentowane_polecenia(self):
        import re
        s = self.serwer()
        a = emisja.StationPlaylistTCP(s.port)
        for akcja,kierunek in (("play",0),("nastepny",0),("co_gra",0),("automat",0),("ruch",1),
                              ("ruch",-1),("znacznik",0),("utwor",0),("stop",0),("instant",0),("stan",0)):
            a.wykonaj(akcja,kierunek)
        wzor = re.compile(r"Helo|Stat|This|Next|Rem|Play|Skip|Stop|Instant Stop|Auto|SelectIndex(?:=[+-])?|CurrIndex|CheckToggle|TrackInfo=[0-9]+-[0-9]+")
        self.assertTrue(s.polecenia)
        for p in s.polecenia:
            self.assertIsNotNone(wzor.fullmatch(p), p)

    def test_fabryka_ustawienia_i_brak_polaczenia_przy_starcie(self):
        with patch("socket.create_connection") as connect:
            a = emisja.utworz()
            self.assertEqual(a.program, "auto")
            b = emisja.utworz(None, {"program": "SARA", "sara_port": 12345})
            self.assertEqual(b.adaptery[0].port, 12345)
            connect.assert_not_called()


class TestStolPlayout(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.s = SerwerPlayoutu(True)
        self.addCleanup(self.s.zamknij)
        self.r.emisja = emisja.SARA(self.s.port, limit_s=0.1)
        self.mapa = MapaMC(self.u.xtouch)

    def midi(self, nuta):
        self.zegar.przesun(0.2)
        self.r.zglos(self.mapa.zdarzenie([0x90, nuta, 127]))

    def test_kazdy_klawisz_transportu_f6_f7_kursora(self):
        oczekiwane = {91:"nauka_klawiszy", 92:"ffwd_wolny", 93:"transport_stop", 94:"transport_play",
                      95:"transport_nastepny", 59:"F6_co_gra", 60:"F7_automat", 96:"emisja_gora",
                      97:"emisja_dol", 98:"kursor_lewo_wolny", 99:"kursor_prawo_wolny",
                      100:"emisja_znacznik", 101:"scrub_wolny"}
        for nuta, nazwa in oczekiwane.items():
            self.assertEqual(self.mapa.zdarzenie([0x90,nuta,127]), ("klawisz",nazwa))
            self.assertIsNone(self.mapa.zdarzenie([0x90,nuta,0]))
            self.assertIsNone(self.mapa.zdarzenie([0x80,nuta,127]))
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        for nuta in (92,98,99):
            self.midi(nuta)
            self.assertEqual(self.slowa(), ["Klawisz wolny"])
        self.assertEqual(self.s.polecenia, [])
        self.midi(94); self.assertEqual(self.slowa(), ["Gra"])
        self.midi(95); self.assertEqual(self.slowa(), ["Gra: Drugi, Kolejny"])
        self.midi(59); self.assertEqual(self.slowa(), ["Gra: Drugi, Kolejny, zostało 2 minuty 15 sekund. Następny: Inny, Następny"])
        self.midi(60); self.assertEqual(self.slowa(), ["Automat włączony"])
        self.midi(60); self.assertEqual(self.slowa(), ["Automat wyłączony"])
        self.midi(97); self.assertIn("Utwór 2", self.slowa()[0])
        self.midi(96); self.assertIn("Utwór 1", self.slowa()[0])
        self.midi(100); self.assertIn("niezaznaczono", self.slowa()[0])
        self.midi(93); self.assertEqual(self.slowa(), ["Zatrzymane"])
        self.midi(93); self.slowa()
        self.assertIn("Instant Stop", self.s.polecenia)
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania)

    def test_nastepny_jak_play_zeruje_okno_drugiego_stop(self):
        self.midi(93); self.slowa()
        self.midi(95); self.slowa()
        self.midi(93); self.slowa()
        self.assertEqual(self.s.polecenia.count("Stop"), 2)
        self.assertNotIn("Instant Stop", self.s.polecenia)

    def test_stop_po_oknie_znow_wycisza(self):
        self.midi(93); self.slowa()
        self.zegar.przesun(2)
        self.midi(93); self.slowa()
        self.assertEqual(self.s.polecenia.count("Stop"), 2)
        self.assertNotIn("Instant Stop", self.s.polecenia)

    def test_konsola_odpowiednik_klawiszy(self):
        for cmd,nuta in {"play":94,"stop":93,"nastepny":95,"coGra":59,"f6":59,"automat":60,"f7":60,
                         "gora":96,"dol":97,"znacznik":100}.items():
            self.assertEqual(polecenie_konsoli(cmd), self.mapa.zdarzenie([0x90,nuta,127]))

    def test_jog_kazdy_zabek_jeden_krok_i_jeden_komunikat_po_ciszy(self):
        self.assertIsNone(self.mapa.zdarzenie([0xB0,60,0]))
        self.assertIsNone(self.mapa.zdarzenie([0xB0,60,64]))
        for v in (3, 0x41):
            for z in self.mapa.zdarzenie([0xB0,60,v]):
                self.r.zglos(z)
        self.assertTrue(self.s.czekaj_na("SelectIndex=-"))
        time.sleep(0.1)
        self.r.odbierz_emisje()
        self.mowa.oproznij()
        self.assertEqual(self.wyjscie.powiedziane, [])
        self.assertEqual(self.s.polecenia.count("SelectIndex=+"), 3)
        self.assertEqual(self.s.polecenia.count("SelectIndex=-"), 1)
        slowa = self.slowa()
        self.assertEqual(len(slowa), 1)
        self.assertIn("Utwór 2", slowa[0])

    def test_zawieszony_program_nie_blokuje_rdzenia_ani_przycisku_mikrofonu(self):
        self.s.milcz.add("helo")
        start = time.monotonic()
        # Nawet trwający odczyt MR18 nie może trzymać zlecenia playoutu.
        with self.r._wykonuje:
            self.midi(94)
        self.assertLess(time.monotonic() - start, 0.05)
        self.assertTrue(self.s.czekaj_na("Helo"))
        start = time.monotonic()
        self.klawisz("F1_mikrofon")
        self.assertLess(time.monotonic() - start, 0.1)
        self.assertTrue(self.suma("mikrofon"))
        slowa = self.slowa()
        self.assertNotIn("Gra", slowa)

    def test_emisja_przy_nieznanym_stanie_miksera_bez_odczytu(self):
        self.r.stan.polaczony = False
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        self.zegar.przesun(10)
        self.midi(94)
        self.assertEqual(self.slowa(), ["Gra"])
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania)

    def test_brak_programu_jeden_komunikat_i_powrot(self):
        port = zamkniety_port()
        self.r.emisja = emisja.WyborProgramu("auto", {"spl_port":port,"sara_port":port})
        self.midi(94); self.assertEqual(self.slowa(), ["Nie odpowiada żaden program emisyjny"])
        for nuta in (59,97,60,100,95):
            self.midi(nuta); self.assertEqual(self.slowa(), [])
        self.r.emisja = emisja.SARA(self.s.port)
        self.midi(94); self.assertEqual(self.slowa(), ["Gra"])

    def test_nie_mowi_gra_bez_stat_rowniez_po_skip_i_dla_kursora(self):
        self.s.odpowiedzi["stat"] = "0000000"
        self.s.statusy[0] = "playing"
        self.midi(94); self.assertEqual(self.slowa(), ["Zatrzymane"])
        self.midi(95); self.assertEqual(self.slowa(), ["Nic nie gra"])
        self.midi(59); self.assertTrue(self.slowa()[0].startswith("Nic nie gra"))
        self.midi(100); self.assertNotIn(", gra", self.slowa()[0])

    def test_tryby_f4_i_f5_z_nowym_komunikatem(self):
        for tryb in Tryb:
            self.info.tryb = tryb
            self.midi(94); self.slowa()
            self.midi(59)
            d, slowa = self.dzwieki_i_slowa()
            self.assertEqual(d, [])
            self.assertIn("zostało 2 minuty 15 sekund", slowa[0])
            self.klawisz("F5_ostatni_komunikat")
            self.assertEqual(self.slowa(), slowa)

    def test_spl_znacznik_bez_zgadywania_stanu(self):
        with SerwerPlayoutu() as s:
            self.r.emisja = emisja.StationPlaylistTCP(s.port)
            self.midi(100)
            tekst = self.slowa()[0]
            self.assertIn("znacznik przełączony", tekst)
            self.assertNotIn("zaznaczono", tekst)

    def test_stop_nie_wygasa_za_powolnym_odczytem(self):
        for akcja in ("stop", "instant"):
            self.s.opoznienie["stat"] = 0.04
            ile = self.s.polecenia.count("Stat")
            self.r._tor_emisji.zlec("co_gra")
            self.assertTrue(self.s.czekaj_na("Stat", ile=ile + 1))
            # Trwający odczyt: kontrolowany wiek wpisu kolejki > 2 s.
            self.r._tor_emisji.zlec(akcja)
            with self.r._tor_emisji._warunek:
                a,k,j,t = self.r._tor_emisji._kolejka[-1]
                self.r._tor_emisji._kolejka[-1] = (a,k,j,t - 3)
            self.slowa()
            self.assertIn("Instant Stop" if akcja == "instant" else "Stop", self.s.polecenia)

    def test_blad_nie_ucisza_kolejnych_nacisniec_na_zawsze(self):
        self.r.emisja = None
        self.midi(94); self.assertEqual(self.slowa(), ["Nie wybrano programu emisyjnego"])
        self.r._tor_emisji._blad_czas -= 6
        self.midi(93); self.assertEqual(self.slowa(), ["Nie wybrano programu emisyjnego"])

    def test_stop_kasuje_zalegla_nawigacje_i_automat(self):
        self.s.opoznienie["stat"] = 0.04
        self.midi(94)
        self.assertTrue(self.s.czekaj_na("Stat"))
        for nuta in (60,97,100,95):
            self.midi(nuta)
        self.midi(93)
        self.assertEqual(self.slowa(), ["Zatrzymane"])
        for p in ("Auto", "SelectIndex=+", "CheckToggle", "Skip"):
            self.assertNotIn(p, self.s.polecenia)

    def test_stare_polecenia_nie_wykonuja_sie_po_czasie(self):
        self.s.opoznienie["stat"] = 0.04
        self.midi(94)
        self.assertTrue(self.s.czekaj_na("Stat"))
        self.midi(60)
        with self.r._tor_emisji._warunek:
            akcja, kierunek, jog, zlecono = self.r._tor_emisji._kolejka[-1]
            self.r._tor_emisji._kolejka[-1] = (akcja, kierunek, jog, zlecono - 3)
        self.assertEqual(self.slowa(), ["Polecenie emisji pominięte, było zbyt długo w kolejce"])
        self.assertNotIn("Auto", self.s.polecenia)

    def test_jog_bez_programu_jeden_blad_bez_odlozonego_odczytu(self):
        port = zamkniety_port()
        self.r.emisja = emisja.WyborProgramu("auto", {"spl_port":port,"sara_port":port})
        for _ in range(6):
            self.r.zglos(("jog", 1))
        self.assertEqual(self.slowa(), ["Nie odpowiada żaden program emisyjny"])
        self.assertIsNone(self.r._tor_emisji._jog_termin)
        self.assertEqual(self.slowa(), [])

    def test_jog_koncowy_opis_nie_zmienia_wybranego_programu(self):
        with SerwerPlayoutu() as spl:
            spl.zerwij.add("helo")
            self.r.emisja = emisja.WyborProgramu("auto", {"spl_port":spl.port,"sara_port":self.s.port})
            self.r.zglos(("jog", 1))
            self.assertTrue(self.s.czekaj_na("SelectIndex=+"))
            spl.zerwij.clear()  # preferowany SPL pojawił się podczas zwłoki jog
            self.assertIn("Utwór 1", self.slowa()[0])
            self.assertEqual(spl.polecenia, ["Helo"])
            self.assertIn("TrackInfoEx=1-1", self.s.polecenia)

    def test_zamkniecie_nie_wykonuje_zaleglych_polecen(self):
        self.s.milcz.add("helo")
        self.midi(94)
        self.assertTrue(self.s.czekaj_na("Helo"))
        self.midi(60)
        self.r.zamknij_emisje()
        self.assertNotIn("Auto", self.s.polecenia)
        self.assertFalse(self.r._tor_emisji._watek.is_alive())


class TestProtokolHold(unittest.TestCase):
    def test_biala_lista_i_spl_nigdy_nie_dostaje_hold(self):
        for p in ("Hold", "Hold=0", "Hold=1"):
            self.assertFalse(emisja.dozwolone_polecenie(p))
            self.assertTrue(emisja.dozwolone_polecenie(p, sara=True))
        for p in ("Hold=2", "Hold=-1", "Hold=true", "Hold=1\nPlay", "Hold=1,Play"):
            self.assertFalse(emisja.dozwolone_polecenie(p, sara=True))

    def test_sesja_spl_nigdy_hold(self):
        with SerwerPlayoutu() as spl:
            s = emisja.SesjaTCP(spl.port)
            try:
                for akcja in ("hold", "hold_odczyt"):
                    try:
                        s.wykonaj(akcja, 1)
                    except (ValueError, emisja.BladEmisji):
                        pass
                self.assertEqual(spl.polecenia, ["Helo"])
            finally:
                s.zamknij()

    def test_auto_uzywa_juz_wybranej_sary_bez_ponownej_sondy_spl(self):
        with SerwerPlayoutu() as spl, SerwerPlayoutu(True) as sara:
            spl.milcz.add('helo')
            u = {'spl_port': spl.port, 'sara_port': sara.port, 'limit_odpowiedzi_s': 0.02}
            a = emisja.WyborProgramu('auto', u, okno_spl=lambda: True)
            a.wykonaj('play')
            self.assertEqual(a.nazwa, 'SARA')
            przed = list(spl.polecenia)
            self.assertEqual(a.wykonaj('hold', 1), emisja.Wstrzymanie(True, 'trzyma'))
            self.assertEqual(spl.polecenia, przed)
            self.assertIn('Hold=1', sara.polecenia)

    def test_sara_protokol_odczyt_idempotencja_i_skladnia(self):
        with SerwerPlayoutu(True) as sara:
            a = emisja.SARA(sara.port)
            self.assertEqual(a.wykonaj("hold", 1), emisja.Wstrzymanie(True, "brak"))
            sara.gra = True
            self.assertEqual(a.wykonaj("hold", 1), emisja.Wstrzymanie(True, "brak"))
            sara.skoncz_utwor()
            self.assertEqual(a.wykonaj("hold_odczyt"), emisja.Wstrzymanie(True, "zatrzymane"))
            self.assertEqual(a.wykonaj("hold", 0), emisja.Wstrzymanie(False, "zatrzymane"))
            self.assertEqual(sara.odpowiedz("Hold=2"), "ERR syntax")
            for odpowiedz in ("1", "1,blad", "2,trzyma", "1,trzyma,extra", "0,trzyma", "ERR syntax"):
                sara.odpowiedzi["hold=1"] = odpowiedz
                with self.assertRaises(emisja.BladEmisji, msg=odpowiedz):
                    a.wykonaj("hold", 1)


class TestBrzmienieZatwierdzone(unittest.TestCase):
    """Michał 24.10.2026: „zaznaczono”/„niezaznaczono” bez „do emisji”,
    przecinek zamiast myślnika między artystą a tytułem (też This/Next)."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from pomoc import wczytaj_ustawienia
        from mostek.playout import TorEmisji
        self._tmp = tempfile.TemporaryDirectory(prefix="mostek-test-")
        self.tor = TorEmisji(wczytaj_ustawienia(Path(self._tmp.name)), lambda: None)

    def tearDown(self):
        self.tor.zamknij()
        self._tmp.cleanup()

    def test_utwor_zaznaczono_i_przecinek(self):
        from mostek.emisja import Odczyt, Utwor
        u = Utwor(0, "Artysta", "Tytuł", "3:45", True, "", False, 1)
        self.assertEqual(self.tor.opisz("ruch", Odczyt("stop", False, utwor=u)), "1. Artysta, Tytuł, 3:45, zaznaczono")
        u = Utwor(0, "Artysta", "Tytuł", "3:45", False, "", False, 1)
        self.assertEqual(self.tor.opisz("znacznik", Odczyt("stop", False, utwor=u)), "1. Artysta, Tytuł, 3:45, niezaznaczono")

    def test_this_next_z_przecinkiem(self):
        from mostek.emisja import Odczyt
        w = Odczyt("gra", False, teraz="Artysta - Tytuł - wersja radiowa", nastepny="Inny - Następny", pozostalo_ms=5000)
        self.assertEqual(self.tor.opisz("co_gra", w),
                         "Gra: Artysta, Tytuł - wersja radiowa, zostało 5 sekund. Następny: Inny, Następny")
        self.assertEqual(self.tor.opisz("nastepny", Odczyt("gra", False, teraz="Sam tytuł")), "Gra: Sam tytuł")

    def test_next_spl_z_czasem_w_nawiasie(self):
        # Prawdziwy SPL 6.20 (pomiar 24.10.2026): Next = „Vincent Ingala - Making the Journey (04:41)”.
        from mostek.emisja import Odczyt
        w = Odczyt("stop", False, nastepny="Vincent Ingala - Making the Journey (04:41)")
        self.assertEqual(self.tor.opisz("co_gra", w), "Nic nie gra. Następny: Vincent Ingala, Making the Journey, 4:41")


class TestSzybkaNawigacja(TestStolPlayout):
    """Michał, 24.10.2026: szybkie chodzenie po playliście ucina poprzednią
    pozycję w NVDA zamiast ją kolejkować; gdy coś gra, sam artysta i tytuł."""

    def test_kursor_ucina_poprzedni_kursor_w_nvda_ale_nie_inne_komunikaty(self):
        from mostek.mowa import AtrapaMowy, KolejkaMowy
        a = AtrapaMowy()
        k = KolejkaMowy(a, alarm=None)
        k.powiedz("1. pierwszy", klucz="emisja-kursor"); k.oproznij()
        k.powiedz("2. drugi", klucz="emisja-kursor"); k.oproznij()
        self.assertEqual(a.przerwania, 1)
        k.powiedz("Mikrofon włączony", klucz="m"); k.oproznij()
        k.powiedz("3. trzeci", klucz="emisja-kursor"); k.oproznij()
        self.assertEqual(a.przerwania, 1)  # komunikat mikrofonu nie został ucięty
        self.assertEqual(a.powiedziane, ["1. pierwszy", "2. drugi", "Mikrofon włączony", "3. trzeci"])

    def test_seria_strzalek_mowi_tylko_ostatnia_pozycje(self):
        self.s.milcz.clear()
        self.s.opoznienie["selectindex=+"] = 0.03  # ruchy przychodzą szybciej, niż program odpowiada
        for _ in range(4):
            self.r.zglos(("klawisz", "emisja_dol"))
            self.zegar.przesun(0.2)
        slowa = self.slowa()
        self.assertEqual(self.s.polecenia.count("SelectIndex=+"), 4)
        self.assertEqual(len(slowa), 1, slowa)
        self.assertIn("Utwór 4", slowa[0])

    def test_gdy_gra_sam_artysta_i_tytul(self):
        self.midi(94); self.slowa()
        self.midi(97)
        self.assertEqual(self.slowa(), ["Żółć, Utwór 1"])
        self.midi(100)
        self.assertEqual(self.slowa(), ["Żółć, Utwór 1, niezaznaczono"])
        self.midi(93); self.slowa()
        self.midi(97)
        tekst = self.slowa()[0]
        self.assertIn("3:45", tekst)  # nic nie gra: pełny opis jak dotąd
        self.assertTrue(tekst.startswith("3. Żółć, Utwór 2"), tekst)

    def test_mozna_wylaczyc_skrot(self):
        self.u.emisja["krotko_gdy_gra"] = False
        self.midi(94); self.slowa()
        self.midi(97)
        self.assertIn("3:45", self.slowa()[0])

    def test_spl_po_zoomie_przy_graniu_znacznik_przelaczony(self):
        from mostek.emisja import Odczyt, Utwor
        u = Utwor(1, "Artysta", "Tytuł", "3:45")
        w = Odczyt("gra", False, utwor=u, znacznik_przelaczony=True)
        self.assertEqual(self.r._tor_emisji.opisz("znacznik", w), "Artysta, Tytuł, znacznik przełączony")
        self.assertEqual(self.r._tor_emisji.opisz("ruch", replace(w, znacznik_przelaczony=False)), "Artysta, Tytuł")

    def test_tor_nie_oddaje_posrednich_pozycji_gdy_czeka_kolejny_ruch(self):
        from mostek.emisja import Odczyt, Utwor
        from mostek.playout import TorEmisji

        class Wolny:
            n = 0
            def wykonaj(self, akcja, kierunek=0):
                time.sleep(0.05)
                Wolny.n += 1
                return Odczyt("stop", False, utwor=Utwor(Wolny.n, "A", f"T{Wolny.n}", "1:00"))

        tor = TorEmisji(self.u, lambda: Wolny())
        self.addCleanup(tor.zamknij)
        for _ in range(4):
            tor.zlec("ruch", 1)
        self.assertTrue(tor.czekaj())
        wyniki = []
        while not tor.wyniki.empty():
            wyniki.append(tor.wyniki.get_nowait())
        self.assertEqual(Wolny.n, 4)          # każdy ruch dotarł do programu
        self.assertEqual(len(wyniki), 1, wyniki)
        self.assertIn("T4", wyniki[0][0])
        self.assertEqual(wyniki[0][2], "emisja-kursor")


class TestResponsywnosc(unittest.TestCase):
    """Michał, 24.10.2026: klawisze emisji z „bezwładnością”. Pomiar na stanowisku:
    przy zamkniętym SPL port 443 milczał do końca limitu, więc każde polecenie
    do SARY czekało ~515 ms; samo SARA odpowiadało w 1 ms."""

    def test_bez_okna_spl_nie_pyta_spl_i_nie_czeka(self):
        with SerwerPlayoutu() as spl, SerwerPlayoutu(True) as sara:
            spl.opoznienie["helo"] = 0.4      # jak milczący port: odpowiedź po limicie
            u = {"spl_port": spl.port, "sara_port": sara.port, "limit_odpowiedzi_s": 0.3}
            a = emisja.WyborProgramu("auto", u, emisja.StationPlaylist(lambda w, l: None), okno_spl=lambda: False)
            t = time.monotonic()
            a.wykonaj("play")
            self.assertLess(time.monotonic() - t, 0.15)
            self.assertEqual(a.nazwa, "SARA")
            self.assertEqual(spl.polecenia, [])

    def test_z_oknem_spl_albo_bez_wiedzy_pyta_jak_dotad(self):
        for okno in (lambda: True, lambda: None):
            with SerwerPlayoutu() as spl, SerwerPlayoutu(True) as sara:
                u = {"spl_port": spl.port, "sara_port": sara.port}
                a = emisja.WyborProgramu("auto", u, emisja.StationPlaylist(lambda w, l: None), okno_spl=okno)
                a.wykonaj("play")
                self.assertEqual(a.nazwa, "StationPlaylist")

    def test_wynik_trafia_do_mowy_od_razu_bez_czekania_na_tick(self):
        from mostek.playout import TorEmisji
        from mostek.emisja import Odczyt

        class Szybki:
            def wykonaj(self, akcja, kierunek=0):
                return Odczyt("gra", False)

        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        oddane = threading.Event()
        tor = TorEmisji(wczytaj_ustawienia(Path(tmp.name)), lambda: Szybki())
        self.addCleanup(tor.zamknij)
        tor.przy_wyniku = oddane.set
        tor.zlec("play")
        self.assertTrue(oddane.wait(0.5))
        self.assertFalse(tor.wyniki.empty())
