"""Mechanizmy z konsolet D&R (plan v21) i przyciszanie słuchacza (plan v22).

Podniesienie suwaka rozmówcy z CUE, przycisk kaszlu, liczniki czasu z polską
odmianą, alarm ciszy z mierników, klucz przyciszania (Bus 5) przy przejściach,
głośniki mono (Bus 6). Wszystko na symulatorze, nie na MR18.
"""

import unittest

from pomoc import TestZSymulatorem, sciezki
from mostek.liczniki import czas_slownie, odmiana, MINUTA, SEKUNDA, GODZINA
from mostek.mierniki import DetektorCiszy, db_na_int16, dekoduj_blok, koduj_blok, poziom_lr
from mostek.xtouch import AtrapaPortuMIDI, MapaMC, PowierzchniaXTouch


def indeks(adresy, adres, od_konca=False):
    if od_konca:
        return len(adresy) - 1 - adresy[::-1].index(adres)
    return adresy.index(adres)


# =============================================================================
# 1. Podniesienie suwaka rozmówcy z CUE (plan v21, pkt 1; decyzja 1)
# =============================================================================
class TestSuwakKonczyCue(TestZSymulatorem):
    def adresy(self, od):
        return [a for a, _ in self.zapisy(od)]

    def test_kolejnosc_rozmowa_program_main_on(self):
        """Najpierw zamknięcie dróg rozmowy do szyny słuchacza, potem powrót
        programu, na końcu Main On słuchacza."""
        self.cue("telefon")
        self.slowa()
        self.assertTrue(self.cue_sym("telefon"))
        od = len(self.sym.dziennik)
        self.ruch("telefon", 1.0)
        zapisy = self.zapisy(od)
        adresy = [a for a, _ in zapisy]
        zamk = indeks(adresy, sciezki.wysylka(9, 1))
        self.assertEqual(zapisy[zamk][1], 0.0, "mikrofon przed suwakiem zamknięty")
        program = indeks(adresy, sciezki.wysylka(1, 1))      # muzyka bez przyciszenia
        main_on = indeks(adresy, sciezki.lr(10))
        self.assertLess(zamk, program)
        self.assertLess(program, main_on)
        self.assertEqual(self.slowa(), ["Słuchacz na antenie. Głośniki włączone"])
        self.assertFalse(self.cue_sym("telefon"))
        self.assertEqual(self.antena(), {"muzyka", "telefon"})
        self.assertEqual(self.slyszy("telefon"), {"muzyka"}, "słyszy antenę bez siebie")
        self.assertIn("telefon", self.slyszy("zoom"))
        self.assertFalse(self.podsluch())
        self.assertFalse(self.pfl("telefon") or self.pfl("mikrofon"), "PFL rozmowy zgaszone")

    def test_zoom_na_antenie(self):
        self.cue("zoom")
        self.slowa()
        self.ruch("zoom", 1.0)
        self.assertEqual(self.slowa(), ["Zoom na antenie. Głośniki włączone"])
        self.assertEqual(self.antena(), {"muzyka", "zoom"})
        self.assertEqual(self.m(sciezki.lr(7)), 1)
        self.assertEqual(self.m(sciezki.lr(8)), 1)

    def test_drugi_uczestnik_cue_zostaje(self):
        self.cue("telefon")
        self.cue("zoom")
        self.slowa()
        self.ruch("zoom", 1.0)
        self.assertEqual(self.slowa(), ["Zoom na antenie"])
        self.assertTrue(self.cue_sym("telefon"), "słuchacz zostaje w rozmowie poza anteną")
        self.assertFalse(self.cue_sym("zoom"))
        self.assertEqual(self.slyszy("telefon"), {"mikrofon", "muzyka ciszej"},
                         "słuchacz z CUE nie słyszy Zooma na antenie")
        self.assertEqual(self.slyszy("zoom"), {"muzyka"}, "Zoom nie słyszy rozmowy")
        self.assertEqual(self.antena(), {"muzyka", "zoom"})
        # Fader Start kończy również pozostałe CUE słuchacza.
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertFalse(self.cue_sym("telefon"))
        self.assertEqual(self.slowa(), ["Mikrofon włączony, koniec rozmowy"])
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_ostatni_cue_odblokowuje_przelacznik_mikrofonu(self):
        self.cue("telefon")
        self.slowa()
        self.ruch("telefon", 1.0)
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])
        self.assertEqual(self.antena(), {"mikrofon", "muzyka", "telefon"})

    def test_suwak_trzymany_od_wejscia_w_cue_nie_wpuszcza(self):
        """Wariant bezpieczniejszy dla anteny: liczy się podniesienie z dołu.
        Suwak, którego silnik nie ściągnął (trzymany ręką), nie kończy CUE ruchem w górze."""
        p = self.pasek("zoom")
        self.ruch("zoom", 1.0, puszczony=False)
        self.cue("zoom")
        self.slowa()
        self.nacisnij("suwak", p, 0.9)
        self.tick(0.6)
        self.assertTrue(self.cue_sym("zoom"))
        self.assertEqual(self.m(sciezki.lr(7)), 0)
        self.nacisnij("suwak", p, 0.0)
        self.tick(0.6)
        self.nacisnij("suwak", p, 1.0)
        self.nacisnij("dotyk", p, False)
        self.tick(0.6)
        self.assertFalse(self.cue_sym("zoom"))
        self.assertEqual(self.antena(), {"muzyka", "zoom"})

    def test_suwak_ponizej_progu_nie_konczy_cue(self):
        self.cue("telefon")
        self.slowa()
        self.ruch("telefon", 0.05)          # poniżej progu -50 dB
        self.assertTrue(self.cue_sym("telefon"))
        self.assertEqual(self.m(sciezki.lr(10)), 0)

    def test_niepelne_przejscie_bez_main_on(self):
        self.cue("telefon")
        self.slowa()
        self.sym.awarie.ignoruj_zapis = {sciezki.wysylka(9, 1)}
        self.ruch("telefon", 1.0)
        self.assertEqual(self.slowa(), ["Przejście niepełne, prywatność niepotwierdzona"])
        self.assertEqual(self.m(sciezki.lr(10)), 0, "bez potwierdzonego zamknięcia rozmowy brak anteny")
        self.assertEqual(self.naruszenia_miksera(), [])


