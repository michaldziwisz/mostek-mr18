"""Kontrakt paczki testowej: wspólne dane, brak zapisu bez zgody, instrukcja."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from narzedzia import zbuduj_paczke_windows as b


class BudowaWindows(unittest.TestCase):
    def test_plan_bez_zapisu(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            r = subprocess.run([sys.executable, '-B', str(b.REPO / 'narzedzia/zbuduj_paczke_windows.py'),
                                '--katalog-pracy', str(p / 'praca'), '--wyjscie', str(p / 'wynik')],
                               capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list(p.iterdir()), [])
            self.assertIn('bez zapisu', json.loads(r.stdout)['tryb'])

    def test_instrukcja_jedna_tresc(self):
        from html.parser import HTMLParser
        class Czytnik(HTMLParser):
            def __init__(self):
                super().__init__(); self.w_main = False; self.teksty = []
            def handle_starttag(self, tag, attrs):
                if tag == 'main': self.w_main = True
            def handle_endtag(self, tag):
                if tag == 'main': self.w_main = False
            def handle_data(self, data):
                if self.w_main and data.strip(): self.teksty.append(data)
        zrodlo = b.REPO / 'narzedzia/windows/instrukcja.json'
        txt, html = b.instrukcja(zrodlo)
        parser = Czytnik(); parser.feed(html)
        bloki = json.loads(zrodlo.read_text(encoding='utf-8'))
        tresci = [s for tag, t in bloki for s in (t if isinstance(t, list) else [t])]
        self.assertEqual(parser.teksty, tresci)
        for t in tresci:
            self.assertIn(t, txt)
            self.assertNotIn('\u2014', t)
            self.assertNotIn('\u2013', t)
        self.assertIn('<html lang="pl">', html)
        self.assertEqual(html.count('<h1>'), 1)

    def test_dane_bez_dziennikow_i_zapisanego_trybu(self):
        with tempfile.TemporaryDirectory() as tmp:
            cel = Path(tmp) / 'paczka'
            b.przygotuj_dane(b.REPO, cel)
            self.assertTrue((cel / 'INSTRUKCJA.txt').read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertFalse((cel / 'ustawienia/tryb_informacji.json').exists())
            self.assertEqual(len(list(cel.glob('*.bat'))), 6)
            for folder in ('dzwieki', 'biblioteki', 'ustawienia', 'wyniki'):
                self.assertTrue((cel / folder).is_dir())
            for p in cel.glob('*.bat'):
                txt = p.read_text(encoding='utf-8')
                self.assertIn('chcp 65001', txt)
                self.assertIn('pause', txt)
                self.assertIn('pushd "%~dp0"', txt)
                if p.name.startswith(('5_', '6_')):
                    self.assertLess(txt.index('ZAPISUJE'), txt.index('"mostek.exe"'))
                    self.assertLess(txt.index('goto anuluj'), txt.index('"mostek.exe"'))
                    self.assertIn('"TAK"', txt)

    def test_scena_kompletna_albo_wyrazna_odmowa(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            scena = p / 'scena'; scena.mkdir()
            for n in ('BAZA.scn', 'WCZYTANIE-BAZY.txt', 'WCZYTANIE-BAZY.html'):
                (scena / n).write_text('ATRApa testowa ' + n, encoding='utf-8')
            (scena / 'BAZA-naglowek-2.1.scn').write_text('ATRApa wariantu', encoding='utf-8')
            b.przygotuj_dane(b.REPO, p / 'z_scena', scena)
            self.assertEqual({f.name for f in (p / 'z_scena/scena').iterdir()},
                             {'BAZA.scn', 'WCZYTANIE-BAZY.txt', 'WCZYTANIE-BAZY.html'})
            self.assertEqual((p / 'z_scena/scena/BAZA.scn').read_bytes(), (scena / 'BAZA.scn').read_bytes())
            b.przygotuj_dane(b.REPO, p / 'bez_sceny')
            self.assertIn('tylko kroki 1 do 4', (p / 'bez_sceny/scena/CZYTAJ.txt').read_text(encoding='utf-8-sig'))
            (scena / 'WCZYTANIE-BAZY.html').unlink()
            with self.assertRaises(FileNotFoundError):
                b.przygotuj_dane(b.REPO, p / 'niepelna', scena)

    def test_prosty_start_uklad_i_dokumenty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            scena = p / 'scena'; scena.mkdir()
            import shutil
            shutil.copy2(b.REPO / 'dane_sceny/BAZA.scn', scena / 'BAZA.scn')
            for n in ('WCZYTANIE-BAZY.txt', 'WCZYTANIE-BAZY.html'):
                (scena / n).write_text('Instrukcja testowa', encoding='utf-8')
            cel = p / 'paczka'
            b.przygotuj_prosty_start(b.REPO, cel, scena)
            self.assertEqual({x.name for x in cel.iterdir()},
                {'START.bat', 'RESTART.bat', 'PRZYWROC.bat', 'CZYTAJ-NAJPIERW.txt', 'CZYTAJ-NAJPIERW.html', 'program'})
            for n in ('CZYTAJ-NAJPIERW.txt', 'CZYTAJ-NAJPIERW.html'):
                self.assertTrue((cel / n).read_bytes().startswith(b'\xef\xbb\xbf'))
            txt = (cel / 'CZYTAJ-NAJPIERW.txt').read_text(encoding='utf-8-sig')
            kod = (cel / 'CZYTAJ-NAJPIERW.html').read_text(encoding='utf-8-sig')
            self.assertIn('lang="pl"', kod)
            self.assertEqual(kod.count('<li>'), 10)
            for tresc in ('693', '48 V', 'wejściu 9', 'koniec', 'PRZYWROC.bat', 'RESTART.bat'):
                self.assertIn(tresc, txt)
            for znak in ('\u2014', '\u2013', '[uzupełnij]'):
                self.assertNotIn(znak, txt)
            for n, tryb in (('START.bat', b'start'), ('RESTART.bat', b'restart'), ('PRZYWROC.bat', b'przywroc')):
                bat = (cel / n).read_bytes()
                self.assertIn(b'chcp 65001\r\n', bat.replace(b' >nul', b''))
                self.assertIn(b'"program\\prosty_start.exe" ' + tryb + b'\r\n', bat)
            dodatki = cel / 'program/dodatki'
            self.assertEqual(len(list(dodatki.glob('*.bat'))), 6)
            for plik in dodatki.glob('*.bat'):
                self.assertIn('pushd "%~dp0.."', plik.read_text())
            self.assertTrue((dodatki / 'INSTRUKCJA.txt').is_file())
            self.assertTrue((dodatki / 'INSTRUKCJA.html').is_file())

    def test_scalanie_nie_nadpisuje_innej_biblioteki(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, c = Path(tmp) / 'a', Path(tmp) / 'c'
            a.mkdir(); c.mkdir()
            (a / 'lib').write_bytes(b'1'); (c / 'lib').write_bytes(b'2')
            with self.assertRaises(ValueError): b.polacz(a, c)
            self.assertEqual((c / 'lib').read_bytes(), b'2')
            (a / 'lib').write_bytes(b'2')
            b.polacz(a, c)
