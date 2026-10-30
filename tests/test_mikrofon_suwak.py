"""Fader Start mikrofonu: surowy dziennik DSP, ruch ręki i stare ustawienia."""
import hashlib
from pathlib import Path
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki, poziom_db_na_float
from mostek import ustawienia
from mostek.informacja import Tryb
from mostek.logika import Widok
from mostek.stan import NIEZNANY

FADER = sciezki.fader(9)
MAIN = sciezki.lr(9)
BUSY = (1, 3, 4)


class TestMikrofonSuwak(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.ustaw_mikser({FADER: 0.0, MAIN: 0})
        self.r.synchronizuj()
        self.slowa()

    def oba_cue(self):
        self.cue("telefon")
        self.cue("zoom")
        self.slowa()

    def sprawdz_kolejnosc(self, przed, od):
        stan = dict(przed)
        for a, v in self.zapisy(od):
            stan[a] = v
            cue = any(stan[sciezki.wysylka(9, b)] > 0 and
                      stan[sciezki.tap(9, b)] == sciezki.TAP_PRE for b in BUSY)
            if a == FADER and v > 0:
                self.assertFalse(cue, "fader przed zamknięciem CUE/talkbacku")
                self.assertEqual(stan[sciezki.mute_szyny(6)], 0, "fader przed ciszą głośników")
            if stan[MAIN] == 1:
                self.assertFalse(cue, "antena i rozmowa przed suwakiem jednocześnie")
                self.assertEqual(stan[sciezki.mute_szyny(6)], 0, "antena przy grających głośnikach")

    def test_pierwszy_krok_nad_dolem_wlacza(self):
        self.ruch("mikrofon", 1 / 16383)
        self.assertTrue(self.suma("mikrofon"))
        self.assertGreater(self.m(FADER), 0)
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])

    def test_podniesienie_konczy_wszystkie_cue(self):
        self.oba_cue()
        przed, od = dict(self.sym.wartosci), len(self.sym.dziennik)
        self.ruch("mikrofon", 0.4)
        self.assertTrue(self.suma("mikrofon"))
        self.assertFalse(self.cue_sym("telefon"))
        self.assertFalse(self.cue_sym("zoom"))
        self.assertTrue(self.suma("telefon"))
        self.assertTrue(self.suma("zoom"))
        self.assertAlmostEqual(self.m(FADER), 0.4)
        self.sprawdz_kolejnosc(przed, od)
        self.assertIn("Mikrofon włączony, koniec rozmowy", self.slowa())

    def test_f1_przy_cue_konczy_i_wlacza(self):
        self.oba_cue()
        przed, od = dict(self.sym.wartosci), len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 1.0)
        self.assertEqual(self.pow.suwaki[1], 1.0)
        self.assertFalse(self.cue_sym("telefon"))
        self.assertFalse(self.cue_sym("zoom"))
        self.sprawdz_kolejnosc(przed, od)

    def test_glosniki_przed_faderem_i_main_on(self):
        przed, od = dict(self.sym.wartosci), len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.suma("mikrofon"))
        self.sprawdz_kolejnosc(przed, od)
        z = self.zapisy(od)
        self.assertLess(z.index((FADER, 1.0)), z.index((MAIN, 1)))

    def test_f1_select_silnik_gora_dol(self):
        for zd in (("klawisz", "F1_mikrofon"), ("przycisk", 1, 3)):
            self.nacisnij(*zd)
            self.assertTrue(self.suma("mikrofon"))
            self.assertEqual(self.m(FADER), 1.0)
            self.assertEqual(self.pow.suwaki[1], 1.0)
            self.nacisnij(*zd)
            self.assertFalse(self.suma("mikrofon"))
            self.assertEqual(self.m(FADER), 0.0)
            self.assertEqual(self.pow.suwaki[1], 0.0)

    def test_dol_wylacza_i_mute_act(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.ruch("mikrofon", 0.0)
        self.assertFalse(self.suma("mikrofon"))
        self.assertFalse(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Głośniki włączone"])

    def test_ruch_w_gorze_tylko_fader_bez_mowy(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        od = len(self.sym.dziennik)
        self.ruch("mikrofon", 0.6)
        self.assertTrue(self.suma("mikrofon"))
        self.assertAlmostEqual(self.m(FADER), 0.6)
        self.assertEqual({a for a, _ in self.zapisy(od)}, {FADER})
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_odmowa_glosnikow_odklada_fader_na_dol(self):
        self.sym.awarie.ignoruj_zapis = {sciezki.mute_szyny(6)}
        self.ruch("mikrofon", 0.8)
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        self.assertEqual(self.pow.suwaki[1], 0.0)
        self.assertIn("Mikrofon nie włączony, głośniki niewyciszone, mikrofon zamknięty", self.slowa())

    def test_niepotwierdzony_pierwszy_krok_nie_otwiera(self):
        self.sym.awarie.ignoruj_zapis = {FADER}
        self.ruch("mikrofon", 1 / 16383)
        self.assertFalse(self.suma("mikrofon"), "tolerancja OSC nie może pomylić dołu z pierwszym krokiem")
        self.assertIn("Mikrofon nie włączony", " ".join(self.slowa()))

    def test_blad_koncowego_odczytu_zamyka_antene_i_suwak(self):
        oryginal = self.r._dwa_odczyty
        def odczyt(oczekiwane):
            wynik = oryginal(oczekiwane)
            return [MAIN] if oczekiwane.get(MAIN) == 1 else wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=odczyt):
            self.klawisz("F1_mikrofon")
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        self.assertIn("Mikrofon nie włączony", " ".join(self.slowa()))

    def test_podniesienie_przerywa_trzymany_talkback(self):
        self.nacisnij("przycisk", 2, 2)
        self.nacisnij("przycisk", 3, 2)
        self.slowa()
        przed, od = dict(self.sym.wartosci), len(self.sym.dziennik)
        self.ruch("mikrofon", 0.75)
        self.assertEqual(self.r._talkback, set())
        self.assertIsNone(self.r._mikrofon_sprzed)
        self.assertTrue(self.suma("mikrofon"))
        self.sprawdz_kolejnosc(przed, od)
        od = len(self.sym.dziennik)
        self.nacisnij("puszczenie", 2, 2)
        self.nacisnij("puszczenie", 3, 2)
        self.assertEqual(self.zapisy(od), [])

    def test_cue_sciaga_mikrofon_po_zamknieciu_anteny(self):
        self.klawisz("F1_mikrofon")
        od = len(self.sym.dziennik)
        self.cue("telefon")
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        z = self.zapisy(od)
        self.assertLess(z.index((MAIN, 0)), z.index((FADER, 0.0)))

    def test_poziomy_dol_rowne_dawnym_gora_cue_i_talkback(self):
        # Pomiar na wersji sprzed zmiany: Bus 1/3/4, CUE i oba MUTE = 1.0 (+10 dB).
        self.oba_cue()
        for b in BUSY:
            self.assertEqual(self.m(sciezki.wysylka(9, b)), 1.0)
        self.klawisz("F3_koniec_rozmowy")
        self.nacisnij("przycisk", 2, 2)
        self.nacisnij("przycisk", 3, 2)
        for b in BUSY:
            self.assertEqual(self.m(sciezki.wysylka(9, b)), 1.0)
        self.assertEqual(self.m(FADER), 0.0)

    def test_korekta_nieznany_maks_i_false(self):
        with patch.object(self.r.widok, "fader_db", return_value=NIEZNANY):
            self.assertEqual(self.r._korekta_mikrofonu_db(), 10.0)
            self.assertEqual(self.r._mikrofon_w_rozmowie_db(5), 10.0)
            self.u.zachowanie["mikrofon_w_rozmowie_jak_na_antenie"] = False
            self.assertEqual(self.r._korekta_mikrofonu_db(), 0.0)

    def test_cichsza_antena_talkback_z_biezacej_pozycji(self):
        self.klawisz("F1_mikrofon")
        self.ruch("mikrofon", 0.6)
        self.nacisnij("przycisk", 2, 2)
        self.assertAlmostEqual(self.m(sciezki.wysylka(9, 1)), poziom_db_na_float(-6.0), places=5)
        self.assertAlmostEqual(self.m(FADER), 0.6)
        self.nacisnij("puszczenie", 2, 2)
        self.assertTrue(self.suma("mikrofon"))

    def test_nieznany_f1_tylko_zamyka_i_sciaga(self):
        self.klawisz("F1_mikrofon")
        self.r.stan.utrata()
        self.klawisz("F1_mikrofon")
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        self.assertEqual(self.pow.suwaki[1], 0.0)

    def test_obce_podniesienie_nie_wlacza_i_nie_cofa(self):
        od = len(self.sym.dziennik)
        self.inny(FADER, 0.7)
        self.assertFalse(self.suma("mikrofon"))
        self.assertAlmostEqual(self.m(FADER), 0.7)
        self.assertEqual(self.zapisy(od), [])
        self.assertIn("z innego urządzenia", " ".join(self.slowa()))

    def test_obcy_dol_nie_zmienia_main_i_oglasza(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        od = len(self.sym.dziennik)
        self.inny(FADER, 0.0)
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        self.assertEqual(self.zapisy(od), [])
        self.assertIn("suwak na dole", " ".join(self.slowa()))

    def test_start_niespojny_bez_zapisow_pierwszy_ruch_rozstrzyga(self):
        for main, fader in ((1, 0.0), (0, 1.0)):
            self.slowa()
            self.ustaw_mikser({MAIN: main, FADER: fader, sciezki.mute_szyny(6): 0})
            od = len(self.sym.dziennik)
            self.r.synchronizuj()
            self.assertEqual(self.zapisy(od), [])
            tekst = self.slowa()
            self.assertEqual(len(tekst), 1)
            self.assertIn("suwak", tekst[0])
            self.tick()
            self.assertEqual(self.slowa(), [])
            self.ruch("mikrofon", 0.3 if main == 0 else 0.0)
            self.assertEqual(self.suma("mikrofon"), main == 0)

    def test_f1_dotyk_bez_walki_po_puszczeniu_silnik_dogania(self):
        self.nacisnij("dotyk", 1, True)
        self.pow.suwaki.clear()
        self.klawisz("F1_mikrofon")
        self.assertNotIn(1, self.pow.suwaki)
        self.assertEqual(self.m(FADER), 1.0)
        self.nacisnij("dotyk", 1, False)
        self.assertEqual(self.pow.suwaki[1], 1.0)
        self.nacisnij("dotyk", 1, True)
        self.nacisnij("suwak", 1, 0.5)
        self.klawisz("F1_mikrofon")  # świadome OFF wygrywa z zaległym ruchem
        self.nacisnij("dotyk", 1, False)
        self.tick()
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)

    def test_kaszel_ma_pierwszenstwo_dol_uniewaznia_powrot(self):
        self.klawisz("F1_mikrofon")
        self.nacisnij("przycisk", 1, 2)
        self.ruch("mikrofon", 0.5)
        self.assertFalse(self.suma("mikrofon"))
        self.assertIsNotNone(self.r._kaszel)
        self.nacisnij("puszczenie", 1, 2)
        self.assertTrue(self.suma("mikrofon"))
        self.nacisnij("przycisk", 1, 2)
        self.ruch("mikrofon", 0.0)
        self.nacisnij("puszczenie", 1, 2)
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)

    def test_f4_f5_stany_suwaka(self):
        self.info.tryb = Tryb.DZWIEKI
        self.ruch("mikrofon", 0.4)
        self.assertEqual(self.dzwieki_i_slowa(), (["mikrofon_na_antenie"], []))
        self.klawisz("F5_ostatni_komunikat")
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])

    def test_f1_przy_cue_krotki_komunikat_we_wszystkich_trybach(self):
        # Michał 30.10.2026: „Mikrofon włączony, koniec rozmowy”, bez wyliczania rozmówców.
        wyniki = {}
        for tryb in (Tryb.MOWA, Tryb.DZWIEKI, Tryb.DZWIEKI_Z_MOWA):
            self.info.tryb = tryb
            self.oba_cue()
            self.dzwieki_i_slowa()
            self.klawisz("F1_mikrofon")
            self.assertTrue(self.suma("mikrofon"))
            wyniki[tryb] = self.dzwieki_i_slowa()
            self.klawisz("F1_mikrofon")
            self.dzwieki_i_slowa()
        self.assertEqual(wyniki[Tryb.MOWA], ([], ["Mikrofon włączony, koniec rozmowy"]))
        self.assertIn("mikrofon_na_antenie", wyniki[Tryb.DZWIEKI][0])
        self.assertIn("mikrofon_na_antenie", wyniki[Tryb.DZWIEKI_Z_MOWA][0])
        self.assertIn("Mikrofon włączony, koniec rozmowy", wyniki[Tryb.DZWIEKI_Z_MOWA][1])

    def test_kaszel_trzymany_dol_gora_nie_otwiera(self):
        self.klawisz("F1_mikrofon")
        self.nacisnij("przycisk", 1, 2)
        self.ruch("mikrofon", 0.0)
        self.ruch("mikrofon", 0.8)
        self.assertFalse(self.suma("mikrofon"))
        self.nacisnij("puszczenie", 1, 2)
        self.assertFalse(self.suma("mikrofon"))
        self.ruch("mikrofon", 0.7)
        self.assertTrue(self.suma("mikrofon"))

    def test_zgubione_obce_zgloszenie_czyta_fader_bez_otwarcia(self):
        od = len(self.sym.dziennik)
        self.sym.wartosci[FADER] = 0.6  # bez xremote
        self.tick(1.0)
        self.assertAlmostEqual(self.r.widok.fader_db("mikrofon"), -6.0, places=2)
        self.assertEqual(self.zapisy(od), [])
        self.assertFalse(self.suma("mikrofon"))
        self.assertIn("z innego urządzenia", " ".join(self.slowa()))

    def test_powrot_lacznosci_nie_wykonuje_zaleglego_podniesienia(self):
        self.nacisnij("suwak", 1, 0.8)
        self.sym.awarie.rozlaczony = True
        self.tick(0.6)
        self.sym.awarie.rozlaczony = False
        od = len(self.sym.dziennik)
        self.tick(1.5)
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        self.assertEqual(self.zapisy(od), [])

    def test_niespojny_main_on_dol_najpierw_glosniki(self):
        self.ustaw_mikser({MAIN: 1, FADER: 0.0, sciezki.mute_szyny(6): 1})
        self.r.synchronizuj()
        od = len(self.sym.dziennik)
        self.ruch("mikrofon", 0.2)
        z = self.zapisy(od)
        self.assertLess(z.index((sciezki.mute_szyny(6), 0)), next(i for i, (a, v) in enumerate(z) if a == FADER and v > 0))
        self.assertTrue(self.suma("mikrofon"))

    def test_brak_potwierdzenia_cue_nigdy_dodatni_fader(self):
        self.oba_cue()
        self.sym.awarie.ignoruj_zapis = {sciezki.wysylka(9, 1)}
        od = len(self.sym.dziennik)
        self.ruch("mikrofon", 1.0)
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 0.0)
        self.assertFalse(any(a == FADER and v > 0 for a, v in self.zapisy(od)))
        self.assertIn("Mikrofon nie włączony", " ".join(self.slowa()))

    def test_fader_wylaczenia_niepotwierdzony_nie_udaje_sukcesu(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.sym.awarie.ignoruj_zapis = {FADER}
        self.klawisz("F1_mikrofon")
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 1.0)
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Synchronizacja niepełna"])

    def test_maks_z_ustawien_i_false_w_rzeczywistym_cue(self):
        from dataclasses import replace
        self.u.zrodla["mikrofon"] = replace(self.u.zrodla["mikrofon"], suwak_maks_db=5.0)
        self.klawisz("F1_mikrofon")
        self.assertAlmostEqual(self.m(FADER), poziom_db_na_float(5.0), places=5)
        self.assertAlmostEqual(self.pow.suwaki[1], 1.0, places=5)
        self.cue("telefon")
        self.assertAlmostEqual(self.m(sciezki.wysylka(9, 1)), poziom_db_na_float(5.0), places=5)
        self.cue("telefon")
        self.u.zachowanie["mikrofon_w_rozmowie_jak_na_antenie"] = False
        self.cue("telefon")
        self.assertEqual(self.m(sciezki.wysylka(9, 1)), poziom_db_na_float(0.0))

    def test_hold_i_licznik_po_ruchu(self):
        zdarzenia = []
        with patch.object(self.r, "_zlec_hold", side_effect=lambda on: zdarzenia.append((on, self.m(MAIN)))):
            self.ruch("mikrofon", 0.4)
            self.assertIn((True, 0), zdarzenia, "zamiar Hold przed Main On")
            self.r._aktualizuj_liczniki()
            self.assertIs(self.r._liczniki["mikrofon"][0], True)
            poczatek = self.r._liczniki["mikrofon"][1]
            self.ruch("mikrofon", 0.6)
            self.assertEqual(self.r._liczniki["mikrofon"][1], poczatek)
            self.ruch("mikrofon", 0.0)
            self.assertIn((False, 0), zdarzenia)
        self.assertFalse(self.suma("mikrofon"))

    def test_ustawienia_michala_bez_scalania(self):
        katalog = Path(__file__).parent / "dane_mikrofon_suwak"
        for nazwa, md5 in (("stanowisko.json", "998374b9336fa40f3650f90a5cf06c7e"),
                           ("poziomy_bazowe.json", "3c40ba18e3fb07c04fcec99527314390")):
            self.assertEqual(hashlib.md5((katalog / nazwa).read_bytes()).hexdigest(), md5)
        u = ustawienia.wczytaj(katalog / "stanowisko.json", katalog / "poziomy_bazowe.json")
        self.r.u = self.u = u
        self.r.widok = Widok(u, self.r.stan)
        self.oba_cue()
        self.ruch("mikrofon", 0.2)
        self.assertTrue(self.suma("mikrofon"))
        self.ruch("mikrofon", 0.0)
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.m(FADER), 1.0)
