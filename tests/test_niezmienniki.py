"""Niezmienniki anteny (plan v20, rozdz. 4-8): zapora, nowe reguły CUE, profil.

Każda nowa reguła zapory ma test, w którym stan jest ustawiony tak, że
zapis może odrzucić TYLKO ona (pozostałe reguły go przepuszczają). Test
sprawdza też nazwę reguły w wyjątku. Test mutacyjny w test_mutacje.py
wyłącza kolejno każdą regułę w kopii kodu i potwierdza, że ten zestaw pada.
"""

import random
import unittest

from pomoc import TestZSymulatorem, sciezki, poziom_db_na_float
from mostek.logika import NOWE_REGULY, REGULY_ZLOZONE, NaruszenieZapory, sprawdz_profil

POZIOM = poziom_db_na_float(0.0)


class TestZapora(TestZSymulatorem):
    def odrzuc(self, adres, wartosc, regula=None):
        przed = len(self.sym.dziennik)
        with self.assertRaises(NaruszenieZapory) as kontekst:
            self.r.zapora.sprawdz(adres, wartosc, self.r.widok)
        self.assertEqual(len(self.sym.dziennik), przed)
        if regula is not None:
            self.assertEqual(kontekst.exception.regula, regula, str(kontekst.exception))

    def przepusc(self, adres, wartosc):
        self.r.zapora.sprawdz(adres, wartosc, self.r.widok)

    def wycisz_glosniki(self):
        self.ustaw_mikser({sciezki.mute_szyny(b): 0 for b in self.u.szyny_glosnikow})
        self.assertTrue(self.r.synchronizuj())

    # --- stałe niezmienniki (bez osłabienia) ----------------------------------
    def test_telefon_nigdy_w_bus1(self):
        self.odrzuc(sciezki.wysylka(10, 1), POZIOM)

    def test_zoom_nigdy_w_bus3_i_bus4(self):
        for k in (7, 8):
            for b in (3, 4):
                self.odrzuc(sciezki.wysylka(k, b), POZIOM)

    def test_do_bus2_tylko_telefon(self):
        for k in (1, 2, 3, 4, 5, 6, 7, 8, 9):
            self.odrzuc(sciezki.wysylka(k, 2), POZIOM)
        self.przepusc(sciezki.wysylka(10, 2), POZIOM)

    def test_mikrofon_nigdy_w_glosnikach(self):
        """Plan v22: zakaz dotyczy Bus 6 (głośniki mono); Bus 5 to klucz przyciszania."""
        self.wycisz_glosniki()
        self.assertEqual(self.u.szyny_glosnikow, (6,))
        with self.assertRaisesRegex(NaruszenieZapory, "głośnik"):
            self.r.zapora.sprawdz(sciezki.wysylka(9, 6), POZIOM, self.r.widok)

    def test_wysylki_do_fx_zamkniete(self):
        for b in sciezki.SZYNY_FX:
            self.odrzuc(sciezki.wysylka(9, b), POZIOM)

    def test_szyny_nie_trafiaja_na_main(self):
        for b in range(1, 7):
            self.odrzuc(sciezki.szyna_lr(b), 1)

    def test_zamkniecie_zawsze_dozwolone(self):
        self.r.widok.cue_zbior()
        for adres in (sciezki.lr(9), sciezki.wysylka(10, 1), sciezki.wysylka(9, 5), sciezki.szyna_lr(1),
                      sciezki.wysylka(9, 1), sciezki.lr(10)):
            self.przepusc(adres, 0)

    def test_otwarcie_mikrofonu_wymaga_wyciszonych_glosnikow(self):
        self.assertFalse(self.glosniki_wyciszone())
        self.odrzuc(sciezki.lr(9), 1)
        self.odrzuc(sciezki.wysylka(9, 1), POZIOM)

    def test_stan_nieznany_blokuje_kazde_otwarcie(self):
        self.r._utrata("test")
        self.odrzuc(sciezki.lr(1), 1)
        self.odrzuc(sciezki.wysylka(1, 1), POZIOM)
        self.odrzuc(sciezki.mute_szyny(6), 1)
        self.przepusc(sciezki.lr(9), 0)

    def test_glosniki_nie_graja_przy_otwartym_torze_mikrofonu(self):
        self.cue("zoom")
        self.assertTrue(self.wysylka("mikrofon", "zoom"))
        self.odrzuc(sciezki.mute_szyny(6), 1)

    def test_sciezka_spoza_rejestru_odrzucona(self):
        self.odrzuc("/ch/09/eq/1/g", 0.5)

    def test_regula_sciezka_tylko_do_odczytu(self):
        """Indeks jest w rejestrze. Tylko nowa reguła odrzuca ten zapis."""
        self.assertTrue(sciezki.w_rejestrze(sciezki.SCENA_INDEKS))
        self.odrzuc(sciezki.SCENA_INDEKS, 0, "sciezka_tylko_do_odczytu")
        self.r.zapora.wylaczone.add("sciezka_tylko_do_odczytu")
        self.przepusc(sciezki.SCENA_INDEKS, 0)

    def test_scen_i_akcji_nie_zapisuje_zadna_wartosc(self):
        for rodzina in ("/-snap", "/snap", "/-action"):
            for koniec in ("", "/", "/index", "/load", "/save", "/delete", "/clearsolo", "/nowa/akcja"):
                for wartosc in (0, 1, -1, 0.0, "", "BAZA", None):
                    with self.subTest(adres=rodzina + koniec, wartosc=wartosc):
                        self.odrzuc(rodzina + koniec, wartosc, "sciezka_tylko_do_odczytu")
        # Bez regresji zwykłych zamknięć i odczytu sceny.
        self.przepusc(sciezki.lr(9), 0)
        self.assertTrue(self.r.synchronizuj())

    def test_regula_sciezka_w_rejestrze(self):
        """L06 (analiza v22): pełna ścieżka z rejestru, nie dopasowanie sufiksu.
        Zamknięcie (wartość 0) też nie przechodzi: adres nie istnieje w MR18."""
        for adres in ("/obce/mix/lr", "/ch/17/mix/lr", "/ch/00/mix/lr", "/ch/09/mix/11/level",
                      "/bus/7/mix/on", "/rtn/5/mix/05/level", "/ch/9/mix/lr"):
            self.odrzuc(adres, 0, "sciezka_w_rejestrze")
        self.przepusc(sciezki.lr(9), 0)
        self.przepusc(sciezki.wysylka_powrotu("aux", 5), 0.0)

    def test_regula_glosniki_przy_niezgodnym_profilu(self):
        """L03 (analiza v22): mikrofon bez otwartego toru, głośniki wyciszone,
        profil blokuje: odciszenie Bus 6 odrzuca tylko ta reguła. Wyciszenie
        zawsze dozwolone."""
        self.wycisz_glosniki()
        self.assertIs(self.r.widok.mikrofon_ma_otwarty_tor(), False)
        self.r.zapora.profil_blokuje = True
        self.odrzuc(sciezki.mute_szyny(6), 1, "glosniki_przy_niezgodnym_profilu")
        self.przepusc(sciezki.mute_szyny(6), 0)
        self.r.zapora.profil_blokuje = False
        self.przepusc(sciezki.mute_szyny(6), 1)

    def test_powrot_do_klucza_tylko_zamykany(self):
        """L05: wysyłki powrotów do szyn mostek wyłącznie zamyka."""
        self.odrzuc(sciezki.wysylka_powrotu("aux", 5), POZIOM)
        self.odrzuc(sciezki.wysylka_powrotu(1, 5), POZIOM)
        self.przepusc(sciezki.wysylka_powrotu(1, 5), 0.0)

    # --- nowe reguły (karta, pkt 4): każda izolowana -------------------------
    def test_regula_cue_mikrofon_na_antene(self):
        self.cue("telefon")
        self.odrzuc(sciezki.lr(9), 1, "cue_mikrofon_na_antene")

    def test_regula_cue_rozmowca_na_antene(self):
        self.cue("telefon")
        self.odrzuc(sciezki.lr(10), 1, "cue_rozmowca_na_antene")
        self.cue("zoom")
        self.odrzuc(sciezki.lr(7), 1, "cue_rozmowca_na_antene")

    def test_regula_cue_mikrofon_do_obcych(self):
        """Przy CUE samego telefonu Zoom nie dostaje mikrofonu (także za suwakiem)."""
        self.cue("telefon")
        self.odrzuc(sciezki.wysylka(9, 3), POZIOM, "cue_mikrofon_do_obcych")

    def test_regula_cue_rozmowca_do_obcych(self):
        """Przy CUE samego telefonu Zoom nie dostaje telefonu."""
        self.cue("telefon")
        self.odrzuc(sciezki.wysylka(10, 3), POZIOM, "cue_rozmowca_do_obcych")

    def test_regula_cue_obcy_do_rozmowy(self):
        """Przy CUE samego telefonu telefon nie dostaje Zooma (Zoom na antenie, sytuacja E)."""
        self.ruch("zoom", 1.0)
        self.cue("telefon")
        self.odrzuc(sciezki.wysylka(7, 1), POZIOM, "cue_obcy_do_rozmowy")

    def test_regula_cue_glos_przed_suwakiem(self):
        """Głos przed suwakiem tylko w rozmowie: oba rozmówcy czekają, punkt PRE."""
        self.ustaw_mikser({sciezki.tap(10, 3): sciezki.TAP_PRE, sciezki.tap(10, 4): sciezki.TAP_PRE})
        self.assertTrue(self.r.synchronizuj())
        self.odrzuc(sciezki.wysylka(10, 3), POZIOM, "cue_glos_przed_suwakiem")
        # Ten sam zapis za suwakiem przechodzi (telefon na dole, nic nie słychać).
        self.ustaw_mikser({sciezki.tap(10, 3): sciezki.TAP_POST, sciezki.tap(10, 4): sciezki.TAP_POST})
        self.assertTrue(self.r.synchronizuj())
        self.przepusc(sciezki.wysylka(10, 3), POZIOM)

    def test_regula_cue_muzyka_ciszej(self):
        self.cue("telefon")
        bazowy = poziom_db_na_float(self.u.poziom_bazowy("muzyka1", "telefon"))
        przyciszony = poziom_db_na_float(self.u.poziom_bazowy("muzyka1", "telefon") + self.u.przyciszenie_muzyki_db)
        self.przepusc(sciezki.wysylka(1, 1), przyciszony)
        self.odrzuc(sciezki.wysylka(1, 1), bazowy, "cue_muzyka_ciszej")

    def test_regula_tap_wartosci(self):
        self.odrzuc(sciezki.tap(9, 1), 1, "tap_wartosci")            # przed korekcją
        self.odrzuc(sciezki.tap(9, 6), sciezki.TAP_PRE, "tap_wartosci")   # głośniki
        self.odrzuc(sciezki.tap(9, 5), sciezki.TAP_POST, "tap_wartosci")  # klucz tylko przed suwakiem
        self.odrzuc(sciezki.tap(10, 5), sciezki.TAP_PRE, "tap_wartosci")  # słuchacz nie w kluczu
        self.odrzuc(sciezki.tap(1, 1), sciezki.TAP_PRE, "tap_wartosci")   # muzyka przed suwakiem
        self.odrzuc(sciezki.tap(9, 7), sciezki.TAP_PRE, "tap_wartosci")   # FX
        self.przepusc(sciezki.tap(9, 1), sciezki.TAP_PRE)

    def test_regula_tap_przy_otwartej(self):
        # Mikrofon na antenie: wysyłka do telefonu otwarta za suwakiem; zmiana
        # punktu pobrania na PRE (wartość dozwolona) odrzucona tylko przez tę regułę.
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.wysylka("mikrofon", "telefon"))
        self.odrzuc(sciezki.tap(9, 1), sciezki.TAP_PRE, "tap_przy_otwartej")
        self.przepusc(sciezki.tap(9, 1), sciezki.TAP_POST)            # bez zmiany: dozwolone

    # --- plan v22: klucz przyciszania (Bus 5) i głośniki mono (Bus 6) --------
    def test_regula_glosniki_przy_mikrofonie(self):
        """Tor mikrofonu otwiera się tylko przy potwierdzonym wyciszeniu Bus 6."""
        self.assertFalse(self.glosniki_wyciszone())
        self.odrzuc(sciezki.lr(9), 1, "glosniki_przy_mikrofonie")
        self.odrzuc(sciezki.wysylka(9, 1), POZIOM, "glosniki_przy_mikrofonie")

    def test_regula_glosniki_bez_mikrofonu(self):
        """Powrót Bus 6: także podczas kaszlu, talkbacku i logicznego CUE."""
        self.wycisz_glosniki()
        for a in (sciezki.lr(9), sciezki.wysylka(9, 1), sciezki.wysylka(9, 3)):
            with self.subTest(adres=a):
                self.r.stan.potwierdz(a, 1, self.zegar())
                self.odrzuc(sciezki.mute_szyny(6), 1, "glosniki_bez_mikrofonu")
                self.r.stan.zapomnij(a)
                self.odrzuc(sciezki.mute_szyny(6), 1, "glosniki_bez_mikrofonu")
                self.r.stan.potwierdz(a, 0, self.zegar())
        for tryb in ("kaszel", "talkback", "cue_chwilowe"):
            stary = getattr(self.r.widok, tryb)
            setattr(self.r.widok, tryb, True if tryb == "kaszel" else frozenset({"telefon"}))
            self.odrzuc(sciezki.mute_szyny(6), 1, "glosniki_bez_mikrofonu")
            self.przepusc(sciezki.mute_szyny(6), 0)
            setattr(self.r.widok, tryb, stary)
        self.przepusc(sciezki.mute_szyny(6), 1)

    def test_talkback_wymaga_potwierdzonego_wyciszenia_glosnikow(self):
        self._chwilowy(talkback={"telefon"})
        self.r.stan.potwierdz(sciezki.tap(9, 1), sciezki.TAP_PRE, self.zegar())
        for v in (1, None):
            if v is None:
                self.r.stan.zapomnij(sciezki.mute_szyny(6))
            else:
                self.r.stan.potwierdz(sciezki.mute_szyny(6), v, self.zegar())
            self.odrzuc(sciezki.wysylka(9, 1), POZIOM, "glosniki_przy_mikrofonie")
        self.r.stan.potwierdz(sciezki.mute_szyny(6), 0, self.zegar())
        self.przepusc(sciezki.wysylka(9, 1), POZIOM)

    def test_regula_klucz_tylko_glosy(self):
        """Do Bus 5 wyłącznie mikrofon i Zoom (kanały 9, 7, 8): telefon, muzyka i rezerwa nie."""
        for k in (10, 1, 2, 3, 6, 11, 16):
            self.odrzuc(sciezki.wysylka(k, 5), POZIOM, "klucz_tylko_glosy")

    def test_regula_klucz_bez_wyjscia(self):
        """Bus 5 nie jest źródłem wyjścia USB ani nie jest połączony linkiem z głośnikami."""
        for wy in (1, 5, 18):
            self.odrzuc(sciezki.usb_zrodlo(wy), sciezki.USB_ZRODLO_SZYNA[5], "klucz_bez_wyjscia")
        self.odrzuc(sciezki.buslink(5), 1, "klucz_bez_wyjscia")
        self.przepusc(sciezki.usb_zrodlo(5), 36)          # kopia Main L, jak w scenie BAZA

    def test_klucz_nie_na_main_lr(self):
        self.odrzuc(sciezki.szyna_lr(5), 1, "klucz_bez_wyjscia")

    def test_regula_klucz_ta_sama_rozmowa(self):
        """Mikrofon na antenie, słuchacz czeka: mikrofon nie trafia do klucza
        (sytuacja B). Zoom na antenie, słuchacz czeka: Zoom też nie."""
        self.klawisz("F1_mikrofon")
        self.ruch("zoom", 1.0)
        self.assertTrue(self.glosniki_wyciszone())
        self.odrzuc(sciezki.wysylka(9, 5), POZIOM, "klucz_ta_sama_rozmowa")
        self.odrzuc(sciezki.wysylka(7, 5), POZIOM, "klucz_ta_sama_rozmowa")

    def test_klucz_przepuszcza_ta_sama_rozmowe(self):
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.ruch("zoom", 1.0)
        self.przepusc(sciezki.wysylka(9, 5), POZIOM)
        self.przepusc(sciezki.wysylka(7, 5), POZIOM)

    def test_ustawienia_przyciszacza_tylko_do_odczytu(self):
        for adres, v in ((sciezki.keysrc(10), 0), (sciezki.dyn_on(10), 0), (sciezki.insert_fxslot(9), 0),
                         (sciezki.insert_on(10), 0), (sciezki.fader_szyny(5), 0.0), (sciezki.mute_szyny(5), 0)):
            with self.assertRaisesRegex(NaruszenieZapory, "scenie BAZA"):
                self.r.zapora.sprawdz(adres, v, self.r.widok)

    def test_regula_klucz_przy_niezgodnym_profilu(self):
        """Słuchacz i Zoom na antenie (ta sama rozmowa), ale profil blokuje
        (np. szyna na Main LR z innego urządzenia): Zoom nie wchodzi do klucza.
        Zamknięcie wysyłki do klucza zawsze dozwolone."""
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.ruch("zoom", 1.0)
        self.r.zapora.profil_blokuje = True
        for k in (7, 8):
            self.odrzuc(sciezki.wysylka(k, 5), POZIOM, "klucz_przy_niezgodnym_profilu")
            self.przepusc(sciezki.wysylka(k, 5), 0.0)

    # --- kaszel_bez_cue: realizowany przez dwie istniejące reguły -------------
    # Test mutacyjny wyłącza każdą z nich i sprawdza, że pada odpowiedni test.
    def _w_kaszlu(self):
        self.klawisz("F1_mikrofon")
        self.nacisnij("przycisk", 1, 2)          # MUTE paska mikrofonu: kaszel
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertIsNotNone(self.r._kaszel)

    def test_kaszel_bez_cue_cue_mikrofon_na_antene(self):
        """W trakcie kaszlu inne urządzenie otworzyło rozmowę na CUE z telefonem:
        przywrócenie Main On mikrofonu odrzuca reguła cue_mikrofon_na_antene."""
        self._w_kaszlu()
        self.inny(sciezki.tap(9, 1), sciezki.TAP_PRE)
        self.inny(sciezki.wysylka(9, 1), POZIOM)
        self.assertTrue(self.r.widok.cue("telefon"))
        self.assertTrue(self.r.widok.glosniki_wyciszone())
        self.odrzuc(sciezki.lr(9), 1, "cue_mikrofon_na_antene")

    def test_kaszel_bez_cue_glosniki_przy_mikrofonie(self):
        """W trakcie kaszlu inne urządzenie odciszyło głośniki: przywrócenie
        Main On mikrofonu odrzuca reguła glosniki_przy_mikrofonie."""
        self._w_kaszlu()
        self.inny(sciezki.mute_szyny(6), 1)
        self.assertFalse(self.r.widok.glosniki_wyciszone())
        # Badamy powrót PO puszczeniu, nie otwarcie podczas trzymania.
        self.r._kaszel = None
        self.r._flagi_chwilowe()
        self.odrzuc(sciezki.lr(9), 1, "glosniki_przy_mikrofonie")

    # Chwilowe przejęcie mikrofonu nie jest zmianą CUE rozmówcy.
    def _chwilowy(self, cue=(), talkback=(), kaszel=False):
        self.wycisz_glosniki()
        self.r.widok.cue_chwilowe = frozenset(cue)
        self.r.widok.talkback = frozenset(talkback)
        self.r.widok.kaszel = kaszel

    def test_regula_chwilowy_bez_anteny(self):
        self._chwilowy(talkback={"telefon"})
        self.odrzuc(sciezki.lr(9), 1, "chwilowy_bez_anteny")
        self.przepusc(sciezki.lr(9), 0)

    def test_regula_chwilowy_bez_klucza(self):
        self._chwilowy(cue={"telefon"}, talkback={"telefon"})
        self.odrzuc(sciezki.wysylka(9, 5), POZIOM, "chwilowy_bez_klucza")
        self.przepusc(sciezki.wysylka(9, 5), 0)

    def test_regula_talkback_tylko_adresaci(self):
        self._chwilowy(talkback={"telefon"})
        self.odrzuc(sciezki.wysylka(9, 3), POZIOM, "talkback_tylko_adresaci")
        self.przepusc(sciezki.wysylka(9, 3), 0)

    def test_regula_talkback_przed_suwakiem(self):
        self._chwilowy(talkback={"telefon"})
        # Punkt POST jest dozwolony ogólnie, ale nie dla talkbacku.
        self.odrzuc(sciezki.wysylka(9, 1), POZIOM, "talkback_przed_suwakiem")

    def test_regula_talkback_izolacja(self):
        self._chwilowy(talkback={"telefon"})
        self.r.stan.potwierdz(sciezki.tap(9, 1), sciezki.TAP_PRE, self.zegar())
        # Stary tor antenowy nadal otwarty: nie wolno jeszcze otworzyć talkbacku.
        self.r.stan.potwierdz(sciezki.lr(9), 1, self.zegar())
        self.odrzuc(sciezki.wysylka(9, 1), POZIOM, "talkback_izolacja")

    def test_regula_kaszel_bez_wysylek(self):
        self._chwilowy(cue={"telefon"}, kaszel=True)
        self.odrzuc(sciezki.wysylka(9, 1), POZIOM, "kaszel_bez_wysylek")
        self.przepusc(sciezki.wysylka(9, 1), 0)

    def test_talkback_do_adresata_nie_przelacza_cue(self):
        self._chwilowy(cue={"zoom"}, talkback={"telefon"})
        self.r.stan.potwierdz(sciezki.tap(9, 1), sciezki.TAP_PRE, self.zegar())
        self.przepusc(sciezki.wysylka(9, 1), POZIOM)
        self.assertEqual(self.r.widok.cue_zbior(), frozenset({"zoom"}))

    def test_kazda_nowa_regula_ma_test(self):
        nazwy = {n[len("test_regula_"):] for n in dir(self) if n.startswith("test_regula_")}
        self.assertEqual(nazwy, set(NOWE_REGULY))
        for zlozona, straznicy in REGULY_ZLOZONE.items():
            for s in straznicy:
                self.assertTrue(hasattr(self, f"test_{zlozona}_{s}"), (zlozona, s))