# =============================================================================
# 2. Przycisk kaszlu: MUTE paska mikrofonu (plan v21, pkt 2; decyzja 2)
# =============================================================================
class TestKaszel(TestZSymulatorem):
    def wcisnij(self):
        self.nacisnij("przycisk", 1, 2)

    def pusc(self):
        self.nacisnij("puszczenie", 1, 2)

    def na_antene(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.slowa()

    def test_trzymanie_zdejmuje_puszczenie_przywraca(self):
        self.na_antene()
        self.wcisnij()
        self.assertEqual(self.m(sciezki.lr(9)), 0, "mikrofon poza anteną na czas trzymania")
        self.assertNotIn("mikrofon", self.slyszy("telefon"), "kaszel nie idzie do rozmówców")
        self.assertTrue(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), [], "w trakcie kaszlu NVDA milczy")
        self.assertIs(self.pow.diody[(1, 2)], True, "dioda MUTE świeci w trakcie kaszlu")
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertNotIn(sciezki.mute_szyny(6), [a for a, _ in self.zapisy(od)],
                         "głośniki były wyciszone cały czas, bez ponownego wyciszania")
        self.assertIn("mikrofon", self.slyszy("telefon"))
        self.assertEqual(self.slowa(), [], "powrót też bez komunikatu")
        self.assertIsNone(self.r._kaszel)

    def test_status_w_trakcie_kaszlu(self):
        self.na_antene()
        self.wcisnij()
        self.klawisz("F2_status")
        self.assertTrue(self.slowa()[0].startswith("Mikrofon poza anteną na czas kaszlu"))

    def test_kaszel_przy_mikrofonie_poza_antena_nic_nie_robi(self):
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.pusc()
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertEqual(self.slowa(), [])

    def test_kaszel_przy_cue_nie_otwiera_anteny(self):
        """Kaszel zamyka rozmowę, ale puszczenie nie otwiera anteny."""
        self.na_antene()
        self.cue("telefon")
        self.slowa()
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertFalse(self.wysylka("mikrofon", "telefon"))
        self.pusc()
        self.assertTrue(self.wysylka("mikrofon", "telefon"))
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertEqual(self.slowa(), [])

    def test_cue_w_trakcie_kaszlu_puszczenie_nie_otwiera(self):
        self.na_antene()
        self.wcisnij()
        self.cue("telefon")
        self.assertEqual(self.slowa(), ["Mikrofon poza anteną, rozmowa ze słuchaczem"])
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertTrue(self.cue_sym("telefon"))
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_zgubione_puszczenie_restart_kontrolera(self):
        self.na_antene()
        self.wcisnij()
        self.nacisnij("kontroler", "restart X-TOUCH")
        self.assertEqual(self.slowa(), ["Kaszel przerwany, mikrofon poza anteną",
                                        "Kontroler odłączony, stół tylko zamyka tory"])
        self.pusc()                          # spóźnione puszczenie po restarcie
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertEqual(self.slowa(), [])

    def test_zgubione_puszczenie_port_midi_zamkniety(self):
        port = AtrapaPortuMIDI()
        self.r.powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), port, self.r.zglos)
        self.na_antene()
        port.wstrzyknij(0x90, 0x10, 0x7F)    # MUTE paska 1 wciśnięty
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        port.przy_zamknieciu()               # X-TOUCH odłączony
        self.assertEqual(self.slowa(), ["Kaszel przerwany, mikrofon poza anteną",
                                        "Kontroler odłączony, stół tylko zamyka tory"])
        self.assertEqual(self.m(sciezki.lr(9)), 0)

    def test_puszczenie_przez_midi(self):
        port = AtrapaPortuMIDI()
        self.r.powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), port, self.r.zglos)
        self.na_antene()
        port.wstrzyknij(0x90, 0x10, 0x7F)
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.zegar.przesun(0.2)
        port.wstrzyknij(0x90, 0x10, 0x00)    # Note On z prędkością 0 = puszczenie
        self.assertEqual(self.m(sciezki.lr(9)), 1)

    def test_zgubione_puszczenie_utrata_lacznosci(self):
        self.na_antene()
        self.wcisnij()
        self.sym.awarie.rozlaczony = True
        self.tick()
        mowa = self.slowa()
        self.assertIn("Kaszel przerwany, zamknięcie mikrofonu niepotwierdzone", mowa)
        self.sym.awarie.rozlaczony = False
        self.tick(1.5)
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 0, "po NIEZNANY mikrofon zostaje poza anteną")

    def test_dlugie_trzymanie_nie_przerywa_kaszlu(self):
        self.u.zachowanie["kaszel_maks_s"] = 5.0
        self.na_antene()
        self.wcisnij()
        self.assertEqual(self.czekaj(120.0), [])
        self.assertIsNotNone(self.r._kaszel)
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 1)

    def test_przelacznik_w_trakcie_kaszlu_wylacza(self):
        self.na_antene()
        self.wcisnij()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Głośniki włączone"])
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 0, "puszczenie po wyłączeniu nie otwiera")

    def test_glosniki_odciszone_z_innego_w_trakcie_kaszlu(self):
        self.na_antene()
        self.wcisnij()
        self.inny(sciezki.mute_szyny(6), 1)
        self.slowa()
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 0, "zapora sprawdza wyciszenie także po kaszlu")
        self.assertEqual(self.slowa(), ["Mikrofon nie włączony, głośniki niewyciszone, mikrofon zamknięty"])

    def test_glosniki_nie_wlaczaja_sie_w_trakcie_kaszlu(self):
        self.na_antene()
        self.wcisnij()
        self.klawisz("glosniki_wlacz")
        self.assertTrue(self.glosniki_wyciszone())

    def test_kaszel_przy_sluchaczu_na_antenie_zdejmuje_mikrofon_z_klucza(self):
        self.na_antene()
        self.ruch("telefon", 1.0)
        self.assertEqual(self.w_kluczu(), {"mikrofon"})
        self.wcisnij()
        self.assertEqual(self.w_kluczu(), set(), "kaszel nie ścisza słuchacza")
        self.pusc()
        self.assertEqual(self.w_kluczu(), {"mikrofon"})

    def test_licznik_mikrofonu_po_kaszlu_liczy_od_nowa(self):
        """Decyzja Michała z 18.10.2026 (P01): licznik mikrofonu podaje czas
        nieprzerwanego stanu antenowego, więc po kaszlu zaczyna od ponownego
        potwierdzenia Main On, a nie od pierwszego włączenia."""
        self.na_antene()
        self.czekaj(30.0)
        self.wcisnij()
        self.czekaj(2.0)
        self.pusc()
        self.czekaj(5.0)
        self.klawisz("F2_status")
        tekst = self.slowa()[0]
        self.assertTrue(tekst.startswith("Mikrofon na antenie od 5 sekund. "), tekst)


