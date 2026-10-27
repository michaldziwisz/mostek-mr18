"""Sygnały talkbacku po potwierdzeniu, nigdy zamiast nich NVDA."""

import array
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from pomoc import KATALOG, TestZSymulatorem, sciezki
from mostek.informacja import Tryb


class TestSygnalyTalkbacku(TestZSymulatorem):
    def przygotuj(self, antena=False):
        self.klawisz("F1_mikrofon" if antena else "glosniki_wylacz")
        self.slowa()

    def wcisnij(self, pasek=2):
        self.nacisnij("przycisk", pasek, 2)

    def pusc(self, pasek=2):
        self.nacisnij("puszczenie", pasek, 2)

    def test_start_drugi_przycisk_i_puszczenia_bez_mowy_w_kazdym_trybie(self):
        self.przygotuj(antena=True)
        for tryb in Tryb:
            for pierwszy, drugi in ((2, 3), (3, 2)):
                with self.subTest(tryb=tryb, pierwszy=pierwszy):
                    self.info.tryb = tryb
                    for p in (pierwszy, drugi):
                        self.wcisnij(p)
                        self.assertEqual(self.dzwieki_i_slowa(), (["talkback_start"], []))
                    for p in (pierwszy, drugi):
                        self.pusc(p)
                        self.assertEqual(self.dzwieki_i_slowa(), (["talkback_koniec"], []))
                    self.assertTrue(self.suma("mikrofon"))

    def test_sygnal_dopiero_po_obu_odczytach_otwarcia_i_powrotu(self):
        self.przygotuj(antena=True)
        odczytaj = self.r._dwa_odczyty
        def kontrola(cel):
            wynik = odczytaj(cel)
            self.assertEqual(self.dzwieki_i_slowa(), ([], []), "sygnał przed końcem potwierdzenia")
            return wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=kontrola) as odczyt:
            self.wcisnij()
            self.assertGreaterEqual(odczyt.call_count, 2)
        self.assertEqual(self.dzwieki_i_slowa(), (["talkback_start"], []))
        with patch.object(self.r, "_dwa_odczyty", side_effect=kontrola):
            self.pusc()
        self.assertEqual(self.dzwieki_i_slowa(), (["talkback_koniec"], []))

    def test_odmowa_bez_startu_krotszy_komunikat(self):
        self.przygotuj()
        del self.u.poziomy["wysylki"]["mikrofon"]["telefon"]
        self.wcisnij()
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Talkback niedostępny, brak poziomu wysyłki"]))

    def test_niepotwierdzone_zamkniecie_bez_startu(self):
        self.przygotuj(antena=True)
        self.sym.awarie.ignoruj_zapis.add(sciezki.lr(9))
        self.wcisnij()
        d, s = self.dzwieki_i_slowa()
        self.assertNotIn("talkback_start", d)
        self.assertNotIn("talkback_koniec", d)
        self.assertTrue(s)

    def test_fizyczne_otwarcie_bez_ostatniego_potwierdzenia_nie_daje_startu(self):
        self.przygotuj()
        odczytaj = self.r._dwa_odczyty
        a = sciezki.wysylka(9, 1)
        def brak(cel):
            wynik = odczytaj(cel)
            return [a] if cel.get(a, 0) > 0 else wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=brak):
            self.wcisnij()
        d, s = self.dzwieki_i_slowa()
        self.assertNotIn("talkback_start", d)
        self.assertTrue(s)

    def test_niepotwierdzony_powrot_bez_dzwieku_konca(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.slowa()
        self.sym.awarie.ignoruj_zapis.add(sciezki.lr(9))
        self.pusc()
        d, s = self.dzwieki_i_slowa()
        self.assertNotIn("talkback_koniec", d)
        self.assertTrue(s)

    def test_kaszel_bez_dzwiekow_takze_w_trakcie_talkbacku(self):
        self.przygotuj(antena=True)
        for tryb in Tryb:
            self.info.tryb = tryb
            for talkback in (False, True):
                if talkback:
                    self.wcisnij()
                    self.slowa()
                self.wcisnij(1)
                self.assertEqual(self.dzwieki_i_slowa(), ([], []))
                self.pusc(1)
                self.assertEqual(self.dzwieki_i_slowa(), ([], []))
                if talkback:
                    self.pusc()
                    self.slowa()

    def test_wcisniecie_podczas_kaszlu_nie_obiecuje_slyszalnosci(self):
        self.przygotuj(antena=True)
        self.wcisnij(1)
        self.wcisnij()
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))
        self.assertFalse(self.slyszalny(9, 1))
        self.pusc(1)
        self.assertEqual(self.dzwieki_i_slowa(), ([], []), "puszczenie kaszlu również bez dźwięku")
        self.assertTrue(self.slyszalny(9, 1))

    def test_powtorzone_wcisniecie_i_obce_puszczenie_bez_sygnalu(self):
        self.przygotuj()
        self.wcisnij()
        self.slowa()
        self.wcisnij()
        self.pusc(3)
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_status_na_zadanie_i_przerwanie_nadal_mowa(self):
        self.przygotuj()
        for tryb in Tryb:
            self.info.tryb = tryb
            self.wcisnij()
            self.slowa()
            self.klawisz("F2_status")
            self.assertIn("Mikrofon do telefonu na czas talkbacku", self.slowa()[0])
            self.nacisnij("galka_wcisnij", 1)
            self.assertIn("Mikrofon do telefonu na czas talkbacku", self.slowa()[0])
            self.r.utrata_kontrolera("próba")
            d, s = self.dzwieki_i_slowa()
            self.assertTrue(any("Talkback przerwany" in t for t in s))
            self.assertNotIn("talkback_koniec", d)
            self.r.powrot_kontrolera()
            self.slowa()

    def test_brak_pliku_lub_mapowania_to_cisza_i_dziennik(self):
        self.przygotuj()
        for tryb in Tryb:
            for brak_mapy in (False, True):
                with self.subTest(tryb=tryb, brak_mapy=brak_mapy):
                    self.info.tryb = tryb
                    self.info._ostrzezone.clear()
                    with patch.dict(self.info.dzwieki, {}, clear=True) if not brak_mapy else patch.dict(self.info.mapa, {}, clear=True):
                        with self.assertLogs("mostek.informacja", "WARNING"):
                            self.wcisnij()
                            self.pusc()
                            self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_awaria_odtwarzania_to_cisza_i_dziennik_naraz_i_sekwencyjnie(self):
        self.przygotuj()
        for tryb in Tryb:
            for naraz in (False, True):
                with self.subTest(tryb=tryb, naraz=naraz):
                    self.info.tryb, self.info.naraz = tryb, naraz
                    self.info._ostrzezone.clear()
                    self.dzwieki.awaria = True
                    with self.assertLogs("mostek.informacja", "WARNING"):
                        self.wcisnij()
                        self.pusc()
                        self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_awaria_kolejnego_adresata_bez_drugiego_startu(self):
        self.przygotuj()
        self.wcisnij()
        self.slowa()
        self.sym.awarie.ignoruj_zapis.update({sciezki.wysylka(9, 3), sciezki.wysylka(9, 4)})
        self.wcisnij(3)
        d, s = self.dzwieki_i_slowa()
        self.assertNotIn("talkback_start", d)
        self.assertNotIn("talkback_koniec", d)
        self.assertTrue(s)

    def test_kaszel_w_cue_bez_dzwieku_i_mowy(self):
        self.cue("telefon")
        self.cue("zoom")
        self.slowa()
        for tryb in Tryb:
            self.info.tryb = tryb
            self.wcisnij(1)
            self.assertEqual(self.dzwieki_i_slowa(), ([], []))
            self.pusc(1)
            self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_wyjatek_backendu_bez_mowy_i_bez_ponawiania_przerwanego_sygnalu(self):
        self.przygotuj()
        for naraz in (False, True):
            self.info.naraz = naraz
            metoda = "odtworz_naraz" if naraz else "odtworz"
            with patch.object(self.info, metoda, side_effect=RuntimeError("awaria backendu")):
                with self.assertLogs("mostek.mowa", "ERROR"):
                    self.wcisnij()
                    self.pusc()
                    self.assertEqual(self.dzwieki_i_slowa(), ([], []))
            self.wcisnij()
            wpis = self.mowa._pobierz()
            assert wpis is not None
            with patch.object(self.mowa, "_czekaj", return_value=True):
                self.mowa._wykonaj(wpis, czekaj=True)
            self.assertEqual(self.mowa.oczekujace(), [], "przerwane potwierdzenie nie wraca po ostrzeżeniu")
            self.assertEqual(self.slowa(), [])
            self.pusc()
            self.slowa()

    def test_brak_odtwarzacza_w_kolejce_nie_wolno_mowic(self):
        self.przygotuj()
        self.mowa.dzwieki = None
        with self.assertLogs("mostek.mowa", "WARNING"):
            self.wcisnij()
            self.pusc()
            self.assertEqual(self.slowa(), [])


