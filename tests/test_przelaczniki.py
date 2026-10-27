"""Przełącznik mikrofonu, stan NIEZNANY, „czekam na mikser”, mapa paska v20, głośniki."""

import threading
import unittest

from pomoc import TestZSymulatorem, sciezki


class TestPrzelacznikMikrofonu(TestZSymulatorem):
    def test_wysyla_jawna_wartosc_przeciwna_do_odczytu(self):
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        self.assertIn((sciezki.lr(9), 1), self.zapisy(od))
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        self.assertIn((sciezki.lr(9), 0), self.zapisy(od))
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Głośniki włączone"])

    def test_select_paska_mikrofonu_dziala_jak_f1(self):
        """Michał 21.10.2026: przełącznik mikrofonu na SELECT paska 1 (najniższy
        przycisk, tuż nad suwakiem), bo używa go najczęściej."""
        self.nacisnij("przycisk", 1, 3)
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])
        self.zegar.przesun(0.2)
        self.nacisnij("przycisk", 1, 3)
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Głośniki włączone"])

    def test_suwak_mikrofonu_do_plus_10_db(self):
        """Michał 21.10.2026: suwak mikrofonu w górze = +10 dB (fader 1,0),
        0 dB w trzech czwartych drogi; pozostałe suwaki dalej do 0 dB."""
        from mostek.konwersje import poziom_float_na_db
        self.nacisnij("suwak", 1, 1.0)
        self.assertAlmostEqual(float(self.m(sciezki.fader(9))), 1.0, places=4)
        self.assertAlmostEqual(poziom_float_na_db(float(self.m(sciezki.fader(9)))), 10.0, places=2)
        self.nacisnij("suwak", 1, 0.75)
        self.assertAlmostEqual(poziom_float_na_db(float(self.m(sciezki.fader(9)))), 0.0, places=1)
        self.nacisnij("suwak", 1, 0.0)
        self.assertEqual(float(self.m(sciezki.fader(9))), 0.0)
        for pasek, kanal in ((2, 10), (3, 7), (4, 1)):
            self.nacisnij("suwak", pasek, 1.0)
            self.assertAlmostEqual(poziom_float_na_db(float(self.m(sciezki.fader(kanal)))), 0.0, places=2,
                                   msg=f"pasek {pasek}: góra = 0 dB")
        self.nacisnij("suwak", 9, 1.0)
        self.assertAlmostEqual(float(self.m(sciezki.MONITOR_POZIOM)), 0.75, places=4, msg="MASTER bez zmian")

    def test_silnik_suwaka_mikrofonu_wedlug_skali_plus_10(self):
        self.sym.wartosci[sciezki.fader(9)] = 1.0
        self.r.synchronizuj()
        self.assertAlmostEqual(self.pow.suwaki[1], 1.0, places=3)
        self.sym.wartosci[sciezki.fader(9)] = 0.75
        self.r.synchronizuj()
        self.assertAlmostEqual(self.pow.suwaki[1], 0.75, places=3)

    def test_opis_suwaka_mikrofonu(self):
        from mostek.logika import opis_fadera
        self.assertEqual(opis_fadera(self.u, 10.0, 10.0), "suwak w górze")
        self.assertEqual(opis_fadera(self.u, 0.0, 10.0), "suwak zero decybeli")
        self.assertEqual(opis_fadera(self.u, 0.0), "suwak w górze")

    def test_rec_paska_mikrofonu_przelacza_alarm_ciszy(self):
        """Michał 21.10.2026: REC paska 1 włącza i wyłącza alarm ciszy, bez
        zapisu do miksera i bez ruszania mikrofonu."""
        od = len(self.sym.dziennik)
        self.assertTrue(self.r.alarm_wlaczony)
        self.nacisnij("przycisk", 1, 0)
        self.assertFalse(self.r.alarm_wlaczony)
        self.assertEqual(self.slowa(), ["Alarm ciszy wyłączony"])
        self.nacisnij("przycisk", 1, 0)
        self.assertTrue(self.r.alarm_wlaczony)
        self.assertEqual(self.slowa(), ["Alarm ciszy włączony"])
        self.assertEqual(self.zapisy(od), [], "żadnego zapisu do miksera")
        self.assertFalse(self.suma("mikrofon"))

    def test_wylaczenie_zdejmuje_mikrofon_z_powrotow_programu(self):
        self.klawisz("F1_mikrofon")
        self.assertIn("mikrofon", self.slyszy("telefon"))
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        adresy = [a for a, _ in self.zapisy(od)]
        self.assertEqual(adresy[0], sciezki.lr(9), "najpierw antena")
        self.assertNotIn("mikrofon", self.slyszy("telefon"))
        self.assertNotIn("mikrofon", self.slyszy("zoom"))

    def test_nie_ufa_pamieci_tylko_odczytowi(self):
        # Inny klient włączył mikrofon, mostek tego jeszcze nie przetworzył:
        # decyduje ostatni POTWIERDZONY odczyt (wyłączony), więc mostek wysyła
        # jawne ON; mikser już ma ON, efekt idempotentny.
        self.sym.wartosci[sciezki.mute_szyny(6)] = 0
        self.r.synchronizuj()
        self.sym.wartosci[sciezki.lr(9)] = 1
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        self.assertIn((sciezki.lr(9), 1), self.zapisy(od))
        self.assertNotIn((sciezki.lr(9), 0), self.zapisy(od))
        self.assertTrue(self.suma("mikrofon"))

    def test_otwarcie_najpierw_wycisza_glosniki_i_potwierdza(self):
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        adresy = [a for a, _ in self.zapisy(od)]
        i_lr = adresy.index(sciezki.lr(9))
        self.assertLess(adresy.index(sciezki.mute_szyny(6)), i_lr)
        self.assertNotIn(sciezki.mute_szyny(5), adresy, "Bus 5 to klucz przyciszania, nie głośniki")
        zapytania = [z[2] for z in self.sym.zapytania]
        self.assertIn(sciezki.mute_szyny(6), zapytania)

    def test_glosniki_niewyciszone_mikrofon_zostaje_zamkniety(self):
        self.sym.awarie.ignoruj_zapis = {sciezki.mute_szyny(6)}
        self.klawisz("F1_mikrofon")
        self.assertFalse(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Mikrofon nie włączony, głośniki niewyciszone, mikrofon zamknięty"])

    def test_niepotwierdzone_wylaczenie_ostrzega(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.sym.awarie.ignoruj_zapis = {sciezki.lr(9)}
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Uwaga, mikrofon może być włączony"])

    def test_przy_cue_przelacznik_nie_otwiera_anteny(self):
        """Decyzja 6: przy dowolnym CUE przełącznik nie wpuszcza mikrofonu na antenę."""
        for r in ("telefon", "zoom"):
            with self.subTest(rozmowca=r):
                self.tearDown()
                self.setUp()
                self.cue(r)
                self.slowa()
                for zdarzenie in (("klawisz", "F1_mikrofon"), ("przycisk", 1, 3)):
                    od = len(self.sym.dziennik)
                    self.nacisnij(*zdarzenie)
                    self.assertEqual(self.zapisy(od), [])
                    self.assertFalse(self.suma("mikrofon"))
                    self.assertEqual(self.slowa(), ["Rozmowa poza anteną, najpierw zwolnij CUE"])

    def test_wylaczanie_dziala_zawsze_takze_przy_cue(self):
        """Mikrofon włączony z innego urządzenia w trakcie rozmowy: przełącznik go wyłącza."""
        self.cue("telefon")
        self.slowa()
        self.inny(sciezki.lr(9), 1)
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.assertFalse(self.suma("mikrofon"))
        self.assertIn("Mikrofon wyłączony", self.slowa())
        self.assertTrue(self.cue_sym("telefon"), "rozmowa trwa")

    def test_suwak_na_dole_to_nie_wylaczenie(self):
        self.sym.wartosci[sciezki.fader(9)] = 0.0
        self.r.synchronizuj()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.slowa(), ["Mikrofon włączony, suwak na dole"])


class TestMapaPaska(TestZSymulatorem):
    def test_solo_i_mute_wolne(self):
        """SOLO wolne wszędzie; MUTE wolne tylko na paskach muzyki."""
        for pasek in range(1, 7):
            for indeks in (1, 2):
                if pasek in (1, 2, 3) and indeks == 2:
                    continue
                od = len(self.sym.dziennik)
                self.nacisnij("przycisk", pasek, indeks)
                self.assertEqual(self.zapisy(od), [])
                self.assertEqual(self.slowa(), ["Przycisk wolny"])

    def test_rec_na_paskach_innych_niz_mikrofon(self):
        for pasek in range(2, 7):
            od = len(self.sym.dziennik)
            self.nacisnij("przycisk", pasek, 0)
            self.assertEqual(self.zapisy(od), [])
            self.assertEqual(self.slowa(), ["Na antenę wchodzi się suwakiem"])

    def test_select_bez_cue_nadal_mowi_komunikat(self):
        """Wariant ustawień bez_cue (SELECT mikrofonu bez przełącznika) zostaje."""
        self.u.paski[1] = dict(self.u.paski[1], select="bez_cue")
        od = len(self.sym.dziennik)
        self.nacisnij("przycisk", 1, 3)
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Mikrofon nie ma CUE, jest w każdej rozmowie"])

    def test_klawisze_f6_i_f7_wolne(self):
        for k in ("kursor_lewo_wolny", "kursor_prawo_wolny"):
            od = len(self.sym.dziennik)
            self.klawisz(k)
            self.assertEqual(self.zapisy(od), [])
            self.assertEqual(self.slowa(), ["Klawisz wolny"])

    def test_paski_wolne(self):
        self.nacisnij("przycisk", 7, 3)
        self.assertEqual(self.slowa(), ["Pasek wolny"])

    def test_diody_cue_i_mikrofonu(self):
        self.cue("telefon")
        self.assertIs(self.pow.diody[(2, 3)], True, "SELECT telefonu świeci przy CUE")
        self.assertIs(self.pow.diody[(1, 0)], True, "REC mikrofonu: alarm ciszy włączony")
        self.assertIs(self.pow.diody[(1, 3)], False, "SELECT mikrofonu: mikrofon poza anteną")
        self.assertIs(self.pow.diody[(2, 0)], False, "REC telefonu bez funkcji")


class TestStanNieznany(TestZSymulatorem):
    synchronizuj_na_starcie = False

    def test_start_bez_synchronizacji_wylacza(self):
        self.sym.wartosci[sciezki.lr(9)] = 1
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0, "przy NIEZNANY naciśnięcie zawsze wyłącza")
        mowa = self.slowa()
        self.assertEqual(mowa[0], "Stan był nieznany, wyłączam mikrofon")
        self.assertEqual(mowa[1], "Mikrofon wyłączony")

    def test_cue_przy_nieznanym_tylko_zamyka(self):
        self.sym.wartosci[sciezki.wysylka(9, 1)] = 0.75
        self.sym.wartosci[sciezki.tap(9, 1)] = 3
        self.cue("telefon")
        self.assertEqual(float(self.m(sciezki.wysylka(9, 1))), 0.0)
        self.assertTrue(all(float(v) == 0.0 for _, v in self.zapisy()), "żadnego otwarcia")
        self.assertEqual(self.slowa()[0], "Stan był nieznany, zamykam rozmowę ze słuchaczem")

    def test_f3_przy_nieznanym_tylko_zamyka(self):
        self.sym.wartosci[sciezki.wysylka(9, 3)] = 0.75
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(float(self.m(sciezki.wysylka(9, 3))), 0.0)
        self.assertTrue(all(float(v) == 0.0 for _, v in self.zapisy()))

    def test_start_nie_wysyla_nic_do_miksera(self):
        stan = dict(self.sym.wartosci)
        self.assertTrue(self.r.start())
        self.assertEqual(self.zapisy(), [], "start nie wysyła lokalnych wartości")
        self.assertEqual(self.sym.wartosci, stan)

    def test_brak_lacznosci_przy_starcie(self):
        self.sym.awarie.rozlaczony = True
        self.assertFalse(self.r.start())
        self.assertIn("Stan nieznany, mikrofon może być na antenie", self.slowa())
        self.nacisnij("galka", 2, 1)
        self.assertEqual(self.slowa(), ["Brak łączności z mikserem"])
        self.klawisz("F2_status")
        self.assertEqual(self.slowa(), ["Stan nieznany, mikrofon może być na antenie"])

    def test_nieznany_punkt_pobrania_daje_nieznany_cue(self):
        self.sym.wartosci[sciezki.wysylka(9, 1)] = 0.75
        self.sym.wartosci[sciezki.tap(9, 1)] = 1          # przed korekcją: spoza planu
        self.assertTrue(self.r.synchronizuj())
        from mostek.stan import NIEZNANY
        self.assertIs(self.r.widok.cue("telefon"), NIEZNANY)
        self.assertIs(self.r.widok.cue_zbior(), NIEZNANY)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0, "nieznane CUE blokuje antenę mikrofonu")


