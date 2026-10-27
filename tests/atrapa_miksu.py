"""Syntetyczny model Mix* dla atrapy TCP. Nie zastępuje odbioru SARY.

Jedna sesja należy do konkretnego połączenia. Model utrzymuje stan, PFL,
cofanie i walidację, ale nie zapisuje plików ani nie odtwarza dźwięku.
"""
from decimal import Decimal

PUNKTY = ('cue', 'intro', 'outro', 'segue', 'segue_fade', 'overlap', 'loop_start', 'loop_end')


class AtrapaMiksu:
    def __init__(self):
        self.wlasciciel = None
        self.busy = False
        self.pfl = True
        self.dlugosc = 225000
        self.zapisane: dict[str, int | None] = dict.fromkeys(PUNKTY)
        self.zapisane['cue'] = 500
        self.punkty = dict(self.zapisane)
        self.pozycja = 500
        self.punkt = 'cue'
        self.odsluch = 'brak'
        self.cofanie = []
        self.indeks = -1
        self.antenowa_pozycja = 90000

    def zamknij(self, klient):
        if self.wlasciciel is klient:
            self.wlasciciel = None
            self.odsluch = 'brak'
            self.punkty = dict(self.zapisane)

    def stan(self):
        v = self.punkty[self.punkt]
        return f'{self.pozycja}|{self.punkt}|{v if v is not None else "-"}|{int(self.punkty != self.zapisane)}|{self.odsluch}'

    def _ogranicz(self, x):
        return max(0, min(self.dlugosc, x))

    def _ustaw(self):
        v = self.dlugosc - self.pozycja if self.punkt == 'overlap' else self.pozycja
        if self.punkt == 'overlap':
            # Przykładowe ograniczenie edytora: od cue do segue/końca.
            v = min(v, max(0, (self.punkty['segue'] or self.dlugosc) - (self.punkty['cue'] or 0)))
        self.punkty[self.punkt] = v
        a, b = self.punkty['loop_start'], self.punkty['loop_end']
        if a is not None and b is not None and a >= b:
            if self.punkt == 'loop_start':
                self.punkty['loop_end'] = min(self.dlugosc, a + 1)
            elif self.punkt == 'loop_end':
                self.punkty['loop_start'] = max(0, b - 1)

    def odpowiedz(self, p, klient, serwer):
        nazwa, _, arg = p.partition('=')
        if nazwa == 'mixopen':
            if self.wlasciciel is not None:
                return 'ERR session'
            if self.busy:
                return 'ERR busy'
            if serwer.indeks < 0:
                return 'ERR empty'
            self.wlasciciel = klient
            self.indeks = serwer.indeks
            self.punkty = dict(self.zapisane)
            self.pozycja, self.punkt = self.punkty['cue'] or 0, 'cue'
            self.cofanie = []
            self.odsluch = 'brak'
            return f'OK|{self.indeks}|{int(serwer.gra and serwer.curr == self.indeks)}|{self.dlugosc}|Żółć|Utwór {self.indeks}'
        if self.wlasciciel is not klient or klient is None:
            return 'ERR nosession'
        if nazwa == 'mixcancel':
            self.zamknij(klient)
            return 'OK'
        if nazwa == 'mixsave':
            a = [self.punkty[k] for k in ('cue', 'intro', 'outro') if self.punkty[k] is not None]
            if any(x >= y for x, y in zip(a, a[1:])):
                return 'ERR invalid|kolejnosc'
            a, b = self.punkty['loop_start'], self.punkty['loop_end']
            if a is not None and b is not None and a >= b:
                return 'ERR invalid|petla'
            self.zapisane = dict(self.punkty)
            segue = self.punkty['segue'] if self.punkty['segue'] is not None else self.dlugosc
            self.zamknij(klient)
            if not serwer.gra or serwer.curr != self.indeks:
                return 'OK|nie_gra'
            if serwer.hold or (self.punkty['segue'] is None and not self.punkty['overlap']
                               and not self.punkty['segue_fade']):
                return 'OK|brak_przejscia'
            za = segue - self.antenowa_pozycja
            return f'OK|przejscie_za={za}' if za > 0 else 'OK|przejscie_teraz'
        if nazwa == 'mixpoint':
            i = PUNKTY.index(self.punkt)
            self.punkt = PUNKTY[(i + (1 if arg == 'next' else -1)) % len(PUNKTY)] if arg in ('next', 'prev') else arg
        elif nazwa == 'mixpos':
            delta = int(Decimal(arg[1:] if arg.startswith('@') else arg) * 1000)
            self.pozycja = self._ogranicz(delta if arg.startswith('@') else self.pozycja + delta)
        elif nazwa in ('mixset', 'mixclear', 'mixnudge'):
            if nazwa == 'mixnudge' and not self.pfl:
                return 'ERR pfl'
            self.cofanie.append((dict(self.punkty), self.punkt, self.pozycja))
            if nazwa == 'mixclear':
                self.punkty[self.punkt] = None
            else:
                if nazwa == 'mixnudge':
                    v = self.punkty[self.punkt]
                    start = self.pozycja if v is None else (self.dlugosc - v if self.punkt == 'overlap' else v)
                    self.pozycja = self._ogranicz(start + int(Decimal(arg) * 1000))
                    self.odsluch = 'przejscie' if self.punkt in ('segue', 'segue_fade') else 'punkt'
                self._ustaw()
        elif nazwa == 'mixundo':
            if self.cofanie:
                self.punkty, self.punkt, self.pozycja = self.cofanie.pop()
        elif nazwa == 'mixstop':
            self.odsluch = 'brak'
        elif nazwa in ('mixplay', 'mixplaypoint', 'mixplaymix'):
            if not self.pfl:
                return 'ERR pfl'
            self.odsluch = ('brak' if self.odsluch != 'brak' else 'pozycja') if nazwa == 'mixplay' else (
                'punkt' if nazwa == 'mixplaypoint' else 'przejscie')
        elif nazwa != 'mixinfo':
            return 'ERR syntax'
        return self.stan()
