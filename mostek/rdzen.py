"""Rdzeń mostka: przełącznik mikrofonu, CUE rozmówców, suwaki, gałki, odsłuch.

Model rozmów jak w konsoletach D&R (plan v20, rozdz. 6 do 8): SELECT na
pasku telefonu albo Zooma to CUE (rozmowa poza anteną), drugie naciśnięcie
zwalnia CUE (rozmówca czeka i słyszy antenę), podniesienie suwaka wpuszcza
czekającego rozmówcę na antenę. F3 zwalnia wszystkie CUE. Mikrofon wchodzi
na antenę wyłącznie przełącznikiem (F1 albo SELECT paska 1) i jest w każdej
rozmowie poza anteną.

Mechanizmy D&R z planu v21 i v22 (rozdz. 8, „Mechanizmy z konsolet D&R”):
  * podniesienie suwaka rozmówcy z CUE kończy jego CUE i wpuszcza go na
    antenę („Auto CUE Reset by FADER”),
  * MUTE na pasku mikrofonu to przycisk kaszlu (tylko na czas trzymania),
  * liczniki czasu od potwierdzonej zmiany stanu w statusie,
  * alarm ciszy na antenie z mierników MR18,
  * klucz przyciszania słuchacza (Bus 5): mikrofon i Zoom tylko z tej samej
    rozmowy co słuchacz; wysyłki przełączane razem z przejściem.

Jedna kolejka zapisów (plan, rozdz. 8, kontrakt pkt 3). Rdzeń decyduje
i mówi wyłącznie na podstawie wartości POTWIERDZONYCH odczytem z miksera.
Każdy zapis przechodzi przez zaporę niezmienników (logika.Zapora), a potem
jest potwierdzany osobnym odczytem (klient.KlientMR18.ustaw).

Każda zmiana stanu rozmów to przejście do celu wyliczonego z odczytu
(Rdzen.cel) według rozdziału 7:
  1. zamknięcia: Main On mikrofonu i rozmówców, głośniki, wysyłki do
     zamknięcia albo przyciszenia, podsłuch prawego ucha; każdy krok jest
     próbowany także po błędzie poprzedniego;
  2. dwa zgodne odczyty, ponowienie wyłącznie brakujących zamknięć;
     zmiana sceny albo routingu z innego klienta przerywa przejście;
  3. silnik ściąga suwak rozmówcy, który dostał CUE;
  4. otwarcia: punkty pobrania (przy zamkniętej wysyłce), Main On
     mikrofonu, rozmowa (najpierw mikrofon), program za suwakiem, Main On
     rozmówców, podsłuch; stop na pierwszym niepotwierdzonym kroku
     i zamknięcie tego, co sekwencja sama otworzyła;
  5. dwa zgodne odczyty otwarć, dopiero potem komunikat NVDA.
Przejście niepełne: „Przejście niepełne, prywatność niepotwierdzona”, bez
otwierania nowych dróg i bez powrotu do dawnego stanu publicznego.
"""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass, field

from . import nauka, sciezki
from .informacja import AtrapaDzwiekow, InformacjaZwrotna, polacz
from .klient import BrakOdpowiedzi, zgodne
from .konwersje import (ZERO_DB, poziom_db_na_float, dimatt_db_na_float, gain_db_na_float, gain_float_na_db,
                        poziom_db_na_float, poziom_float_na_db, trim_db_na_float, trim_float_na_db)
from .liczniki import czas_slownie
from .mierniki import DetektorCiszy, dekoduj_blok, poziom_lr
from .logika import (ANTENA, CUE, CZEKA, CZEKA_POZA_SUMA, MIKROFON, TELEFON, NaruszenieZapory,
                     Widok, Zapora, adresy_krytyczne, czy_otwiera, nazwa_wejscia, obce_wejscia_klucza,
                     opis_fadera, pary_wysylek, sprawdz_profil, wszystkie_adresy_odczytu)
from .mowa import Priorytet
from .playout import TorEmisji
from .stan import NIEZNANY, StanMiksera

log = logging.getLogger("mostek.rdzen")

TOL = 0.005


@dataclass
class Krok:
    adres: str
    wartosc: object
    zamkniecie: object = None      # wartość zamykająca (do wycofania otwarcia); None = brak

    @property
    def otwiera(self) -> bool:
        return self.zamkniecie is not None and not zgodne(self.wartosc, self.zamkniecie)


@dataclass
class GlosnikiTalkbacku:
    aktywne: bool
    wyciszone_przez_talkback: bool = False
    przywroc: bool = False
    obca_zmiana: bool = False


@dataclass
class SoloKaszlu:
    sprzed: dict[str, int]
    oczekiwane: dict[str, int]
    obca_zmiana: bool = False


@dataclass
class WynikSekwencji:
    ok: bool
    niepotwierdzone: list
    powod: str = ""
    utrata: bool = False


@dataclass
class CelWysylki:
    poziom: float
    tap: int | None
    zrodlo: str
    rozmowca: str


@dataclass
class Cel:
    """Docelowy stan parametrów zarządzanych przez mostek (plan v20, rozdz. 6)."""
    cue: frozenset
    lr: dict                     # adres -> 0/1 (tylko zmieniane)
    wysylki: dict                # adres poziomu -> CelWysylki
    podsluch: float
    wycisz_glosniki: bool
    odsluch: list = field(default_factory=list)
    klucz: dict = field(default_factory=dict)   # adres wysyłki do Bus 5 -> poziom (przed suwakiem)


@dataclass
class WynikPrzejscia:
    ok: bool
    etap: str = ""
    utrata: bool = False
    powod: str = ""
    niepotwierdzone: list = field(default_factory=list)
    trzymane: list = field(default_factory=list)
    odsluch_ok: bool = True


def adres_tap(adres_poziomu: str) -> str:
    """/ch/NN/mix/BB/level -> /ch/NN/mix/BB/tap."""
    return adres_poziomu[: -len("level")] + "tap"


# Zdarzenia z powierzchni (adapter X-TOUCH albo konsola) --------------------
# ("przycisk", pasek, indeks 0-3)   REC, SOLO, MUTE, SELECT
# ("galka_wcisnij", pasek)
# ("galka", pasek, kierunek +1/-1)
# ("suwak", pasek, pozycja 0.0-1.0) pasek 9 = MASTER
# ("dotyk", pasek, True/False)
# ("klawisz", nazwa)                nazwy jak w ustawieniach xtouch.klawisze
# ("puszczenie", pasek, indeks)     puszczenie przycisku (tylko kaszel na MUTE)
# ("kontroler", powod)              utrata albo restart kontrolera: przerywa kaszel
#                                   i rozbraja powierzchnię (L01, analiza v22)
# ("kontroler_powrot", powod)       kontroler znowu połączony: silniki i diody
#                                   według odczytu, potem uzbrojenie
# Puszczenie nie jest „przyciskiem”: czeka na koniec trwającej operacji,
# zamiast przepaść z komunikatem „czekam na mikser” (zgubione puszczenie).
PRZYCISKI = ("przycisk", "galka_wcisnij", "klawisz")
# Klawisze bez odczytu i zapisu miksera: F4 (tryb informacji zwrotnej) i F5
# (powtórzenie ostatniego komunikatu) działają także przy stanie NIEZNANY.
KLAWISZE_EMISJI = ("transport_play", "transport_stop", "transport_nastepny",
                   "rewind_wolny", "ffwd_wolny", "F6_co_gra", "F7_automat",
                   "emisja_gora", "emisja_dol", "emisja_znacznik",
                   "bank_lewo_odtwarzacz", "bank_prawo_wolny", "channel_lewo_automat", "emisja_pozostalo",
                   "kursor_lewo_wolny", "kursor_prawo_wolny", "scrub_wolny")
KLAWISZE_BEZ_MIKSERA = ("F4_tryb_informacji", "F5_ostatni_komunikat") + KLAWISZE_EMISJI
# Komunikaty, których F5 nie powtarza: same F4 i F5 oraz „czekam na mikser”.
BEZ_POWTORZENIA = ("tryb", "powtorz", "czekam")