# =============================================================================
# 3. Liczniki czasu (plan v21, pkt 3; decyzja 3)
# =============================================================================
class TestOdmiana(unittest.TestCase):
    def test_mianownik(self):
        for n, f in ((1, "minuta"), (2, "minuty"), (4, "minuty"), (5, "minut"), (11, "minut"), (12, "minut"),
                     (14, "minut"), (21, "minut"), (22, "minuty"), (24, "minuty"), (25, "minut"), (102, "minuty"),
                     (112, "minut"), (0, "minut")):
            self.assertEqual(odmiana(n, MINUTA), f, n)
        self.assertEqual(odmiana(3, SEKUNDA), "sekundy")
        self.assertEqual(odmiana(13, SEKUNDA), "sekund")
        self.assertEqual(odmiana(1, GODZINA), "godzina")

    def test_po_przyimku_od(self):
        self.assertEqual(czas_slownie(130), "2 minut 10 sekund")
        self.assertEqual(czas_slownie(40), "40 sekund")
        self.assertEqual(czas_slownie(61), "1 minuty 1 sekundy")
        self.assertEqual(czas_slownie(62), "1 minuty 2 sekund")
        self.assertEqual(czas_slownie(120), "2 minut")
        self.assertEqual(czas_slownie(3600 + 5 * 60 + 7), "1 godziny 5 minut")
        self.assertEqual(czas_slownie(0.4), "")

    def test_mianownik_calosc(self):
        self.assertEqual(czas_slownie(130, "mianownik"), "2 minuty 10 sekund")
        self.assertEqual(czas_slownie(61, "mianownik"), "1 minuta 1 sekunda")
        self.assertEqual(czas_slownie(22 * 60 + 25, "mianownik"), "22 minuty 25 sekund")
        self.assertEqual(czas_slownie(12 * 60 + 13, "mianownik"), "12 minut 13 sekund")


