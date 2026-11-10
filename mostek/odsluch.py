"""Odsłuch lokalny mono Send3, opt-in. Model sterowania, nie model DSP.

Bez CUE: stereo LR w PHONES, Send3 zamknięty. Podczas CUE: źródło OFF
w PHONES z magistralą SOLO, program bez mikrofonu przez mono Send3 POST.
Ręczne PFL i jawny odsłuch LR pozostają alternatywami operatora.
Nie zapisujemy mastera, routingu, insertów ani kanałów rezerwy.
"""
from math import isfinite
from . import sciezki as s
from .konwersje import poziom_db_na_float
from .stan import NIEZNANY

TRYB = "aux34_mono"
SEND = 9  # Send3 to wysyłka kanałowa 09, nie Bus3.
MASTER = "/fxsend/3/mix/on"
MASTER_FADER = "/fxsend/3/mix/fader"


def aktywny(u):
    return u.zachowanie.get("tryb_odsluchu", "dotychczasowy") == TRYB


def stale():
    # Poziom zatwierdzony odsłuchem Michała; master pozostaje tylko do odczytu.
    return {MASTER: 1, MASTER_FADER: poziom_db_na_float(-30),
            "/routing/aux/03/src": 34, "/routing/aux/04/src": 34,
            "/routing/aux/03/pos": 10, "/routing/aux/04/pos": 10}


def adresy(u):
    a = list(stale())
    for k in range(1, 17):
        a += [s.wysylka(k, SEND), s.tap(k, SEND), s.solo(k)]
    a += [s.wysylka_powrotu(p, SEND) for p in s.POWROTY]
    a += [s.solo(k) for k in range(40, 46)]
    return a


def zgodny(w):
    for a, v in stale().items():
        x = w.stan.wartosc(a)
        if x is NIEZNANY:
            return False
        try:
            liczba = float(x)
        except (TypeError, ValueError, OverflowError):
            return False
        if not isfinite(liczba) or abs(float(x) - v) > 0.005:
            return False
    # Rezerwa i powroty nie należą do miksu. Nie przejmujemy ich sterowania.
    for a in ([s.wysylka(k, SEND) for k in range(11, 17)] +
              [s.wysylka_powrotu(p, SEND) for p in s.POWROTY]):
        if w.stan.wartosc(a) != 0:
            return False
    return True


def cel(w):
    """Poziomy Send3: Main On I brak PFL, wyłącznie POST, mikrofon nigdy.

    Fader, mute, EQ, trim i dynamika są już w torze POST. Nie mnożymy
    poziomu fadera drugi raz. -6 dB par muzyki jak obecny miks programu.
    """
    wynik = {}
    cue = w.cue_zbior()
    bezpieczny = (cue is not NIEZNANY and bool(cue)
                  and w.stan.polaczony and w.stan.zsynchronizowany and zgodny(w)
                  and w.monitor() == s.ZRODLO_OFF
                  and w.stan.wartosc(s.MONITOR_TRYB_KANALOW) == 0)
    for z in w.u.zrodla.values():
        wl = (bezpieczny and z.klucz != "mikrofon" and w.suma(z.klucz) is True
              and w.pfl(z.klucz) is False)
        p = poziom_db_na_float(-6.0 if not z.glos else 0.0) if wl else 0.0
        for k in z.kanaly:
            if k <= 10:
                wynik[s.wysylka(k, SEND)] = p
    return wynik


def narusza(w, adres, wartosc):
    if not aktywny(w.u):
        return False
    # Stałe są wyłącznie sceną, mostek nie zmienia ich nawet na zero.
    if adres in stale():
        return True
    if adres.startswith('/ch/') and '/mix/09/' in adres:
        if adres.endswith('/tap'):
            return int(wartosc) != s.TAP_POST
        if adres.endswith('/level') and float(wartosc) > 0:
            limit = cel(w).get(adres, 0)
            return limit <= 0 or float(wartosc) > limit + 0.005
    return False


