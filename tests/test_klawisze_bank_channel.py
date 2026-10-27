"""Bank, Channel i OK: surowe MIDI, prawdziwy TCP atrapy, bez sprzętu."""
import unittest
from unittest.mock import patch

from mostek import emisja
from mostek.informacja import Tryb
from mostek.xtouch import MapaMC
from tests.atrapa_playoutu import SerwerPlayoutu, zamkniety_port
from tests.pomoc import TestZSymulatorem


class TestBankChannel(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.s = SerwerPlayoutu(True)
        self.addCleanup(self.s.zamknij)
        self.r.emisja = emisja.SARA(self.s.port, limit_s=0.2)
        self.mapa = MapaMC(self.u.xtouch)

    def nuta(self, n):
        self.zegar.przesun(0.2)
        self.r.zglos(self.mapa.zdarzenie([0x90, n, 127]))

    def otworz(self):
        self.nuta(101)
        self.assertEqual(self.slowa(), ['Punkty miksu: Żółć, Utwór 0, 3:45. Cue 0:00,5'])

    def test_bank_prawo_poza_trybem_wolny_bez_tcp_i_miksera(self):
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        for n in (47,):
            with self.subTest(nuta=n):
                self.nuta(n)
                self.assertEqual(self.slowa(), ['Klawisz wolny'])
                self.assertEqual(self.s.polecenia, [])
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania)

    def test_bank_zapis_i_anuluj_rownowazne_starym(self):
        for nowy, stary, komenda, tekst in (
                (46, 80, 'MixSave', 'Zapisano punkty miksu'),
                (47, 82, 'MixCancel', 'Punkty miksu porzucone')):
            wyniki = []
            for n in (stary, nowy):
                with self.subTest(nuta=n):
                    self.otworz()
                    self.nuta(92)
                    self.assertEqual(self.slowa(), [])
                    self.nuta(84)
                    self.assertEqual(self.slowa(), ['Cue ustawione'])
                    od = len(self.s.polecenia)
                    self.nuta(n)
                    slowa = self.slowa()
                    self.assertEqual(slowa, [tekst])
                    self.assertIn(komenda, self.s.polecenia[od:])
                    self.assertFalse(self.r._tor_emisji.tryb_miksu)
                    wyniki.append(([p for p in self.s.polecenia[od:] if p != 'MixInfo'], slowa))
                # Kolejna próba zaczyna od zamkniętej sesji także na czerwonym kodzie.
                if self.r._tor_emisji.tryb_miksu:
                    self.nuta(82); self.slowa()
                self.s.miks.zapisane['cue'] = 500
            if len(wyniki) == 2:
                self.assertEqual(wyniki[0], wyniki[1])

    def test_ok_w_miksie_ustawia_punkt_po_jog_bez_znacznika(self):
        self.otworz()
        od = len(self.s.polecenia)
        with self.r._tor_emisji._warunek:
            self.r.zglos(('jog', 1))
            self.nuta(100)
        self.assertEqual(self.slowa(), ['Cue ustawione'])
        self.assertEqual(self.s.miks.punkty['cue'], 600)
        polecenia = self.s.polecenia[od:]
        self.assertIn('MixSet', polecenia)
        self.assertLess(polecenia.index('MixPos=+0.1'), polecenia.index('MixSet'))
        self.assertNotIn('CheckToggle', polecenia)
        self.assertEqual(self.s.checked, {})
        self.nuta(84)
        self.assertEqual(self.slowa(), ['Cue ustawione'])

    def test_ok_poza_miksem_dalej_przelacza_znacznik(self):
        self.nuta(100)
        self.assertEqual(self.slowa(), ['1. Żółć, Utwór 0, 3:45, niezaznaczono'])
        self.assertIn('CheckToggle', self.s.polecenia)
        self.assertFalse(any(p.startswith('Mix') for p in self.s.polecenia))
        self.assertEqual(self.s.checked, {0: False})

    def test_channel_lewo_jak_f7_w_obu_trybach_i_programach(self):
        with SerwerPlayoutu() as spl:
            for serwer, adapter in ((self.s, emisja.SARA(self.s.port)),
                                   (spl, emisja.StationPlaylistTCP(spl.port))):
                self.r.emisja = adapter
                for miks in ((False, True) if serwer.sara else (False,)):
                    if miks:
                        self.otworz()
                    wyniki = []
                    for n in (60, 48):
                        with self.subTest(sara=serwer.sara, miks=miks, nuta=n):
                            serwer.auto = False
                            przebieg = []
                            for tekst in ('Automat włączony', 'Automat wyłączony'):
                                od = len(serwer.polecenia)
                                self.nuta(n)
                                slowa = self.slowa()
                                self.assertEqual(slowa, [tekst])
                                polecenia = [p for p in serwer.polecenia[od:] if not p.startswith('Mix')]
                                self.assertEqual(polecenia, ['Helo', 'Auto', 'Helo', 'Stat'])
                                przebieg.append((polecenia, slowa, serwer.auto))
                            wyniki.append(przebieg)
                    if len(wyniki) == 2:
                        self.assertEqual(wyniki[0], wyniki[1])
                    if miks:
                        self.nuta(82); self.slowa()

    def test_channel_prawo_czas_anteny_sara_i_spl_bez_zmian(self):
        with SerwerPlayoutu() as spl:
            for serwer, adapter in ((self.s, emisja.SARA(self.s.port)),
                                   (spl, emisja.StationPlaylistTCP(spl.port))):
                self.r.emisja = adapter
                serwer.gra, serwer.curr, serwer.rem = True, 7, '83000'
                for miks in ((False, True) if serwer.sara else (False,)):
                    if miks:
                        self.otworz()
                        self.nuta(83); self.slowa()  # PFL innego utworu niż antenowy
                    od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
                    przed = (serwer.gra, serwer.curr, serwer.indeks, serwer.auto,
                             dict(serwer.checked), serwer.miks.pozycja, serwer.miks.odsluch)
                    for tryb in Tryb:
                        with self.subTest(sara=serwer.sara, miks=miks, tryb=tryb):
                            self.info.tryb = tryb
                            poczatek = len(serwer.polecenia)
                            self.nuta(49)
                            self.assertEqual(self.dzwieki_i_slowa(), ([], ['Zostało 1 minuta 23 sekundy']))
                            self.assertEqual([p for p in serwer.polecenia[poczatek:] if p != 'MixInfo'],
                                             ['Helo', 'Stat', 'Rem'])
                    self.assertEqual((serwer.gra, serwer.curr, serwer.indeks, serwer.auto,
                                      dict(serwer.checked), serwer.miks.pozycja, serwer.miks.odsluch), przed)
                    self.assertEqual(self.zapisy(od), [])
                    with self.subTest(sara=serwer.sara, miks=miks, bez_odczytu_miksera=True):
                        self.assertEqual(len(self.sym.zapytania), pytania)
                    if miks:
                        self.nuta(82); self.slowa()

    def test_channel_prawo_stop_i_pauza_bez_czasu_i_rem(self):
        with SerwerPlayoutu() as spl:
            for serwer, adapter in ((self.s, emisja.SARA(self.s.port)),
                                   (spl, emisja.StationPlaylistTCP(spl.port))):
                self.r.emisja = adapter
                serwer.milcz.update(('rem', 'this', 'next'))
                for miks in ((False, True) if serwer.sara else (False,)):
                    if miks:
                        self.otworz()
                    for pauza, tekst in ((False, 'Nic nie gra'), (True, 'Pauza')):
                        with self.subTest(sara=serwer.sara, miks=miks, pauza=pauza):
                            serwer.gra, serwer.pauza = False, pauza
                            od = len(serwer.polecenia)
                            self.nuta(49)
                            self.assertEqual(self.slowa(), [tekst])
                            self.assertEqual([p for p in serwer.polecenia[od:] if p != 'MixInfo'], ['Helo', 'Stat'])
                    if miks:
                        self.nuta(82); self.slowa()

    def test_channel_prawo_brak_programu_i_zapas_spl(self):
        brak = emisja.WyborProgramu('sara', {'sara_port': zamkniety_port()}, okno_spl=lambda: False)
        zapas = emisja.StationPlaylist(wyslij_komunikat=lambda w, l: 0)
        for adapter, tekst in ((None, 'Nie wybrano programu emisyjnego'),
                               (brak, 'Nie odpowiada żaden program emisyjny'),
                               (zapas, self.u.tekst('emisja_wymaga_tcp'))):
            with self.subTest(adapter=adapter):
                self.r.emisja = adapter
                self.nuta(49)
                self.assertEqual(self.slowa(), [tekst])
        self.assertEqual(self.s.polecenia, [])

    def test_channel_prawo_rem_zero_ujemny_i_bledny(self):
        self.s.gra = True
        for rem, tekst in (('0', 'Zostało 0 sekund'), ('-1', 'Zostało 0 sekund'),
                           ('bledny', self.u.tekst('emisja_niepotwierdzona'))):
            with self.subTest(rem=rem):
                self.s.rem = rem
                od = len(self.s.polecenia)
                self.nuta(49)
                self.assertEqual(self.slowa(), [tekst])
                self.assertEqual(self.s.polecenia[od:], ['Helo', 'Stat', 'Rem'])

    def test_nauka_nowe_nazwy_bez_polecen(self):
        self.nuta(91); self.slowa()
        oczekiwane = {
            46: 'Bank w lewo, w punktach miksu zapis, poza nimi odtwarzacz',
            47: 'Bank w prawo, w punktach miksu anulowanie, poza nimi wolny',
            48: 'Channel w lewo, automat',
            49: 'Channel w prawo, czas do końca utworu na antenie',
            60: 'F7, automat',
            100: 'Zoom, w punktach miksu ustaw punkt, poza nimi znacznik do emisji',
        }
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        for n, tekst in oczekiwane.items():
            with self.subTest(nuta=n):
                self.nuta(n)
                self.assertEqual(self.slowa(), [tekst])
        self.assertEqual(self.s.polecenia, [])
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania)

    def test_nowe_klawisze_bez_miksera_i_bez_jego_blokady(self):
        self.r.stan.polaczony = False
        with patch.object(self.r, '_zapewnij_swiezosc', side_effect=AssertionError('odczyt MR18')):
            for miks in (False, True):
                if miks:
                    self.otworz()
                for n in (48, 49, 100, 46, 47):
                    with self.subTest(miks=miks, nuta=n):
                        if miks and not self.r._tor_emisji.tryb_miksu:
                            self.otworz()
                        with patch.object(self.r, 'obsluz', side_effect=AssertionError('tor MR18')):
                            self.nuta(n)
                        self.slowa()

    def test_mapa_bez_kolizji_i_puszczenie_bez_akcji(self):
        mapa = self.u.xtouch['klawisze']
        self.assertEqual(len(set(mapa.values())), len(mapa))
        for n in (46, 47, 48, 49, 100):
            self.assertIn(str(n), mapa)
            self.assertEqual(self.mapa.nuta_klawisza[mapa[str(n)]], n)
            self.assertIsNone(self.mapa.zdarzenie([0x90, n, 0]))
            self.assertIsNone(self.mapa.zdarzenie([0x80, n, 0]))
        for n, akcja in ((46, 'MixSave'), (47, 'MixCancel'), (100, 'MixSet')):
            self.assertEqual(self.u.xtouch['punkty_miksu'][mapa[str(n)]], akcja)
        for n in (48, 49, 60):
            self.assertNotIn(mapa[str(n)], self.u.xtouch['punkty_miksu'])


if __name__ == '__main__':
    unittest.main()