class TestNiezmiennikiWCalejPracy(TestZSymulatorem):
    """Po każdej sekwencji przycisków mikser nie łamie żadnego niezmiennika."""

    def test_wszystkie_sekwencje_przyciskow(self):
        zdarzenia = [("klawisz", "F1_mikrofon"), ("klawisz", "F3_koniec_rozmowy"),
                     ("przycisk", 2, 3), ("przycisk", 3, 3), ("przycisk", 1, 3), ("przycisk", 4, 3),
                     ("klawisz", "glosniki_wlacz"), ("klawisz", "sluchaj_programu")]
        los = random.Random(20)
        for _ in range(300):
            r = los.random()
            if r < 0.7:
                self.nacisnij(*los.choice(zdarzenia))
            else:
                self.ruch(los.choice(("telefon", "zoom", "mikrofon", "muzyka1")), los.choice((0.0, 1.0)))
            self.slowa()
            self.assertEqual(self.naruszenia_miksera(), [])


class TestProfil(TestZSymulatorem):
    synchronizuj_na_starcie = False

    def test_naruszenie_profilu_blokuje_otwarcie_mikrofonu(self):
        self.ustaw_mikser({sciezki.wysylka(9, 7): POZIOM})     # mikrofon do FX
        self.assertTrue(self.r.synchronizuj())
        self.assertTrue(self.r.zapora.profil_blokuje)
        mowa = self.slowa()
        self.assertTrue(any("Profil miksera niezgodny" in s for s in mowa), mowa)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertTrue(any("nie włączony" in s for s in self.slowa()))

    def test_suchy_mikrofon_na_usb_wykryty(self):
        self.ustaw_mikser({sciezki.usb_zrodlo(5): 8})
        self.assertTrue(self.r.synchronizuj())
        opisy = [n.opis for n in sprawdz_profil(self.u, self.r.widok)]
        self.assertTrue(any("USB 5" in o for o in opisy), opisy)

    def test_telefon_wracajacy_do_siebie_wykryty(self):
        self.ustaw_mikser({sciezki.wysylka(10, 1): POZIOM})
        self.assertTrue(self.r.synchronizuj())
        self.assertTrue(self.r.zapora.profil_blokuje)

    def test_muzyka_przed_suwakiem_zgloszona(self):
        self.ustaw_mikser({sciezki.tap(1, 1): sciezki.TAP_PRE})
        self.assertTrue(self.r.synchronizuj())
        opisy = [n.opis for n in sprawdz_profil(self.u, self.r.widok)]
        self.assertTrue(any("Muzyka 1: punkt wysyłki" in o for o in opisy), opisy)

    def test_poprawny_profil_nie_blokuje(self):
        self.assertTrue(self.r.synchronizuj())
        self.assertFalse(self.r.zapora.profil_blokuje)
        self.assertEqual(sprawdz_profil(self.u, self.r.widok), [])

    # --- plan v22: klucz przyciszania w profilu -------------------------------
    def opisy(self):
        """Naruszenia profilu z pełnego odczytu, z dziennika (P02: pełny odczyt
        może już ochronnie zamknąć groźną drogę, więc stan po odczycie jest
        inny niż wykryty)."""
        od = len(self.r.dziennik)
        self.assertTrue(self.r.synchronizuj())
        return {d[2]: d[3] for d in self.r.dziennik[od:] if d[1] == "profil"}

    def test_muzyka_bez_main_on_zgloszona_bez_blokady(self):
        """Scena BAZA: wszystkie pary muzyki mają Main On stale włączone (decyzja z 17.10.2026)."""
        self.ustaw_mikser({sciezki.lr(3): 0, sciezki.lr(4): 0})
        o = self.opisy()
        self.assertIs(o.get("Muzyka 2 bez Main On, w scenie BAZA muzyka ma Main On stale włączone"), False, o)
        self.assertFalse(self.r.zapora.profil_blokuje)

    def test_scena_baza_muzyka_main_on(self):
        for k in range(1, 7):
            self.assertEqual(self.m(sciezki.lr(k)), 1, k)

    def test_klucz_na_main_lr_blokuje(self):
        self.ustaw_mikser({sciezki.szyna_lr(5): 1})
        o = self.opisy()
        self.assertIs(o.get("klucz przyciszania (Bus 5) przypisany do Main LR"), True, o)
        self.assertTrue(self.r.zapora.profil_blokuje)
        # P02: pełny odczyt zdejmuje szynę z Main LR, blokada zostaje.
        self.assertEqual(self.m(sciezki.szyna_lr(5)), 0)
        self.assertIn("Ochronne zamknięcie: szyna 5 zdjęta z Main LR", self.slowa())

    def test_klucz_na_usb_blokuje(self):
        self.ustaw_mikser({sciezki.usb_zrodlo(7): sciezki.USB_ZRODLO_SZYNA[5]})
        o = self.opisy()
        self.assertIs(o.get("wyjście USB 7 przenosi klucz przyciszania (Bus 5)"), True, o)
        self.assertTrue(self.r.zapora.profil_blokuje)

    def test_klucz_z_linkiem_glosnikow_blokuje(self):
        self.ustaw_mikser({sciezki.buslink(5): 1})
        o = self.opisy()
        self.assertIs(o.get("klucz przyciszania połączony linkiem z szyną 6"), True, o)

    def test_niezgodny_przyciszacz_zgloszony_bez_blokady(self):
        self.ustaw_mikser({sciezki.keysrc(10): 0, sciezki.insert_fxslot(10): 3, sciezki.dyn_on(10): 0,
                           sciezki.fader_szyny(5): 0.5})
        o = self.opisy()
        for opis in ("kanał 10: klucz kompresora nie jest z Bus 5", "kanał 10: insert inny niż Fx1B",
                     "kanał 10: kompresor przyciszający wyłączony", "master Bus 5 nie na poziomie nominalnym"):
            self.assertIs(o.get(opis), False, (opis, o))
        self.assertFalse(self.r.zapora.profil_blokuje, "niezgodny przyciszacz nie blokuje otwarć")
        mowa = self.slowa()
        self.assertFalse(any("Profil miksera niezgodny" in s for s in mowa), mowa)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)

    def test_przyciszacz_nie_jest_zapisywany(self):
        """Pełny odczyt czyta przyciszacz, ale mostek go nigdy nie zapisuje."""
        self.ustaw_mikser({sciezki.keysrc(10): 0})
        self.assertTrue(self.r.synchronizuj())
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        zapisane = {a for a, _ in self.zapisy()}
        for a in (sciezki.keysrc(10), sciezki.dyn_on(10), sciezki.insert_fxslot(10), sciezki.fader_szyny(5),
                  sciezki.mute_szyny(5)):
            self.assertNotIn(a, zapisane)
        self.assertEqual(self.m(sciezki.keysrc(10)), 0)


