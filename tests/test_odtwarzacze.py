"""Bank w lewo: numery z prawdziwego TCP atrapy, nie z czasu ani tytułu."""
import unittest
from unittest.mock import Mock, patch

from mostek import emisja
from mostek.informacja import Tryb
from mostek.xtouch import MapaMC
from tests.atrapa_playoutu import SerwerPlayoutu, zamkniety_port
from tests.pomoc import TestZSymulatorem


class TestOdtwarzacze(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.s = SerwerPlayoutu(True)
        self.addCleanup(self.s.zamknij)
        self.s.odpowiedzi['players'] = '2'
        self.r.emisja = emisja.SARA(self.s.port, limit_s=0.2)
        self.mapa = MapaMC(self.u.xtouch)

    def nuta(self, n):
        self.zegar.przesun(0.2)
        self.r.zglos(self.mapa.zdarzenie([0x90, n, 127]))

    def test_bank_poza_trybem_numery_bez_czasu_tytulu_i_miksera(self):
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        przed = (self.s.gra, self.s.curr, self.s.indeks, self.s.auto, dict(self.s.checked))
        self.s.milcz.update(('stat', 'this', 'next', 'rem', 'selectindex', 'currindex'))
        for tryb in Tryb:
            self.info.tryb = tryb
            for odpowiedz, tekst in (('2', 'Odtwarzacz 2'), ('1,2', 'Odtwarzacze 1 i 2'),
                                     ('1,2,3', 'Odtwarzacze 1, 2 i 3'), ('-', 'Nic nie gra'),
                                     ('1,3,10,12', 'Odtwarzacze 1, 3, 10 i 12')):
                with self.subTest(tryb=tryb, odpowiedz=odpowiedz):
                    self.s.odpowiedzi['players'] = odpowiedz
                    start = len(self.s.polecenia)
                    self.nuta(46)
                    self.assertEqual(self.dzwieki_i_slowa(), ([], [tekst]))
                    self.assertEqual(self.s.polecenia[start:], ['Helo', 'Players'])
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania)
        self.assertEqual((self.s.gra, self.s.curr, self.s.indeks, self.s.auto, self.s.checked), przed)

    def test_bank_w_miksie_zapis_bez_players_a_po_wyjsciu_odczyt(self):
        self.nuta(101)
        self.assertEqual(self.slowa(), ['Punkty miksu: Żółć, Utwór 0, 3:45. Cue 0:00,5'])
        self.nuta(92); self.slowa()
        self.nuta(100)
        self.assertEqual(self.slowa(), ['Cue ustawione'])
        start = len(self.s.polecenia)
        self.nuta(46)
        self.assertEqual(self.slowa(), ['Zapisano punkty miksu'])
        self.assertIn('MixSave', self.s.polecenia[start:])
        self.assertNotIn('Players', self.s.polecenia)
        self.assertFalse(self.r._tor_emisji.tryb_miksu)
        self.assertEqual(self.s.miks.zapisane['cue'], 5500)
        self.nuta(46)
        self.assertEqual(self.slowa(), ['Odtwarzacz 2'])
        self.assertEqual(self.s.polecenia[-2:], ['Helo', 'Players'])

    def test_bank_spl_bez_zapytania_tcp_i_sendmessage(self):
        with SerwerPlayoutu() as spl:
            wyslij = Mock(side_effect=AssertionError('SendMessage'))
            for adapter in (emisja.StationPlaylistTCP(spl.port),
                            emisja.StationPlaylist(wyslij_komunikat=wyslij),
                            emisja.WyborProgramu('spl', {'spl_port': spl.port},
                                                zapas=emisja.StationPlaylist(wyslij), okno_spl=lambda: True)):
                with self.subTest(adapter=type(adapter).__name__):
                    self.r.emisja = adapter
                    self.r._tor_emisji._blad_czas = float('-inf')
                    self.nuta(46)
                    self.assertEqual(self.slowa(), ['Numer odtwarzacza jest tylko w SARZE'])
                    self.assertEqual(spl.polecenia, [])
            wyslij.assert_not_called()
        self.assertEqual(self.s.polecenia, [])

    def test_auto_wybor_spl_tylko_helo_bez_players_i_fallbacku(self):
        with SerwerPlayoutu() as spl:
            self.r.emisja = emisja.WyborProgramu('auto', {'spl_port': spl.port, 'sara_port': self.s.port},
                                                okno_spl=lambda: True)
            self.nuta(46)
            self.assertEqual(self.slowa(), ['Numer odtwarzacza jest tylko w SARZE'])
            self.assertEqual(spl.polecenia, ['Helo'])
            self.assertEqual(self.s.polecenia, [])

    def test_auto_wybor_sary_i_blad_danych_bez_fallbacku(self):
        with SerwerPlayoutu() as spl:
            self.r.emisja = emisja.WyborProgramu('auto', {'preferowany': 'sara', 'spl_port': spl.port,
                                                        'sara_port': self.s.port}, okno_spl=lambda: True)
            self.nuta(46)
            self.assertEqual(self.slowa(), ['Odtwarzacz 2'])
            self.s.odpowiedzi['players'] = 'ERR unknown'
            self.nuta(46)
            self.assertEqual(self.slowa(), ['SARA podała błędne numery odtwarzaczy'])
            self.assertEqual(self.s.polecenia, ['Helo', 'Players', 'Helo', 'Players'])
            self.assertEqual(spl.polecenia, [])

    def test_bledne_dane_odrebne_od_braku_odpowiedzi(self):
        for odpowiedz in ('śmieci', '', '0', '2,1', '1,1', '1,2,', '1, 2', '01', '-1', 'ERR unknown'):
            with self.subTest(odpowiedz=odpowiedz):
                self.s.odpowiedzi['players'] = odpowiedz
                self.r._tor_emisji._blad_czas = float('-inf')
                start = len(self.s.polecenia)
                self.nuta(46)
                self.assertEqual(self.slowa(), ['SARA podała błędne numery odtwarzaczy'])
                self.assertEqual(self.s.polecenia[start:], ['Helo', 'Players'])
        self.s.milcz.add('players')
        self.nuta(46)
        self.assertEqual(self.slowa(), [self.u.tekst('emisja_niepotwierdzona')])
        self.s.milcz.clear()
        self.s.odpowiedzi['players'] = '2'
        self.nuta(46)
        self.assertEqual(self.slowa(), ['Odtwarzacz 2'])

    def test_brak_programu_i_lacza_jak_inne_akcje(self):
        port = zamkniety_port()
        for adapter, tekst in ((None, 'Nie wybrano programu emisyjnego'),
                               (emisja.WyborProgramu('sara', {'sara_port': port}),
                                'Nie odpowiada żaden program emisyjny'),
                               (emisja.SARA(port), self.u.tekst('emisja_niepotwierdzona'))):
            with self.subTest(adapter=adapter):
                self.r.emisja = adapter
                self.nuta(46)
                self.assertEqual(self.slowa(), [tekst])
        self.assertEqual(self.s.polecenia, [])

    def test_nauka_nowy_opis_bez_zapytan(self):
        self.nuta(91); self.slowa()
        self.nuta(46)
        self.assertEqual(self.slowa(), ['Bank w lewo, w punktach miksu zapis, poza nimi odtwarzacz'])
        self.assertEqual(self.s.polecenia, [])

    def test_bez_lacznosci_i_blokady_miksera(self):
        self.r.stan.polaczony = False
        with patch.object(self.r, '_zapewnij_swiezosc', side_effect=AssertionError('odczyt MR18')):
            with patch.object(self.r, 'obsluz', side_effect=AssertionError('tor MR18')):
                self.nuta(46)
        self.assertEqual(self.slowa(), ['Odtwarzacz 2'])

    def test_komunikaty_z_ustawien(self):
        self.u.komunikaty.update(emisja_odtwarzacz='Gra slot {numer}', emisja_odtwarzacze='Grają sloty {lista}',
                                 emisja_odtwarzacze_spojnik=' oraz ')
        self.nuta(46)
        self.assertEqual(self.slowa(), ['Gra slot 2'])
        self.s.odpowiedzi['players'] = '1,2,3'
        self.nuta(46)
        self.assertEqual(self.slowa(), ['Grają sloty 1, 2 oraz 3'])


