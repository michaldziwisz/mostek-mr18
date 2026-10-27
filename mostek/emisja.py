"""Playout lokalny: SPL Pro/SARA przez TCP, zapas SPL przez SendMessage.

Protokół TCP: pomoc SPLStudio.chm, opt_comms.html i opt_commtcp.html.
Nieznane polecenie SPL uruchamia skrypt, dlatego każde wyjście przechodzi
przez zamkniętą listę. TrackInfoEx dopiero po Helo identyfikującym SARĘ.
Akcje nie są ponawiane po wysłaniu (timeout nie dowodzi braku wykonania).

API okna: dodatek NVDA ChrisDuffley/stationPlaylist, splcommon/splbase.py
oraz globalPlugins/splUtils.py: WM_USER, odtwórz 12, stop 13 (0 fade, 1
natychmiast), następny 14, stan 104. To zapas tylko dla play/stop/stanu.
"""

from __future__ import annotations

import csv
import re
import socket
import sys
import time
from dataclasses import dataclass

WM_USER = 1024
SPL_ODTWORZ = 12
SPL_STOP = 13
SPL_NASTEPNY = 14
SPL_PAUZA = 15
SPL_AUTOMATYZACJA = 16
SPL_STAN_ODTWARZANIA = 104
KLASA_OKNA = "splstudio"   # jak w splbase.py: FindWindowW("splstudio", None)
SMTO_ABORTIFHUNG = 0x0002
LIMIT_ODPOWIEDZI_MS = 500


class ProgramEmisyjny:
    """Interfejs dla mostka. Metody zgłaszają NotImplementedError, gdy brak."""

    nazwa = "program emisyjny"

    def polacz_miks(self):
        """Trwałe połączenie tylko do sesji Mix*. Nigdy zapas SPL."""
        raise WymagaSary

    def odtworz(self) -> None:
        raise NotImplementedError

    def wykonaj(self, akcja: str, kierunek: int = 0):
        """Zapas okienkowy i atrapy; wykonywane wyłącznie w wątku emisji."""
        if akcja in ("hold", "hold_odczyt"):
            return None  # adapter bez rozszerzenia SARY: także bez SendMessage
        if akcja == "odtwarzacz":
            raise WymagaSary
        metody = {"play": self.odtworz, "stop": self.stop_wyciszenie,
                  "instant": self.stop_natychmiast}
        if akcja in metody:
            metody[akcja]()
        elif akcja != "stan":
            raise WymagaTCP
        s = self.stan()
        if s is None:
            raise BladEmisji("brak stanu")
        return Odczyt(stan=s)

    def start_nastepnego(self) -> None:
        raise NotImplementedError

    def stop_wyciszenie(self) -> None:
        raise NotImplementedError

    def stop_natychmiast(self) -> None:
        raise NotImplementedError

    def stan(self) -> str | None:
        """'gra', 'pauza', 'stop' albo None, gdy program nie odpowiada."""
        raise NotImplementedError


class StationPlaylist(ProgramEmisyjny):
    nazwa = "StationPlaylist"

    def __init__(self, wyslij_komunikat=None) -> None:
        """`wyslij_komunikat(wparam, lparam) -> int | None`; domyślnie user32 (Windows)."""
        self._wyslij = wyslij_komunikat or _sendmessage_windows()

    def _api(self, wparam: int, lparam: int):
        return self._wyslij(wparam, lparam)

    def start_nastepnego(self) -> None:
        self._api(0, SPL_NASTEPNY)

    def odtworz(self) -> None:
        self._api(0, SPL_ODTWORZ)

    def stop_wyciszenie(self) -> None:
        self._api(0, SPL_STOP)

    def stop_natychmiast(self) -> None:
        self._api(1, SPL_STOP)

    def stan(self) -> str | None:
        v = self._api(0, SPL_STAN_ODTWARZANIA)
        if v is None:
            return None
        if v == 0:
            return "stop"
        if v == 3:
            return "pauza"
        return "gra"


class BrakStationPlaylist(RuntimeError):
    pass