class TestCzekamNaMikser(TestZSymulatorem):
    def test_drugie_nacisniecie_w_trakcie_nie_przelacza(self):
        wejscie = threading.Event()
        zwolnij = threading.Event()
        oryginal = self.klient.ustaw

        def wolne_ustaw(adres, wartosc):
            wejscie.set()
            zwolnij.wait(2)
            return oryginal(adres, wartosc)

        self.klient.ustaw = wolne_ustaw
        w = threading.Thread(target=self.klawisz, args=("F1_mikrofon",))
        w.start()
        self.assertTrue(wejscie.wait(2))
        od = len(self.sym.dziennik)
        self.zegar.przesun(0.2)
        przyjete = self.r.zglos(("klawisz", "F1_mikrofon"))
        self.assertFalse(przyjete)
        zwolnij.set()
        w.join(2)
        self.assertTrue(self.suma("mikrofon"), "pierwsze naciśnięcie włączyło")
        self.assertNotIn((sciezki.lr(9), 0), self.zapisy(od), "drugie nie wyłączyło")
        self.assertIn("Czekam na mikser", self.slowa())

    def test_cue_w_trakcie_przejscia_czeka_na_mikser(self):
        wejscie = threading.Event()
        zwolnij = threading.Event()
        oryginal = self.klient.ustaw

        def wolne_ustaw(adres, wartosc):
            wejscie.set()
            zwolnij.wait(2)
            return oryginal(adres, wartosc)

        self.klient.ustaw = wolne_ustaw
        w = threading.Thread(target=self.cue, args=("telefon",))
        w.start()
        self.assertTrue(wejscie.wait(2))
        self.zegar.przesun(0.2)
        self.assertFalse(self.r.zglos(("przycisk", 2, 3)))
        zwolnij.set()
        w.join(2)
        self.assertTrue(self.cue_sym("telefon"), "drugie naciśnięcie nie zwolniło CUE")
        self.assertIn("Czekam na mikser", self.slowa())

    def test_okresowy_odczyt_nie_daje_czekam(self):
        self.r._wykonuje.acquire()
        zwolnienie = threading.Timer(0.05, self.r._wykonuje.release)
        zwolnienie.start()
        self.zegar.przesun(0.2)
        self.assertTrue(self.r.zglos(("klawisz", "F1_mikrofon")))
        zwolnienie.join()
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])

    def test_drganie_styku_ignorowane(self):
        # Przerwa między dwoma odczytami przesuwa sterowany zegar; tu badamy
        # samo drganie styku 10 ms po naciśnięciu.
        self.r.przerwa_odczytu = 0.0
        od = len(self.sym.dziennik)
        self.zegar.przesun(0.2)
        self.r.zglos(("klawisz", "F1_mikrofon"))
        self.zegar.przesun(0.01)
        self.assertFalse(self.r.zglos(("klawisz", "F1_mikrofon")))
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual([z for z in self.zapisy(od) if z[0] == sciezki.lr(9)], [(sciezki.lr(9), 1)])


