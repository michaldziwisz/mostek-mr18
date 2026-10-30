"""Regresja luk L01-L06 z analizy wersji 22 i decyzji Michała P01-P03 (18.10.2026).

Źródło luk: analiza wersji 22 (kontrakty zachowań). Każdy
test L0x odtwarza obserwację z migawki e2f11c2 i sprawdza zachowanie po
poprawce. Mutanty w narzedzia/mutacje_zapory.py (MUTANTY_POPRAWEK i reguły
zapory) wywracają te testy po cofnięciu poprawki w kopii kodu.

Oracle: wartości w symulatorze („mikser”) i to, co powiedziała NVDA, nie
stan, który mostek sam sobie zapisał.
"""

import unittest

from pomoc import TestZSymulatorem, sciezki, poziom_db_na_float
from mostek.logika import NaruszenieZapory
from mostek.xtouch import AtrapaPortuMIDI, MapaMC, PowierzchniaXTouch

POZIOM = poziom_db_na_float(0.0)
NUTA_F1 = 54


# =============================================================================
# L01: utrata kontrolera rozbraja powierzchnię
# =============================================================================
class TestL01UtrataKontrolera(TestZSymulatorem):
    def test_utrata_kontrolera_rozbraja_powierzchnie(self):
        """Po restarcie X-TOUCH zdarzenia z powierzchni nie otwierają: F1 nie
        wpuszcza mikrofonu, suwak nie rusza miksera. NVDA mówi o utracie."""
        self.nacisnij("kontroler", "restart X-TOUCH")
        self.assertFalse(self.r.uzbrojony, "powierzchnia rozbrojona")
        self.assertIn("Kontroler odłączony, stół tylko zamyka tory", self.slowa())
        od = len(self.sym.dziennik)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0, "F1 nie otwiera mikrofonu przy utraconym kontrolerze")
        self.assertEqual(self.slowa(), ["Mikrofon nie włączony, kontroler odłączony"])
        self.ruch("telefon", 1.0)
        self.assertEqual(float(self.m(sciezki.fader(10))), 0.0, "suwak nie wpuszcza słuchacza na antenę")
        self.cue("telefon")
        self.assertFalse(self.cue_sym("telefon"), "CUE nie otwiera rozmowy")
        self.klawisz("glosniki_wylacz")
        self.assertTrue(self.glosniki_wyciszone(), "zamknięcia działają")
        self.klawisz("glosniki_wlacz")
        self.assertTrue(self.glosniki_wyciszone(), "odciszenie to otwarcie")
        self.assertTrue(all(float(v) == 0.0 for _, v in self.zapisy(od)), self.zapisy(od))

    def test_wylaczenie_mikrofonu_dziala_po_utracie(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.nacisnij("kontroler", "port MIDI zamknięty")
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertTrue(self.glosniki_wyciszone(), "Mute-Act to otwarcie, czeka na powrót kontrolera")
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony"])

    def test_kaszel_przerwany_mikrofon_poza_antena(self):
        self.klawisz("F1_mikrofon")
        self.nacisnij("przycisk", 1, 2)
        self.nacisnij("kontroler", "restart X-TOUCH")
        self.nacisnij("puszczenie", 1, 2)
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertIsNone(self.r._kaszel)

    def test_powrot_kontrolera_silniki_potem_uzbrojenie(self):
        self.nacisnij("kontroler", "restart X-TOUCH")
        self.slowa()
        self.pow.suwaki.clear()
        od = len(self.sym.dziennik)
        self.nacisnij("kontroler_powrot", "port MIDI otwarty")
        self.assertEqual(self.zapisy(od), [], "powrót kontrolera nic nie zapisuje do miksera")
        # Mikrofon w symulatorze na 0 dB; góra suwaka mikrofonu to +10 dB
        # (Michał 21.10.2026), więc 0 dB to trzy czwarte drogi.
        self.assertAlmostEqual(self.pow.suwaki[1], 0.75, places=3)
        self.assertTrue(self.r.uzbrojony)
        self.assertEqual(self.slowa(), ["Kontroler podłączony, suwaki według miksera"])
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)

    def test_f8_po_utracie_nie_mowi_synchronizacja_zgodna(self):
        self.nacisnij("kontroler", "restart X-TOUCH")
        self.slowa()
        self.klawisz("F8_odczytaj_powierzchnie")
        tekst = self.slowa()[0]
        self.assertIn("Kontroler odłączony", tekst)
        self.assertTrue(tekst.endswith("Synchronizacja niepełna"), tekst)

    def test_midi_pierwszy_komunikat_po_utracie_to_powrot(self):
        """Port MIDI zamknięty, potem X-TOUCH znowu wysyła: pierwszy komunikat
        uzgadnia kontroler i sam nie jest wykonywany."""
        port = AtrapaPortuMIDI()
        self.r.powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), port, self.r.zglos)
        port.przy_zamknieciu()
        self.assertFalse(self.r.uzbrojony)
        self.zegar.przesun(0.2)
        port.wstrzyknij(0x90, NUTA_F1, 0x7F)
        self.assertEqual(self.m(sciezki.lr(9)), 0, "naciśnięcie sprzed uzgodnienia nie jest wykonywane")
        self.assertTrue(self.r.uzbrojony)
        self.zegar.przesun(0.2)
        port.wstrzyknij(0x90, NUTA_F1, 0x7F)
        self.assertEqual(self.m(sciezki.lr(9)), 1)