class TestLiczniki(TestZSymulatorem):
    def test_status_z_czasem_od_potwierdzonej_zmiany(self):
        self.klawisz("F1_mikrofon")
        self.cue("zoom")
        self.cue("zoom")             # Zoom czeka, mikrofon poza anteną
        self.klawisz("F1_mikrofon")  # mikrofon na antenie od teraz
        self.czekaj(40.0)
        self.ruch("telefon", 1.0)    # słuchacz na antenie od teraz
        self.czekaj(90.0)
        self.slowa()
        self.klawisz("F2_status")
        tekst = self.slowa()[0]
        self.assertTrue(tekst.startswith("Mikrofon na antenie od 2 minut 11 sekund. "
                                         "Słuchacz na antenie od 1 minuty 30 sekund. "
                                         "Zoom czeka od 2 minut 11 sekund."), tekst)

    def test_po_starcie_poczatek_nieznany_bez_czasu(self):
        self.czekaj(100.0)
        self.klawisz("F2_status")
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Słuchacz czeka. Zoom czeka. Głośniki włączone."])
        self.cue("telefon")
        self.czekaj(5.0)
        self.slowa()
        self.klawisz("F2_status")
        self.assertIn("Słuchacz w rozmowie poza anteną od 5 sekund", self.slowa()[0])

    def test_galka_paska_podaje_czas(self):
        self.cue("telefon")
        self.czekaj(65.0)
        self.nacisnij("galka_wcisnij", 2)
        self.assertEqual(self.slowa(), ["Słuchacz w rozmowie poza anteną od 1 minuty 5 sekund, suwak na dole. "
                                        "Telefon, wzmocnienie zero"])

    def test_utrata_lacznosci_kasuje_liczniki(self):
        self.klawisz("F1_mikrofon")
        self.czekaj(20.0)
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.sym.awarie.rozlaczony = False
        self.tick(1.5)
        self.slowa()
        self.klawisz("F2_status")
        self.assertTrue(self.slowa()[0].startswith("Mikrofon włączony. "), "po powrocie łączności bez czasu")

    def test_przypomnienie_domyslnie_wylaczone(self):
        self.assertEqual(self.u.przypomnienie_mikrofonu_min, 0)
        self.klawisz("F1_mikrofon")
        self.slowa()
        mowa = self.czekaj(25 * 60.0)
        self.assertEqual(mowa, [], "liczniki nie mówią same")

    def test_przypomnienie_co_n_minut(self):
        self.u.zachowanie["przypomnienie_mikrofonu_min"] = 5
        self.klawisz("F1_mikrofon")
        self.slowa()
        mowa = self.czekaj(11 * 60.0)
        self.assertEqual(mowa, ["Mikrofon na antenie od 5 minut", "Mikrofon na antenie od 10 minut"])


