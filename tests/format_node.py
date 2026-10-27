"""Format tekstowego /node, odtworzony ze źródłowych scen X AIR.

Nie odtwarza zapamiętanych wierszy ani nie czyta BAZA.scn. Reguły i granice
potwierdzenia: dowody/FORMAT-NODE.md. Nie jest emulatorem firmware MR18.
FX CMB/CMB2: skale X AIR; prezentacja według X32.c, bez próbki MR18.
"""
from __future__ import annotations
import json
import math
import re


def physical(spec, value):
    kind, arg = spec
    v = float(value)
    if kind == 'x':
        if v <= 0:
            return float('-inf')
        if v >= .5:
            return v * 40 - 30
        if v >= .25:
            return v * 80 - 50
        if v >= .0625:
            return v * 160 - 70
        return v * 480 - 90
    lo, hi, steps = map(float, arg.split(','))
    # Odtworzenie indeksu usuwa błąd transmisji float32. Kroki: schemat sceny;
    # 0 = pole bez siatki po naszej stronie.
    if steps:
        v = math.floor(v * steps + .5) / steps
    return lo + (hi - lo) * v if kind == 'l' else lo * (hi / lo) ** v


def frequency(v, decimals=2):
    # Factory: 1977.106... -> 1k97, nie 1k98; FX: 7261... -> 7k2.
    if v < 1000:
        return f'{v:.1f}' if decimals == 2 else f'{v:.0f}'
    scale = 10 ** decimals
    n = int((v / 1000) * scale + 1e-7)
    return f'{n // scale}k{n % scale:0{decimals}d}'


def hold(v):
    # Factory: szerokość 4, 10.0 i  502. Niższe zakresy: ekstrapolacja.
    precision = 2 if v < 1 else 1 if v < 100 else 0
    return f'{v:4.{precision}f}'


def format_value(path, index, spec, value, fx_type=None):
    k, a = spec
    if k == 's':
        return json.dumps(str(value), ensure_ascii=False)
    if k == 'b':
        return 'ON' if value else 'OFF'
    if k == 'm':
        return a.split(';')[int(value)]
    if k == 'g':
        return '%' + format(int(value), '04b')
    if k == 'z':
        return '0'
    v = physical(spec, value)
    if k == 'x':
        # Sample scene zawiera +4.0, +6.0, -78.0, 0.0, -0.0 i +0.0.
        t = '-oo' if not math.isfinite(v) else f'{v:+.1f}' if v > 0 else f'{v:.1f}'
        return t.rjust(5)
    if path.startswith('/fx/') and path.endswith('/par'):
        return fx_value(fx_type, index, v)
    last = path.split('/')[-1]
    if path.startswith('/headamp/'):
        return f'{v:+.1f}'
    if path == '/config/solo':
        return f'{v:.1f}' if index == 2 else f'{v:.0f}'
    if last == 'preamp':
        return f'{v:+.1f}' if index == 0 else f'{v:3.0f}'
    if last == 'automix':
        return f'{v:+5.1f}'
    if last == 'gate':
        if index in (2, 3):
            return f'{v:.1f}'
        if index == 5:
            return hold(v)
        return f'{v:.0f}'
    if last == 'dyn':
        if index == 4:
            return f'{v:.1f}'
        if index == 7:
            return f'{v:.2f}'
        if index == 9:
            return hold(v)
        return f'{v:.0f}'
    if last == 'filter':
        return frequency(v)
    if re.search(r'/eq/\d+$', path):
        if index == 1:
            return frequency(v)
        if index == 2:
            return f'{v:+.2f}'
        return f'{v:.1f}'
    if last == 'geq':
        return f'{v:.1f}'
    if '/mix' in path:
        return f'{v:+.0f}'
    raise ValueError(f'Nieopisane pole liczbowe: {path}[{index}] {spec}')


# Każda pozycja to reguła zapisu pola efektu w tekście /node, bez przechowywania wartości.
FX = {
    'VRM': ['i','d2','i','i','i','d1','d2','d2','i','f1','i','i'],
    'HALL': ['i','d2','i','f2','i','d1','i','f1','d2','i','i','i'],
    'MODD': ['i',None,'d1','i','f1','i','d2',None,None,'d1','f1','signed','i'],
    'DIMC': [],
    'DES2': ['d1'] * 4,
    # LIM: zapis z pomiaru MR18 fw 1.26 (tests/dane_sceny/pomiar-mr18-probki.json).
    'LIM': ['d1', 'd1', 'i', 'i', 'd2', 'i'],
}


def fx_value(fx_type, index, v):
    if fx_type in ('CMB', 'CMB2'):
        # Maillot X32.c 2614–2674: release ma .1f, pozostałe liczby .0f.
        # Źródło niezależne od BAZY, ale nie jest zrzutem firmware MR18.
        return f'{v:.1f}' if index % 29 == 4 else f'{v:.0f}'
    rules = FX.get(fx_type)
    if rules is None or index >= len(rules) or rules[index] is None:
        raise ValueError(f'Niepotwierdzony format FX {fx_type}, pole {index + 1}')
    rule = rules[index]
    if rule.startswith('f'):
        if rule == 'f2' and v < 1000:
            return f'{v:.0f}'
        return frequency(v, int(rule[1]))
    if rule == 'signed':
        return f'{v:+.0f}'
    return f'{v:.{int(rule[1])}f}' if rule.startswith('d') else f'{v:.0f}'