# =============================================================================
# L02: limit świeżości odczytu krytycznego
# =============================================================================
class TestL02Swiezosc(TestZSymulatorem):
    def test_po_limicie_bez_odczytu_stan_nieznany(self):
        self.zegar.przesun(5.0)
        self.assertFalse(self.r._gotowy(), "odczyt starszy niż limit to stan NIEZNANY")
        self.assertEqual(self.r.tekst_statusu(), "Stan nieznany, mikrofon może być na antenie")

    def test_otwarcie_po_limicie_swiezosci_wymaga_odczytu(self):
        """Inne urządzenie otworzyło rozmowę ze słuchaczem, zgłoszenie zginęło,
        5 s bez odczytu. F1 nie może zdecydować na starym odczycie: najpierw
        świeży odczyt, który pokazuje CUE; Fader Start musi je najpierw zamknąć."""
        self.sym.wartosci[sciezki.tap(9, 1)] = sciezki.TAP_PRE
        self.sym.wartosci[sciezki.wysylka(9, 1)] = POZIOM
        self.zegar.przesun(5.0)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertFalse(self.cue_sym("telefon"))
        zapisy = self.zapisy()
        self.assertLess(zapisy.index((sciezki.wysylka(9, 1), 0.0)), zapisy.index((sciezki.lr(9), 1)))
        self.assertIn("Mikrofon włączony, koniec rozmowy", self.slowa())

    def test_brak_odczytu_przy_nieswiezym_to_utrata(self):
        self.zegar.przesun(5.0)
        self.sym.awarie.rozlaczony = True
        self.klawisz("F1_mikrofon")
        self.assertFalse(self.r.stan.polaczony)
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertIn("Brak łączności z mikserem, stan mikrofonu nieznany", self.slowa())

    def test_zapis_otwierajacy_na_starym_odczycie_najpierw_czyta(self):
        """Bezpośredni zapis otwierający przy starym odczycie: świeży odczyt
        przed zapisem; zmiana od ostatniego odczytu odrzuca otwarcie."""
        from mostek.rdzen import Krok
        self.zegar.przesun(5.0)
        zap = len(self.sym.zapytania)
        self.sym.wartosci[sciezki.mute_szyny(6)] = 0
        with self.assertRaises(NaruszenieZapory):
            self.r._zapis(Krok(sciezki.lr(1), 1))
        self.assertGreater(len(self.sym.zapytania), zap, "przed zapisem świeży odczyt")
        self.r._zapis(Krok(sciezki.lr(9), 0))       # zamknięcie zawsze dozwolone

    def test_odczyt_okresowy_utrzymuje_swiezosc(self):
        self.czekaj(10.0, krok=0.5)
        self.assertTrue(self.r._gotowy())


