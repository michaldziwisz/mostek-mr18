"""Własny schemat sceny MR18 (dane_sceny/schemat-mr18.json).

Sprawdza budowę schematu, jego pokrycie BAZY i pomiarów oraz to, że skale
odtwarzają próbki zmierzone na MR18 (tests/dane_sceny/pomiar-mr18-probki.json).
"""
import json
import math
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from narzedzia import scena_mr18 as s  # noqa: E402
from narzedzia.format_scn import Schemat, czytaj_scn, pole_json  # noqa: E402

PLIK = REPO / 'dane_sceny/schemat-mr18.json'
PROBKI = REPO / 'tests/dane_sceny/pomiar-mr18-probki.json'


def wartosc_fizyczna(spec, f):
    """Float OSC -> wartość w jednostkach sceny, skalą ze schematu."""
    k, a = spec
    if k == 'x':
        if f <= 0:
            return float('-inf')
        return f * 40 - 30 if f >= .5 else f * 80 - 50 if f >= .25 else f * 160 - 70 if f >= .0625 else f * 480 - 90
    lo, hi = map(float, a.split(',')[:2])
    return lo + (hi - lo) * f if k == 'l' else lo * (hi / lo) ** f


def tekst_pasuje(tekst, v):
    """Czy tekst miksera to v zapisane z jego dokładnością (ostatnia cyfra)."""
    if tekst == '-oo' or math.isinf(v):
        return tekst == '-oo' and math.isinf(v)
    t = tekst.lstrip('+-')
    if 'k' in t:
        a, b = t.split('k')
        krok = 1000 * 10 ** -len(b) if b else 1000
    elif '.' in t:
        krok = 10 ** -len(t.split('.')[1])
    else:
        krok = 1.0
    roznica = abs(s.num(tekst) - v)
    return roznica <= krok * 0.51 + 1e-9 or roznica <= abs(v) * 0.006


class SchematWlasny(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dane = json.loads(PLIK.read_text(encoding='utf-8'))
        cls.schemat = Schemat(PLIK.read_text(encoding='utf-8'))
        cls.baza = czytaj_scn((REPO / 'dane_sceny/BAZA.scn').read_text(encoding='utf-8-sig'))

    def test_format_i_lista_wezlow(self):
        self.assertEqual(self.dane['format'], 'mostek-mr18/schemat-sceny')
        w = self.dane['wezly']
        self.assertEqual(len(w), 693)
        self.assertEqual(len(set(w)), 693)
        self.assertEqual(s.zakres(PLIK), w)
        self.assertEqual(list(self.baza), w, 'BAZA w kolejności węzłów schematu')

    def test_kazde_pole_ma_zrodlo(self):
        pola = [p for k in self.dane['klasy'] for p in k['pola']]
        pola += [p for e in self.dane['efekty'].values() for p in e['pola']]
        bez = [p for p in pola if p['rodzaj'] not in ('tekst',) and not p.get('zrodlo')]
        self.assertEqual(bez, [])
        self.assertTrue(all(p['zrodlo'].startswith(('pomiar', 'analogia', 'dokumentacja', 'pole type'))
                            for p in pola if p.get('zrodlo')))

    def test_kazdy_wezel_ma_dokladnie_jedna_klase(self):
        import re
        for w in self.dane['wezly']:
            n = sum(1 for k in self.dane['klasy'] if re.fullmatch(k['wzorzec'], w))
            self.assertEqual(n, 1, w)

    def test_baza_przechodzi_walidacje(self):
        self.assertEqual(self.schemat.sprawdz(self.baza), 2900)

    def test_61_efektow_z_indeksem_jak_lista_typu(self):
        typ = next(k for k in self.dane['klasy'] if k['wzorzec'] == '/fx/[1-4]')['pola'][0]['wartosci']
        self.assertEqual(len(typ), 61)
        for nazwa, e in self.dane['efekty'].items():
            self.assertEqual(typ[e['indeks']], nazwa)
            self.assertEqual(e['pola_lacznie'], 64)
            for p in e['pola']:
                pole_json(p)

    def test_zly_typ_efektu_odrzucony(self):
        rows = dict(self.baza)
        rows['/fx/1'] = ['NIEISTNIEJACY', 'ON']
        with self.assertRaises(Exception):
            self.schemat.pola('/fx/1/par', rows)

    def test_skale_odtwarzaja_probki_z_mr18(self):
        """Każda próbka: zapis wartości OSC na MR18, odczyt typowany i tekst
        /node. Tekst przeliczony naszą skalą ma dać odczyt typowany."""
        probki = json.loads(PROBKI.read_text(encoding='utf-8'))
        rows = dict(self.baza)
        sprawdzone = 0
        for p in probki['probki']:
            if p['efekt']:
                rows['/fx/4'] = [p['efekt'], 'ON']
            spec = self.schemat.pola(p['wezel'], rows)[p['pole']]
            if spec[0] in 'smbgz':
                continue
            # Odczyt typowany przeliczony naszą skalą daje tekst miksera.
            self.assertTrue(tekst_pasuje(p['tekst'], wartosc_fizyczna(spec, p['odczyt'])), (p, spec))
            # Nasz zapis tekstu trafia w ten sam krok, gdy schemat zna kroki
            # i tekst jest dość dokładny, by krok rozróżnić.
            kroki = spec[1].split(',')[2:] if spec[0] in 'le' else [spec[1]]
            if kroki and kroki[0] and float(kroki[0]):
                n = float(kroki[0])
                wynik = s.wartosc_osc(spec, p['tekst'])[1]
                if abs(wynik - p['odczyt']) > 1e-6:
                    # Dopuszczalne tylko, gdy oba kroki dają ten sam tekst.
                    self.assertTrue(tekst_pasuje(p['tekst'], wartosc_fizyczna(spec, wynik)), (p, spec, wynik))
                    self.assertLessEqual(abs(wynik - p['odczyt']) * n, 1.0001, p)
            sprawdzone += 1
        self.assertGreater(sprawdzone, 5000)

    def test_wysylki_bez_pan_na_parzystych_szynach(self):
        self.assertEqual(len(self.schemat.pola('/ch/01/mix/01', self.baza)), 4)
        self.assertEqual(len(self.schemat.pola('/ch/01/mix/02', self.baza)), 3)
        self.assertEqual(len(self.schemat.pola('/ch/01/mix/07', self.baza)), 3)


if __name__ == '__main__':
    unittest.main()
