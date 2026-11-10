"""Niezależne oczekiwania z kontraktu, bez wywoływania produkcyjnego cel()."""
import unittest
import test_odsluch_aux34 as baza
s = baza.s

class KontraktCue(unittest.TestCase):
    def setUp(self):
        self.h = baza.TestAux34()
        self.h.setUp()

    def tearDown(self):
        self.h.tearDown()

    def stereo(self):
        h = self.h
        self.assertEqual(h.m(s.MONITOR_ZRODLO), 1, 'Źródło stereo Main LR, nie OFF ani LRPFL')
        self.assertEqual([h.m(s.solo(k)) for k in range(1, 17)], [0]*16)
        self.assertEqual(h.m(s.SOLO_MAIN_LR), 0)
        self.assertEqual([h.a(k) for k in range(1, 11)], [0]*10)
        # Oba człony każdej pary programu nadal dochodzą do stereo LR.
        for l, r in ((1,2),(3,4),(5,6)):
            self.assertEqual((h.m(s.lr(l)),h.m(s.lr(r))), (1,1))

    def test_stereo_spoczynek_antena_koniec_cue(self):
        h = self.h
        self.stereo()
        h.klawisz('F1_mikrofon')
        self.stereo()
        h.klawisz('F1_mikrofon')
        for rozmowcy in (('telefon',), ('zoom',), ('telefon','zoom')):
            with self.subTest(cue=rozmowcy):
                for z in rozmowcy: h.cue(z)
                self.assertEqual(h.m(s.MONITOR_ZRODLO), 0)
                self.assertTrue(all(h.a(k) > 0 for k in range(1,7)))
                for z in rozmowcy: h.cue(z)
                self.stereo()

    def test_obcy_koniec_cue_przywraca_stereo_bez_solo(self):
        h = self.h
        h.cue('telefon')
        h.inny(s.wysylka(9,1), 0.0)
        h.odswiez()
        self.stereo()

    def test_obcy_koniec_czesci_cue_zdejmuje_tylko_tego_rozmowce(self):
        h = self.h
        h.cue('telefon'); h.cue('zoom')
        h.inny(s.wysylka(9,1), 0.0)
        h.odswiez()
        self.assertEqual(h.m(s.solo(10)), 0)
        self.assertEqual(h.m(s.solo(7)), 1)
        self.assertEqual(h.m(s.solo(8)), 1)
        self.assertEqual(h.m(s.MONITOR_ZRODLO), 0)
        self.assertGreater(h.a(1), 0)

    def test_sam_talkback_nie_otwiera_aux_i_wraca_stereo(self):
        for pasek in (2,3):
            self.h.nacisnij('przycisk',pasek,2)
            self.stereo()
            self.h.nacisnij('puszczenie',pasek,2)
            self.stereo()

    def test_pfl_przed_cue_i_automatyczny_powrot(self):
        h = self.h
        h.r.przelacz_pfl('muzyka1')
        h.cue('telefon')
        self.assertEqual((h.a(1),h.a(2)), (0,0))
        self.assertGreater(h.a(3),0)
        h.r.koniec_pfl(); h.odswiez()
        self.assertGreater(h.a(1),0)
        h.cue('telefon')
        self.stereo()

    def test_odmowa_powrotu_lr_przed_potwierdzeniem_ciszy_aux(self):
        h = self.h
        h.cue('telefon')
        h.sym.awarie.ignoruj_zapis.add(s.wysylka(1,9))
        h.inny(s.wysylka(9,1),0.0)
        start = len(h.sym.dziennik)
        self.assertFalse(h.r.odsluch_aux.uzgodnij())
        self.assertNotIn((s.MONITOR_ZRODLO,1),h.zapisy(start))

if __name__ == '__main__':
    unittest.main()
