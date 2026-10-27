"""Kaszel w PHONES: surowe solo symulatora, nie odbiór audio MR18."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki
from mostek.informacja import Tryb
from mostek.klient import BrakOdpowiedzi
from mostek.logika import NaruszenieZapory
from mostek.rdzen import SoloKaszlu


class TestKaszelSolo(TestZSymulatorem):
    def wcisnij(self):
        self.nacisnij("przycisk", 1, 2)

    def pusc(self):
        self.nacisnij("puszczenie", 1, 2)

    def solo_zapisy(self, od):
        return [(a, v) for a, v in self.zapisy(od) if a.startswith("/-stat/solosw/")]

    def przygotuj(self, rozmowca="telefon"):
        self.cue(rozmowca)
        self.slowa()
        self.assertEqual(self.m(sciezki.solo(9)), 1)

    def test_cue_telefon_i_zoom_migawka_i_nietkniete_trasy(self):
        for rozmowca, kanaly in (("telefon", (10,)), ("zoom", (7, 8))):
            with self.subTest(rozmowca=rozmowca):
                self.przygotuj(rozmowca)
                przed = dict(self.sym.wartosci)
                od = len(self.sym.dziennik)
                self.wcisnij()
                self.assertEqual(self.m(sciezki.solo(9)), 0)
                for k in kanaly:
                    self.assertEqual(self.m(sciezki.solo(k)), 1)
                dozwolone = self.r._adresy_mikrofonu() | {sciezki.solo(9)}
                self.assertTrue(all(a in dozwolone for a, _ in self.zapisy(od)))
                for a, v in przed.items():
                    if a not in dozwolone:
                        self.assertEqual(self.m(a), v, a)
                self.pusc()
                self.assertEqual(self.sym.wartosci, przed)
                self.assertEqual(self.solo_zapisy(od), [(sciezki.solo(9), 0), (sciezki.solo(9), 1)])
                self.assertEqual(self.dzwieki_i_slowa(), ([], []))
                self.klawisz("F3_koniec_rozmowy")

    def test_pfl_mikrofonu_z_innym_solo_bez_otwartych_wysylek(self):
        self.ustaw_mikser({sciezki.solo(9): 1, sciezki.solo(10): 1})
        self.r.synchronizuj()
        self.slowa()
        przed = dict(self.sym.wartosci)
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.pusc()
        self.assertEqual(self.sym.wartosci, przed)
        self.assertEqual(self.zapisy(od), [(sciezki.solo(9), 0), (sciezki.solo(9), 1)])

    def test_jedyne_solo_mikrofonu_znika_i_wraca(self):
        self.ustaw_mikser({sciezki.solo(9): 1})
        self.r.synchronizuj()
        self.slowa()
        przed = dict(self.sym.wartosci)
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)
        self.assertEqual(self.zapisy(od), [(sciezki.solo(9), 0), (sciezki.solo(9), 1)])
        self.assertEqual(self.sym.wartosci, przed)
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_cue_po_obcym_zgaszeniu_pozostalych_solo_te_same_zasady(self):
        self.przygotuj()
        for a in self.sym.wartosci:
            if a.startswith("/-stat/solosw/") and a != sciezki.solo(9):
                self.sym.wartosci[a] = 0
        od = len(self.sym.dziennik)
        przed = dict(self.sym.wartosci)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertFalse(self.slyszalny(9, 1))
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)
        self.assertEqual(self.solo_zapisy(od), [(sciezki.solo(9), 0), (sciezki.solo(9), 1)])
        self.assertEqual(self.sym.wartosci, przed)
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_antena_bez_solo_nie_zapisuje_solo(self):
        self.klawisz("F1_mikrofon")
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertEqual(self.solo_zapisy(od), [])

    def test_antena_z_solo_ta_sama_regula(self):
        self.klawisz("F1_mikrofon")
        self.inny(sciezki.solo(9), 1)
        self.inny(sciezki.solo(10), 1)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)
        self.assertEqual(self.m(sciezki.lr(9)), 1)

    def test_talkback_bez_zmian_kaszel_w_obu_kolejnosciach(self):
        self.przygotuj("zoom")
        for pierwszy_kaszel in (False, True):
            with self.subTest(pierwszy_kaszel=pierwszy_kaszel):
                if pierwszy_kaszel:
                    self.wcisnij()
                self.nacisnij("przycisk", 2, 2)
                if not pierwszy_kaszel:
                    self.assertEqual(self.m(sciezki.solo(9)), 1)
                    self.wcisnij()
                self.assertEqual(self.m(sciezki.solo(9)), 0)
                self.assertEqual(self.m(sciezki.solo(7)), 1)
                self.pusc()
                self.assertTrue(self.slyszalny(9, 1))
                self.assertEqual(self.m(sciezki.solo(9)), 1)
                self.nacisnij("puszczenie", 2, 2)

    def test_dwa_odczyty_solo_i_powrot_po_wysylkach(self):
        self.przygotuj()
        zdarzenia = []
        odczyt, zapis = self.r._dwa_odczyty, self.r._zapis

        def czytaj(cel):
            wynik = odczyt(cel)
            zdarzenia.append(("odczyt", dict(cel), wynik))
            return wynik

        def pisz(krok):
            zdarzenia.append(("zapis", krok.adres, krok.wartosc))
            return zapis(krok)

        with patch.object(self.r, "_dwa_odczyty", side_effect=czytaj), patch.object(self.r, "_zapis", side_effect=pisz):
            self.wcisnij()
            self.assertTrue(any(z[0] == "odczyt" and z[1].get(sciezki.solo(9)) == 0 and not z[2]
                                for z in zdarzenia))
            zdarzenia.clear()
            self.pusc()
        i = zdarzenia.index(("zapis", sciezki.solo(9), 1))
        self.assertTrue(any(z[0] == "odczyt" and z[1].get(sciezki.wysylka(9, 1), 0) > 0 and not z[2]
                            for z in zdarzenia[:i]))
        self.assertTrue(any(z[0] == "odczyt" and z[1].get(sciezki.solo(9)) == 1 and not z[2]
                            for z in zdarzenia[i + 1:]))

    def test_przerwanie_kontroler_f1_obca_wysylka_i_synchronizacja(self):
        for przerwanie in ("kontroler", "F1", "wysylka", "synchronizacja"):
            with self.subTest(przerwanie=przerwanie):
                self.przygotuj()
                self.wcisnij()
                self.assertEqual(self.m(sciezki.solo(9)), 0)
                if przerwanie == "kontroler":
                    self.nacisnij("kontroler", "restart")
                elif przerwanie == "F1":
                    self.klawisz("F1_mikrofon")
                elif przerwanie == "wysylka":
                    self.inny(sciezki.wysylka(9, 1), 0.1)
                else:
                    self.r.synchronizuj()
                self.assertEqual(self.m(sciezki.solo(9)), 1)
                self.assertFalse(self.slyszalny(9, 1))
                self.assertEqual(self.m(sciezki.lr(9)), 0)
                od = len(self.sym.dziennik)
                self.pusc()
                self.assertEqual(self.solo_zapisy(od), [])
                self.nacisnij("kontroler_powrot", "test")
                self.klawisz("F3_koniec_rozmowy")

    def test_utrata_miksera_zostawia_solo_bez_zaleglego_powrotu(self):
        self.przygotuj()
        self.wcisnij()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.sym.awarie.rozlaczony = False
        self.tick(2.0)
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertFalse(self.slyszalny(9, 1))

    def test_obce_solo_impuls_nie_jest_cofany(self):
        self.przygotuj()
        self.wcisnij()
        for v in (1, 0):
            self.transport.rozeslij(self.sym.zmien_z_innego(sciezki.solo(9), v))
        self.r.przetworz_zgloszenia()
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertEqual(self.solo_zapisy(od), [])

    def test_obce_solo_innego_kanalu_bez_zgloszenia_uniewaznia_powrot(self):
        self.przygotuj()
        self.wcisnij()
        self.sym.wartosci[sciezki.solo(10)] = 0
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertEqual(self.solo_zapisy(od), [])

    def test_jawny_koniec_pfl_bez_wskrzeszenia_migawki(self):
        self.przygotuj()
        self.wcisnij()
        self.klawisz("koniec_pfl")
        od = len(self.sym.dziennik)
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertEqual(self.solo_zapisy(od), [])

    def test_dlugo_i_powtorzone_wcisniecie_bez_nadpisania(self):
        self.przygotuj()
        self.wcisnij()
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.czekaj(180.0), [])
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertEqual(self.solo_zapisy(od), [])
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)

    def test_cisza_we_wszystkich_trybach(self):
        self.przygotuj()
        for tryb in Tryb:
            self.info.tryb = tryb
            self.wcisnij()
            self.assertEqual(self.m(sciezki.solo(9)), 0)
            self.pusc()
            self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_niepotwierdzone_solo_ostrzega_ale_nie_otwiera_wysylek(self):
        self.przygotuj()
        self.sym.awarie.ignoruj_zapis.add(sciezki.solo(9))
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertFalse(self.slyszalny(9, 1))
        self.assertFalse(any(a == sciezki.wysylka(9, 1) and v > 0 for a, v in self.zapisy(od)))
        self.assertIn(self.r.t("odsluch_niepotwierdzony"), self.slowa())

    def test_brak_dwoch_odczytow_solo_nie_udaje_sukcesu(self):
        self.przygotuj()
        oryginal = self.r._dwa_odczyty

        def czytaj(cel):
            if cel.get(sciezki.solo(9)) == 0:
                return [sciezki.solo(9)]
            return oryginal(cel)

        with patch.object(self.r, "_dwa_odczyty", side_effect=czytaj):
            self.wcisnij()
        self.assertIn(self.r.t("odsluch_niepotwierdzony"), self.slowa())
        self.assertFalse(self.slyszalny(9, 1))

    def test_niepotwierdzony_powrot_solo_ostrzega(self):
        self.przygotuj()
        self.wcisnij()
        self.sym.awarie.ignoruj_zapis.add(sciezki.solo(9))
        self.pusc()
        self.assertIn(self.r.t("odsluch_niepotwierdzony"), self.slowa())
        self.assertEqual(self.m(sciezki.solo(9)), 0)

    def test_zapora_sesji_i_adresow_nawet_przy_zatrutej_migawce(self):
        self.przygotuj()
        self.wcisnij()
        s = self.r._solo_kaszlu
        self.assertIsNotNone(s)
        obce = [sciezki.solo(10), sciezki.solo(7), sciezki.solo(1), sciezki.SOLO_MAIN_LR,
                sciezki.lr(9), sciezki.lr(10), sciezki.wysylka(9, 1), sciezki.wysylka(9, 5),
                sciezki.mute_szyny(6), sciezki.wysylka(9, 6), sciezki.MONITOR_ZRODLO]
        od = len(self.sym.dziennik)
        for a in obce:
            with self.subTest(adres=a):
                # Wadliwy generator nie może rozszerzyć uprawnień migawki.
                s.sprzed[a] = 1
                for v in (0, 1):
                    with self.assertRaises(NaruszenieZapory):
                        self.r._zapis_solo_kaszlu(s, a, v)
                del s.sprzed[a]
        with self.assertRaises(NaruszenieZapory):
            self.r._zapis_solo_kaszlu(SoloKaszlu(dict(s.sprzed), dict(s.oczekiwane)), sciezki.solo(9), 1)
        self.assertEqual(self.zapisy(od), [])
        self.pusc()
        od = len(self.sym.dziennik)
        with self.assertRaises(NaruszenieZapory):
            self.r._zapis_solo_kaszlu(s, sciezki.solo(9), 0)
        self.assertEqual(self.zapisy(od), [])

    def test_obce_solo_wlaczone_wygrywa_bez_zamykania(self):
        self.przygotuj()
        self.wcisnij()
        self.inny(sciezki.solo(9), 1)
        od = len(self.sym.dziennik)
        self.tick()
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)
        self.assertEqual(self.solo_zapisy(od), [])

    def test_nieznany_stan_bez_powrotu_solo(self):
        self.przygotuj()
        self.wcisnij()
        self.r.stan.zsynchronizowany = False
        self.r._przerwij_kaszel()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.r.synchronizuj()
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 0)

    def test_blad_zapisu_solo_traci_sesje_bez_zaleglego_powrotu(self):
        self.przygotuj()
        ustaw = self.klient.ustaw

        def zapis(a, v):
            if a == sciezki.solo(9):
                raise BrakOdpowiedzi("awaria solo")
            return ustaw(a, v)

        with patch.object(self.klient, "ustaw", side_effect=zapis):
            self.wcisnij()
        self.assertFalse(self.r.stan.polaczony)
        self.assertIsNone(self.r._solo_kaszlu)
        self.assertIsNone(self.r._kaszel)
        self.assertFalse(self.slyszalny(9, 1))

    def test_przerwany_powrot_wysylek_oddaje_tylko_bezpieczne_solo(self):
        self.przygotuj()
        self.wcisnij()
        self.sym.awarie.ignoruj_zapis.add(sciezki.wysylka(9, 1))
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)
        self.assertFalse(self.slyszalny(9, 1))
        self.assertEqual(self.m(sciezki.lr(9)), 0)

    def test_wiele_kanalow_mikrofonu_migawka_rozbiezna(self):
        self.u.zrodla["mikrofon"] = replace(self.u.zrodla["mikrofon"], kanaly=(9, 11))
        self.ustaw_mikser({sciezki.solo(9): 1, sciezki.solo(11): 0, sciezki.solo(10): 1})
        self.r.synchronizuj()
        self.wcisnij()
        self.assertEqual(self.m(sciezki.solo(9)), 0)
        self.assertEqual(self.m(sciezki.solo(11)), 0)
        self.pusc()
        self.assertEqual(self.m(sciezki.solo(9)), 1)
        self.assertEqual(self.m(sciezki.solo(11)), 0)


if __name__ == "__main__":
    unittest.main()
