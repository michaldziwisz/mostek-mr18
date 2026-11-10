"""Regresja pierwszego kroku MR18: rzeczywisty klient, kodek i awarie.

Model obcięcia pasuje do logu, nie rozstrzyga arytmetyki firmware.
"""
from unittest.mock import patch
from typing import cast
from pomoc import TestZSymulatorem, sciezki
from kwantyzacja_mikrofonu import model, kwantyzuj, float32
from mostek.klient import BrakOdpowiedzi
from mostek.konwersje import poziom_float_na_db

FADER = sciezki.fader(9)
MAIN = sciezki.lr(9)
GLOSNIKI = sciezki.mute_szyny(6)


class TestKwantyzacjaMikrofonu(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.ustaw_mikser({FADER: 0.0, MAIN: 0})
        self.r.synchronizuj()
        self.dzwieki_i_slowa()
        self.r.obsluz(('dotyk', 1, True))

    def ruch_teraz(self, v):
        self.r.obsluz(('suwak', 1, v))

    def zamkniety(self):
        self.assertEqual(self.m(MAIN), 0)
        self.assertIn('Mikrofon nie włączony', ' '.join(self.slowa()))

    def test_model_odtwarza_obie_pary_logu(self):
        self.assertEqual(kwantyzuj(16/16383), 0.0)
        self.assertEqual(kwantyzuj(.04370383934566319), .04301075264811516)
        self.assertEqual(kwantyzuj(1/1023-1e-7), 0.0)
        self.assertEqual(kwantyzuj(1/1023+1e-7), float32(1/1023))

    def test_dodatni_zamiar_od_pierwszego_kroku(self):
        for v in (1/16383, 16/16383, 1/1023-1e-7, 1/1023, 1/1023+1e-7):
            with self.subTest(v=v), model(self):
                t = self.zegar()
                self.ruch_teraz(v)
                self.assertEqual(self.m(MAIN), 1)
                self.assertEqual(self.m(FADER), float32(1/1023))
                self.assertLess(self.zegar()-t, self.r.zwloka_suwaka)
                self.assertEqual(self.dzwieki_i_slowa(), (['mikrofon_na_antenie'], ['Mikrofon włączony']))
                self.ruch_teraz(0.0); self.slowa()

    def test_zapas_float32_i_brak_istotnego_podbicia(self):
        for v in (1/16383, 16/16383):
            kod = self.r._koduj_fader_mikrofonu(v)
            self.assertGreater(float32(kod)*1023, 1)
            self.assertLess(kod, .001)
            self.assertLess(poziom_float_na_db(kod), -89.5)
        for v in (.002, .04370383934566319, .75, 1.0, 0.0):
            self.assertEqual(self.r._koduj_fader_mikrofonu(v), v)

    def test_bezposredni_zapis_takze_koduje(self):
        with model(self):
            self.assertTrue(self.r._ustaw_fader_mikrofonu(1/16383))
            self.assertEqual(self.m(FADER), float32(1/1023))
            self.assertTrue(self.r._ustaw_fader_mikrofonu(0.0))
            self.assertEqual(self.m(FADER), 0.0)

    def test_regulacja_do_minimum_nie_zamyka_i_nie_wznawia(self):
        for odstep in (.012, .4):
            with self.subTest(odstep=odstep), model(self), patch.object(
                    self.r, '_wykonaj_przejscie', wraps=self.r._wykonaj_przejscie) as przejscia:
                self.ruch_teraz(16/16383)
                self.slowa()
                od = len(self.sym.dziennik)
                for v in (.04, 1/16383, 16/16383, .04370383934566319):
                    self.zegar.przesun(odstep)
                    self.ruch_teraz(v); self.r.tick()
                    self.assertEqual(self.m(MAIN), 1)
                    self.assertGreater(cast(float, self.m(FADER)), 0)
                self.tick(.31)
                self.assertEqual(przejscia.call_count, 1)
                self.assertEqual({a for a, _ in self.zapisy(od)}, {FADER})
                self.assertEqual(self.dzwieki_i_slowa(), ([], []))
                self.ruch_teraz(0.0); self.slowa()

    def test_szybki_dol_gora_kazde_zero_zamyka(self):
        with model(self):
            for v in (1/16383, 0.0, 16/16383, 0.0, 1/16383):
                self.ruch_teraz(v)
                self.assertEqual(self.m(MAIN), int(v>0))
                self.assertEqual(cast(float, self.m(FADER))>0, v>0)
                self.assertFalse(any('nie włączony' in s for s in self.slowa()))

    def test_ignorowany_dodatni_zapis_nadal_odmawia(self):
        self.sym.awarie.ignoruj_zapis = {FADER}
        with model(self) as zd:
            self.ruch_teraz(16/16383)
        self.zamkniety()
        self.assertFalse(any(z['typ']=='zapis' and z['adres']==MAIN and z['wartosc']==1 for z in zd))

    def test_odmowa_zera_nie_udaje_zamkniecia_fadera(self):
        with model(self):
            self.ruch_teraz(16/16383); self.slowa()
            self.sym.awarie.ignoruj_zapis = {FADER}
            self.ruch_teraz(0.0)
        self.assertEqual(self.m(MAIN), 0)
        self.assertGreater(cast(float, self.m(FADER)), 0)
        self.assertFalse(any('Głośniki włączone' in s for s in self.slowa()))
        self.assertFalse(self.r._ustaw_fader_mikrofonu(0.0))

    def test_main_on_odmawia_i_zamyka_fader(self):
        self.sym.awarie.ignoruj_zapis = {MAIN}
        with model(self):
            self.ruch_teraz(1/16383)
        self.zamkniety()
        self.assertEqual(self.m(FADER), 0.0)

    def test_zamkniecia_przed_pierwszym_dodatnim_faderem(self):
        for cue in ((), ('telefon',), ('zoom',), ('telefon', 'zoom')):
            with self.subTest(cue=cue):
                for zr in cue:
                    self.cue(zr)
                self.slowa()
                przed = dict(self.sym.wartosci)
                with model(self) as zd:
                    self.ruch_teraz(1/16383)
                self.assertEqual(self.m(MAIN), 1)
                i = next(i for i,z in enumerate(zd) if z['typ']=='zapis' and z['adres']==FADER and z['wartosc']>0)
                for a in ([GLOSNIKI] if przed[GLOSNIKI] else [])+[sciezki.wysylka(9,b) for b in (1,3,4) if cast(float, przed[sciezki.wysylka(9,b)])>0]:
                    self.assertTrue(any(z['typ']=='zapis' and z['adres']==a and z['wartosc']==0 for z in zd[:i]))
                    self.assertGreaterEqual(sum(z['typ']=='odczyt' and z['dane'].get(a)==0 for z in zd[:i]), 2)
                self.ruch_teraz(0.0); self.slowa()

    def test_odmowy_zamkniec_blokuja_minimalny_krok(self):
        for a in (GLOSNIKI, sciezki.wysylka(9,1), sciezki.wysylka(9,3)):
            with self.subTest(a=a):
                if a != GLOSNIKI:
                    self.cue('telefon'); self.cue('zoom'); self.slowa()
                self.sym.awarie.ignoruj_zapis = {a, sciezki.wysylka(9,4)} if a.endswith('/03/level') else {a}
                od = len(self.sym.dziennik)
                with model(self):
                    self.ruch_teraz(1/16383)
                self.assertNotIn((MAIN,1), self.zapisy(od))
                self.assertFalse(any(b==FADER and cast(float, v)>0 for b,v in self.zapisy(od)))
                self.zamkniety()
                self.sym.awarie.ignoruj_zapis = set()
                self.klawisz('F3_koniec_rozmowy'); self.slowa()

    def test_pusty_odczyt_fadera_nie_potwierdza(self):
        czytaj = self.klient.odczytaj_wiele
        licznik = 0
        def brak(adresy, *a, **kw):
            nonlocal licznik
            wynik = czytaj(adresy, *a, **kw)
            if list(adresy)==[FADER]:
                licznik += 1
                # Pierwszy odczyt należy do klient.ustaw; drugi do rdzenia.
                if licznik == 2:
                    return {}
            return wynik
        with model(self), patch.object(self.klient, 'odczytaj_wiele', side_effect=brak):
            self.ruch_teraz(1/16383)
        self.zamkniety()

    def test_stary_lub_sprzeczny_odczyt_nie_potwierdza(self):
        for v in (0.0, .5, float('nan')):
            with self.subTest(v=v):
                czytaj = self.klient.odczytaj_wiele
                licznik = 0
                def falszywy(adresy, *a, **kw):
                    nonlocal licznik
                    wynik = czytaj(adresy, *a, **kw)
                    if list(adresy)==[FADER]:
                        licznik += 1
                        if licznik == 2:
                            return {FADER:v}
                    return wynik
                with model(self), patch.object(self.klient, 'odczytaj_wiele', side_effect=falszywy):
                    self.ruch_teraz(1/16383)
                self.zamkniety()

    def test_brak_odpowiedzi_nie_potwierdza(self):
        czytaj = self.klient.odczytaj_wiele
        def brak(adresy, *a, **kw):
            if list(adresy)==[FADER]:
                raise BrakOdpowiedzi('test: cisza')
            return czytaj(adresy, *a, **kw)
        with model(self), patch.object(self.klient, 'odczytaj_wiele', side_effect=brak):
            self.ruch_teraz(1/16383)
        self.assertFalse(self.r.stan.polaczony)
        self.assertEqual(self.m(MAIN), 0)
        self.assertIn('Mikrofon nie włączony', ' '.join(self.slowa()))

    def test_opozniony_prawidlowy_odczyt_nadal_otwiera(self):
        czytaj = self.klient.odczytaj_wiele
        def pozniej(adresy, *a, **kw):
            self.zegar.przesun(.002)
            return czytaj(adresy, *a, **kw)
        with model(self), patch.object(self.klient, 'odczytaj_wiele', side_effect=pozniej):
            t=self.zegar(); self.ruch_teraz(16/16383)
        self.assertEqual(self.m(MAIN), 1)
        self.assertLess(self.zegar()-t, self.r.zwloka_suwaka)
        self.assertEqual(self.slowa(), ['Mikrofon włączony'])

    def test_utrata_kontrolera_i_miksera_blokuje_minimum(self):
        for tryb in ('kontroler', 'mikser'):
            with self.subTest(tryb=tryb):
                self.r.kontroler_polaczony = tryb != 'kontroler'
                self.sym.awarie.rozlacz_po_zapisach = 1 if tryb == 'mikser' else 0
                od = len(self.sym.dziennik)
                with model(self):
                    self.ruch_teraz(1/16383)
                self.assertNotIn((MAIN,1), self.zapisy(od))
                self.assertEqual(self.m(MAIN), 0)
                self.sym.awarie.rozlaczony = False
                self.sym.awarie.rozlacz_po_zapisach = 0
                self.r.kontroler_polaczony = True
                self.r.uzbrojony = True
                self.r.synchronizuj(); self.slowa()

    def test_aux34_cue_najmniejszy_krok_i_kaszel(self):
        import test_odsluch_aux34 as baza
        h = baza.TestAux34()
        h.setUp()
        try:
            h.ustaw_mikser({FADER:0.0, MAIN:0})
            h.r.synchronizuj(); h.slowa()
            h.cue('telefon'); h.cue('zoom'); h.slowa()
            with model(h):
                h.r.obsluz(('suwak',1,1/16383))
                self.assertEqual(h.m(MAIN), 1)
                self.assertGreater(cast(float, h.m(FADER)), 0)
                self.assertFalse(h.cue_sym('telefon'))
                self.assertFalse(h.cue_sym('zoom'))
                self.assertEqual(h.m(sciezki.MONITOR_ZRODLO), 1)
                self.assertEqual(h.a(9), 0)
                h.r.kaszel_wcisniety()
                h.r.obsluz(('suwak',1,16/16383))
                self.assertEqual(h.m(MAIN), 0)
                h.r.kaszel_puszczony()
                self.assertEqual(h.m(MAIN), 1)
                h.r.obsluz(('suwak',1,0.0))
                self.assertEqual(h.m(FADER), 0)
                self.assertEqual(h.m(MAIN), 0)
        finally:
            h.tearDown()

    def test_hold_bez_skoku_przy_ciaglym_ruchu(self):
        from atrapa_playoutu import SerwerPlayoutu
        from mostek import emisja
        s = SerwerPlayoutu(True)
        self.addCleanup(s.zamknij)
        self.r.emisja = emisja.SARA(s.port, limit_s=.1)
        zlec = self.r._zlec_hold
        def hold(v):
            zlec(v)
            self.assertTrue(self.r._tor_emisji.czekaj())
        with model(self), patch.object(self.r, '_zlec_hold', side_effect=hold):
            for v in (16/16383, .04, 1/16383, .04370383934566319):
                self.ruch_teraz(v); self.r.tick(); self.slowa()
            self.assertEqual([p for p in s.polecenia if p.startswith('Hold')], ['Hold=1'])
            self.ruch_teraz(0.0); self.slowa()
            self.assertEqual([p for p in s.polecenia if p.startswith('Hold')], ['Hold=1','Hold=0'])
