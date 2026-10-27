"""Odbiór fundamentu konfiguracji. Żaden z testów nie potrzebuje sprzętu."""
import contextlib
import copy
import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mostek import glowny, ustawienia
from przypadki_walidatora import PRZYPADKI, sciezka, zmien

ROOT = Path(__file__).resolve().parents[1]
DANE = ROOT / 'tests/dane_walidatora'


def normalizuj(u):
    d = dataclasses.asdict(u)
    d['plik_poziomow'] = '$POZIOMY'
    d['plik_trybu'] = str(d['plik_trybu']).replace(str(ROOT), '$KATALOG')
    return json.loads(json.dumps(d))


class TestWalidator(unittest.TestCase):
    def setUp(self):
        self.d = json.loads((DANE / 'stanowisko.json').read_text(encoding='utf-8'))
        self.p = json.loads((DANE / 'poziomy_bazowe.json').read_text(encoding='utf-8'))

    def waliduj(self, d=None, p=None):
        from mostek.walidator import waliduj
        return waliduj(self.d if d is None else d, self.p if p is None else p)

    def bledy(self, d=None, p=None):
        return [x for x in self.waliduj(d, p) if x.poziom == 'błąd']

    def test_zlote_repo_i_michal(self):
        for nazwa, katalog in [('repo', ROOT / 'ustawienia'), ('michal', DANE)]:
            with self.subTest(nazwa=nazwa):
                u = ustawienia.wczytaj(katalog / 'stanowisko.json', katalog / 'poziomy_bazowe.json')
                wzorzec = json.loads((DANE / ('zlote-' + nazwa + '.json')).read_text(encoding='utf-8'))
                self.assertEqual(normalizuj(u), wzorzec)
                self.assertEqual(self.bledy(u.surowe, u.poziomy), [])

    def test_56_znieksztalcen_sciezki_i_zgodnosc_startu(self):
        wzorce = json.loads((DANE / 'zgodnosc-cbb5a4b.json').read_text(encoding='utf-8'))
        self.assertEqual(len(wzorce), len(PRZYPADKI))
        self.assertGreaterEqual(len(PRZYPADKI), 30)
        with tempfile.TemporaryDirectory() as tmp:
            s, p = Path(tmp) / 's.json', Path(tmp) / 'p.json'
            for przypadek, wzorzec in zip(PRZYPADKI, wzorce):
                pole = sciezka(*przypadek[:2])
                with self.subTest(pole=pole, wartosc=str(przypadek[2])):
                    d, po = zmien(self.d, self.p, przypadek)
                    self.assertIn(pole, [x.sciezka for x in self.bledy(d, po)])
                    s.write_text(json.dumps(d), encoding='utf-8')
                    p.write_text(json.dumps(po), encoding='utf-8')
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        self.assertEqual(glowny.main(['--sprawdz', '--json', '--ustawienia', str(s), '--poziomy', str(p)]), 1)
                    self.assertTrue(json.loads(out.getvalue())['bledy'])
                    if wzorzec['status'] == 'OK':
                        u = ustawienia.wczytaj(s, p)
                        sha = hashlib.sha256(json.dumps(normalizuj(u), sort_keys=True).encode()).hexdigest()
                        self.assertEqual(sha, wzorzec['sha256'])
                    else:
                        with self.assertRaises(ustawienia.BladUstawien):
                            ustawienia.wczytaj(s, p)

    def test_zbiera_wiele_i_nie_mutuje(self):
        self.d['zrodla']['mikrofon']['kanaly'] = [0]
        self.d['odbiorcy']['telefon']['szyny'] = [7]
        self.d['paski'][1]['pasek'] = 1
        przed = copy.deepcopy((self.d, self.p))
        b = self.bledy()
        for pole in ['zrodla.mikrofon.kanaly[0]', 'odbiorcy.telefon.szyny[0]', 'paski[1].pasek']:
            self.assertIn(pole, [x.sciezka for x in b])
        self.assertEqual((self.d, self.p), przed)

    def test_rozlacznosc_szyn(self):
        self.d['odbiorcy']['zoom']['szyny'] = [1, 4]
        self.assertIn('odbiorcy.zoom.szyny[0]', [x.sciezka for x in self.bledy()])

    def test_unikalnosc_paska(self):
        self.d['paski'][1]['pasek'] = 1
        self.assertIn('paski[1].pasek', [x.sciezka for x in self.bledy()])

    def test_zakres_kanalu(self):
        self.d['zrodla']['mikrofon']['kanaly'] = [17]
        self.assertIn('zrodla.mikrofon.kanaly[0]', [x.sciezka for x in self.bledy()])

    def test_typy_przed_konwersja(self):
        self.d['zrodla']['mikrofon']['kanaly'] = ['9']
        self.assertIn('zrodla.mikrofon.kanaly[0]', [x.sciezka for x in self.bledy()])

    def test_powiazanie_w_obie_strony(self):
        self.d['odbiorcy']['telefon']['wlasne_zrodlo'] = 'zoom'
        self.assertIn('odbiorcy.telefon.wlasne_zrodlo', [x.sciezka for x in self.bledy()])
        self.d['zrodla']['telefon']['odbiorca'] = 'brak'
        self.assertIn('zrodla.telefon.odbiorca', [x.sciezka for x in self.bledy()])

    def test_bledne_typy_kontenerow_nigdy_traceback(self):
        for pole, klucze, _ in PRZYPADKI:
            for v in [None, [], {}, True, 'źle']:
                with self.subTest(klucze=klucze, wartosc=v):
                    d, p = zmien(self.d, self.p, (pole, klucze, v))
                    self.assertIsInstance(self.waliduj(d, p), list)
        from mostek.walidator import waliduj
        for d in [None, [], 1, 'tekst', True]:
            self.assertTrue(waliduj(d, {}))

    def test_ostrzezenia_domyslne_i_nieznany_klucz(self):
        self.d['zrodla']['mikrofon']['_literowka'] = 'komentarz'
        del self.d['zrodla']['mikrofon']['suwak_maks_db']
        w = {x.sciezka: x for x in self.waliduj()}
        self.assertEqual(w['zrodla.mikrofon._literowka'].poziom, 'ostrzeżenie')
        self.assertEqual(w['zrodla.mikrofon.suwak_maks_db'].poziom, 'ostrzeżenie')
        self.assertIn('0', w['zrodla.mikrofon.suwak_maks_db'].komunikat)
        self.assertEqual(self.bledy(), [])

    def test_raport_zasobow_v22(self):
        from mostek.walidator import raport_zasobow
        r = raport_zasobow(self.d)
        self.assertEqual(r['kanaly']['9'], ['mikrofon'])
        self.assertEqual(r['kanaly']['10'], ['telefon'])
        self.assertEqual(r['wolne_kanaly'], [11, 12, 13, 14, 15, 16])
        self.assertEqual(r['szyny'], {'1': ['odbiorcy.telefon'], '2': ['podsluch_telefonu'],
            '3': ['odbiorcy.zoom'], '4': ['odbiorcy.zoom'], '5': ['klucz_przyciszania'], '6': ['glosniki']})
        self.assertEqual(r['wolne_szyny'], [])
        self.assertEqual(r['usb']['1']['rola'], 'N-1 Zoom, lewy')
        self.assertEqual(r['usb']['3']['rola'], 'antena Main L')
        self.assertEqual(len(r['usb']), 18)
        self.assertEqual(r['sluchacz'], 'telefon')
        self.assertEqual(r['zrodla_klucza'], ['mikrofon', 'zoom'])
        self.assertEqual(r['paski'][0]['select'], 'antena_mikrofonu')
        self.assertEqual(r['playout'], 'auto')

    def test_drugi_mikrofon_jeden_blad(self):
        d = json.loads((ROOT / 'dokumentacja/stanowisko/przyklad-dwa-mikrofony.json').read_text(encoding='utf-8'))
        b = self.bledy(d)
        self.assertEqual(len(b), 1, b)
        self.assertIn('drugi mikrofon lokalny nie jest jeszcze obsługiwany', b[0].komunikat)
        self.assertIn('projekt-drugi-mikrofon.md', b[0].komunikat)

    def test_cli_bez_sprzetu_i_zapisow(self):
        self._cli_bez_sprzetu()

    def _cli_bez_sprzetu(self):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            # Kontrola także przy jawnej prośbie o NVDA/MIDI; tryb sprawdzający
            # musi wrócić przed konstruktorami i konfiguracją dziennika.
            for nazwa in ['socket.socket', 'mostek.xtouch.PortWinMM', 'mostek.glowny.KlientMR18',
                          'mostek.mowa.utworz_wyjscie', 'mostek.informacja.utworz_odtwarzacz',
                          'mostek.mowa.KolejkaMowy', 'mostek.emisja.utworz',
                          'pathlib.Path.write_text', 'pathlib.Path.write_bytes', 'pathlib.Path.mkdir',
                          'logging.basicConfig']:
                stack.enter_context(patch(nazwa, side_effect=AssertionError(nazwa)))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                rc = glowny.main(['--sprawdz', '--ustawienia', str(DANE / 'stanowisko.json'),
                    '--poziomy', str(DANE / 'poziomy_bazowe.json'), '--midi', 'winmm', '--mowa', 'nvda'])
            except (SystemExit, AssertionError) as e:
                self.fail(f'Tryb sprawdzający nie jest odizolowany: {e}')
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().splitlines()[0], 'Stanowisko poprawne')
        self.assertIn('Wolne szyny: brak', out.getvalue())

    def test_cli_kody_i_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            s, pozi = p / 's.json', p / 'p.json'
            pozi.write_text(json.dumps(self.p), encoding='utf-8')
            for tekst, rc in [(json.dumps(self.d), 0), ('{}', 1), ('{', 2)]:
                s.write_text(tekst, encoding='utf-8')
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(glowny.main(['--sprawdz', '--json', '--ustawienia', str(s), '--poziomy', str(pozi)]), rc)
                r = json.loads(out.getvalue())
                self.assertEqual(r['kod'], rc)
                self.assertIn('problemy', r)
            s.unlink()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(glowny.main(['--sprawdz', '--json', '--ustawienia', str(s), '--poziomy', str(s)]), 2)
            self.assertEqual(len(json.loads(out.getvalue())['problemy']), 2)

    def test_cienkie_narzedzie(self):
        r = subprocess.run([sys.executable, '-B', str(ROOT / 'narzedzia/sprawdz_stanowisko.py'), '--json'],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['bledy'], 0)

    def test_nowe_bledy_tylko_ostrzezenia_startu_w_dzienniku(self):
        self.d['paski'][1]['pasek'] = 1
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp) / 's.json'
            s.write_text(json.dumps(self.d), encoding='utf-8')
            with patch('mostek.glowny.TransportUDP'), \
                 patch('mostek.glowny.KlientMR18', side_effect=StopIteration('po ostrzeżeniach')), \
                 patch('logging.basicConfig'), self.assertLogs('mostek', level='WARNING') as dziennik:
                with self.assertRaises(StopIteration):
                    glowny.main(['--mr18', '127.0.0.1', '--ustawienia', str(s),
                        '--poziomy', str(DANE / 'poziomy_bazowe.json'), '--dziennik', str(Path(tmp) / 'd.log')])
            self.assertTrue(any('paski[1].pasek' in x for x in dziennik.output))
            self.assertTrue(all('WARNING' in x for x in dziennik.output))

    def test_stary_blad_nadal_zatrzymuje_przed_urzadzeniami(self):
        self.d['zrodla']['muzyka1']['kanaly'] = [9]
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp) / 's.json'
            s.write_text(json.dumps(self.d), encoding='utf-8')
            with patch('mostek.glowny.TransportUDP') as udp, patch('mostek.xtouch.PortWinMM') as midi:
                with self.assertRaisesRegex(ustawienia.BladUstawien, 'przypisany dwa razy'):
                    glowny.main(['--mr18', '127.0.0.1', '--ustawienia', str(s)])
                udp.assert_not_called()
                midi.assert_not_called()

    def test_wszystkie_dawne_reguly_zbierane_jednoczesnie(self):
        self.d['zrodla']['muzyka3']['kanaly'] = [9]
        self.d['szyny']['klucz_przyciszania'] = 1
        self.d['szyny']['podsluch_telefonu'] = 3
        self.d['szyny']['glosniki'] = [4]
        self.d['przyciszanie']['sluchacz'] = 'muzyka1'
        self.d['przyciszanie']['zrodla_klucza'] = ['muzyka1']
        self.d['paski'][1].update(mute='kaszel', rec='antena_mikrofonu', select='pfl')
        self.d['paski'][0]['mute'] = 'talkback'
        self.d['profil']['usb_suche_dozwolone'] = [1]
        self.d['zachowanie']['alarm_ciszy'].update(prog_dbfs=5, czas_s=0, powtorka_s=0)
        self.d['zachowanie']['przyciszenie_muzyki_cue_db'] = -80
        self.d['zachowanie']['przypomnienie_mikrofonu_min'] = -1
        self.d['xtouch'].update(ponowienie_portu_s=0, zycie_s=0.1, zycie_proby=11)
        self.d['informacja_zwrotna']['zdarzenia']['nie_ma'] = 3
        self.d['informacja_zwrotna']['dzwiek_ostrzezenia'] = ''
        del self.d['komunikaty']['tryb_mowa']
        del self.p['wysylki']['mikrofon']['telefon']
        pola = {x.sciezka for x in self.bledy()}
        for pole in ['zrodla.muzyka3.kanaly[0]', 'szyny.klucz_przyciszania',
                     'szyny.podsluch_telefonu', 'szyny.glosniki[0]', 'przyciszanie.sluchacz',
                     'przyciszanie.zrodla_klucza', 'paski[1].mute', 'paski[1].rec', 'paski[1].select',
                     'paski[0].mute', 'profil.usb_suche_dozwolone',
                     'zachowanie.alarm_ciszy.prog_dbfs', 'zachowanie.alarm_ciszy.czas_s',
                     'zachowanie.alarm_ciszy.powtorka_s', 'zachowanie.przyciszenie_muzyki_cue_db',
                     'zachowanie.przypomnienie_mikrofonu_min', 'xtouch.ponowienie_portu_s',
                     'xtouch.zycie_s', 'xtouch.zycie_proby', 'informacja_zwrotna.zdarzenia.nie_ma',
                     'informacja_zwrotna.dzwiek_ostrzezenia', 'komunikaty.tryb_mowa',
                     'poziomy.wysylki.mikrofon.telefon']:
            self.assertIn(pole, pola)

    def test_pliki_uszkodzone_i_nieczytelne(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp) / 's.json'
            for blob in [b'\xff', b'{', b'[']:
                s.write_bytes(blob)
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    rc = glowny.main(['--sprawdz', '--json', '--ustawienia', str(s)])
                self.assertEqual(rc, 2)
                self.assertIn('nie można odczytać', out.getvalue())

    def test_wartosci_nieskonczone_i_duze(self):
        for v in [float('nan'), float('inf'), float('-inf'), 10 ** 400]:
            self.d['zachowanie']['alarm_ciszy']['prog_dbfs'] = v
            self.assertIn('zachowanie.alarm_ciszy.prog_dbfs', [x.sciezka for x in self.bledy()])

    def test_brak_playoutu_tylko_opcja_cli(self):
        self.d['emisja']['program'] = 'brak'
        self.assertIn('emisja.program', [x.sciezka for x in self.bledy()])

    def test_katalog_komunikatow_nie_zalezy_od_pliku(self):
        from mostek.walidator import KOMUNIKATY_V1
        self.assertEqual(set(KOMUNIKATY_V1), {k for k in self.d['komunikaty'] if not k.startswith('_')})
        for nazwa in KOMUNIKATY_V1:
            d = copy.deepcopy(self.d)
            del d['komunikaty'][nazwa]
            self.assertIn('komunikaty.' + nazwa, [x.sciezka for x in self.bledy(d)])

    def test_frozen_z_innego_katalogu_bez_zapisu(self):
        from narzedzia.zbuduj_paczke_windows import przygotuj_dane
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'paczka'
            przygotuj_dane(ROOT, p)
            przed = {str(f.relative_to(p)): f.read_bytes() for f in p.rglob('*') if f.is_file()}
            kod = ('import sys; sys.frozen=True; sys.executable=sys.argv[1]; '
                   'from mostek.glowny import main; raise SystemExit(main(["--sprawdz", "--json"]))')
            r = subprocess.run([sys.executable, '-B', '-c', kod, str(p / 'mostek.exe')], cwd=tmp,
                env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)['bledy'], 0)
            self.assertEqual({str(f.relative_to(p)): f.read_bytes() for f in p.rglob('*') if f.is_file()}, przed)


if __name__ == '__main__':
    unittest.main()
