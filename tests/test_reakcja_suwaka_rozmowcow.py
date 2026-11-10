"""Pierwszy krok rozmówcy przez zglos/obsluz/tick; model, nie audio MR18."""
from contextlib import contextmanager
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki as s
from mostek import odsluch
from mostek.logika import ANTENA, CZEKA
from mostek.stan import NIEZNANY


class TestTelefon(TestZSymulatorem):
    zr = 'telefon'
    aux = False

    def setUp(self):
        super().setUp()
        if self.aux:
            self.u.zachowanie['tryb_odsluchu'] = 'aux34_mono'
            self.sym.wartosci.update(odsluch.stale())
            for k in range(1, 17):
                self.sym.wartosci[s.tap(k, 9)] = 4
            for p in s.POWROTY:
                self.sym.wartosci[s.wysylka_powrotu(p, 9)] = 0.0
        self.kanaly = self.u.zrodla[self.zr].kanaly
        self.fadery = [s.fader(k) for k in self.kanaly]
        self.main = [s.lr(k) for k in self.kanaly]
        self.nr_paska = self.r._pasek_zrodla(self.zr)
        self.drugi = 'zoom' if self.zr == 'telefon' else 'telefon'
        self.ustaw_mikser({a: 0.0 for a in self.fadery})
        self.r.synchronizuj()
        self.dzwieki_i_slowa()

    def ruch_teraz(self, v):
        self.r.zglos(('suwak', self.nr_paska, v))

    @contextmanager
    def slad(self):
        zd = []
        obsluz = self.sym._obsluz
        czytaj = self.klient.odczytaj_wiele
        def zapis(k, nadawca):
            od = len(self.sym.dziennik)
            w = obsluz(k, nadawca)
            zd.extend(('zapis', a, v) for _, _, a, v in self.sym.dziennik[od:])
            return w
        def odczyt(adresy, *args, **kwargs):
            d = czytaj(adresy, *args, **kwargs)
            zd.append(('odczyt', dict(d)))
            return d
        with patch.object(self.sym, '_obsluz', side_effect=zapis), patch.object(self.klient, 'odczytaj_wiele', side_effect=odczyt):
            yield zd

    def test_pierwszy_krok_i_dol_bez_dotyku(self):
        for v in (1 / 16383, 1e-8, .6):
            with self.subTest(v=v):
                self.cue(self.zr)
                self.dzwieki_i_slowa()
                self.r.zwloka_suwaka = 10
                self.ruch_teraz(v)
                self.assertFalse(self.r.widok.cue(self.zr))
                self.assertIs(self.r.widok.suwak_w_gorze(self.zr), True)
                self.assertEqual(self.r.widok.stan_rozmowcy(self.zr), ANTENA)
                self.assertTrue(all(self.m(a) > 0 for a in self.fadery))
                self.ruch_teraz(0)
                self.assertIs(self.r.widok.suwak_w_gorze(self.zr), False)
                self.assertEqual(self.r.widok.stan_rozmowcy(self.zr), CZEKA)
                self.assertTrue(all(self.m(a) == 0 for a in self.fadery))
                self.assertEqual(self.r.zwloka_suwaka, 10)

    def test_ciagly_ruch_jeden_komunikat_i_przejscie(self):
        self.cue(self.zr)
        self.dzwieki_i_slowa()
        self.r.zglos(('dotyk', self.nr_paska, True))
        with patch.object(self.r, '_po_zmianie_suwaka', wraps=self.r._po_zmianie_suwaka) as przejscia:
            self.ruch_teraz(1 / 16383)
            self.assertEqual(self.r.widok.stan_rozmowcy(self.zr), ANTENA)
            self.assertEqual(len(self.slowa()), 1)
            start = self.zegar()
            od = len(self.sym.dziennik)
            for i in range(1, 11):
                self.zegar.przesun(.08)
                self.ruch_teraz(i / 12)
                self.r.tick()
                self.assertTrue(self.r.widok.na_antenie(self.zr))
                for a in self.fadery:
                    self.assertAlmostEqual(self.m(a), i / 12 * self.r._gora_suwaka(self.nr_paska), places=5)
            self.assertGreater(self.zegar() - start, self.r.zwloka_suwaka)
            self.assertEqual(set(a for a, _ in self.zapisy(od)), set(self.fadery))
            self.r.zglos(('dotyk', self.nr_paska, False))
            self.tick(.31)
            self.assertEqual(przejscia.call_count, 1)
            self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_dol_szybko_gora_i_koncowy_odczyt(self):
        self.ruch_teraz(.6)
        self.dzwieki_i_slowa()
        with patch.object(self.r, '_po_zmianie_suwaka', wraps=self.r._po_zmianie_suwaka) as p:
            self.ruch_teraz(0)
            self.assertIs(self.r.widok.na_antenie(self.zr), False)
            self.ruch_teraz(1e-8)
            self.assertIs(self.r.widok.na_antenie(self.zr), True)
            self.ruch_teraz(.7)
            self.tick(.31)
            self.assertEqual(p.call_count, 2)
        for a in self.fadery:
            self.assertAlmostEqual(self.r.stan.wartosc(a), .7 * self.r._gora_suwaka(self.nr_paska), places=5)

    def test_cue_wlasne_obu_i_tylko_drugiego(self):
        for cue in ((self.zr,), (self.zr, self.drugi), (self.drugi,)):
            with self.subTest(cue=cue):
                self.r.zglos(('klawisz', 'F3_koniec_rozmowy'))
                self.ruch_teraz(0)
                for zr in cue:
                    self.cue(zr)
                self.ruch_teraz(1 / 16383)
                self.assertEqual(self.r.widok.cue_zbior(), frozenset(cue) - {self.zr})
                self.assertIs(self.r.widok.na_antenie(self.zr), True)
                self.assertEqual(self.naruszenia_miksera(), [])

    def test_zastany_w_gorze_cue_wymaga_dolu(self):
        self.ruch_teraz(.5)
        self.r.zglos(('dotyk', self.nr_paska, True))
        self.cue(self.zr)
        self.ruch_teraz(.6)
        self.tick(.31)
        self.assertIs(self.r.widok.cue(self.zr), True)
        self.assertTrue(all(self.m(a) == 0 for a in self.main))
        self.ruch_teraz(0)
        self.assertIs(self.r.widok.cue(self.zr), True)
        self.ruch_teraz(1e-8)
        self.assertIs(self.r.widok.na_antenie(self.zr), True)

    def test_prywatne_potwierdzone_przed_main_publiczny_powrot_i_n_minus_1(self):
        self.cue(self.zr)
        self.cue(self.drugi)
        wymagane = [a for a in self.r.widok.adresy_wysylki('mikrofon', self.r.widok.odbiorca(self.zr)) if self.m(a) > 0]
        with self.slad() as zd:
            self.ruch_teraz(1 / 16383)
        pierwszy = next(i for i, z in enumerate(zd) if z[0] == 'zapis' and z[1] in self.main and z[2] == 1)
        for a in wymagane:
            zamk = max(i for i, z in enumerate(zd[:pierwszy]) if z == ('zapis', a, 0))
            self.assertGreaterEqual(sum(z[0] == 'odczyt' and z[1].get(a) == 0 for z in zd[zamk + 1:pierwszy]), 2)
        odb = self.r.widok.odbiorca(self.zr)
        for a in wymagane:
            self.assertEqual(self.m(a), 0)
        for a in self.r.widok.adresy_tap('muzyka1', odb):
            self.assertEqual(self.m(a), s.TAP_POST)
        for a in self.r.widok.adresy_wysylki(self.zr, odb):
            self.assertEqual(self.m(a), 0)
        self.assertIs(self.r.widok.cue(self.drugi), True)
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_odmowa_zamkniec_nie_otwiera_main(self):
        self.cue(self.zr)
        odb = self.r.widok.odbiorca(self.zr)
        self.sym.awarie.ignoruj_zapis.update(self.r.widok.adresy_wysylki('mikrofon', odb))
        od = len(self.sym.dziennik)
        self.ruch_teraz(.7)
        self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))
        self.assertIs(self.r.widok.cue(self.zr), True)

    def test_odmowa_fadera_dodatniego_nie_otwiera(self):
        self.cue(self.zr)
        self.sym.awarie.ignoruj_zapis.update(self.fadery)
        od = len(self.sym.dziennik)
        self.ruch_teraz(1e-8)
        self.assertTrue(all(self.m(a) == 0 for a in self.main))
        self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))
        self.assertIs(self.r.widok.cue(self.zr), True)

    def test_nieznany_stary_i_kontroler_nie_otwieraja(self):
        for tryb in ('nieznany', 'stary', 'kontroler'):
            with self.subTest(tryb=tryb):
                self.r.kontroler_polaczony = True
                self.r.uzbrojony = True
                self.sym.awarie.rozlaczony = False
                self.r.synchronizuj()
                self.cue(self.zr)
                if tryb == 'nieznany':
                    self.r.stan.zsynchronizowany = False
                elif tryb == 'stary':
                    self.zegar.przesun(self.r.limit_swiezosci + 1)
                    self.sym.awarie.rozlaczony = True
                else:
                    self.r.zglos(('kontroler', 'test'))
                od = len(self.sym.dziennik)
                self.ruch_teraz(.7)
                self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))

    def test_utrata_w_trakcie_potwierdzen(self):
        self.cue(self.zr)
        self.sym.awarie.rozlacz_po_zapisach = 1
        od = len(self.sym.dziennik)
        self.ruch_teraz(.7)
        self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))
        self.assertFalse(self.r.stan.polaczony)

    def test_utrata_kontrolera_przed_otwarciem(self):
        self.cue(self.zr)
        oryginal = self.r._dwa_odczyty
        def odczyt(oczek):
            w = oryginal(oczek)
            self.r.kontroler_polaczony = False
            return w
        od = len(self.sym.dziennik)
        with patch.object(self.r, '_dwa_odczyty', side_effect=odczyt):
            self.ruch_teraz(.7)
        self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))

    def test_hold_z_widoku_od_pierwszego_kroku_do_zera(self):
        self.ustaw_mikser({s.lr(9): 0, s.fader(9): 0})
        self.r.synchronizuj()
        with patch.object(self.r, '_zlec_hold') as hold:
            self.ruch_teraz(1e-8)
            self.r.tick()
            self.assertEqual(hold.call_args.args, (True,))
            self.ruch_teraz(0)
            self.r.tick()
            self.assertEqual(hold.call_args.args, (False,))

    def test_kaszel_i_talkback_nie_otwieraja_mikrofonu(self):
        for tryb in ('kaszel', 'talkback'):
            with self.subTest(tryb=tryb):
                if tryb == 'kaszel':
                    self.r.zglos(('klawisz', 'F1_mikrofon'))
                    p = 1
                else:
                    p = self.nr_paska
                self.r.zglos(('przycisk', p, 2))
                od = len(self.sym.dziennik)
                self.ruch_teraz(1e-8)
                self.ruch_teraz(0)
                self.assertNotIn((s.lr(9), 1), self.zapisy(od))
                self.r.zglos(('puszczenie', p, 2))
                if self.suma('mikrofon'):
                    self.r.zglos(('klawisz', 'F1_mikrofon'))

    def test_stereo_rozbieznosc_i_brak_jednego_odczytu(self):
        if len(self.kanaly) < 2:
            return
        for wartosci in ((0, 1e-8), (.2, .7)):
            with self.subTest(wartosci=wartosci):
                self.ustaw_mikser(dict(zip(self.fadery, wartosci)))
                self.r.synchronizuj()
                self.assertIs(self.r.widok.suwak_w_gorze(self.zr), NIEZNANY)
                od = len(self.sym.dziennik)
                self.ruch_teraz(.6)
                self.assertFalse(any(a in self.fadery for a, _ in self.zapisy(od)))

    def test_niepelny_odczyt_pary_nie_otwiera(self):
        self.cue(self.zr)
        czytaj = self.klient.odczytaj_wiele
        def odczyt(adresy, *args, **kwargs):
            dane = czytaj(adresy, *args, **kwargs)
            if set(adresy) == set(self.fadery):
                dane.pop(self.fadery[-1])
            return dane
        od = len(self.sym.dziennik)
        with patch.object(self.klient, 'odczytaj_wiele', side_effect=odczyt):
            self.ruch_teraz(1e-8)
        self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))
        self.assertFalse(self.r.stan.polaczony)

    def test_odczyt_zera_zamiast_kroku_nie_otwiera(self):
        self.cue(self.zr)
        czytaj = self.klient.odczytaj_wiele
        def odczyt(adresy, *args, **kwargs):
            dane = czytaj(adresy, *args, **kwargs)
            if set(adresy) == set(self.fadery):
                dane[self.fadery[-1]] = 0.0
            return dane
        od = len(self.sym.dziennik)
        with patch.object(self.klient, 'odczytaj_wiele', side_effect=odczyt):
            self.ruch_teraz(1 / 16383)
        self.assertFalse(any(a in self.main and v == 1 for a, v in self.zapisy(od)))
        self.assertIs(self.r.widok.cue(self.zr), True)

    def test_nieznany_fader_blokuje_pierwszy_zapis(self):
        self.r.stan.zapomnij(self.fadery[-1])
        od = len(self.sym.dziennik)
        self.ruch_teraz(.5)
        self.assertFalse(any(a in self.fadery for a, v in self.zapisy(od)))

    def test_dol_zamyka_powrot_do_drugiego_natychmiast(self):
        self.ruch_teraz(1e-8)
        odb = self.r.widok.odbiorca(self.drugi)
        adresy = self.r.widok.adresy_wysylki(self.zr, odb)
        self.assertTrue(all(self.m(a) > 0 for a in adresy))
        self.ruch_teraz(0)
        self.assertTrue(all(self.m(a) == 0 for a in adresy))
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_odmowa_zera_nie_udaje_zamkniecia(self):
        self.ruch_teraz(1 / 16383)
        self.sym.awarie.ignoruj_zapis.update(self.fadery)
        self.ruch_teraz(0)
        self.assertIs(self.r.widok.na_antenie(self.zr), True)

    def test_koncowy_odczyt_regulacji_bez_przejsc_i_utraty(self):
        self.ruch_teraz(.2)
        self.dzwieki_i_slowa()
        self.r.zglos(('dotyk', self.nr_paska, True))
        czytaj = self.klient.odczytaj_wiele
        with patch.object(self.klient, 'odczytaj_wiele', wraps=czytaj) as odczyty:
            for v in (.3, .4, .5):
                self.zegar.przesun(.08)
                self.ruch_teraz(v)
                self.r.tick()
            self.assertFalse(any(set(c.args[0]) == set(self.fadery) for c in odczyty.call_args_list))
            self.tick(.31)
            self.assertEqual(sum(set(c.args[0]) == set(self.fadery) for c in odczyty.call_args_list), 1)
        self.ruch_teraz(.6)
        self.sym.awarie.rozlaczony = True
        self.tick(.31)
        self.assertFalse(self.r.stan.polaczony)

    def test_obaj_od_pierwszego_kroku_klucz_i_n_minus_1(self):
        self.ruch_teraz(1e-8)
        p = self.r._pasek_zrodla(self.drugi)
        self.r.zglos(('suwak', p, 1e-8))
        self.assertIs(self.r.widok.na_antenie(self.drugi), True)
        self.assertEqual(self.naruszenia_miksera(), [])
        self.assertEqual(self.naruszenia_klucza(), [])
        self.ruch_teraz(0)
        self.assertEqual(self.naruszenia_klucza(), [])

    def test_muzyka_i_monitor_bez_zmiany_progu_i_zwloki(self):
        prog = self.u.prog_suwaka_db
        self.assertEqual(prog, -50)
        self.r.zglos(('suwak', 4, 1e-8))
        self.tick(.31)
        self.assertIs(self.r.widok.suwak_w_gorze('muzyka1'), False)
        self.r.zglos(('suwak', 9, .3))
        self.assertIn(9, self.r._suwak_ruch)
        self.assertEqual(self.u.prog_suwaka_db, prog)


class TestZoom(TestTelefon):
    zr = 'zoom'


class TestTelefonAux(TestTelefon):
    aux = True


class TestZoomAux(TestZoom):
    aux = True