class TestGlosniki(TestZSymulatorem):
    def test_wlaczenie_odrzucone_przy_otwartym_torze(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.klawisz("glosniki_wlacz")
        self.assertTrue(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Głośniki nie włączone, mikrofon ma otwarty tor"])

    def test_glosniki_wyciszone_przy_kazdym_cue(self):
        """Rozdz. 6a: każde CUE rozmówcy wycisza głośniki, włączenie odrzucone."""
        for r in ("telefon", "zoom"):
            with self.subTest(rozmowca=r):
                self.tearDown()
                self.setUp()
                self.assertFalse(self.glosniki_wyciszone())
                od = len(self.sym.dziennik)
                self.cue(r)
                adresy = [a for a, _ in self.zapisy(od)]
                b = self.u.odbiorcy[r].szyny[0]
                self.assertLess(adresy.index(sciezki.mute_szyny(6)), adresy.index(sciezki.wysylka(9, b)))
                self.assertTrue(self.glosniki_wyciszone())
                self.slowa()
                self.klawisz("glosniki_wlacz")
                self.assertTrue(self.glosniki_wyciszone())
                self.assertEqual(self.slowa(), ["Głośniki nie włączone, mikrofon ma otwarty tor"])

    def test_bez_mute_act_glosniki_zostaja_wyciszone(self):
        """Opcja wyłączona w ustawieniach: głośniki czekają na „Głośniki włącz”."""
        self.u.zachowanie["odciszaj_glosniki_po_wylaczeniu_mikrofonu"] = False
        self.klawisz("F1_mikrofon")
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.glosniki_wyciszone())
        self.assertEqual(self.slowa()[-1], "Mikrofon wyłączony")
        self.klawisz("glosniki_wlacz")
        self.assertFalse(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Głośniki włączone"])
        self.cue("telefon")
        self.klawisz("F3_koniec_rozmowy")
        self.assertTrue(self.glosniki_wyciszone())

    def test_po_f3_glosniki_mozna_wlaczyc(self):
        self.u.zachowanie["odciszaj_glosniki_po_wylaczeniu_mikrofonu"] = False
        self.cue("telefon")
        self.klawisz("F3_koniec_rozmowy")
        self.slowa()
        self.klawisz("glosniki_wlacz")
        self.assertFalse(self.glosniki_wyciszone())


class TestMuteAct(TestZSymulatorem):
    """Mute-Act jak w D&R (plan v22, rozdz. 6a, decyzja Michała z 17.10.2026):
    głośniki włączają się same po wyłączeniu mikrofonu i po zwolnieniu
    ostatniego CUE, tylko przy potwierdzonym braku toru mikrofonu i CUE."""

    def test_domyslnie_wlaczone(self):
        self.assertIs(self.u.zachowanie.get("odciszaj_glosniki_po_wylaczeniu_mikrofonu"), True)

    def test_po_wylaczeniu_mikrofonu(self):
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.glosniki_wyciszone())
        self.slowa()
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        adresy = [a for a, _ in self.zapisy(od)]
        self.assertLess(adresy.index(sciezki.lr(9)), adresy.index(sciezki.mute_szyny(6)),
                        "najpierw mikrofon z anteny, potem głośniki")
        self.assertFalse(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Głośniki włączone"])

    def test_po_f3(self):
        self.cue("telefon")
        self.cue("zoom")
        self.assertTrue(self.glosniki_wyciszone())
        self.slowa()
        self.klawisz("F3_koniec_rozmowy")
        self.assertFalse(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Koniec rozmowy. Słuchacz czeka. Zoom czeka. Głośniki włączone"])

    def test_po_select_ostatniego_cue(self):
        self.cue("telefon")
        self.cue("zoom")
        self.slowa()
        self.cue("telefon")                     # Zoom nadal w CUE
        self.assertTrue(self.glosniki_wyciszone(), "trwa CUE Zooma")
        self.assertEqual(self.slowa(), ["Słuchacz czeka"])
        self.cue("zoom")                        # ostatnie CUE
        self.assertFalse(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Zoom czeka. Głośniki włączone"])

    def test_po_suwaku_konczacym_ostatnie_cue(self):
        self.cue("telefon")
        self.slowa()
        self.ruch("telefon", 1.0)
        self.assertFalse(self.cue_sym("telefon"))
        self.assertFalse(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Słuchacz na antenie. Głośniki włączone"])

    def test_nie_przy_mikrofonie_na_antenie(self):
        """W trakcie CUE ktoś włączył mikrofon z innego urządzenia. Po F3
        mikrofon ma otwarty tor (antena), więc głośniki zostają wyciszone."""
        self.cue("telefon")
        self.inny(sciezki.lr(9), 1)
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.slowa()
        self.klawisz("F3_koniec_rozmowy")
        self.assertFalse(self.cue_sym("telefon"))
        self.assertTrue(self.glosniki_wyciszone())
        self.assertNotIn("Głośniki włączone", " ".join(self.slowa()))

    def test_nie_w_trakcie_kaszlu(self):
        self.klawisz("F1_mikrofon")
        self.nacisnij("przycisk", 1, 2)         # kaszel: mikrofon poza anteną
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertEqual(self.r._po_zamknieciu_mikrofonu(), "")
        self.assertTrue(self.glosniki_wyciszone(), "w trakcie kaszlu głośniki milczą")
        self.nacisnij("puszczenie", 1, 2)
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertTrue(self.glosniki_wyciszone())

    def test_nie_przy_stanie_nieznanym(self):
        self.cue("telefon")
        self.slowa()
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.assertEqual(self.r._po_zamknieciu_mikrofonu(), "")
        self.sym.awarie.rozlaczony = False
        self.assertTrue(self.glosniki_wyciszone())

    def test_nie_przy_blokujacym_profilu(self):
        """Mikrofon na antenie, z innego urządzenia szyna 3 na Main LR (profil
        blokuje). Wyłączenie mikrofonu działa, ale głośniki zostają wyciszone."""
        self.klawisz("F1_mikrofon")
        self.inny(sciezki.szyna_lr(3), 1)
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertTrue(self.glosniki_wyciszone(), "przy blokującym profilu głośniki zostają")
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony"])

    def test_glosniki_juz_wlaczone_bez_dopisku(self):
        """CUE bez wyciszonych głośników nie istnieje, ale wyłączenie mikrofonu
        przy włączonych (odciszonych z innego urządzenia) nie mówi nic więcej."""
        self.klawisz("F1_mikrofon")
        self.inny(sciezki.mute_szyny(6), 1)
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony"])

    def test_wylaczenie_zawsze(self):
        self.klawisz("glosniki_wylacz")
        self.assertTrue(self.glosniki_wyciszone())


if __name__ == "__main__":
    unittest.main()