# =============================================================================
# L03: głośniki przy blokującym profilu i stanie NIEZNANY
# =============================================================================
class TestL03Glosniki(TestZSymulatorem):
    def test_glosniki_wlacz_przy_blokujacym_profilu(self):
        self.inny(sciezki.szyna_lr(5), 1)
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.klawisz("glosniki_wylacz")
        self.slowa()
        self.klawisz("glosniki_wlacz")
        self.assertTrue(self.glosniki_wyciszone(), "Bus 6 zostaje wyciszony")
        self.assertEqual(self.slowa(), ["Głośniki nie włączone, profil miksera niezgodny"])

    def test_glosniki_wlacz_przy_stanie_nieznanym(self):
        self.klawisz("glosniki_wylacz")
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.slowa()
        self.sym.awarie.rozlaczony = False
        self.r.glosniki(True)
        self.assertTrue(self.glosniki_wyciszone())
        self.assertEqual(self.slowa(), ["Głośniki nie włączone, stan nieznany"])

    def test_status_mowi_o_blokadzie_profilu(self):
        """Naruszenie, którego mostek nie zamyka sam (suchy mikrofon na USB):
        F2 robi pełny odczyt, blokada zostaje, status ją podaje."""
        self.inny(sciezki.usb_zrodlo(3), 8)
        self.slowa()
        self.klawisz("F2_status")
        tekst = self.slowa()[-1]
        self.assertTrue(tekst.startswith("Mikrofon wyłączony. Słuchacz czeka. Zoom czeka. "), tekst)
        self.assertIn("Profil miksera niezgodny: wyjście USB 3 przenosi suchy mikrofon albo telefon", tekst)

    def test_suchy_glos_na_usb_nagran_nie_blokuje(self):
        """Michał 21.10.2026: suchy mikrofon na USB 9 do nagrań poza anteną.
        Wyjścia 5 do 18 nie blokują, 1/2 (Zoom) i 3/4 (emisja) blokują."""
        self.inny(sciezki.usb_zrodlo(9), 8)        # kanał 9 = mikrofon
        self.slowa()
        self.assertFalse(self.r.zapora.profil_blokuje)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 1, "mikrofon włącza się mimo USB 9")
        self.inny(sciezki.usb_zrodlo(10), 9)       # kanał 10 = telefon
        self.assertFalse(self.r.zapora.profil_blokuje)
        for wy in (1, 2, 3, 4):
            self.inny(sciezki.usb_zrodlo(wy), 8)
            self.assertTrue(self.r.zapora.profil_blokuje, f"USB {wy}")
            self.inny(sciezki.usb_zrodlo(wy), sciezki.USB_ZRODLO_SZYNA[3] if wy in (1, 2) else 36)
            self.assertFalse(self.r.zapora.profil_blokuje, f"USB {wy} po przywróceniu")

    def test_f2_po_ochronnym_zamknieciu_zdejmuje_blokade(self):
        """Bus 5 na Main LR: mostek zamyka, blokada zostaje; F2 to pełny odczyt
        zgodnego profilu, który zdejmuje blokadę (kontrakt pkt 8)."""
        self.inny(sciezki.szyna_lr(5), 1)
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.slowa()
        self.klawisz("F2_status")
        self.assertIn("Profil miksera zgodny, otwieranie odblokowane", self.slowa())
        self.assertFalse(self.r.zapora.profil_blokuje)


# =============================================================================
# L04: licznik nowego stanu od pierwszego potwierdzenia
# =============================================================================
class TestL04Licznik(TestZSymulatorem):
    def test_pierwszy_odczyt_nowego_stanu_bez_czasu_poprzedniego(self):
        self.cue("telefon")
        self.cue("telefon")              # słuchacz czeka
        self.czekaj(40)
        self.slowa()
        # Suwak słuchacza z innego urządzenia bez zgłoszenia /xremote: wykrywa go F2.
        self.sym.wartosci[sciezki.fader(10)] = 0.75
        self.klawisz("F2_status")
        mowa = self.slowa()
        status = mowa[-1]
        self.assertNotIn("od 40 sekund", status, mowa)
        self.assertIn("Słuchacz na antenie. ", status, mowa)
        self.czekaj(5.0)
        self.klawisz("F2_status")
        self.assertIn("Słuchacz na antenie od 5 sekund", self.slowa()[-1])


# =============================================================================
# L05: wszystkie wejścia klucza przyciszania (Bus 5)
# =============================================================================
class TestL05WejsciaKlucza(TestZSymulatorem):
    def test_obca_wysylka_do_klucza_blokuje_i_jest_zamykana(self):
        a = sciezki.wysylka(11, 5)
        self.sym.wartosci[a] = 0.75
        self.assertTrue(self.r.synchronizuj())
        self.assertIn(a, self.r.stan.adresy(), "wysyłka kanału 11 do Bus 5 jest w odczycie")
        self.assertTrue(self.r.zapora.profil_blokuje, "obce wejście klucza blokuje profil")
        self.assertEqual(self.m(a), 0.0, "mostek zamyka obce wejście klucza")
        mowa = self.slowa()
        self.assertTrue(any("kanał 11 w kluczu przyciszania" in s for s in mowa), mowa)
        self.assertIn("Ochronne zamknięcie: zamknięta wysyłka do klucza przyciszania: kanał 11", mowa)
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.m(sciezki.lr(9)), 0, "otwarcia zablokowane do pełnego odczytu")

    def test_powrot_aux_do_klucza_z_innego_urzadzenia(self):
        a = sciezki.wysylka_powrotu("aux", 5)
        self.inny(a, 0.5)
        self.assertEqual(self.m(a), 0.0)
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.assertIn("Ochronne zamknięcie: zamknięta wysyłka do klucza przyciszania: powrót AUX", self.slowa())

    def test_muzyka_do_klucza_zamykana(self):
        self.inny(sciezki.wysylka(1, 5), POZIOM)
        self.assertEqual(self.m(sciezki.wysylka(1, 5)), 0.0)
        self.assertTrue(self.r.zapora.profil_blokuje)

    def test_zgubione_zgloszenie_zamyka_odczyt_okresowy(self):
        self.sym.wartosci[sciezki.wysylka(16, 5)] = 0.5
        self.czekaj(1.0, krok=0.6)
        self.assertEqual(self.m(sciezki.wysylka(16, 5)), 0.0)
        self.assertTrue(self.r.zapora.profil_blokuje)

    def test_glosy_klucza_nie_sa_obce(self):
        """Mikrofon i Zoom w kluczu w tej samej rozmowie co słuchacz to nie naruszenie."""
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.ruch("zoom", 1.0)
        self.assertEqual(self.w_kluczu(), {"mikrofon", "zoom"})
        self.assertTrue(self.r.synchronizuj())
        self.assertFalse(self.r.zapora.profil_blokuje)
        self.assertEqual(self.w_kluczu(), {"mikrofon", "zoom"})


