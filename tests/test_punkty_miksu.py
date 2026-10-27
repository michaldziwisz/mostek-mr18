"""Tryb stołu przeciw prawdziwemu TCP atrapy, bez SARY i sprzętu."""
import time
import unittest
from unittest.mock import patch

from mostek import emisja
from mostek.xtouch import MapaMC
from mostek.mowa import AtrapaMowy, KolejkaMowy
from tests.atrapa_playoutu import SerwerPlayoutu
from tests.pomoc import TestZSymulatorem


class TestZaporaMiksu(unittest.TestCase):
    def test_biala_lista_tylko_sara(self):
        dobre = ['MixOpen', 'MixInfo', 'MixSet', 'MixClear', 'MixUndo', 'MixSave',
                 'MixCancel', 'MixPlay', 'MixPlayPoint', 'MixPlayMix', 'MixStop',
                 'MixPos=+0.1', 'MixPos=-5', 'MixPos=@83.4', 'MixNudge=-0.1',
                 'MixNudge=+1', 'MixPoint=next', 'MixPoint=prev']
        dobre += ['MixPoint=' + p for p in ('cue', 'intro', 'outro', 'segue',
                  'segue_fade', 'overlap', 'loop_start', 'loop_end')]
        for p in dobre:
            with self.subTest(p=p):
                self.assertTrue(emisja.dozwolone_polecenie(p.swapcase(), sara=True))
                self.assertFalse(emisja.dozwolone_polecenie(p, sara=False))
        for p in ('Mix', 'MixScript', 'MixOpen=x', 'MixPos=1', 'MixPos=+nan',
                  'MixPos=+inf', 'MixPos=+1e3', 'MixPos=+1,5', 'MixPos=@-1',
                  'MixNudge=@1', 'MixNudge=1', 'MixPoint=all', 'MixPos=+1\nPlay',
                  'MixSave\r', 'MixPos=+1,Play', 'MixPoint=next|Play'):
            self.assertFalse(emisja.dozwolone_polecenie(p, sara=True), p)

    def test_zapora_na_gniezdzie_spl(self):
        with SerwerPlayoutu() as spl:
            s = emisja.SesjaTCP(spl.port)
            try:
                for p in ('MixOpen', 'MixSet', 'MixPos=+1', 'MixSave'):
                    try:
                        s.wyslij(p)
                    except ValueError:
                        pass
                s.pytaj('Helo')  # bariera, nie samo sprawdzenie listy w pamięci
                self.assertEqual(spl.polecenia, ['Helo', 'Helo'])
            finally:
                s.zamknij()

    def test_mowa_ucina_tylko_swoj_tryb(self):
        a = AtrapaMowy()
        k = KolejkaMowy(a, alarm=None)
        for tekst, klucz in [('Pozycja 1', 'emisja-miks'), ('Pozycja 2', 'emisja-miks'),
                             ('Mikrofon włączony', 'm'), ('Pozycja 3', 'emisja-miks'),
                             ('Automat czeka', 'emisja-hold'), ('Pozycja 4', 'emisja-miks')]:
            k.powiedz(tekst, klucz=klucz)
            k.oproznij()
        self.assertEqual(a.przerwania, 1)