class Odsluch:
    def __init__(self, rdzen):
        self.r = rdzen
        self.w_toku = False
        self.mikrofon_auto = False
        self.talkback_auto = set()
        self.program_lr = False
        self.cue_przed = None

    def przed(self, krok):
        """Break-before-make: brak drugiej kopii nawet między krokami."""
        if not aktywny(self.r.u) or self.w_toku:
            return True
        from .rdzen import Krok
        a, v = krok.adres, krok.wartosc
        kanaly = set()
        if a == s.MONITOR_ZRODLO and int(v) != s.ZRODLO_OFF:
            kanaly = set(range(1, 11))
        for z in self.r.u.zrodla.values():
            if ((a in [s.solo(k) for k in z.kanaly] and int(v) == 1)
                    or (a in [s.lr(k) for k in z.kanaly] and int(v) == 0)):
                kanaly.update(z.kanaly)
        kroki = [Krok(s.wysylka(k, SEND), 0.0) for k in sorted(kanaly)
                 if k <= 10 and self.r.stan.wartosc(s.wysylka(k, SEND)) != 0]
        return self.r._zamknij(kroki).ok

    def uzgodnij(self, tylko_zamknij=False):
        r = self.r
        if not aktywny(r.u) or self.w_toku or not (r.stan.polaczony and r.stan.zsynchronizowany):
            return True
        from .rdzen import Krok
        self.w_toku = True
        try:
            cue = r.widok.cue_zbior()
            jest_cue = cue is not NIEZNANY and bool(cue)
            if cue != self.cue_przed:
                self.program_lr = False
                if cue is not NIEZNANY and self.cue_przed is not None and self.cue_przed is not NIEZNANY:
                    # CUE mogło zakończyć inne sterowanie. Solo założone przez
                    # plan rozmowy również trzeba zdjąć, nie tylko auto-PFL.
                    self.talkback_auto.update(self.cue_przed - cue)
                    if self.cue_przed and not cue:
                        self.mikrofon_auto = True
                self.cue_przed = cue
            # Talkback zachowuje CUE sprzed trzymania, nie jest nowym CUE.
            monitor = s.ZRODLO_OFF if jest_cue and not self.program_lr else s.ZRODLO_LR
            if (not tylko_zamknij and cue is not NIEZNANY
                    and (not jest_cue or r.widok.monitor() != monitor)):
                # Najpierw zamknięcie i potwierdzenie drugiej drogi.
                if not r._zamknij([Krok(a, 0.0) for a in cel(r.widok)
                                   if r.stan.wartosc(a) != 0]).ok:
                    return False
                if r.widok.monitor() != monitor:
                    if r.zapora.profil_blokuje or r._rozbrojone() or not r._gotowy():
                        return True
                    if not r._zamknij([Krok(s.MONITOR_ZRODLO, monitor)]).ok:
                        return False
            # Własny PFL mikrofonu tylko w rozmowie, nigdy zamiast stereo anteny.
            if not jest_cue and not tylko_zamknij:
                if self.mikrofon_auto:
                    a = s.solo(r.u.zrodla['mikrofon'].kanaly[0])
                    if not r._zamknij([Krok(a, 0)]).ok:
                        return False
                    self.mikrofon_auto = False
                for zr in tuple(self.talkback_auto):
                    if not r._zamknij(r.kroki_pfl(zr, False)).ok:
                        return False
                    self.talkback_auto.discard(zr)
            # Program LR jest świadomą alternatywą, nigdy domieszką.
            if jest_cue and r.widok.monitor() == s.ZRODLO_OFF and not tylko_zamknij:
                cue = r.widok.cue_zbior()
                mik = not r.widok.kaszel
                # Automatycznie zdjęte tylko to solo, które włączył ten tryb.
                a = s.solo(r.u.zrodla['mikrofon'].kanaly[0])
                if mik and r.stan.wartosc(a) == 0:
                    if not r._zamknij([Krok(a, 1)]).ok:
                        return False
                    self.mikrofon_auto = True
                elif (r.widok.kaszel or (self.mikrofon_auto and not mik)) and r.stan.wartosc(a) == 1:
                    if not r._zamknij([Krok(a, 0)]).ok:
                        return False
                    self.mikrofon_auto = False
                for zr in r.widok.rozmowcy():
                    chce = zr in r._talkback or (cue is not NIEZNANY and zr in cue)
                    if chce and r.widok.pfl(zr) is False:
                        # Najpierw odbierz kopię AUX, dopiero otwórz PFL.
                        if not r._zamknij([Krok(s.wysylka(k, SEND), 0.0) for k in r.u.zrodla[zr].kanaly]).ok:
                            return False
                        if not r._zamknij(r.kroki_pfl(zr, True)).ok:
                            return False
                        self.talkback_auto.add(zr)
                    elif zr in self.talkback_auto and not chce:
                        if cue is not NIEZNANY and zr not in cue:
                            if not r._zamknij(r.kroki_pfl(zr, False)).ok:
                                return False
                        self.talkback_auto.discard(zr)
            docelowe = cel(r.widok)
            # Każda korekta tap przy zamkniętej wysyłce, zapora też tego pilnuje.
            zamknij = []
            for a, p in docelowe.items():
                t = a.rsplit('/', 1)[0] + '/tap'
                v = r.stan.wartosc(a)
                if v is NIEZNANY or (v > p + .005) or (v > 0 and r.stan.wartosc(t) != s.TAP_POST):
                    zamknij.append(Krok(a, 0.0))
            if not r._zamknij(zamknij).ok:
                return False
            if tylko_zamknij or r.zapora.profil_blokuje or r._rozbrojone():
                return True
            otworz = []
            for a, p in docelowe.items():
                if p <= 0:
                    continue
                t = a.rsplit('/', 1)[0] + '/tap'
                if r.stan.wartosc(t) != s.TAP_POST:
                    otworz.append(Krok(t, s.TAP_POST))
                if r.stan.wartosc(a) is NIEZNANY or abs(r.stan.wartosc(a) - p) > .005:
                    otworz.append(Krok(a, p, 0.0))
            return r._otworz(otworz).ok
        finally:
            self.w_toku = False
