"""Tryby informacji zwrotnej: mowa, dźwięki, dźwięki z mową (decyzja Michała z 17.10.2026).

Dźwięki dają szybszą informację o zmianie stanu niż mowa. Nie zastępują
ostrzeżeń. Zasady:

  * MOWA: jak przed zmianą, każdy komunikat mową, bez dźwięków.
  * DZWIEKI: komunikat zmiany stanu z odpowiednikiem dźwięku tylko dźwiękiem.
  * DZWIEKI_Z_MOWA (domyślny): dźwięk, a zaraz po nim mowa.

Zdarzenie to klucz komunikatu z pliku ustawień, dla stanów mikrofonu
i rozmówców z wariantem po dwukropku („rozmowca_czeka:telefon”). Mapowanie
zdarzenie -> klucz dźwięku jest w ustawieniach (informacja_zwrotna.zdarzenia),
pliki dźwięków i ich czasy w dzwieki/dzwieki.json.

Mowa zostaje ZAWSZE, w każdym trybie, gdy:
  * komunikat ma priorytet bezpieczeństwa,
  * którakolwiek część komunikatu nie jest komunikatem stanu z listy
    KOMUNIKATY_DZWIEKIEM (lista w kodzie, nie w ustawieniach: ustawienia nie
    mogą odebrać mowy ostrzeżeniu, odmowie, licznikowi ani statusowi),
  * którakolwiek część nie ma dźwięku albo jej dźwięk jest niedostępny,
  * odtwarzanie się nie udało (wtedy mowa zamiast dźwięku).
Ostrzeżenia i odmowy w trybach z dźwiękami dostają dźwięk alarm albo odmowa
z ustawień i zawsze mowę z powodem.

Wyjątek z 25.10.2026: talkback_start/talkback_koniec są osobnymi sygnałami,
nie komunikatami. Grają także w MOWA, nigdy nie dostają zastępczej mowy.
Kaszel nie emituje sygnału. Odmowy, przerwania i statusy zachowują mowę.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from enum import Enum
from pathlib import Path

from .mowa import Priorytet

log = logging.getLogger("mostek.informacja")


class Tryb(str, Enum):
    MOWA = "mowa"
    DZWIEKI = "dzwieki"
    DZWIEKI_Z_MOWA = "dzwieki_z_mowa"


DOMYSLNY = Tryb.DZWIEKI_Z_MOWA
KOLEJNOSC = (Tryb.MOWA, Tryb.DZWIEKI, Tryb.DZWIEKI_Z_MOWA)

# Zdarzenia bez tekstu: decyzja Michała z 25.10.2026. Nie obejmuje ostrzeżeń.
SYGNALY_BEZ_MOWY = frozenset({"talkback_start", "talkback_koniec"})

# Komunikaty zmiany stanu, które w trybie DZWIEKI mogą zabrzmieć tylko
# dźwiękiem. Każdy inny klucz komunikatu (ostrzeżenia, odmowy, liczby
# i liczniki, status F2, gałka, kontroler, profil, ochronne zamknięcia, błędy)
# zawsze ma mowę, także gdy ktoś przypisze mu dźwięk w ustawieniach.
KOMUNIKATY_DZWIEKIEM = frozenset({
    "mikrofon_stan",
    "rozmowa_poza_antena",
    "mikrofon_poza_antena_rozmowa",
    "rozmowca_w_rozmowie",
    "rozmowca_czeka",
    "rozmowca_na_antenie",
    "koniec_rozmowy",
    "glosniki_wlaczone",
    "glosniki_wyciszone",
    "emisja_gra",
    "emisja_stop",
    "emisja_automat_wstrzymany",
    "emisja_automat_zwolniony",
    "emisja_automat_zwolniony_zatrzymane",
    "emisja_automat_zatrzymane",
    "czekam",
    # Michał, 23.10.2026: dźwięk na włączenie i wyłączenie odsłuchu kontrolnego.
    "pfl_stan",
    "koniec_pfl",
})


def baza_zdarzenia(zdarzenie: str) -> str:
    """Klucz komunikatu bez wariantu: „rozmowca_czeka:telefon” -> „rozmowca_czeka”."""
    return zdarzenie.split(":", 1)[0]


def _zdarzenia_czesci(x) -> tuple:
    if isinstance(x, Komunikat):
        return x.zdarzenia
    if isinstance(x, str) and not x.strip(" .,;:"):
        return ()              # sam separator („. ”, „, ”)
    return (None,)             # zwykły tekst bez klucza: część bez dźwięku, zawsze mowa


class Komunikat(str):
    """Tekst komunikatu z listą zdarzeń (kluczy komunikatów z ustawień).

    Ustawienia.tekst zwraca Komunikat z jednym zdarzeniem. Sklejanie przez +
    zachowuje zdarzenia kolejnych części; zwykły tekst bez klucza dokłada
    zdarzenie None, czyli część, która zawsze ma mowę. Inne operacje na
    tekście (np. lower, capitalize, format) dają zwykły str: bez zdarzeń
    komunikat zawsze idzie mową (bezpieczny kierunek)."""

    zdarzenia: tuple = ()

    def __new__(cls, tekst: str, zdarzenia=()):
        o = super().__new__(cls, tekst)
        o.zdarzenia = tuple(zdarzenia)
        return o

    def __add__(self, inny):
        if not isinstance(inny, str):
            return NotImplemented
        return Komunikat(str.__add__(self, inny), self.zdarzenia + _zdarzenia_czesci(inny))

    def __radd__(self, inny):
        if not isinstance(inny, str):
            return NotImplemented
        return Komunikat(str.__add__(inny, self), _zdarzenia_czesci(inny) + self.zdarzenia)

    def wariant(self, wariant: str) -> "Komunikat":
        """Pierwsze zdarzenie z wariantem: „mikrofon_stan” -> „mikrofon_stan:wlaczony”."""
        if not self.zdarzenia or self.zdarzenia[0] is None:
            return self
        return Komunikat(self, (f"{baza_zdarzenia(self.zdarzenia[0])}:{wariant}",) + self.zdarzenia[1:])


def polacz(separator: str, czesci) -> str:
    """Jak separator.join(czesci), ale z zachowaniem zdarzeń części."""
    wynik = None
    for c in czesci:
        wynik = c if wynik is None else wynik + separator + c
    return "" if wynik is None else wynik


def dzwieki_zdarzenia(wartosc) -> list[str]:
    """Wartość mapowania z ustawień: klucz dźwięku albo lista kluczy."""
    if isinstance(wartosc, str):
        return [wartosc]
    return list(wartosc)


# --- odtwarzacze ---------------------------------------------------------------

class AtrapaDzwiekow:
    """Zapisuje klucze odtworzonych dźwięków. Do testów i pracy poza Windows.
    Z podanym strumieniem wypisuje też „[dzwiek] klucz” (konsola symulatora).
    Gra kilka dźwięków naraz jak waveOut: grupy w self.naraz."""

    wiele_glosow = True

    def __init__(self, strumien=None) -> None:
        self.odtworzone: list[str] = []
        self.naraz: list[list[str]] = []
        self.zatrzymania = 0
        self.awaria = False
        self.strumien = strumien

    def odtworz(self, klucz: str, plik: Path) -> None:
        if self.awaria:
            raise RuntimeError("atrapa: symulowana awaria odtwarzania")
        self.odtworzone.append(klucz)
        if self.strumien is not None:
            print(f"[dzwiek] {klucz}", file=self.strumien, flush=True)

    def odtworz_wiele(self, pozycje) -> list:
        wyniki = []
        grupa = []
        for klucz, plik in pozycje:
            try:
                self.odtworz(klucz, plik)
                grupa.append(klucz)
                wyniki.append(None)
            except Exception as e:  # noqa: BLE001
                wyniki.append(e)
        self.naraz.append(grupa)
        return wyniki

    def zatrzymaj(self) -> None:
        self.zatrzymania += 1


class OdtwarzaczWinsound:
    """Windows: winsound.PlaySound z plikiem, asynchronicznie (SND_ASYNC), więc
    wywołanie wraca od razu i nie blokuje ani pętli mostka, ani kolejki mowy.
    SND_NODEFAULT: brak pliku nie daje domyślnego dźwięku systemu.
    Dokumentacja: moduł winsound biblioteki standardowej Pythona."""

    def __init__(self, winsound_mod=None) -> None:
        if winsound_mod is None:
            if sys.platform != "win32":
                raise RuntimeError("winsound działa tylko w Windows")
            import winsound as winsound_mod  # noqa: PLC0415
        self._ws = winsound_mod

    def odtworz(self, klucz: str, plik: Path) -> None:
        ws = self._ws
        ws.PlaySound(str(plik), ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_NODEFAULT)

    def zatrzymaj(self) -> None:
        # Dźwięk None zatrzymuje bieżące odtwarzanie (dokumentacja winsound).
        self._ws.PlaySound(None, 0)


class OdtwarzaczWaveOut:
    """Windows: każdy dźwięk na osobnym wyjściu waveOut (winmm, część
    systemu), więc kilka dźwięków gra naraz, a miksuje je Windows. Bez
    przygotowanych plików z kombinacjami (Michał, 23.10.2026: „a co jeśli
    będzie tych kombinacji jeszcze więcej?”). Pliki WAV PCM są wczytane do
    pamięci raz, wyjście otwierane przy każdym dźwięku na urządzeniu
    domyślnym (WAVE_MAPPER), więc zmiana urządzenia domyślnego działa od razu.
    Wyjścia po zakończonym dźwięku są zamykane przy następnym dźwięku albo
    zatrzymaniu. Dokumentacja: waveOutOpen, waveOutPrepareHeader,
    waveOutWrite, waveOutReset (Windows Multimedia, mmeapi.h)."""

    wiele_glosow = True
    WAVE_MAPPER = 0xFFFFFFFF
    WHDR_DONE = 0x1

    def __init__(self, winmm=None) -> None:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        self._c = ctypes
        if winmm is None:
            if sys.platform != "win32":
                raise RuntimeError("waveOut działa tylko w Windows")
            winmm = ctypes.WinDLL("winmm")

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                        ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                        ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                        ("cbSize", wintypes.WORD)]

        class WAVEHDR(ctypes.Structure):
            pass
        WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                            ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                            ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                            ("lpNext", ctypes.POINTER(WAVEHDR)), ("reserved", ctypes.c_size_t)]
        self._WAVEFORMATEX, self._WAVEHDR = WAVEFORMATEX, WAVEHDR
        uchwyt = ctypes.c_void_p
        mm = winmm
        mm.waveOutOpen.argtypes = [ctypes.POINTER(uchwyt), wintypes.UINT, ctypes.POINTER(WAVEFORMATEX),
                                   ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
        for nazwa in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
            getattr(mm, nazwa).argtypes = [uchwyt, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        mm.waveOutReset.argtypes = [uchwyt]
        mm.waveOutClose.argtypes = [uchwyt]
        for nazwa in ("waveOutOpen", "waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite",
                      "waveOutReset", "waveOutClose"):
            getattr(mm, nazwa).restype = wintypes.UINT
        self._mm = mm
        self._pamiec: dict[str, tuple] = {}
        self._aktywne: list[tuple] = []          # (uchwyt, nagłówek, bufor)
        self._blokada = threading.Lock()

    def _wczytaj(self, plik: Path):
        klucz = str(plik)
        if klucz not in self._pamiec:
            import wave  # noqa: PLC0415
            with wave.open(klucz, "rb") as w:
                kan, szer, fs = w.getnchannels(), w.getsampwidth(), w.getframerate()
                dane = w.readframes(w.getnframes())
            fmt = self._WAVEFORMATEX(1, kan, fs, fs * kan * szer, kan * szer, 8 * szer, 0)
            self._pamiec[klucz] = (fmt, self._c.create_string_buffer(dane, len(dane)))
        return self._pamiec[klucz]

    def _zamknij(self, wpis) -> None:
        uchwyt, naglowek, _ = wpis
        rozmiar = self._c.sizeof(naglowek)
        self._mm.waveOutUnprepareHeader(uchwyt, self._c.byref(naglowek), rozmiar)
        self._mm.waveOutClose(uchwyt)

    def _sprzatnij(self) -> None:
        zostaja = []
        for wpis in self._aktywne:
            if wpis[1].dwFlags & self.WHDR_DONE:
                self._zamknij(wpis)
            else:
                zostaja.append(wpis)
        self._aktywne = zostaja

    def odtworz_wiele(self, pozycje) -> list:
        """pozycje: [(klucz, plik)]. Najpierw otwiera wszystkie wyjścia, potem
        wysyła dźwięki jeden po drugim bez przerwy, więc ruszają razem. Zwraca
        listę wyjątków (None = dźwięk ruszył) w kolejności pozycji."""
        c, mm = self._c, self._mm
        with self._blokada:
            self._sprzatnij()
            gotowe, wyniki = [], []
            for _, plik in pozycje:
                try:
                    fmt, bufor = self._wczytaj(plik)
                    uchwyt = c.c_void_p()
                    kod = mm.waveOutOpen(c.byref(uchwyt), self.WAVE_MAPPER, c.byref(fmt), 0, 0, 0)
                    if kod:
                        raise OSError(f"waveOutOpen zwróciło kod {kod}")
                    naglowek = self._WAVEHDR()
                    naglowek.lpData = c.cast(bufor, c.c_void_p)
                    naglowek.dwBufferLength = len(bufor)
                    kod = mm.waveOutPrepareHeader(uchwyt, c.byref(naglowek), c.sizeof(naglowek))
                    if kod:
                        mm.waveOutClose(uchwyt)
                        raise OSError(f"waveOutPrepareHeader zwróciło kod {kod}")
                    gotowe.append((uchwyt, naglowek, bufor))
                    wyniki.append(None)
                except Exception as e:  # noqa: BLE001
                    gotowe.append(None)
                    wyniki.append(e)
            for i, wpis in enumerate(gotowe):
                if wpis is None:
                    continue
                kod = mm.waveOutWrite(wpis[0], c.byref(wpis[1]), c.sizeof(wpis[1]))
                if kod:
                    self._zamknij(wpis)
                    wyniki[i] = OSError(f"waveOutWrite zwróciło kod {kod}")
                else:
                    self._aktywne.append(wpis)
            return wyniki

    def odtworz(self, klucz: str, plik: Path) -> None:
        blad = self.odtworz_wiele([(klucz, plik)])[0]
        if blad is not None:
            raise blad

    def zatrzymaj(self) -> None:
        with self._blokada:
            for wpis in self._aktywne:
                self._mm.waveOutReset(wpis[0])
                self._zamknij(wpis)
            self._aktywne = []


def utworz_odtwarzacz(strumien=None, *, konsola=False):
    if sys.platform == "win32" and not konsola:
        try:
            return OdtwarzaczWaveOut()
        except Exception:  # noqa: BLE001
            log.warning("waveOut niedostępny, dźwięki po kolei przez winsound", exc_info=True)
        try:
            return OdtwarzaczWinsound()
        except Exception:  # noqa: BLE001
            log.warning("winsound niedostępny, dźwięki tylko w dzienniku")
    return AtrapaDzwiekow(strumien)


# --- tryb i plan komunikatu ------------------------------------------------------

class InformacjaZwrotna:
    def __init__(self, u, odtwarzacz) -> None:
        cfg = getattr(u, "informacja", {}) or {}
        self.odtwarzacz = odtwarzacz
        self.plik_trybu = Path(u.plik_trybu)
        self.mapa: dict[str, list[str]] = {z: dzwieki_zdarzenia(v) for z, v in cfg.get("zdarzenia", {}).items()
                                           if not z.startswith("_")}
        katalog = Path(cfg.get("katalog_dzwiekow", "dzwieki"))
        if not katalog.is_absolute():
            from .ustawienia import KATALOG  # noqa: PLC0415
            katalog = KATALOG / katalog
        self.katalog = katalog
        self.dzwiek_ostrzezenia = cfg.get("dzwiek_ostrzezenia", "alarm")
        # Michał, 23.10.2026: dźwięki jednego komunikatu grają naraz, nie po
        # kolei. Działa, gdy odtwarzacz ma kilka głosów (waveOut, atrapa);
        # winsound gra jeden plik naraz, więc z nim zostaje kolejno.
        self.naraz = bool(cfg.get("dzwieki_naraz", True)) and bool(getattr(odtwarzacz, "wiele_glosow", False))
        self.dzwieki: dict[str, tuple[Path, float]] = {}
        self._ostrzezone: set[str] = set()
        self._wczytaj_dzwieki()
        self.tryb = self._wczytaj_tryb()

    # --- dźwięki ------------------------------------------------------------
    def _ostrzez_raz(self, klucz: str, tekst: str, *arg) -> None:
        if klucz in self._ostrzezone:
            return
        self._ostrzezone.add(klucz)
        log.warning(tekst, *arg)

    def _wczytaj_dzwieki(self) -> None:
        opis = self.katalog / "dzwieki.json"
        try:
            dane = json.loads(opis.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._ostrzez_raz("*", "brak zestawu dźwięków %s (%s)", opis, e)
            return
        for klucz, d in dane.items():
            try:
                plik, czas = self.katalog / str(d["plik"]), float(d.get("czas_s", 0.3))
            except (KeyError, TypeError, ValueError):
                self._ostrzez_raz(klucz, "dźwięk %s: zły opis w dzwieki.json, dźwięk pominięty", klucz)
                continue
            if not plik.is_file():
                self._ostrzez_raz(klucz, "brak pliku dźwięku %s: dźwięk pominięty", plik)
                continue
            self.dzwieki[klucz] = (plik, czas)
        for zdarzenie, klucze in self.mapa.items():
            for k in klucze:
                if k not in self.dzwieki and k not in dane:
                    self._ostrzez_raz(k, "zdarzenie %s: nieznany dźwięk %s, dźwięk pominięty", zdarzenie, k)

    def dostepny(self, klucz: str) -> bool:
        return klucz in self.dzwieki

    def czas(self, klucz: str) -> float:
        return self.dzwieki[klucz][1]

    def odtworz(self, klucz: str) -> float | None:
        """Odtwarza dźwięk asynchronicznie. Zwraca jego czas albo None, gdy
        dźwięku nie ma albo odtwarzanie się nie udało (wtedy mowa zamiast
        dźwięku, jedno ostrzeżenie w dzienniku na klucz)."""
        wpis = self.dzwieki.get(klucz)
        if wpis is None:
            self._ostrzez_raz(klucz, "brak dźwięku %s: dźwięk pominięty", klucz)
            return None
        try:
            self.odtwarzacz.odtworz(klucz, wpis[0])
        except Exception as e:  # noqa: BLE001 - błąd dźwięku nie wywraca mostka
            self._ostrzez_raz("blad:" + klucz, "nie udało się odtworzyć dźwięku %s (%s): dźwięk pominięty",
                              klucz, e)
            return None
        return wpis[1]

    def odtworz_naraz(self, klucze) -> tuple[float | None, bool]:
        """Wszystkie dźwięki komunikatu naraz. Zwraca (czas najdłuższego
        dźwięku, który ruszył, albo None; czy któryś zawiódł). Zawiedziony
        dźwięk: mowa zamiast niego, jedno ostrzeżenie w dzienniku na klucz."""
        pozycje, braki = [], False
        for k in klucze:
            wpis = self.dzwieki.get(k)
            if wpis is None:
                self._ostrzez_raz(k, "brak dźwięku %s: dźwięk pominięty", k)
                braki = True
            else:
                pozycje.append((k, wpis[0], wpis[1]))
        if not pozycje:
            return None, True
        try:
            wyniki = self.odtwarzacz.odtworz_wiele([(k, p) for k, p, _ in pozycje])
        except Exception as e:  # noqa: BLE001 - błąd dźwięku nie wywraca mostka
            wyniki = [e] * len(pozycje)
        czas = None
        for (k, _, t), blad in zip(pozycje, wyniki):
            if blad is None:
                czas = t if czas is None else max(czas, t)
            else:
                braki = True
                self._ostrzez_raz("blad:" + k, "nie udało się odtworzyć dźwięku %s (%s): dźwięk pominięty",
                                  k, blad)
        return czas, braki

    def zatrzymaj(self) -> None:
        try:
            self.odtwarzacz.zatrzymaj()
        except Exception:  # noqa: BLE001
            log.debug("zatrzymanie dźwięku nie powiodło się", exc_info=True)

    # --- plan komunikatu --------------------------------------------------------
    def plan(self, zdarzenia, priorytet: Priorytet, tryb: Tryb | None = None) -> tuple[list[str], bool]:
        """(klucze dźwięków, czy mówić) dla komunikatu w bieżącym trybie.

        zdarzenia: po jednym na część komunikatu; None = część bez zdarzenia.
        Brak zdarzeń: sama mowa."""
        tryb = self.tryb if tryb is None else tryb
        if tryb is Tryb.MOWA or not zdarzenia:
            return [], True
        dzwieki: list[str] = []
        mow = tryb is Tryb.DZWIEKI_Z_MOWA or priorytet == Priorytet.BEZPIECZENSTWO  # POPRAWKA: ostrzeżenie zawsze mową
        for z in zdarzenia:
            klucze = self.mapowanie(z)
            if klucze is None:
                mow = True                      # część bez dźwięku: zawsze mowa
                continue
            if baza_zdarzenia(z) not in KOMUNIKATY_DZWIEKIEM:  # POPRAWKA: tylko stany bez mowy
                mow = True
            for k in klucze:
                if self.dostepny(k):
                    dzwieki.append(k)
                else:
                    mow = True                  # brak pliku: dźwięk pominięty
        if not dzwieki:
            mow = True
        return dzwieki, mow

    def plan_sygnalu(self, zdarzenie: str) -> list[str]:
        """Sygnał potwierdzenia niezależny od trybu, bez zastępczej mowy."""
        if zdarzenie not in SYGNALY_BEZ_MOWY:
            raise ValueError(f"nieznany sygnał bez mowy: {zdarzenie}")
        klucze = self.mapowanie(zdarzenie)
        if not klucze:
            self._ostrzez_raz("sygnal:" + zdarzenie, "brak mapowania sygnału %s, bez zastępczej mowy", zdarzenie)
            return []
        gotowe = []
        for k in klucze:
            if self.dostepny(k):
                gotowe.append(k)
            else:
                self._ostrzez_raz("sygnal:" + k, "brak dźwięku sygnału %s, bez zastępczej mowy", k)
        return gotowe

    def mapowanie(self, zdarzenie) -> list[str] | None:
        """Klucze dźwięków zdarzenia: najpierw z wariantem, potem sam klucz komunikatu."""
        if zdarzenie is None:
            return None
        if zdarzenie in self.mapa:
            return self.mapa[zdarzenie]
        return self.mapa.get(baza_zdarzenia(zdarzenie))

    def plan_ostrzezenia(self, zdarzenia, priorytet: Priorytet, tryb: Tryb | None = None) -> list[str]:
        """Dźwięk przed komunikatem, który zawsze ma mowę (ostrzeżenie, odmowa,
        status): w trybach z dźwiękami pierwsze zdarzenie spoza listy stanów,
        które ma dźwięk w ustawieniach (np. odmowa), albo dźwięk ostrzeżenia
        (alarm) dla priorytetu bezpieczeństwa. Pusta lista w ustawieniach = bez
        dźwięku (np. dobra wiadomość: łączność przywrócona)."""
        tryb = self.tryb if tryb is None else tryb
        if tryb is Tryb.MOWA:
            return []
        for z in zdarzenia or ():
            klucze = self.mapowanie(z)
            if klucze is None or baza_zdarzenia(z) in KOMUNIKATY_DZWIEKIEM:
                continue
            return [k for k in klucze if self.dostepny(k)]
        if priorytet == Priorytet.BEZPIECZENSTWO and self.dzwiek_ostrzezenia \
                and self.dostepny(self.dzwiek_ostrzezenia):
            return [self.dzwiek_ostrzezenia]
        return []

    # --- tryb ---------------------------------------------------------------------
    def _wczytaj_tryb(self) -> Tryb:
        try:
            tekst = self.plik_trybu.read_text(encoding="utf-8")
        except FileNotFoundError:
            return DOMYSLNY
        except OSError as e:
            log.warning("nie odczytano trybu informacji zwrotnej z %s (%s): tryb domyślny %s",
                        self.plik_trybu, e, DOMYSLNY.value)
            return DOMYSLNY
        try:
            return Tryb(json.loads(tekst)["tryb"])
        except (ValueError, KeyError, TypeError):
            log.warning("uszkodzony albo nieznany tryb informacji zwrotnej w %s: tryb domyślny %s",
                        self.plik_trybu, DOMYSLNY.value)
            return DOMYSLNY

    def zapisz_tryb(self) -> bool:
        """Zapis atomowy: plik tymczasowy, potem os.replace."""
        tymczasowy = self.plik_trybu.with_name(self.plik_trybu.name + ".tmp")
        try:
            self.plik_trybu.parent.mkdir(parents=True, exist_ok=True)
            tymczasowy.write_text(json.dumps({"tryb": self.tryb.value}) + "\n", encoding="utf-8")
            os.replace(tymczasowy, self.plik_trybu)
        except OSError as e:
            log.warning("nie zapisano trybu informacji zwrotnej w %s: %s", self.plik_trybu, e)
            return False
        return True

    def przelacz(self) -> tuple[Tryb, bool]:
        """F4: następny tryb w kolejności MOWA -> DZWIEKI -> DZWIEKI_Z_MOWA -> MOWA.
        Zwraca nowy tryb i to, czy zapis się udał."""
        self.tryb = KOLEJNOSC[(KOLEJNOSC.index(self.tryb) + 1) % len(KOLEJNOSC)]
        log.info("tryb informacji zwrotnej: %s", self.tryb.value)
        return self.tryb, self.zapisz_tryb()
