"""Wstrzymanie automatu: prawdziwe TCP + mikser w pamięci, bez audio/SARY."""
import threading
import time
import unittest
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki
from atrapa_playoutu import SerwerPlayoutu, zamkniety_port
from mostek import emisja
from mostek.informacja import Tryb
from mostek.mowa import Priorytet
from mostek.rdzen import Rdzen
from mostek.stan import NIEZNANY


class TestHold(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.s = SerwerPlayoutu(True)
        self.addCleanup(self.s.zamknij)
        self.s.gra = True
        self.r.emisja = emisja.SARA(self.s.port, limit_s=0.1)

    def holds(self):
        return [p for p in self.s.polecenia if p.startswith('Hold')]

    def test_f1_wyprzedza_20_ruchow_i_dociera_przed_potwierdzeniem(self):
        tor = self.r._tor_emisji
        # Kolejka deterministycznie czeka na Condition, bez operacji w toku.
        # Każdy ruch jest wolny: mutant FIFO przekroczy 30 ms, nie tylko kolejność.
        self.s.opoznienie['selectindex=+'] = 0.005
        przejscie = self.r._wykonaj_przejscie
        pomiar = []
        def wolny_mikser(*args, **kwargs):
            bramka.set()
            dotarl = self.s.czekaj_na('Hold=1', timeout=0.03)
            if dotarl:
                pomiar.append(next(t for p, t in self.s.czasy if p == 'Hold=1') - start)
            self.assertTrue(dotarl, 'Hold nie dotarł przed potwierdzeniem MR18 w 30 ms')
            return przejscie(*args, **kwargs)
        bramka = threading.Event()
        def worker():
            bramka.wait()
            tor._petla()
        tor._watek = threading.Thread(target=worker, daemon=True)
        tor._watek.start()
        self.addCleanup(bramka.set)
        for _ in range(20):
            tor.zlec('ruch', 1, jog=True)
        start = time.monotonic()
        with patch.object(self.r, '_wykonaj_przejscie', side_effect=wolny_mikser):
            self.r.zglos(('klawisz', 'F1_mikrofon'))
        self.slowa()
        self.assertEqual(len(pomiar), 1)
        self.assertLessEqual(pomiar[0], 0.030)
        print(f'POMIAR F1->Hold: {pomiar[0]*1000:.3f} ms', flush=True)
        self.assertEqual(self.s.polecenia.count('SelectIndex=+'), 20)
        self.assertLess(self.s.polecenia.index('Hold=1'), self.s.polecenia.index('SelectIndex=+'))

    def test_nieudane_otwarcie_zwalnia(self):
        self.sym.awarie.ignoruj_zapis = {sciezki.mute_szyny(6)}
        przejscie = self.r._wykonaj_przejscie
        def po_hold(*args, **kwargs):
            self.assertTrue(self.s.czekaj_na('Hold=1'))
            return przejscie(*args, **kwargs)
        with patch.object(self.r, '_wykonaj_przejscie', side_effect=po_hold):
            self.klawisz('F1_mikrofon')
        self.slowa()
        self.assertFalse(self.suma('mikrofon'))
        self.assertEqual(self.holds(), ['Hold=1', 'Hold=0'])

    def test_zewnetrzny_mikrofon_i_zamkniecie(self):
        self.inny(sciezki.mute_szyny(6), 0)
        self.inny(sciezki.lr(9), 1)
        self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])
        self.inny(sciezki.lr(9), 0)
        self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1', 'Hold=0'])

    def test_kaszel_nie_zwalnia_ale_przelacznik_w_kaszlu_tak(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        self.r.kaszel_wcisniety()
        self.tick(0.01); self.slowa()
        self.assertIsNotNone(self.r._kaszel)
        self.assertEqual(self.holds(), ['Hold=1'])
        self.r.kaszel_puszczony()
        self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])
        self.r.kaszel_wcisniety()
        self.klawisz('F1_mikrofon'); self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1', 'Hold=0'])

    def test_restart_przy_otwartym_mikrofonie(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        self.r.zamknij_emisje()
        self.s.polecenia.clear()
        self.r = Rdzen(self.u, self.klient, self.mowa, emisja=emisja.SARA(self.s.port),
                       zegar=self.zegar, sen=self.zegar.sen)
        self.assertTrue(self.r.synchronizuj())
        self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])

    def test_nieznany_nie_zwalnia(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        with patch.object(self.r.widok, 'suma', return_value=NIEZNANY):
            self.r._obserwuj_hold()
        self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])

    def test_mikrofon_nie_czeka_na_zajety_odbior_komunikatow(self):
        # Stary komunikat może być odbierany w drugim wątku. Samo otwarcie
        # MR18 nie może czekać na tę blokadę. Zwolnienie po otwarciu pozwala
        # zakończyć odbiór, bez ingerowania w kolejność przejścia.
        otwarty = threading.Event()
        przejscie = self.r._wykonaj_przejscie
        def zaznacz(*args, **kwargs):
            w = przejscie(*args, **kwargs)
            otwarty.set()
            return w
        with patch.object(self.r, '_wykonaj_przejscie', side_effect=zaznacz):
            with self.r._odbior_emisji:
                worker = threading.Thread(target=self.r.przelacz_mikrofon)
                worker.start()
                wynik = otwarty.wait(0.1)
            worker.join(2)
        self.assertTrue(wynik, 'Otwarcie czekało na odbiór starego komunikatu')
        self.assertFalse(worker.is_alive())
        self.slowa()

    def test_brak_programu_nie_uruchamia_nawet_workera_hold(self):
        self.r.emisja = None
        self.tick(0.01)
        self.klawisz('F1_mikrofon')
        self.assertIsNone(self.r._tor_emisji._watek)

    def test_ustawienie_domyslne_i_walidacja_bool(self):
        from mostek.ustawienia import sprawdz, BladUstawien
        self.assertIs(self.u.emisja['mikrofon_wstrzymuje_automat'], True)
        self.u.emisja['mikrofon_wstrzymuje_automat'] = 'false'
        with self.assertRaises(BladUstawien):
            sprawdz(self.u)
        self.u.emisja['mikrofon_wstrzymuje_automat'] = False
        sprawdz(self.u)

    def test_wylaczone_ustawienie(self):
        self.u.emisja['mikrofon_wstrzymuje_automat'] = False
        self.klawisz('F1_mikrofon'); self.tick(); self.slowa()
        self.klawisz('F1_mikrofon'); self.tick(); self.slowa()
        self.assertEqual(self.holds(), [])
        self.assertEqual(self.s.polecenia, [])

    def test_cue_i_rozbrojenie_bez_zamiaru(self):
        self.cue('telefon'); self.slowa()
        self.klawisz('F1_mikrofon'); self.slowa()
        self.assertEqual(self.holds(), [])
        self.cue('telefon'); self.slowa()
        self.r.kontroler_polaczony = False
        self.klawisz('F1_mikrofon'); self.slowa()
        self.assertEqual(self.holds(), [])

    def test_komunikaty_koniec_raz_i_zwolnienie_bez_play(self):
        self.klawisz('F1_mikrofon')
        self.assertIn('Automat czeka na mikrofon', '. '.join(self.slowa()))
        self.s.skoncz_utwor()
        self.r._tor_emisji._hold_odczyt_czas -= 2
        self.tick(0.01)
        self.assertEqual(self.slowa(), ['Utwór skończony, następny czeka'])
        self.r._tor_emisji._hold_odczyt_czas -= 2
        self.tick(0.01)
        self.assertEqual(self.slowa(), [])
        self.klawisz('F1_mikrofon'); self.tick(0.01)
        self.assertIn('Automat wznowiony, następny czeka na Play', '. '.join(self.slowa()))
        self.assertNotIn('Play', self.s.polecenia)
        self.assertNotIn('Skip', self.s.polecenia)

    def test_za_pozno_zawsze_mowa(self):
        self.s.przejscie = True
        self.info.tryb = Tryb.DZWIEKI
        self.klawisz('F1_mikrofon')
        self.assertIn('Przejście już trwa, automat zatrzyma się po następnym utworze', '. '.join(self.slowa()))
        self.assertIn('alarm', self.ostatnie_dzwieki)

    def test_zamknieta_sara_bez_alarmu_przy_wylaczonym_mikrofonie(self):
        # Główna 24.10.2026: SARA zamknięta, mikrofon wyłączony, alarm co 5 s.
        self.r.emisja = emisja.SARA(zamkniety_port(), limit_s=0.1)
        for _ in range(4):
            self.r._tor_emisji._hold_odczyt_czas -= 2
            self.r._tor_emisji._hold_blad_czas -= 6
            self.tick(0.01)
            self.assertEqual(self.slowa(), [])
        self.assertFalse(self.suma('mikrofon'))

    def test_zamknieta_sara_bez_alarmu_przy_otwarciu_mikrofonu(self):
        # Nic nie słucha na porcie: SARA nie gra, nie ma czego wstrzymywać.
        self.r.emisja = emisja.SARA(zamkniety_port(), limit_s=0.1)
        self.klawisz('F1_mikrofon')
        self.assertTrue(self.suma('mikrofon'))
        self.assertFalse(any('Nie udało' in s for s in self.slowa()))

    def test_zamknieta_sara_ponawia_rzadko(self):
        # Połączenie do zamkniętej SARY na stanowisku czeka 0,5 s: nie co sekundę.
        self.r.emisja = emisja.SARA(zamkniety_port(), limit_s=0.1)
        for _ in range(4):
            self.tick(1.01); self.slowa()
        tor = self.r._tor_emisji
        self.assertGreater(tor._hold_odczyt_czas - time.monotonic(), 2.0)

    def test_brak_sary_alarm_co_najmniej_5_s_bez_blokowania_mikrofonu(self):
        # SARA słucha i odpowiada na Helo, ale nie potwierdza Hold=1.
        self.s.milcz.add('hold=1')
        t = time.monotonic()
        self.klawisz('F1_mikrofon')
        self.assertLess(time.monotonic()-t, 0.1)
        self.assertTrue(self.suma('mikrofon'))
        self.assertTrue(self.r._tor_emisji.czekaj())
        self.r.odbierz_emisje()
        alarmy = [w for w in self.mowa._oczekujace if 'Nie udało' in w[2]]
        self.assertEqual(len(alarmy), 1)
        self.assertEqual(alarmy[0][0], Priorytet.BEZPIECZENSTWO)
        self.assertIn('alarm', alarmy[0][4])
        self.slowa()
        for _ in range(3):
            self.r._tor_emisji.zlec('hold', 1)
            self.assertEqual(self.slowa(), [])
        self.r._tor_emisji._hold_blad_czas -= 6
        self.r._tor_emisji.zlec('hold', 1)
        self.assertEqual(self.slowa(), ['Nie udało się wstrzymać automatu'])

    def test_powrot_sary_ponawia_stan(self):
        self.s.milcz.add('hold=1')
        self.klawisz('F1_mikrofon'); self.slowa()
        self.s.milcz.clear()
        self.r._tor_emisji._hold_odczyt_czas -= 2
        self.tick(0.01); self.slowa()
        self.assertEqual(self.holds().count('Hold=1'), 2)
        self.assertTrue(self.s.hold)
        # Restart niewidoczny między odczytami TCP: serwer stracił wstrzymanie.
        self.s.hold = False
        self.s.hold_stan = 'brak'
        self.r._tor_emisji._hold_odczyt_czas -= 2
        self.tick(0.01); self.slowa()
        self.assertTrue(self.s.hold)
        self.assertEqual(self.holds().count('Hold=1'), 3)

    def test_tryby_i_wspolny_dzwiek_mikrofonu(self):
        for tryb in Tryb:
            with self.subTest(tryb=tryb):
                self.info.tryb = tryb
                self.klawisz('F1_mikrofon')
                d, s = self.dzwieki_i_slowa()
                if tryb == Tryb.MOWA:
                    self.assertEqual(d, [])
                    self.assertIn('Automat czeka na mikrofon', '. '.join(s))
                else:
                    self.assertIn('automat_wstrzymany', d)
                    self.assertTrue(any('mikrofon_na_antenie' in g and 'automat_wstrzymany' in g
                                        for g in self.dzwieki.naraz), self.dzwieki.naraz)
                    if tryb == Tryb.DZWIEKI:
                        self.assertEqual(s, [])
                self.klawisz('F1_mikrofon'); self.tick(0.01); self.slowa()
                self.dzwieki.naraz.clear()

    def test_odczyt_co_sekunde_nie_wypiera_klawiszy(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        tor = self.r._tor_emisji
        for _ in range(5):
            self.tick(0.001)
        self.slowa()
        self.assertNotIn('Hold', self.s.polecenia)
        with tor._warunek:
            tor._hold_odczyt_czas -= 2
            self.tick(0.001)
            tor.zlec('ruch', 1)
            self.assertEqual([z[0] for z in tor._kolejka], ['ruch', 'hold_odczyt'])
        self.slowa()
        self.assertEqual(self.holds(), ['Hold=1', 'Hold'])

    def test_pozny_hold_dolacza_do_grajacego_dzwieku_bez_uciecia(self):
        self.s.opoznienie['hold=1'] = 0.04
        czasy = {}
        uslyszano = threading.Event()
        odtworz = self.dzwieki.odtworz
        def zapisz(klucz, plik):
            czasy[klucz] = time.monotonic()
            odtworz(klucz, plik)
            if klucz == 'automat_wstrzymany':
                uslyszano.set()
        with patch.object(self.dzwieki, 'odtworz', side_effect=zapisz):
            self.mowa.start()
            try:
                self.klawisz('F1_mikrofon')
                self.assertTrue(uslyszano.wait(1))
                self.assertTrue(self.r._tor_emisji.czekaj())
                self.assertLess(czasy['automat_wstrzymany']-czasy['mikrofon_na_antenie'], 0.23)
                self.assertGreater(czasy['automat_wstrzymany'], czasy['mikrofon_na_antenie'])
                self.assertEqual(self.dzwieki.zatrzymania, 0)
            finally:
                self.mowa.stop()
        self.assertEqual(self.wyjscie.powiedziane, ['Mikrofon włączony', 'Automat czeka na mikrofon'])
        self.assertEqual(self.wyjscie.przerwania, 0)

    def test_kursor_nie_ucina_potwierdzenia_hold(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        przed = self.wyjscie.przerwania
        self.r.zglos(('klawisz', 'emisja_dol')); self.slowa()
        self.assertEqual(self.wyjscie.przerwania, przed)

    def test_dzwiek_zawiedziony_daje_mowe_w_obu_trybach_miksowania(self):
        for naraz in (True, False):
            self.info.naraz = naraz
            self.info.tryb = Tryb.DZWIEKI
            self.dzwieki.awaria = True
            self.klawisz('F1_mikrofon')
            self.assertIn('Automat czeka na mikrofon', '. '.join(self.slowa()))
            self.klawisz('F1_mikrofon'); self.slowa()

    def test_hold_nie_zmienia_zapisow_miksera(self):
        scenariusze = []
        for wlaczone in (False, True):
            self.u.emisja['mikrofon_wstrzymuje_automat'] = wlaczone
            od = len(self.sym.dziennik)
            self.klawisz('F1_mikrofon'); self.slowa()
            self.r.kaszel_wcisniety(); self.r.kaszel_puszczony()
            self.klawisz('F1_mikrofon'); self.slowa()
            scenariusze.append(self.zapisy(od))
        self.assertEqual(*scenariusze)

    def test_stop_zachowuje_hold_ostatni_wygrywa_i_nie_wygasa(self):
        tor = self.r._tor_emisji
        for stop in ('stop', 'instant'):
            with tor._warunek:
                tor.zlec('ruch', 1)
                tor.zlec('hold', 1)
                tor.zlec('hold', 0)
                tor.zlec('hold', 1)
                tor.zlec(stop)
                q = list(tor._kolejka)
                self.assertEqual([z[0] for z in q], ['hold', stop])
                a,k,j,t = tor._kolejka[0]
                tor._kolejka[0] = (a,k,j,t-3)
            self.slowa()
        self.assertEqual(self.holds(), ['Hold=1', 'Hold=1'])
        self.assertNotIn('SelectIndex=+', self.s.polecenia)

    def test_spl_i_brak_wyboru_bez_hold_i_bez_komunikatu(self):
        with SerwerPlayoutu() as spl:
            for adapter in (emisja.StationPlaylistTCP(spl.port), emisja.StationPlaylist(lambda w,l: 0), None):
                self.r.emisja = adapter
                self.r._tor_emisji.zlec('hold', 1)
                self.assertEqual(self.slowa(), [])
            self.assertEqual(spl.polecenia, [])
        for okno in (True, None, False):
            with SerwerPlayoutu() as spl:
                u = {'spl_port':spl.port, 'sara_port':self.s.port}
                self.r.emisja = emisja.WyborProgramu('auto', u, okno_spl=lambda: okno)
                self.r._tor_emisji.zlec('hold', 1); self.slowa()
                self.assertEqual(spl.polecenia, [])


class TestHoldRozmowcow(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.s = SerwerPlayoutu(True)
        self.addCleanup(self.s.zamknij)
        self.s.gra = True
        self.r.emisja = emisja.SARA(self.s.port, limit_s=0.1)

    def holds(self):
        return [p for p in self.s.polecenia if p.startswith('Hold=')]

    def rozmowca(self, zr, poziom=0.75, main=1):
        for k in self.u.zrodla[zr].kanaly:
            self.inny(sciezki.lr(k), main)
            self.inny(sciezki.fader(k), poziom)
        self.tick(0.01)

    def test_telefon_z_innego_urzadzenia_bez_mikrofonu(self):
        self.rozmowca('telefon')
        self.slowa()
        self.assertFalse(self.suma('mikrofon'))
        self.assertEqual(self.holds(), ['Hold=1'])
        self.assertTrue(self.s.hold)

    def test_zoom_z_innego_urzadzenia_bez_mikrofonu(self):
        self.rozmowca('zoom')
        self.slowa()
        self.assertFalse(self.suma('mikrofon'))
        self.assertEqual(self.holds(), ['Hold=1'])
        self.assertTrue(self.s.hold)

    def test_mikrofon_off_przy_rozmowcy_nie_zwalnia(self):
        for zr in ('telefon', 'zoom'):
            with self.subTest(zr=zr):
                self.klawisz('F1_mikrofon'); self.slowa()
                self.rozmowca(zr); self.slowa()
                self.s.polecenia.clear()
                self.klawisz('F1_mikrofon'); self.slowa()
                self.assertFalse(self.suma('mikrofon'))
                self.assertEqual(self.holds(), [])
                self.assertTrue(self.s.hold)
                self.rozmowca(zr, poziom=0); self.slowa()
                self.assertEqual(self.holds(), ['Hold=0'])

    def test_zwolnienie_dopiero_po_ostatnim_z_trzech(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        self.rozmowca('telefon'); self.slowa()
        self.rozmowca('zoom'); self.slowa()
        self.klawisz('F1_mikrofon'); self.slowa()
        self.rozmowca('telefon', poziom=0); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])
        self.rozmowca('zoom', main=0); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1', 'Hold=0'])

    def test_cue_nie_blokuje(self):
        for zr in ('telefon', 'zoom'):
            with self.subTest(zr=zr):
                self.cue(zr)
                self.tick(0.01); self.slowa()
                self.assertTrue(self.cue_sym(zr))
                self.assertFalse(self.s.hold)
                self.cue(zr)
                self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=0'])

    def test_main_on_z_suwakiem_na_dole_nie_blokuje(self):
        for zr in ('telefon', 'zoom'):
            with self.subTest(zr=zr):
                self.rozmowca(zr, poziom=0); self.slowa()
                self.assertTrue(self.suma(zr))
                self.assertFalse(self.s.hold)
        self.assertEqual(self.holds(), ['Hold=0'])

    def test_main_off_z_suwakiem_w_gorze_nie_blokuje(self):
        for zr in ('telefon', 'zoom'):
            with self.subTest(zr=zr):
                self.rozmowca(zr, main=0); self.slowa()
                self.assertFalse(self.suma(zr))
                self.assertFalse(self.s.hold)
        self.assertEqual(self.holds(), ['Hold=0'])

    def test_zejscie_ostatniego_suwakiem_main_off_lub_cue(self):
        for zr in ('telefon', 'zoom'):
            for jak in ('suwak', 'main', 'cue'):
                with self.subTest(zr=zr, jak=jak):
                    self.rozmowca(zr); self.slowa()
                    self.assertTrue(self.s.hold)
                    self.s.polecenia.clear()
                    if jak == 'cue':
                        self.cue(zr)
                        self.tick(0.01)
                    else:
                        self.rozmowca(zr, poziom=0 if jak == 'suwak' else 0.75,
                                      main=0 if jak == 'main' else 1)
                    self.slowa()
                    self.assertEqual(self.holds(), ['Hold=0'])
                    self.assertFalse(self.s.hold)
                    if jak == 'cue':
                        self.cue(zr)
                        self.tick(0.01); self.slowa()

    def test_auto_cue_reset_suwakiem_wstrzymuje(self):
        for zr in ('telefon', 'zoom'):
            with self.subTest(zr=zr):
                self.cue(zr)
                self.tick(0.01); self.slowa()
                self.assertTrue(self.cue_sym(zr))
                self.assertFalse(self.s.hold)
                self.s.polecenia.clear()
                self.ruch(zr, 0.75); self.slowa()
                self.assertFalse(self.cue_sym(zr))
                self.assertTrue(self.na_antenie_sym(zr))
                self.assertEqual(self.holds(), ['Hold=1'])
                self.ruch(zr, 0); self.slowa()
                self.assertEqual(self.holds(), ['Hold=1', 'Hold=0'])

    def test_prog_anteny_z_ustawien(self):
        from mostek.konwersje import poziom_db_na_float
        self.u.zachowanie['prog_suwaka_na_antenie_db'] = -30.0
        for zr in ('telefon', 'zoom'):
            with self.subTest(zr=zr):
                self.rozmowca(zr, poziom=poziom_db_na_float(-31)); self.slowa()
                self.assertFalse(self.s.hold)
                self.rozmowca(zr, poziom=poziom_db_na_float(-29)); self.slowa()
                self.assertTrue(self.s.hold)
                self.rozmowca(zr, poziom=0); self.slowa()
                self.assertFalse(self.s.hold)

    def test_nieznane_pola_rozmowcow_nie_zwalniaja(self):
        for adres in (sciezki.lr(10), sciezki.fader(10), sciezki.wysylka(9, 1),
                      sciezki.lr(8), sciezki.fader(8), sciezki.wysylka(9, 4)):
            with self.subTest(adres=adres):
                self.r.stan.potwierdz(sciezki.lr(9), 1, self.zegar())
                self.r._obserwuj_hold(); self.slowa()
                self.s.polecenia.clear()
                self.r.stan.potwierdz(sciezki.lr(9), 0, self.zegar())
                self.r.stan.zapomnij(adres)
                self.r._obserwuj_hold(); self.slowa()
                self.assertEqual(self.holds(), [])
                self.assertTrue(self.s.hold)
                self.r.stan.potwierdz(adres, self.m(adres), self.zegar())
                self.r._obserwuj_hold(); self.slowa()
                self.assertEqual(self.holds(), ['Hold=0'])

    def test_rozbiezna_para_zooma_nie_zwalnia(self):
        self.klawisz('F1_mikrofon'); self.slowa()
        self.r.stan.potwierdz(sciezki.lr(9), 0, self.zegar())
        self.r.stan.potwierdz(sciezki.lr(8), 0, self.zegar())
        self.r._obserwuj_hold(); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])

    def test_trojwartosciowa_alternatywa(self):
        from itertools import product
        for mikrofon, telefon, zoom in product((False, True, NIEZNANY), repeat=3):
            with self.subTest(mikrofon=mikrofon, telefon=telefon, zoom=zoom):
                stany = (mikrofon, telefon, zoom)
                with patch.object(self.r.widok, 'suma', return_value=mikrofon), \
                     patch.object(self.r.widok, 'na_antenie',
                                  side_effect=lambda zr: {'telefon': telefon, 'zoom': zoom}[zr]), \
                     patch.object(self.r, '_zlec_hold') as zlec:
                    self.r._obserwuj_hold()
                if any(s is True for s in stany):
                    zlec.assert_called_once_with(True)
                elif any(s is NIEZNANY for s in stany):
                    zlec.assert_not_called()
                else:
                    zlec.assert_called_once_with(False)

    def test_lista_z_pol_odbiorca_nie_z_nazw_ani_glos(self):
        from dataclasses import replace
        # Syntetyczny rozmówca w konfiguracji: nie telefon/Zoom, bez flagi głosu.
        self.u.zrodla['gosc'] = replace(self.u.zrodla['telefon'], klucz='gosc', glos=False)
        with patch.object(self.r.widok, 'na_antenie', side_effect=lambda zr: zr == 'gosc'), \
             patch.object(self.r, '_zlec_hold') as zlec:
            self.r._obserwuj_hold()
        zlec.assert_called_once_with(True)

    def test_muzyka_i_solo_mikrofonu_nie_blokuja(self):
        self.inny(sciezki.solo(9), 1)
        self.tick(0.01); self.slowa()
        self.assertTrue(self.suma('muzyka1'))
        self.assertFalse(self.suma('mikrofon'))
        self.assertEqual(self.holds(), ['Hold=0'])

    def test_kaszel_i_talkback_z_telefonem_na_antenie(self):
        self.rozmowca('telefon'); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])
        for tryb in ('kaszel', 'telefon', 'zoom'):
            with self.subTest(tryb=tryb):
                if tryb == 'kaszel':
                    # Zamknięty mikrofon bez toru i solo to celowy brak operacji.
                    # PFL daje rzeczywisty kaszel bez mikrofonowego Hold.
                    self.inny(sciezki.solo(9), 1)
                    self.r.kaszel_wcisniety()
                    self.assertIsNotNone(self.r._kaszel)
                else:
                    self.r.talkback_wcisniety(tryb)
                    self.assertIn(tryb, self.r._talkback)
                self.tick(0.01); self.slowa()
                self.assertTrue(self.suma('telefon'))
                self.assertEqual(self.holds(), ['Hold=1'])
                if tryb == 'kaszel':
                    self.r.kaszel_puszczony()
                else:
                    self.r.talkback_puszczony(tryb)
                self.tick(0.01); self.slowa()
                self.assertEqual(self.holds(), ['Hold=1'])

    def test_restart_przy_rozmowcy_na_antenie(self):
        self.rozmowca('telefon'); self.slowa()
        self.r.zamknij_emisje()
        self.s.polecenia.clear()
        self.r = Rdzen(self.u, self.klient, self.mowa, emisja=emisja.SARA(self.s.port),
                       zegar=self.zegar, sen=self.zegar.sen)
        self.assertTrue(self.r.synchronizuj())
        self.tick(0.01); self.slowa()
        self.assertEqual(self.holds(), ['Hold=1'])

    def test_wylaczone_ustawienie_obejmuje_rozmowcow(self):
        self.u.emisja['mikrofon_wstrzymuje_automat'] = False
        for zr in ('telefon', 'zoom'):
            self.rozmowca(zr); self.slowa()
            self.rozmowca(zr, poziom=0); self.slowa()
        self.assertEqual(self.s.polecenia, [])

    def test_spl_nie_dostaje_hold_od_rozmowcow(self):
        with SerwerPlayoutu() as spl:
            self.r.emisja = emisja.StationPlaylistTCP(spl.port)
            for zr in ('telefon', 'zoom'):
                self.rozmowca(zr); self.slowa()
                self.rozmowca(zr, poziom=0); self.slowa()
            self.assertEqual(spl.polecenia, [])

    def test_komunikat_raz_mimo_ruchow_i_zmiany_blokujacego(self):
        slowa, dzwieki = [], []
        def odbierz():
            slowa.extend(self.slowa())
            dzwieki.extend(self.ostatnie_dzwieki)
        self.rozmowca('telefon'); odbierz()
        for poziom in (0.6, 0.7, 0.75):
            self.rozmowca('telefon', poziom=poziom); odbierz()
        self.rozmowca('zoom'); odbierz()
        self.rozmowca('telefon', poziom=0); odbierz()
        # Również okresowy odczyt SARY nie powtarza komunikatu.
        self.r._tor_emisji._hold_odczyt_czas -= 2
        self.tick(0.01); odbierz()
        self.assertEqual(self.holds(), ['Hold=1'])
        self.rozmowca('zoom', poziom=0); odbierz()
        self.assertEqual(self.holds(), ['Hold=1', 'Hold=0'])
        self.assertEqual('. '.join(slowa).count('Automat czeka na mikrofon'), 1)
        self.assertEqual('. '.join(slowa).count('Automat wznowiony'), 1)
        self.assertEqual(dzwieki.count('automat_wstrzymany'), 1)
        self.assertEqual(dzwieki.count('automat_zwolniony'), 1)
        self.assertNotIn('Play', self.s.polecenia)
        self.assertNotIn('Skip', self.s.polecenia)


if __name__ == '__main__':
    unittest.main()