class Rdzen:
    def __init__(self, u, klient, mowa, powierzchnia=None, emisja=None,
                 zegar=time.monotonic, sen=time.sleep, informacja=None) -> None:
        self.u = u
        self.klient = klient
        self.mowa = mowa
        # Tryby informacji zwrotnej (mowa, dźwięki, dźwięki z mową). Kolejka
        # mowy odtwarza dźwięki tym samym obiektem (KolejkaMowy.dzwieki).
        if informacja is None:
            informacja = getattr(mowa, "dzwieki", None) or InformacjaZwrotna(u, AtrapaDzwiekow())
        self.informacja = informacja
        self._ostatni: str | None = None    # ostatni komunikat stanu dla F5
        self.powierzchnia = powierzchnia
        self.emisja = emisja
        self._tor_emisji = TorEmisji(u, lambda: self.emisja)
        self._odbior_emisji = threading.Lock()  # wątek playoutu i tick: kolejność komunikatów
        self._hold_przejscie = False
        self._hold_wyniki = []
        self._tor_emisji.przy_wyniku = self.odbierz_emisje
        self._blokada_emisji = threading.Lock()
        self.zegar = zegar
        self.sen = sen
        self.stan = StanMiksera()
        self.widok = Widok(u, self.stan)
        self.zapora = Zapora(u)
        z = u.zachowanie
        m = u.mikser
        self.debounce_s = float(z.get("debounce_s", 0.05))
        self.zwloka_suwaka = float(z.get("zwloka_potwierdzenia_suwaka_s", 0.3))
        self.okres_xremote = float(m.get("odnowienie_xremote_s", 5.0))
        self.okres_krytyczny = float(m.get("okres_odczytu_krytycznego_s", 0.5))
        self.przerwa_odczytu = float(m.get("przerwa_podwojnego_odczytu_s", 0.05))
        self.okres_ponowienia = float(m.get("okres_ponowienia_polaczenia_s", 1.0))
        # L02: odczyt krytyczny starszy niż limit to stan NIEZNANY (plan, rozdz. 8,
        # kontrakt pkt 6). Każde otwarcie wymaga świeżego odczytu przed zapisem.
        self.limit_swiezosci = float(m.get("limit_swiezosci_s", 1.0))
        self._ost_swiezy = float("-inf")
        # Echo pary (Michał, 24.10.2026): zapis jednego kanału linkowanej pary
        # (/config/chlink, /config/buslink) mikser powiela sam na drugi. Ta
        # zmiana nie jest zmianą z innego urządzenia: adres -> (wartość, czas).
        self.okno_echa_par = float(m.get("okno_echa_par_s", 2.0))
        self._echo_par: dict[str, tuple[object, float]] = {}
        # L01: utrata kontrolera rozbraja powierzchnię do jego powrotu.
        self.kontroler_polaczony = True
        self._w_zdarzeniu = False
        self._baza_galek: dict[str, float] = {}
        self._galka_komunikat: dict[str, float] = {}
        self._dotyk: set[int] = set()
        self._suwak_ruch: dict[int, float] = {}
        self._rozbieznosc_zgloszona: set[int] = set()
        self.uzbrojony = False
        self._zgloszenia: queue.SimpleQueue = queue.SimpleQueue()
        self._wykonuje = threading.Lock()
        self._zmiana = threading.Lock()
        self._zmiana_w_toku = False
        self._ostatnie_nacisniecie: dict[tuple, float] = {}
        self._nauka_od: float | None = None   # tryb nauki klawiszy: czas ostatniego naciśnięcia
        self._ost_xremote = float("-inf")
        self._ost_krytyczny = float("-inf")
        self._ost_proba = float("-inf")
        self._ost_stop = float("-inf")
        self.dziennik: list[tuple] = []
        # Kaszel (plan v21, pkt 2): {"od": czas} od potwierdzonego zdjęcia mikrofonu.
        self._kaszel: dict | None = None
        self._solo_kaszlu: SoloKaszlu | None = None
        self._zapisuje_solo_kaszlu = False
        self._talkback: set[str] = set()
        self._mikrofon_sprzed: dict | None = None
        # Rozmówcy, którym trzymany talkback przyciszył muzykę w powrocie
        # (zlecenie Michała z 26.10.2026). Pusty zbiór = mostek niczego nie
        # przycisza i niczego nie ma do przywrócenia.
        self._muzyka_przyciszona: set[str] = set()
        # Wartości wysyłek muzyki sprzed przyciszenia: powrót ma oddać dokładnie
        # ten poziom, a nie przeliczony z decybeli.
        self._muzyka_sprzed: dict[str, float] = {}
        self._glosniki_talkback: GlosnikiTalkbacku | None = None
        self._chwilowy_rodzaj = "kaszel"
        self._zamkniecia_chwilowe_zalegle = False
        self._opis_blokady = ""          # pierwsza blokująca niezgodność profilu
        # Liczniki (plan v21, pkt 3): klucz -> (stan, czas zmiany albo None = początek nieznany).
        self._liczniki: dict[str, tuple] = {}
        self._przypomnienie: tuple = (None, 0)
        # Alarm ciszy (plan v21, pkt 4).
        a = u.alarm_ciszy
        self.alarm_wlaczony = bool(a.get("wlaczony", True))
        mi = u.mierniki
        self.detektor = DetektorCiszy(prog_dbfs=float(a.get("prog_dbfs", -50.0)),
                                      czas_s=float(a.get("czas_s", 10.0)),
                                      powtorka_s=float(a.get("powtorka_s", 30.0)),
                                      limit_braku_s=float(mi.get("limit_braku_s", 2.0)))
        self.okres_miernikow = float(mi.get("odnowienie_s", self.okres_xremote))
        self._ost_mierniki = float("-inf")
        self.bledy_miernikow = 0
        if hasattr(klient, "przy_zgloszeniu"):
            klient.przy_zgloszeniu = self.zgloszenie
        if hasattr(klient, "przy_miernikach"):
            klient.przy_miernikach = self._przyjmij_mierniki

    # ======================================================================
    # mowa i pomocnicze
    # ======================================================================
    def powiedz(self, tekst: str, priorytet: Priorytet = Priorytet.STAN, klucz: str | None = None,
                dzwiek: bool = False) -> None:
        """Komunikat według trybu informacji zwrotnej.

        dzwiek=True tylko dla komunikatu potwierdzonej zmiany stanu: w trybie
        DZWIEKI może zabrzmieć samym dźwiękiem, ale wyłącznie wtedy, gdy każda
        jego część jest stanem z informacja.KOMUNIKATY_DZWIEKIEM i ma dźwięk.
        Pozostałe komunikaty (domyślnie) zawsze mają mowę; ostrzeżenia
        i odmowy dostają przed mową dźwięk alarm albo odmowa."""
        zdarzenia = getattr(tekst, "zdarzenia", ())
        if dzwiek:
            dzwieki, mow = self.informacja.plan(zdarzenia, priorytet)
        else:
            dzwieki, mow = self.informacja.plan_ostrzezenia(zdarzenia, priorytet), True
        if priorytet != Priorytet.INFORMACJA and klucz not in BEZ_POWTORZENIA:
            self._ostatni = str(tekst)
        self.mowa.powiedz(tekst, priorytet, klucz, dzwieki=dzwieki, mow=mow)

    def t(self, klucz: str, **p) -> str:
        return self.u.tekst(klucz, **p)

    def _nazwa(self, zr: str) -> str:
        return self.u.zrodla[zr].nazwa

    def _rodzaj(self, zr: str) -> str:
        return self.u.zrodla[zr].rodzaj

    def _swiezy(self, limit: float | None = None) -> bool:
        """Czy ostatni pełny odczyt torów krytycznych mieści się w limicie
        świeżości z ustawień (mikser.limit_swiezosci_s) albo w podanym."""
        limit = self.limit_swiezosci if limit is None else limit
        return self.zegar() - self._ost_swiezy <= limit + 1e-9  # POPRAWKA L02: limit świeżości

    def _gotowy(self) -> bool:
        """Stan znany: połączenie, pełna synchronizacja i świeży odczyt krytyczny (L02)."""
        return self.stan.polaczony and self.stan.zsynchronizowany and self._swiezy()

    def _zapewnij_swiezosc(self) -> None:
        """Przed decyzją ze zdarzenia: odczyt krytyczny, gdy ostatni jest
        starszy niż okres odczytu krytycznego albo połowa limitu świeżości,
        więc decyzja i zapisy przejścia mieszczą się w limicie świeżości. Brak
        odpowiedzi daje utratę łączności, czyli stan NIEZNANY (L02).

        Zapas połowy limitu: przy odczycie okresowym co 5 s próg równy całemu
        limitowi (1 s) przepuszczał odczyt sprzed np. 0,9 s, a odczyty samego
        przejścia wypychały go za limit, zanim padł komunikat (Michał,
        26.10.2026: suwak czasem bez dźwięku, 3 z 296 przejść w dzienniku)."""
        prog = min(self.okres_krytyczny, self.limit_swiezosci / 2)
        if (self.stan.polaczony and self.stan.zsynchronizowany
                and not self._swiezy(prog)):  # POPRAWKA SUWAK: zapas przed limitem
            self._ost_krytyczny = self.zegar()
            self._odczyt_krytyczny()

    def _odswiez_przed_otwarciem(self) -> None:
        """Otwarcie przy odczycie krytycznym starszym niż limit (L02): najpierw
        świeży odczyt torów krytycznych. Gdy coś się zmieniło, otwarcie jest
        odrzucone, odczyt zostaje nieświeży, a zmianę ogłasza najbliższy odczyt
        okresowy (bez otwarć, P02). Brak odpowiedzi: BrakOdpowiedzi, czyli
        stan NIEZNANY."""
        reczne = self._suwaki_w_rekach()
        adresy = [a for a in adresy_krytyczne(self.u) if a not in reczne]
        dane = self.klient.odczytaj_wiele(adresy)
        teraz = self.zegar()
        zmienione = [a for a in adresy
                     if (self.stan.wartosc(a) is NIEZNANY or not zgodne(self.stan.wartosc(a), dane[a]))
                     and not self._przyjmij_echo(a, dane[a])]
        for a in adresy:
            if a not in zmienione:
                self.stan.potwierdz(a, dane[a], teraz)
        if zmienione:
            self._dz("swiezosc-zmiana", zmienione)
            self._ost_krytyczny = float("-inf")
            raise NaruszenieZapory(self.t("powod_nieswiezy"))
        self._ost_swiezy = teraz

    def _rozbrojone(self) -> bool:
        """Zdarzenie z powierzchni przy utraconym kontrolerze: bez otwarć (L01)."""
        return self._w_zdarzeniu and not self.kontroler_polaczony

    def _rozmowcy(self) -> list[str]:
        return self.widok.rozmowcy()

    def _pasek_zrodla(self, zr: str) -> int | None:
        for p, opis in self.u.paski.items():
            if opis.get("zrodlo") == zr:
                return p
        return None

    def _zrodlo_paska(self, pasek: int):
        opis = self.u.paski.get(pasek) or {}
        return opis.get("zrodlo")

    def _z_kim(self, cue) -> str:
        lista = [r for r in self._rozmowcy() if r in cue]
        if len(lista) == 1:
            return self.u.zrodla[lista[0]].z_kim
        return self.t("rozmowa_wszyscy")

    def _dz(self, *wpis) -> None:
        self.dziennik.append((self.zegar(),) + wpis)
        log.info("%s", wpis)

    @staticmethod
    def _wl(db: float) -> float:
        """Poziom włączonej wysyłki: nigdy zero, bo zero to wysyłka wyłączona."""
        v = poziom_db_na_float(db)
        return v if v > 0.0 else 0.001

    # ======================================================================
    # łączność i synchronizacja
    # ======================================================================
    def _utrata(self, powod: str = "", oglos: bool | None = None) -> None:
        byl = self.stan.polaczony if oglos is None else oglos
        self.stan.utrata()
        self.uzbrojony = False
        self._dz("utrata", powod)
        if byl:
            self.powiedz(self.t("utrata_lacznosci"), Priorytet.BEZPIECZENSTWO, "lacznosc")
        # Stan NIEZNANY przerywa kaszel: mikrofon zostaje poza anteną (decyzja 2).
        self._przerwij_kaszel()
        self._liczniki.clear()
        self.detektor.reset()
        self._odswiez_powierzchnie()

    def synchronizuj(self, nowa_baza_galek: bool = False) -> bool:
        """Pełny odczyt. Nigdy nie wysyła lokalnych wartości do miksera (kontrakt pkt 1 i 9).
        Jedyne zapisy to ochronne zamknięcia niebezpiecznych dróg (decyzja P02)."""
        self.uzbrojony = False
        byl_blokowany = self.zapora.profil_blokuje
        # Pełny odczyt (start, powrót łączności, scena z innego urządzenia)
        # kończy kaszel bez przywracania mikrofonu (decyzja 2).
        self._przerwij_kaszel()
        byl_polaczony = self.stan.polaczony
        try:
            info = self.klient.identyfikuj()
            self.stan.nowa_sesja()
            dane = self.klient.odczytaj_wiele(wszystkie_adresy_odczytu(self.u))
        except BrakOdpowiedzi as e:
            # nowa_sesja() ustawia połączenie przed pełnym odczytem. Bez tego
            # każda nieudana próba co okres_ponowienia ogłaszała utratę od nowa
            # (pomiar 18.10.2026: komunikat co 3 s).
            self._utrata(str(e), oglos=byl_polaczony)
            return False
        teraz = self.zegar()
        for a, v in dane.items():
            self.stan.potwierdz(a, v, teraz)
        self.stan.zsynchronizowany = True
        self._ost_swiezy = teraz
        if self._zamkniecia_chwilowe_zalegle:
            self._domknij_chwilowy()
            if not self.stan.polaczony:
                return False
        self._dz("synchronizacja", info)
        self._przelicz_profil()
        if byl_blokowany and not self.zapora.profil_blokuje:
            self.powiedz(self.t("profil_zgodny"), Priorytet.BEZPIECZENSTWO, "profil")
        for zr, z in self.u.zrodla.items():
            if z.galka and (nowa_baza_galek or zr not in self._baza_galek):
                db = self._galka_db(zr)
                if db is not NIEZNANY:
                    self._baza_galek[zr] = db
        try:
            self.klient.odnow_subskrypcje()
        except Exception:  # noqa: BLE001
            log.exception("nie udało się odnowić subskrypcji")
        self._odnow_mierniki(self.zegar())
        self.detektor.oczekuj(self.zegar())
        self._ost_xremote = self.zegar()
        self._ost_krytyczny = self.zegar()
        # Najpierw silniki według odczytu, potem uzbrojenie dotyku (kontrakt pkt 10).
        # Przy utraconym kontrolerze powierzchnia zostaje rozbrojona (L01).
        self._ustaw_silniki()
        self.uzbrojony = self.kontroler_polaczony
        # Po starcie i po powrocie łączności nie wiadomo, od kiedy trwa stan.
        self._aktualizuj_liczniki(poczatek_znany=False)
        self._ochronne_zamkniecia()
        self._odswiez_powierzchnie()
        return True

    def _przelicz_profil(self, oglos: bool = True) -> bool:
        """Porównanie odczytu z profilem i ustawienie blokady otwarć. Woła je
        pełny odczyt oraz każdy odczyt ze zmianą (także z innego urządzenia),
        bo wysyłki, linki i szyny na Main LR wchodzą do profilu. Zwraca, czy
        profil blokuje."""
        naruszenia = sprawdz_profil(self.u, self.widok)
        blokujace = [n for n in naruszenia if n.blokuje]
        self.zapora.profil_blokuje = bool(blokujace)
        self._opis_blokady = blokujace[0].opis if blokujace else ""
        if oglos:
            for n in naruszenia:
                self._dz("profil", n.opis, n.blokuje)
        if blokujace and oglos:
            self.powiedz(self.t("profil_niezgodny", opis=blokujace[0].opis),
                         Priorytet.BEZPIECZENSTWO, "profil")
        return bool(blokujace)

    def _uzgodnij_klucz(self) -> list[Krok]:
        """Wysyłki do klucza przyciszania (Bus 5) do zamknięcia: źródła spoza
        rozmowy słuchacza, np. po przejściu urwanym utratą łączności albo po
        ruchu suwaka bez potwierdzenia. Przy blokującej niezgodności profilu
        (np. szyna na Main LR) cały klucz, także w trwającej rozmowie."""
        blokuje = self.zapora.profil_blokuje   # POPRAWKA: klucz zamknięty przy niezgodnym profilu
        zle = [a for zr in self.u.zrodla_klucza if self.widok.klucz(zr) is not False
               and (blokuje or self.widok.ta_sama_rozmowa(zr) is not True) for a in self.widok.adresy_klucza(zr)]
        return self._bez_zbednych([Krok(a, 0.0) for a in zle], self.widok)

    def _ochronne_zamkniecia(self) -> None:
        """Ochronne zamknięcia po odczycie (decyzja Michała z 18.10.2026, P02).

        Pełny odczyt, odczyt okresowy i status zamykają wyłącznie niebezpieczne
        drogi wykryte w odczycie: szynę na Main LR, obce wejście klucza
        przyciszania (L05) i klucz przy blokującym profilu albo poza rozmową
        słuchacza. Nic nie otwierają, nie przywracają sceny ani dawnych stanów,
        nie dotykają anteny ani rozmów. NVDA ostrzega. Blokada profilu zostaje
        do pełnego odczytu zgodnego profilu (kontrakt pkt 8): samo zamknięcie
        jej nie zdejmuje. Pełny odczyt robi zmiana routingu albo sceny,
        powrót łączności i F2 przy blokadzie (świadome polecenie Michała)."""
        if not (self.stan.polaczony and self.stan.zsynchronizowany):
            return
        w = self.widok
        kroki: list[Krok] = []
        opisy: list[str] = []
        for b in range(1, 7):
            if w.stan.wartosc(sciezki.szyna_lr(b)) == 1:  # POPRAWKA P02: szyna zdejmowana z Main LR
                kroki.append(Krok(sciezki.szyna_lr(b), 0))
                opisy.append(self.t("ochrona_szyna_lr", szyna=b))
        for a in obce_wejscia_klucza(self.u, w):   # POPRAWKA L05: obce wejście klucza zamykane
            kroki.append(Krok(a, 0.0))
            opisy.append(self.t("ochrona_klucz_obce", nazwa=nazwa_wejscia(self.u, a)))
        klucz = [k for k in self._uzgodnij_klucz() if k.adres not in {x.adres for x in kroki}]
        if klucz:
            kroki += klucz
            opisy.append(self.t("ochrona_klucz" if self.zapora.profil_blokuje else "ochrona_klucz_poza_rozmowa"))
        if not kroki:
            return
        self._dz("ochronne-zamkniecie", [k.adres for k in kroki])
        self._zamknij(kroki)
        oczek = {k.adres: k.wartosc for k in kroki}
        zle = self._dwa_odczyty(oczek) if self.stan.polaczony else list(oczek)
        if zle and self.stan.polaczony:
            self._zamknij([k for k in kroki if k.adres in zle])
            zle = self._dwa_odczyty({a: oczek[a] for a in zle}) if self.stan.polaczony else zle
        lista = ", ".join(opisy)
        if zle:
            self._dz("ochronne-zamkniecie-niepelne", zle)
            self.powiedz(self.t("ochronne_zamkniecie_niepotwierdzone", lista=lista),
                         Priorytet.BEZPIECZENSTWO, "ochrona")
            return
        self.powiedz(self.t("ochronne_zamkniecie", lista=lista), Priorytet.BEZPIECZENSTWO, "ochrona")

    def start(self) -> bool:
        self.powiedz(self.t("sterowanie_uruchomione"), Priorytet.INFORMACJA)
        ok = self.synchronizuj(nowa_baza_galek=True)
        if ok:
            self.powiedz(self.tekst_statusu(), Priorytet.STAN, "status")
        else:
            self.powiedz(self.t("stan_nieznany"), Priorytet.BEZPIECZENSTWO, "lacznosc")
        return ok

    # ======================================================================
    # zapis i sekwencje
    # ======================================================================
    def _zapis(self, krok: Krok) -> bool:
        # Jawne polecenie odsłuchu (także OFF -> OFF) unieważnia migawkę.
        if (self._solo_kaszlu is not None and not self._zapisuje_solo_kaszlu
                and krok.adres.startswith("/-stat/solosw/")):
            self._solo_kaszlu.obca_zmiana = True
        if czy_otwiera(krok.adres, krok.wartosc):
            if self._rozbrojone():
                raise NaruszenieZapory(self.t("kontroler_otwieranie"))
            if not self._swiezy():
                # L02: otwarcie tylko na świeżym odczycie; zamknięcia zawsze.
                self._odswiez_przed_otwarciem()
        self.zapora.sprawdz(krok.adres, krok.wartosc, self.widok)
        teraz = self.zegar()
        self.stan.zanotuj_wyslanie(krok.adres, krok.wartosc, teraz)
        try:
            w = self.klient.ustaw(krok.adres, krok.wartosc)
        except BrakOdpowiedzi:
            self.stan.zakoncz_wyslanie(krok.adres)
            self._dz("zapis-brak-odpowiedzi", krok.adres, krok.wartosc)
            raise
        self.stan.zakoncz_wyslanie(krok.adres)
        self._echo_par.pop(krok.adres, None)
        if w.odczytana is not None:
            self.stan.potwierdz(krok.adres, w.odczytana, self.zegar())
        if w.potwierdzony:
            self._zanotuj_echo_par(krok.adres, w.odczytana)
        self._dz("zapis", krok.adres, krok.wartosc, w.odczytana, w.potwierdzony)
        return w.potwierdzony

    # --- echo linkowanych par --------------------------------------------------
    def _w_parze(self, adres_linku: str) -> bool:
        return self.stan.wartosc(adres_linku) == 1

    def partnerzy_pary(self, adres: str) -> list[str]:
        """Adresy, które mikser ustawi sam po zapisie adresu (para według
        odczytanych /config/chlink i /config/buslink)."""
        return sciezki.partnerzy_pary(adres, self._w_parze)

    def _zanotuj_echo_par(self, adres: str, wartosc) -> None:
        teraz = self.zegar()
        for p in self.partnerzy_pary(adres):
            self._echo_par[p] = (wartosc, teraz)

    def _przyjmij_echo(self, adres: str, wartosc) -> bool:
        """Czy odczytana zmiana adresu to echo własnego zapisu drugiego kanału
        pary: dokładnie ta wartość, w oknie okno_echa_par_s. Echo jest zużywane
        jednorazowo. Każda inna wartość dalej jest zmianą z innego urządzenia."""
        e = self._echo_par.get(adres)
        if e is None:
            return False
        v, t = e
        if self.zegar() - t > self.okno_echa_par:
            del self._echo_par[adres]
            return False
        if not zgodne(v, wartosc):
            return False
        del self._echo_par[adres]
        self._dz("echo-pary", adres, wartosc)
        return True

    def _zamknij(self, kroki: list[Krok]) -> WynikSekwencji:
        """Sekwencja zamykająca: każdy krok jest próbowany."""
        nie, utrata, powod = [], False, ""
        klucz = {sciezki.wysylka(k, self.u.szyna_klucza) for zr in self.u.zrodla_klucza
                 for k in self.u.zrodla[zr].kanaly}
        for k in kroki:
            if utrata and not (k.adres.endswith("/mix/lr") or k.adres in klucz
                               or k.adres in self._adresy_mikrofonu()):
                # Po utracie łączności próbujemy już tylko zdjąć kanały z anteny
                # i źródła z klucza przyciszania (plan v22).
                nie.append(k)
                continue
            try:
                if not self._zapis(k):
                    nie.append(k)
            except NaruszenieZapory as e:
                nie.append(k)
                powod = str(e)
            except BrakOdpowiedzi:
                nie.append(k)
                utrata = True
        if utrata:
            self._utrata("brak odpowiedzi przy zamykaniu")
        return WynikSekwencji(not nie, nie, powod, utrata)

    def _otworz(self, kroki: list[Krok]) -> WynikSekwencji:
        """Sekwencja otwierająca: stop na pierwszym błędzie, wycofanie otwartych kroków."""
        wykonane: list[Krok] = []
        for k in kroki:
            powod, utrata, ok = "", False, False
            try:
                ok = self._zapis(k)
            except NaruszenieZapory as e:
                powod = str(e)
            except BrakOdpowiedzi:
                utrata = True
            if ok:
                wykonane.append(k)
                continue
            wycofanie = [Krok(x.adres, x.zamkniecie) for x in reversed(wykonane) if x.otwiera]
            if utrata:
                self._zamknij(wycofanie)        # mimo utraty próbujemy zamknąć otwarte
                self._utrata("brak odpowiedzi przy otwieraniu")
            elif wycofanie:
                self._zamknij(wycofanie)
            return WynikSekwencji(False, [k], powod or self.t("powod_niepotwierdzone"), utrata)
        return WynikSekwencji(True, [])

    def _dwa_odczyty(self, oczekiwane: dict[str, object]) -> list[str]:
        """Dwa zgodne odczyty po zapisach (kontrakt pkt 4). Zwraca adresy niezgodne."""
        if not oczekiwane:
            return []
        adresy = list(oczekiwane)
        try:
            pierwszy = self.klient.odczytaj_wiele(adresy)
            self.sen(self.przerwa_odczytu)
            drugi = self.klient.odczytaj_wiele(adresy)
        except BrakOdpowiedzi:
            self._utrata("brak odpowiedzi przy weryfikacji")
            return adresy
        teraz = self.zegar()
        zle = []
        for a in adresy:
            self.stan.potwierdz(a, drugi[a], teraz)
            if not (zgodne(pierwszy[a], oczekiwane[a]) and zgodne(drugi[a], oczekiwane[a])):
                zle.append(a)
        return zle

    # --- generatory kroków --------------------------------------------------
    def kroki_sumy(self, zr: str, wl: bool) -> list[Krok]:
        return [Krok(sciezki.lr(k), 1 if wl else 0, 0) for k in self.u.zrodla[zr].kanaly]

    def kroki_solo_lr(self, wl: bool) -> list[Krok]:
        """Solo Main LR (/-stat/solosw/50) zawsze wyłączone. Pomiar na MR18
        fw 1.19 z 22.10.2026: włączone nie dodaje sumy do PHONES (różnica
        PHONES do LR bez zmian), więc muzykę przy CUE daje PFL kanałów muzyki
        (kroki_muzyki_przy_cue). Krok zostaje, żeby sprzątnąć stan z d99eb23."""
        return [Krok(sciezki.SOLO_MAIN_LR, 0)]

    def kroki_muzyki_przy_cue(self, cue) -> list[Krok]:
        """Michał 22.10.2026: przy CUE słyszy muzykę z anteny jak rozmówca.
        Przy aktywnym solo PHONES gra tylko kanały solo (pomiar: solo Zooma
        -42 dB wobec LR, solo Zooma i muzyki -4 dB), więc na czas rozmowy
        PFL dostaje muzyka, która jest na antenie (Main On). Po rozmowie PFL
        muzyki wyłączony. Antena bez zmian."""
        wl_cue = bool(cue) and self.u.zachowanie.get("program_w_sluchawkach_przy_cue", True)
        kroki: list[Krok] = []
        for zr in self.widok.muzyka():
            wl = wl_cue and self.widok.suma(zr) is True
            kroki += self.kroki_pfl(zr, wl)
        return kroki

    def kroki_pfl(self, zr: str, wl: bool) -> list[Krok]:
        return [Krok(sciezki.solo(k), 1 if wl else 0) for k in self.u.zrodla[zr].kanaly]

    def kroki_wycisz_glosniki(self) -> list[Krok]:
        return [Krok(sciezki.mute_szyny(b), 0) for b in self.u.szyny_glosnikow]

    def _korekta_mikrofonu_db(self) -> float:
        """Ile decybeli dodać do wysyłki mikrofonu przed suwakiem (rozmowa na
        CUE), żeby rozmówca słyszał go jak na antenie, gdzie wysyłka idzie za
        suwakiem (Michał 22.10.2026). Suwak na dole albo nieznany: bez korekty."""
        if not self.u.zachowanie.get("mikrofon_w_rozmowie_jak_na_antenie", True):
            return 0.0
        f = self.widok.fader_db(MIKROFON)
        if f is NIEZNANY or f == float("-inf"):
            return 0.0
        return float(f)

    def _jest_rozmowa_cue(self) -> bool:
        cue = self.widok.cue_zbior()
        return cue is not NIEZNANY and bool(cue)

    def _mikrofon_w_rozmowie_db(self, baza: float) -> float:
        return min(baza + self._korekta_mikrofonu_db(), 10.0)   # wysyłka MR18 najwyżej +10 dB

    def _kroki_dim(self, wl: bool) -> list[Krok]:
        """Przyciszenie przy PFL (/config/solo/dimpfl). Instrukcja MR18, 7.11:
        PFL dimmer ścisza sygnał odsłuchu kontrolnego, żeby zrównać go z AFL.
        Michał 22.10.2026: rozmówcy w słuchawkach jak na antenie, więc
        przyciszenie_pfl_cue_db = 0 wyłącza dimpfl także przy CUE."""
        db = float(self.u.zachowanie.get("przyciszenie_pfl_cue_db", -10.0))
        wl = wl and db < 0.0
        kroki = []
        if wl:
            kroki.append(Krok(sciezki.MONITOR_DIMATT, dimatt_db_na_float(db)))
        kroki.append(Krok(sciezki.MONITOR_DIMPFL, 1 if wl else 0))
        return kroki

    def kroki_odsluchu_rozmowy(self, cue) -> list[Krok]:
        """PFL mikrofonu i uczestników CUE, program przyciszony (plan, rozdz. 6)."""
        kroki: list[Krok] = []
        for zr in [MIKROFON] + self._rozmowcy():
            kroki += self.kroki_pfl(zr, bool(cue) and (zr == MIKROFON or zr in cue))
        kroki += self.kroki_solo_lr(False) + self.kroki_muzyki_przy_cue(cue)
        if cue:
            kroki.append(Krok(sciezki.MONITOR_ZRODLO, sciezki.ZRODLO_LRPFL))
        return kroki + self._kroki_dim(bool(cue))

    def kroki_rozmowy_do_zamkniecia(self, rozmowcy) -> list[Krok]:
        """Wszystkie głosy do i od podanych rozmówców wyłączone (stan NIEZNANY)."""
        kroki: list[Krok] = []
        for r in rozmowcy:
            odb = self.widok.odbiorca(r)
            for s in [MIKROFON] + self._rozmowcy():
                if s != r:
                    kroki += [Krok(a, 0.0) for a in self.widok.adresy_wysylki(s, odb)]
            for inny in self._rozmowcy():
                if inny != r:
                    kroki += [Krok(a, 0.0) for a in self.widok.adresy_wysylki(r, self.widok.odbiorca(inny))]
        # Klucz przyciszania: przy stanie NIEZNANY nie wiadomo, kto jest w rozmowie
        # ze słuchaczem, więc wysyłki do Bus 5 też zamykamy (słuchacz bez przyciszania).
        for zr in self.u.zrodla_klucza:
            kroki += [Krok(a, 0.0) for a in self.widok.adresy_klucza(zr)]
        return list({k.adres: k for k in kroki}.values())

    @staticmethod
    def _bez_zbednych(kroki: list[Krok], widok: Widok) -> list[Krok]:
        """Pomija kroki, których potwierdzony stan już jest równy docelowemu."""
        wynik = []
        for k in kroki:
            v = widok.stan.wartosc(k.adres)
            if v is NIEZNANY or not zgodne(v, k.wartosc):
                wynik.append(k)
        return wynik

    # ======================================================================
    # model CUE: cel i przejście (plan v20, rozdz. 6 i 7)
    # ======================================================================
    def cel(self, cue: frozenset, mikrofon_na_antenie: bool, cue_przed=None, przywroc=(),
            na_antene=()) -> Cel:
        """Cel wyliczony z potwierdzonego odczytu: kto co słyszy w nowym stanie.

        `przywroc`: rozmówcy, którym Main On może wrócić (zwolnione CUE albo
        zmiana ich suwaka); wraca tylko przy suwaku na dole (rozdz. 7).
        `na_antene`: rozmówcy, którym Main On wraca także przy suwaku w górze,
        bo podnieśli suwak z CUE (plan v21, „Auto CUE Reset by FADER”).
        """
        w, u = self.widok, self.u
        rozm = self._rozmowcy()
        lr: dict[str, int] = {}
        for k in u.zrodla[MIKROFON].kanaly:
            lr[sciezki.lr(k)] = 1 if mikrofon_na_antenie else 0
        suma_po: dict[str, object] = {}
        for r in rozm:
            if r in cue:
                v = False                       # Main On rozmówcy OFF na czas CUE
            elif r in na_antene and w.suma(r) is False:
                v = True                        # suwak podniesiony z CUE: wejście na antenę
            elif r in przywroc and w.suma(r) is False and w.suwak_na_dole(r) is True:
                v = True                        # Main On wraca tylko przy suwaku na dole
            else:
                v = w.suma(r)
            suma_po[r] = v
            if v is True or v is False:
                for a in w.adresy_sumy(r):
                    lr[a] = 1 if v else 0

        def na_antenie(s: str) -> bool:
            if s == MIKROFON:
                return mikrofon_na_antenie
            if s in rozm:
                return s not in cue and suma_po[s] is True and w.suwak_w_gorze(s) is True
            return w.suma(s) is True

        wys: dict[str, CelWysylki] = {}
        for r in rozm:
            odb = w.odbiorca(r)
            for s, z in u.zrodla.items():
                if s == r:
                    continue
                baza = u.poziom_bazowy(s, odb)
                if r in cue:
                    if s == MIKROFON:
                        p, t = self._wl(self._mikrofon_w_rozmowie_db(baza)), sciezki.TAP_PRE
                    elif s in cue:
                        p, t = self._wl(baza), sciezki.TAP_PRE
                    elif not z.glos and w.suma(s) is True:
                        p, t = self._wl(baza + u.przyciszenie_muzyki_db), sciezki.TAP_POST
                    else:
                        p, t = 0.0, None
                elif s not in cue and na_antenie(s) and not (s == MIKROFON and cue):
                    # Program za suwakiem. Przy trwającej rozmowie mikrofon nie
                    # idzie do rozmówcy bez CUE, nawet gdy ktoś włączył go na
                    # antenę z innego urządzenia (decyzja 3).
                    p, t = self._wl(baza), sciezki.TAP_POST
                else:
                    p, t = 0.0, None
                for k, b in pary_wysylek(z.kanaly, u.odbiorcy[odb].szyny):
                    wys[sciezki.wysylka(k, b)] = CelWysylki(p, t, s, r)
        tel_slyszy_sie = TELEFON in cue or na_antenie(TELEFON)
        podsluch = 0.0 if tel_slyszy_sie else self._wl(u.poziom_podsluchu())
        odsluch = []
        if cue_przed is not None and frozenset(cue_przed) != frozenset(cue) \
                and u.zachowanie.get("pfl_podaza_za_cue", True):
            odsluch = self.kroki_odsluchu_rozmowy(cue)
        # Klucz przyciszania (plan v22, rozdz. 8, pkt 5): źródło w Bus 5 tylko
        # w tej samej rozmowie co słuchacz. Słuchacz na CUE: mikrofon zawsze,
        # Zoom, gdy też ma CUE. Słuchacz bez CUE: oboje na antenie.
        # Blokująca niezgodność profilu (np. Bus 5 na Main LR): klucz zamknięty.
        sl = u.sluchacz
        klucz: dict[str, float] = {}
        for zr in u.zrodla_klucza:
            if self.zapora.profil_blokuje:
                wl = False
            elif sl in cue:
                wl = zr == MIKROFON or zr in cue
            else:
                wl = na_antenie(sl) and na_antenie(zr) and zr not in cue
            for a in w.adresy_klucza(zr):
                klucz[a] = self._wl(u.poziom_klucza()) if wl else 0.0
        return Cel(frozenset(cue), lr, wys, podsluch, mikrofon_na_antenie or bool(cue), odsluch, klucz)

    def _plan_zamkniec(self, c: Cel, zakres=None) -> list[Krok]:
        st = self.stan
        w_zakresie = (lambda a: True) if zakres is None else (lambda a: a in zakres)
        lr = [Krok(a, 0) for a, v in c.lr.items()
              if v == 0 and w_zakresie(a) and st.wartosc(a) != 0]
        glosniki = []
        if (c.wycisz_glosniki and self.widok.glosniki_wyciszone() is not True
                and (zakres is None or any(a in zakres for a in self.widok.adresy_glosnikow()))):
            glosniki = self.kroki_wycisz_glosniki()
        glosy, muzyka = [], []
        for a, cw in c.wysylki.items():
            if not w_zakresie(a):
                continue
            obecny = st.wartosc(a)
            tap = st.wartosc(adres_tap(a))
            zmiana_tap = cw.poziom > 0 and cw.tap is not None and (tap is NIEZNANY or int(tap) != cw.tap)
            if obecny is NIEZNANY:
                docelowa = 0.0
            elif zmiana_tap and float(obecny) > 0.0:
                docelowa = 0.0       # punkt pobrania zmieniamy tylko przy zamkniętej wysyłce
            elif float(obecny) > cw.poziom + TOL:
                docelowa = cw.poziom if not zmiana_tap else 0.0
            else:
                continue
            (glosy if self.u.zrodla[cw.zrodlo].glos else muzyka).append(Krok(a, docelowa))
        # Znacznik rozmowy (mikrofon przed suwakiem) zamykany na końcu: do
        # ostatniej chwili rozmówca jest w CUE, więc żadna przerwana sekwencja
        # nie zostawi „czekającego” z otwartym głosem innego uczestnika.
        glosy.sort(key=lambda k: 1 if (self.u.zrodla[c.wysylki[k.adres].zrodlo].klucz == MIKROFON
                                       and st.wartosc(adres_tap(k.adres)) == sciezki.TAP_PRE) else 0)
        pods = []
        ap = self.widok.adres_podsluchu()
        if w_zakresie(ap) or zakres is None:
            v = st.wartosc(ap)
            if v is NIEZNANY or float(v) > c.podsluch + TOL:
                pods = [Krok(ap, 0.0 if v is NIEZNANY else c.podsluch)]
        klucz = []
        for a, poziom in c.klucz.items():
            if not w_zakresie(a):
                continue
            v, t = st.wartosc(a), st.wartosc(adres_tap(a))
            zly_tap = poziom > 0 and (t is NIEZNANY or int(t) != sciezki.TAP_PRE)
            if v is NIEZNANY or float(v) > poziom + TOL or (zly_tap and float(v) > 0.0):
                klucz.append(Krok(a, 0.0))
        # Kolejność zamknięć: Main On (antena ma pierwszeństwo, rozdz. 7 pkt 2),
        # głośniki, klucz przyciszania (źródło wychodzi z Bus 5, zanim zmieni
        # się rozmowa), drogi rozmowy, muzyka, podsłuch.
        return lr + glosniki + klucz + glosy + muzyka + pods

    def _plan_otwarc(self, c: Cel, zakres=None) -> list[Krok]:
        st = self.stan
        w_zakresie = (lambda a: True) if zakres is None else (lambda a: a in zakres)
        mik = set(self.widok.adresy_sumy(MIKROFON))
        antena = [Krok(a, 1, 0) for a, v in c.lr.items()
                  if a in mik and v == 1 and w_zakresie(a) and st.wartosc(a) != 1]
        tapy, rozmowa, program = [], [], []
        for a, cw in c.wysylki.items():
            if not w_zakresie(a) or cw.poziom <= 0.0:
                continue
            at = adres_tap(a)
            t = st.wartosc(at)
            if t is NIEZNANY or int(t) != cw.tap:
                tapy.append(Krok(at, cw.tap))
            v = st.wartosc(a)
            if v is NIEZNANY or float(v) < cw.poziom - TOL:
                (rozmowa if cw.tap == sciezki.TAP_PRE else program).append((cw.zrodlo, Krok(a, cw.poziom, 0.0)))
        # Rozmowa: najpierw mikrofon (on wyznacza CUE), potem pozostali uczestnicy.
        rozmowa.sort(key=lambda para: 0 if para[0] == MIKROFON else 1)
        program.sort(key=lambda para: 0 if self.u.zrodla[para[0]].glos else 1)
        sumy = [Krok(a, 1, 0) for a, v in c.lr.items()
                if a not in mik and v == 1 and w_zakresie(a) and st.wartosc(a) != 1]
        # Najpierw antena, potem powroty (rozdz. 7): wysyłki rozmówcy, którego
        # Main On dopiero się otwiera, idą do innych powrotów po jego Main On.
        wchodzacy = {zr for zr in self._rozmowcy()
                     if any(k.adres in set(self.widok.adresy_sumy(zr)) for k in sumy)}
        po_sumie = [k for zr, k in program if zr in wchodzacy]
        program = [k for zr, k in program if zr not in wchodzacy]
        pods = []
        ap = self.widok.adres_podsluchu()
        if c.podsluch > 0.0 and (zakres is None or ap in zakres):
            v = st.wartosc(ap)
            if v is NIEZNANY or float(v) < c.podsluch - TOL:
                pods = [Krok(ap, c.podsluch, 0.0)]
        # Klucz przyciszania na samym końcu: źródło jest już w tej samej
        # rozmowie co słuchacz, więc zapora (klucz_ta_sama_rozmowa) go przepuści.
        klucz_tap, klucz = [], []
        for a, poziom in c.klucz.items():
            if poziom <= 0.0 or not w_zakresie(a):
                continue
            t = st.wartosc(adres_tap(a))
            if t is NIEZNANY or int(t) != sciezki.TAP_PRE:
                klucz_tap.append(Krok(adres_tap(a), sciezki.TAP_PRE))
            v = st.wartosc(a)
            if v is NIEZNANY or float(v) < poziom - TOL:
                klucz.append(Krok(a, poziom, 0.0))
        # Kolejność z rozdz. 7 i planu v21 (pkt 1): rozmowa, program do
        # rozmówców, podsłuch, Main On rozmówcy, jego głos do innych powrotów,
        # klucz przyciszania.
        return (tapy + antena + [k for _, k in rozmowa] + program + pods + sumy + po_sumie
                + klucz_tap + klucz)

    def _zmiana_profilu(self, adres: str, wartosc) -> bool:
        """Zgłoszenie zmienia profil: scena zawsze, inne ścieżki profilu tylko
        z wartością inną niż potwierdzona. Zgłoszenie własnego ochronnego
        zamknięcia (np. szyna zdjęta z Main LR, P02) nie jest zmianą z innego
        urządzenia ani nowym pełnym odczytem."""
        if not sciezki.zmienia_profil(adres):
            return False
        if adres.startswith(("/-snap/", "/snap/")):
            return True
        v = self.stan.wartosc(adres)
        return v is NIEZNANY or wartosc is None or not zgodne(v, wartosc)

    def _obca_zmiana_profilu(self) -> bool:
        """Czy w kolejce zgłoszeń czeka zmiana sceny albo routingu z innego klienta."""
        zebrane = []
        while True:
            try:
                zebrane.append(self._zgloszenia.get_nowait())
            except queue.Empty:
                break
        for z in zebrane:
            self._zgloszenia.put(z)
        return any(self._zmiana_profilu(a, v) for a, v in zebrane)

    def _sciagnij_suwaki(self, rozmowcy) -> list[str]:
        """Silnik ściąga suwak rozmówcy, który dostał CUE (decyzja 4).
        Zwraca rozmówców, których suwaka nie ściągnięto (trzymany ręką)."""
        trzymane = []
        for r in rozmowcy:
            if self.widok.suwak_na_dole(r) is True:
                continue
            pasek = self._pasek_zrodla(r)
            if pasek in self._dotyk:
                trzymane.append(r)
                continue
            ok = True
            try:
                for k in self.u.zrodla[r].kanaly:
                    ok = self._zapis(Krok(sciezki.fader(k), 0.0)) and ok
            except NaruszenieZapory:
                ok = False
            except BrakOdpowiedzi:
                self._utrata("brak odpowiedzi przy ściąganiu suwaka")
                ok = False
            if not ok:
                trzymane.append(r)
                continue
            if pasek is not None:
                self._suwak_ruch.pop(pasek, None)
                if self.powierzchnia is not None:
                    self.powierzchnia.ustaw_suwak(pasek, 0.0)
        return trzymane

    def _wykonaj_przejscie(self, c: Cel, zakres=None, sciagnij=()) -> WynikPrzejscia:
        if self._mikrofon_sprzed is not None:
            # Świadoma zmiana CUE/suwaka zastępuje dawny zamiar powrotu. Nie
            # przywracamy anteny sprzed trzymania po zmianie rozmowy.
            if zakres is None or self._adresy_mikrofonu().intersection(zakres):
                self._mikrofon_sprzed.update({a: 0 for a in self.widok.adresy_sumy(MIKROFON)})
                for a, cw in c.wysylki.items():
                    if cw.zrodlo == MIKROFON:
                        self._mikrofon_sprzed[a] = cw.poziom
                        if cw.tap is not None:
                            self._mikrofon_sprzed[adres_tap(a)] = cw.tap
                for a in self.widok.adresy_klucza(MIKROFON):
                    self._mikrofon_sprzed[a] = c.klucz.get(a, 0.0)
                self.widok.cue_chwilowe = c.cue
            chwilowy = self._cel_chwilowy()
            for a in self.widok.adresy_sumy(MIKROFON):
                c.lr[a] = 0
            for a, cw in c.wysylki.items():
                if cw.zrodlo == MIKROFON:
                    cw.poziom, cw.tap = chwilowy[a], chwilowy[adres_tap(a)]
                elif a in chwilowy:
                    # Muzyka adresata talkbacku zostaje przyciszona także wtedy,
                    # gdy w trakcie trzymania weszła na antenę albo z niej zeszła
                    # (SARA, suwak muzyki): wysyłka podąża za stanem, ale ciszej.
                    cw.poziom = chwilowy[a]
                    if cw.poziom > 0.0:
                        cw.tap = chwilowy.get(adres_tap(a), cw.tap)
            for a in self.widok.adresy_klucza(MIKROFON):
                c.klucz[a] = 0.0
        elif self.widok.cue_chwilowe is not None:
            # Świadome wyjście z CUE po przerwaniu kaszlu musi zwolnić również
            # zachowany znacznik, zanim zapora sprawdzi Main On rozmówcy.
            self.widok.cue_chwilowe = c.cue
        wynik = self._wykonaj_przejscie_plan(c, zakres, sciagnij)
        if not wynik.ok and self._mikrofon_sprzed is not None:
            self._przerwij_kaszel()
        elif wynik.ok and self._mikrofon_sprzed is None and self.widok.cue_chwilowe is not None:
            self._zwolnij_nakladke_cue(c.cue)
        return wynik

    def _wykonaj_przejscie_plan(self, c: Cel, zakres=None, sciagnij=()) -> WynikPrzejscia:
        zamk = self._plan_zamkniec(c, zakres)
        if zamk:
            self._zamknij(zamk)
            oczek = {k.adres: k.wartosc for k in zamk}
            zle = self._dwa_odczyty(oczek) if self.stan.polaczony else list(oczek)
            if zle and self.stan.polaczony:
                # Ponowić wyłącznie brakujące zamknięcia.
                self._zamknij([k for k in zamk if k.adres in zle])
                zle = self._dwa_odczyty({a: oczek[a] for a in zle}) if self.stan.polaczony else zle
            if zle:
                self._dz("przejscie-niepelne", "zamkniecia", zle)
                return WynikPrzejscia(False, "zamkniecia", utrata=not self.stan.polaczony, niepotwierdzone=zle)
        if self._obca_zmiana_profilu():
            self._dz("przejscie-przerwane", "zmiana z innego klienta")
            return WynikPrzejscia(False, "obce")
        trzymane = self._sciagnij_suwaki(sciagnij) if self.stan.polaczony else list(sciagnij)
        if not self.stan.polaczony:
            return WynikPrzejscia(False, "zamkniecia", utrata=True, trzymane=trzymane)
        otw = self._plan_otwarc(c, zakres)
        if otw and self._rozbrojone():
            # L01: przy utraconym kontrolerze zamknięcia tak, otwarcia nie.
            self._dz("przejscie-niepelne", "kontroler rozbrojony")
            return WynikPrzejscia(False, "rozbrojony", trzymane=trzymane)
        if otw:
            wynik = self._otworz(otw)
            if not wynik.ok:
                self._dz("przejscie-niepelne", "otwarcia", wynik.niepotwierdzone)
                return WynikPrzejscia(False, "otwarcia", utrata=wynik.utrata, powod=wynik.powod,
                                      niepotwierdzone=[k.adres for k in wynik.niepotwierdzone], trzymane=trzymane)
            zle = self._dwa_odczyty({k.adres: k.wartosc for k in otw})
            if zle:
                self._dz("przejscie-niepelne", "weryfikacja", zle)
                return WynikPrzejscia(False, "weryfikacja", utrata=not self.stan.polaczony,
                                      niepotwierdzone=zle, trzymane=trzymane)
        odsluch_ok = True
        kroki = self._bez_zbednych(c.odsluch, self.widok)
        if kroki:
            odsluch_ok = self._zamknij(kroki).ok
        return WynikPrzejscia(True, trzymane=trzymane, odsluch_ok=odsluch_ok)

    def _niepowodzenie(self, w: WynikPrzejscia) -> None:
        if w.utrata or not self.stan.polaczony:
            self.powiedz(self.t("stan_nieznany"), Priorytet.BEZPIECZENSTWO, "przejscie")
        elif w.etap == "obce":
            self.powiedz(self.t("przejscie_przerwane_obce"), Priorytet.BEZPIECZENSTWO, "przejscie")
        elif w.etap == "rozbrojony":
            self.powiedz(self.t("kontroler_otwieranie"), Priorytet.BEZPIECZENSTWO, "przejscie")
        else:
            self.powiedz(self.t("przejscie_niepelne"), Priorytet.BEZPIECZENSTWO, "przejscie")

    def _dopisz_odsluch(self, tekst: str, w: WynikPrzejscia) -> str:
        if not w.odsluch_ok:
            tekst += ". " + self.t("odsluch_niepotwierdzony")
        return tekst

    # ======================================================================
    # wejście zdarzeń
    # ======================================================================
    def zgloszenie(self, adres: str, wartosc) -> None:
        """Wywoływane z wątku sieciowego przy zgłoszeniu zmiany przez /xremote."""
        self._zgloszenia.put((adres, wartosc))
        s = self._solo_kaszlu
        if (s is not None and adres.startswith("/-stat/solosw/")
                and not zgodne(s.oczekiwane.get(adres, self.stan.wartosc(adres)), wartosc)
                and not zgodne(self.stan.wyslane(adres), wartosc)):
            s.obca_zmiana = True  # także obcy impuls ON -> OFF między odczytami
        # Sam odczyt końcowy nie wykryje szybkiego obcego ON -> OFF. Wątek
        # sieciowy tylko unieważnia migawkę, zamknięcia robi wątek roboczy.
        g = self._glosniki_talkback
        if (g is not None and adres in self.widok.adresy_glosnikow()
                and wartosc != 0 and not zgodne(self.stan.wyslane(adres), wartosc)):
            g.obca_zmiana = True

    def zglos(self, zdarzenie: tuple) -> bool:
        """Zdarzenie z powierzchni. Naciśnięcie w trakcie trwającej operacji
        nie jest kolejnym przełączeniem: mostek mówi „czekam na mikser”."""
        rodzaj = zdarzenie[0]
        if self._nauka_od is None or self._tor_emisji.tryb_miksu:
            with self._blokada_emisji:
                miks = self._tor_emisji.akcja_miksu(zdarzenie)
                if miks is not None:
                    if rodzaj == "klawisz":
                        teraz = self.zegar()
                        ost = self._ostatnie_nacisniecie.get(zdarzenie, float("-inf"))
                        if teraz - ost < self.debounce_s:
                            return False
                        self._ostatnie_nacisniecie[zdarzenie] = teraz
                    self._nauka_od = None
                    self._tor_emisji.zlec(*miks)
                    return True
        if self._nauka_od is not None or (rodzaj == "klawisz" and zdarzenie[1] == nauka.KLAWISZ_NAUKI):
            if self._nauka_klawiszy(zdarzenie):
                return True
        if rodzaj == "jog" or (rodzaj == "klawisz" and zdarzenie[1] in KLAWISZE_EMISJI):
            # Playout nie czeka na blokadę/odczyt MR18. Osobna serializacja
            # tylko krótkiego zlecenia, bez jakiegokolwiek I/O sieciowego.
            with self._blokada_emisji:
                teraz = self.zegar()
                if rodzaj == "klawisz":
                    ost = self._ostatnie_nacisniecie.get(zdarzenie, float("-inf"))
                    if teraz - ost < self.debounce_s:
                        return False
                    self._ostatnie_nacisniecie[zdarzenie] = teraz
                    self._klawisz(zdarzenie[1])
                else:
                    self._tor_emisji.zlec("ruch", int(zdarzenie[1]), jog=True)
            return True
        if rodzaj in PRZYCISKI:
            teraz = self.zegar()
            ost = self._ostatnie_nacisniecie.get(zdarzenie)
            if ost is not None and teraz - ost < self.debounce_s:
                return False    # drganie styku
            self._ostatnie_nacisniecie[zdarzenie] = teraz
            # „Czekam na mikser” tylko wtedy, gdy trwa inne naciśnięcie;
            # okresowy odczyt (tick) jest krótki, więc na niego czekamy.
            with self._zmiana:
                if self._zmiana_w_toku:
                    self.powiedz(self.t("czekam"), Priorytet.STAN, "czekam", dzwiek=True)
                    return False
                self._zmiana_w_toku = True
            try:
                with self._wykonuje:
                    self.obsluz(zdarzenie)
            finally:
                self._zmiana_w_toku = False
            return True
        with self._wykonuje:
            self.obsluz(zdarzenie)
        return True

    def _nauka_klawiszy(self, z: tuple) -> bool:
        """Tryb nauki klawiszy (Michał, 24.10.2026, mostek.nauka). Klawisz
        nauki włącza i wyłącza tryb. W trybie przycisk, gałka i kółko mówią
        tylko nazwę i nic nie robią, a dziennik dostaje numer MIDI. Suwak,
        dotyk, puszczenie kaszlu i utrata kontrolera idą zwykłą drogą.
        Zwraca True, gdy zdarzenie obsłużył tryb nauki. Bez odczytu miksera."""
        rodzaj = z[0]
        teraz = self.zegar()
        przelacznik = rodzaj == "klawisz" and z[1] == nauka.KLAWISZ_NAUKI
        if not przelacznik and (self._nauka_od is None or rodzaj not in nauka.ZDARZENIA_NAUKI):
            return False
        if rodzaj in PRZYCISKI:
            ost = self._ostatnie_nacisniecie.get(z, float("-inf"))
            if teraz - ost < self.debounce_s:
                return True     # drganie styku: w nauce też nic nie robi
            self._ostatnie_nacisniecie[z] = teraz
        if przelacznik:
            wlacz = self._nauka_od is None
            self._nauka_od = teraz if wlacz else None
            log.info("nauka klawiszy %s", "włączona" if wlacz else "wyłączona")
            self.mowa.powiedz(nauka.TEKST_START if wlacz else nauka.TEKST_KONIEC,
                              Priorytet.STAN, "nauka")
            return True
        self._nauka_od = teraz
        tekst, opis = nauka.opisz(self.u, z)
        log.info("nauka klawiszy: %s, mówi: %s", opis, tekst)
        self.mowa.powiedz(tekst, Priorytet.INFORMACJA, "nauka")
        return True

    def _koniec_nauki_po_czasie(self) -> None:
        od = self._nauka_od
        if od is not None and self.zegar() - od > nauka.LIMIT_BEZCZYNNOSCI_S:
            self._nauka_od = None
            log.info("nauka klawiszy wyłączona po minucie bez naciśnięcia")
            self.mowa.powiedz(nauka.TEKST_KONIEC_CZAS, Priorytet.STAN, "nauka")

    def obsluz(self, z: tuple) -> None:
        rodzaj = z[0]
        if rodzaj == "jog" or (rodzaj == "klawisz" and z[1] in KLAWISZE_EMISJI):
            self.zglos(z)
            return
        # Zdarzenie z powierzchni (nie sygnał utraty albo powrotu kontrolera).
        self._w_zdarzeniu = rodzaj not in ("kontroler", "kontroler_powrot")
        try:
            # L02: decyzja tylko na świeżym odczycie torów krytycznych.
            if rodzaj not in ("dotyk", "kontroler", "kontroler_powrot") and not (
                    rodzaj == "klawisz" and z[1] in KLAWISZE_BEZ_MIKSERA):  # POPRAWKA F5: bez odczytu
                self._zapewnij_swiezosc()
            if rodzaj == "przycisk":
                self._przycisk_paska(int(z[1]), int(z[2]))
            elif rodzaj == "galka_wcisnij":
                self.status_paska(int(z[1]))
            elif rodzaj == "galka":
                self.obrot_galki(int(z[1]), int(z[2]))
            elif rodzaj == "suwak":
                self.ruch_suwaka(int(z[1]), float(z[2]))
            elif rodzaj == "dotyk":
                self.dotyk_suwaka(int(z[1]), bool(z[2]))
            elif rodzaj == "klawisz":
                self._klawisz(str(z[1]))
            elif rodzaj == "puszczenie":
                self._puszczenie_przycisku(int(z[1]), int(z[2]))
            elif rodzaj == "kontroler":
                self.utrata_kontrolera(str(z[1]) if len(z) > 1 else "")
            elif rodzaj == "kontroler_powrot":
                self.powrot_kontrolera(str(z[1]) if len(z) > 1 else "")
        finally:
            self._w_zdarzeniu = False
            self._aktualizuj_liczniki()
            self._odswiez_powierzchnie()

    def _klawisz(self, nazwa: str) -> None:
        akcje = {
            "F1_mikrofon": self.przelacz_mikrofon,
            "F2_status": self.status,
            "F3_koniec_rozmowy": self.f3_koniec_rozmowy,
            "F4_tryb_informacji": self.f4_tryb_informacji,
            "F5_ostatni_komunikat": self.f5_ostatni_komunikat,
            "F8_odczytaj_powierzchnie": self.f8_powierzchnia,
            "glosniki_wlacz": lambda: self.glosniki(True),
            "glosniki_wylacz": lambda: self.glosniki(False),
            "sluchaj_programu": self.sluchaj_programu,
            "sluchaj_rozmowy": self.sluchaj_rozmowy,
            "koniec_pfl": self.koniec_pfl,
            "transport_play": self.transport_play,
            "transport_stop": self.transport_stop,
            "transport_nastepny": self.transport_nastepny,
            "F6_co_gra": lambda: self._tor_emisji.zlec("co_gra"),
            "F7_automat": lambda: self._tor_emisji.zlec("automat"),
            "channel_lewo_automat": lambda: self._tor_emisji.zlec("automat"),
            "emisja_pozostalo": lambda: self._tor_emisji.zlec("pozostalo"),
            "bank_lewo_odtwarzacz": lambda: self._tor_emisji.zlec("odtwarzacz"),
            "emisja_gora": lambda: self._tor_emisji.zlec("ruch", -1),
            "emisja_dol": lambda: self._tor_emisji.zlec("ruch", 1),
            "emisja_znacznik": lambda: self._tor_emisji.zlec("znacznik"),
            "alarm_ciszy": self.przelacz_alarm_ciszy,
        }
        akcja = akcje.get(nazwa)
        if akcja is not None:
            akcja()
        elif nazwa.endswith("_wolny"):
            self.powiedz(self.t("klawisz_wolny"), Priorytet.INFORMACJA)
        else:
            self.powiedz(self.t("funkcja_techniczna"), Priorytet.INFORMACJA)

    # ======================================================================
    # F4 i F5: tryb informacji zwrotnej i powtórzenie komunikatu
    # ======================================================================
    def f4_tryb_informacji(self) -> None:
        """F4: tryb cyklicznie MOWA -> DZWIEKI -> DZWIEKI_Z_MOWA -> MOWA, zapis
        w ustawieniach, nowy tryb ZAWSZE mową (z pominięciem trybu). Bez
        odczytu i zapisu miksera."""
        tryb, zapisany = self.informacja.przelacz()
        tekst = self.t({"mowa": "tryb_mowa", "dzwieki": "tryb_dzwieki",
                        "dzwieki_z_mowa": "tryb_dzwieki_z_mowa"}[tryb.value])
        if not zapisany:
            tekst += ". " + self.t("tryb_niezapisany")
        self.mowa.powiedz(tekst, Priorytet.STAN, "tryb")  # POPRAWKA F4: tryb zawsze mową

    def f5_ostatni_komunikat(self) -> None:
        """F5: powtarza mową ostatni komunikat stanu, także taki, który w trybie
        DZWIEKI zabrzmiał tylko dźwiękiem. Bez odczytu i zapisu miksera."""
        if self._ostatni is None:
            self.mowa.powiedz(self.t("brak_powtorzenia"), Priorytet.INFORMACJA, "powtorz")
            return
        self.mowa.powiedz(self._ostatni, Priorytet.STAN, "powtorz")  # POPRAWKA F5: tylko mowa

    def _przycisk_paska(self, pasek: int, indeks: int) -> None:
        """Mapa paska v20: REC, SOLO, MUTE, SELECT (rozdz. 8, „Mapa paska B”)."""
        opis = self.u.paski.get(pasek) or {}
        zr = opis.get("zrodlo")
        if not zr:
            self.powiedz(self.t("pasek_wolny"), Priorytet.INFORMACJA)
            return
        if indeks == 0:
            rec = opis.get("rec")
            if rec == "antena_mikrofonu":
                self.przelacz_mikrofon()
            elif rec == "alarm_ciszy":
                self.przelacz_alarm_ciszy()     # Michał 21.10.2026: REC paska 1
            elif rec == "suwakiem":
                self.powiedz(self.t("na_antene_suwakiem"), Priorytet.INFORMACJA)
            else:
                self.powiedz(self.t("przycisk_wolny"), Priorytet.INFORMACJA)
        elif indeks == 2 and opis.get("mute") == "kaszel":
            self.kaszel_wcisniety()
        elif indeks == 2 and opis.get("mute") == "talkback":
            self.talkback_wcisniety(zr)
        elif indeks == 3:
            sel = opis.get("select")
            if sel == "cue":
                self.przelacz_cue(zr)
            elif sel == "pfl":
                self.przelacz_pfl(zr)
            elif sel == "antena_mikrofonu":
                self.przelacz_mikrofon()    # Michał 21.10.2026: mikrofon na SELECT paska 1
            elif sel == "bez_cue":
                self.powiedz(self.t("mikrofon_bez_cue"), Priorytet.INFORMACJA)
            else:
                self.powiedz(self.t("przycisk_wolny"), Priorytet.INFORMACJA)
        else:
            self.powiedz(self.t("przycisk_wolny"), Priorytet.INFORMACJA)

    # ======================================================================
    # przełącznik mikrofonu (rozdz. 8, „Co mówi NVDA”)
    # ======================================================================
    def przelacz_mikrofon(self) -> None:
        # Hold wykonuje osobny wątek. Zatrzymujemy wyłącznie jego komunikaty
        # do chwili ogłoszenia wyniku mikrofonu, nigdy przejście ani TCP.
        self._hold_przejscie = True
        try:
            self._przelacz_mikrofon()
        finally:
            if self._tor_emisji._hold_cel is not None:
                self._obserwuj_hold()
            with self._odbior_emisji:
                self._hold_przejscie = False
            self.odbierz_emisje()

    def _przelacz_mikrofon(self) -> None:
        if self._mikrofon_sprzed is not None:
            talkback = self._glosniki_talkback is not None
            self._przerwij_kaszel(oglos=talkback)
            if not talkback:
                self._wylacz_mikrofon()
            return
        stan = self.widok.suma(MIKROFON)
        if stan is NIEZNANY or not self._gotowy():
            self.powiedz(self.t("stan_nieznany_wylaczam_mikrofon"), Priorytet.BEZPIECZENSTWO)
            self._wylacz_mikrofon()
        elif stan:
            self._wylacz_mikrofon()
        else:
            self._wlacz_mikrofon()

    def _komunikat_mikrofonu(self, z_czasem: bool = False) -> str:
        stan = self.widok.suma(MIKROFON)
        if stan is NIEZNANY:
            return self.t("stan_nieznany")
        if stan is False and self._kaszel is not None:
            return self.t("mikrofon_kaszel")
        if stan is False and self._talkback:
            do = self.t("talkback_obaj") if len(self._talkback) > 1 else self.u.odbiorcy[
                self.widok.odbiorca(next(iter(self._talkback)))].do
            return self.t("mikrofon_talkback", do=do)
        czas = self._czas_licznika("mikrofon") if (z_czasem and stan is True) else None
        if czas:
            tekst = self.t("mikrofon_licznik", **czas)
        else:
            tekst = self.t("mikrofon_stan", stan=self.u.stan_slowo(bool(stan), "m")).wariant(
                "wlaczony" if stan else "wylaczony")
        if stan is True and self.widok.fader_db(MIKROFON) == float("-inf"):
            tekst += ", " + opis_fadera(self.u, float("-inf"))
        return tekst

    def _wlacz_mikrofon(self) -> None:
        if self._rozbrojone():
            self.powiedz(self.t("mikrofon_nie_wlaczony", powod=self.t("powod_kontroler")),
                         Priorytet.BEZPIECZENSTWO, "przelacznik")
            return
        cue = self.widok.cue_zbior()
        if cue is NIEZNANY or cue:
            # Decyzja 6: przełącznik przy dowolnym CUE nie otwiera anteny.
            self.powiedz(self.t("najpierw_zwolnij_cue"), Priorytet.BEZPIECZENSTWO, "przelacznik")
            return
        # Tylko tory mikrofonu i głośniki: najpierw potwierdzone wyciszenie
        # głośników, potem Main On mikrofonu, potem powroty rozmówców (rozdz. 6a i 7).
        zakres = self._adresy_mikrofonu() | set(self.widok.adresy_glosnikow())
        self._zlec_hold(True)  # HOLD_ZAMIAR: przed potwierdzeniami miksera
        w = self._wykonaj_przejscie(self.cel(frozenset(), True), zakres=zakres)
        if w.ok:
            self.powiedz(self._komunikat_mikrofonu(), Priorytet.STAN, "przelacznik", dzwiek=True)
            return
        if not self.stan.polaczony:
            powod = self.t("powod_brak_lacznosci")
        elif self.widok.glosniki_wyciszone() is not True:
            powod = self.t("powod_glosniki")
        elif w.etap == "rozbrojony":
            powod = self.t("powod_kontroler")
        elif self.zapora.profil_blokuje:
            powod = self.t("powod_profil")
        elif w.etap == "obce":
            powod = self.t("przejscie_przerwane_obce").lower()
        else:
            powod = self.t("powod_niepotwierdzone")
        self.powiedz(self.t("mikrofon_nie_wlaczony", powod=powod), Priorytet.BEZPIECZENSTWO, "przelacznik")
        if self.widok.suma(MIKROFON) is not False:
            self.powiedz(self.t("mikrofon_moze_byc_wlaczony"), Priorytet.BEZPIECZENSTWO, "przelacznik-uwaga")

    def _adresy_mikrofonu(self) -> set[str]:
        """Main On mikrofonu, jego wysyłki do powrotów i do klucza przyciszania."""
        a = set(self.widok.adresy_sumy(MIKROFON))
        for odb in self.u.odbiorcy:
            a.update(self.widok.adresy_wysylki(MIKROFON, odb))
        a.update(self.widok.adresy_klucza(MIKROFON))
        return a

    def _wylacz_mikrofon(self) -> None:
        """Wyłączenie działa zawsze: Main On mikrofonu, potem jego wysyłki do
        programu rozmówców. Rozmowa na CUE zostaje (mikrofon jest w rozmowie)."""
        kroki = self.kroki_sumy(MIKROFON, False)
        if self._gotowy():
            cue = self.widok.cue_zbior()
            if cue is not NIEZNANY:
                kroki = self._plan_zamkniec(self.cel(cue, False), zakres=self._adresy_mikrofonu())
        wynik = self._zamknij(kroki)
        if wynik.ok and (self.widok.suma(MIKROFON) is False or not self._gotowy()):
            # Każdy krok potwierdzony odczytem z miksera (także przy stanie NIEZNANY).
            self.powiedz(self._z_mute_act(self.t("mikrofon_stan", stan=self.u.stan_slowo(False, "m"))
                                          .wariant("wylaczony")),
                         Priorytet.STAN, "przelacznik", dzwiek=True)
            return
        # Nie mówimy „wyłączony” bez potwierdzenia (kryterium odbioru 2).
        sumy = [s for s in wynik.niepotwierdzone if s.adres.endswith("/mix/lr")]
        if sumy or self.widok.suma(MIKROFON) is not False:
            self.powiedz(self.t("mikrofon_moze_byc_wlaczony"), Priorytet.BEZPIECZENSTWO, "przelacznik")
        else:
            self.powiedz(self._komunikat_mikrofonu() + ". " + self.t("synchronizacja_brak"), Priorytet.STAN)

    # ======================================================================
    # przycisk kaszlu: MUTE na pasku mikrofonu (plan v21, pkt 2, decyzja 2)
    # ======================================================================
    def _migawka_mikrofonu(self) -> dict:
        a = self._adresy_mikrofonu()
        a |= {adres_tap(x) for x in a if x.endswith("/level")}
        return {x: self.stan.wartosc(x) for x in a}

    def _rozpocznij_chwilowy(self) -> bool:
        if self._mikrofon_sprzed is not None:
            return True
        cue, dane = self.widok.cue_zbior(), self._migawka_mikrofonu()
        if cue is NIEZNANY or any(v is NIEZNANY for v in dane.values()):
            return False
        self._mikrofon_sprzed = dane
        self.widok.cue_chwilowe = cue
        return True

    def _zwolnij_nakladke_cue(self, cue) -> None:
        # Po awaryjnym zamknięciu mikrofonu rozmówcy nadal mogą być na CUE.
        # Nie zmieniamy ich torów ani diod tylko dlatego, że zgasł znacznik
        # mikrofonowy. Nakładka znika, gdy potwierdzone trasy znowu go wyrażają.
        self.widok.cue_chwilowe = None
        if self.widok.cue_zbior() != cue:
            self.widok.cue_chwilowe = cue

    def _flagi_chwilowe(self) -> None:
        self.widok.talkback = frozenset(self._talkback)
        self.widok.kaszel = self._kaszel is not None

    def _adresaci_przyciszenia(self) -> set[str]:
        """Adresaci talkbacku, u których mostek ma przyciszyć muzykę: tylko gdy
        ustawienie pozwala. Kaszel niczego nie dokłada ani nie zdejmuje: ma
        własne, ostrzejsze zamknięcie samego mikrofonu."""
        if not self._talkback or not self.u.przyciszenie_muzyki_talkback:
            return set()
        return set(self._talkback)

    def _muzyka_chwilowa(self, adresaci, przyciszona: bool) -> dict:
        """Wysyłki muzyki do powrotów adresatów: muzyka, która jest na antenie,
        dostaje poziom bazowy plus przyciszenie z CUE (`przyciszona`), a przy
        powrocie dokładnie tę wartość, którą zapamiętała migawka. Muzyka poza
        anteną zostaje zamknięta. Punkt pobrania POST, jak w zwykłym celu.

        Migawka trzyma poziom sprzed przyciszenia, więc powrót nie przelicza
        go z decybeli i oddaje bajt w bajt to, co zastał mostek. Muzyka, której
        Main On zmienił się w trakcie, nie wraca z migawki, tylko idzie za
        bieżącym stanem (wejście = poziom bazowy, zejście = zamknięta).

        Rozmówca z CUE jest pomijany: jego muzyką rządzi zwykły cel, który i
        tak ją przycisza. Nieznany Main On muzyki: wysyłka zostaje, jaka jest.
        """
        cel: dict = {}
        for r in adresaci:
            if self.widok.cue_chwilowe is not None and r in self.widok.cue_chwilowe:
                continue
            odb = self.widok.odbiorca(r)
            if odb is None:
                continue
            for zr in self.widok.muzyka():
                suma = self.widok.suma(zr)
                if suma is NIEZNANY:
                    continue
                baza = self.u.poziom_bazowy(zr, odb)
                for a in self.widok.adresy_wysylki(zr, odb):
                    if suma is not True:
                        p = 0.0
                    elif przyciszona:
                        p = self._wl(baza + self.u.przyciszenie_muzyki_db)
                    else:
                        sprzed = self._muzyka_sprzed.get(a)
                        p = sprzed if sprzed is not None and sprzed > 0.0 else self._wl(baza)
                    cel[a] = p
                    if p > 0.0:
                        cel[adres_tap(a)] = sciezki.TAP_POST
        return cel

    def _cel_chwilowy(self) -> dict:
        """Mikrofon i, przy talkbacku, muzyka w powrocie adresata.

        Mikrofon do adresata talkbacku dostaje poziom jak w rozmowie na CUE
        (`_mikrofon_w_rozmowie_db`: poziom bazowy plus dB suwaka mikrofonu,
        najwyżej plus 10 dB), bo rozmówca ma go słyszeć tak samo głośno jak
        na antenie (zgłoszenie Michała z 26.10.2026). CUE, PFL, antena
        rozmówców i program nieadresatów bez zmian.

        Muzyka adresata wraca do poziomu ze zwykłego celu dla BIEŻĄCEGO stanu
        (nie z migawki), więc muzyka, która w trakcie zeszła z anteny, zostaje
        po puszczeniu zamknięta, a ta, która weszła, dostaje poziom bazowy.
        """
        cel = dict(self._mikrofon_sprzed)
        adresaci = self._adresaci_przyciszenia() if self._kaszel is None or self._talkback else set()
        if not (self._kaszel is not None or self._talkback):
            # Puszczony ostatni adresat: muzyka do zwykłego celu.
            cel.update(self._muzyka_chwilowa(self._muzyka_przyciszona, przyciszona=False))
            return cel
        for a in self._adresy_mikrofonu():
            cel[a] = 0
        if self._kaszel is None:
            for r in self._talkback:
                odb = self.widok.odbiorca(r)
                p = poziom_db_na_float(self._mikrofon_w_rozmowie_db(self.u.poziom_bazowy(MIKROFON, odb)))
                for a in self.widok.adresy_wysylki(MIKROFON, odb):
                    cel[a], cel[adres_tap(a)] = p, sciezki.TAP_PRE
        # Muzyka adresatów zostaje przyciszona także na czas kaszlu w środku
        # talkbacku: wraca dopiero z puszczeniem danego adresata.
        cel.update(self._muzyka_chwilowa(self._muzyka_przyciszona - adresaci, przyciszona=False))
        cel.update(self._muzyka_chwilowa(adresaci, przyciszona=True))
        return cel

    def _wykonaj_chwilowy(self, cel: dict) -> WynikPrzejscia:
        """Zamknij przed zmianą tap, dwa odczyty, dopiero otwieraj. Przywraca
        także tap zamkniętych wysyłek, którego zwykły cel CUE nie potrzebuje.

        Wysyłki mikrofonu zawsze idą przez zero (izolacja toru). Wysyłki muzyki
        adresata obniżamy wprost do poziomu docelowego, jak zwykły cel CUE:
        przejście przez zero urwałoby rozmówcy muzykę na czas sekwencji.
        """
        sumy = self.widok.adresy_sumy(MIKROFON)
        mikrofon = set(self._mikrofon_sprzed or {})
        poziomy = sorted(a for a in cel if a.endswith("/level"))
        zamknij = [Krok(a, 0) for a in sumy if cel[a] == 0 and self.stan.wartosc(a) != 0]
        for a in poziomy:
            v, t = self.stan.wartosc(a), self.stan.wartosc(adres_tap(a))
            tap_celu = cel.get(adres_tap(a))
            zly_tap = tap_celu is not None and t != tap_celu
            if v is NIEZNANY:
                zamknij.append(Krok(a, 0.0))
            elif float(v) <= 0:
                continue
            elif a in mikrofon:
                if not zgodne(v, cel[a]) or zly_tap:
                    zamknij.append(Krok(a, 0.0))
            elif zly_tap or float(cel[a]) <= 0.0:
                zamknij.append(Krok(a, 0.0))
            elif float(v) > float(cel[a]) + TOL:
                zamknij.append(Krok(a, cel[a]))   # muzyka ciszej bez przerwy w dźwięku
        if zamknij:
            self._zamknij(zamknij)
            oczek = {k.adres: k.wartosc for k in zamknij}
            zle = self._dwa_odczyty(oczek) if self.stan.polaczony else list(oczek)
            if zle and self.stan.polaczony:
                self._zamknij([k for k in zamknij if k.adres in zle])
                zle = self._dwa_odczyty(oczek) if self.stan.polaczony else zle
            if zle:
                return WynikPrzejscia(False, "zamkniecia", niepotwierdzone=zle)
        # Odczyt przed otwarciem wykrywa też cudzą zmianę głośników albo CUE
        # w trakcie sekwencji, nie tylko zmianę routingu zgłoszoną przez OSC.
        migawka = self._mikrofon_sprzed
        self._odczyt_krytyczny()
        if migawka is not self._mikrofon_sprzed or not self._gotowy() or self._obca_zmiana_profilu():
            return WynikPrzejscia(False, "obce", utrata=not self.stan.polaczony)
        tapy = [Krok(a, v) for a, v in cel.items() if a.endswith("/tap") and self.stan.wartosc(a) != v]
        antena = [Krok(a, cel[a], 0) for a in sumy if cel[a] != 0 and self.stan.wartosc(a) != cel[a]]
        klucz = set(self.widok.adresy_klucza(MIKROFON))
        wysylki = [Krok(a, cel[a], 0.0) for a in sorted(poziomy, key=lambda a: a in klucz)
                   if cel[a] > 0 and not zgodne(self.stan.wartosc(a), cel[a])]
        otworz = tapy + antena + wysylki
        w = self._otworz(otworz)
        if not w.ok:
            return WynikPrzejscia(False, "otwarcia", powod=w.powod, utrata=w.utrata)
        zle = self._dwa_odczyty(cel)
        if self._glosniki_talkback is not None:
            zle += self._dwa_odczyty({a: 0 for a in self.widok.adresy_glosnikow()})
        return WynikPrzejscia(not zle, "weryfikacja" if zle else "", niepotwierdzone=zle,
                              utrata=not self.stan.polaczony)

    def _zapamietaj_muzyke(self, adresaci) -> None:
        """Poziomy wysyłek muzyki sprzed przyciszenia, raz na adresata.
        Nieznanej wartości nie zapamiętujemy: powrót policzy ją z celu."""
        for r in adresaci:
            odb = self.widok.odbiorca(r)
            if odb is None:
                continue
            for zr in self.widok.muzyka():
                for a in self.widok.adresy_wysylki(zr, odb):
                    if a in self._muzyka_sprzed:
                        continue
                    v = self.stan.wartosc(a)
                    if v is not NIEZNANY:
                        self._muzyka_sprzed[a] = float(v)

    def _zmien_chwilowy(self) -> bool:
        if self._mikrofon_sprzed is None:
            return False
        powrot = not self._talkback and self._kaszel is None
        adresaci = self._adresaci_przyciszenia()
        self._zapamietaj_muzyke(adresaci - self._muzyka_przyciszona)
        cel = self._cel_chwilowy()
        self._flagi_chwilowe()
        w = self._wykonaj_chwilowy(cel)
        if not w.ok:
            powod = (self.t("powod_brak_lacznosci") if not self.stan.polaczony else
                     self.t("powod_glosniki") if self.widok.glosniki_wyciszone() is not True else
                     self.t("powod_profil") if self.zapora.profil_blokuje else
                     w.powod or self.t("powod_niepotwierdzone"))
            self._przerwij_kaszel(oglos=self._glosniki_talkback is not None)
            if self._zamkniecia_chwilowe_zalegle:
                powod = self.t("powod_niepotwierdzone")
            if powrot:
                self.powiedz(self.t("mikrofon_nie_wlaczony", powod=powod),
                             Priorytet.BEZPIECZENSTWO, "przelacznik")
            else:
                self._niepowodzenie(w)
            return False
        if self._glosniki_talkback is not None and self._glosniki_talkback.obca_zmiana:
            self._przerwij_kaszel()
            return False
        # Zamiar przywrócenia muzyki obejmuje tylko potwierdzone przyciszenia.
        self._muzyka_przyciszona = set(adresaci)
        if powrot:
            self._mikrofon_sprzed = None
            self._muzyka_przyciszona.clear()
            self._muzyka_sprzed.clear()
            self._zwolnij_nakladke_cue(self.widok.cue_chwilowe)
        return True

    def _solo_mikrofonu(self) -> set[str]:
        return {sciezki.solo(k) for k in self.u.zrodla[MIKROFON].kanaly}

    def _odczytaj_solo_kaszlu(self) -> dict | None:
        """Świeża migawka odsłuchu, także bez zgłoszeń /xremote."""
        adresy = sorted({sciezki.solo(k) for z in self.u.zrodla.values() for k in z.kanaly}
                        | {sciezki.SOLO_MAIN_LR})
        try:
            dane = self.klient.odczytaj_wiele(adresy)
        except BrakOdpowiedzi:
            self._solo_kaszlu = None  # nie odkładaj powrotu do następnej sesji miksera
            self._utrata("brak odpowiedzi przy odczycie solo kaszlu")
            return None
        s = self._solo_kaszlu
        if s is not None and any(not zgodne(v, s.oczekiwane.get(a)) for a, v in dane.items()):
            s.obca_zmiana = True
        for a, v in dane.items():
            self.stan.potwierdz(a, v, self.zegar())
        return dane

    def _zapis_solo_kaszlu(self, s: SoloKaszlu, adres: str, wartosc: int) -> bool:
        """Wąska zapora: tylko solo mikrofonu i tylko bieżąca migawka kaszlu.
        Bez Main LR, wysyłek, Bus 6 czy solo rozmówców, także przy błędnym celu."""
        if (s is not self._solo_kaszlu or adres not in self._solo_mikrofonu()
                or adres not in s.sprzed or wartosc not in (0, s.sprzed[adres])):
            raise NaruszenieZapory(self.t("odsluch_niepotwierdzony"))
        if s.obca_zmiana:
            return False
        s.oczekiwane[adres] = wartosc
        self._zapisuje_solo_kaszlu = True
        try:
            return self._zapis(Krok(adres, wartosc))
        finally:
            self._zapisuje_solo_kaszlu = False

    def _zdejmij_solo_kaszlu(self) -> None:
        dane = self._odczytaj_solo_kaszlu()
        if dane is None or self._kaszel is None:
            return
        mikrofon = self._solo_mikrofonu()
        if not any(dane.get(a) == 1 for a in mikrofon):
            return
        # Decyzja Michała 25.10.2026: zdejmij także jedyne solo mikrofonu.
        # PHONES wraca wtedy na program; nie otwieraj żadnego zastępczego solo.
        s = SoloKaszlu({a: dane[a] for a in mikrofon}, dict(dane))
        self._solo_kaszlu = s
        ok = True
        try:
            for a, v in sorted(s.sprzed.items()):
                if v == 1:
                    ok = self._zapis_solo_kaszlu(s, a, 0) and ok
            zle = self._dwa_odczyty({a: 0 for a in s.sprzed})
            ok = ok and not zle and not s.obca_zmiana
        except BrakOdpowiedzi:
            self._solo_kaszlu = None
            self._utrata("brak odpowiedzi przy zdjęciu solo kaszlu")
            ok = False
        except NaruszenieZapory:
            ok = False
        if not ok:
            # Błąd odsłuchu nie otwiera właśnie zamkniętych dróg mikrofonu.
            self.powiedz(self.t("odsluch_niepotwierdzony"), Priorytet.BEZPIECZENSTWO, "kaszel-solo")
        self._dz("kaszel-solo", "zdjecie", ok)

    def _przywroc_solo_kaszlu(self) -> None:
        """Po wysyłkach albo po przerwaniu. Bez łączności zamiar przepada."""
        s = self._solo_kaszlu
        if s is None:
            return
        try:
            if not (self.stan.polaczony and self.stan.zsynchronizowany):
                self._dz("kaszel-solo", "bez-powrotu-stan-nieznany")
                return
            dane = self._odczytaj_solo_kaszlu()
            if dane is None or s.obca_zmiana or self._solo_kaszlu is not s:
                self._dz("kaszel-solo", "bez-powrotu-zmiana-lub-brak-odczytu")
                return
            ok = True
            for a, v in sorted(s.sprzed.items()):
                if dane[a] != v:
                    ok = self._zapis_solo_kaszlu(s, a, v) and ok
            zle = self._dwa_odczyty(dict(s.sprzed))
            if not ok or zle:
                self.powiedz(self.t("odsluch_niepotwierdzony"), Priorytet.BEZPIECZENSTWO, "kaszel-solo")
            self._dz("kaszel-solo", "powrot", ok and not zle)
        except BrakOdpowiedzi:
            self._solo_kaszlu = None
            self._utrata("brak odpowiedzi przy powrocie solo kaszlu")
        finally:
            if self._solo_kaszlu is s:
                self._solo_kaszlu = None

    def kaszel_wcisniety(self) -> None:
        """Kaszel na antenie i poza nią: wszystkie wyjścia głosu zamknięte.
        Brak otwartego toru to cichy brak operacji. Bez limitu czasu."""
        if self._kaszel is not None:
            return
        if not self._gotowy():
            self.powiedz(self.t("kaszel_nieznany"), Priorytet.INFORMACJA, "kaszel")
            return
        solo = self._odczytaj_solo_kaszlu()
        if solo is None:
            return
        if (not self._talkback and self.widok.mikrofon_ma_otwarty_tor() is False
                and self.widok.klucz(MIKROFON) is False
                and not any(solo.get(a) == 1 for a in self._solo_mikrofonu())):
            return
        if not self._rozpocznij_chwilowy():
            self.powiedz(self.t("kaszel_nieznany"), Priorytet.INFORMACJA, "kaszel")
            return
        if not self._talkback:
            self._chwilowy_rodzaj = "kaszel"
        self._kaszel = {"od": self.zegar()}
        self._dz("kaszel", "start")
        if self._zmien_chwilowy():
            self._zdejmij_solo_kaszlu()

    def kaszel_puszczony(self) -> None:
        if self._kaszel is None:
            return
        self._odczyt_krytyczny()
        if self._kaszel is None:
            return
        self._kaszel = None
        self._dz("kaszel", "puszczenie")
        if self._zmien_chwilowy():
            self._przywroc_solo_kaszlu()
            self._przywroc_glosniki_talkbacku()

    def _wycisz_glosniki_talkbacku(self) -> bool:
        """Pierwszy talkback przejmuje tylko wcześniej aktywne głośniki."""
        if self._glosniki_talkback is not None:
            return not self._glosniki_talkback.obca_zmiana and self.widok.glosniki_wyciszone() is True
        g = GlosnikiTalkbacku(aktywne=self.widok.glosniki_wyciszone() is False)
        self._glosniki_talkback = g
        if not g.aktywne:
            return self.widok.glosniki_wyciszone() is True
        kroki = self.kroki_wycisz_glosniki()
        w = self._zamknij(kroki)
        zle = self._dwa_odczyty({k.adres: 0 for k in kroki}) if self.stan.polaczony else kroki
        if not w.ok or zle or self._glosniki_talkback is not g or g.obca_zmiana:
            return False
        g.wyciszone_przez_talkback = True
        g.przywroc = True
        return True

    def _przywroc_glosniki_talkbacku(self) -> None:
        """Po potwierdzonym powrocie mikrofonu, niezależnie od Mute-Act.
        Nie używa glosniki(): udane automatyczne przywrócenie ma być ciche."""
        g = self._glosniki_talkback
        if g is None or self._mikrofon_sprzed is not None:
            return
        if not (g.aktywne and g.wyciszone_przez_talkback and g.przywroc):
            self._glosniki_talkback = None
            return
        # Nigdy nie ufaj samemu odczytowi kończącemu przywrócenie mikrofonu:
        # inny klient mógł od tego czasu otworzyć tor albo zmienić głośniki.
        self._odczyt_krytyczny()
        if self._glosniki_talkback is not g:
            return
        self._glosniki_talkback = None   # zamiar jednorazowy, także po odmowie
        if g.obca_zmiana or not g.przywroc:
            return
        if not self._gotowy():
            powod = self.t("stan_nieznany").lower()
        elif not self.kontroler_polaczony:
            powod = self.t("powod_kontroler")
        elif self.zapora.profil_blokuje:
            powod = self.t("powod_profil")
        else:
            # Odczyt toru + reguła glosniki_bez_mikrofonu w _zapis. Nie ma
            # ścieżki na skróty omijającej zaporę dla automatu.
            w = self._otworz([Krok(a, 1, 0) for a in self.widok.adresy_glosnikow()])
            zle = self._dwa_odczyty({a: 1 for a in self.widok.adresy_glosnikow()}) if w.ok else [True]
            if w.ok and not zle:
                self._dz("talkback-glosniki", "przywrocone")
                return
            # Zapis mógł się udać, ale odczyt zawiódł: wolno tylko zamknąć.
            self._zamknij(self._bez_zbednych(self.kroki_wycisz_glosniki(), self.widok))
            zamkniete = {a: 0 for a in self.widok.adresy_glosnikow()}
            zle = self._dwa_odczyty(zamkniete) if self.stan.polaczony else list(zamkniete)
            powod = w.powod or self.t("powod_niepotwierdzone")
            if zle:
                self._zamkniecia_chwilowe_zalegle = True
                powod += ". " + self.t("glosniki_moga_grac")
        self.powiedz(self.t("talkback_glosniki_powrot", powod=powod),
                     Priorytet.BEZPIECZENSTWO, "talkback-glosniki")

    def talkback_wcisniety(self, r: str) -> None:
        if r in self._talkback:
            return
        migawka = self._mikrofon_sprzed
        self._odczyt_krytyczny()
        if migawka is not None and self._mikrofon_sprzed is not migawka:
            return  # odczyt właśnie przerwał poprzednie trzymanie
        powod = None
        if not self._gotowy():
            powod = self.t("stan_nieznany").lower()
        elif not self.kontroler_polaczony:
            powod = self.t("powod_kontroler")
        elif self.zapora.profil_blokuje:
            powod = self.t("powod_profil")
        elif self.widok.glosniki_wyciszone() is NIEZNANY:
            powod = self.t("stan_nieznany").lower()
        else:
            try:
                p = self.u.poziom_bazowy(MIKROFON, self.widok.odbiorca(r))
                if not math.isfinite(p) or not -90.0 < p <= 10.0:
                    raise ValueError("poziom poza zakresem")
            except (KeyError, TypeError, ValueError):
                powod = self.t("talkback_brak_bazy")
        if powod is None and not self._rozpocznij_chwilowy():
            powod = self.t("powod_nieswiezy")
        if powod is None:
            self._chwilowy_rodzaj = "talkback"
            if not self._wycisz_glosniki_talkbacku():
                powod = self.t("talkback_glosniki")
                if self._kaszel is not None or self._talkback:
                    self._przerwij_kaszel()
                else:
                    # Odmowa przed dotknięciem mikrofonu. Nie udawaj, że
                    # zastany otwarty tor mikrofonu został zamknięty.
                    self._mikrofon_sprzed = None
                    self._glosniki_talkback = None
                    self._zwolnij_nakladke_cue(self.widok.cue_chwilowe)
        if powod is not None:
            self.powiedz(self.t("talkback_odmowa", powod=powod), Priorytet.INFORMACJA, "talkback")
            return
        self._talkback.add(r)
        self._dz("talkback", "start", r)
        if self._zmien_chwilowy() and self._kaszel is None:
            self.mowa.sygnal("talkback_start")

    def talkback_puszczony(self, r: str) -> None:
        if r not in self._talkback:
            return
        self._odczyt_krytyczny()
        if r not in self._talkback:
            return
        self._talkback.remove(r)
        self._dz("talkback", "puszczenie", r)
        if self._zmien_chwilowy():
            self.mowa.sygnal("talkback_koniec")
            self._przywroc_glosniki_talkbacku()

    def _domknij_chwilowy(self) -> None:
        """Bez przywracania. Po utracie miksera ponawiane po synchronizacji."""
        kroki = self.kroki_sumy(MIKROFON, False)
        kroki += [Krok(a, 0.0) for a in sorted(self._adresy_mikrofonu()) if a.endswith("/level")]
        if self._chwilowy_rodzaj == "talkback":
            # Także obce odciszenie przerywa talkback i wymusza ciszę.
            # Już potwierdzone OFF nie dostaje zbędnego zapisu.
            kroki = self._bez_zbednych(self.kroki_wycisz_glosniki(), self.widok) + kroki
        self._zamknij(kroki)
        oczekiwane = {k.adres: k.wartosc for k in kroki}
        if self._chwilowy_rodzaj == "talkback":
            oczekiwane.update({a: 0 for a in self.widok.adresy_glosnikow()})
        zle = self._dwa_odczyty(oczekiwane) if self.stan.polaczony else list(oczekiwane)
        self._zamkniecia_chwilowe_zalegle = bool(zle)
        if zle and self.stan.polaczony:
            self.powiedz(self.t("przejscie_niepelne"), Priorytet.BEZPIECZENSTWO, "przejscie")

    def _oddaj_muzyke_adresatow(self) -> None:
        """Po przerwaniu talkbacku muzyka adresatów wraca do zwykłego celu,
        z poziomem z migawki sprzed przyciszenia.

        Otwarcie idzie zwykłą drogą (zapora, świeży odczyt, rozbrojona
        powierzchnia), więc przy utracie miksera albo kontrolera nie udaje się
        i muzyka zostaje przyciszona. To jest bezpieczny kierunek: ciszej niż
        przed talkbackiem, nigdy głośniej. Zostaje do pierwszej zmiany stanu,
        która przelicza powroty.
        """
        adresaci, self._muzyka_przyciszona = self._muzyka_przyciszona, set()
        sprzed, self._muzyka_sprzed = dict(self._muzyka_sprzed), {}
        if not adresaci or not self._gotowy():
            return
        cue = self.widok.cue_zbior()
        mik = self.widok.suma(MIKROFON)
        if cue is NIEZNANY or mik is NIEZNANY:
            return
        c = self.cel(cue, mik is True)
        zakres: set[str] = set()
        for r in adresaci:
            odb = self.widok.odbiorca(r)
            if odb is None or r in cue:
                continue
            for zr in self.widok.muzyka():
                for a in self.widok.adresy_wysylki(zr, odb):
                    zakres.add(a)
                    zakres.add(adres_tap(a))
                    cw, v = c.wysylki.get(a), sprzed.get(a)
                    if cw is not None and cw.poziom > 0.0 and v is not None and v > 0.0:
                        cw.poziom = v   # dokładny poziom sprzed przyciszenia
        if zakres:
            self._wykonaj_przejscie(c, zakres=zakres)

    def _przerwij_kaszel(self, oglos: bool = True) -> None:
        """Przerywa całą sesję kaszlu/talkbacku. Żaden timer tu nie prowadzi.
        Stan NIEZNANY, restart kontrolera, obca zmiana albo F1: bez powrotu."""
        if self._mikrofon_sprzed is None and self._glosniki_talkback is None:
            return
        rodzaj = self._chwilowy_rodzaj
        # Najpierw usuń zamiar powrotu: błąd domykania może wywołać _utrata.
        self._mikrofon_sprzed = None
        self._glosniki_talkback = None
        self._kaszel = None
        self._talkback.clear()
        self._flagi_chwilowe()
        # CUE rozmówców zostaje; znika wyłącznie prawo odtworzenia mikrofonu.
        self._zamkniecia_chwilowe_zalegle = True
        self._domknij_chwilowy()
        # Solo to wyłącznie PHONES: można je oddać po przerwaniu, nie antenę.
        self._przywroc_solo_kaszlu()
        self._dz(rodzaj, "przerwany")
        if oglos:
            klucz = rodzaj + ("_niepotwierdzony" if self._zamkniecia_chwilowe_zalegle else "_przerwany")
            self.powiedz(self.t(klucz), Priorytet.BEZPIECZENSTWO, rodzaj)
        self._oddaj_muzyke_adresatow()

    def utrata_kontrolera(self, powod: str = "") -> None:
        """X-TOUCH zniknął albo się zrestartował: puszczenie przycisku przepadło
        i stan powierzchni (dotyk, silniki, diody) jest nieznany. Powierzchnia
        zostaje rozbrojona do powrotu kontrolera (L01): jej zdarzenia nie
        otwierają, zamknięcia działają, kaszel kończy się z mikrofonem poza anteną."""
        self._dz("kontroler", powod)
        byl = self.kontroler_polaczony
        self.kontroler_polaczony = False  # POPRAWKA L01: utrata kontrolera rozbraja powierzchnię
        self.uzbrojony = False
        # Dotyk i niepotwierdzony ruch suwaka sprzed utraty przepadają: suwaki
        # odczyta odczyt okresowy, który niczego nie otwiera (P02).
        self._dotyk.clear()
        self._suwak_ruch.clear()
        self._przerwij_kaszel()
        if byl:
            self.powiedz(self.t("kontroler_utracony"), Priorytet.BEZPIECZENSTWO, "kontroler")

    def powrot_kontrolera(self, powod: str = "") -> None:
        """Kontroler znowu połączony: najpierw silniki i diody według odczytu,
        potem uzbrojenie (plan, rozdz. 8, kontrakt pkt 10). Nic nie zapisuje
        do miksera i nie wykonuje zaległych zdarzeń."""
        self._dz("kontroler-powrot", powod)
        if self.kontroler_polaczony:
            return
        self.kontroler_polaczony = True
        self._dotyk.clear()
        self._ustaw_silniki()
        self._odswiez_powierzchnie()
        self.uzbrojony = self.stan.polaczony and self.stan.zsynchronizowany
        self.powiedz(self.t("kontroler_powrot"), Priorytet.BEZPIECZENSTWO, "kontroler")

    def _puszczenie_przycisku(self, pasek: int, indeks: int) -> None:
        opis = self.u.paski.get(pasek) or {}
        if indeks == 2 and opis.get("mute") == "kaszel":
            self.kaszel_puszczony()
        elif indeks == 2 and opis.get("mute") == "talkback":
            self.talkback_puszczony(opis["zrodlo"])
        # Puszczenie każdego innego przycisku nie wykonuje drugiej operacji.

    # ======================================================================
    # liczniki czasu (plan v21, pkt 3, decyzja 3)
    # ======================================================================
    def _stany_licznikow(self) -> dict:
        # Decyzja Michała z 18.10.2026 (P01): licznik mikrofonu podaje czas
        # nieprzerwanego stanu antenowego, więc po kaszlu liczy od nowa, od
        # ponownego potwierdzenia Main On.
        stany = {"mikrofon": self.widok.suma(MIKROFON)}  # POPRAWKA P01
        for r in self._rozmowcy():
            stany[r] = self.widok.stan_rozmowcy(r)
        return stany

    def _aktualizuj_liczniki(self, poczatek_znany: bool = True) -> None:
        """Licznik startuje od potwierdzonej zmiany stanu. Po starcie i powrocie
        łączności początek jest nieznany: status mówi stan bez czasu."""
        if not (self.stan.polaczony and self.stan.zsynchronizowany):
            self._liczniki.clear()
            return
        teraz = self.zegar()
        for k, s in self._stany_licznikow().items():
            if s is NIEZNANY:
                self._liczniki.pop(k, None)
                continue
            stary = self._liczniki.get(k)
            if stary is None or stary[0] != s:
                self._liczniki[k] = (s, teraz if (poczatek_znany and stary is not None) else None)

    def _czas_licznika(self, klucz: str):
        """Czas bieżącego stanu. Licznik jest uzgadniany z odczytem PRZED opisem,
        więc nowy stan nigdy nie dostaje czasu poprzedniego (L04)."""
        self._aktualizuj_liczniki()  # POPRAWKA L04: licznik według bieżącego stanu przed opisem
        wpis = self._liczniki.get(klucz)
        if not wpis or wpis[1] is None:
            return None
        czas = czas_slownie(self.zegar() - wpis[1])
        return {"czas": czas} if czas else None

    def _przypomnienia(self, teraz: float) -> None:
        """Przypomnienie co N minut mikrofonu na antenie; domyślnie wyłączone."""
        n = self.u.przypomnienie_mikrofonu_min
        wpis = self._liczniki.get("mikrofon")
        if n <= 0 or not wpis or wpis[0] is not True or wpis[1] is None:
            return
        ktore = int((teraz - wpis[1]) // (n * 60.0))
        start, ostatnie = self._przypomnienie
        if start != wpis[1]:
            self._przypomnienie = (wpis[1], 0)
            start, ostatnie = wpis[1], 0
        if ktore > ostatnie:
            self._przypomnienie = (start, ktore)
            if self._kaszel is None:
                self.powiedz(self.t("mikrofon_licznik", czas=czas_slownie(teraz - wpis[1])),
                             Priorytet.INFORMACJA, "przypomnienie")

    # ======================================================================
    # mierniki i alarm ciszy (plan v21, pkt 4, decyzja 4)
    # ======================================================================
    def _odnow_mierniki(self, teraz: float) -> None:
        self._ost_mierniki = teraz
        if not self.alarm_wlaczony or not hasattr(self.klient, "subskrybuj_mierniki"):
            return
        try:
            self.klient.subskrybuj_mierniki(str(self.u.mierniki.get("identyfikator", "/meters/5")))
        except Exception:  # noqa: BLE001
            log.exception("nie udało się odnowić subskrypcji mierników")

    def _przyjmij_mierniki(self, blob: bytes) -> None:
        """Wątek sieciowy: blok mierników. Zły blok to brak danych, nie cisza."""
        mi = self.u.mierniki
        try:
            wartosci = dekoduj_blok(blob, str(mi.get("kolejnosc_bajtow", "little")))
            db = poziom_lr(wartosci, tuple(int(i) for i in mi.get("indeksy_main_lr", (6, 7))))
        except (ValueError, TypeError):
            self.bledy_miernikow += 1
            return
        self.detektor.przyjmij(db, self.zegar())

    def przelacz_alarm_ciszy(self) -> None:
        """Włączenie albo wyłączenie alarmu ciszy w trakcie pracy, bez restartu
        (Michał 21.10.2026). Stan po starcie bierze się z ustawień
        (zachowanie.alarm_ciszy.wlaczony); przełącznik nie zapisuje pliku.
        Bez odczytu i zapisu miksera, poza subskrypcją mierników."""
        teraz = self.zegar()
        self.alarm_wlaczony = not self.alarm_wlaczony
        if self.alarm_wlaczony:
            # Pomiar od nowa: cisza sprzed włączenia nie wywoła od razu alarmu.
            if self.stan.polaczony and self.stan.zsynchronizowany:
                self._odnow_mierniki(teraz)
                self.detektor.oczekuj(teraz)
            self.powiedz(self.t("alarm_ciszy_wlaczony"), Priorytet.STAN, "alarm_ciszy")
        else:
            self.detektor.reset()
            self.powiedz(self.t("alarm_ciszy_wylaczony"), Priorytet.STAN, "alarm_ciszy")
        self._dz("alarm_ciszy", "wlaczony" if self.alarm_wlaczony else "wylaczony")

    def _alarm_ciszy(self, teraz: float) -> None:
        # W trakcie kaszlu NVDA milczy (decyzja 2): zdarzenia mierników czekają
        # do puszczenia; pomiar trwa dalej.
        if not self.alarm_wlaczony or self._mikrofon_sprzed is not None:
            return
        for z in self.detektor.krok(teraz):
            self._dz("mierniki", z)
            if z == "cisza":
                self.powiedz(self.t("cisza_na_antenie"), Priorytet.BEZPIECZENSTWO, "cisza")
            elif z == "powrot":
                self.powiedz(self.t("dzwiek_na_antenie"), Priorytet.STAN, "cisza")
            elif z == "niedostepne":
                self.powiedz(self.t("mierniki_niedostepne"), Priorytet.STAN, "mierniki")
            elif z == "dostepne":
                self.powiedz(self.t("mierniki_dostepne"), Priorytet.INFORMACJA, "mierniki")

    def _po_zamknieciu_mikrofonu(self) -> str:
        """Mute-Act jak w konsoletach D&R (plan v22, rozdz. 6a, decyzja Michała
        z 17.10.2026): po wyłączeniu mikrofonu i po zwolnieniu ostatniego CUE
        głośniki włączają się same. Tylko gdy odczyt potwierdza brak otwartego
        toru mikrofonu i brak CUE; nigdy w trakcie kaszlu, przy stanie
        NIEZNANY ani przy blokującej niezgodności profilu. Zwraca dopisek do
        komunikatu albo pusty tekst, gdy nic nie zmieniono."""
        if not self.u.zachowanie.get("odciszaj_glosniki_po_wylaczeniu_mikrofonu", True):
            return ""
        if (not self._gotowy() or self.zapora.profil_blokuje or self._kaszel is not None
                or self._talkback or self._glosniki_talkback is not None or self._zamkniecia_chwilowe_zalegle
                or self.widok.glosniki_wyciszone() is not True or self._rozbrojone()):
            return ""
        if self.widok.mikrofon_ma_otwarty_tor() is not False or self.widok.cue_zbior() != frozenset():
            return ""
        w = self._otworz([Krok(sciezki.mute_szyny(b), 1, 0) for b in self.u.szyny_glosnikow])
        self._dz("mute-act", w.ok)
        if w.ok and self.widok.glosniki_wyciszone() is False:
            return self.t("glosniki_wlaczone")
        if self.widok.glosniki_wyciszone() is True:
            return self.t("glosniki_wyciszone")
        return self.t("glosniki_moga_grac")

    def _z_mute_act(self, tekst: str) -> str:
        dopisek = self._po_zamknieciu_mikrofonu()
        return tekst + ". " + dopisek if dopisek else tekst

    # ======================================================================
    # CUE rozmówców (rozdz. 6 i 7, decyzje 1-5)
    # ======================================================================
    def _opis_rozmowcy(self, r: str, z_czasem: bool = False) -> str:
        s = self.widok.stan_rozmowcy(r)
        nazwa = self.u.zrodla[r].rozmowca
        if s is NIEZNANY:
            return self.t("rozmowca_moze_byc_na_antenie", rozmowca=nazwa)
        if s == CZEKA_POZA_SUMA and self.widok.suwak_na_dole(r) is True:
            return self.t("rozmowca_poza_suma", rozmowca=nazwa)
        opis = self.t({CUE: "rozmowca_w_rozmowie", ANTENA: "rozmowca_na_antenie", CZEKA: "rozmowca_czeka",
                       CZEKA_POZA_SUMA: "rozmowca_czeka_poza_suma"}[s], rozmowca=nazwa).wariant(r)
        czas = self._czas_licznika(r) if (z_czasem and s in (CUE, ANTENA, CZEKA)) else None
        return self.t("licznik", opis=opis, **czas) if czas else opis

    def _zamknij_rozmowe_nieznany(self, rozmowcy, z_kim: str) -> None:
        """Przy stanie NIEZNANY przycisk CUE i F3 tylko zamykają rozmowę."""
        self.powiedz(self.t("stan_nieznany_zamykam_rozmowe", z_kim=z_kim), Priorytet.BEZPIECZENSTWO)
        w = self._zamknij(self.kroki_rozmowy_do_zamkniecia(rozmowcy))
        if not self.stan.polaczony:
            self.powiedz(self.t("stan_nieznany"), Priorytet.BEZPIECZENSTWO, "przejscie")
        elif not w.ok:
            self.powiedz(self.t("przejscie_niepelne"), Priorytet.BEZPIECZENSTWO, "przejscie")
        elif self._gotowy():
            self.powiedz(". ".join(self._opis_rozmowcy(r) for r in rozmowcy), Priorytet.STAN, "przejscie")

    def przelacz_cue(self, r: str) -> None:
        z_kim = self.u.zrodla[r].z_kim
        cue = self.widok.cue_zbior() if self._gotowy() else NIEZNANY
        c = self.widok.cue(r) if self._gotowy() else NIEZNANY
        if cue is NIEZNANY or c is NIEZNANY:
            self._zamknij_rozmowe_nieznany([r], z_kim)
            return
        if not c and self._rozbrojone():
            # L01: wejście w CUE otwiera rozmowę, więc przy utraconym kontrolerze nic.
            self.powiedz(self.t("kontroler_otwieranie"), Priorytet.BEZPIECZENSTWO, "przejscie")
            return
        mik_przed = self.widok.suma(MIKROFON) is True or self._kaszel is not None
        if c:
            # Zwolnienie CUE: rozmówca czeka i słyszy antenę (decyzje 1 i 2).
            nowe = cue - {r}
            w = self._wykonaj_przejscie(self.cel(nowe, mik_przed, cue_przed=cue, przywroc={r}))
            if not w.ok:
                self._niepowodzenie(w)
                return
            self.powiedz(self._z_mute_act(self._dopisz_odsluch(self._opis_rozmowcy(r), w)),
                         Priorytet.STAN, "przejscie", dzwiek=True)
            return
        # Wejście w CUE: najpierw mikrofon i rozmówca z anteny (decyzje 4 i 5).
        nowe = cue | {r}
        w = self._wykonaj_przejscie(self.cel(nowe, False, cue_przed=cue), sciagnij=[r])
        if not w.ok:
            self._niepowodzenie(w)
            return
        if mik_przed:
            tekst = self.t("mikrofon_poza_antena_rozmowa", z_kim=self._z_kim(nowe)).wariant(r)
        else:
            tekst = self.t("rozmowa_poza_antena", z_kim=self._z_kim(nowe)).wariant(r)
        if w.trzymane:
            tekst += ". " + self.t("suwak_trzymany")
        self.powiedz(self._dopisz_odsluch(tekst, w), Priorytet.STAN, "przejscie", dzwiek=True)

    def f3_koniec_rozmowy(self) -> None:
        """F3: zwalnia wszystkie CUE naraz; rozmówcy wracają do oczekiwania."""
        rozm = self._rozmowcy()
        cue = self.widok.cue_zbior() if self._gotowy() else NIEZNANY
        if cue is NIEZNANY:
            self._zamknij_rozmowe_nieznany(rozm, self.t("rozmowa_wszyscy"))
            return
        if not cue:
            self.powiedz(self.t("brak_rozmowy"), Priorytet.INFORMACJA)
            return
        mik = self.widok.suma(MIKROFON) is True
        w = self._wykonaj_przejscie(self.cel(frozenset(), mik, cue_przed=cue, przywroc=cue))
        if not w.ok:
            self._niepowodzenie(w)
            return
        tekst = polacz(". ", [self.t("koniec_rozmowy")] + [self._opis_rozmowcy(r) for r in rozm])
        self.powiedz(self._z_mute_act(self._dopisz_odsluch(tekst, w)), Priorytet.STAN, "przejscie", dzwiek=True)

    def _zakres_zrodla(self, zr: str) -> set[str]:
        """Adresy, które zależą od tego, czy źródło jest na antenie: jego
        wysyłki do powrotów rozmówców, a dla rozmówcy także jego Main On
        i podsłuch prawego ucha (dla telefonu)."""
        a: set[str] = set()
        for odb in self.u.odbiorcy:
            if self.u.odbiorcy[odb].wlasne_zrodlo != zr:
                a.update(self.widok.adresy_wysylki(zr, odb))
        if zr in self._rozmowcy():
            a.update(self.widok.adresy_sumy(zr))
        if zr == TELEFON:
            a.add(self.widok.adres_podsluchu())
        # Klucz przyciszania zależy od anteny słuchacza i źródeł klucza (plan v22).
        if zr == self.u.sluchacz:
            for k in self.u.zrodla_klucza:
                a.update(self.widok.adresy_klucza(k))
        elif zr in self.u.zrodla_klucza:
            a.update(self.widok.adresy_klucza(zr))
        return a

    def _po_zmianie_suwaka(self, r: str, przed, byl_w_gorze=None) -> None:
        """Podniesienie albo ściągnięcie suwaka rozmówcy (rozdz. 7): najpierw
        antena (zrobił to suwak), potem powroty; przy suwaku na dole po CUE
        Main On wraca. Komunikat po odczycie.

        Podniesienie suwaka rozmówcy z CUE (plan v21, pkt 1, „Auto CUE Reset
        by FADER”): kończy jego CUE i wpuszcza go na antenę. Liczy się tylko
        podniesienie z dołu: suwak trzymany w górze od wejścia w CUE nie
        wpuszcza na antenę (rozdz. 6, przytrzymany suwak)."""
        if (przed == CUE and byl_w_gorze is False and self.widok.cue(r) is True
                and self.widok.suwak_w_gorze(r) is True):
            self._suwak_konczy_cue(r)
            return
        self._dopasuj_zrodlo(r, przywroc={r})
        po = self.widok.stan_rozmowcy(r)
        if not self._gotowy() or po is NIEZNANY:
            return
        # Suwak podniesiony, a kanał poza sumą: Michał musi to usłyszeć, bo
        # spodziewa się wejścia na antenę (rozdz. 6, przytrzymany suwak).
        w_gorze = po == CZEKA_POZA_SUMA and self.widok.suwak_w_gorze(r) is True
        if po != przed or w_gorze:
            self.powiedz(self._opis_rozmowcy(r), Priorytet.STAN, f"rozmowca-{r}", dzwiek=True)

    def _suwak_konczy_cue(self, r: str) -> None:
        """Kolejność z planu v21, pkt 1: najpierw zamknięcie dróg rozmowy do
        szyny rozmówcy (mikrofon i uczestnicy przed suwakiem), potem powrót
        programu za suwakiem, na końcu Main On rozmówcy. Inni uczestnicy CUE
        zostają w rozmowie. Klucz przyciszania przełącza się w tym samym
        przejściu (zamknięcia razem z zamknięciami, otwarcia na końcu)."""
        cue = self.widok.cue_zbior()
        mik = self.widok.suma(MIKROFON)
        if cue is NIEZNANY or mik is NIEZNANY:
            return
        nowe = cue - {r}
        w = self._wykonaj_przejscie(self.cel(nowe, mik is True, cue_przed=cue, na_antene={r}))
        if not w.ok:
            self._niepowodzenie(w)
            return
        self.powiedz(self._z_mute_act(self._dopisz_odsluch(self._opis_rozmowcy(r), w)),
                     Priorytet.STAN, f"rozmowca-{r}", dzwiek=True)

    def _dopasuj_zrodlo(self, zr: str, przywroc=(), obce: bool = False) -> bool:
        """Powroty rozmówców według nowego stanu jednego źródła (suwak albo
        Main On), jak szyna N-1 w konsolecie: powrót bierze to, co jest na
        antenie. Zamknięcia przed otwarciami; otwierany jest wyłącznie program
        za suwakiem, nigdy rozmowa ani antena. Main On rozmówcy wraca tylko
        dla `przywroc` (własny ruch suwaka po CUE). Przy zmianie z innego
        urządzenia (`obce`) Main On tego źródła zostaje, jakie jest: mostek
        nie cofa cudzej zmiany, tylko ją ogłasza (plan, rozdz. 3)."""
        if not self._gotowy():
            return False
        cue = self.widok.cue_zbior()
        mik = self.widok.suma(MIKROFON)
        if cue is NIEZNANY or mik is NIEZNANY:
            return False
        c = self.cel(cue, mik is True, przywroc=przywroc)
        zakres = self._zakres_zrodla(zr)
        if obce:
            zakres -= set(self.widok.adresy_sumy(zr))
        w = self._wykonaj_przejscie(c, zakres=zakres)
        if not w.ok and (not obce or w.etap == "zamkniecia" or w.utrata):
            # Po zmianie z innego urządzenia nieudane otwarcie powrotu programu
            # jest wycofane i nie dotyczy prywatności; mówimy tylko o zamknięciach.
            self._niepowodzenie(w)
        return w.ok

    # ======================================================================
    # PFL muzyki i głośniki
    # ======================================================================
    def przelacz_pfl(self, zr: str) -> None:
        stan = self.widok.pfl(zr)
        cel = False if (stan is NIEZNANY or not self._gotowy()) else not stan
        kroki = self.kroki_pfl(zr, cel)
        wynik = self._otworz(kroki) if cel else self._zamknij(kroki)
        stan = self.widok.pfl(zr)
        if stan is NIEZNANY or not wynik.ok:
            self.powiedz(self.t("pfl_stan", nazwa=self._nazwa(zr), stan=self.t("powod_niepotwierdzone")),
                         Priorytet.STAN, "przelacznik")
            return
        self.powiedz(self.t("pfl_stan", nazwa=self._nazwa(zr), stan=self.u.stan_slowo(bool(stan), "m"))
                     .wariant("wlaczony" if stan else "wylaczony"),
                     Priorytet.STAN, "przelacznik", dzwiek=True)

    def glosniki(self, wlacz: bool) -> None:
        # Świadome polecenie wygrywa, również OFF przy już wyciszonym Bus 6
        # oraz odmówione ON. Automat nie nadpisze go po puszczeniu MUTE.
        if self._glosniki_talkback is not None:
            self._glosniki_talkback.przywroc = False
        if not wlacz:
            w = self._zamknij(self.kroki_wycisz_glosniki())
            if w.ok and self.widok.glosniki_wyciszone() is True:
                self.powiedz(self.t("glosniki_wyciszone"), Priorytet.STAN, "glosniki", dzwiek=True)
            else:
                self.powiedz(self.t("glosniki_moga_grac"), Priorytet.BEZPIECZENSTWO, "glosniki")
            return
        # L03: rdzeń i zapora (glosniki_przy_niezgodnym_profilu) odrzucają
        # odciszenie przy stanie NIEZNANY i przy blokującym profilu; NVDA mówi powód.
        powod = None
        if not self._gotowy():
            powod = "glosniki_odrzucone_nieznany"
        elif self._rozbrojone():
            powod = "glosniki_odrzucone_kontroler"
        elif self.zapora.profil_blokuje:  # POPRAWKA L03: rdzeń odrzuca przy niezgodnym profilu
            powod = "glosniki_odrzucone_profil"
        elif (self.widok.mikrofon_ma_otwarty_tor() is not False
              or self.widok.cue_zbior() != frozenset() or self._kaszel is not None or self._talkback):
            powod = "glosniki_odrzucone"
        if powod:
            self.powiedz(self.t(powod), Priorytet.BEZPIECZENSTWO, "glosniki")
            return
        w = self._otworz([Krok(sciezki.mute_szyny(b), 1, 0) for b in self.u.szyny_glosnikow])
        if w.ok and self.widok.glosniki_wyciszone() is False:
            self.powiedz(self.t("glosniki_wlaczone"), Priorytet.STAN, "glosniki", dzwiek=True)
        else:
            self.powiedz(self.t("glosniki_odrzucone"), Priorytet.BEZPIECZENSTWO, "glosniki")

    # ======================================================================
    # odsłuch
    # ======================================================================
    def sluchaj_programu(self) -> None:
        kroki = [k for zr in self.u.zrodla for k in self.kroki_pfl(zr, False)] + self.kroki_solo_lr(False)
        w = self._zamknij(kroki + [Krok(sciezki.MONITOR_ZRODLO, sciezki.ZRODLO_LR)] + self._kroki_dim(False))
        self.powiedz(self.t("sluchasz_programu") if w.ok else self.t("synchronizacja_brak"), Priorytet.STAN, "odsluch")

    def sluchaj_rozmowy(self) -> None:
        cue = self.widok.cue_zbior() if self._gotowy() else NIEZNANY
        if cue is NIEZNANY:
            self.powiedz(self.t("stan_nieznany"), Priorytet.BEZPIECZENSTWO)
            return
        if not cue:
            self.powiedz(self.t("brak_rozmowy"), Priorytet.INFORMACJA, "odsluch")
            return
        w = self._zamknij(self.kroki_odsluchu_rozmowy(cue))
        self.powiedz(self.t("sluchasz_rozmowy") if w.ok else self.t("synchronizacja_brak"), Priorytet.STAN, "odsluch")

    def _muzyka_w_sluchawkach_przy_cue(self, zr: str) -> None:
        """Muzyka weszła na antenę albo zeszła w trakcie rozmowy: PFL za nią."""
        if not self.u.zachowanie.get("program_w_sluchawkach_przy_cue", True):
            return
        s = self.widok.suma(zr)
        if s is NIEZNANY or self.widok.pfl(zr) is s:
            return
        kroki = self.kroki_pfl(zr, s is True)
        if s is True:
            self._otworz(kroki)
        else:
            self._zamknij(kroki)

    def koniec_pfl(self) -> None:
        kroki = [k for zr in self.u.zrodla for k in self.kroki_pfl(zr, False)] + self.kroki_solo_lr(False)
        w = self._zamknij(kroki + self._kroki_dim(False))
        if w.ok:
            self.powiedz(self.t("koniec_pfl"), Priorytet.STAN, "odsluch", dzwiek=True)
        else:
            self.powiedz(self.t("synchronizacja_brak"), Priorytet.STAN, "odsluch")

    # ======================================================================
    # komunikaty stanu
    # ======================================================================
    def tekst_statusu(self) -> str:
        """Stała kolejność: mikrofon, telefon, Zoom, głośniki (rozdz. 8)."""
        if not self._gotowy():
            return self.t("stan_nieznany")
        czesci = [self._komunikat_mikrofonu(z_czasem=True)] + [self._opis_rozmowcy(r, z_czasem=True)
                                                               for r in self._rozmowcy()]
        g = self.widok.glosniki_wyciszone()
        czesci.append(self.t("glosniki_wyciszone") if g is True else
                      self.t("glosniki_wlaczone") if g is False else self.t("glosniki_moga_grac"))
        # P03: F2 krótkie, poziomy daje gałka paska; po stałej części tylko
        # ostrzeżenia o niepewnym stanie.
        if self.zapora.profil_blokuje:
            czesci.append(self.t("status_profil", opis=self._opis_blokady))
        if not self.kontroler_polaczony:
            czesci.append(self.t("kontroler_odlaczony"))
        if self.alarm_wlaczony:
            s = self.detektor.stan
            if s == "alarm":
                czesci.append(self.t("cisza_na_antenie"))
            elif s == "niedostepne":
                czesci.append(self.t("mierniki_niedostepne"))
        else:
            czesci.append(self.t("alarm_ciszy_wylaczony"))
        return ". ".join(czesci) + "."

    def status(self) -> None:
        """F2: świeży odczyt torów krytycznych, potem jedno zdanie. Zgodny mikser:
        zero zapisów. Wolno tylko ochronne zamknięcie wykrytej niebezpiecznej
        drogi (P02); odczyt niczego nie otwiera. Przy blokadzie profilu F2 robi
        pełny odczyt: zgodny profil zdejmuje blokadę (kontrakt pkt 8)."""
        if self.stan.polaczony and self.stan.zsynchronizowany:
            if self.zapora.profil_blokuje:
                self.synchronizuj()
            else:
                self._ost_krytyczny = self.zegar()
                self._odczyt_krytyczny()
        self.powiedz(self.tekst_statusu(), Priorytet.STAN, "status")

    def status_paska(self, pasek: int) -> None:
        zr = self._zrodlo_paska(pasek)
        if not zr:
            self.powiedz(self.t("pasek_wolny"), Priorytet.INFORMACJA)
            return
        if not self._gotowy():
            self.powiedz(self.t("stan_nieznany"), Priorytet.BEZPIECZENSTWO)
            return
        if zr == MIKROFON:
            pierwsza = self._komunikat_mikrofonu(z_czasem=True)
        elif zr in self._rozmowcy():
            pierwsza = self._opis_rozmowcy(zr, z_czasem=True)
        else:
            s = self.widok.suma(zr)
            pierwsza = (self.t("moze_byc_wlaczony", nazwa=self._nazwa(zr)) if s is NIEZNANY else
                        self.t("suma_stan", nazwa=self._nazwa(zr), stan=self.u.stan_slowo(bool(s), self._rodzaj(zr))))
        f = opis_fadera(self.u, self.widok.fader_db(zr), self.u.zrodla[zr].suwak_maks_db)
        if f and not pierwsza.endswith(f):
            pierwsza += ", " + f
        czesci = [pierwsza]
        if not self.u.zrodla[zr].glos and self.widok.pfl(zr) is True:
            czesci.append(self.t("pfl_stan", nazwa=self._nazwa(zr), stan=self.u.stan_slowo(True, "m")))
        if self.u.zrodla[zr].galka:
            przes = self._przesuniecie_galki(zr)
            if przes is not NIEZNANY:
                czesci.append(self.t("wzmocnienie", nazwa=self._nazwa(zr), wartosc=_opis_przesuniecia(przes)))
        self.powiedz(". ".join(czesci), Priorytet.STAN, "status")

    def f8_powierzchnia(self) -> None:
        """F8: opis powierzchni i odsłuchu. Przy utraconym kontrolerze mówi to
        i nie mówi „synchronizacja zgodna” (L01, plan rozdz. 8, kontrakt pkt 12)."""
        czesci = [self.t("powierzchnia")]
        mon = self.widok.monitor()
        if mon is not NIEZNANY:
            czesci.append(self.t("monitor", zrodlo=sciezki.ZRODLO_NAZWY.get(mon, str(mon))))
        aktywne = [self._nazwa(zr) for zr in self.u.zrodla if self.widok.pfl(zr) is True]
        czesci.append(self.t("solo_aktywne", lista=", ".join(aktywne)) if aktywne else self.t("solo_brak"))
        g = self.widok.glosniki_wyciszone()
        czesci.append(self.t("glosniki_wyciszone") if g is True else
                      self.t("glosniki_wlaczone") if g is False else self.t("glosniki_moga_grac"))
        if not self.kontroler_polaczony:
            czesci.append(self.t("kontroler_odlaczony"))
        czesci.append(self.t("synchronizacja_zgodna")
                      if self._gotowy() and not self.zapora.profil_blokuje and self.kontroler_polaczony
                      else self.t("synchronizacja_brak"))
        self.powiedz(". ".join(czesci), Priorytet.STAN, "status")

    # ======================================================================
    # gałki (plan, rozdz. 8, „Gałki i suwaki”)
    # ======================================================================
    def _galka_adresy(self, zr: str) -> list[str]:
        g = self.u.zrodla[zr].galka or {}
        if g.get("typ") == "gain":
            return [sciezki.gain(int(g["wejscie"]))]
        if g.get("typ") == "rtntrim":
            return [sciezki.rtntrim(k) for k in self.u.zrodla[zr].kanaly]
        return []

    def _galka_db(self, zr: str):
        g = self.u.zrodla[zr].galka or {}
        wart = [self.stan.wartosc(a) for a in self._galka_adresy(zr)]
        if not wart or any(v is NIEZNANY for v in wart):
            return NIEZNANY
        konw = gain_float_na_db if g.get("typ") == "gain" else trim_float_na_db
        dbs = [konw(float(v)) for v in wart]
        if max(dbs) - min(dbs) > 0.25:
            return NIEZNANY
        return dbs[0]

    def _przesuniecie_galki(self, zr: str):
        db = self._galka_db(zr)
        if db is NIEZNANY or zr not in self._baza_galek:
            return NIEZNANY
        return round(db - self._baza_galek[zr])

    def obrot_galki(self, pasek: int, kierunek: int) -> None:
        zr = self._zrodlo_paska(pasek)
        if not zr or not self.u.zrodla[zr].galka:
            return      # gałki mikrofonu i muzyki bez funkcji obrotu
        if self._rozbrojone():
            self.powiedz(self.t("kontroler_otwieranie"), Priorytet.STAN, "galka")
            return
        if not self._gotowy():
            self.powiedz(self.t("powod_brak_lacznosci").capitalize(), Priorytet.STAN, "galka")
            return
        przes = self._przesuniecie_galki(zr)
        if przes is NIEZNANY:
            self.powiedz(self.t("powod_niepotwierdzone").capitalize(), Priorytet.STAN, "galka")
            return
        krok = float(self.u.zachowanie.get("krok_galki_db", 1.0))
        zakres = float(self.u.zachowanie.get("zakres_galki_db", 12.0))
        # Jeden ząbek = jeden krok, bez przyspieszania przy szybkim obrocie.
        nowe = przes + (krok if kierunek > 0 else -krok)
        if abs(nowe) > zakres + 1e-6:
            self.powiedz(self.t("granica_wzmocnienia"), Priorytet.STAN, "galka")
            return
        g = self.u.zrodla[zr].galka
        db = self._baza_galek[zr] + nowe
        wartosc = gain_db_na_float(db) if g["typ"] == "gain" else trim_db_na_float(db)
        try:
            for a in self._galka_adresy(zr):
                self._zapis(Krok(a, wartosc))
        except NaruszenieZapory as e:
            self.powiedz(str(e), Priorytet.STAN, "galka")
            return
        except BrakOdpowiedzi:
            self._utrata("brak odpowiedzi przy gałce")
            return
        self._galka_komunikat[zr] = self.zegar()

    def _komunikaty_galek(self, teraz: float) -> None:
        zwloka = float(self.u.zachowanie.get("zwloka_komunikatu_galki_s", 0.5))
        for zr, t in list(self._galka_komunikat.items()):
            if teraz - t >= zwloka:
                del self._galka_komunikat[zr]
                przes = self._przesuniecie_galki(zr)
                if przes is not NIEZNANY:
                    self.powiedz(self.t("wzmocnienie", nazwa=self._nazwa(zr), wartosc=_opis_przesuniecia(przes)),
                                 Priorytet.INFORMACJA, "galka")

    # ======================================================================
    # suwaki
    # ======================================================================
    def dotyk_suwaka(self, pasek: int, dotkniety: bool) -> None:
        if dotkniety:
            self._dotyk.add(pasek)
            if pasek != 9 and not self._zrodlo_paska(pasek):
                self.powiedz(self.t("suwak_wolny"), Priorytet.INFORMACJA, "suwak")
        else:
            self._dotyk.discard(pasek)
            self._rozbieznosc_zgloszona.discard(pasek)

    def _gora_suwaka(self, pasek: int) -> float:
        """Wartość fadera MR18 przy suwaku w samej górze: 0 dB (0,75), dla
        źródła z suwak_maks_db wyżej, np. mikrofon do plus 10 dB (1,0)."""
        zr = None if pasek == 9 else self._zrodlo_paska(pasek)
        if not zr:
            return ZERO_DB
        return poziom_db_na_float(self.u.zrodla[zr].suwak_maks_db)

    def ruch_suwaka(self, pasek: int, pozycja: float) -> None:
        """Suwak zawsze czynny; góra = suwak_maks_db źródła (domyślnie 0 dB,
        poziom ze sceny), dół = minus nieskończoność."""
        if not self.uzbrojony or not self._gotowy():
            return
        pozycja = min(max(pozycja, 0.0), 1.0)
        wartosc = pozycja * self._gora_suwaka(pasek)
        if pasek == 9:
            adresy = [sciezki.MONITOR_POZIOM]
        else:
            zr = self._zrodlo_paska(pasek)
            if not zr:
                return
            if self.widok.para_rozbiezna(zr):
                if pasek not in self._rozbieznosc_zgloszona:
                    self._rozbieznosc_zgloszona.add(pasek)
                    self.powiedz(self.t("pary_rozbiezne", nazwa=self._nazwa(zr)), Priorytet.STAN, "suwak")
                return
            adresy = [sciezki.fader(k) for k in self.u.zrodla[zr].kanaly]
        for a in adresy:
            self.zapora.sprawdz(a, wartosc, self.widok)
            self.klient.wyslij(a, wartosc)
        self._suwak_ruch[pasek] = self.zegar()

    def _potwierdz_suwaki(self, teraz: float) -> None:
        """Po zatrzymaniu suwaka odczyt potwierdzający (bez komentarza NVDA),
        a dla rozmówcy dopasowanie powrotów i Main On do nowej pozycji."""
        for pasek, t in list(self._suwak_ruch.items()):
            if teraz - t < self.zwloka_suwaka:
                continue
            del self._suwak_ruch[pasek]
            zr = None if pasek == 9 else self._zrodlo_paska(pasek)
            if pasek == 9:
                adresy = [sciezki.MONITOR_POZIOM]
            else:
                adresy = [sciezki.fader(k) for k in self.u.zrodla[zr].kanaly]
            przed = self.widok.stan_rozmowcy(zr) if zr in self._rozmowcy() else None
            # Ostatni potwierdzony odczyt suwaka sprzed ruchu ręki (ruch idzie
            # bez potwierdzenia, a odczyt okresowy pomija suwaki w ręku).
            byl_w_gorze = self.widok.suwak_w_gorze(zr) if zr in self._rozmowcy() else None
            try:
                dane = self.klient.odczytaj_wiele(adresy)
            except BrakOdpowiedzi:
                self._utrata("brak odpowiedzi po ruchu suwaka")
                return
            for a, v in dane.items():
                self.stan.potwierdz(a, v, teraz)
            if zr in self._rozmowcy() or zr == MIKROFON:
                # Decyzja i komunikat po suwaku wymagają świeżego odczytu torów
                # krytycznych (L02). Odczyt okresowy idzie co 5 s, więc bez tego
                # komunikat przepadał (Michał, 22.10.2026: brak dźwięku przy
                # szybkich ruchach suwaka). Suwak jest już potwierdzony wyżej,
                # więc ten odczyt nie ogłosi go jako zmiany z innego urządzenia.
                self._zapewnij_swiezosc()
                if not self.stan.polaczony:
                    return
            if zr in self._rozmowcy():
                self._po_zmianie_suwaka(zr, przed, byl_w_gorze)
            elif zr == MIKROFON and self._jest_rozmowa_cue():
                self._dopasuj_zrodlo(MIKROFON)   # rozmowa na CUE: poziom mikrofonu jak na antenie
            # Suwak na stole stoi tam, gdzie mikser potwierdził (puszczony suwak;
            # dotknięty pomija _ustaw_silniki).
            self._ustaw_silniki()

    def _ustaw_silniki(self) -> None:
        if self.powierzchnia is None:
            return
        for pasek, opis in self.u.paski.items():
            zr = opis.get("zrodlo")
            if not zr or pasek in self._dotyk:
                continue
            v = self.stan.wartosc(sciezki.fader(self.u.zrodla[zr].kanaly[0]))
            if v is not NIEZNANY:
                self.powierzchnia.ustaw_suwak(pasek, min(float(v) / self._gora_suwaka(pasek), 1.0))
        v = self.stan.wartosc(sciezki.MONITOR_POZIOM)
        if v is not NIEZNANY and 9 not in self._dotyk:
            self.powierzchnia.ustaw_suwak(9, min(float(v) / ZERO_DB, 1.0))

    def _odswiez_powierzchnie(self) -> None:
        """Diody pokazują stan potwierdzony; NIEZNANY = miganie. Nie są źródłem informacji dla Michała."""
        p = self.powierzchnia
        if p is None:
            return
        for pasek, opis in self.u.paski.items():
            zr = opis.get("zrodlo")
            for i in range(4):
                s = False
                if zr and i == 0 and opis.get("rec") == "alarm_ciszy":
                    s = self.alarm_wlaczony
                elif zr and ((i == 0 and opis.get("rec") == "antena_mikrofonu")
                           or (i == 3 and opis.get("select") == "antena_mikrofonu")):
                    s = self.widok.suma(MIKROFON)
                elif zr and i == 2 and opis.get("mute") == "kaszel":
                    s = self._kaszel is not None
                elif zr and i == 2 and opis.get("mute") == "talkback":
                    s = zr in self._talkback
                elif zr and i == 3 and opis.get("select") == "cue":
                    s = self.widok.cue(zr)
                elif zr and i == 3 and opis.get("select") == "pfl":
                    s = self.widok.pfl(zr)
                p.ustaw_diode(pasek, i, None if s is NIEZNANY else bool(s))
            if zr and self.u.zrodla[zr].galka:
                przes = self._przesuniecie_galki(zr)
                if przes is not NIEZNANY:
                    zakres = float(self.u.zachowanie.get("zakres_galki_db", 12.0))
                    p.ustaw_pierscien(pasek, 0.5 + przes / (2 * zakres))
        m = self.widok.suma(MIKROFON)
        p.ustaw_klawisz("F1_mikrofon", None if m is NIEZNANY else bool(m))

    # ======================================================================
    # program emisyjny
    # ======================================================================
    def _emisja_stan(self) -> None:
        self._tor_emisji.zlec("stan")

    def transport_play(self) -> None:
        self._ost_stop = float("-inf")
        self._tor_emisji.zlec("play")

    def transport_nastepny(self) -> None:
        self._ost_stop = float("-inf")
        self._tor_emisji.zlec("nastepny")

    def transport_stop(self) -> None:
        teraz = self.zegar()
        drugi = teraz - self._ost_stop <= float(self.u.zachowanie.get("drugi_stop_w_ciagu_s", 1.0))
        self._ost_stop = teraz
        self._tor_emisji.zlec("instant" if drugi else "stop")

    def _zlec_hold(self, aktywne) -> None:
        try:
            self._tor_emisji.obserwuj_hold(aktywne)
        except Exception:  # błąd dodatkowego toru nie blokuje mikrofonu
            log.exception("zlecenie wstrzymania automatu")

    def _obserwuj_hold(self) -> None:
        stan = self.widok.suma(MIKROFON)
        if stan is False and self._mikrofon_sprzed is not None:  # HOLD_KASZEL
            stan = any(self._mikrofon_sprzed[a] == 1 for a in self.widok.adresy_sumy(MIKROFON))
        # Rozmówcy z ustawień: Main On, suwak powyżej progu i bez CUE.
        stany = [stan] + [self.widok.na_antenie(z.klucz) for z in self.u.zrodla.values()
                          if z.odbiorca is not None]  # HOLD_ROZMOWCY
        if any(s is True for s in stany):
            self._zlec_hold(True)
        elif all(s is False for s in stany):  # HOLD_ZNANE_ZAMKNIECIE
            self._zlec_hold(False)
        # NIEZNANY bez potwierdzonej anteny zachowuje dotychczasowe wstrzymanie.

    def odbierz_emisje(self) -> None:
        """Tylko gotowe wyniki: żadnego czekania na sieć ani odczytu miksera.
        Woła to wątek playoutu zaraz po wyniku, a tick jako zabezpieczenie."""
        with self._odbior_emisji:
            while True:
                try:
                    tekst, dzwiek, klucz = self._tor_emisji.wyniki.get_nowait()
                except queue.Empty:
                    break
                if klucz.startswith("emisja-hold"):
                    self._hold_wyniki.append((tekst, dzwiek, klucz))
                else:
                    self.powiedz(tekst, Priorytet.STAN, klucz, dzwiek=dzwiek)
            if self._hold_przejscie:
                return
            wyniki, self._hold_wyniki = self._hold_wyniki, []
            for tekst, dzwiek, klucz in wyniki:
                if klucz == "emisja-hold-blad":
                    self.powiedz(tekst, Priorytet.BEZPIECZENSTWO, klucz)
                else:
                    d, mow = (self.informacja.plan(tekst.zdarzenia, Priorytet.STAN) if dzwiek else ([], True))
                    # Kolejka dołącza do potwierdzonego mikrofonu, gdy jeszcze
                    # czeka albo gra jego dźwięk. Późny wynik idzie osobno,
                    # zawsze po mikrofonie i poza przerywalnym kursorem.
                    zd = tekst.zdarzenia[0]
                    wariant = ("wlaczony" if zd == "emisja_automat_wstrzymany" else
                               "wylaczony" if zd.startswith("emisja_automat_zwolniony") else None)
                    dolacz = getattr(self.mowa, "dolacz", None)
                    if not (wariant and dolacz and dolacz(
                            tekst, "mikrofon_stan:" + wariant, dzwieki=d, mow=mow)):
                        self.powiedz(tekst, Priorytet.STAN, klucz, dzwiek=dzwiek)
                    else:
                        self._ostatni = str(tekst)

    def zamknij_emisje(self) -> None:
        self._tor_emisji.zamknij()

    # ======================================================================
    # praca cykliczna: subskrypcja, odczyt krytyczny, zmiany z innych klientów
    # ======================================================================
    def tick(self) -> None:
        self.odbierz_emisje()
        self._koniec_nauki_po_czasie()
        # Ponowne otwarcie portu MIDI po utracie X-TOUCH (co xtouch.ponowienie_portu_s)
        # poza blokadą rdzenia: udany powrót zgłasza zdarzenie przez zglos().
        ponow = getattr(self.powierzchnia, "ponow_otwarcie", None)
        if ponow is not None:
            ponow(self.zegar())  # POPRAWKA MIDI: ponawianie otwarcia portu
        with self._wykonuje:
            self._tick()
            self._obserwuj_hold()

    def _tick(self) -> None:
        teraz = self.zegar()
        if not self.stan.polaczony:
            if teraz - self._ost_proba >= self.okres_ponowienia:
                self._ost_proba = teraz
                self._zgloszenia = queue.SimpleQueue()
                if self.synchronizuj():
                    self.powiedz(self.t("powrot_lacznosci") + ". " + self.tekst_statusu(),
                                 Priorytet.BEZPIECZENSTWO, "lacznosc")
            return
        if teraz - self._ost_xremote >= self.okres_xremote:
            self._ost_xremote = teraz
            self.klient.odnow_subskrypcje()
        if teraz - self._ost_mierniki >= self.okres_miernikow:
            self._odnow_mierniki(teraz)
        self.przetworz_zgloszenia()
        if not self.stan.polaczony:
            return
        if teraz - self._ost_krytyczny >= self.okres_krytyczny:
            self._ost_krytyczny = teraz
            self._odczyt_krytyczny()
        if self.stan.polaczony:
            self._potwierdz_suwaki(teraz)
            self._komunikaty_galek(teraz)
        if self.stan.polaczony:
            self._aktualizuj_liczniki()
            self._przypomnienia(teraz)
            self._alarm_ciszy(teraz)
        self._odswiez_powierzchnie()

    def _suwaki_w_rekach(self) -> set[str]:
        """Suwaki dotknięte albo czekające na potwierdzenie: ich odczyt nie jest zmianą z innego urządzenia."""
        wynik = set()
        for p in set(self._dotyk) | set(self._suwak_ruch):
            zr = self._zrodlo_paska(p) if p != 9 else None
            if zr:
                wynik.update(sciezki.fader(k) for k in self.u.zrodla[zr].kanaly)
        return wynik

    def _odczyt_krytyczny(self) -> None:
        """Odczyt okresowy i odczyt statusu: ogłasza zmiany, wolno mu tylko
        ochronnie zamykać (P02), nigdy otwierać."""
        reczne = self._suwaki_w_rekach()
        adresy = adresy_krytyczne(self.u)
        if self._solo_kaszlu is not None:
            adresy += [a for a in self._solo_kaszlu.oczekiwane if a not in adresy]
        self._odczytaj_i_oglos([a for a in adresy if a not in reczne],
                               krytyczny=True, z_odczytu=True)

    def przetworz_zgloszenia(self) -> None:
        adresy: list[str] = []
        profil = False
        while True:
            try:
                a, v = self._zgloszenia.get_nowait()
            except queue.Empty:
                break
            adresy.append(a)
            profil = profil or self._zmiana_profilu(a, v)
        if not adresy:
            return
        if profil:
            scena = any(a.startswith(("/-snap/", "/snap/")) for a in adresy)
            self.powiedz(self.t("scena_z_innego" if scena else "profil_zmieniony"),
                         Priorytet.BEZPIECZENSTWO, "zmiana-profilu")
            self.stan.zsynchronizowany = False
            if self.synchronizuj(nowa_baza_galek=scena):
                self.powiedz(self.tekst_statusu(), Priorytet.STAN, "status")
            return
        znane = set(wszystkie_adresy_odczytu(self.u))
        if not any(a in znane for a in adresy):
            # Zgłoszenia wyłącznie spoza torów mostka (np. kanał 16 albo efekty
            # ruszane w AOSC): nic do odczytu ani do ogłoszenia. Dawniej przy
            # nieświeżym odczycie każde takie zgłoszenie dawało pełny odczyt
            # krytyczny (Michał, 23.10.2026: sonda na ch16 co sekundę podniosła
            # odczyty z 12 do 40 na minutę). Zmiany profilu obsłużono wyżej.
            return
        reczne = self._suwaki_w_rekach()
        lista = [a for a in dict.fromkeys(adresy) if a in znane and a not in reczne]
        krytyczny = False
        if self.stan.polaczony and self.stan.zsynchronizowany and not self._swiezy():
            # L02: stary odczyt krytyczny odświeżany razem ze zgłoszonymi adresami.
            lista = list(dict.fromkeys(lista + [a for a in adresy_krytyczne(self.u) if a not in reczne]))
            krytyczny = True
        self._odczytaj_i_oglos(lista, krytyczny=krytyczny)

    def _odczytaj_i_oglos(self, adresy: list[str], krytyczny: bool = False, z_odczytu: bool = False) -> None:
        """Świeży odczyt; zmiany względem potwierdzonego stanu są ogłaszane, nie cofane.

        Zgłoszenie /xremote zmiany z innego urządzenia: powroty idą za anteną
        (dopasowanie zamyka i otwiera program za suwakiem). Odczyt okresowy
        i status (z_odczytu, decyzja Michała P02): zmiany są ogłaszane, a zapis
        wolno wykonać wyłącznie jako ochronne zamknięcie niebezpiecznej drogi
        (szyna na Main LR, obce wejście klucza, klucz przy blokującym profilu:
        _profil_po_odczycie i _ochronne_zamkniecia). Bez dopasowania powrotów,
        nigdy otwarcie; powroty dopasuje najbliższe zgłoszenie albo przejście.
        krytyczny: pełny zestaw torów krytycznych, odnawia świeżość (L02)."""
        if not adresy:
            return
        przed = self.widok.migawka()
        stare = {a: self.stan.wartosc(a) for a in adresy}
        try:
            dane = self.klient.odczytaj_wiele(adresy)
        except BrakOdpowiedzi:
            self._utrata("brak odpowiedzi przy odczycie")
            return
        teraz = self.zegar()
        for a, v in dane.items():
            self.stan.potwierdz(a, v, teraz)
        if krytyczny:
            self._ost_swiezy = teraz
        zmienione = [a for a in adresy if (stare[a] is NIEZNANY or not zgodne(stare[a], dane[a]))
                     and not self._przyjmij_echo(a, dane[a])]
        if self._solo_kaszlu is not None and any(a.startswith("/-stat/solosw/") for a in zmienione):
            self._solo_kaszlu.obca_zmiana = True
        g = self._glosniki_talkback
        if g is not None:
            if set(self.widok.adresy_glosnikow()).intersection(zmienione):
                g.przywroc = False
                g.obca_zmiana = True
            if g.obca_zmiana:
                self._przerwij_kaszel()
                return
        if not zmienione:
            return
        if self._mikrofon_sprzed is not None:
            chronione = set(self._mikrofon_sprzed)
            # Wysyłki muzyki przyciszone przez talkback są pod tą samą ochroną
            # co migawka mikrofonu: obcej zmiany nie cofamy na ślepo, tylko
            # przerywamy trzymanie (zlecenie Michała z 26.10.2026).
            muzyka_adresatow = set()
            for r in self._muzyka_przyciszona:
                odb = self.widok.odbiorca(r)
                if odb is None:
                    continue
                for zr in self.widok.muzyka():
                    muzyka_adresatow.update(self.widok.adresy_wysylki(zr, odb))
            chronione |= muzyka_adresatow
            for r in self._rozmowcy():
                chronione.update(self.widok.adresy_sumy(r))
                chronione.update(sciezki.fader(k) for k in self.u.zrodla[r].kanaly)
            if chronione.intersection(zmienione):
                if muzyka_adresatow.intersection(zmienione):
                    # Cudza wartość tej wysyłki jest nowym źródłem prawdy:
                    # po przerwaniu nie odtwarzamy ani migawki, ani celu.
                    self._muzyka_przyciszona.clear()
                    self._muzyka_sprzed.clear()
                self._przerwij_kaszel()
                return  # obce zmiany bez automatycznego odtwarzania dawnych wysyłek
        elif self.widok.cue_chwilowe is not None and self._adresy_mikrofonu().intersection(zmienione):
            # Nowa, jawna obca zmiana mikrofonu po przerwaniu jest nowym
            # źródłem prawdy, nie echem własnego awaryjnego zamknięcia.
            self.widok.cue_chwilowe = None
        if self._profil_po_odczycie(zmienione):
            return
        po = self.widok.migawka()
        self._ucz_poziomow_bazowych(zmienione)
        for klucz in po:
            if przed.get(klucz) != po[klucz] and po[klucz] is not NIEZNANY:
                self.powiedz(self.t("z_innego_urzadzenia", opis=self._opis_zmiany(klucz, po[klucz])),
                             Priorytet.BEZPIECZENSTWO if klucz[0] in ("suma", "rozmowca") else Priorytet.STAN)
        if any(a.endswith("/mix/fader") or a == sciezki.MONITOR_POZIOM for a in zmienione):
            self._ustaw_silniki()
        if z_odczytu:
            # POPRAWKA P02: odczyt okresowy i status bez dopasowania tras,
            # wyłącznie ochronne zamknięcia (np. klucz poza rozmową słuchacza).
            self._ochronne_zamkniecia()
            return
        # Zgłoszenie zmiany z innego urządzenia: powroty idą za anteną (nie
        # cofamy samej zmiany).
        for zr, z in self.u.zrodla.items():
            lr_zm = any(sciezki.lr(k) in zmienione for k in z.kanaly)
            fad_zm = zr in self._rozmowcy() and any(sciezki.fader(k) in zmienione for k in z.kanaly)
            if lr_zm or fad_zm:
                self._dopasuj_zrodlo(zr, obce=True)
            if lr_zm and not z.glos and self._jest_rozmowa_cue():
                self._muzyka_w_sluchawkach_przy_cue(zr)

    def _profil_po_odczycie(self, zmienione: list[str]) -> bool:
        """Profil po zwykłym odczycie (zgłoszenie /xremote albo odczyt okresowy).
        Zwraca prawdę, gdy wykonano pełny odczyt i dalsze ogłaszanie jest zbędne."""
        if any(sciezki.zmienia_profil(a) for a in zmienione):
            # Szyna na Main LR zmieniona bez zgłoszenia /xremote (zgubiony pakiet,
            # wykrył ją odczyt okresowy): jak zmiana routingu, pełny odczyt
            # (kontrakt pkt 8), który liczy profil i zamyka klucz przyciszania.
            self.powiedz(self.t("profil_zmieniony"), Priorytet.BEZPIECZENSTWO, "zmiana-profilu")
            self.stan.zsynchronizowany = False
            if self.synchronizuj():
                self.powiedz(self.tekst_statusu(), Priorytet.STAN, "status")
            return True
        # Inne adresy profilu (np. wysyłka do efektów albo telefon do własnej
        # szyny z innego urządzenia): profil liczony od nowa. Gdy stał się
        # blokujący, klucz przyciszania jest zamykany (plan v22, rozdz. 8).
        # Zniesienie blokady wymaga pełnego odczytu (kontrakt pkt 8), więc
        # zgodny wynik bieżącego odczytu jej nie zdejmuje.
        byl, opis_przed = self.zapora.profil_blokuje, self._opis_blokady
        self._przelicz_profil(oglos=False)
        if byl and not self.zapora.profil_blokuje:
            self.zapora.profil_blokuje, self._opis_blokady = True, opis_przed
        elif self.zapora.profil_blokuje:
            if not byl or self._opis_blokady != opis_przed:
                self._dz("profil", self._opis_blokady, True)
                self.powiedz(self.t("profil_niezgodny", opis=self._opis_blokady),
                             Priorytet.BEZPIECZENSTWO, "profil")
            self._ochronne_zamkniecia()
        return False

    def _opis_zmiany(self, klucz: tuple, wartosc) -> str:
        rodzaj = klucz[0]
        if rodzaj == "suma":
            zr = klucz[1]
            slowo = self.u.stan_slowo(bool(wartosc), self._rodzaj(zr))
            if zr == MIKROFON:
                return self.t("mikrofon_stan", stan=slowo)
            return self.t("suma_stan", nazwa=self._nazwa(zr), stan=slowo)
        if rodzaj == "rozmowca":
            return self._opis_rozmowcy(klucz[1])
        if rodzaj == "wysylka":
            zr, odb = klucz[1], klucz[2]
            return self.t("wysylka_stan", kogo=self.u.zrodla[zr].dopelniacz, do=self.u.odbiorcy[odb].do,
                          stan=self.u.stan_slowo(bool(wartosc), "z"))
        if rodzaj == "wyciszony":
            return self.t("wyciszony_wszedzie" if wartosc else "odciszony", nazwa=self._nazwa(klucz[1]))
        if rodzaj == "glosniki":
            return self.t("glosniki_wyciszone" if wartosc else "glosniki_wlaczone")
        return str(klucz)

    def _ucz_poziomow_bazowych(self, adresy: list[str]) -> None:
        """Nowy poziom włączonej wysyłki z innego urządzenia staje się bazowym
        (plan, rozdz. 3). Muzyka do rozmowy na CUE jest przyciszona, więc jej
        poziom bazowy to odczyt bez przyciszenia."""
        for zr in self.u.zrodla:
            for odb, o in self.u.odbiorcy.items():
                if o.wlasne_zrodlo == zr:
                    continue
                pierwszy = self.widok.adresy_wysylki(zr, odb)[0]
                if pierwszy not in adresy:
                    continue
                v = self.stan.wartosc(pierwszy)
                if v is NIEZNANY or float(v) <= 0.0:
                    continue
                db = poziom_float_na_db(float(v))
                if not self.u.zrodla[zr].glos and self.widok.cue(o.wlasne_zrodlo) is True:
                    db -= self.u.przyciszenie_muzyki_db
                if zr == MIKROFON and self.widok.cue(o.wlasne_zrodlo) is True:
                    if db >= 10.0 - 0.5:
                        continue      # wysyłka na maksimum: poziomu bazowego nie da się odtworzyć
                    db -= self._korekta_mikrofonu_db()
                if abs(db - self.u.poziom_bazowy(zr, odb)) > 0.5:
                    self.u.ustaw_poziom_bazowy(zr, odb, db)
                    self._dz("nowy-poziom-bazowy", zr, odb, db)


def _opis_przesuniecia(przes) -> str:
    przes = int(przes)
    if przes == 0:
        return "zero"
    return f"plus {przes}" if przes > 0 else f"minus {-przes}"