# =============================================================================
# L06: zamknięty rejestr ścieżek
# =============================================================================
class TestL06Rejestr(TestZSymulatorem):
    def test_adres_spoza_rejestru_odrzucony(self):
        for adres in ("/obce/mix/lr", "/ch/17/mix/lr", "/ch/09/mix/11/level"):
            with self.assertRaises(NaruszenieZapory) as k:
                self.r.zapora.sprawdz(adres, 0, self.r.widok)
            self.assertEqual(k.exception.regula, "sciezka_w_rejestrze")

    def test_klient_nie_wysyla_adresu_spoza_rejestru(self):
        with self.assertRaises(KeyError):
            self.klient.ustaw("/obce/mix/lr", 0)


# =============================================================================
# P02: odczyt tylko ochronnie zamyka
# =============================================================================
class TestP02OchronneZamkniecia(TestZSymulatorem):
    def test_status_zgodnego_miksera_zero_zapisow(self):
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 1.0)
        self.czekaj(3.0)
        self.slowa()
        od = len(self.sym.dziennik)
        self.klawisz("F2_status")
        self.czekaj(5.0, krok=0.5)
        self.klawisz("F2_status")
        self.assertEqual(self.zapisy(od), [], "status i odczyt okresowy zgodnego miksera nic nie zapisują")

    def test_odczyt_okresowy_tylko_zamyka(self):
        """Suwak słuchacza z innego urządzenia bez zgłoszenia: odczyt okresowy
        ogłasza zmianę, ale nie przestawia tras (to nie jest szyna na Main LR
        ani klucz przy blokadzie), więc zero zapisów i powrót słuchacza do
        Zooma się nie otwiera. Trasy dopasuje zgłoszenie albo przejście."""
        self.slowa()
        od = len(self.sym.dziennik)
        self.sym.wartosci[sciezki.fader(10)] = 0.75
        mowa = self.czekaj(1.0, krok=0.6)
        self.assertIn("Słuchacz na antenie z innego urządzenia", mowa)
        self.assertEqual(self.zapisy(od), [], "odczyt okresowy bez zapisów poza ochronnymi zamknięciami")
        self.assertNotIn("telefon", self.slyszy("zoom"))

    def test_pelny_odczyt_zamyka_szyne_na_main_lr_i_ostrzega(self):
        self.ustaw_mikser({sciezki.szyna_lr(2): 1})
        od = len(self.sym.dziennik)
        self.assertTrue(self.r.synchronizuj())
        self.assertEqual(self.zapisy(od), [(sciezki.szyna_lr(2), 0)])
        self.assertIn("Ochronne zamknięcie: szyna 2 zdjęta z Main LR", self.slowa())
        self.assertTrue(self.r.zapora.profil_blokuje)


# =============================================================================
# P03: F2 krótkie
# =============================================================================
class TestP03StatusKrotki(TestZSymulatorem):
    def test_f2_bez_poziomow_w_stalej_kolejnosci(self):
        self.ruch("zoom", 0.5)
        self.slowa()
        self.klawisz("F2_status")
        tekst = self.slowa()[0]
        self.assertEqual(tekst, "Mikrofon wyłączony. Słuchacz czeka. Zoom na antenie. Głośniki włączone.")
        self.nacisnij("galka_wcisnij", 3)
        self.assertIn("suwak", self.slowa()[0], "poziom podaje gałka paska")


if __name__ == "__main__":
    unittest.main()
