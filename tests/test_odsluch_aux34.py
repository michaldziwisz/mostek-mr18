"""Test kontraktu sterowania AUX34, nie pomiar DSP ani dźwięku MR18."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from typing import Any, cast

from pomoc import TestZSymulatorem, ZERO_DB, poziom_db_na_float, sciezki as s
from mostek import odsluch
from mostek.logika import NaruszenieZapory, wszystkie_adresy_odczytu
from mostek.rdzen import Krok
from mostek.ustawienia import wczytaj

ROOT = Path(__file__).resolve().parents[1]
DANE = ROOT / 'tests' / 'dane_aux34'
SPEC = importlib.util.spec_from_file_location('scena_aux34', ROOT / 'narzedzia/migracja_aux34.py')
assert SPEC is not None and SPEC.loader is not None
MIG = None
if (ROOT / 'narzedzia/migracja_aux34.py').exists():
    MIG = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MIG)


class TestAux34(TestZSymulatorem):
    synchronizuj_na_starcie = False

    def setUp(self):
        super().setUp()
        self.u.zachowanie['tryb_odsluchu'] = 'aux34_mono'
        self.sym.wartosci.update(odsluch.stale())
        for k in range(1, 17):
            self.sym.wartosci[s.tap(k, 9)] = 4
        for p in s.POWROTY:
            self.sym.wartosci[s.wysylka_powrotu(p, 9)] = 0.0
        self.sym.wartosci[s.MONITOR_ZRODLO] = 0
        self.assertTrue(self.r.synchronizuj())
        self.assertFalse(self.r.zapora.profil_blokuje)
        self.r.odsluch_aux.uzgodnij()

    def odswiez(self):
        self.r.odsluch_aux.uzgodnij()

    def a(self, k):
        return cast(float, self.m(s.wysylka(k, 9)))

    def test_spoczynek_program_post_bez_mikrofonu(self):
        self.assertEqual(self.a(1), 0)
        self.assertEqual(self.a(9), 0)
        self.assertEqual(self.m(s.MONITOR_ZRODLO), 1)
        self.assertFalse(self.pfl('muzyka1'))
        self.assertTrue(self.podsluch())

    def test_main_off_zamyka_nawet_z_faderem(self):
        self.cue('telefon')
        self.inny(s.lr(1), 0)
        self.odswiez()
        self.assertEqual(self.a(1), 0)
        self.assertEqual(self.a(2), 0)

    def test_fader_trim_nie_sa_mnozone_drugi_raz(self):
        self.cue('telefon')
        przed = self.a(1)
        self.inny(s.fader(1), poziom_db_na_float(-18))
        self.odswiez()
        self.assertAlmostEqual(self.a(1), przed)
        self.assertEqual(self.m(s.tap(1, 9)), 4)

    def test_mikrofon_antena_raz_przez_phones(self):
        self.klawisz('F1_mikrofon')
        self.assertTrue(self.suma('mikrofon'))
        self.assertFalse(self.pfl('mikrofon'))
        self.assertEqual(self.m(s.MONITOR_ZRODLO), 1)
        self.assertTrue(all(self.a(k) == 0 for k in range(1, 11)))
        self.assertEqual(self.a(9), 0)

    def test_cel_mikrofon_bez_solo_nadal_zero(self):
        self.cue('telefon')
        # Okno po obcej zmianie Main, przed automatycznym PFL.
        self.r.stan.potwierdz(s.lr(9), 1, self.zegar())
        self.r.stan.potwierdz(s.solo(9), 0, self.zegar())
        self.assertEqual(odsluch.cel(self.r.widok)[s.wysylka(9,9)], 0)

    def test_program_i_koniec_pfl_przy_trwajacym_cue(self):
        self.cue('telefon')
        self.r.sluchaj_programu()
        self.odswiez()
        self.assertFalse(self.pfl('telefon'))
        self.r.koniec_pfl()
        self.odswiez()
        self.assertTrue(self.pfl('telefon'))
        self.assertTrue(self.pfl('mikrofon'))
        self.assertEqual(self.a(10), 0)

    def test_niepotwierdzony_wlasny_glos_nie_udaje_sukcesu(self):
        self.cue('telefon')
        self.r.stan.potwierdz(s.lr(9), 1, self.zegar())
        self.sym.wartosci[s.lr(9)] = 1
        self.sym.wartosci[s.solo(9)] = 0
        self.r.stan.potwierdz(s.solo(9), 0, self.zegar())
        self.sym.awarie.ignoruj_zapis.add(s.solo(9))
        self.assertFalse(self.r.odsluch_aux.uzgodnij())

    def test_cue_kazda_kombinacja_i_bez_wycieku(self):
        for cue in (('telefon',), ('zoom',), ('telefon', 'zoom')):
            with self.subTest(cue=cue):
                for r in cue:
                    self.cue(r)
                self.assertTrue(self.pfl('mikrofon'))
                self.assertEqual(self.m(s.MONITOR_ZRODLO), 0)
                self.assertGreater(self.a(1), 0)
                for r in cue:
                    self.assertTrue(self.pfl(r))
                    for k in self.u.zrodla[r].kanaly:
                        self.assertEqual(self.a(k), 0)
                self.assertEqual(self.naruszenia_miksera(), [])
                for r in cue:
                    self.cue(r)

    def test_rozmowca_antena_i_drugi_cue(self):
        self.ruch('telefon', 1.0)
        self.cue('zoom')
        self.assertGreater(self.a(10), 0)
        self.assertFalse(self.pfl('telefon'))
        self.assertTrue(self.pfl('zoom'))
        self.assertEqual(self.a(7), 0)
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_zoom_antena_telefon_cue(self):
        self.ruch('zoom', 1.0)
        self.cue('telefon')
        self.assertGreater(self.a(7), 0)
        self.assertEqual(self.a(10), 0)
        self.assertEqual(self.naruszenia_miksera(), [])

    def test_pfl_muzyki_break_before_make(self):
        self.cue('telefon')
        start = len(self.sym.dziennik)
        self.nacisnij('przycisk', 4, 3)
        self.assertTrue(self.pfl('muzyka1'))
        self.assertEqual(self.a(1), 0)
        zapisy = self.zapisy(start)
        zamk = next(i for i, (a, v) in enumerate(zapisy) if a == s.wysylka(1, 9) and v == 0)
        solo = next(i for i, (a, v) in enumerate(zapisy) if a == s.solo(1) and v == 1)
        self.assertLess(zamk, solo)
        self.r.koniec_pfl()
        self.odswiez()
        self.assertFalse(self.pfl('muzyka1'))
        self.assertGreater(self.a(1), 0)

    def test_program_lr_bez_drugiej_kopii_i_powrot(self):
        self.cue('telefon')
        self.r.sluchaj_programu()
        self.odswiez()
        self.assertEqual(self.m(s.MONITOR_ZRODLO), 1)
        self.assertTrue(all(self.a(k) == 0 for k in range(1, 11)))
        self.r.koniec_pfl()
        self.odswiez()
        self.assertEqual(self.m(s.MONITOR_ZRODLO), 0)
        self.assertGreater(self.a(1), 0)

    def test_kaszel_nie_wraca_na_lr(self):
        self.klawisz('F1_mikrofon')
        self.nacisnij('przycisk', 1, 2)
        self.assertFalse(self.pfl('mikrofon'))
        self.assertEqual(self.m(s.MONITOR_ZRODLO), 1)
        self.assertEqual(self.a(1), 0)
        self.assertEqual(self.a(9), 0)
        self.nacisnij('puszczenie', 1, 2)
        self.assertFalse(self.pfl('mikrofon'))

    def test_talkback_i_kaszel_izolacja(self):
        self.nacisnij('przycisk', 2, 2)
        self.assertFalse(self.pfl('mikrofon'))
        self.assertFalse(self.pfl('telefon'))
        self.assertEqual(self.a(10), 0)
        self.assertFalse(self.suma('mikrofon'))
        self.assertEqual(self.naruszenia_miksera(), [])
        self.nacisnij('przycisk', 1, 2)
        self.assertFalse(self.pfl('mikrofon'))
        self.nacisnij('puszczenie', 1, 2)
        self.nacisnij('puszczenie', 2, 2)
        self.assertFalse(self.pfl('telefon'))
        self.assertFalse(self.pfl('mikrofon'))

    def test_zapora_mikrofon_rezerwa_obcy_fx_i_pre(self):
        for k, b, pole, v in ((9,9,'level',.5), (11,9,'level',.5), (1,10,'level',.5), (1,9,'tap',3)):
            with self.subTest(k=k, b=b, pole=pole):
                with self.assertRaises(NaruszenieZapory):
                    self.r.zapora.sprawdz(f'/ch/{k:02d}/mix/{b:02d}/{pole}', v, self.r.widok)

    def test_zapora_pfl_i_main_off(self):
        self.inny(s.solo(1), 1)
        with self.assertRaises(NaruszenieZapory):
            self.r.zapora.sprawdz(s.wysylka(1, 9), .5, self.r.widok)
        self.inny(s.solo(1), 0)
        self.inny(s.lr(1), 0)
        with self.assertRaises(NaruszenieZapory):
            self.r.zapora.sprawdz(s.wysylka(1, 9), .5, self.r.widok)

    def test_master_i_routing_tylko_odczyt(self):
        for a, v in odsluch.stale().items():
            with self.assertRaises(NaruszenieZapory):
                self.r.zapora.sprawdz(a, v, self.r.widok)
        self.assertTrue(set(odsluch.adresy(self.u)) <= set(wszystkie_adresy_odczytu(self.u)))

    def test_master_minus30_jest_wiazacy(self):
        self.assertEqual(odsluch.stale()[odsluch.MASTER_FADER], .25)
        self.assertEqual(odsluch.stale()[odsluch.MASTER], 1)

    def test_master_sprzetowo_skwantyzowany_jest_zgodny(self):
        self.cue('telefon')
        self.inny(odsluch.MASTER_FADER, .24926686)
        self.assertTrue(odsluch.zgodny(self.r.widok))
        self.odswiez()
        self.assertGreater(self.a(1), 0)

    def test_zly_master_blokuje_i_nie_jest_naprawiany(self):
        for db in (0, -20, -40):
            with self.subTest(db=db):
                self.sym.wartosci[odsluch.MASTER_FADER] = poziom_db_na_float(db)
                start = len(self.sym.dziennik)
                self.assertTrue(self.r.synchronizuj())
                self.assertTrue(self.r.zapora.profil_blokuje)
                self.odswiez()
                self.assertEqual(self.a(1), 0)
                self.assertNotIn(odsluch.MASTER_FADER, [a for a, _ in self.zapisy(start)])
                with self.assertRaises(NaruszenieZapory):
                    self.r.zapora.sprawdz(s.wysylka(1, 9), .5, self.r.widok)

    def test_master_wylaczony_blokuje(self):
        self.sym.wartosci[odsluch.MASTER] = 0
        self.assertTrue(self.r.synchronizuj())
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.odswiez()
        self.assertEqual(self.a(1), 0)

    def test_stary_tryb_nie_wymaga_minus30(self):
        self.u.zachowanie.pop('tryb_odsluchu')
        self.assertTrue(self.r.synchronizuj())
        blokuje_przed = self.r.zapora.profil_blokuje
        self.sym.wartosci[odsluch.MASTER_FADER] = ZERO_DB
        start = len(self.sym.dziennik)
        self.assertTrue(self.r.synchronizuj())
        self.assertEqual(self.r.zapora.profil_blokuje, blokuje_przed)
        self.odswiez()
        self.assertNotIn(odsluch.MASTER_FADER, [a for a, _ in self.zapisy(start)])

    def test_zly_profil_nie_otwiera(self):
        self.sym.wartosci['/routing/aux/03/src'] = 28
        self.assertTrue(self.r.synchronizuj())
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.odswiez()
        self.assertEqual(self.a(1), 0)

    def test_utrata_nie_otwiera(self):
        self.r._utrata('test')
        start = len(self.sym.dziennik)
        self.odswiez()
        self.assertEqual(self.zapisy(start), [])

    def test_odmowa_pfl_po_niepotwierdzonym_zamknieciu(self):
        self.cue('telefon')
        self.sym.awarie.ignoruj_zapis.add(s.wysylka(1, 9))
        self.nacisnij('przycisk', 4, 3)
        self.assertFalse(self.pfl('muzyka1'))

    def test_f4_f5_nie_dopasuja_odsluchu(self):
        start = len(self.sym.dziennik)
        self.klawisz('F4_tryb_informacji')
        self.klawisz('F5_ostatni_komunikat')
        self.assertEqual(self.zapisy(start), [])

    def test_start_tylko_zamyka_i_nie_otwiera_programu(self):
        for k in range(1, 11):
            self.sym.wartosci[s.wysylka(k, 9)] = 0
        start = len(self.sym.dziennik)
        self.r.synchronizuj()
        self.assertEqual(self.zapisy(start), [])

    def test_rezerwa_inserty_usb_glosniki_nietkniete(self):
        chronione = {a: v for a,v in self.sym.wartosci.items() if a.startswith(('/routing/usb/', '/fx/', '/bus/5/', '/ch/11/', '/ch/12/', '/ch/13/', '/ch/14/', '/ch/15/', '/ch/16/')) or '/insert/' in a}
        self.cue('telefon')
        self.cue('zoom')
        self.klawisz('F1_mikrofon')
        self.ten_sam_stan({a:self.m(a) for a in chronione}, chronione)
        self.assertEqual(self.naruszenia_miksera(), [])


    def test_osobista_baza_na_symulatorze_bez_dopisanych_nastaw(self):
        if MIG is None:
            self.skipTest('Integracja wymaga fixture osobistej BAZY')
        sys.path.insert(0, str(ROOT / 'narzedzia'))
        from format_scn import stan_mostka, czytaj_scn
        from mostek import konwersje
        wej = DANE
        src = (wej / 'BAZA.scn').read_text()
        nowa, _ = MIG.przygotuj(src)
        dane = stan_mostka(czytaj_scn(nowa), konwersje)
        # Osobista BAZA po migracji musi pasować do profilu bez jego naprawiania.
        self.assertAlmostEqual(dane[odsluch.MASTER_FADER], .25, delta=.005)
        self.assertEqual(dane[odsluch.MASTER], 1)
        self.u = self.r.u = wczytaj(wej/'stanowisko.json', wej/'poziomy_bazowe.json')
        self.u.zachowanie['tryb_odsluchu'] = 'aux34_mono'
        self.r.widok.u = self.r.zapora.u = self.u
        # To jawne warunki runtime testu, nie odczyt sprzętu ani zawartość SCN.
        dane.update({s.solo(k): 0 for k in (*range(1, 17), *range(40, 46), 50)})
        dane[s.SCENA_INDEKS] = 17
        self.assertEqual(set(wszystkie_adresy_odczytu(self.u)) - set(dane), set())
        self.sym.wartosci = dane
        self.assertTrue(self.r.synchronizuj())
        self.assertFalse(self.r.zapora.profil_blokuje)
        self.cue('telefon')
        self.assertEqual(self.a(9), 0)
        self.assertTrue(self.pfl('mikrofon'))
        self.assertTrue(self.pfl('telefon'))
        self.assertEqual(self.naruszenia_miksera(), [])
        self.assertEqual(self.m('/routing/aux/05/src'), 31)
        self.assertEqual(self.m('/routing/aux/06/src'), 31)

    def test_kazdy_zapis_macierzy_ma_najwyzej_jedna_kopie(self):
        oryginal = self.sym.przyjmij
        probki = []
        def przyjmij(dane, nadawca):
            wynik = oryginal(dane, nadawca)
            v = cast(dict[str, Any], self.sym.wartosci)
            solo = any(v[s.solo(k)] == 1 for k in range(1, 17))
            for k in range(1, 11):
                aux = v[s.wysylka(k, 9)] > 0 and v[s.fader(k)] > 0
                phones = (v[s.solo(k)] == 1 if solo else
                          v[s.MONITOR_ZRODLO] in (1, 2, 3) and v[s.lr(k)] == 1 and v[s.fader(k)] > 0)
                probki.append((k, int(aux) + int(phones)))
            return wynik
        self.sym.przyjmij = przyjmij
        self.klawisz('F1_mikrofon')
        self.cue('telefon')
        self.cue('zoom')
        self.cue('telefon')
        self.ruch('telefon', 1.0)
        self.nacisnij('przycisk', 4, 3)
        self.nacisnij('przycisk', 1, 2)
        self.nacisnij('puszczenie', 1, 2)
        self.r.sluchaj_programu()
        self.odswiez()
        self.r.koniec_pfl()
        self.odswiez()
        self.assertTrue(probki)
        self.assertEqual([p for p in probki if p[1] > 1], [])

    def test_macierz_pieciu_punktow_z_surowych_nastaw(self):
        # Oczekiwania z kontraktu, nie z odsluch.cel ani produkcyjnego Widoku.
        U, M, T, Z, C = 'muzyka', 'mikrofon', 'telefon', 'zoom', 'muzyka ciszej'
        przypadki = [
            ('spoczynek', [], ({U}, set(), {U}, {U}, {U})),
            ('sam M', ['M'], ({U,M}, set(), {U,M}, {U,M}, {U,M})),
            ('pełna antena', ['M','AT','AZ'], ({U,M,T,Z}, set(), {U,M,T,Z}, {U,M,Z}, {U,M,T})),
            ('CUE T', ['CT'], ({U}, {U}, {M,T}, {C,M}, {U})),
            ('CUE Z', ['CZ'], ({U}, {U}, {M,Z}, {U}, {C,M})),
            ('CUE T+Z', ['CT','CZ'], ({U}, {U}, {M,T,Z}, {C,M,Z}, {C,M,T})),
            ('T antena Z CUE', ['AT','CZ'], ({U,T}, {U,T}, {M,Z}, {U}, {C,M})),
            ('Z antena T CUE', ['AZ','CT'], ({U,Z}, {U,Z}, {M,T}, {C,M}, {U})),
            ('talkback T', ['BT'], ({U}, set(), {U}, {C,M}, {U})),
            ('talkback Z', ['BZ'], ({U}, set(), {U}, {U}, {C,M})),
            ('talkback T+Z', ['BT','BZ'], ({U}, set(), {U}, {C,M}, {C,M})),
            ('kaszel antena', ['M','K'], ({U}, set(), {U}, {U}, {U})),
            ('kaszel CUE', ['CT','CZ','K'], ({U}, {U}, {T,Z}, {C,Z}, {C,T})),
            ('kaszel talkback', ['BT','BZ','K'], ({U}, set(), {U}, {C}, {C})),
        ]
        for nazwa, akcje, oczekiwane in przypadki:
            with self.subTest(stan=nazwa):
                h = TestAux34()
                h.setUp()
                try:
                    for akcja in akcje:
                        if akcja == 'M': h.klawisz('F1_mikrofon')
                        elif akcja in ('AT','AZ'): h.ruch(T if akcja == 'AT' else Z, 1.0)
                        elif akcja in ('CT','CZ'): h.cue(T if akcja == 'CT' else Z)
                        elif akcja in ('BT','BZ'): h.nacisnij('przycisk', 2 if akcja == 'BT' else 3, 2)
                        elif akcja == 'K': h.nacisnij('przycisk', 1, 2)
                    h.odswiez()
                    aux = {h.GRUPY[z] for z, dane in h.u.zrodla.items()
                           if any(h.a(k) > 0 and cast(float, h.m(s.fader(k))) > 0 for k in dane.kanaly)}
                    solo = any(h.m(s.solo(k)) == 1 for k in range(1,17))
                    phones = {h.GRUPY[z] for z,dane in h.u.zrodla.items()
                              if any(h.m(s.solo(k)) == 1 for k in dane.kanaly)} if solo else (h.antena() if h.m(s.MONITOR_ZRODLO) == 1 else set())
                    self.assertEqual((h.antena(), aux, phones, h.slyszy(T), h.slyszy(Z)), oczekiwane)
                    self.assertEqual(h.naruszenia_miksera(), [])
                    self.assertEqual(h.a(9), 0)
                    self.assertEqual(h.m('/routing/aux/03/src'), h.m('/routing/aux/04/src'))
                finally:
                    h.tearDown()

    def test_n1_zoom_zachowuje_osobne_lewe_i_prawe_wejscia(self):
        # Model symbolicznych impulsów, nie DSP: surowa macierz wysyłek.
        self.klawisz('F1_mikrofon')
        self.ruch('telefon', 1.0)
        self.ruch('zoom', 1.0)
        for lewy,prawy in ((1,2),(3,4),(5,6)):
            self.assertGreater(cast(float, self.m(s.wysylka(lewy,3))), 0)
            self.assertGreater(cast(float, self.m(s.wysylka(prawy,4))), 0)
            self.assertEqual(self.m(s.wysylka(lewy,4)), 0)
            self.assertEqual(self.m(s.wysylka(prawy,3)), 0)
        for k in (7,8):
            self.assertEqual(self.m(s.wysylka(k,3)), 0)
            self.assertEqual(self.m(s.wysylka(k,4)), 0)
        self.assertEqual(self.m(s.wysylka(10,1)), 0)

    def test_pfl_rozmowcy_linkowana_para_i_powrot(self):
        self.ruch('zoom', 1.0)
        self.r.przelacz_pfl('zoom')
        self.odswiez()
        for k in (7,8):
            self.assertEqual(self.a(k), 0)
            self.assertEqual(self.m(s.solo(k)), 1)
        self.r.koniec_pfl()
        self.odswiez()
        for k in (7,8):
            self.assertEqual(self.a(k), 0)
            self.assertEqual(self.m(s.solo(k)), 0)

    def test_cel_fader_zero_posredni_maks_i_mute_post(self):
        self.cue('telefon')
        # POST/mute to założenie topologii do próby na stole, nie symulacja audio.
        przed = self.a(1)
        for db in (-90, -18, 0):
            self.inny(s.fader(1), poziom_db_na_float(db))
            self.odswiez()
            self.assertEqual(self.m(s.tap(1,9)), 4)
            self.assertAlmostEqual(self.a(1), przed)
        self.inny('/ch/01/mix/on', 0)
        self.odswiez()
        self.assertEqual(self.m('/ch/01/mix/on'), 0)
        self.assertAlmostEqual(self.a(1), przed)
        self.assertNotIn('/ch/01/mix/on', [a for a,_ in self.zapisy()])

    def test_obcy_main_off_zamyka_rozmowce(self):
        self.ruch('telefon', 1.0)
        self.cue('zoom')
        self.assertGreater(self.a(10), 0)
        self.inny(s.lr(10), 0)
        self.odswiez()
        self.assertEqual(self.a(10), 0)
        with self.assertRaises(NaruszenieZapory):
            self.r.zapora.sprawdz(s.wysylka(10,9), .5, self.r.widok)

    def test_poziomy_send3_bez_zmiany_trymu(self):
        self.cue('telefon')
        for k in range(1,7):
            self.assertAlmostEqual(self.a(k), poziom_db_na_float(-6))
        self.ruch('telefon', 1.0)
        self.ruch('zoom', 1.0)
        self.cue('telefon')
        for k in (7,8):
            self.assertAlmostEqual(self.a(k), ZERO_DB)
        self.assertEqual(self.a(9), 0)

    def test_talkback_z_programu_przywraca_podzial_phones_aux(self):
        self.r.sluchaj_programu()
        self.odswiez()
        self.nacisnij('przycisk', 2, 2)
        self.assertEqual(self.m(s.MONITOR_ZRODLO), 1)
        self.assertFalse(self.pfl('mikrofon'))
        self.assertFalse(self.pfl('telefon'))
        self.assertEqual(self.a(9), 0)
        self.assertEqual(self.a(10), 0)
        self.assertEqual(self.a(1), 0)

    def test_stare_stanowisko_dalej_odmawia_fx(self):
        self.u.zachowanie.pop('tryb_odsluchu')
        with self.assertRaises(NaruszenieZapory):
            self.r.zapora.sprawdz(s.wysylka(1, 9), .5, self.r.widok)


@unittest.skipUnless(MIG is not None, 'Integracja wymaga fixture osobistej BAZY')
class TestOsobiste(unittest.TestCase):
    def test_duplikaty_idempotencja_i_tylko_dozwolone(self):
        src = (DANE / 'BAZA.scn').read_text()
        dst, zm = MIG.przygotuj(src)
        self.assertEqual(len(src.splitlines()), len(dst.splitlines()))
        self.assertEqual(MIG.przygotuj(dst), (dst, []))
        for a,b in zip(src.splitlines(), dst.splitlines()):
            if a != b:
                self.assertTrue(a.startswith(('/config/solo ', '/fxsend/3/mix ', '/routing/aux/03 ', '/routing/aux/04 ')) or (a.startswith('/ch/') and '/mix/09 ' in a))
        self.assertTrue(zm)
        self.assertEqual([l for l in src.splitlines() if '/preamp ' in l], [l for l in dst.splitlines() if '/preamp ' in l])

    def test_osobiste_ustawienia_fixture(self):
        wej = DANE
        u = wczytaj(wej/'stanowisko.json', wej/'poziomy_bazowe.json')
        przed = copy.deepcopy(u.surowe)
        u.zachowanie['tryb_odsluchu'] = 'aux34_mono'
        self.assertFalse(u.alarm_ciszy['wlaczony'])
        for zr in ('muzyka1','muzyka2','muzyka3','telefon','zoom'):
            self.assertEqual(u.zrodla[zr].suwak_maks_db, 0)
        from mostek.ustawienia import sprawdz
        sprawdz(u)
        przed['zachowanie']['tryb_odsluchu'] = 'aux34_mono'
        self.assertEqual(przed, u.surowe)


if __name__ == '__main__':
    unittest.main()
