"""Niezależne kryteria odmowy. Czerwony wynik jest blokadą odbioru, nie xfail."""
import unittest
from typing import cast
from unittest.mock import patch

import test_odsluch_aux34 as baza
from mostek import odsluch
from mostek.rdzen import Krok


class BezpieczenstwoAux34(unittest.TestCase):
    def setUp(self):
        self.h = baza.TestAux34()
        self.h.setUp()

    def tearDown(self):
        self.h.tearDown()

    def test_niefinitywny_master_nie_uprawnia_do_otwarcia(self):
        h = self.h
        for x in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(master=x):
                h.inny(odsluch.MASTER_FADER, x)
                self.assertFalse(odsluch.zgodny(h.r.widok))

    def test_utrata_kontrolera_nie_otwiera_pfl_z_przycisku(self):
        h = self.h
        h.r.utrata_kontrolera()
        start = len(h.sym.dziennik)
        h.nacisnij('przycisk', 4, 3)
        otwarcia = [(a,v) for a,v in h.zapisy(start)
                    if a.startswith('/-stat/solosw/') and v == 1]
        self.assertEqual(otwarcia, [], 'L01: rozbrojony kontroler nie uprawnia do PFL')

    def test_nieswiezy_stan_i_brak_odpowiedzi_bez_otwarc(self):
        h = self.h
        h.cue('telefon')
        for k in (1,2):
            h.sym.wartosci[baza.s.wysylka(k,9)] = 0
            h.r.stan.potwierdz(baza.s.wysylka(k,9), 0, h.zegar())
        h.zegar.przesun(h.r.limit_swiezosci + 1)
        h.sym.awarie.rozlaczony = True
        start = len(h.sym.dziennik)
        h.odswiez()
        self.assertEqual([(a,v) for a,v in h.zapisy(start)
                          if '/mix/09/level' in a and cast(float,v) > 0], [])

    def test_wszystkie_stale_profili_odmawiaja_niefinitywnych_i_blednych(self):
        h = self.h
        for a, v in odsluch.stale().items():
            for x in (float('nan'), float('inf'), -float('inf'), None, 'bledne'):
                with self.subTest(adres=a, wartosc=x):
                    h.r.stan.potwierdz(a, x, h.zegar())
                    self.assertFalse(odsluch.zgodny(h.r.widok))
                    self.assertTrue(all(p == 0 for p in odsluch.cel(h.r.widok).values()))
            h.r.stan.potwierdz(a, v, h.zegar())
        self.assertTrue(odsluch.zgodny(h.r.widok))

    def test_zamknij_nie_omija_rozbrojenia_solo_ale_pozwala_zamknac(self):
        h = self.h
        h.r.utrata_kontrolera()
        h.r._w_zdarzeniu = True
        try:
            start = len(h.sym.dziennik)
            wynik = h.r._zamknij([Krok(baza.s.solo(1), 1), Krok(baza.s.solo(2), 0)])
            self.assertFalse(wynik.ok)
            self.assertNotIn((baza.s.solo(1), 1), h.zapisy(start))
            self.assertIn((baza.s.solo(2), 0), h.zapisy(start))
        finally:
            h.r._w_zdarzeniu = False

    def test_koncowe_uzgodnij_pozostaje_zdarzeniem_rozbrojonej_powierzchni(self):
        h = self.h
        # Automat własnego głosu działa teraz wyłącznie podczas CUE.
        # Bez tego warunku mutant utraty kontekstu nie próbuje otworzyć PFL.
        h.cue('telefon')
        h.r.utrata_kontrolera()
        # Obcy Main On, jeszcze bez lokalnego PFL. Sam przycisk nie otwiera toru.
        h.inny(baza.s.lr(9), 1)
        h.inny(baza.s.solo(9), 0)
        start = len(h.sym.dziennik)
        with patch.object(h.r, '_przycisk_paska'):
            h.nacisnij('przycisk', 4, 3)
        self.assertEqual([(a,v) for a,v in h.zapisy(start)
                          if a.startswith('/-stat/solosw/') and v == 1], [])
        self.assertFalse(h.r._w_zdarzeniu)

    def test_swiadoma_komenda_programowa_pfl_po_utracie_kontrolera_dozwolona(self):
        h = self.h
        h.r.utrata_kontrolera()
        self.assertFalse(h.r._w_zdarzeniu)
        h.r.przelacz_pfl('muzyka1')
        self.assertTrue(h.pfl('muzyka1'))

    def test_wyjatek_uzgodnienia_nie_zostawia_kontekstu_powierzchni(self):
        h = self.h
        with patch.object(h.r.odsluch_aux, 'uzgodnij', side_effect=RuntimeError('próba')):
            with self.assertRaises(RuntimeError):
                h.nacisnij('dotyk', 4, False)
        self.assertFalse(h.r._w_zdarzeniu)

    def test_stary_tryb_solo_nie_dostaje_nowej_blokady(self):
        h = self.h
        h.u.zachowanie.pop('tryb_odsluchu')
        h.r.utrata_kontrolera()
        h.r._w_zdarzeniu = True
        try:
            self.assertTrue(h.r._zamknij([Krok(baza.s.solo(1), 1)]).ok)
        finally:
            h.r._w_zdarzeniu = False

    def test_migracja_ogolna_odmawia_sprzecznych_duplikatow_bez_wrappera(self):
        src = (baza.DANE/'BAZA.scn').read_text()
        for adres in ('/ch/01/mix/09', '/ch/01/mix', '/config/solo', '/ch/01/preamp'):
            with self.subTest(adres=adres):
                linia = next(x for x in src.splitlines() if x.startswith(adres+' '))
                # Także adresy, których migracja nie zmienia; brak zależności od MD5.
                sprzeczna = src + linia + ' INNY_TOKEN\n'
                with self.assertRaisesRegex(ValueError, 'duplik|sprzecz|konflikt'):
                    baza.MIG.przygotuj(sprzeczna)

    def test_tory_starego_trybu_rownowazne_po_cue_talkback_i_kaszlu(self):
        h = self.h
        stary = baza.TestAux34()
        stary.setUp()
        try:
            stary.u.zachowanie.pop('tryb_odsluchu')
            for akcja in ('cueT','cueZ','kaszel','puscKaszel','cueT','talkT','puscTalkT'):
                for ob in (h,stary):
                    if akcja == 'cueT': ob.cue('telefon')
                    elif akcja == 'cueZ': ob.cue('zoom')
                    elif akcja == 'kaszel': ob.nacisnij('przycisk',1,2)
                    elif akcja == 'puscKaszel': ob.nacisnij('puszczenie',1,2)
                    elif akcja == 'talkT': ob.nacisnij('przycisk',2,2)
                    elif akcja == 'puscTalkT': ob.nacisnij('puszczenie',2,2)
                # Nowy odsłuch ma prawo zmienić tylko Send3 i lokalny monitor/solo.
                chronione = {a:v for a,v in stary.sym.wartosci.items()
                             if '/mix/09/' not in a and not a.startswith('/-stat/solosw/')
                             and not a.startswith('/config/solo/')}
                h.ten_sam_stan({a:h.m(a) for a in chronione}, chronione, akcja)
        finally:
            stary.tearDown()


if __name__ == '__main__':
    unittest.main()