class TestPlikiTalkbacku(unittest.TestCase):
    def test_format_czas_szczyt_roznica_i_powtarzalny_generator(self):
        skrypt = KATALOG / "narzedzia/generuj_talkback.py"
        spec = importlib.util.spec_from_file_location("generuj_talkback", skrypt)
        assert spec is not None and spec.loader is not None
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        opis = json.loads((KATALOG / "dzwieki/dzwieki.json").read_text())
        pozostale = {p.read_bytes() for p in (KATALOG / "dzwieki").glob("*.wav") if not p.stem.startswith("talkback_")}
        with tempfile.TemporaryDirectory() as d:
            gen.generuj(Path(d))
            for nazwa, kierunek in (("talkback_start", 1), ("talkback_koniec", -1)):
                p = KATALOG / "dzwieki" / (nazwa + ".wav")
                self.assertEqual(p.read_bytes(), (Path(d) / p.name).read_bytes())
                self.assertNotIn(p.read_bytes(), pozostale)
                with wave.open(str(p)) as w:
                    self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth()), (48000, 1, 2))
                    self.assertEqual(w.getcomptype(), "NONE")
                    czas = w.getnframes() / w.getframerate()
                    self.assertEqual(czas, opis[nazwa]["czas_s"])
                    self.assertLessEqual(czas, 0.2)
                    a = array.array("h", w.readframes(w.getnframes()))
                self.assertEqual(max(map(abs, a)), 7616)
                self.assertEqual((a[0], a[-1]), (0, 0))
                # Niezależny od generatora kierunek tonu: przejścia przez zero.
                def przejscia(fragment):
                    return sum(x <= 0 < y for x, y in zip(fragment, fragment[1:]))
                pierwszy = przejscia(a[:3360])
                drugi = przejscia(a[4320:7680])
                self.assertGreater((drugi - pierwszy) * kierunek, 0)