def _sendmessage_windows():
    if sys.platform != "win32":
        def brak(_w, _l):
            return None
        return brak
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    user32 = ctypes.WinDLL("user32")
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    # SendMessageTimeoutW zamiast SendMessageW: zawieszone Studio nie może
    # zawiesić mostka (zwykłe SendMessage czeka bez końca na odpowiedź okna).
    user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                           wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                           ctypes.POINTER(ctypes.c_size_t)]
    user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t

    def wyslij(wparam: int, lparam: int):
        okno = user32.FindWindowW(KLASA_OKNA, None)
        if not okno:
            return None
        wynik = ctypes.c_size_t(0)
        ok = user32.SendMessageTimeoutW(okno, WM_USER, wparam, lparam,
                                        SMTO_ABORTIFHUNG, LIMIT_ODPOWIEDZI_MS, ctypes.byref(wynik))
        if not ok:
            return None          # przekroczony czas albo okno zawieszone
        # Jak w dodatku NVDA: po wywołaniu sprawdzamy, czy okno nadal istnieje.
        if not user32.FindWindowW(KLASA_OKNA, None):
            return None
        return ctypes.c_int32(wynik.value & 0xFFFFFFFF).value

    return wyslij


def _okno_spl_windows():
    """Funkcja: czy istnieje okno Studio (klasa splstudio). None poza Windows,
    gdzie nie da się tego sprawdzić; wtedy mostek pyta SPL jak dotąd."""
    if sys.platform != "win32":
        return lambda: None
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    user32 = ctypes.WinDLL("user32")
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    return lambda: bool(user32.FindWindowW(KLASA_OKNA, None))


class AtrapaEmisji(ProgramEmisyjny):
    nazwa = "atrapa"

    def __init__(self) -> None:
        self.polecenia: list[str] = []
        self._stan = "stop"
        self.odpowiada = True

    def odtworz(self) -> None:
        self.polecenia.append("play")
        self._stan = "gra"

    def start_nastepnego(self) -> None:
        self.polecenia.append("nastepny")
        self._stan = "gra"

    def stop_wyciszenie(self) -> None:
        self.polecenia.append("stop_wyciszenie")
        self._stan = "stop"

    def stop_natychmiast(self) -> None:
        self.polecenia.append("stop_natychmiast")
        self._stan = "stop"

    def stan(self) -> str | None:
        return self._stan if self.odpowiada else None


class BladEmisji(RuntimeError):
    """Brak wiarygodnej odpowiedzi; nie jest potwierdzeniem wykonania."""


class BledneDaneOdtwarzaczy(BladEmisji):
    """Players odpowiedziało, ale nie podało kanonicznej listy numerów."""


class WymagaTCP(BladEmisji):
    pass


class WymagaSary(BladEmisji):
    pass


class BrakProgramu(BladEmisji):
    pass


class NiePolaczono(BladEmisji):
    """Nic nie przyjęło połączenia: program zamknięty (na stanowisku port
    zamkniętej SARY milczy do limitu zamiast odmówić). Żadne polecenie nie
    zostało wysłane, więc nie ma niepotwierdzonego skutku."""


@dataclass(frozen=True)
class Utwor:
    indeks: int
    artysta: str
    tytul: str
    czas: str
    zaznaczony: bool | None = None
    status: str = ""
    przerwa: bool | None = None
    numer: int | None = None   # numer dla człowieka; indeks protokołu bez zmian


@dataclass(frozen=True)
class Odczyt:
    stan: str = "stop"
    automat: bool = False
    teraz: str = ""
    nastepny: str = ""
    pozostalo_ms: int = 0
    utwor: Utwor | None = None
    znacznik_przelaczony: bool = False
    odtwarzacze: tuple[int, ...] = ()


def dozwolone_polecenie(polecenie: str, sara: bool = False) -> bool:
    """Jedna linia, bez dowolnych skryptów, ścieżek ani wstrzyknięć separatorów."""
    p = polecenie.lower()
    if p == "players":
        return sara  # PLAYERS_TYLKO_SARA
    if p in {"hold", "hold=0", "hold=1"}:
        return sara
    if p.startswith("mix"):
        if not sara:  # MIX_TYLKO_SARA
            return False
        if p in {"mixopen", "mixinfo", "mixset", "mixclear", "mixundo", "mixsave",
                 "mixcancel", "mixplay", "mixplaypoint", "mixplaymix", "mixstop"}:
            return True
        if re.fullmatch(r"mixpos=[+@-][0-9]+(?:\.[0-9]+)?", p):
            return True
        if re.fullmatch(r"mixnudge=[+-][0-9]+(?:\.[0-9]+)?", p):
            return True
        return bool(re.fullmatch(r"mixpoint=(?:next|prev|cue|intro|outro|segue|segue_fade|overlap|loop_start|loop_end)", p))
    if p in {"helo", "stat", "play", "skip", "stop", "instant stop", "pause",
             "autoon", "autooff", "auto", "this", "next", "rem", "elap",
             "selectindex", "currindex", "lastindex", "checktoggle"}:
        return True
    if re.fullmatch(r"selectindex=(?:[0-9]{1,9}|[+-])", p):
        return True
    m = re.fullmatch(r"(trackinfo|trackinfoex)=([0-9]{1,9})-([0-9]{1,9})", p)
    return bool(m and (m[1] == "trackinfo" or sara) and int(m[2]) <= int(m[3]))