# =============================================================================
# 4. Alarm ciszy na antenie (plan v21, pkt 4; decyzja 4)
# =============================================================================
class TestBlokMiernikow(unittest.TestCase):
    def test_dekodowanie_i_main_lr(self):
        w = [db_na_int16(-90.0)] * 44
        w[6], w[7] = db_na_int16(-20.5), db_na_int16(-12.25)
        blob = koduj_blok(w)
        self.assertEqual(len(blob), 4 + 88)
        self.assertEqual(dekoduj_blok(blob), w)
        self.assertAlmostEqual(poziom_lr(dekoduj_blok(blob)), -12.25)

    def test_kolejnosc_bajtow_z_ustawien(self):
        w = [db_na_int16(-30.0)] * 8
        self.assertEqual(dekoduj_blok(koduj_blok(w, "big"), "big"), w)

    def test_zly_blok(self):
        with self.assertRaises(ValueError):
            dekoduj_blok(b"\x00\x00")
        with self.assertRaises(ValueError):
            dekoduj_blok(koduj_blok([1, 2, 3])[:-2])
        with self.assertRaises(ValueError):
            poziom_lr([0, 0, 0])


class TestDetektorCiszy(unittest.TestCase):
    def test_cisza_powtorka_powrot(self):
        d = DetektorCiszy(prog_dbfs=-50, czas_s=10, powtorka_s=30, limit_braku_s=2)
        d.oczekuj(0.0)
        zd = []
        for t in range(0, 80):
            d.przyjmij(-60.0 if t < 70 else -20.0, float(t))
            zd += [(t, z) for z in d.krok(float(t))]
        self.assertEqual(zd, [(10, "cisza"), (40, "cisza"), (70, "powrot")])

    def test_krotka_cisza_bez_alarmu(self):
        d = DetektorCiszy(czas_s=10)
        d.oczekuj(0.0)
        zd = []
        for t in range(30):
            d.przyjmij(-60.0 if t % 12 < 9 else -10.0, float(t))
            zd += d.krok(float(t))
        self.assertEqual(zd, [])

    def test_brak_danych_to_nie_cisza(self):
        d = DetektorCiszy(czas_s=10, limit_braku_s=2)
        d.oczekuj(0.0)
        self.assertEqual(d.krok(1.0), [])
        self.assertEqual(d.stan, "oczekiwanie")
        self.assertEqual(d.krok(3.0), ["niedostepne"])
        self.assertEqual(d.krok(60.0), [], "bez alarmu ciszy i bez powtórek")
        self.assertEqual(d.stan, "niedostepne")
        d.przyjmij(-20.0, 61.0)
        self.assertEqual(d.krok(61.0), ["dostepne"])

    def test_utrata_miernikow_w_trakcie_ciszy_kasuje_alarm(self):
        d = DetektorCiszy(czas_s=5, limit_braku_s=2)
        d.oczekuj(0.0)
        for t in range(8):
            d.przyjmij(-80.0, float(t))
            d.krok(float(t))
        self.assertEqual(d.stan, "alarm")
        self.assertEqual(d.krok(10.0), ["niedostepne"])
        self.assertEqual(d.stan, "niedostepne")