class TestProtokolOdtwarzaczy(unittest.TestCase):
    def test_parser_odrzuca_niekanoniczne_odpowiedzi(self):
        with SerwerPlayoutu(True) as sara:
            for odpowiedz in ('0', '01', '-2', '+2', '2.0', '2,1', '2,2', '1,,2', '1,', ',1',
                              ' 2', '2 ', '２', '1;2', '-', '1,10', '9' * 5000):
                with self.subTest(odpowiedz=odpowiedz[:40]):
                    sara.odpowiedzi['players'] = odpowiedz
                    if odpowiedz in ('-', '1,10'):
                        wynik = emisja.SARA(sara.port).wykonaj('odtwarzacz')
                        self.assertEqual(wynik.odtwarzacze, () if odpowiedz == '-' else (1, 10))
                    else:
                        with self.assertRaises(emisja.BladEmisji) as blad:
                            emisja.SARA(sara.port).wykonaj('odtwarzacz')
                        self.assertEqual(type(blad.exception).__name__, 'BledneDaneOdtwarzaczy')

    def test_zapora_players_tylko_sara_bez_argumentow(self):
        for p in ('Players', 'players', 'PLAYERS'):
            self.assertTrue(emisja.dozwolone_polecenie(p, sara=True))
            self.assertFalse(emisja.dozwolone_polecenie(p, sara=False))
        for p in ('Players=', 'Players=1', 'Players\nPlay', 'Players\r', 'Players,Play', 'Players '):
            for sara in (False, True):
                self.assertFalse(emisja.dozwolone_polecenie(p, sara=sara), p)

    def test_zapora_na_gniezdzie_spl(self):
        with SerwerPlayoutu() as spl:
            s = emisja.SesjaTCP(spl.port)
            try:
                for p in ('Players', 'PLAYERS', 'Players='):
                    try:
                        s.wyslij(p)
                    except ValueError:
                        pass
                s.pytaj('Helo')  # bariera odczytu listy poleceń po stronie serwera
                self.assertEqual(spl.polecenia, ['Helo', 'Helo'])
            finally:
                s.zamknij()

    def test_sesja_spl_odmawia_przed_wyslaniem(self):
        with SerwerPlayoutu() as spl:
            s = emisja.SesjaTCP(spl.port)
            try:
                with self.assertRaises(emisja.WymagaSary):
                    s.wykonaj('odtwarzacz')
                self.assertEqual(spl.polecenia, ['Helo'])
            finally:
                s.zamknij()


if __name__ == '__main__':
    unittest.main()
