"""Czytnik i walidator tekstowych węzłów .scn. Bez zależności, bez sieci.
Waliduje KAŻDY wiersz względem schematu sceny, nie tylko parametry mostka.

Schemat: własny plik dane_sceny/schemat-mr18.json, zmierzony na Midas MR18
(opis pochodzenia każdego pola w polu "zrodlo"). Klasa przyjmuje też opis
w składni scn.xnd, jeśli ktoś ma go lokalnie; projekt go nie dołącza.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import re
import shlex


class BladSceny(ValueError):
    pass


def czytaj_scn(text: str) -> dict[str, list[str]]:
    """Węzły pliku .scn. Identyczny powtórzony wiersz jest pomijany: AOSC
    z prawdziwym MR18 zapisuje całe odpowiedzi /node, a mikser odsyła np.
    /ch/01/gate razem z /ch/01/gate/filter, więc węzeł filtra pojawia się
    w pliku dwa razy (scena Michała z 21.10.2026: 1076 wierszy, 383 identyczne
    powtórzenia). Ten sam adres z INNĄ wartością nadal jest błędem."""
    rows = {}
    for nr, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if line.startswith('#2.1#') and nr == 1:
            continue
        try:
            parts = shlex.split(line)
        except ValueError as e:
            raise BladSceny(f'Wiersz {nr}: {e}') from e
        if not parts or not parts[0].startswith('/') or len(parts) < 2:
            raise BladSceny(f'Wiersz {nr}: brak adresu/wartości')
        if parts[0] in rows:
            if rows[parts[0]] == parts[1:]:
                continue    # POPRAWKA AOSC: identyczne powtórzenie z odpowiedzi /node
            raise BladSceny(f'Wiersz {nr}: adres {parts[0]} powtórzony z inną wartością')
        rows[parts[0]] = parts[1:]
    return rows


def num(token: str) -> float:
    # Zapis częstotliwości w przykładach AOSC: 1k97 = 1970 Hz.
    if token == '-oo':
        return float('-inf')
    if re.fullmatch(r'[+-]?\d+k\d*', token):
        a, b = token.split('k')
        return float(a + '.' + (b or '0')) * 1000
    value = float(token)
    if not math.isfinite(value):
        raise BladSceny('Niedozwolone NaN/inf')
    return value


KODY = {'tekst': 's', 'przelacznik': 'b', 'lista': 'm', 'maska': 'g', 'liniowa': 'l',
        'logarytmiczna': 'e', 'poziom': 'x', 'zarezerwowane': 'z'}


def pole_json(p: dict) -> tuple[str, str]:
    """Pole schematu JSON jako para (rodzaj, parametry) jak w scn.xnd.
    Kroki 0 znaczą: bez zaokrąglania po naszej stronie (robi to mikser)."""
    r = p['rodzaj']
    if r not in KODY:
        raise BladSceny(f'Nieznany rodzaj pola schematu: {r}')
    k = KODY[r]
    if r == 'lista':
        return k, ';'.join(p['wartosci'])
    if r in ('liniowa', 'logarytmiczna'):
        return k, f"{float(p['od'])!r},{float(p['do'])!r},{int(p.get('kroki') or 0)}"
    if r == 'poziom':
        return k, str(p['kroki']) if p.get('kroki') else ''
    return k, ''


class Schemat:
    def __init__(self, text: str):
        self.text = text
        self.i = 0
        self.json = None
        if text.lstrip().startswith('{'):
            self._z_json(json.loads(text))
            return
        self.tree = self.lista()
        self.spacje()
        if self.i != len(text):
            raise BladSceny('Nadmiar tekstu po schemacie')

    def _z_json(self, d: dict):
        if d.get('format') != 'mostek-mr18/schemat-sceny':
            raise BladSceny('To nie jest schemat sceny mostka (pole format).')
        self.json = d
        self.wezly = list(d['wezly'])
        self.klasy = []
        for k in d['klasy']:
            pola = k['pola']
            efekt = len(pola) == 1 and pola[0]['rodzaj'] == 'efekt'
            self.klasy.append((re.compile(k['wzorzec']), None if efekt else [pole_json(p) for p in pola]))
        self.efekty = {}
        for nazwa, e in d['efekty'].items():
            pola = [pole_json(p) for p in e['pola']]
            pola += [('z', '')] * (e['pola_lacznie'] - len(pola))
            self.efekty[nazwa] = pola

    def _pola_json(self, path: str, rows: dict):
        for wzor, pola in self.klasy:
            if wzor.fullmatch(path):
                if pola is not None:
                    return list(pola)
                typ = rows[path.rsplit('/', 1)[0]][0]
                if typ not in self.efekty:
                    raise BladSceny(f'Nieznany typ efektu {typ} w {path}')
                return list(self.efekty[typ])
        raise BladSceny(f'Brak węzła {path} w schemacie')

    def spacje(self):
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def znak(self, c):
        self.spacje()
        if self.text[self.i:self.i + 1] != c:
            raise BladSceny(f'Schemat: oczekiwano {c!r} przy {self.i}')
        self.i += 1

    def lista(self):
        self.znak('[')
        nodes = {}
        while True:
            self.spacje()
            if self.text[self.i] == ']':
                self.i += 1
                return nodes
            self.znak('{')
            self.spacje()
            match = re.match(r'([^\s{}\[\]]+)\s+', self.text[self.i:])
            name = ''
            if match and not re.fullmatch(r'(?:[smlegbxz](?:\([^)]*\))?)+', match[1]):
                name = match[1]
                self.i += match.end()
            fields = []
            while True:
                self.spacje()
                c = self.text[self.i]
                if c in '[}':
                    break
                if c not in 'smlegbxz':
                    raise BladSceny(f'Nieznany typ {c!r} przy {self.i}')
                self.i += 1
                params = ''
                if self.text[self.i:self.i + 1] == '(':
                    end = self.text.index(')', self.i)
                    params = self.text[self.i + 1:end]
                    self.i = end + 1
                fields.append((c, params))
            children = self.lista() if self.text[self.i] == '[' else {}
            self.znak('}')
            if name in nodes:
                raise BladSceny(f'Powtórzony węzeł schematu: {name}')
            nodes[name] = (fields, children)

    def pola(self, path: str, rows: dict):
        if self.json is not None:
            return self._pola_json(path, rows)
        children = self.tree
        fields = []
        for part in path.strip('/').split('/'):
            key = part if part in children else ''
            if path.startswith('/headamp/') and part.isdigit() and int(part) > 16:
                key = '_'
            if key not in children:
                raise BladSceny(f'Brak węzła {path} w schemacie')
            fields, children = children[key]
        if path.startswith('/fx/') and path.endswith('/par'):
            typ = rows[path.rsplit('/', 1)[0]][0]
            for part in typ.split('/'):
                fields, children = children[part]
        # Szablon definiuje pan wspólnie, ale zapisują go tylko nieparzyste
        # wysyłki Bus 1/3/5 (pomiar /ch/16/mix/01 i /02 na MR18).
        if re.fullmatch(r'/(?:ch/\d\d|rtn/(?:aux|[1-4]))/mix/\d\d', path):
            b = int(path[-2:])
            if b not in (1, 3, 5):
                fields = fields[:-1]
        return fields

    def sprawdz(self, rows: dict):
        scalar_count = 0
        for path, values in rows.items():
            fields = self.pola(path, rows)
            if len(fields) != len(values):
                raise BladSceny(f'{path}: {len(values)} pól, schemat wymaga {len(fields)}')
            for i, (spec, token) in enumerate(zip(fields, values), 1):
                try:
                    sprawdz_token(spec, token)
                except (ValueError, OverflowError) as e:
                    raise BladSceny(f'{path}, pole {i}, {token!r}: {e}') from e
            scalar_count += len(values)
        return scalar_count


def sprawdz_token(spec, token):
    kind, args = spec
    if kind == 's':
        if any(ord(c) < 32 for c in token):
            raise BladSceny('Znak sterujący w nazwie')
        return
    if kind == 'b':
        if token not in ('ON', 'OFF'):
            raise BladSceny('Oczekiwano ON/OFF')
    elif kind == 'm':
        if token not in args.split(';'):
            raise BladSceny(f'Wartość spoza enum {args}')
    elif kind == 'g':
        if not re.fullmatch(r'%[01]{4}', token):
            raise BladSceny('Oczekiwano maski 4-bitowej')
    elif kind == 'z':
        if token != '0':
            raise BladSceny('Zarezerwowane pole musi być 0')
    elif kind == 'x':
        if token != '-oo' and not -90 <= num(token) <= 10:
            raise BladSceny('Poziom poza -90..10 dB')
    elif kind in ('l', 'e'):
        lo, hi, _ = map(float, args.split(','))
        if not min(lo, hi) <= num(token) <= max(lo, hi):
            raise BladSceny(f'Wartość poza {lo}..{hi}')
    else:
        raise BladSceny('Nieznany typ')


def stan_mostka(rows: dict, konwersje) -> dict[str, object]:
    """Przekład WYŁĄCZNIE pól obecnych w scenie. Bez domyślnych z symulatora.
    Kolejność pól: schemat sceny; nazwy pól: publiczna lista parametrów OSC X AIR.
    Skale poziomów/gain/trim/dim: publiczne mostek.konwersje (te same źródła).
    Brak solo i indeksu snapshotu pozostaje brakiem, nie dopisanym zerem.
    """
    state = {}
    boolean = {'OFF': 0, 'ON': 1}
    tap = ('IN', 'PREEQ', 'POSTEQ', 'PRE', 'POST', 'GRP')
    slot = ('OFF', 'Fx1A', 'Fx1B', 'Fx2A', 'Fx2B', 'Fx3A', 'Fx3B', 'Fx4A', 'Fx4B')
    src = [f'Ch{i:02d}' for i in range(1, 17)] + ['AuxL', 'AuxR'] + [f'Fx{i}{lr}' for i in range(1, 5) for lr in 'LR'] + [f'Bus{i}' for i in range(1, 7)] + [f'Send{i}' for i in range(1, 5)] + ['L', 'R']
    key = ['SELF'] + [f'Ch{i:02d}' for i in range(1, 17)] + [f'Bus{i}' for i in range(1, 7)]
    mon = ('OFF', 'LR', 'LRPFL', 'LRAFL', 'AUX', 'U1718', 'Bus1', 'Bus2', 'Bus3', 'Bus4', 'Bus5', 'Bus6', 'Bus12', 'Bus34', 'Bus56')
    for path, v in rows.items():
        if path == '/config/chlink' or path == '/config/buslink':
            for n, tok in enumerate(v):
                state[f'{path}/{2*n+1}-{2*n+2}'] = boolean[tok]
        elif path == '/config/solo':
            state.update({path + '/level': konwersje.poziom_db_na_float(num(v[0])),
                          path + '/source': mon.index(v[1]),
                          path + '/chmode': ('PFL', 'AFL').index(v[3]),
                          path + '/busmode': ('PFL', 'AFL').index(v[4]),
                          path + '/dimatt': konwersje.dimatt_db_na_float(num(v[5])),
                          **{path + '/' + field: boolean[tok] for field, tok in zip(('dim', 'mono', 'mute', 'dimpfl'), v[6:])}})
        elif re.fullmatch(r'/(ch/\d\d|bus/[1-6]|rtn/(aux|[1-4]))/mix', path):
            state.update({path + '/on': boolean[v[0]], path + '/fader': konwersje.poziom_db_na_float(num(v[1])),
                          path + '/lr': boolean[v[2]], path + '/pan': (num(v[3]) + 100) / 200})
        elif re.fullmatch(r'/(ch/\d\d|rtn/(aux|[1-4]))/mix/\d\d', path):
            state[path + '/level'] = konwersje.poziom_db_na_float(num(v[0]))
            state[path + '/grpon'] = boolean[v[1]]
            state[path + '/tap'] = tap.index(v[2])
            if len(v) == 4:
                state[path + '/pan'] = (num(v[3]) + 100) / 200
        elif re.fullmatch(r'/ch/\d\d/grp', path):
            state[path + '/dca'], state[path + '/mute'] = [int(tok[1:], 2) for tok in v]
        elif re.fullmatch(r'/ch/\d\d/preamp', path):
            state[path + '/rtntrim'] = konwersje.trim_db_na_float(num(v[0]))
            state[path + '/rtnsw'] = boolean[v[1]]
        elif re.fullmatch(r'/headamp/\d\d', path):
            if int(path[-2:]) <= 16:
                state[path + '/gain'] = konwersje.gain_db_na_float(num(v[0]))
                state[path + '/phantom'] = boolean[v[1]]
        elif re.fullmatch(r'/ch/\d\d/insert', path):
            state[path + '/on'], state[path + '/sel'] = boolean[v[0]], slot.index(v[1])
        elif re.fullmatch(r'/ch/\d\d/dyn', path):
            state[path + '/on'], state[path + '/keysrc'] = boolean[v[0]], key.index(v[12])
        elif re.fullmatch(r'/routing/usb/\d\d', path):
            state[path + '/src'] = src.index(v[0])
    return state