class TestAlarmCiszy(TestZSymulatorem):
    def przebieg(self, sekundy, krok=0.5):
        return self.czekaj(sekundy, krok)

    def test_subskrypcja_mierników_main_lr(self):
        self.assertIn(self.r.klient._subskrypcja.ident, self.sym.subskrybenci_miernikow)
        ident, _ = self.sym.subskrybenci_miernikow[self.r.klient._subskrypcja.ident]
        self.assertEqual(ident, "/meters/5")
        self.przebieg(1.0)
        self.assertEqual(self.r.detektor.stan, "dzwiek")
        self.assertAlmostEqual(self.r.detektor.ostatni_db, -18.0, places=2)

    def test_subskrypcja_odnawiana_jak_xremote(self):
        self.przebieg(25.0, krok=0.6)
        self.assertEqual(self.r.detektor.stan, "dzwiek", "subskrypcja nie wygasła po 25 s")

    def test_cisza_powtorka_i_powrot(self):
        self.przebieg(1.0)
        self.sym.cisza()
        mowa = self.przebieg(9.0)
        self.assertNotIn("Cisza na antenie", mowa, "przed upływem 10 s bez alarmu")
        mowa = self.przebieg(2.0)
        self.assertEqual(mowa, ["Cisza na antenie"])
        mowa = self.przebieg(31.0)
        self.assertEqual(mowa, ["Cisza na antenie"], "jedna powtórka po 30 s")
        self.klawisz("F2_status")
        self.assertTrue(self.slowa()[0].endswith("Cisza na antenie."))
        self.sym.cisza(False)
        mowa = self.przebieg(5.0)
        self.assertEqual(mowa, ["Dźwięk na antenie wrócił"], "komunikat o powrocie jednorazowo")
        od = len(self.sym.dziennik)
        self.assertEqual(self.zapisy(od), [], "bez automatycznego startu utworu")

    def test_alarm_bez_startu_utworu(self):
        class Program:
            nazwa = "atrapa"
            starty = 0

            def start_nastepnego(self):
                Program.starty += 1

            def stan(self):
                return "stop"
        self.r.emisja = Program()
        self.sym.cisza()
        self.przebieg(15.0)
        self.assertEqual(Program.starty, 0)

    def test_brak_miernikow_to_nie_cisza(self):
        self.przebieg(1.0)
        self.sym.mierniki_wylaczone = True
        mowa = self.przebieg(30.0)
        self.assertEqual(mowa, ["Mierniki niedostępne, alarm ciszy nie działa"])
        self.klawisz("F2_status")
        self.assertTrue(self.slowa()[0].endswith("Mierniki niedostępne, alarm ciszy nie działa."))
        self.sym.mierniki_wylaczone = False
        mowa = self.przebieg(1.0)
        self.assertEqual(mowa, ["Mierniki dostępne"])

    def test_zly_blok_to_brak_danych(self):
        self.przebieg(1.0)
        self.sym.mierniki_wylaczone = True
        for _ in range(10):
            self.r._przyjmij_mierniki(b"\x01\x02")
        self.assertGreater(self.r.bledy_miernikow, 0)
        mowa = self.przebieg(5.0)
        self.assertEqual(mowa, ["Mierniki niedostępne, alarm ciszy nie działa"])

    def test_prog_i_czas_z_ustawien(self):
        self.tearDown()
        self.setUp_z({"prog_dbfs": -10.0, "czas_s": 3.0, "powtorka_s": 30.0})
        self.przebieg(1.0)
        self.assertEqual(self.r.detektor.prog_dbfs, -10.0)
        mowa = self.przebieg(4.0)
        self.assertEqual(mowa, ["Cisza na antenie"], "-18 dB jest poniżej progu -10 z ustawień")

    def setUp_z(self, alarm):
        from pomoc import wczytaj_ustawienia  # noqa: F401
        import json
        import tempfile
        from pathlib import Path
        from mostek import ustawienia
        super().setUp()
        dane = json.loads(ustawienia.DOMYSLNE_USTAWIENIA.read_text(encoding="utf-8"))
        dane["zachowanie"]["alarm_ciszy"].update(alarm)
        tmp = Path(tempfile.mkdtemp(dir=self._tmp.name))
        (tmp / "s.json").write_text(json.dumps(dane), encoding="utf-8")
        self.u = ustawienia.wczytaj(tmp / "s.json", self.u.plik_poziomow)
        self.u.plik_trybu = tmp / "tryb_informacji.json"
        from mostek.rdzen import Rdzen
        self.r = Rdzen(self.u, self.klient, self.mowa, powierzchnia=self.pow, zegar=self.zegar, sen=self.zegar.sen)
        self.assertTrue(self.r.synchronizuj(nowa_baza_galek=True))
        self.slowa()

    def test_alarm_wylaczony_w_ustawieniach(self):
        self.tearDown()
        self.setUp_z({"wlaczony": False})
        self.sym.cisza()
        self.assertEqual(self.przebieg(20.0), [])

    def test_przelacznik_wylacza_alarm_w_trakcie_ciszy(self):
        """Michał 21.10.2026: alarm wyłączony przełącznikiem milknie od razu,
        F2 mówi, że jest wyłączony, a po ponownym włączeniu cisza liczy się
        od nowa (10 s), nie od początku ciszy."""
        self.przebieg(1.0)
        self.sym.cisza()
        self.assertEqual(self.przebieg(11.0), ["Cisza na antenie"])
        self.klawisz("alarm_ciszy")
        self.assertEqual(self.slowa(), ["Alarm ciszy wyłączony"])
        self.assertEqual(self.przebieg(60.0), [], "po wyłączeniu bez powtórek")
        self.klawisz("F2_status")
        self.assertTrue(self.slowa()[0].endswith("Alarm ciszy wyłączony."))
        self.klawisz("alarm_ciszy")
        self.assertEqual(self.slowa(), ["Alarm ciszy włączony"])
        self.assertNotIn("Cisza na antenie", self.przebieg(8.0), "pomiar od nowa")
        self.assertIn("Cisza na antenie", self.przebieg(4.0))

    def test_przelacznik_wlacza_alarm_wylaczony_w_ustawieniach(self):
        self.tearDown()
        self.setUp_z({"wlaczony": False})
        self.przebieg(1.0)
        self.sym.cisza()
        self.assertEqual(self.przebieg(15.0), [])
        self.klawisz("alarm_ciszy")
        self.assertEqual(self.slowa(), ["Alarm ciszy włączony"])
        self.assertEqual(self.przebieg(11.0), ["Cisza na antenie"])

    def test_dioda_rec_paska_1_pokazuje_alarm(self):
        self.przebieg(1.0)
        self.assertTrue(self.pow.diody[(1, 0)])
        self.klawisz("alarm_ciszy")
        self.przebieg(0.5)
        self.assertFalse(self.pow.diody[(1, 0)])

    def test_polecenie_konsoli_alarm(self):
        from mostek.glowny import polecenie_konsoli
        self.assertEqual(polecenie_konsoli("alarm"), ("klawisz", "alarm_ciszy"))

    def test_utrata_lacznosci_bez_alarmu_ciszy(self):
        self.przebieg(1.0)
        self.sym.awarie.rozlaczony = True
        mowa = self.przebieg(20.0)
        self.assertNotIn("Cisza na antenie", mowa)


