"""Automat Bus 6 przy talkbacku: kolejność i skutki na symulatorze."""

import unittest
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki
from mostek.informacja import Tryb


BUS = sciezki.mute_szyny(6)
MIC = sciezki.wysylka(9, 1)


class TestGlosnikiTalkbacku(TestZSymulatorem):
    def wcisnij(self, pasek=2):
        self.nacisnij("przycisk", pasek, 2)

    def pusc(self, pasek=2):
        self.nacisnij("puszczenie", pasek, 2)

    def zapisy_glosnikow(self, od=0):
        return [v for a, v in self.zapisy(od) if a == BUS]

    def mikrofon_zamkniety(self):
        for a in (sciezki.lr(9), *(sciezki.wysylka(9, b) for b in (1, 3, 4, 5))):
            self.assertEqual(self.m(a), 0, a)

    def test_aktywne_wycisza_przed_otwarciem_i_przywraca_bez_mowy(self):
        for mute_act in (False, True):
            for tryb in Tryb:
                with self.subTest(mute_act=mute_act, tryb=tryb):
                    self.u.zachowanie["odciszaj_glosniki_po_wylaczeniu_mikrofonu"] = mute_act
                    self.info.tryb = tryb
                    przed = dict(self.sym.wartosci)
                    od = len(self.sym.dziennik)
                    self.assertEqual(self.m(BUS), 1)
                    self.wcisnij()
                    self.assertEqual(self.m(BUS), 0)
                    self.assertTrue(self.slyszalny(9, 1))
                    zapisy = self.zapisy(od)
                    self.assertLess(zapisy.index((BUS, 0)), next(i for i, (a, v) in enumerate(zapisy)
                                                              if a == MIC and isinstance(v, (int, float)) and v > 0))
                    self.assertEqual(self.dzwieki_i_slowa(), (["talkback_start"], []))
                    od_powrotu = len(self.sym.dziennik)
                    self.pusc()
                    self.ten_sam_stan(self.sym.wartosci, przed)
                    zapisy = self.zapisy(od_powrotu)
                    self.assertLess(zapisy.index((MIC, 0)), zapisy.index((BUS, 1)))
                    self.assertEqual(self.zapisy_glosnikow(od), [0, 1])
                    self.assertEqual(self.dzwieki_i_slowa(), (["talkback_koniec"], []))

    def test_sygnaly_i_odciszenie_po_potwierdzeniach(self):
        odczyt = self.r._dwa_odczyty
        potwierdzenia = []
        zapis = self.r._zapis
        def sprawdz_zapis(krok):
            if krok.adres == MIC and krok.wartosc > 0:
                self.assertIn({BUS: 0}, potwierdzenia)
            if krok.adres == BUS and krok.wartosc == 1:
                self.assertTrue(any(c.get(MIC) == 0 and sciezki.lr(9) in c for c in potwierdzenia))
            return zapis(krok)
        def sprawdz_odczyt(cel):
            wynik = odczyt(cel)
            potwierdzenia.append(dict(cel))
            return wynik
        def sygnal(klucz):
            if klucz == "talkback_start":
                self.assertIn({BUS: 0}, potwierdzenia)
                self.assertTrue(any(c.get(MIC, 0) > 0 for c in potwierdzenia))
            else:
                self.assertTrue(any(c.get(MIC) == 0 and sciezki.lr(9) in c for c in potwierdzenia))
        with patch.object(self.r, "_dwa_odczyty", side_effect=sprawdz_odczyt), \
                patch.object(self.r, "_zapis", side_effect=sprawdz_zapis), \
                patch.object(self.mowa, "sygnal", side_effect=sygnal) as dzwiek:
            self.wcisnij()
            self.pusc()
        self.assertEqual([c.args[0] for c in dzwiek.call_args_list], ["talkback_start", "talkback_koniec"])

    def test_wczesniej_wyciszone_nietkniete_takze_mute_act(self):
        for antena in (False, True):
            for mute_act in (False, True):
                with self.subTest(antena=antena, mute_act=mute_act):
                    self.u.zachowanie["odciszaj_glosniki_po_wylaczeniu_mikrofonu"] = mute_act
                    if self.suma("mikrofon"):
                        self.klawisz("F1_mikrofon")
                    self.klawisz("F1_mikrofon" if antena else "glosniki_wylacz")
                    self.slowa()
                    od = len(self.sym.dziennik)
                    self.wcisnij()
                    self.pusc()
                    self.assertEqual(self.zapisy_glosnikow(od), [])
                    self.assertEqual(self.m(BUS), 0)
                    self.assertEqual(self.suma("mikrofon"), antena)
                    self.assertEqual(self.dzwieki_i_slowa(), (["talkback_start", "talkback_koniec"], []))

    def test_niepotwierdzone_wyciszenie_odmowa_bez_otwarcia(self):
        self.sym.awarie.ignoruj_zapis.add(BUS)
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.mikrofon_zamkniety()
        self.assertTrue(self.zapisy_glosnikow(od), "musi spróbować wyciszyć")
        self.assertFalse(any(a.startswith("/ch/09/") for a, _ in self.zapisy(od)))
        self.assertEqual(self.dzwieki_i_slowa(),
                         ([], ["Talkback niedostępny, nie udało się wyciszyć głośników"]))
        self.sym.awarie.ignoruj_zapis.clear()
        self.pusc()
        self.assertEqual(self.m(BUS), 1)
        self.wcisnij()
        self.assertEqual(self.m(BUS), 0)
        self.pusc()
        self.assertEqual(self.m(BUS), 1)

    def test_brak_koncowego_potwierdzenia_wyciszenia_bez_otwarcia(self):
        odczyt = self.r._dwa_odczyty
        def brak(cel):
            wynik = odczyt(cel)
            return [BUS] if cel == {BUS: 0} else wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=brak):
            self.wcisnij()
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        self.assertFalse(any(a == MIC and isinstance(v, (int, float)) and v > 0 for a, v in self.zapisy()),
                         "nie wystarcza później zamknąć tor: nie wolno go otworzyć")
        self.assertNotIn("talkback_start", self.dzwieki_i_slowa()[0])
        self.assertFalse(self.r._talkback)
        self.pusc()
        self.assertEqual(self.m(BUS), 0)

    def test_obaj_adresaci_wyciszenie_raz_powrot_po_ostatnim(self):
        for pierwszy, drugi in ((2, 3), (3, 2)):
            with self.subTest(pierwszy=pierwszy):
                od = len(self.sym.dziennik)
                self.wcisnij(pierwszy)
                self.wcisnij(drugi)
                self.pusc(pierwszy)
                self.assertEqual(self.m(BUS), 0)
                self.assertEqual(self.zapisy_glosnikow(od), [0])
                self.pusc(drugi)
                self.assertEqual(self.zapisy_glosnikow(od), [0, 1])
                self.assertEqual(self.slowa(), [])

    def test_kaszel_odracza_powrot_do_puszczenia_wszystkiego(self):
        for kaszel_ostatni in (False, True):
            with self.subTest(kaszel_ostatni=kaszel_ostatni):
                od = len(self.sym.dziennik)
                self.wcisnij()
                self.wcisnij(1)
                self.wcisnij(3)
                self.pusc(2)
                self.pusc(3 if kaszel_ostatni else 1)
                self.assertEqual(self.m(BUS), 0)
                self.assertEqual(self.zapisy_glosnikow(od), [0])
                self.pusc(1 if kaszel_ostatni else 3)
                self.assertEqual(self.zapisy_glosnikow(od), [0, 1])
                self.assertEqual(self.slowa(), [])

    def test_reczne_wyciszenie_uniewaznia_powrot_takze_gdy_juz_cisza(self):
        self.wcisnij()
        self.klawisz("glosniki_wylacz")
        self.slowa()
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertEqual(self.m(BUS), 0)
        self.assertEqual(self.zapisy_glosnikow(od), [])
        self.assertEqual(self.dzwieki_i_slowa(), (["talkback_koniec"], []))

    def test_reczna_odmowa_wlaczenia_tego_samego_nie_odcisza_pozniej(self):
        self.wcisnij()
        self.klawisz("glosniki_wlacz")
        self.assertEqual(self.m(BUS), 0)
        self.slowa()
        self.pusc()
        self.assertEqual(self.m(BUS), 0)

    def test_obce_odciszenie_przerywa_i_nie_przywraca(self):
        self.wcisnij()
        self.slowa()
        self.inny(BUS, 1)
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        self.assertTrue(any("Talkback przerwany" in s and "głośniki wyciszone" in s for s in self.slowa()))
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertEqual(self.zapisy_glosnikow(od), [])

    def test_obca_zmiana_bez_zgloszenia_wykryta_przy_puszczeniu(self):
        self.wcisnij()
        self.slowa()
        self.sym.wartosci[BUS] = 1
        self.pusc()
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        self.assertNotIn("talkback_koniec", self.dzwieki_i_slowa()[0])

    def test_obce_odciszenie_i_wyciszenie_przed_odczytem_uniewaznia(self):
        self.wcisnij()
        self.slowa()
        for v in (1, 0):
            self.transport.rozeslij(self.sym.zmien_z_innego(BUS, v))
        self.pusc()
        self.assertEqual(self.m(BUS), 0)
        self.mikrofon_zamkniety()

    def test_wlasne_echa_i_odczyty_nie_uniewazniaja_powrotu(self):
        self.wcisnij()
        self.assertTrue(self.r._talkback)
        self.tick()
        self.pusc()
        self.tick()
        self.assertEqual(self.m(BUS), 1)
        self.assertEqual(self.dzwieki_i_slowa(), (["talkback_start", "talkback_koniec"], []))

    def test_cue_w_trakcie_blokuje_odciszenie_z_powodem(self):
        self.wcisnij()
        self.cue("zoom")
        self.slowa()
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertTrue(self.slyszalny(9, 3))
        self.assertEqual(self.m(BUS), 0)
        self.assertEqual(self.zapisy_glosnikow(od), [])
        self.assertTrue(any("Głośniki" in s and "mikrofon" in s for s in self.slowa()))

    def test_mute_act_w_trakcie_i_po_f3_nie_odbiera_wlasnosci(self):
        for poczatkowo_wyciszone in (False, True):
            with self.subTest(wyciszone=poczatkowo_wyciszone):
                if poczatkowo_wyciszone:
                    self.klawisz("glosniki_wylacz")
                self.wcisnij()
                self.wcisnij(1)
                self.cue("zoom")
                self.klawisz("F3_koniec_rozmowy")
                self.assertEqual(self.m(BUS), 0)
                self.pusc()
                self.assertEqual(self.m(BUS), 0)
                self.pusc(1)
                self.assertEqual(self.m(BUS), 0 if poczatkowo_wyciszone else 1)
                self.slowa()

    def test_przerwanie_kontrolerem_zostawia_wyciszone_i_mowi(self):
        self.wcisnij()
        self.slowa()
        self.nacisnij("kontroler", "restart")
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        self.assertTrue(any("Talkback przerwany, mikrofon poza anteną, głośniki wyciszone" == s
                            for s in self.slowa()))
        self.nacisnij("kontroler_powrot", "test")
        self.pusc()
        self.assertEqual(self.m(BUS), 0)

    def test_f1_po_puszczeniu_talkbacku_pod_kaszlem_nie_odcisza(self):
        self.wcisnij()
        self.wcisnij(1)
        self.pusc()
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.pusc(1)
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        self.assertTrue(any("Talkback przerwany" in s and "głośniki wyciszone" in s for s in self.slowa()))

    def test_utrata_miksera_bez_falszywego_potwierdzenia_i_bez_powrotu(self):
        self.wcisnij()
        self.slowa()
        self.sym.awarie.rozlaczony = True
        self.tick()
        slowa = self.slowa()
        self.assertTrue(any("Talkback przerwany" in s and "niepotwierdzone" in s and "głośnik" in s for s in slowa))
        self.sym.awarie.rozlaczony = False
        self.tick(2.0)
        self.pusc()
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)

    def test_niepotwierdzone_otwarcie_zostawia_glosniki_wyciszone(self):
        self.sym.awarie.ignoruj_zapis.add(MIC)
        self.wcisnij()
        self.pusc()
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        d, s = self.dzwieki_i_slowa()
        self.assertNotIn("talkback_start", d)
        self.assertTrue(any("Talkback przerwany" in x and "głośniki wyciszone" in x for x in s))

    def test_niepotwierdzony_powrot_mikrofonu_nie_odcisza(self):
        self.wcisnij()
        self.slowa()
        self.sym.awarie.ignoruj_zapis.add(MIC)
        self.pusc()
        self.assertEqual(self.m(BUS), 0)
        d, s = self.dzwieki_i_slowa()
        self.assertNotIn("talkback_koniec", d)
        self.assertTrue(any("Talkback przerwany" in x and "głośnik" in x for x in s))

    def test_niepotwierdzone_odciszenie_ostrzega_bez_dzwieku_glosnikow(self):
        self.wcisnij()
        self.slowa()
        self.sym.awarie.ignoruj_zapis.add(BUS)
        self.pusc()
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        d, s = self.dzwieki_i_slowa()
        self.assertFalse(any(x.startswith("glosniki_") for x in d))
        self.assertTrue(any("Głośniki nie przywrócone, mikser nie potwierdził" == x for x in s))

    def test_talkback_dolaczony_do_kaszlu_przejmuje_aktywne_glosniki(self):
        self.klawisz("F1_mikrofon")
        self.wcisnij(1)
        # W kaszlu mikrofon zamknięty. AOSC może w tym czasie odciszyć Bus 6.
        self.inny(BUS, 1)
        self.slowa()
        self.wcisnij()
        self.assertEqual(self.m(BUS), 0)
        self.mikrofon_zamkniety()
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))
        self.pusc(1)
        self.assertTrue(self.slyszalny(9, 1))
        self.pusc()
        # Zastany mikrofon wraca na antenę, więc zapora odmawia głośnikom.
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.m(BUS), 0)
        self.assertTrue(any("Głośniki nie przywrócone" in x for x in self.slowa()))

    def test_blad_potwierdzenia_odciszenia_zamyka_je_ponownie(self):
        self.wcisnij()
        self.slowa()
        odczyt = self.r._dwa_odczyty
        def brak(cel):
            wynik = odczyt(cel)
            return [BUS] if cel == {BUS: 1} else wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=brak):
            self.pusc()
        self.assertEqual(self.zapisy_glosnikow(), [0, 1, 0])
        self.assertTrue(any("Głośniki nie przywrócone" in x for x in self.slowa()))
        self.tick()
        self.assertEqual(self.m(BUS), 0)

    def test_utrata_potwierdzenia_odciszenia_domknie_po_polaczeniu(self):
        self.wcisnij()
        self.slowa()
        ustaw = self.klient.ustaw
        def utrata(adres, wartosc):
            wynik = ustaw(adres, wartosc)
            if adres == BUS and wartosc == 1:
                self.sym.awarie.rozlaczony = True
            return wynik
        with patch.object(self.klient, "ustaw", side_effect=utrata):
            self.pusc()
        # DSP zdążył odciszyć, ale bez transportu nie można go zamknąć.
        self.assertEqual(self.m(BUS), 1)
        self.assertTrue(any("głośniki mogą grać" in x for x in self.slowa()))
        self.sym.awarie.rozlaczony = False
        self.tick(2.0)
        self.assertEqual(self.m(BUS), 0)
        self.mikrofon_zamkniety()
        self.pusc()
        self.assertEqual(self.m(BUS), 0)

    def test_niepotwierdzone_glosniki_przy_przerwaniu_nie_udaja_ciszy(self):
        self.wcisnij()
        self.slowa()
        self.sym.awarie.ignoruj_zapis.add(BUS)
        self.inny(BUS, 1)
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 1)
        slowa = self.slowa()
        self.assertTrue(any("Talkback przerwany" in x and "niepotwierdzone" in x for x in slowa))
        self.assertFalse(any("głośniki wyciszone" in x for x in slowa))
        self.sym.awarie.ignoruj_zapis.clear()
        self.r.synchronizuj()
        self.assertEqual(self.m(BUS), 0)
        self.pusc()
        self.assertEqual(self.m(BUS), 0)

    def test_zmiana_glosnikow_podczas_potwierdzania_startu(self):
        odczyt = self.r._dwa_odczyty
        def zmiana(cel):
            wynik = odczyt(cel)
            if cel.get(MIC, 0) > 0:
                self.sym.wartosci[BUS] = 1
            return wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=zmiana):
            self.wcisnij()
        self.mikrofon_zamkniety()
        self.assertEqual(self.m(BUS), 0)
        self.assertNotIn("talkback_start", self.dzwieki_i_slowa()[0])

    def test_przerwanie_przy_dolaczaniu_drugiego_nie_zaczyna_nowego_talkbacku(self):
        self.wcisnij()
        self.slowa()
        self.inny(BUS, 1)
        # Wariant bez przetworzenia zgłoszeń: wykrywa odczyt drugiego MUTE.
        self.klawisz("glosniki_wlacz")
        self.wcisnij()
        self.slowa()
        self.sym.wartosci[BUS] = 1
        self.wcisnij(3)
        self.assertFalse(self.r._talkback)
        self.assertEqual(self.m(BUS), 0)
        self.mikrofon_zamkniety()
        self.assertNotIn("talkback_start", self.dzwieki_i_slowa()[0])

    def test_obce_otwarcie_mikrofonu_tuz_przed_odciszeniem(self):
        self.wcisnij()
        self.slowa()
        odczyt = self.r._dwa_odczyty
        zmieniono = False
        def zmiana(cel):
            nonlocal zmieniono
            wynik = odczyt(cel)
            if not zmieniono and cel.get(MIC) == 0 and sciezki.lr(9) in cel:
                zmieniono = True
                self.sym.wartosci[sciezki.lr(9)] = 1
            return wynik
        with patch.object(self.r, "_dwa_odczyty", side_effect=zmiana):
            self.pusc()
        self.assertTrue(zmieniono)
        self.assertEqual(self.m(BUS), 0)
        self.assertNotIn(1, self.zapisy_glosnikow())


if __name__ == "__main__":
    unittest.main()