class TestPunktyMiksu(TestZSymulatorem):
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

    def test_jog_w_trybie_nie_rusza_playlisty_po_wyjsciu_rusza(self):
        self.otworz()
        przed = self.s.indeks
        self.r.zglos(('jog', 1))
        self.assertEqual(self.slowa(), [])  # decyzja Michała: zmiany bez czasu
        self.nuta(59)
        self.assertEqual(self.slowa(), ['Pozycja 0:00,6. Cue 0:00,5'])
        self.assertFalse(any(p.startswith('SelectIndex') for p in self.s.polecenia))
        self.assertEqual(self.s.indeks, przed)
        self.nuta(82); self.slowa()
        self.r.zglos(('jog', 1)); self.slowa()
        self.assertIn('SelectIndex=+', self.s.polecenia)

    def test_szybki_jog_sumowany_mowi_tylko_koniec(self):
        self.otworz()
        # Zegar kroku niezależny od planisty wątku. Pierwszy krok 0,1 s,
        # kolejne 19 szybkich kroków po 1 s. Seria kończy się na 19,6 s.
        start = time.monotonic()
        with patch('mostek.playout.time.monotonic', return_value=start):
            with self.r._tor_emisji._warunek:
                for _ in range(20):
                    self.r.zglos(('jog', 1))
        slowa = self.slowa()
        p = [p for p in self.s.polecenia if p.startswith('MixPos=')]
        self.assertGreater(len(p), 0)
        self.assertLess(len(p), 20)
        self.assertAlmostEqual(sum(float(v.split('=')[1]) for v in p), 19.1)
        self.assertEqual(slowa, [])
        self.nuta(59)
        self.assertEqual(self.slowa(), ['Pozycja 0:19,6. Cue 0:00,5'])

    def test_mapa_wszystkich_klawiszy_i_rewind(self):
        self.otworz()
        mapa = {91:'MixPos=-5', 92:'MixPos=+5', 98:'MixPoint=prev', 99:'MixPoint=next',
                96:'MixNudge=+0.1', 97:'MixNudge=-0.1', 84:'MixSet', 87:'MixClear',
                83:'MixPlay', 85:'MixPlayPoint', 86:'MixPlayMix', 81:'MixUndo', 59:'MixInfo'}
        for nuta, polecenie in mapa.items():
            od = len(self.s.polecenia)
            self.nuta(nuta); self.slowa()
            self.assertIn(polecenie, self.s.polecenia[od:], nuta)
            self.assertIsNone(self.r._nauka_od)
        self.nuta(82)
        self.assertEqual(self.slowa(), ['Punkty miksu porzucone'])
        self.nuta(91)
        self.assertIn('Nauka klawiszy', self.slowa()[0])

    def test_transport_i_f1_f7_bez_zmian(self):
        def przebieg():
            wyniki = []
            for n in (94, 93, 93, 95, 60, 54, 54):
                od = len(self.s.polecenia)
                self.nuta(n)
                slowa = self.slowa()
                # Inne połączenie MixInfo do dozoru nie wpływa na antenę.
                polecenia = [p for p in self.s.polecenia[od:] if not p.startswith('Mix')]
                wyniki.append((polecenia, slowa, self.suma('mikrofon'), self.s.hold))
            return wyniki
        poza = przebieg()
        self.s.auto = False
        self.otworz()
        self.assertEqual(przebieg(), poza)
        self.nuta(59)
        self.assertTrue(self.slowa()[0].startswith('Pozycja'))

    def test_spl_odmowa_bez_mix(self):
        with SerwerPlayoutu() as spl:
            for a in (emisja.StationPlaylistTCP(spl.port), emisja.StationPlaylist(),
                      emisja.WyborProgramu('auto', {'spl_port':spl.port, 'sara_port':self.s.port},
                                          okno_spl=lambda: True), None):
                self.r.emisja = a
                self.nuta(101)
                self.assertEqual(self.slowa(), ['Punkty miksu tylko w SARZE'])
                self.assertFalse(any(p.lower().startswith('mix') for p in spl.polecenia))
                self.assertFalse(any(p.lower().startswith('mix') for p in self.s.polecenia))

    def test_scrub_zmiany_cancel_i_walidacja(self):
        self.otworz()
        self.nuta(99); self.slowa()
        self.nuta(84)
        self.assertEqual(self.slowa(), ['Intro ustawione'])
        self.nuta(101)
        self.assertEqual(self.slowa(), ['Niezapisane zmiany. Save zapisuje, Cancel porzuca'])
        self.nuta(80)
        self.assertEqual(self.slowa(), ['Nie zapisano: cue, intro i outro w złej kolejności'])
        self.nuta(59)
        self.assertIn('Intro 0:00,5', self.slowa()[0])
        self.nuta(82)
        self.assertEqual(self.slowa(), ['Punkty miksu porzucone'])
        self.nuta(97); self.slowa()
        self.assertIn('SelectIndex=+', self.s.polecenia)

    def test_start_na_antenie_nie_konczy_sesji_save_obie_odpowiedzi(self):
        for pozycja, tekst in [('102', 'Zapisano. Przejście za 12 sekund'),
                               ('80', 'Zapisano. Punkt przejścia już minął, przejście następuje teraz')]:
            self.otworz()
            self.r._tor_emisji.zlec('miks', 'MixPoint=segue')
            self.r._tor_emisji.zlec('miks', 'MixPos=@' + pozycja)
            self.slowa()
            self.nuta(84); self.slowa()
            self.nuta(94); self.slowa()
            self.nuta(80)
            self.assertEqual(self.slowa(), [tekst])
            self.nuta(59)
            self.assertTrue(self.slowa()[0].startswith('Gra:'))
            self.s.indeks = 0

    def test_utrata_polaczenia_wychodzi_bez_ponowienia(self):
        self.otworz()
        self.s.zerwij.add('mixinfo')
        self.nuta(59)
        self.assertEqual(self.slowa(), ['Punkty miksu zamknięte, SARA nie odpowiada'])
        self.assertEqual(self.s.polecenia.count('MixOpen'), 1)
        self.nuta(97); self.slowa()
        self.assertIn('SelectIndex=+', self.s.polecenia)

    def test_scrub_bez_zmian_i_save(self):
        self.otworz()
        self.nuta(101); self.slowa()
        self.assertIn('MixCancel', self.s.polecenia)
        self.otworz()
        self.nuta(80)
        self.assertEqual(self.slowa(), ['Zapisano punkty miksu'])

    def test_odmowy_busy_empty_pfl_petla_i_nosession(self):
        for blad, tekst in [('busy', 'Okno punktów miksu jest otwarte w SARZE'),
                            ('empty', 'Brak utworu pod kursorem')]:
            self.s.odpowiedzi['mixopen'] = 'ERR ' + blad
            self.nuta(101)
            self.assertEqual(self.slowa(), [tekst])
            self.assertFalse(self.r._tor_emisji.tryb_miksu)
        self.s.odpowiedzi.clear()
        self.otworz()
        self.s.miks.pfl = False
        for n in (83, 85, 86, 96):
            self.nuta(n)
            self.assertEqual(self.slowa(), ['Brak urządzenia odsłuchu PFL w SARZE'])
            self.assertTrue(self.r._tor_emisji.tryb_miksu)
        self.s.odpowiedzi['mixsave'] = 'ERR invalid|petla'
        self.nuta(80)
        self.assertEqual(self.slowa(), ['Nie zapisano: początek pętli za końcem'])
        self.assertTrue(self.r._tor_emisji.tryb_miksu)
        self.s.odpowiedzi['mixinfo'] = 'ERR nosession'
        self.nuta(59)
        self.assertEqual(self.slowa(), ['Punkty miksu zamknięte, SARA nie odpowiada'])
        self.assertFalse(self.r._tor_emisji.tryb_miksu)

    def test_jog_marker_zachowuja_kolejnosc(self):
        self.otworz()
        self.nuta(99); self.slowa()
        with self.r._tor_emisji._warunek:
            self.r.zglos(('jog', 1))
            self.nuta(84)
        self.assertEqual(self.slowa(), ['Intro ustawione'])
        self.assertEqual(self.s.miks.punkty['intro'], 600)
        self.assertLess(self.s.polecenia.index('MixPos=+0.1'), self.s.polecenia.index('MixSet'))

    def test_jog_powolny_i_ujemny_nie_akumuluje_float(self):
        self.otworz()
        for kier, tekst in [(1, 'Pozycja 0:00,6. Cue 0:00,5'), (-1, 'Pozycja 0:00,5. Cue 0:00,5')]:
            time.sleep(0.1)  # wolny obrót: krok 0,1 s, nie szybki 1 s
            self.r.zglos(('jog', kier))
            self.assertEqual(self.slowa(), [])
            self.nuta(59)
            self.assertEqual(self.slowa(), [tekst])
        self.assertIn('MixPos=-0.1', self.s.polecenia)

    def test_wszystkie_punkty_wartosci_undo_i_odsluch(self):
        self.otworz()
        nazwy = ['Intro', 'Outro', 'Segue', 'Segue fade', 'Overlap', 'Początek pętli', 'Koniec pętli']
        for nazwa in nazwy:
            self.nuta(99)
            self.assertEqual(self.slowa(), [nazwa + ' nieustawione'])
        self.nuta(99)
        self.assertEqual(self.slowa(), ['Cue 0:00,5'])
        self.nuta(87)
        self.assertEqual(self.slowa(), ['Cue usunięte'])
        self.nuta(81)
        self.assertEqual(self.slowa(), ['Cue 0:00,5'])
        self.nuta(83)
        self.assertEqual(self.slowa(), ['Odsłuch od pozycji'])
        self.nuta(83)
        self.assertEqual(self.slowa(), ['Odsłuch punktów miksu zatrzymany'])
        self.nuta(85)
        self.assertEqual(self.slowa(), ['Odsłuch punktu'])
        self.nuta(86)
        self.assertEqual(self.slowa(), ['Odsłuch przejścia'])
        self.r._tor_emisji.zlec('miks', 'MixStop')
        self.assertEqual(self.slowa(), ['Odsłuch punktów miksu zatrzymany'])

    def test_jedno_gniazdo_przezywa_limit_operacji_i_cudze_polaczenia(self):
        self.otworz()
        wlasciciel = self.s.miks.wlasciciel
        self.nuta(54); self.slowa()
        self.nuta(94); self.slowa()
        self.assertIs(self.s.miks.wlasciciel, wlasciciel)
        time.sleep(3.1)  # pierwotny SesjaTCP.termin wygasłby po 3 sekundach
        self.nuta(59)
        self.assertEqual(self.slowa(), ['Pozycja 0:00,5. Cue 0:00,5'])
        self.assertIs(self.s.miks.wlasciciel, wlasciciel)
        self.assertEqual(self.s.polecenia.count('MixOpen'), 1)
        self.r.zamknij_emisje()
        with self.s.warunek:
            self.assertTrue(self.s.warunek.wait_for(lambda: self.s.miks.wlasciciel is None, 1))
        self.assertEqual(self.s.miks.odsluch, 'brak')

    def test_utrata_wykryta_takze_bez_klawisza(self):
        self.otworz()
        ile = self.s.polecenia.count('MixInfo')
        self.s.zerwij.add('mixinfo')
        self.assertTrue(self.s.czekaj_na('MixInfo', ile=ile + 1, timeout=2))
        self.assertEqual(self.slowa(), ['Punkty miksu zamknięte, SARA nie odpowiada'])
        self.assertFalse(self.r._tor_emisji.tryb_miksu)

    def test_zmiany_pozycji_i_punktu_bez_czytania_czasu(self):
        # Decyzja Michała 25.10.2026 (wariant 1): kółko, REWIND/FFWD i góra/dół
        # nie mówią czasu, słychać tylko odsłuch PFL. Czas: F6 i lewo/prawo.
        self.otworz()
        self.nuta(99); self.slowa()
        od = len(self.s.polecenia)
        for zdarzenie in (('jog', 1), ('jog', -1)):
            self.r.zglos(zdarzenie)
            self.assertEqual(self.slowa(), [], zdarzenie)
        for n in (91, 92, 96, 97, 96):
            self.nuta(n)
            self.assertEqual(self.slowa(), [], n)
        wyslane = self.s.polecenia[od:]
        for p in ('MixPos=-5', 'MixPos=+5', 'MixNudge=+0.1', 'MixNudge=-0.1'):
            self.assertIn(p, wyslane)
        self.nuta(98)
        self.assertEqual(self.slowa(), ['Cue 0:00,5'])
        self.nuta(99)
        intro = self.slowa()
        self.assertEqual(len(intro), 1)
        self.assertRegex(intro[0], r'^Intro [0-9]+:[0-9]{2},[0-9]$')  # wybór punktu mówi czas
        self.nuta(59)
        self.assertRegex(self.slowa()[0], r'^Pozycja [0-9]+:[0-9]{2},[0-9]\. ' + intro[0] + '$')
        self.nuta(84)
        self.assertEqual(self.slowa(), ['Intro ustawione'])

    def test_nie_ma_zapisow_ani_odczytow_miksera_od_punktow(self):
        od, pytania = len(self.sym.dziennik), len(self.sym.zapytania)
        self.r.stan.polaczony = False
        self.otworz()
        for n in (91, 92, 98, 99, 96, 97, 84, 87, 83, 85, 86, 81, 59, 82):
            self.nuta(n); self.slowa()
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(len(self.sym.zapytania), pytania)

    def test_suwak_dziala_w_trybie(self):
        self.klawisz('F3_koniec_rozmowy'); self.slowa()
        self.nacisnij('dotyk', 2, True)
        self.nacisnij('suwak', 2, 1.0)
        self.nacisnij('dotyk', 2, False)
        self.tick(0.6); self.slowa()
        self.assertIn('telefon', self.antena())
        self.otworz()
        self.nacisnij('dotyk', 2, True)
        self.nacisnij('suwak', 2, 0.0)
        self.nacisnij('dotyk', 2, False)
        self.tick(0.6); self.slowa()
        self.assertNotIn('telefon', self.antena())
        self.assertTrue(self.r._tor_emisji.tryb_miksu)

    def test_hold_przed_kolejka_miksu(self):
        self.otworz()
        tor = self.r._tor_emisji
        with tor._warunek:
            for _ in range(20):
                self.nuta(99)
            self.r.zglos(('jog', 1))
            tor.zlec('hold', 1)
        self.slowa()
        p = self.s.polecenia
        self.assertLess(p.index('Hold=1'), p.index('MixPoint=next'))
        self.assertLess(p.index('Hold=1'), p.index('MixPos=+0.1'))

    def test_jog_w_trakcie_otwierania_nie_rusza_playlisty(self):
        self.s.opoznienie['mixopen'] = 0.05
        self.nuta(101)
        self.assertTrue(self.s.czekaj_na('MixOpen'))
        self.r.zglos(('jog', 1))
        slowa = self.slowa()
        self.assertFalse(any(s.startswith('Pozycja') for s in slowa), slowa)
        self.nuta(59)
        self.assertEqual(self.slowa(), ['Pozycja 0:00,6. Cue 0:00,5'])
        self.assertFalse(any(p.startswith('SelectIndex') for p in self.s.polecenia))

    def test_stop_anuluje_nierozpoczete_wejscie_bez_zawieszonego_trybu(self):
        tor = self.r._tor_emisji
        with tor._warunek:
            self.nuta(101)
            self.nuta(93)
        self.slowa()
        self.assertNotIn('MixOpen', self.s.polecenia)
        self.assertFalse(tor.tryb_miksu)
        self.nuta(91)
        self.assertIn('Nauka klawiszy', self.slowa()[0])

    def test_zepsute_odpowiedzi_nie_potwierdzaja_zapisu(self):
        self.otworz()
        self.s.odpowiedzi['mixsave'] = 'OK|przejscie_za=nan'
        self.nuta(80)
        self.assertEqual(self.slowa(), ['Punkty miksu zamknięte, SARA podała błędny punkt'])
        self.assertFalse(self.r._tor_emisji.tryb_miksu)

    def test_zapis_grajacego_przy_hold_bez_obietnicy_przejscia(self):
        # Decyzja rodzica: OK|brak_przejscia jest sukcesem, nie awarią.
        self.otworz()
        self.nuta(94); self.slowa()
        self.nuta(54); self.slowa()
        self.assertEqual(self.r.emisja.wykonaj('hold_odczyt'), emisja.Wstrzymanie(True, 'trzyma'))
        od = len(self.s.polecenia)
        # Oddzielny tekst pozwala wykryć użycie właściwego klucza mimo
        # identycznego roboczego brzmienia dwóch komunikatów zapisu.
        self.u.komunikaty['miks_zapisano_bez_przejscia'] = 'Zapisano punkty miksu, test osobnego klucza'
        self.nuta(80)
        self.assertEqual(self.slowa(), ['Zapisano punkty miksu, test osobnego klucza'])
        self.assertFalse(self.r._tor_emisji.tryb_miksu)
        self.assertEqual(self.r.emisja.wykonaj('hold_odczyt'), emisja.Wstrzymanie(True, 'trzyma'))
        self.assertNotIn('Hold=0', self.s.polecenia[od:])

    def test_wybor_auto_sara_i_przypiecie_do_tego_samego_gniazda(self):
        with SerwerPlayoutu() as spl:
            self.r.emisja = emisja.WyborProgramu('auto', {
                'spl_port': spl.port, 'sara_port': self.s.port, 'preferowany': 'SARA'})
            self.otworz()
            self.assertEqual(spl.polecenia, [])
            self.r.emisja.adaptery.reverse()  # teraz preferowany byłby SPL
            self.nuta(59)
            self.assertEqual(self.slowa(), ['Pozycja 0:00,5. Cue 0:00,5'])
            self.nuta(82); self.slowa()
            self.assertEqual(spl.polecenia, [])
            self.assertEqual(self.s.polecenia.count('Helo'), 1)

    def test_otwarcie_puste_cue_i_porzucone_nie_zmienia_punktow(self):
        self.s.miks.zapisane['cue'] = None
        przed = dict(self.s.miks.zapisane)
        self.nuta(101)
        self.assertEqual(self.slowa(), ['Punkty miksu: Żółć, Utwór 0, 3:45. Cue nieustawione'])
        self.nuta(92); self.slowa()
        self.nuta(84); self.slowa()
        self.nuta(82); self.slowa()
        self.assertEqual(self.s.miks.zapisane, przed)
        self.assertEqual(self.s.miks.punkty, przed)

    def test_mowa_punktow_zawsze_takze_w_trybie_dzwiekowym(self):
        from mostek.informacja import Tryb
        for tryb in Tryb:
            self.info.tryb = tryb
            self.otworz()
            self.assertEqual(self.ostatnie_dzwieki, [])
            self.nuta(59)
            self.assertEqual(self.slowa(), ['Pozycja 0:00,5. Cue 0:00,5'])
            self.assertEqual(self.ostatnie_dzwieki, [])
            self.nuta(82); self.slowa()

    def test_bledny_punkt_z_sary_nie_udaje_utraty_polaczenia(self):
        # Loona 25.10.2026: SARA podała Segue za końcem utworu; połączenie było zdrowe.
        self.otworz()
        self.s.odpowiedzi['mixpoint=next'] = '0|intro|999999999|0|brak'
        self.nuta(99)
        self.assertEqual(self.slowa(), ['Punkty miksu zamknięte, SARA podała błędny punkt'])
        self.assertFalse(self.r._tor_emisji.tryb_miksu)

    def test_parsowanie_stanu_zapobiega_zgadywaniu(self):
        from mostek.miks import StanMiksu
        for tekst in ('1|cue|0|0|brak', '0|overlap|-|1|przejscie'):
            self.assertIsNotNone(StanMiksu.czytaj(tekst, 100))
        for tekst in ('1|xyz|0|0|brak', '101|cue|0|0|brak', '0|cue|101|0|brak',
                      '-1|cue|0|0|brak', '0|cue|0|2|brak', '0|cue|0|0|gra',
                      '0|cue|0|0|brak|x', '0|cue|0|0', '0|cue|NaN|0|brak'):
            with self.assertRaises(emisja.BladEmisji, msg=tekst):
                StanMiksu.czytaj(tekst, 100)


if __name__ == '__main__':
    unittest.main()