# =============================================================================
# 5. Klucz przyciszania (Bus 5) przy przejściach (plan v22, pkt 5; decyzja 5)
# =============================================================================
class TestKluczPrzejscia(TestZSymulatorem):
    def test_start_klucz_pusty(self):
        self.assertEqual(self.w_kluczu(), set())

    def test_mikrofon_wchodzi_gdy_sluchacz_na_antenie(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.w_kluczu(), set(), "B: słuchacz czeka, mikrofon nie przycisza")
        od = len(self.sym.dziennik)
        self.ruch("telefon", 1.0)
        self.assertEqual(self.w_kluczu(), {"mikrofon"})
        adresy = [a for a, _ in self.zapisy(od)]
        self.assertLess(indeks(adresy, sciezki.fader(10)), indeks(adresy, sciezki.wysylka(9, 5)))
        self.assertEqual(self.m(sciezki.tap(9, 5)), sciezki.TAP_PRE, "klucz przed suwakiem")
        self.ruch("telefon", 0.0)
        self.assertEqual(self.w_kluczu(), set())

    def test_wylaczenie_mikrofonu_zdejmuje_z_klucza(self):
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        adresy = [a for a, _ in self.zapisy(od)]
        self.assertEqual(adresy[0], sciezki.lr(9), "najpierw antena")
        self.assertIn(sciezki.wysylka(9, 5), adresy)
        self.assertEqual(self.w_kluczu(), set())

    def test_zoom_w_kluczu_gdy_oboje_na_antenie(self):
        self.ruch("telefon", 1.0)
        self.assertEqual(self.w_kluczu(), set())
        self.ruch("zoom", 1.0)
        self.assertEqual(self.w_kluczu(), {"zoom"})
        self.ruch("zoom", 0.0)
        self.assertEqual(self.w_kluczu(), set())

    def test_cue_sluchacza_mikrofon_w_kluczu_przed_rozmowa_zamkniecia(self):
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.ruch("zoom", 1.0)
        self.assertEqual(self.w_kluczu(), {"mikrofon", "zoom"})
        od = len(self.sym.dziennik)
        self.cue("telefon")
        zapisy = self.zapisy(od)
        adresy = [a for a, _ in zapisy]
        # Zoom na antenie, słuchacz na CUE: Zoom wychodzi z klucza w zamknięciach,
        # przed otwarciem rozmowy.
        self.assertEqual(dict(zapisy)[sciezki.wysylka(7, 5)], 0.0)
        self.assertLess(indeks(adresy, sciezki.wysylka(7, 5)), indeks(adresy, sciezki.wysylka(9, 1), od_konca=True))
        self.assertEqual(self.w_kluczu(), {"mikrofon"}, "E: mikrofon w rozmowie ze słuchaczem")
        self.cue("zoom")
        self.assertEqual(self.w_kluczu(), {"mikrofon", "zoom"}, "F: oboje na CUE")
        self.cue("zoom")
        self.assertEqual(self.w_kluczu(), {"mikrofon"})
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(self.w_kluczu(), set(), "słuchacz czeka")

    def test_cue_samego_zooma_nie_rusza_klucza(self):
        self.cue("zoom")
        self.assertEqual(self.w_kluczu(), set())

    def test_suwak_konczy_cue_sluchacza(self):
        self.ruch("zoom", 1.0)
        self.cue("telefon")
        self.assertEqual(self.w_kluczu(), {"mikrofon"})
        self.ruch("telefon", 1.0)
        self.assertEqual(self.w_kluczu(), {"zoom"}, "słuchacz i Zoom na antenie, mikrofon poza")

    def test_mikrofon_z_innego_urzadzenia(self):
        self.ruch("telefon", 1.0)
        self.inny(sciezki.mute_szyny(6), 0)
        self.inny(sciezki.lr(9), 1)
        self.assertEqual(self.w_kluczu(), {"mikrofon"}, "klucz idzie za anteną")
        self.inny(sciezki.lr(9), 0)
        self.assertEqual(self.w_kluczu(), set())

    def test_nieznany_cue_zamyka_klucz(self):
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.sym.awarie.rozlaczony = False
        self.cue("telefon")              # stan NIEZNANY: tylko zamyka
        self.assertEqual(self.w_kluczu(), set())

    def test_uzgodnienie_po_powrocie_lacznosci(self):
        """Klucz niezgodny z rozmową (np. przejście urwane utratą łączności):
        pełny odczyt zamyka nadmiarowe wysyłki do Bus 5, nic nie otwiera."""
        self.sym.wartosci[sciezki.wysylka(9, 5)] = 0.75
        self.assertTrue(self.r.synchronizuj())
        self.assertEqual(self.w_kluczu(), set())
        self.assertEqual(self.naruszenia_miksera(), [])


