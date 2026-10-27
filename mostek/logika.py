"""Logika radiowa bez sprzętu: widok logiczny stanu, model CUE, zapora.

Wszystko tu jest czystą funkcją stanu POTWIERDZONEGO (StanMiksera) i pliku
ustawień. Nic nie wysyła pakietów.

Źródło reguł: plan w wersji 22, rozdziały 4, 5, 6, 6a, 7 i 8 (model CUE
z wersji 20, mechanizmy D&R z wersji 21, przyciszanie słuchacza i głośniki
mono na Bus 6 z wersji 22). Model rozmów jak
w konsoletach D&R: rozmówca (telefon, Zoom) czeka, jest w rozmowie poza
anteną (CUE) albo jest na antenie. Stan wynika wyłącznie z odczytu MR18:

  * CUE rozmówcy R: wysyłka mikrofonu do szyny R otwarta i pobierana przed
    suwakiem (punkt pobrania PRE). Mikrofon jest w każdej rozmowie, więc to
    jest znacznik rozmowy niezależny od odsłuchu w słuchawkach.
  * na antenie: bez CUE, Main On włączone, suwak powyżej progu z ustawień.
  * czeka: bez CUE i nie na antenie.

Klucz przyciszania (Bus 5, plan v22, rozdz. 8, „Mechanizmy z konsolet D&R”,
pkt 5): mikrofon i Zoom trafiają do Bus 5 tylko wtedy, gdy są w tej samej
rozmowie co słuchacz (oboje na antenie albo oboje na CUE; mikrofon jest
w każdej rozmowie na CUE).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import sciezki
from .konwersje import poziom_db_na_float, poziom_float_na_db
from .stan import NIEZNANY, StanMiksera
from .ustawienia import Ustawienia

MIKROFON = "mikrofon"
TELEFON = "telefon"
ZOOM = "zoom"

CUE = "cue"
ANTENA = "antena"
CZEKA = "czeka"
CZEKA_POZA_SUMA = "czeka_poza_suma"

TOLERANCJA = 0.005


def wszystkie(wartosci) -> object:
    """True, gdy wszystkie True; False, gdy wszystkie False; inaczej NIEZNANY.

    Rozbieżność kanałów pary stereo daje NIEZNANY: nie wolno zgadywać.
    """
    wartosci = list(wartosci)
    if not wartosci or any(v is NIEZNANY for v in wartosci):
        return NIEZNANY
    if all(wartosci):
        return True
    if not any(wartosci):
        return False
    return NIEZNANY


def moze(v) -> bool:
    """Prawda albo nieznane: przy kontroli bezpieczeństwa liczy się jak prawda."""
    return v is not False


def pary_wysylek(kanaly, szyny) -> list[tuple[int, int]]:
    """Które kanały źródła idą do których szyn odbiorcy.

    Plan, rozdz. 5: lewe kanały muzyki do Bus 3, prawe do Bus 4, mikrofon
    i telefon na środek (do obu szyn), a do mono Bus 1 oba kanały pary
    (suma mono w DSP). Para stereo do pary stereo: kanał nieparzysty do
    szyny nieparzystej, parzysty do parzystej, bez wysyłek krzyżowych.
    Jak MR18 traktuje wysyłkę linkowanej pary kanałów do linkowanej pary
    szyn, trzeba zmierzyć (README, luki).
    """
    if len(kanaly) == 2 and len(szyny) == 2:
        return [(kanaly[0], szyny[0]), (kanaly[1], szyny[1])]
    return [(k, b) for k in kanaly for b in szyny]


def jest_wlaczona(poziom) -> object:
    """Wysyłka włączona = poziom powyżej minus nieskończoności."""
    if poziom is NIEZNANY:
        return NIEZNANY
    return float(poziom) > 0.0


class StanZNakladka:
    """Stan potwierdzony z jedną albo kilkoma wartościami „gdyby zapisać”.

    Zapora sprawdza na nim, czy zapis nie doprowadzi do stanu łamiącego
    niezmiennik. Niczego nie zmienia w prawdziwym stanie.
    """

    def __init__(self, stan: StanMiksera, zmiany: dict[str, object]) -> None:
        self._stan = stan
        self._zmiany = zmiany
        self.polaczony = stan.polaczony
        self.zsynchronizowany = stan.zsynchronizowany

    def wartosc(self, adres: str):
        if not self._stan.polaczony:
            return NIEZNANY
        if adres in self._zmiany:
            return self._zmiany[adres]
        return self._stan.wartosc(adres)


class Widok:
    """Logiczne odczytanie potwierdzonego stanu miksera."""

    def __init__(self, u: Ustawienia, stan) -> None:
        self.u = u
        self.stan = stan
        # CUE jest znacznikiem wysyłki mikrofonu. Podczas chwilowego przejęcia
        # zachowujemy CUE odczytane przed nim, nie myląc talkbacku z SELECT.
        self.cue_chwilowe: frozenset | None = None
        self.talkback: frozenset = frozenset()
        self.kaszel = False

    def z_zapisem(self, adres: str, wartosc) -> "Widok":
        w = Widok(self.u, StanZNakladka(self.stan, {adres: wartosc}))
        w.cue_chwilowe, w.talkback, w.kaszel = self.cue_chwilowe, self.talkback, self.kaszel
        return w

    def _w(self, adres: str):
        return self.stan.wartosc(adres)

    def _rowne(self, adres: str, oczekiwana) -> object:
        v = self._w(adres)
        return NIEZNANY if v is NIEZNANY else v == oczekiwana

    # --- adresy -----------------------------------------------------------
    def adresy_sumy(self, zr: str) -> list[str]:
        return [sciezki.lr(k) for k in self.u.zrodla[zr].kanaly]

    def adresy_wysylki(self, zr: str, odb: str) -> list[str]:
        return [sciezki.wysylka(k, b) for k, b in
                pary_wysylek(self.u.zrodla[zr].kanaly, self.u.odbiorcy[odb].szyny)]

    def adresy_tap(self, zr: str, odb: str) -> list[str]:
        return [sciezki.tap(k, b) for k, b in
                pary_wysylek(self.u.zrodla[zr].kanaly, self.u.odbiorcy[odb].szyny)]

    def adresy_pfl(self, zr: str) -> list[str]:
        return [sciezki.solo(k) for k in self.u.zrodla[zr].kanaly]

    def adresy_glosnikow(self) -> list[str]:
        return [sciezki.mute_szyny(b) for b in self.u.szyny_glosnikow]

    def adres_podsluchu(self) -> str:
        return sciezki.wysylka(self.u.zrodla[TELEFON].kanaly[0], self.u.szyna_podsluchu)

    def adresy_klucza(self, zr: str) -> list[str]:
        """Wysyłki źródła do szyny klucza przyciszania (Bus 5)."""
        return [sciezki.wysylka(k, self.u.szyna_klucza) for k in self.u.zrodla[zr].kanaly]

    # --- rozmówcy ---------------------------------------------------------
    def rozmowcy(self) -> list[str]:
        """Źródła, które mają własny powrót (telefon, Zoom), w kolejności ustawień."""
        return [o.wlasne_zrodlo for o in self.u.odbiorcy.values()]

    def odbiorca(self, zr: str) -> str | None:
        for o in self.u.odbiorcy.values():
            if o.wlasne_zrodlo == zr:
                return o.klucz
        return None

    def muzyka(self) -> list[str]:
        return [z.klucz for z in self.u.zrodla.values() if not z.glos]

    # --- stany logiczne ---------------------------------------------------
    def suma(self, zr: str):
        return wszystkie(self._rowne(a, 1) for a in self.adresy_sumy(zr))

    def wysylka(self, zr: str, odb: str):
        if self.u.odbiorcy[odb].wlasne_zrodlo == zr:
            return False
        return wszystkie(jest_wlaczona(self._w(a)) for a in self.adresy_wysylki(zr, odb))

    def poziom_max(self, zr: str, odb: str):
        """Najwyższy poziom wysyłki pary (do kontroli przyciszenia)."""
        w = [self._w(a) for a in self.adresy_wysylki(zr, odb)]
        if any(v is NIEZNANY for v in w):
            return NIEZNANY
        return max(float(v) for v in w)

    def tap(self, zr: str, odb: str):
        w = [self._w(a) for a in self.adresy_tap(zr, odb)]
        if not w or any(v is NIEZNANY for v in w) or len({int(v) for v in w}) != 1:
            return NIEZNANY
        return int(w[0])

    def pfl(self, zr: str):
        return wszystkie(self._rowne(a, 1) for a in self.adresy_pfl(zr))

    def wyciszony_wszedzie(self, zr: str):
        return wszystkie(self._rowne(sciezki.mute_kanalu(k), 0) for k in self.u.zrodla[zr].kanaly)

    def glosniki_wyciszone(self):
        return wszystkie(self._rowne(a, 0) for a in self.adresy_glosnikow())

    def podsluch(self):
        return jest_wlaczona(self._w(self.adres_podsluchu()))

    def monitor(self):
        return self._w(sciezki.MONITOR_ZRODLO)

    def dim(self):
        return self._rowne(sciezki.MONITOR_DIMPFL, 1)

    def fader_db(self, zr: str):
        wart = [self._w(sciezki.fader(k)) for k in self.u.zrodla[zr].kanaly]
        if any(v is NIEZNANY for v in wart):
            return NIEZNANY
        if max(wart) - min(wart) > TOLERANCJA:
            return NIEZNANY   # para rozbieżna
        return poziom_float_na_db(wart[0])

    def suwak_w_gorze(self, zr: str):
        """Suwak powyżej progu „na antenie” z pliku ustawień (plan, rozdz. 7)."""
        db = self.fader_db(zr)
        if db is NIEZNANY:
            return NIEZNANY
        return db > self.u.prog_suwaka_db

    def suwak_na_dole(self, zr: str):
        db = self.fader_db(zr)
        if db is NIEZNANY:
            return NIEZNANY
        return db == float("-inf")

    def para_rozbiezna(self, zr: str) -> bool:
        k = self.u.zrodla[zr].kanaly
        if len(k) < 2:
            return False
        for adresy in ([sciezki.fader(x) for x in k], [sciezki.lr(x) for x in k]):
            w = [self._w(a) for a in adresy]
            if all(v is not NIEZNANY for v in w) and max(w) - min(w) > TOLERANCJA:
                return True
        return False

    def cue(self, rozmowca: str):
        """CUE rozmówcy: mikrofon idzie do jego szyny przed suwakiem.

        Liczy się każda szyna pary osobno, więc w połowie przejścia (jedna
        szyna stereo otwarta, druga jeszcze nie) wynik jest pewny, a nie
        NIEZNANY: otwarta wysyłka za suwakiem to program, przed suwakiem
        to rozmowa, inny albo nieznany punkt pobrania to NIEZNANY.
        """
        if self.cue_chwilowe is not None:
            if not (self.stan.polaczony and self.stan.zsynchronizowany):
                return NIEZNANY
            return rozmowca in self.cue_chwilowe
        odb = self.odbiorca(rozmowca)
        if odb is None:
            return False
        nieznane = False
        for a, at in zip(self.adresy_wysylki(MIKROFON, odb), self.adresy_tap(MIKROFON, odb)):
            p = jest_wlaczona(self._w(a))
            if p is NIEZNANY:
                nieznane = True
                continue
            if not p:
                continue
            t = self._w(at)
            if t is NIEZNANY or int(t) not in (sciezki.TAP_PRE, sciezki.TAP_POST):
                nieznane = True
            elif int(t) == sciezki.TAP_PRE:
                return True
        return NIEZNANY if nieznane else False

    def cue_zbior(self):
        """Zbiór rozmówców z CUE albo NIEZNANY, gdy któregoś nie da się ustalić."""
        wynik = set()
        for r in self.rozmowcy():
            c = self.cue(r)
            if c is NIEZNANY:
                return NIEZNANY
            if c:
                wynik.add(r)
        return frozenset(wynik)

    def stan_rozmowcy(self, r: str):
        c = self.cue(r)
        if c is NIEZNANY:
            return NIEZNANY
        if c:
            return CUE
        s, g = self.suma(r), self.suwak_w_gorze(r)
        if s is NIEZNANY or g is NIEZNANY:
            return NIEZNANY
        if s is False:
            return CZEKA_POZA_SUMA
        return ANTENA if g else CZEKA

    def na_antenie(self, zr: str):
        """Czy źródło jest w programie: mikrofon i muzyka przez Main On,
        rozmówca przez Main On i suwak powyżej progu, bez CUE."""
        if zr in self.rozmowcy():
            s = self.stan_rozmowcy(zr)
            return NIEZNANY if s is NIEZNANY else s == ANTENA
        return self.suma(zr)

    def klucz(self, zr: str):
        """Czy źródło jest w kluczu przyciszania (wysyłka do Bus 5 otwarta)."""
        return wszystkie(jest_wlaczona(self._w(a)) for a in self.adresy_klucza(zr))

    def ta_sama_rozmowa(self, zr: str):
        """Czy źródło jest w tej samej rozmowie co słuchacz (decyzja 5, plan v22).

        Słuchacz na CUE: mikrofon zawsze (jest w każdej rozmowie), inne źródło,
        gdy też ma CUE. Słuchacz bez CUE: oboje na antenie.
        """
        sl = self.u.sluchacz
        c = self.cue(sl)
        if c is NIEZNANY:
            return NIEZNANY
        if c:
            if zr == MIKROFON:
                return True
            return self.cue(zr) if zr in self.rozmowcy() else False
        a_sl, a_zr = self.na_antenie(sl), self.na_antenie(zr)
        if a_sl is NIEZNANY or a_zr is NIEZNANY:
            return NIEZNANY
        return bool(a_sl and a_zr)

    def mikrofon_ma_otwarty_tor(self):
        """Antena albo wysyłka do dowolnego rozmówcy (plan, rozdz. 6a)."""
        stany = [self.suma(MIKROFON)] + [self.wysylka(MIKROFON, o) for o in self.u.odbiorcy]
        if any(s is True for s in stany):
            return True
        if any(s is NIEZNANY for s in stany):
            return NIEZNANY
        return False

    def migawka(self) -> dict:
        """Stany logiczne do wykrywania i ogłaszania zmian z innego urządzenia."""
        m: dict = {}
        for zr in self.u.zrodla:
            if zr not in self.rozmowcy():
                m[("suma", zr)] = self.suma(zr)
            m[("wyciszony", zr)] = self.wyciszony_wszedzie(zr)
            for odb in self.u.odbiorcy:
                if self.u.odbiorcy[odb].wlasne_zrodlo != zr:
                    m[("wysylka", zr, odb)] = self.wysylka(zr, odb)
        for r in self.rozmowcy():
            m[("rozmowca", r)] = self.stan_rozmowcy(r)
        m[("glosniki",)] = self.glosniki_wyciszone()
        return m


def opis_fadera(u: Ustawienia, db, maks_db: float = 0.0) -> str:
    """„suwak w górze” tylko przy górze suwaka tego źródła (maks_db), inaczej
    liczba decybeli, także „zero decybeli” przy mikrofonie z górą +10 dB."""
    if db is NIEZNANY:
        return ""
    if db == float("-inf"):
        return u.tekst("suwak_na_dole")
    if abs(db - maks_db) < 0.25:
        return u.tekst("suwak_w_gorze")
    from .konwersje import opis_db
    return u.tekst("suwak_db", wartosc=opis_db(db))


# --- Niezmienniki rozmowy na CUE (plan v20, rozdz. 6 i 7) -------------------
# Każda reguła to osobna funkcja zwracająca listę naruszeń w danym stanie.
# Zapora odrzuca zapis otwierający, który dodałby NOWE naruszenie.
# Nazwy reguł są stałe: używa ich test mutacyjny (narzedzia/mutacje_zapory.py).

def regula_cue_mikrofon_na_antene(w: Widok) -> list:
    """Przy dowolnym CUE mikrofon nie jest na antenie (decyzje 5 i 6)."""
    if any(w.cue(r) is not False for r in w.rozmowcy()) and moze(w.suma(MIKROFON)):
        return [("cue_mikrofon_na_antene", MIKROFON)]
    return []


def regula_cue_rozmowca_na_antene(w: Widok) -> list:
    """Rozmówca z CUE nie jest na sumie (decyzja 4)."""
    return [("cue_rozmowca_na_antene", r) for r in w.rozmowcy()
            if w.cue(r) is not False and moze(w.suma(r))]


def _bez_cue(w: Widok) -> list[str]:
    return [r for r in w.rozmowcy() if w.cue(r) is False]


def _z_cue(w: Widok) -> list[str]:
    return [r for r in w.rozmowcy() if w.cue(r) is not False]


def regula_cue_mikrofon_do_obcych(w: Widok) -> list:
    """Przy CUE rozmówca bez CUE nie dostaje mikrofonu (decyzja 3)."""
    if not _z_cue(w) or w.talkback:
        # Talkback ma własną, ostrzejszą listę adresatów i nie zmienia CUE.
        return []
    return [("cue_mikrofon_do_obcych", r) for r in _bez_cue(w)
            if moze(w.wysylka(MIKROFON, w.odbiorca(r)))]


def regula_cue_rozmowca_do_obcych(w: Widok) -> list:
    """Rozmówca bez CUE nie słyszy rozmówcy z CUE (np. Zoom nie słyszy słuchacza)."""
    return [("cue_rozmowca_do_obcych", r, inny) for r in _z_cue(w) for inny in _bez_cue(w)
            if moze(w.wysylka(r, w.odbiorca(inny)))]


def regula_cue_obcy_do_rozmowy(w: Widok) -> list:
    """Rozmówca z CUE nie słyszy rozmówcy bez CUE (np. słuchacz nie słyszy Zooma)."""
    return [("cue_obcy_do_rozmowy", inny, r) for r in _z_cue(w) for inny in _bez_cue(w)
            if moze(w.wysylka(inny, w.odbiorca(r)))]


def regula_cue_glos_przed_suwakiem(w: Widok) -> list:
    """Głos rozmówcy idzie przed suwakiem tylko między uczestnikami CUE."""
    wynik = []
    for x in w.rozmowcy():
        for r in w.rozmowcy():
            if r == x:
                continue
            odb = w.odbiorca(r)
            if not moze(w.wysylka(x, odb)) or w.tap(x, odb) == sciezki.TAP_POST:
                continue
            if not (w.cue(x) is True and w.cue(r) is True):
                wynik.append(("cue_glos_przed_suwakiem", x, r))
    return wynik


def regula_cue_muzyka_ciszej(w: Widok) -> list:
    """Muzyka do rozmówcy z CUE najwyżej poziom bazowy minus przyciszenie."""
    wynik = []
    for r in _z_cue(w):
        odb = w.odbiorca(r)
        for m in w.muzyka():
            limit = poziom_db_na_float(w.u.poziom_bazowy(m, odb) + w.u.przyciszenie_muzyki_db)
            p = w.poziom_max(m, odb)
            if p is NIEZNANY or p > limit + TOLERANCJA:
                wynik.append(("cue_muzyka_ciszej", m, r))
    return wynik


def regula_klucz_ta_sama_rozmowa(w: Widok) -> list:
    """Do klucza (Bus 5) trafia tylko źródło z tej samej rozmowy co słuchacz (plan v22)."""
    return [("klucz_ta_sama_rozmowa", zr) for zr in w.u.zrodla_klucza
            if moze(w.klucz(zr)) and w.ta_sama_rozmowa(zr) is not True]


# Reguły stanu: sprawdzane na stanie „po zapisie” każdego zapisu otwierającego.
REGULY_CUE = {
    "cue_mikrofon_na_antene": regula_cue_mikrofon_na_antene,
    "cue_rozmowca_na_antene": regula_cue_rozmowca_na_antene,
    "cue_mikrofon_do_obcych": regula_cue_mikrofon_do_obcych,
    "cue_rozmowca_do_obcych": regula_cue_rozmowca_do_obcych,
    "cue_obcy_do_rozmowy": regula_cue_obcy_do_rozmowy,
    "cue_glos_przed_suwakiem": regula_cue_glos_przed_suwakiem,
    "cue_muzyka_ciszej": regula_cue_muzyka_ciszej,
    "klucz_ta_sama_rozmowa": regula_klucz_ta_sama_rozmowa,
}

OPISY_REGUL = {
    "cue_mikrofon_na_antene": "rozmowa poza anteną, mikrofon nie idzie na antenę",
    "cue_rozmowca_na_antene": "rozmówca na CUE nie idzie na antenę",
    "cue_mikrofon_do_obcych": "rozmowa poza anteną, rozmówca bez CUE nie słyszy mikrofonu",
    "cue_rozmowca_do_obcych": "rozmówca bez CUE nie słyszy rozmówcy z CUE",
    "cue_obcy_do_rozmowy": "rozmówca z CUE nie słyszy rozmówcy bez CUE",
    "cue_glos_przed_suwakiem": "głos przed suwakiem tylko między uczestnikami CUE",
    "cue_muzyka_ciszej": "muzyka do rozmowy na CUE tylko przyciszona",
    "tap_wartosci": "punkt pobrania tylko przed albo za suwakiem, tylko do szyn rozmówców",
    "tap_przy_otwartej": "punkt pobrania zmieniany tylko przy zamkniętej wysyłce",
    # Plan v22 (karta zlecenia, nowe i zmienione niezmienniki).
    "klucz_tylko_glosy": "do klucza przyciszania trafia wyłącznie mikrofon i Zoom",
    "klucz_bez_wyjscia": "klucz przyciszania (Bus 5) bez wyjścia: nie na Main LR, nie na USB, bez linku z głośnikami",
    "klucz_ta_sama_rozmowa": "do klucza przyciszania tylko źródło z tej samej rozmowy co słuchacz",
    "klucz_przy_niezgodnym_profilu": "profil miksera niezgodny, klucz przyciszania zamknięty",
    "glosniki_przy_mikrofonie": "głośniki niewyciszone, mikrofon zamknięty",
    "glosniki_bez_mikrofonu": "mikrofon jeszcze otwarty",
    # Poprawki luk z analizy v22 (L03, L06).
    "glosniki_przy_niezgodnym_profilu": "profil miksera niezgodny, głośniki zostają wyciszone",
    "sciezka_w_rejestrze": "ścieżka spoza rejestru ścieżek mostka, zapis zablokowany",
    "sciezka_tylko_do_odczytu": "sceny i akcje systemowe tylko do odczytu, zapis zablokowany",
    "chwilowy_bez_anteny": "kaszel i talkback nie otwierają anteny mikrofonu",
    "chwilowy_bez_klucza": "kaszel i talkback nie otwierają klucza mikrofonu",
    "talkback_tylko_adresaci": "talkback mikrofonu tylko do wybranych adresatów",
    "talkback_przed_suwakiem": "talkback mikrofonu wyłącznie przed suwakiem",
    "talkback_izolacja": "talkback dopiero po zamknięciu anteny, klucza i pozostałych adresatów",
    "kaszel_bez_wysylek": "kaszel zamyka mikrofon do wszystkich rozmówców",
}

# Reguły z wyłącznikiem (test mutacyjny). „glosniki_przy_mikrofonie” to dawny
# stały niezmiennik z rozdz. 6a, od planu v22 nazwany, bo pilnuje też powrotu
# po kaszlu.
NOWE_REGULY = tuple(k for k in OPISY_REGUL if k != "kaszel_bez_cue")

# Niezmienniki realizowane przez inne reguły (karta zlecenia v22): test
# mutacyjny wyłącza każdą z reguł-strażników i sprawdza, że pada test
# test_kaszel_bez_cue_<reguła>.
REGULY_ZLOZONE = {
    "kaszel_bez_cue": ("cue_mikrofon_na_antene", "glosniki_przy_mikrofonie"),
}
OPISY_REGUL["kaszel_bez_cue"] = ("powrót mikrofonu po kaszlu tylko bez CUE i przy wyciszonych głośnikach "
                                 "(pilnują cue_mikrofon_na_antene i glosniki_przy_mikrofonie)")


def naruszenia_cue(w: Widok, wylaczone: frozenset | set = frozenset()) -> set:
    wynik = set()
    for nazwa, regula in REGULY_CUE.items():
        if nazwa in wylaczone:
            continue
        wynik.update(regula(w))
    return wynik


# --- Zapora niezmienników -------------------------------------------------

class NaruszenieZapory(RuntimeError):
    """Zapis złamałby stały niezmiennik planu. Zapis nie jest wysyłany."""

    def __init__(self, opis: str, regula: str = "") -> None:
        super().__init__(opis)
        self.regula = regula


def czy_otwiera(adres: str, wartosc) -> bool:
    """Czy zapis może otworzyć drogę dźwięku: Main On, wysyłka albo odciszenie."""
    czesci = adres.strip("/").split("/")
    if adres.endswith("/mix/lr"):
        return int(wartosc) == 1
    if len(czesci) == 5 and czesci[0] in ("ch", "rtn") and czesci[4] == "level":
        return float(wartosc) > 0.0
    if len(czesci) == 4 and czesci[0] == "bus" and czesci[3] == "on":
        return int(wartosc) == 1
    if len(czesci) == 4 and czesci[0] == "ch" and czesci[3] == "on":
        return int(wartosc) == 1
    return False


def zwieksza_ekspozycje(adres: str, wartosc, widok: Widok) -> bool:
    """Otwarcie względem potwierdzonego stanu: włączenie albo podniesienie poziomu."""
    if not czy_otwiera(adres, wartosc):
        return False
    obecna = widok.stan.wartosc(adres)
    if obecna is NIEZNANY:
        return True
    if adres.endswith("/level"):
        return float(wartosc) > float(obecna) + TOLERANCJA
    return int(obecna) != int(wartosc)


@dataclass
class Zapora:
    u: Ustawienia
    profil_blokuje: bool = False
    wylaczone: set = field(default_factory=set)      # tylko testy: wyłączone reguły CUE i tap

    def _kanal_zrodla(self, kanal: int) -> str | None:
        for z in self.u.zrodla.values():
            if kanal in z.kanaly:
                return z.klucz
        return None

    def _odrzuc(self, regula: str, szczegol: str = "") -> None:
        opis = self.u.komunikaty.get("zapora_" + regula, OPISY_REGUL[regula])
        raise NaruszenieZapory(opis + (f" ({szczegol})" if szczegol else ""), regula)

    def sprawdz(self, adres: str, wartosc, widok: Widok) -> None:
        # Indeks sceny jest w rejestrze odczytu, lecz nigdy nie wolno go zapisać.
        if "sciezka_tylko_do_odczytu" not in self.wylaczone and regula_sciezka_tylko_do_odczytu(adres):
            self._odrzuc("sciezka_tylko_do_odczytu", adres)
        # L06: tylko pełne ścieżki z rejestru (sciezki.REJESTR z zakresem pól).
        if "sciezka_w_rejestrze" not in self.wylaczone and regula_sciezka_w_rejestrze(adres):
            self._odrzuc("sciezka_w_rejestrze", adres)
        czesci = adres.strip("/").split("/")
        # Stan NIEZNANY blokuje każde otwarcie (plan, rozdz. 6a i 8).
        if czy_otwiera(adres, wartosc) and not (widok.stan.polaczony and widok.stan.zsynchronizowany):
            raise NaruszenieZapory("stan nieznany, otwieranie zablokowane")
        if "klucz_bez_wyjscia" not in self.wylaczone and regula_klucz_bez_wyjscia(self.u, adres, wartosc):
            self._odrzuc("klucz_bez_wyjscia", f"{adres} = {wartosc}")
        if czy_ustawienie_przyciszacza(self.u, adres):
            # Plan v22: przyciszacz kanału słuchacza i master Bus 5 są w scenie
            # BAZA; mostek ich nie zmienia i nie zapisuje, tylko odczytuje.
            raise NaruszenieZapory("ustawienia przyciszania są w scenie BAZA, mostek ich nie zapisuje")
        # Sprawdzamy także ponowny zapis tej samej dodatniej wartości: samo
        # porównanie nowych naruszeń stanu nie wystarcza do ochrony trzymania.
        for nazwa, regula in REGULY_CHWILOWE.items():
            if nazwa not in self.wylaczone and regula(widok, adres, wartosc):
                self._odrzuc(nazwa)
        otwiera_mikrofon = False
        if len(czesci) == 5 and czesci[0] == "ch" and czesci[2] == "mix" and czesci[4] == "level":
            kanal, szyna = int(czesci[1]), int(czesci[3])
            zr = self._kanal_zrodla(kanal)
            if float(wartosc) > 0.0:
                if szyna in sciezki.SZYNY_FX:
                    raise NaruszenieZapory("wysyłki do FX są zamknięte w wariancie bazowym")
                for odb in self.u.odbiorcy.values():
                    if zr == odb.wlasne_zrodlo and szyna in odb.szyny:
                        raise NaruszenieZapory(f"{odb.nazwa} nie może wracać do siebie (szyna {szyna})")
                if szyna == self.u.szyna_podsluchu and zr != TELEFON:
                    raise NaruszenieZapory("do szyny podsłuchu trafia wyłącznie telefon")
                if szyna in self.u.szyny_glosnikow and zr == MIKROFON:
                    raise NaruszenieZapory("mikrofon nigdy nie trafia do głośników")
                if "klucz_tylko_glosy" not in self.wylaczone and regula_klucz_tylko_glosy(self.u, kanal, szyna,
                                                                                          wartosc):
                    self._odrzuc("klucz_tylko_glosy", f"kanał {kanal}")
                if "klucz_przy_niezgodnym_profilu" not in self.wylaczone and \
                        regula_klucz_przy_niezgodnym_profilu(self.u, szyna, self.profil_blokuje):
                    self._odrzuc("klucz_przy_niezgodnym_profilu", f"kanał {kanal}")
                if zr == MIKROFON:
                    otwiera_mikrofon = True
        elif len(czesci) == 5 and czesci[0] == "ch" and czesci[2] == "mix" and czesci[4] == "tap":
            self._sprawdz_tap(int(czesci[1]), int(czesci[3]), wartosc, widok)
        elif len(czesci) == 4 and czesci[0] == "ch" and czesci[2] == "mix" and czesci[3] == "lr":
            zr = self._kanal_zrodla(int(czesci[1]))
            if int(wartosc) == 1:
                if zr == MIKROFON:
                    otwiera_mikrofon = True
                if self.profil_blokuje:
                    raise NaruszenieZapory("profil miksera niezgodny, otwieranie zablokowane")
        elif len(czesci) == 4 and czesci[0] == "bus" and czesci[2] == "mix" and czesci[3] == "lr":
            if int(wartosc) == 1:
                raise NaruszenieZapory("szyny rozmówców i głośników nie trafiają na Main LR")
        elif len(czesci) == 5 and czesci[0] == "rtn" and czesci[4] == "level":
            if float(wartosc) > 0.0:
                raise NaruszenieZapory("wysyłki powrotów mostek tylko zamyka")
        elif len(czesci) == 4 and czesci[0] == "bus" and czesci[2] == "mix" and czesci[3] == "on":
            szyna = int(czesci[1])
            if szyna in self.u.szyny_glosnikow and int(wartosc) == 1:
                if "glosniki_bez_mikrofonu" not in self.wylaczone and regula_glosniki_bez_mikrofonu(widok):
                    self._odrzuc("glosniki_bez_mikrofonu")
                if "glosniki_przy_niezgodnym_profilu" not in self.wylaczone and \
                        regula_glosniki_przy_niezgodnym_profilu(self.u, szyna, wartosc, self.profil_blokuje):
                    self._odrzuc("glosniki_przy_niezgodnym_profilu", f"szyna {szyna}")
        if otwiera_mikrofon:
            if self.profil_blokuje:
                raise NaruszenieZapory("profil miksera niezgodny, otwieranie zablokowane")
            if "glosniki_przy_mikrofonie" not in self.wylaczone and regula_glosniki_przy_mikrofonie(widok):
                self._odrzuc("glosniki_przy_mikrofonie")
        # Niezmienniki rozmowy na CUE: zapis otwierający nie może dodać naruszenia.
        if zwieksza_ekspozycje(adres, wartosc, widok):
            przed = naruszenia_cue(widok, self.wylaczone)
            po = naruszenia_cue(widok.z_zapisem(adres, wartosc), self.wylaczone)
            nowe = sorted(po - przed)
            if nowe:
                self._odrzuc(nowe[0][0], " ".join(str(x) for x in nowe[0][1:]))

    def _sprawdz_tap(self, kanal: int, szyna: int, wartosc, widok: Widok) -> None:
        if "tap_wartosci" not in self.wylaczone and regula_tap_wartosci(self.u, kanal, szyna, wartosc,
                                                                        self._kanal_zrodla(kanal)):
            self._odrzuc("tap_wartosci", f"kanał {kanal}, szyna {szyna}, wartość {wartosc}")
        if "tap_przy_otwartej" not in self.wylaczone and regula_tap_przy_otwartej(kanal, szyna, wartosc, widok):
            self._odrzuc("tap_przy_otwartej", f"kanał {kanal}, szyna {szyna}")


def regula_chwilowy_bez_anteny(w: Widok, adres: str, wartosc) -> bool:
    """Kaszel albo talkback nigdy nie otwiera Main LR mikrofonu."""
    return bool(w.kaszel or w.talkback) and adres in w.adresy_sumy(MIKROFON) and int(wartosc) != 0


def regula_chwilowy_bez_klucza(w: Widok, adres: str, wartosc) -> bool:
    """Mikrofon w kaszlu i talkbacku nie przycisza słuchacza."""
    return bool(w.kaszel or w.talkback) and adres in w.adresy_klucza(MIKROFON) and float(wartosc) > 0


def regula_talkback_tylko_adresaci(w: Widok, adres: str, wartosc) -> bool:
    """Dodatnia wysyłka mikrofonu tylko do trzymanych adresatów."""
    return bool(w.talkback) and any(
        r not in w.talkback and adres in w.adresy_wysylki(MIKROFON, w.odbiorca(r))
        and float(wartosc) > 0 for r in w.rozmowcy())


def regula_talkback_przed_suwakiem(w: Widok, adres: str, wartosc) -> bool:
    """Otwarcie talkbacku wymaga potwierdzonego punktu PRE."""
    return bool(w.talkback) and any(
        adres in w.adresy_wysylki(MIKROFON, w.odbiorca(r)) and float(wartosc) > 0
        and w.tap(MIKROFON, w.odbiorca(r)) != sciezki.TAP_PRE for r in w.talkback)


def regula_talkback_izolacja(w: Widok, adres: str, wartosc) -> bool:
    """Dodatnia wysyłka talkbacku dopiero po potwierdzeniu izolacji mikrofonu."""
    if not w.talkback or not any(adres in w.adresy_wysylki(MIKROFON, o) for o in w.u.odbiorcy):
        return False
    if float(wartosc) <= 0:
        return False
    zamkniete = w.adresy_sumy(MIKROFON) + w.adresy_klucza(MIKROFON)
    for r in w.rozmowcy():
        if r not in w.talkback:
            zamkniete += w.adresy_wysylki(MIKROFON, w.odbiorca(r))
    return any(w.stan.wartosc(a) != 0 for a in zamkniete)


def regula_kaszel_bez_wysylek(w: Widok, adres: str, wartosc) -> bool:
    """Kaszel ma pierwszeństwo także nad trzymanym talkbackiem."""
    return w.kaszel and any(adres in w.adresy_wysylki(MIKROFON, o) and float(wartosc) > 0
                            for o in w.u.odbiorcy)


REGULY_CHWILOWE = {
    "chwilowy_bez_anteny": regula_chwilowy_bez_anteny,
    "chwilowy_bez_klucza": regula_chwilowy_bez_klucza,
    "talkback_tylko_adresaci": regula_talkback_tylko_adresaci,
    "talkback_przed_suwakiem": regula_talkback_przed_suwakiem,
    "kaszel_bez_wysylek": regula_kaszel_bez_wysylek,
    "talkback_izolacja": regula_talkback_izolacja,
}


def regula_glosniki_przy_mikrofonie(widok: Widok) -> bool:
    """Prawda = naruszenie. Tor mikrofonu otwiera się tylko przy potwierdzonym
    wyciszeniu głośników (rozdz. 6a); dotyczy też powrotu po kaszlu."""
    return widok.glosniki_wyciszone() is not True


def regula_glosniki_bez_mikrofonu(widok: Widok) -> bool:
    """Odciszenie tylko po potwierdzonym zamknięciu głosu i końcu trzymania.
    Chroni ręczne ON, Mute-Act i przywrócenie po talkbacku tą samą bramką."""
    return (widok.mikrofon_ma_otwarty_tor() is not False or bool(widok.talkback) or widok.kaszel
            or widok.cue_zbior() != frozenset())


def regula_sciezka_tylko_do_odczytu(adres: str) -> bool:
    """Prawda = naruszenie. Żadnych zapisów scen ani akcji systemowych.

    Zakaz obejmuje całe rodziny, także przyszłe akcje i wartość zero.
    Odczyt i nasłuch indeksu sceny nie przechodzą przez zaporę zapisu.
    """
    return any(adres == p or adres.startswith(p + "/") for p in ("/-snap", "/snap", "/-action"))


def regula_sciezka_w_rejestrze(adres: str) -> bool:
    """Prawda = naruszenie. Zapis tylko na pełną ścieżkę z rejestru
    (sciezki.REJESTR z zakresem kanałów i szyn), nie na samo dopasowanie
    sufiksu, np. /obce/mix/lr albo /ch/17/mix/lr (L06, analiza v22)."""
    return not sciezki.w_rejestrze(adres)


def regula_glosniki_przy_niezgodnym_profilu(u: Ustawienia, szyna: int, wartosc, profil_blokuje: bool) -> bool:
    """Prawda = naruszenie. Przy blokującej niezgodności profilu głośniki nie
    są odciszane, ani ręcznie, ani przez Mute-Act (L03, analiza v22)."""
    return szyna in u.szyny_glosnikow and int(wartosc) == 1 and profil_blokuje


def regula_klucz_tylko_glosy(u: Ustawienia, kanal: int, szyna: int, wartosc) -> bool:
    """Prawda = naruszenie. Do klucza przyciszania (Bus 5) wyłącznie kanały
    mikrofonu i Zooma (9, 7, 8): nic innego, także telefon i muzyka."""
    if szyna != u.szyna_klucza or float(wartosc) <= 0.0:
        return False
    dozwolone = {k for zr in u.zrodla_klucza for k in u.zrodla[zr].kanaly}
    return kanal not in dozwolone


def regula_klucz_przy_niezgodnym_profilu(u: Ustawienia, szyna: int, profil_blokuje: bool) -> bool:
    """Prawda = naruszenie. Przy blokującej niezgodności profilu (np. szyna na
    Main LR ustawiona z innego urządzenia) żadne źródło nie wchodzi do klucza
    przyciszania: Bus 5 mógłby wyprowadzić rozmowę na antenę."""
    return szyna == u.szyna_klucza and profil_blokuje


def regula_klucz_bez_wyjscia(u: Ustawienia, adres: str, wartosc) -> bool:
    """Prawda = naruszenie. Bus 5 nigdy na Main LR, nigdy źródłem wyjścia USB
    i nigdy połączony linkiem z głośnikami (Bus 6)."""
    b = u.szyna_klucza
    if adres == sciezki.szyna_lr(b):
        return int(wartosc) == 1
    if adres.startswith("/routing/usb/") and adres.endswith("/src"):
        return int(wartosc) == sciezki.USB_ZRODLO_SZYNA[b]
    para = b if b % 2 else b - 1
    if adres == sciezki.buslink(para):
        return int(wartosc) != 0
    return False


def czy_ustawienie_przyciszacza(u: Ustawienia, adres: str) -> bool:
    """Ścieżki przyciszacza i mastera Bus 5: tylko odczyt (scena BAZA)."""
    if adres.endswith(("/dyn/keysrc", "/dyn/on")) or "/insert/" in adres:
        return True
    b = u.szyna_klucza
    return adres in (sciezki.fader_szyny(b), sciezki.mute_szyny(b))


def regula_tap_wartosci(u: Ustawienia, kanal: int, szyna: int, wartosc, zr) -> bool:
    """Prawda = naruszenie. Tylko PRE albo POST (lista X AIR [43]), tylko szyny
    rozmówców, muzyka zawsze za suwakiem. Do klucza przyciszania (Bus 5) tylko
    mikrofon i Zoom, zawsze przed suwakiem (plan v22)."""
    if zr is not None and szyna == u.szyna_klucza:
        return not (zr in u.zrodla_klucza and int(wartosc) == sciezki.TAP_PRE)
    szyny_rozmowcow = {s for o in u.odbiorcy.values() for s in o.szyny}
    if zr is None or szyna not in szyny_rozmowcow:
        return True
    if int(wartosc) not in (sciezki.TAP_PRE, sciezki.TAP_POST):
        return True
    if not u.zrodla[zr].glos and int(wartosc) != sciezki.TAP_POST:
        return True
    return False


def regula_tap_przy_otwartej(kanal: int, szyna: int, wartosc, widok: Widok) -> bool:
    """Prawda = naruszenie. Zmiana punktu pobrania tylko przy wysyłce zamkniętej
    (wysyłka przed suwakiem przy suwaku na dole to otwarta droga)."""
    obecny = widok.stan.wartosc(sciezki.tap(kanal, szyna))
    if obecny is not NIEZNANY and int(obecny) == int(wartosc):
        return False
    poziom = widok.stan.wartosc(sciezki.wysylka(kanal, szyna))
    return poziom is NIEZNANY or float(poziom) > 0.0


# --- Kontrola profilu przy pełnym odczycie ----------------------------------

@dataclass
class Naruszenie:
    opis: str
    blokuje: bool


def sprawdz_profil(u: Ustawienia, widok: Widok) -> list[Naruszenie]:
    """Porównanie odczytu z profilem planu. Nic nie poprawia, tylko zgłasza."""
    w = widok.stan.wartosc
    wynik: list[Naruszenie] = []

    def poziom(a):
        v = w(a)
        return 0.0 if v is NIEZNANY else float(v)

    glosy = [k for z in u.zrodla.values() if z.glos for k in z.kanaly]
    for odb in u.odbiorcy.values():
        for k in u.zrodla[odb.wlasne_zrodlo].kanaly:
            for b in odb.szyny:
                if poziom(sciezki.wysylka(k, b)) > 0:
                    wynik.append(Naruszenie(f"{odb.nazwa} wraca do siebie", True))
    tel = u.zrodla[TELEFON].kanaly
    for z in u.zrodla.values():
        if z.klucz == TELEFON:
            continue
        for k in z.kanaly:
            if poziom(sciezki.wysylka(k, u.szyna_podsluchu)) > 0:
                wynik.append(Naruszenie(f"{z.nazwa} w szynie podsłuchu telefonu", True))
    for k in u.zrodla[MIKROFON].kanaly:
        for b in u.szyny_glosnikow:
            if poziom(sciezki.wysylka(k, b)) > 0:
                wynik.append(Naruszenie("mikrofon w głośnikach", True))
    for k in glosy:
        for b in sciezki.SZYNY_FX:
            if poziom(sciezki.wysylka(k, b)) > 0:
                wynik.append(Naruszenie(f"kanał {k} wysyła do efektów", True))
        if w(sciezki.dca(k)) not in (0, NIEZNANY) or w(sciezki.grupa_mute(k)) not in (0, NIEZNANY):
            wynik.append(Naruszenie(f"kanał {k} w DCA albo grupie wyciszeń", True))
    kb = u.szyna_klucza
    for b in range(1, 7):
        if w(sciezki.szyna_lr(b)) == 1:
            opis = (f"klucz przyciszania (Bus {b}) przypisany do Main LR" if b == kb
                    else f"szyna {b} przypisana do Main LR")
            wynik.append(Naruszenie(opis, True))
    suche = {sciezki.USB_ZRODLO_KANAL[k] for k in u.zrodla[MIKROFON].kanaly + tel}
    # Michał 21.10.2026: suchy mikrofon albo telefon wolno wyprowadzić na USB do
    # nagrań poza anteną, ale nie na wyjścia emisji (3/4) ani Zooma (1/2).
    dozwolone = {int(x) for x in u.profil.get("usb_suche_dozwolone", [])}
    for wy in range(1, int(u.profil.get("wyjscia_usb", 18)) + 1):
        zrodlo_usb = w(sciezki.usb_zrodlo(wy))
        if zrodlo_usb in suche:
            if wy in dozwolone:
                wynik.append(Naruszenie(f"wyjście USB {wy}: suchy głos do nagrań, poza emisją", False))
            else:
                wynik.append(Naruszenie(f"wyjście USB {wy} przenosi suchy mikrofon albo telefon", True))
        elif zrodlo_usb == sciezki.USB_ZRODLO_SZYNA[kb]:
            wynik.append(Naruszenie(f"wyjście USB {wy} przenosi klucz przyciszania (Bus {kb})", True))
    wynik += _profil_klucza(u, widok)
    for para in u.profil.get("linki_kanalow", []):
        if w(sciezki.chlink(para)) == 0:
            wynik.append(Naruszenie(f"kanały {para} i {para + 1} bez linku", False))
    for para in u.profil.get("linki_szyn", []):
        if w(sciezki.buslink(para)) == 0:
            wynik.append(Naruszenie(f"szyny {para} i {para + 1} bez linku", False))
    # Punkty pobrania (plan v20, rozdz. 4 i 6): muzyka za suwakiem, głosy przed
    # albo za suwakiem, podsłuch telefonu przed suwakiem.
    for z in u.zrodla.values():
        dozwolone = (sciezki.TAP_PRE, sciezki.TAP_POST) if z.glos else (sciezki.TAP_POST,)
        for odb in u.odbiorcy.values():
            if odb.wlasne_zrodlo == z.klucz:
                continue
            for k, b in pary_wysylek(z.kanaly, odb.szyny):
                t = w(sciezki.tap(k, b))
                if t is not NIEZNANY and int(t) not in dozwolone:
                    wynik.append(Naruszenie(f"{z.nazwa}: punkt wysyłki do szyny {b} inny niż w planie", False))
        if widok.para_rozbiezna(z.klucz):
            wynik.append(Naruszenie(f"{z.nazwa}: kanały pary rozbieżne", False))
        # Decyzja Michała z 17.10.2026 (plan v22, rozdz. 5): w scenie BAZA wszystkie
        # pary muzyki mają Main On stale włączone, o antenie decyduje suwak.
        if not z.glos and any(w(sciezki.lr(k)) == 0 for k in z.kanaly):
            wynik.append(Naruszenie(f"{z.nazwa} bez Main On, w scenie BAZA muzyka ma Main On stale włączone",
                                    False))
    t = w(sciezki.tap(tel[0], u.szyna_podsluchu))
    if t is not NIEZNANY and int(t) != sciezki.TAP_PRE:
        wynik.append(Naruszenie("podsłuch telefonu nie jest przed suwakiem", False))
    widziane, unikalne = set(), []
    for n in wynik:
        if n.opis not in widziane:
            widziane.add(n.opis)
            unikalne.append(n)
    return unikalne


FXSLOT = ("OFF", "Fx1A", "Fx1B", "Fx2A", "Fx2B", "Fx3A", "Fx3B", "Fx4A", "Fx4B")   # FORUM wiersz 153


def _profil_klucza(u: Ustawienia, widok: Widok) -> list[Naruszenie]:
    """Klucz przyciszania i przyciszacz słuchacza (plan v22, rozdz. 8, pkt 5).

    Blokujące: Bus 5 połączony linkiem z głośnikami (mikrofon trafiłby do
    głośników). Pozostałe tylko zgłaszane: ustawienia przyciszacza są w scenie
    BAZA i mostek ich nie zmienia.
    """
    w = widok.stan.wartosc
    kb = u.szyna_klucza
    wynik: list[Naruszenie] = []
    para = kb if kb % 2 else kb - 1
    if w(sciezki.buslink(para)) == 1:
        wynik.append(Naruszenie(f"klucz przyciszania połączony linkiem z szyną {para if para != kb else kb + 1}",
                                True))
    glosy_klucza = {k for zr in u.zrodla_klucza for k in u.zrodla[zr].kanaly}
    # L05: wszystkie wejścia Bus 5 (kanały 1-16 i powroty), nie tylko źródła
    # z ustawień. Każde wejście spoza mikrofonu i Zooma blokuje otwarcia,
    # a mostek je zamyka (Rdzen._ochronne_zamkniecia, decyzja P02).
    for a in obce_wejscia_klucza(u, widok):
        wynik.append(Naruszenie(f"{nazwa_wejscia(u, a)} w kluczu przyciszania", True))  # POPRAWKA L05
    for z in u.zrodla.values():
        for k in z.kanaly:
            if k in glosy_klucza:
                t = w(sciezki.tap(k, kb))
                if t is not NIEZNANY and int(t) != sciezki.TAP_PRE:
                    wynik.append(Naruszenie(f"{z.nazwa}: wysyłka do klucza przyciszania nie przed suwakiem",
                                            False))
    oczek = u.przyciszanie.get("profil", {})
    keysrc_ocz = sciezki.KEYSRC_SZYNA[kb]
    for k in u.zrodla[u.sluchacz].kanaly:
        v = w(sciezki.keysrc(k))
        if v is not NIEZNANY and int(v) != keysrc_ocz:
            wynik.append(Naruszenie(f"kanał {k}: klucz kompresora nie jest z Bus {kb}", False))
        v = w(sciezki.dyn_on(k))
        if v is not NIEZNANY and int(v) != 1:
            wynik.append(Naruszenie(f"kanał {k}: kompresor przyciszający wyłączony", False))
    for kanal, slot in oczek.get("inserty", {}).items():
        k = int(kanal)
        v = w(sciezki.insert_fxslot(k))
        if v is not NIEZNANY and int(v) != FXSLOT.index(slot):
            wynik.append(Naruszenie(f"kanał {k}: insert inny niż {slot}", False))
        v = w(sciezki.insert_on(k))
        if v is not NIEZNANY and int(v) != 1:
            wynik.append(Naruszenie(f"kanał {k}: insert wyłączony", False))
    if w(sciezki.mute_szyny(kb)) == 0:
        wynik.append(Naruszenie(f"Bus {kb} wyciszony, przyciszanie słuchacza nie zadziała", False))
    v = w(sciezki.fader_szyny(kb))
    if v is not NIEZNANY and abs(float(v) - poziom_db_na_float(0.0)) > TOLERANCJA:
        wynik.append(Naruszenie(f"master Bus {kb} nie na poziomie nominalnym", False))
    return wynik


def obce_wejscia_klucza(u: Ustawienia, widok: Widok) -> list[str]:
    """Otwarte wysyłki do Bus 5 spoza źródeł klucza: kanały 1-16 i powroty (L05)."""
    glosy = {k for zr in u.zrodla_klucza for k in u.zrodla[zr].kanaly}
    wynik = []
    for a in sciezki.wejscia_szyny(u.szyna_klucza):
        if sciezki.kanal_wysylki(a) in glosy:
            continue
        v = widok.stan.wartosc(a)
        if v is not NIEZNANY and float(v) > 0.0:
            wynik.append(a)
    return wynik


def nazwa_wejscia(u: Ustawienia, adres: str) -> str:
    """Nazwa wejścia szyny do komunikatu: źródło z ustawień, kanał albo powrót."""
    k = sciezki.kanal_wysylki(adres)
    if k is None:
        powrot = adres.strip("/").split("/")[1]
        return "powrót AUX" if powrot == "aux" else f"powrót efektu {powrot}"
    for z in u.zrodla.values():
        if k in z.kanaly:
            return z.nazwa
    return f"kanał {k}"


def wszystkie_adresy_odczytu(u: Ustawienia) -> list[str]:
    """Pełny odczyt profilu (plan, rozdz. 8, kontrakt pkt 2)."""
    a: list[str] = []
    kanaly = sorted({k for z in u.zrodla.values() for k in z.kanaly})
    for k in kanaly:
        a += [sciezki.lr(k), sciezki.mute_kanalu(k), sciezki.fader(k), sciezki.solo(k),
              sciezki.dca(k), sciezki.grupa_mute(k)]
        a += [sciezki.wysylka(k, b) for b in range(1, 11)]
        a += [sciezki.tap(k, b) for b in range(1, 7)]
    for z in u.zrodla.values():
        g = z.galka
        if g and g.get("typ") == "gain":
            a.append(sciezki.gain(int(g["wejscie"])))
        elif g and g.get("typ") == "rtntrim":
            a += [sciezki.rtntrim(k) for k in z.kanaly]
    a += [sciezki.chlink(p) for p in (1, 3, 5, 7, 9)]
    a += [sciezki.buslink(p) for p in (1, 3, 5)]
    for b in range(1, 7):
        a += [sciezki.mute_szyny(b), sciezki.szyna_lr(b)]
    a += [sciezki.usb_zrodlo(w) for w in range(1, int(u.profil.get("wyjscia_usb", 18)) + 1)]
    # Przyciszacz słuchacza i inserty (plan v22): tylko odczyt.
    for k in u.zrodla[u.sluchacz].kanaly:
        a += [sciezki.keysrc(k), sciezki.dyn_on(k)]
    for kanal in sorted({int(x) for x in u.przyciszanie.get("profil", {}).get("inserty", {})}):
        a += [sciezki.insert_fxslot(kanal), sciezki.insert_on(kanal)]
    a.append(sciezki.fader_szyny(u.szyna_klucza))
    # L05: wszystkie wejścia klucza przyciszania (kanały 1-16 i powroty).
    a += sciezki.wejscia_szyny(u.szyna_klucza)
    a += [sciezki.MONITOR_ZRODLO, sciezki.MONITOR_TRYB_KANALOW, sciezki.MONITOR_DIMPFL,
          sciezki.MONITOR_DIMATT, sciezki.MONITOR_POZIOM, sciezki.SCENA_INDEKS]
    a.append(sciezki.SOLO_MAIN_LR)    # solo Main LR przy CUE (Michał 22.10.2026)
    return list(dict.fromkeys(a))


def adresy_krytyczne(u: Ustawienia) -> list[str]:
    """Okresowy odczyt torów antenowych i rozmów (kontrakt pkt 6): Main On,
    mute głosów, wysyłki do szyn rozmówców, punkty pobrania mikrofonu (znacznik
    CUE), suwaki rozmówców, głośniki, podsłuch. Pozostałe punkty pobrania
    zmieniają się rzadko: ich zmianę z innego klienta zgłasza /xremote."""
    a: list[str] = []
    rozmowcy = {o.wlasne_zrodlo for o in u.odbiorcy.values()}
    for z in u.zrodla.values():
        a += [sciezki.lr(k) for k in z.kanaly]
        if z.glos:
            a += [sciezki.mute_kanalu(k) for k in z.kanaly]
        if z.klucz in rozmowcy:
            a += [sciezki.fader(k) for k in z.kanaly]
        for odb in u.odbiorcy.values():
            if odb.wlasne_zrodlo != z.klucz:
                for k, b in pary_wysylek(z.kanaly, odb.szyny):
                    a.append(sciezki.wysylka(k, b))
                    if z.klucz == MIKROFON:
                        a.append(sciezki.tap(k, b))
    a += [sciezki.mute_szyny(b) for b in u.szyny_glosnikow]
    a.append(sciezki.wysylka(u.zrodla[TELEFON].kanaly[0], u.szyna_podsluchu))
    # Szyna na Main LR wyprowadza rozmowę albo klucz na antenę: odczyt okresowy
    # łapie też zmianę, której zgłoszenie /xremote zginęło.
    a += [sciezki.szyna_lr(b) for b in range(1, 7)]
    # Wszystkie wejścia klucza przyciszania (L05): także obce, żeby odczyt
    # okresowy zamknął je, gdy zgłoszenie /xremote zginęło.
    a += sciezki.wejscia_szyny(u.szyna_klucza)
    return list(dict.fromkeys(a))