class TestSzynaNaMainLRZInnegoUrzadzenia(TestZSymulatorem):
    """Poprawka przed odbiorem: szyna 1 do 6 przypisana do Main LR z innego
    urządzenia (AOSC) w trakcie pracy unieważnia profil, blokuje otwarcia
    i zamyka klucz przyciszania (Bus 5), także w trwającej rozmowie."""

    SZYNY = (1, 2, 3, 4, 5, 6)

    def kazda_szyna(self, scenariusz):
        """Scenariusz dla każdej szyny 1 do 6 na świeżym symulatorze."""
        self.tearDown()
        try:
            for b in self.SZYNY:
                with self.subTest(szyna=b):
                    self.setUp()
                    try:
                        scenariusz(b)
                    finally:
                        self.tearDown()
        finally:
            self.setUp()

    def na_lr(self, b):
        self.slowa()
        self.inny(sciezki.szyna_lr(b), 1)
        mowa = self.slowa()
        # Jak zmiana routingu: pełny odczyt, potem komunikat profilu (kontrakt pkt 8).
        self.assertEqual(mowa[:1], ["Zmiana routingu z innego urządzenia, odczytuję stan"], (b, mowa))
        self.assertTrue(self.r.zapora.profil_blokuje, (b, mowa))
        self.assertTrue(any("Profil miksera niezgodny" in s for s in mowa), (b, mowa))
        return mowa

    def test_przed_cue(self):
        def scenariusz(b):
            self.na_lr(b)
            self.cue("telefon")
            self.assertEqual(self.w_kluczu(), set(), b)
            self.klawisz("F1_mikrofon")
            self.assertEqual(self.m(sciezki.lr(9)), 0, "F1 nie otwiera mikrofonu")
            self.assertEqual(self.w_kluczu(), set(), b)
        self.kazda_szyna(scenariusz)

    def test_w_trakcie_cue(self):
        def scenariusz(b):
            self.cue("telefon")
            self.assertTrue(self.cue_sym("telefon"))
            self.assertEqual(self.w_kluczu(), {"mikrofon"})
            self.na_lr(b)
            self.assertEqual(self.w_kluczu(), set(), "klucz zamknięty w trwającej rozmowie")
            self.tick()
            self.assertEqual(self.w_kluczu(), set(), "klucz nie wraca")
        self.kazda_szyna(scenariusz)

    def test_mikrofon_i_sluchacz_na_antenie(self):
        def scenariusz(b):
            self.klawisz("F1_mikrofon")
            self.ruch("telefon", 1.0)
            self.ruch("zoom", 1.0)
            self.assertEqual(self.w_kluczu(), {"mikrofon", "zoom"})
            self.na_lr(b)
            self.assertEqual(self.w_kluczu(), set(), "klucz zamknięty przy blokadzie profilu")
            self.ruch("zoom", 0.0)
            self.ruch("zoom", 1.0)
            mowa = self.slowa()
            self.assertEqual(self.w_kluczu(), set(), "ruch suwaka nie otwiera klucza")
            # Cel przejścia nie planuje klucza przy blokadzie, więc zapora nie
            # musi niczego odrzucać i przejście jest pełne.
            self.assertFalse(any("Przejście niepełne" in s for s in mowa), mowa)
        self.kazda_szyna(scenariusz)

    def test_inne_blokujace_naruszenie_w_trakcie_cue(self):
        """Mikrofon do efektów z innego urządzenia w trakcie rozmowy ze
        słuchaczem: profil przeliczony bez pełnego odczytu, otwarcia
        zablokowane, klucz przyciszania zamknięty."""
        self.cue("telefon")
        self.assertEqual(self.w_kluczu(), {"mikrofon"})
        self.slowa()
        self.inny(sciezki.wysylka(9, 7), POZIOM)
        mowa = self.slowa()
        self.assertTrue(self.r.zapora.profil_blokuje, mowa)
        self.assertTrue(any("Profil miksera niezgodny: kanał 9 wysyła do efektów" in s for s in mowa), mowa)
        self.assertEqual(self.w_kluczu(), set())
        self.inny(sciezki.wysylka(9, 7), 0.0)
        self.assertTrue(self.r.zapora.profil_blokuje, "blokadę zdejmuje dopiero pełny odczyt")

    def test_zgubione_zgloszenie_lapie_odczyt_okresowy(self):
        """Zgłoszenie /xremote zginęło: odczyt okresowy torów krytycznych
        widzi szynę na Main LR i robi to samo co przy zgłoszeniu."""
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.assertEqual(self.w_kluczu(), {"mikrofon"})
        self.slowa()
        self.sym.wartosci[sciezki.szyna_lr(5)] = 1      # bez rozesłania zgłoszenia
        mowa = self.czekaj(1.0, krok=0.6)
        self.assertTrue(self.r.zapora.profil_blokuje, mowa)
        self.assertTrue(any("Profil miksera niezgodny" in s for s in mowa), mowa)
        self.assertEqual(self.w_kluczu(), set())

    def test_powrot_szyny_z_main_lr_zdejmuje_blokade(self):
        """P02: mostek sam zdejmuje szynę z Main LR, ale blokada zostaje do
        pełnego odczytu zgodnego profilu. F2 przy blokadzie robi pełny odczyt."""
        mowa = self.na_lr(5)
        self.assertIn("Ochronne zamknięcie: szyna 5 zdjęta z Main LR", mowa)
        self.assertEqual(self.m(sciezki.szyna_lr(5)), 0)
        self.assertTrue(self.r.zapora.profil_blokuje, "samo zamknięcie nie zdejmuje blokady")
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.slowa()
        self.klawisz("F2_status")
        self.assertIn("Profil miksera zgodny, otwieranie odblokowane", self.slowa())
        self.assertFalse(self.r.zapora.profil_blokuje)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)

    def test_szyna_przywrocona_z_innego_urzadzenia_pelny_odczyt(self):
        """Inne urządzenie przypisuje szynę do Main LR, mostek ją zdejmuje,
        potem inne urządzenie przypisuje ją znowu: każda zmiana to pełny odczyt."""
        self.na_lr(3)
        self.assertEqual(self.m(sciezki.szyna_lr(3)), 0)
        self.na_lr(3)
        self.assertEqual(self.m(sciezki.szyna_lr(3)), 0)


if __name__ == "__main__":
    unittest.main()
