"""Przejścia z rozdziału 7 planu v20 i awarie w połowie (rozdz. 7 i 13).

Kolejność sprawdzana na dzienniku zapisów symulatora: CUE, zwolnienie CUE,
podniesienie i ściągnięcie suwaka rozmówcy, CUE przy mikrofonie i rozmówcy
na antenie, przytrzymany suwak, dwa CUE, F3.
"""

import unittest

from pomoc import TestZSymulatorem, sciezki


def indeks(adresy, adres, od_konca=False):
    if od_konca:
        return len(adresy) - 1 - adresy[::-1].index(adres)
    return adresy.index(adres)


class TestCue(TestZSymulatorem):
    def adresy(self, od):
        return [a for a, _ in self.zapisy(od)]

    def test_cue_telefonu_kolejnosc_zamknij_odczytaj_otworz(self):
        od = len(self.sym.dziennik)
        zap_przed = len(self.sym.zapytania)
        self.cue("telefon")
        adresy = self.adresy(od)
        otwarcie = indeks(adresy, sciezki.wysylka(9, 1), od_konca=True)
        # Zamknięcia (Main On telefonu, przyciszenie muzyki, podsłuch) przed otwarciem rozmowy.
        for zamk in (sciezki.lr(10), sciezki.wysylka(1, 1), sciezki.wysylka(10, 2)):
            self.assertLess(indeks(adresy, zamk), otwarcie, zamk)
        self.assertLess(indeks(adresy, sciezki.tap(9, 1)), otwarcie, "punkt pobrania przed otwarciem")
        # Głośniki wyciszone przed rozmową (rozdz. 6a).
        self.assertLess(indeks(adresy, sciezki.mute_szyny(6)), otwarcie)
        # Między zamknięciami a otwarciem są odczyty weryfikujące (dwa zgodne).
        zapytania = [z[2] for z in self.sym.zapytania[zap_przed:]]
        self.assertGreaterEqual(zapytania.count(sciezki.lr(10)), 3, "zapis + dwa odczyty")
        self.assertEqual(self.slowa(), ["Rozmowa poza anteną ze słuchaczem"])
        self.assertTrue(self.cue_sym("telefon"))
        self.assertEqual(self.slyszy("telefon"), {"mikrofon", "muzyka ciszej"})
        self.assertEqual(self.slyszy("zoom"), {"muzyka"}, "Zoom bez CUE nie słyszy rozmowy")
        self.assertEqual(self.m(sciezki.tap(9, 1)), sciezki.TAP_PRE)
        self.assertFalse(self.podsluch(), "telefon w obu uszach, podsłuch Bus 2 wyłączony")
        self.assertTrue(self.pfl("mikrofon") and self.pfl("telefon"))
        self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0, "bez przyciszenia (Michał 22.10.2026)")
        self.assertTrue(self.glosniki_wyciszone())

    def test_zwolnienie_cue_rozmowca_czeka_i_slyszy_antene(self):
        self.cue("telefon")
        self.slowa()
        od = len(self.sym.dziennik)
        self.cue("telefon")
        adresy = self.adresy(od)
        # Najpierw zamknięcie rozmowy, potem program, Main On na końcu.
        zamk = indeks(adresy, sciezki.wysylka(9, 1))
        self.assertEqual(self.zapisy(od)[zamk][1], 0.0)
        self.assertLess(zamk, indeks(adresy, sciezki.wysylka(1, 1)))
        self.assertLess(indeks(adresy, sciezki.wysylka(1, 1)), indeks(adresy, sciezki.lr(10)))
        self.assertEqual(self.slowa(), ["Słuchacz czeka. Głośniki włączone"])
        self.assertFalse(self.cue_sym("telefon"))
        self.assertEqual(self.slyszy("telefon"), {"muzyka"}, "czekający słyszy antenę na właściwej głośności")
        self.assertEqual(self.m(sciezki.lr(10)), 1, "suwak na dole: Main On wraca")
        self.assertTrue(self.podsluch(), "podsłuch prawego ucha wraca")
        self.assertFalse(self.pfl("telefon") or self.pfl("mikrofon"))
        self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0)

    def test_czekajacy_slyszy_mikrofon_na_antenie_za_suwakiem(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.tap(9, 1)), sciezki.TAP_POST)
        self.assertEqual(self.slyszy("telefon"), {"mikrofon", "muzyka"})
        self.ruch("mikrofon", 0.0)
        self.assertNotIn("mikrofon", self.slyszy("telefon"), "fade mikrofonu słychać u czekającego")

    def test_cue_przy_mikrofonie_na_antenie(self):
        """Decyzja 5: mikrofon najpierw z anteny (odczyt), dopiero potem rozmowa."""
        self.klawisz("F1_mikrofon")
        self.slowa()
        od = len(self.sym.dziennik)
        self.cue("zoom")
        adresy = self.adresy(od)
        self.assertEqual(adresy[0], sciezki.lr(9), "Main On mikrofonu OFF jako pierwszy krok")
        self.assertLess(0, indeks(adresy, sciezki.wysylka(9, 3), od_konca=True))
        self.assertEqual(self.slowa(), ["Mikrofon poza anteną, rozmowa z Zoomem"])
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertEqual(self.antena(), {"muzyka"})
        self.assertEqual(self.slyszy("zoom"), {"mikrofon", "muzyka ciszej"})
        self.assertEqual(self.slyszy("telefon"), {"muzyka"}, "telefon nie słyszy mikrofonu spoza anteny")

    def test_cue_przy_rozmowcy_na_antenie_main_on_przed_silnikiem(self):
        """Decyzja 4: Main On rozmówcy OFF (odczyt), potem silnik ściąga suwak."""
        self.ruch("zoom", 1.0)
        self.assertEqual(self.antena(), {"muzyka", "zoom"})
        self.slowa()
        od = len(self.sym.dziennik)
        self.cue("zoom")
        adresy = self.adresy(od)
        self.assertLess(indeks(adresy, sciezki.lr(7)), indeks(adresy, sciezki.fader(7)))
        self.assertLess(indeks(adresy, sciezki.lr(8)), indeks(adresy, sciezki.fader(8)))
        self.assertLess(indeks(adresy, sciezki.fader(7)), indeks(adresy, sciezki.wysylka(9, 3), od_konca=True))
        self.assertEqual(float(self.m(sciezki.fader(7))), 0.0)
        self.assertEqual(self.pow.suwaki[3], 0.0, "silnik X-TOUCH na dole")
        self.assertEqual(self.m(sciezki.lr(7)), 0)
        self.assertEqual(self.antena(), {"muzyka"})
        self.assertEqual(self.slowa(), ["Rozmowa poza anteną z Zoomem"])
        # Po zwolnieniu CUE Zoom czeka; Main On wraca, bo suwak jest na dole.
        self.cue("zoom")
        self.assertEqual(self.m(sciezki.lr(7)), 1)
        self.assertEqual(self.antena(), {"muzyka"}, "na antenę wraca dopiero ponownym podniesieniem")
        self.assertEqual(self.slowa(), ["Zoom czeka. Głośniki włączone"])
        self.ruch("zoom", 1.0)
        self.assertEqual(self.antena(), {"muzyka", "zoom"})
        self.assertEqual(self.slowa(), ["Zoom na antenie"])

    def test_cue_przy_przytrzymanym_suwaku(self):
        """Suwak w ręku: silnik go nie ściąga, kanał zostaje poza sumą do zejścia
        suwaka na dół i ponownego podniesienia (rozdz. 6)."""
        p = self.pasek("zoom")
        self.ruch("zoom", 1.0, puszczony=False)       # Michał trzyma suwak
        self.slowa()
        od = len(self.sym.dziennik)
        self.cue("zoom")
        self.assertNotIn(sciezki.fader(7), self.adresy(od), "silnik nie walczy z ręką")
        self.assertEqual(self.m(sciezki.lr(7)), 0, "kanał poza sumą mimo suwaka w górze")
        self.assertEqual(self.antena(), {"muzyka"})
        self.assertEqual(self.slowa(), ["Rozmowa poza anteną z Zoomem. Suwak trzymany, kanał poza sumą do ściągnięcia suwaka"])
        self.cue("zoom")                               # zwolnienie CUE, suwak dalej w górze
        self.assertEqual(self.m(sciezki.lr(7)), 0, "Main On wraca tylko przy suwaku na dole")
        self.assertEqual(self.antena(), {"muzyka"})
        self.assertEqual(self.slowa(), ["Zoom czeka poza sumą, ściągnij suwak na dół. Głośniki włączone"])
        self.nacisnij("suwak", p, 0.5)                 # ruch w górze nic nie otwiera
        self.tick(0.6)
        self.assertEqual(self.m(sciezki.lr(7)), 0)
        self.nacisnij("suwak", p, 0.0)                 # na dół: Main On wraca
        self.tick(0.6)
        self.assertEqual(self.m(sciezki.lr(7)), 1)
        self.assertEqual(self.slowa(), ["Zoom czeka"])
        self.nacisnij("suwak", p, 1.0)
        self.nacisnij("dotyk", p, False)
        self.tick(0.6)
        self.assertEqual(self.antena(), {"muzyka", "zoom"})
        self.assertEqual(self.slowa(), ["Zoom na antenie"])

    def test_dwa_cue_naraz_rozmowa_we_troje(self):
        self.cue("telefon")
        self.cue("zoom")
        self.assertEqual(self.slowa()[-1], "Rozmowa poza anteną ze słuchaczem i Zoomem")
        self.assertEqual(self.slyszy("telefon"), {"mikrofon", "zoom", "muzyka ciszej"})
        self.assertEqual(self.slyszy("zoom"), {"mikrofon", "telefon", "muzyka ciszej"})
        self.assertEqual(self.antena(), {"muzyka"})
        # Zoom i telefon słyszą się przed suwakiem.
        self.assertEqual(self.m(sciezki.tap(7, 1)), sciezki.TAP_PRE)
        self.assertEqual(self.m(sciezki.tap(10, 3)), sciezki.TAP_PRE)
        # Zwolnienie jednego: zostaje rozmowa z drugim, zwolniony czeka i słyszy antenę.
        self.cue("telefon")
        self.assertEqual(self.slowa()[-1], "Słuchacz czeka")
        self.assertEqual(self.slyszy("telefon"), {"muzyka"})
        self.assertEqual(self.slyszy("zoom"), {"mikrofon", "muzyka ciszej"})
        self.assertTrue(self.cue_sym("zoom"))

    def test_f3_zwalnia_wszystkie_cue(self):
        self.cue("telefon")
        self.cue("zoom")
        self.slowa()
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(self.slowa(), ["Koniec rozmowy. Słuchacz czeka. Zoom czeka. Głośniki włączone"])
        self.assertFalse(self.cue_sym("telefon") or self.cue_sym("zoom"))
        self.assertEqual(self.slyszy("telefon"), {"muzyka"})
        self.assertEqual(self.slyszy("zoom"), {"muzyka"})
        self.assertTrue(self.podsluch())
        self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0)

    def test_mikrofon_w_rozmowie_jak_na_antenie(self):
        """Michał 22.10.2026: rozmówca na CUE słyszy mikrofon tak głośno jak
        antena. Wysyłka przed suwakiem dostaje poziom bazowy plus poziom
        suwaka mikrofonu (0 dB w symulatorze, potem +10 dB), także po ruchu
        suwaka w trakcie rozmowy; po CUE wysyłka znika."""
        from mostek.konwersje import poziom_float_na_db
        db = lambda k, b: poziom_float_na_db(float(self.m(sciezki.wysylka(k, b))))
        self.cue("telefon")
        self.assertEqual(self.m(sciezki.tap(9, 1)), sciezki.TAP_PRE)
        self.assertAlmostEqual(db(9, 1), 0.0, places=1, msg="suwak mikrofonu 0 dB")
        self.nacisnij("dotyk", 1, True)
        self.nacisnij("suwak", 1, 1.0)               # mikrofon +10 dB
        self.nacisnij("dotyk", 1, False)
        self.czekaj(1.0)
        self.assertAlmostEqual(db(9, 1), 10.0, places=1, msg="rozmówca słyszy +10 jak antena")
        self.cue("zoom")
        self.assertAlmostEqual(db(9, 3), 10.0, places=1)
        self.assertAlmostEqual(db(9, 4), 10.0, places=1)
        self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0, "słuchawki bez przyciszenia")
        self.nacisnij("dotyk", 1, True)
        self.nacisnij("suwak", 1, 0.5)               # niżej: rozmowa idzie za suwakiem
        self.nacisnij("dotyk", 1, False)
        self.czekaj(1.0)
        f = poziom_float_na_db(float(self.m(sciezki.fader(9))))
        self.assertAlmostEqual(db(9, 1), f, places=1)
        self.assertAlmostEqual(db(9, 3), f, places=1)
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(float(self.m(sciezki.wysylka(9, 1))), 0.0)
        self.assertEqual(float(self.m(sciezki.wysylka(9, 3))), 0.0)
        self.assertEqual(self.u.poziom_bazowy("mikrofon", "telefon"), 0.0, "korekta nie zmienia poziomu bazowego")

    def test_program_w_sluchawkach_przy_cue(self):
        """Michał 22.10.2026: przy CUE w słuchawkach gra muzyka z anteny. Pomiar
        na MR18: solo Main LR nie dodaje sumy do PHONES, więc mostek daje PFL
        muzyce na antenie, tylko na czas rozmowy; muzyka poza anteną bez PFL."""
        self.u.zachowanie["program_w_sluchawkach_przy_cue"] = True   # domyślnie wyłączone (Michał 22.10.2026)
        self.inny(sciezki.lr(3), 0)
        self.inny(sciezki.lr(4), 0)                  # muzyka 2 poza anteną
        na = [z for z in ("muzyka1", "muzyka2", "muzyka3") if self.suma(z)]
        self.assertIn("muzyka1", na)
        self.cue("zoom")
        for z in na:
            self.assertTrue(self.pfl(z), f"{z} w słuchawkach przy CUE")
        self.assertFalse(self.pfl("muzyka2"), "muzyka poza anteną bez PFL")
        self.assertEqual(self.m(sciezki.SOLO_MAIN_LR), 0, "solo LR nie działa na MR18, wyłączone")
        self.assertEqual(self.m(sciezki.MONITOR_ZRODLO), sciezki.ZRODLO_LRPFL)
        self.inny(sciezki.lr(3), 1)
        self.inny(sciezki.lr(4), 1)                  # muzyka 2 wchodzi w trakcie rozmowy
        self.tick()
        self.assertTrue(self.pfl("muzyka2"), "muzyka weszła na antenę: też w słuchawkach")
        self.inny(sciezki.lr(1), 0)
        self.inny(sciezki.lr(2), 0)
        self.tick()
        self.assertFalse(self.pfl("muzyka1"), "muzyka zeszła z anteny: bez PFL")
        self.cue("telefon")
        self.klawisz("F3_koniec_rozmowy")
        for z in ("muzyka1", "muzyka2", "muzyka3"):
            self.assertFalse(self.pfl(z), f"{z}: po rozmowie PFL wyłączony")
        self.cue("telefon")
        self.assertTrue(self.pfl("muzyka2"))
        self.klawisz("sluchaj_programu")
        self.assertFalse(self.pfl("muzyka2"))

    def test_program_przy_cue_wylaczony_w_ustawieniach(self):
        self.u.zachowanie["program_w_sluchawkach_przy_cue"] = False
        self.cue("zoom")
        for z in ("muzyka1", "muzyka2", "muzyka3"):
            self.assertFalse(self.pfl(z))

    def test_mikrofon_w_rozmowie_wylaczone_w_ustawieniach(self):
        from mostek.konwersje import poziom_float_na_db
        self.u.zachowanie["mikrofon_w_rozmowie_jak_na_antenie"] = False
        self.sym.wartosci[sciezki.fader(9)] = 1.0
        self.r.synchronizuj()
        self.cue("telefon")
        self.assertAlmostEqual(poziom_float_na_db(float(self.m(sciezki.wysylka(9, 1)))), 0.0, places=1)

    def test_f3_bez_rozmowy(self):
        od = len(self.sym.dziennik)
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Nie ma rozmowy poza anteną"])

    def test_cue_muzyki_tylko_pfl(self):
        """Decyzja 7: SELECT muzyki to tylko PFL dla Michała."""
        od = len(self.sym.dziennik)
        self.nacisnij("przycisk", 4, 3)
        self.assertEqual([a for a, _ in self.zapisy(od)], [sciezki.solo(1), sciezki.solo(2)])
        self.assertTrue(self.pfl("muzyka1"))
        self.assertEqual(self.slyszy("telefon"), {"muzyka"})
        self.assertEqual(self.slowa(), ["Odsłuch kontrolny, Muzyka 1, włączony"])