@dataclass(frozen=True)
class Wstrzymanie:
    aktywne: bool
    stan: str


class SesjaTCP:
    """Jedna operacja użytkownika, jedno gniazdo. Po awarii następna ma nowe.

    Limit dotyczy CAŁEJ linii, nie pojedynczego recv (ochrona przed serwerem
    wysyłającym po jednym bajcie). Ograniczone także rozmiar i cała operacja.
    """
    def __init__(self, port: int, limit_s: float = 0.5, kodowanie: str = "utf-8"):
        if not 1 <= int(port) <= 65535 or not 0 < limit_s <= 0.5:
            raise ValueError("nieprawidłowy port lub limit odpowiedzi emisji")
        self.limit_s = limit_s
        self.kodowanie = kodowanie
        self.termin = time.monotonic() + 3.0
        self.bufor = b""
        self.helo = ""
        self.sara = False
        try:
            self.g = socket.create_connection(("127.0.0.1", int(port)), timeout=limit_s)
        except OSError as e:
            raise NiePolaczono(str(e)) from e
        try:
            self.helo = self.pytaj("Helo")
            self.sara = self.helo.startswith("SARA")
            if not (self.sara or self.helo.startswith("StationPlaylist Studio v")):
                raise BladEmisji("nieznana odpowiedź Helo")
        except Exception:
            self.zamknij()
            raise

    def zamknij(self):
        self.g.close()

    def _czas(self, termin):
        zostalo = min(termin, self.termin) - time.monotonic()
        if zostalo <= 0:
            raise TimeoutError("limit odpowiedzi programu emisyjnego")
        self.g.settimeout(zostalo)  # ZAPORA_EMISJI_LIMIT

    def wyslij(self, polecenie):
        if not dozwolone_polecenie(polecenie, self.sara):  # ZAPORA_EMISJI_POLECENIA
            raise ValueError("polecenie spoza bezpiecznego podzbioru SPL/SARA")
        self._czas(time.monotonic() + self.limit_s)
        self.g.sendall((polecenie + "\n").encode("ascii"))

    def linia(self, termin=None):
        termin = termin if termin is not None else time.monotonic() + self.limit_s
        while b"\n" not in self.bufor:
            self._czas(termin)
            cz = self.g.recv(4096)
            if not cz:
                raise BladEmisji("program zamknął połączenie")
            self.bufor += cz
            if len(self.bufor) > 65536:
                raise BladEmisji("odpowiedź zbyt długa")
        w, self.bufor = self.bufor.split(b"\n", 1)
        tekst = w.rstrip(b"\r").decode(self.kodowanie)
        return tekst

    def pytaj(self, polecenie):
        self.wyslij(polecenie)
        tekst = self.linia()
        # Metadane są dowolnym tekstem: np. artysta ERRA nie jest błędem.
        if polecenie not in ("This", "Next") and tekst.startswith("ERR "):
            raise BladEmisji(tekst)
        return tekst

    def akcja(self, polecenie):
        # SPL może nie wysłać ACK przy pustym Send Response. Helo to bariera
        # kolejności, nie potwierdzenie zmiany stanu. Nie łączymy '=' z przecinkiem.
        self.wyslij(polecenie)
        self.wyslij("Helo")
        termin = time.monotonic() + self.limit_s
        for _ in range(8):
            tekst = self.linia(termin)
            if tekst.startswith("ERR "):
                raise BladEmisji(tekst)
            if tekst == self.helo:
                return
        raise BladEmisji("nieoczekiwane odpowiedzi po poleceniu")

    def stat(self):
        s = self.pytaj("Stat")
        # Pomoc SPL opisuje 7 cyfr, ale SPL Studio 6.20 Michała odpowiada
        # ośmioma (pomiar 24.10.2026: „00000010”). Znaczenie mają pierwsze
        # cyfry z pomocy; dalsze przyjmujemy bez interpretacji.
        if not re.fullmatch(r"[01]{7,16}", s):
            raise BladEmisji("Stat nie zawiera co najmniej siedmiu bitów")
        return ("pauza" if s[4] == "1" else "gra" if s[0] == "1" else "stop", s[1] == "1")

    def indeks(self, polecenie):
        s = self.pytaj(polecenie)
        if not re.fullmatch(r"-1|[0-9]{1,9}", s):
            raise BladEmisji("nieprawidłowy indeks")
        return int(s)

    def utwor(self, stan):
        n = self.indeks("SelectIndex")
        if n < 0:
            return None
        if self.sara:
            p = self.pytaj(f"TrackInfoEx={n}-{n}").split("|")
            if (len(p) != 7 or p[0] != str(n) or p[1] not in ("0", "1")
                    or p[2] not in ("pending", "playing", "paused", "played")
                    or p[6] not in ("0", "1") or not p[5].isdigit()):
                raise BladEmisji("nieprawidłowe TrackInfoEx")
            m, s = divmod(int(p[5]) // 1000, 60)
            status = p[2]
            # Nawet TrackInfoEx nie daje prawa ogłaszać „gra”, gdy Stat temu przeczy.
            if status == "playing" and stan != "gra":
                status = ""
            return Utwor(n, p[3], p[4], f"{m}:{s:02d}", p[1] == "1", status, p[6] == "1", n + 1)
        p = next(csv.reader([self.pytaj(f"TrackInfo={n}-{n}")], strict=True))
        if len(p) != 10 or p[0] != str(n):
            raise BladEmisji("nieprawidłowe TrackInfo")
        # SPL nie zwraca checkboxa ani historii zagrań; nie rekonstruujemy ich.
        grajacy = self.indeks("CurrIndex")
        if p[1] == "4":
            # Hour Marker (typ 4 w SPL 6.20): artystą jest linia myślników,
            # do mowy idzie tylko opis godziny z tytułu.
            p[2] = ""
        # SPL 6.20 podaje Duration w milisekundach (pomiar: 317000).
        czas = p[5]
        if czas.isdigit():
            m, sek = divmod(int(czas) // 1000, 60)
            czas = f"{m}:{sek:02d}"
        return Utwor(n, p[2], p[3], czas, status="playing" if stan == "gra" and n == grajacy else "")

    def odtwarzacze(self):
        # Bez Stat/This/Rem: Players opisuje wszystkie grające odtwarzacze
        # głównej playlisty, także w czasie nakładania się utworów.
        self.wyslij("Players")
        try:
            tekst = self.linia()
        except UnicodeError as e:
            raise BledneDaneOdtwarzaczy("nieprawidłowe kodowanie Players") from e
        if tekst == "-":
            return ()
        if not re.fullmatch(r"[1-9][0-9]*(?:,[1-9][0-9]*)*", tekst):
            raise BledneDaneOdtwarzaczy("nieprawidłowa lista Players")
        try:
            numery = tuple(int(n) for n in tekst.split(","))
        except ValueError as e:
            raise BledneDaneOdtwarzaczy("nieprawidłowy numer Players") from e
        if any(a >= b for a, b in zip(numery, numery[1:])):
            raise BledneDaneOdtwarzaczy("numery Players nie są rosnące")
        return numery

    def wykonaj(self, akcja, kierunek=0):
        if akcja == "odtwarzacz":
            if not self.sara:
                raise WymagaSary
            return Odczyt(odtwarzacze=self.odtwarzacze())
        if akcja in ("hold", "hold_odczyt"):
            if not self.sara:  # HOLD_TYLKO_SARA
                return None
            if akcja == "hold" and kierunek not in (0, 1):
                raise ValueError("Hold wymaga 0 albo 1")
            p = "Hold" if akcja == "hold_odczyt" else f"Hold={int(kierunek)}"
            odpowiedz = self.pytaj(p)
            m = re.fullmatch(r"([01]),(brak|trzyma|zatrzymane|za_pozno)", odpowiedz)
            if not m or (akcja == "hold" and int(m[1]) != kierunek):
                raise BladEmisji("niepotwierdzone Hold")
            return Wstrzymanie(m[1] == "1", m[2])
        polecenia = {"play": "Play", "stop": "Stop", "instant": "Instant Stop", "automat": "Auto", "nastepny": "Skip"}
        przelaczony = False
        if akcja in polecenia:
            self.akcja(polecenia[akcja])
        elif akcja == "ruch":
            if kierunek not in (-1, 1):
                raise ValueError("kierunek musi wynosić -1 albo 1")
            self.akcja("SelectIndex=" + ("+" if kierunek > 0 else "-"))
        elif akcja == "znacznik":
            if self.indeks("SelectIndex") >= 0:
                self.akcja("CheckToggle")
                przelaczony = True
        elif akcja not in ("stan", "co_gra", "utwor", "pozostalo"):
            raise ValueError("nieznana akcja emisji")
        stan, auto = self.stat()
        # SPL 6.20 (pomiar 24.10.2026) na This przy ciszy nie odpowiada wcale,
        # więc pytamy o bieżący utwór tylko, gdy Stat mówi, że coś gra.
        cos_gra = stan in ("gra", "pauza")
        if akcja == "nastepny":
            return Odczyt(stan, auto, teraz=self.pytaj("This") if cos_gra else "")
        if akcja == "pozostalo":
            # Stat/Rem dotyczą anteny, nie kursora ani sesji odsłuchu Mix*.
            # Przy stop/pauzie nie pytaj o niegrający utwór i nie ogłaszaj czasu.
            if stan != "gra":
                return Odczyt(stan, auto)
            rem = self.pytaj("Rem")
            if not re.fullmatch(r"-?[0-9]{1,12}", rem):
                raise BladEmisji("nieprawidłowe Rem")
            return Odczyt(stan, auto, pozostalo_ms=max(0, int(rem)))
        if akcja == "co_gra":
            teraz = self.pytaj("This") if cos_gra else ""
            nastepny = self.pytaj("Next")
            rem = self.pytaj("Rem")
            if not re.fullmatch(r"-?[0-9]{1,12}", rem):
                raise BladEmisji("nieprawidłowe Rem")
            return Odczyt(stan, auto, teraz, nastepny, max(0, int(rem)))
        if akcja in ("ruch", "utwor", "znacznik"):
            return Odczyt(stan, auto, utwor=self.utwor(stan), znacznik_przelaczony=przelaczony)
        return Odczyt(stan, auto)


class ProgramTCP(ProgramEmisyjny):
    def __init__(self, port, limit_s=0.5, kodowanie="utf-8"):
        self.port, self.limit_s, self.kodowanie = port, limit_s, kodowanie

    def polacz(self):
        s = SesjaTCP(self.port, self.limit_s, self.kodowanie)
        if s.sara != (self.nazwa == "SARA"):
            s.zamknij()
            raise BladEmisji("inny program na wybranym porcie")
        return s

    def wykonaj(self, akcja, kierunek=0):
        if akcja == "odtwarzacz" and self.nazwa != "SARA":
            raise WymagaSary
        if akcja in ("hold", "hold_odczyt") and self.nazwa != "SARA":
            return None  # nie łącz się z SPL tylko po to, żeby sprawdzić Hold
        s = self.polacz()
        try:
            return s.wykonaj(akcja, kierunek)
        finally:
            s.zamknij()

    def odtworz(self):
        self.wykonaj("play")

    def start_nastepnego(self):
        self.wykonaj("nastepny")

    def stop_wyciszenie(self):
        self.wykonaj("stop")

    def stop_natychmiast(self):
        self.wykonaj("instant")

    def stan(self):
        return self.wykonaj("stan").stan


class StationPlaylistTCP(ProgramTCP):
    nazwa = "StationPlaylist"

    def __init__(self, port=443, limit_s=0.5, kodowanie="utf-8"):
        super().__init__(port, limit_s, kodowanie)


class SARA(ProgramTCP):
    nazwa = "SARA"

    def polacz_miks(self):
        return self.polacz()

    def __init__(self, port=51443, limit_s=0.5):
        super().__init__(port, limit_s)


BLEDY_POLACZENIA = (OSError, BladEmisji, UnicodeError)


class WyborProgramu(ProgramEmisyjny):
    """Helo przy każdym poleceniu; preferencja tylko gdy dany program odpowiada.

    Fallback wyłącznie PRZED wysłaniem akcji. Po błędzie podczas akcji nie
    uruchamiamy jej ponownie ani w drugim programie, ani przez API okna.
    """
    nazwa = "program emisyjny"

    def __init__(self, nazwa="auto", ustawienia=None, zapas=None, okno_spl=None):
        u = ustawienia or {}
        # Michał, 24.10.2026: przy zamkniętym SPL każdy klawisz czekał ~0,5 s,
        # bo port 443 na stanowisku nie odrzuca połączenia, tylko milczy do końca
        # limitu. Bez okna Studio nie pytamy SPL wcale (FindWindow trwa mikrosekundy).
        self.okno_spl = okno_spl if okno_spl is not None else _okno_spl_windows()
        self.program = nazwa.lower()
        preferowany = u.get("preferowany", "StationPlaylist").lower()
        if self.program not in ("auto", "stationplaylist", "spl", "sara"):
            raise ValueError("nieznany program emisyjny")
        if preferowany not in ("stationplaylist", "spl", "sara"):
            raise ValueError("nieznany preferowany program")
        limit = float(u.get("limit_odpowiedzi_s", 0.5))
        spl = StationPlaylistTCP(int(u.get("spl_port", 443)), limit, u.get("spl_kodowanie", "utf-8"))
        sara = SARA(int(u.get("sara_port", 51443)), limit)
        self.adaptery = ([sara, spl] if preferowany == "sara" else [spl, sara]) if self.program == "auto" else (
            [sara] if self.program == "sara" else [spl])
        self.zapas = zapas if zapas is not None else StationPlaylist()

    def polacz_miks(self):
        # Takie same preferencje jak zwykły transport, lecz bez akcji w SPL.
        # Po otwarciu tor zachowuje to gniazdo aż do Save/Cancel/awarii.
        if self.program in ("stationplaylist", "spl"):
            raise WymagaSary
        bez_spl = self.okno_spl() is False
        for adapter in self.adaptery:
            if bez_spl and isinstance(adapter, StationPlaylistTCP):
                continue
            try:
                s = adapter.polacz()
            except BLEDY_POLACZENIA:
                continue
            self.nazwa, self.wybrany = adapter.nazwa, adapter
            if not s.sara:
                s.zamknij()
                raise WymagaSary
            return s
        raise WymagaSary

    def _wykonaj_hold(self, akcja, kierunek):
        # Hold nie jest sondą SPL. W auto respektujemy wybór/preferencję i
        # FindWindow, bez TCP ani SendMessage do Studio. Brak wiedzy o oknie
        # poza Windows jest konserwatywnie traktowany jak możliwy SPL.
        if self.program in ("stationplaylist", "spl"):
            return None
        if (self.program == "auto" and isinstance(self.adaptery[0], StationPlaylistTCP)
                and self.okno_spl() is not False and self.nazwa != "SARA"):
            # Jeżeli zwykła akcja wybrała SARĘ mimo okna niedostępnego SPL,
            # respektujemy ten wybór bez kolejnej półsekundowej sondy Studio.
            return None
        sara = next(a for a in self.adaptery if isinstance(a, SARA))
        try:
            wynik = sara.wykonaj(akcja, kierunek)
        except BLEDY_POLACZENIA:
            if self.program == "auto" and self.okno_spl() is True and self.nazwa != "SARA":
                return None
            raise
        self.nazwa, self.wybrany = sara.nazwa, sara
        return wynik

    def wykonaj(self, akcja, kierunek=0):
        if akcja == "odtwarzacz" and self.program in ("stationplaylist", "spl"):
            raise WymagaSary
        if akcja in ("hold", "hold_odczyt"):
            return self._wykonaj_hold(akcja, kierunek)
        bez_spl = self.okno_spl() is False
        for adapter in self.adaptery:
            if bez_spl and isinstance(adapter, StationPlaylistTCP):
                continue
            try:
                s = adapter.polacz()
            except BLEDY_POLACZENIA:
                continue
            self.nazwa = adapter.nazwa
            self.wybrany = adapter
            try:
                return s.wykonaj(akcja, kierunek)
            finally:
                s.zamknij()
        if self.program != "sara" and not bez_spl and self.zapas.stan() is not None:
            self.nazwa = "StationPlaylist"
            return self.zapas.wykonaj(akcja, kierunek)
        self.nazwa = "program emisyjny"
        raise BrakProgramu


def utworz(nazwa: str | None = None, ustawienia: dict | None = None) -> ProgramEmisyjny:
    u = ustawienia or {}
    nazwa = nazwa if nazwa is not None else u.get("program", "auto")
    if nazwa.lower() == "atrapa":
        return AtrapaEmisji()
    return WyborProgramu(nazwa, u)