class TestGlosnikiMono(TestZSymulatorem):
    def test_bus6_glosniki_bus5_klucz(self):
        self.assertEqual(self.u.szyny_glosnikow, (6,))
        self.assertEqual(self.u.szyna_klucza, 5)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.mute_szyny(6)), 0)
        self.assertEqual(self.m(sciezki.mute_szyny(5)), 1, "klucz przyciszania nie jest wyciszany")
        self.klawisz("F1_mikrofon")
        self.klawisz("glosniki_wlacz")
        self.assertEqual(self.m(sciezki.mute_szyny(6)), 1)

    def test_link_5_6_wylaczony_w_scenie(self):
        self.assertEqual(self.m(sciezki.buslink(5)), 0)
        self.assertNotIn(5, self.u.profil["linki_szyn"])


class TestMapaMute(unittest.TestCase):
    def test_puszczenie_mute_jest_zdarzeniem(self):
        from mostek import ustawienia
        mapa = MapaMC(ustawienia.wczytaj().xtouch)
        self.assertEqual(mapa.zdarzenie(bytes((0x90, 0x10, 0x7F))), ("przycisk", 1, 2))
        self.assertEqual(mapa.zdarzenie(bytes((0x90, 0x10, 0x00))), ("puszczenie", 1, 2))
        self.assertEqual(mapa.zdarzenie(bytes((0x80, 0x10, 0x40))), ("puszczenie", 1, 2))
        self.assertIsNone(mapa.zdarzenie(bytes((0x90, 0x00, 0x00))), "puszczenie REC bez zdarzenia")


if __name__ == "__main__":
    unittest.main()