class TestSuwakRozmowcy(TestZSymulatorem):
    def test_podniesienie_najpierw_antena_potem_powroty(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        od = len(self.sym.dziennik)
        self.ruch("telefon", 1.0)
        adresy = [a for a, _ in self.zapisy(od)]
        self.assertLess(indeks(adresy, sciezki.fader(10)), indeks(adresy, sciezki.wysylka(10, 3)))
        self.assertEqual(self.slowa(), ["Słuchacz na antenie"])
        self.assertEqual(self.antena(), {"mikrofon", "telefon", "muzyka"})
        self.assertEqual(self.slyszy("zoom"), {"mikrofon", "telefon", "muzyka"})
        self.assertEqual(self.m(sciezki.tap(10, 3)), sciezki.TAP_POST, "program za suwakiem")
        self.assertFalse(self.podsluch(), "telefon na antenie: obu uszy z programu")

    def test_sciagniecie_najpierw_powroty(self):
        self.ruch("telefon", 1.0)
        self.slowa()
        od = len(self.sym.dziennik)
        self.ruch("telefon", 0.0)
        zapisy = self.zapisy(od)
        adresy = [a for a, _ in zapisy]
        self.assertLess(indeks(adresy, sciezki.fader(10)), indeks(adresy, sciezki.wysylka(10, 3)))
        self.assertEqual(dict(zapisy)[sciezki.wysylka(10, 3)], 0.0)
        self.assertEqual(self.slowa(), ["Słuchacz czeka"])
        self.assertEqual(self.slyszy("zoom"), {"muzyka"})
        self.assertTrue(self.podsluch(), "czeka: znowu w prawym uchu")

    def test_podniesienie_przy_main_on_wylaczonym_z_innego_urzadzenia(self):
        """Rozmówca poza sumą (np. z AOSC): podniesienie suwaka nie wpuszcza na
        antenę i NVDA mówi, co zrobić; zejście na dół przywraca Main On."""
        self.inny(sciezki.lr(10), 0)
        self.assertIn("Słuchacz czeka poza sumą, suwak na dole z innego urządzenia", self.slowa())
        self.ruch("telefon", 1.0)
        self.assertEqual(self.m(sciezki.lr(10)), 0)
        self.assertEqual(self.antena(), {"muzyka"})
        self.assertEqual(self.slowa(), ["Słuchacz czeka poza sumą, ściągnij suwak na dół"])
        self.ruch("telefon", 0.0)
        self.assertEqual(self.m(sciezki.lr(10)), 1)
        self.assertEqual(self.slowa(), ["Słuchacz czeka"])
        self.ruch("telefon", 1.0)
        self.assertEqual(self.antena(), {"muzyka", "telefon"})

    def test_prog_suwaka_z_pliku_ustawien(self):
        self.u.zachowanie["prog_suwaka_na_antenie_db"] = -20.0
        # Poziom około -36 dB: powyżej -50, ale poniżej progu -20 z ustawień.
        self.ruch("telefon", 0.2)
        self.assertEqual(self.r.widok.stan_rozmowcy("telefon"), "czeka")
        self.assertNotIn("telefon", self.slyszy("zoom"), "poniżej progu powrót nie bierze telefonu")

    def test_suwaki_muzyki_zawsze_czynne_i_fade_u_rozmowcy(self):
        self.nacisnij("dotyk", 4, True)
        self.nacisnij("suwak", 4, 0.0)
        self.tick(0.6)
        self.assertNotIn("muzyka", self.slyszy("telefon"), "ściszona muzyka ściszona też w powrocie")


class TestAwariaWPolowie(TestZSymulatorem):
    def test_zamkniecie_nieprzyjete_przejscie_niepelne_bez_otwarcia(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.sym.awarie.ignoruj_zapis = {sciezki.lr(9)}
        od = len(self.sym.dziennik)
        self.cue("telefon")
        self.assertEqual(self.slowa(), ["Przejście niepełne, prywatność niepotwierdzona"])
        adresy = [a for a, _ in self.zapisy(od)]
        self.assertGreaterEqual(adresy.count(sciezki.lr(9)), 2, "ponowione brakujące zamknięcie")
        self.assertEqual(adresy.count(sciezki.lr(10)), 1, "potwierdzone zamknięcie nie jest ponawiane")
        self.assertFalse(self.cue_sym("telefon"), "żadnej nowej drogi rozmowy")
        self.assertEqual(int(self.m(sciezki.tap(9, 1))), sciezki.TAP_POST)
        self.assertNotIn(sciezki.tap(9, 1), adresy, "otwarcia nie zaczęto")
        # Bez automatycznego powrotu do dawnego stanu publicznego.
        self.assertEqual(self.m(sciezki.lr(10)), 0)

    def test_utrata_lacznosci_w_trakcie_zamykania(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.sym.awarie.rozlacz_po_zapisach = 2
        self.cue("telefon")
        self.assertFalse(self.r.stan.polaczony)
        mowa = self.slowa()
        self.assertIn("Brak łączności z mikserem, stan mikrofonu nieznany", mowa)
        self.assertNotIn("Mikrofon poza anteną, rozmowa ze słuchaczem", mowa)
        self.assertFalse(self.cue_sym("telefon"), "nic nie otwarto")

    def test_nieudane_otwarcie_zamyka_otwarte(self):
        self.cue("telefon")
        self.slowa()
        # Dołączenie Zooma: mikrofon do Zooma otworzy się, telefon do Zooma nie.
        # Szyny 3/4 są linkowane (jeden poziom pary), więc mikser odrzuca obie.
        self.sym.awarie.ignoruj_zapis = {sciezki.wysylka(10, 3), sciezki.wysylka(10, 4)}
        self.cue("zoom")
        self.assertEqual(self.slowa(), ["Przejście niepełne, prywatność niepotwierdzona"])
        self.assertEqual(float(self.m(sciezki.wysylka(10, 3))), 0.0, "wycofane")
        self.assertEqual(float(self.m(sciezki.wysylka(9, 3))), 0.0, "wycofane")
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_utrata_w_rozmowie_i_przycisk_cue_tylko_zamyka(self):
        self.cue("telefon")
        self.slowa()
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.assertEqual(self.slowa(), ["Brak łączności z mikserem, stan mikrofonu nieznany"])
        self.sym.awarie.rozlaczony = False
        # Bez synchronizacji mostek nie zna stanu: CUE tylko zamyka rozmowę.
        od = len(self.sym.dziennik)
        self.cue("telefon")
        zapisy = self.zapisy(od)
        self.assertTrue(zapisy, "próba zamknięcia")
        self.assertTrue(all(float(v) == 0.0 for _, v in zapisy), zapisy)
        self.assertEqual(self.slowa()[0], "Stan był nieznany, zamykam rozmowę ze słuchaczem")
        self.assertFalse(self.cue_sym("telefon"))

    def test_scena_z_innego_klienta_przerywa_przejscie(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        oryginal = self.r._dwa_odczyty

        def z_obca_scena(oczek):
            self.transport.rozeslij(self.sym.wczytaj_scene_z_innego({}))
            self.r._dwa_odczyty = oryginal
            return oryginal(oczek)

        self.r._dwa_odczyty = z_obca_scena
        self.cue("telefon")
        mowa = self.slowa()
        self.assertEqual(mowa[0], "Przejście przerwane, zmiana z innego urządzenia")
        self.assertFalse(self.cue_sym("telefon"), "po obcej scenie bez otwierania nowych dróg")
        self.assertEqual(self.m(sciezki.lr(9)), 0, "zamknięcie zostaje")

    def test_reconnect_bez_nadpisywania_miksera(self):
        self.klawisz("F1_mikrofon")
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.slowa()
        self.sym.wartosci[sciezki.lr(9)] = 0
        self.sym.wartosci[sciezki.fader(1)] = 0.3
        self.sym.wartosci[sciezki.fader(2)] = 0.3
        self.sym.awarie.rozlaczony = False
        od = len(self.sym.dziennik)
        self.tick(1.5)
        self.assertTrue(self.r.stan.polaczony)
        self.assertEqual(self.zapisy(od), [], "reconnect nie wysyła starych wartości")
        mowa = self.slowa()
        self.assertTrue(mowa[-1].startswith("Łączność z mikserem przywrócona"), mowa)
        self.assertIn("Mikrofon wyłączony", mowa[-1])
        self.assertAlmostEqual(self.pow.suwaki[4], 0.3 / 0.75, places=3, msg="silnik według odczytu")

    def test_utrata_po_otwarciu_mikrofonu(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.assertEqual(self.slowa(), ["Brak łączności z mikserem, stan mikrofonu nieznany"])
        self.klawisz("F2_status")
        self.assertEqual(self.slowa(), ["Stan nieznany, mikrofon może być na antenie"])
        self.klawisz("F1_mikrofon")
        mowa = self.slowa()
        self.assertEqual(mowa[0], "Stan był nieznany, wyłączam mikrofon")
        self.assertEqual(mowa[-1], "Uwaga, mikrofon może być włączony")
        self.assertEqual(self.m(sciezki.lr(9)), 1, "symulator był rozłączony, nic nie dotarło")


if __name__ == "__main__":
    unittest.main()
