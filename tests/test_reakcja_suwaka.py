"""Reakcja ręki przez obsluz/tick, bez pomocnika czekającego na bezruch."""
from contextlib import contextmanager
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki

FADER = sciezki.fader(9)
MAIN = sciezki.lr(9)
GLOSNIKI = sciezki.mute_szyny(6)
PRYWATNE = [sciezki.wysylka(9, b) for b in (1, 3, 4)]


class TestReakcjaSuwaka(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.ustaw_mikser({FADER: 0.0, MAIN: 0})
        self.r.synchronizuj()
        self.dzwieki_i_slowa()

    def ruch_teraz(self, wartosc):
        self.r.obsluz(('suwak', 1, wartosc))

    def bez_otwarcia(self, od):
        z = self.zapisy(od)
        self.assertNotIn((MAIN, 1), z)
        self.assertFalse(any(a == FADER and v > 0 for a, v in z), z)

    @contextmanager
    def slad(self):
        """Wspólny porządek rzeczywistych zapisów DSP i zwróconych odczytów."""
        zd = []
        obsluz = self.sym._obsluz
        czytaj = self.klient.odczytaj_wiele
        def zapis(k, nadawca):
            od = len(self.sym.dziennik)
            wynik = obsluz(k, nadawca)
            zd.extend(('zapis', a, v) for _, _, a, v in self.sym.dziennik[od:])
            return wynik
        def odczyt(adresy, *args, **kwargs):
            wynik = czytaj(adresy, *args, **kwargs)
            zd.append(('odczyt', dict(wynik)))
            return wynik
        with patch.object(self.sym, '_obsluz', side_effect=zapis), patch.object(
                self.klient, 'odczytaj_wiele', side_effect=odczyt):
            yield zd

    def test_ciagly_ruch_otwiera_od_pierwszego_zdarzenia(self):
        self.r.obsluz(('dotyk', 1, True))
        t = self.zegar()
        self.ruch_teraz(1 / 16383)
        self.assertTrue(self.suma('mikrofon'), 'pierwszy ruch nie może czekać na bezruch')
        self.assertLess(self.zegar() - t, self.r.zwloka_suwaka)
        self.assertIn((MAIN, 1), self.zapisy())
        self.assertEqual(self.dzwieki_i_slowa(), (['mikrofon_na_antenie'], ['Mikrofon włączony']))
        od = len(self.sym.dziennik)
        poczatek = self.zegar()
        for i in range(1, 11):
            self.zegar.przesun(0.08)
            self.ruch_teraz(i / 12)
            self.r.tick()
            self.assertTrue(self.suma('mikrofon'))
            self.assertAlmostEqual(self.m(FADER), i / 12, places=5)
        self.assertGreater(self.zegar() - poczatek, self.r.zwloka_suwaka)
        self.assertEqual({a for a, _ in self.zapisy(od)}, {FADER})
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))
        self.r.obsluz(('dotyk', 1, False))
        self.tick(0.31)
        self.assertEqual(self.dzwieki_i_slowa(), ([], []))

    def test_regulacja_odczytuje_koncowa_pozycje_dopiero_po_bezruchu(self):
        self.r.obsluz(('dotyk', 1, True))
        self.ruch_teraz(0.2)
        czytaj = self.klient.odczytaj_wiele
        with patch.object(self.klient, 'odczytaj_wiele', wraps=czytaj) as odczyty:
            for wartosc in (0.3, 0.4, 0.5, 0.6, 0.7):
                self.zegar.przesun(0.08)
                self.ruch_teraz(wartosc)
                self.r.tick()
            self.assertFalse(any(FADER in c.args[0] for c in odczyty.call_args_list))
            self.tick(0.31)
            self.assertEqual(sum(FADER in c.args[0] for c in odczyty.call_args_list), 1)
        potwierdzona = self.r.stan.wartosc(FADER)
        assert isinstance(potwierdzona, (float, int))
        self.assertAlmostEqual(potwierdzona, 0.7, places=5)

    def test_nie_zmienia_globalnej_zwloki_ani_nie_czeka_na_dotyk(self):
        self.r.zwloka_suwaka = 10.0
        self.ruch_teraz(0.1)
        self.assertEqual(self.m(MAIN), 1)
        self.ruch_teraz(0.0)
        self.assertEqual(self.m(MAIN), 0)
        self.assertEqual(self.r.zwloka_suwaka, 10.0)

    def test_dol_natychmiast_i_powrot_po_potwierdzonym_main_off(self):
        self.r.obsluz(('klawisz', 'F1_mikrofon'))
        self.dzwieki_i_slowa()
        with self.slad() as zd:
            self.ruch_teraz(0.0)
        self.assertEqual(self.m(MAIN), 0)
        self.assertEqual(self.m(FADER), 0)
        self.assertEqual(self.m(GLOSNIKI), 1)
        powrot = zd.index(('zapis', GLOSNIKI, 1))
        self.assertTrue(any(z[0] == 'odczyt' and z[1].get(MAIN) == 0 for z in zd[:powrot]))
        self.assertEqual(self.slowa(), ['Mikrofon wyłączony. Głośniki włączone'])

    def test_potwierdzenia_prywatnych_i_glosnikow_przed_kazdym_otwarciem(self):
        for cue in ((), ('telefon',), ('zoom',), ('telefon', 'zoom')):
            with self.subTest(cue=cue):
                for zr in cue:
                    self.cue(zr)
                self.dzwieki_i_slowa()
                przed = dict(self.sym.wartosci)
                with self.slad() as zd:
                    self.ruch_teraz(0.4)
                self.assertEqual(self.m(MAIN), 1)
                pierwszy = next(i for i, z in enumerate(zd) if z[0] == 'zapis' and
                                 ((z[1] == FADER and z[2] > 0) or (z[1] == MAIN and z[2] == 1)))
                # Nie tylko kolejność końcowych wartości: po ostatnim zamknięciu
                # muszą być co najmniej dwa rzeczywiste odczyty ciszy.
                wymagane = ([GLOSNIKI] if przed[GLOSNIKI] else []) + [
                    a for a in PRYWATNE if przed[a] > 0]
                for a in wymagane:
                    zamk = max(i for i, z in enumerate(zd[:pierwszy]) if z == ('zapis', a, 0))
                    potw = [z for z in zd[zamk + 1:pierwszy] if z[0] == 'odczyt' and z[1].get(a) == 0]
                    self.assertGreaterEqual(len(potw), 2, (a, zd))
                self.ruch_teraz(0.0)
                self.dzwieki_i_slowa()

    def test_odmowa_potwierdzen_nigdy_nawet_chwilowo_nie_otwiera(self):
        for a in [GLOSNIKI] + PRYWATNE:
            with self.subTest(adres=a):
                if a != GLOSNIKI:
                    self.cue('telefon')
                    self.cue('zoom')
                self.sym.awarie.ignoruj_zapis = ({sciezki.wysylka(9, 3), sciezki.wysylka(9, 4)}
                                                  if a in PRYWATNE[1:] else {a})
                od = len(self.sym.dziennik)
                self.ruch_teraz(0.8)
                self.bez_otwarcia(od)
                self.assertEqual(self.m(MAIN), 0)
                self.sym.awarie.ignoruj_zapis = set()
                self.r.obsluz(('klawisz', 'F3_koniec_rozmowy'))
                self.dzwieki_i_slowa()

    def test_nieznany_przeterminowany_i_rozbrojony_nie_otwiera(self):
        for tryb in ('nieznany', 'stary', 'kontroler', 'rozbrojony'):
            with self.subTest(tryb=tryb):
                if tryb == 'nieznany':
                    self.r.stan.zsynchronizowany = False
                elif tryb == 'stary':
                    self.zegar.przesun(self.r.limit_swiezosci + 1)
                    self.sym.awarie.rozlaczony = True
                elif tryb == 'kontroler':
                    self.r.obsluz(('kontroler', 'test'))
                else:
                    self.r.uzbrojony = False
                od = len(self.sym.dziennik)
                self.ruch_teraz(0.6)
                self.bez_otwarcia(od)
                self.sym.awarie.rozlaczony = False
                self.r.kontroler_polaczony = True
                self.r.uzbrojony = True
                self.r.synchronizuj()
                self.dzwieki_i_slowa()

    def test_utrata_miksera_w_trakcie_przed_otwarciem(self):
        self.sym.awarie.rozlacz_po_zapisach = 1
        od = len(self.sym.dziennik)
        self.ruch_teraz(0.7)
        self.bez_otwarcia(od)
        self.assertFalse(self.r.stan.polaczony)
        self.sym.awarie.rozlaczony = False
        self.sym.awarie.rozlacz_po_zapisach = 0
        self.tick(1.5)
        self.assertEqual(self.m(MAIN), 0)
        self.bez_otwarcia(od)

    def test_utrata_kontrolera_w_trakcie_zamkniec(self):
        oryginal = self.r._dwa_odczyty
        def czytaj(oczekiwane):
            wynik = oryginal(oczekiwane)
            if oczekiwane.get(GLOSNIKI) == 0:
                self.r.kontroler_polaczony = False
            return wynik
        od = len(self.sym.dziennik)
        with patch.object(self.r, '_dwa_odczyty', side_effect=czytaj):
            self.ruch_teraz(0.6)
        self.bez_otwarcia(od)

    def test_kaszel_ruch_nie_zwalnia_a_dol_uniewaznia_powrot(self):
        self.r.obsluz(('klawisz', 'F1_mikrofon'))
        self.r.obsluz(('przycisk', 1, 2))
        od = len(self.sym.dziennik)
        self.ruch_teraz(0.5)
        self.assertNotIn((MAIN, 1), self.zapisy(od))
        self.assertEqual(self.m(MAIN), 0)
        self.ruch_teraz(0.0)
        self.assertEqual(self.m(FADER), 0)
        self.ruch_teraz(0.8)
        self.r.obsluz(('puszczenie', 1, 2))
        self.assertNotIn((MAIN, 1), self.zapisy(od))
        self.assertEqual(self.m(MAIN), 0)

    def test_talkback_przerywa_juz_pierwszy_ruch(self):
        self.r.obsluz(('przycisk', 2, 2))
        self.r.obsluz(('przycisk', 3, 2))
        self.dzwieki_i_slowa()
        self.ruch_teraz(0.7)
        self.assertEqual(self.m(MAIN), 1)
        self.assertEqual(self.r._talkback, set())
        od = len(self.sym.dziennik)
        self.r.obsluz(('puszczenie', 2, 2))
        self.r.obsluz(('puszczenie', 3, 2))
        self.assertEqual(self.zapisy(od), [])

    def test_brak_potwierdzenia_main_off_nie_przywraca_glosnikow(self):
        self.r.obsluz(('klawisz', 'F1_mikrofon'))
        self.sym.awarie.ignoruj_zapis = {MAIN}
        od = len(self.sym.dziennik)
        self.ruch_teraz(0.0)
        self.assertNotIn((GLOSNIKI, 1), self.zapisy(od))
        self.assertEqual(self.m(GLOSNIKI), 0)
