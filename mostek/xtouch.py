"""Adapter X-TOUCH w trybie MC (Mackie Control) przez MIDI.

ŹRÓDŁO NUMERÓW MIDI: otwarty projekt Ardour, obsługa powierzchni Mackie
Control, commit a9ea4a98a336729a69453edbcc29905a79ac75e1:
  * libs/surfaces/mackie/device_info.cc: nuty przycisków pasków REC 0x00,
    SOLO 0x08, MUTE 0x10, SELECT 0x18, wciśnięcie gałki (V-Select) 0x20,
    dotyk suwaka 0x68, dotyk MASTER 0x70; F1-F8 0x36-0x3D; MIDI Tracks
    0x3E, Inputs 0x3F, Audio Tracks 0x40, Outputs 0x44, User 0x45;
    Rewind 0x5B, Ffwd 0x5C, Stop 0x5D, Play 0x5E, Record 0x5F;
    kursor góra/dół/lewo/prawo 0x60-0x63, Zoom 0x64, Scrub 0x65,
    jog CC 0x3C (względny, jak gałka),
  * libs/surfaces/mackie/surface.cc: suwaki to Pitch Bend na kanale paska
    (MASTER na kanale 9, indeks 8); obrót gałki to Control Change
    0x10 + pasek, bit 0x40 = kierunek w lewo, bity 0-5 = liczba ząbków,
  * libs/surfaces/mackie/fader.cc: pozycja silnika 14 bitów, E0+kanał, LSB, MSB,
  * libs/surfaces/mackie/led.cc: dioda = Note On, 0x7F świeci, 0x01 miga, 0x00 gaśnie,
  * libs/surfaces/mackie/pot.cc: pierścień diod = CC 0x30 + pasek,
    bity 4-5 tryb, bity 0-3 pozycja 1-11.
STATUS: do potwierdzenia na X-TOUCH. Behringer nie publikuje tabeli MC
w odczytanych materiałach; dokument „MIDI Mode Implementation” opisuje tryb
Generic, nie MC (plan, rozdz. 3B). Przed uzbrojeniem mapy trzeba nagrać
narzędziem narzedzia/podsluch_midi.py, co egzemplarz faktycznie wysyła.

Numery są w pliku ustawień (xtouch), nie w kodzie. Adapter zamienia MIDI na
zdarzenia rdzenia (rdzen.PRZYCISKI i dalej) i odwrotnie: diody, silniki,
pierścienie. Zwolnienie przycisku (Note On z prędkością 0) nie wykonuje
drugiej operacji (plan, rozdz. 8, kontrakt pkt 3). Wyjątek: MUTE paska to
kaszel (pasek 1) albo talkback (paski 2 i 3), więc puszczenie jest zdarzeniem
(„puszczenie”, pasek, 2). Zamknięcie portu MIDI (X-TOUCH odłączony albo
restart) daje zdarzenie („kontroler”, powód): mostek przerywa kaszel i talkback
oraz rozbraja powierzchnię (L01, analiza v22): do zdarzenia („kontroler_powrot”,
powód) przyciski i suwaki niczego nie otwierają, zamknięcia działają.
Po zgubieniu portu (MIM_CLOSE, odłączony USB) adapter sam ponawia otwarcie
portu co xtouch.ponowienie_portu_s sekund (PowierzchniaXTouch.ponow_otwarcie,
wołane z pętli mostka). Udane otwarcie to powrót kontrolera: rdzeń najpierw
ustawia silniki według miksera, potem uzbraja stół. NVDA mówi raz o utracie
i raz o powrocie; nieudane próby nie trafiają do mowy, a do dziennika tylko
pierwsza. LUKA: winmm zgłasza MIM_CLOSE przy zamknięciu urządzenia; czy
zgłasza coś przy odłączeniu albo restarcie X-TOUCH, nie sprawdzono, podobnie
jak to, co X-TOUCH w trybie MC wysyła po własnym restarcie. Od 25.10.2026
kaszel i talkback nie mają limitu czasu. Samo zgubienie puszczenia bez
wykrycia utraty urządzenia nie kończy trzymania; wymagany odbiór sprzętowy.
"""

from __future__ import annotations

from datetime import datetime
import logging
import sys
import threading
import time
from typing import Callable

log = logging.getLogger("mostek.xtouch")

NAZWY_PRZYCISKOW = ("rec", "solo", "mute", "select")
INDEKS_MUTE = 2


class MapaMC:
    def __init__(self, xtouch: dict) -> None:
        n = xtouch["pasek_nuty"]
        self.baza = [int(n[k]) for k in NAZWY_PRZYCISKOW]
        self.galka_wcisnij = int(n["galka_wcisnij"])
        self.dotyk = int(n["dotyk_suwaka"])
        self.dotyk_master = int(xtouch["dotyk_master"])
        self.galka_cc = int(xtouch["galka_cc"])
        self.jog_cc = int(xtouch.get("jog_cc", 60))
        self.pierscien_cc = int(xtouch["pierscien_cc"])
        self.kanal_master = int(xtouch["kanal_master_pitchbend"])
        self.klawisze = {int(k): v for k, v in xtouch["klawisze"].items()}
        self.nuta_klawisza = {v: k for k, v in self.klawisze.items()}
        self.suwak_wymaga_dotyku = bool(xtouch.get("suwak_wymaga_dotyku", True))
        self.paski = 8

    # --- MIDI -> zdarzenie -----------------------------------------------
    def zdarzenie(self, bajty: bytes | list[int]):
        if not bajty:
            return None
        status = bajty[0] & 0xF0
        kanal = bajty[0] & 0x0F
        if status == 0x90 and len(bajty) >= 3:
            nuta, predkosc = bajty[1], bajty[2]
            wcisniety = predkosc > 0
            for indeks, baza in enumerate(self.baza):
                if baza <= nuta < baza + self.paski:
                    if wcisniety:
                        return ("przycisk", nuta - baza + 1, indeks)
                    return ("puszczenie", nuta - baza + 1, indeks) if indeks == INDEKS_MUTE else None
            if self.galka_wcisnij <= nuta < self.galka_wcisnij + self.paski:
                return ("galka_wcisnij", nuta - self.galka_wcisnij + 1) if wcisniety else None
            if self.dotyk <= nuta < self.dotyk + self.paski:
                return ("dotyk", nuta - self.dotyk + 1, wcisniety)
            if nuta == self.dotyk_master:
                return ("dotyk", 9, wcisniety)
            if nuta in self.klawisze:
                return ("klawisz", self.klawisze[nuta]) if wcisniety else None
            return ("klawisz", f"nuta_{nuta}") if wcisniety else None
        if status == 0x80:
            # Zwolnienie przycisku nie wykonuje operacji; wyjątek: MUTE (kaszel).
            if len(bajty) >= 2:
                baza = self.baza[INDEKS_MUTE]
                if baza <= bajty[1] < baza + self.paski:
                    return ("puszczenie", bajty[1] - baza + 1, INDEKS_MUTE)
            return None
        if status == 0xE0 and len(bajty) >= 3:
            wartosc = (bajty[1] & 0x7F) | ((bajty[2] & 0x7F) << 7)
            pasek = 9 if kanal == self.kanal_master else kanal + 1
            return ("suwak", pasek, wartosc / 16383.0)
        if status == 0xB0 and len(bajty) >= 3:
            cc, v = bajty[1], bajty[2]
            if cc == self.jog_cc:
                zabki = v & 0x3F
                kierunek = -1 if v & 0x40 else 1
                return [("jog", kierunek)] * zabki if zabki else None
            if self.galka_cc <= cc < self.galka_cc + self.paski:
                zabki = v & 0x3F or 1
                kierunek = -1 if v & 0x40 else 1
                # Każdy ząbek to osobny krok: szybki obrót nie przyspiesza zmiany.
                return [("galka", cc - self.galka_cc + 1, kierunek)] * zabki
        return None

    # --- zdarzenie -> MIDI ------------------------------------------------
    def dioda(self, pasek: int, indeks: int, stan) -> bytes:
        v = 0x01 if stan is None else (0x7F if stan else 0x00)
        return bytes((0x90, self.baza[indeks] + pasek - 1, v))

    def dioda_klawisza(self, nazwa: str, stan) -> bytes | None:
        nuta = self.nuta_klawisza.get(nazwa)
        if nuta is None:
            return None
        v = 0x01 if stan is None else (0x7F if stan else 0x00)
        return bytes((0x90, nuta, v))

    def silnik(self, pasek: int, pozycja: float) -> bytes:
        pozycja = min(max(pozycja, 0.0), 1.0)
        v = int(round(16383 * pozycja))
        kanal = self.kanal_master if pasek == 9 else pasek - 1
        return bytes((0xE0 | kanal, v & 0x7F, v >> 7))

    def pierscien(self, pasek: int, wartosc: float) -> bytes:
        wartosc = min(max(wartosc, 0.0), 1.0)
        tryb = 0      # pojedyncza dioda (dot), Ardour pot.cc
        return bytes((0xB0, self.pierscien_cc + pasek - 1, (tryb << 4) | (int(round(wartosc * 10)) + 1)))


# Zapytanie urządzenia Mackie Control (Ardour, libs/surfaces/mackie/surface.cc,
# Surface::say_hello). X-TOUCH w trybie MC przez USB odpowiada
# F0 00 00 66 14 01 <numer seryjny> F7; w trybie Xctl, MIDI albo sieć milczy.
# Pomiar na stanowisku Michała 21.10.2026: 5 odpowiedzi na 5 zapytań co 2 s.
ZAPYTANIE_MC = bytes((0xF0, 0x00, 0x00, 0x66, 0x14, 0x00, 0xF7))
ODPOWIEDZ_MC = bytes((0xF0, 0x00, 0x00, 0x66, 0x14, 0x01))


class _BrakPortu:
    """Zaślepka, gdy portu MIDI nie udało się otworzyć: wysyłka nic nie robi."""
    przy_komunikacie = przy_zamknieciu = przy_otwarciu = None

    def wyslij(self, dane: bytes) -> None:
        pass

    def zapytaj(self) -> None:
        pass

    def zamknij(self) -> None:
        pass


class PowierzchniaXTouch:
    """Powierzchnia dla rdzenia: przyjmuje MIDI z portu, wysyła diody i silniki.

    otworz_port: funkcja bez argumentów, która otwiera port MIDI od nowa (np.
    lambda: PortWinMM(nazwa)) albo rzuca wyjątek, gdy urządzenia nie ma.
    Bez niej adapter nie ponawia otwarcia (port w pamięci, testy).

    okres_zycia: co tyle sekund zapytanie MC (ZAPYTANIE_MC). Stół, który nie
    odpowiada na proby_zycia kolejnych zapytań, jest utracony, a port jest
    otwierany od nowa. Powód (pomiar 21.10.2026 na Windows 11 z Windows MIDI
    Services): po wyłączeniu i włączeniu X-TOUCH Windows wystawia nowe
    urządzenie, a stary uchwyt winmm milczy bez MIM_CLOSE, więc mostek nie
    wiedział, że stół zniknął. Po ponownym otwarciu powrót kontrolera ogłasza
    dopiero pierwsza odpowiedź stołu, nie samo otwarcie portu: stół w trybie
    innym niż MC nie jest przedstawiany jako podłączony. None = bez zapytań."""

    def __init__(self, mapa: MapaMC, port_midi, zglos: Callable[[tuple], object],
                 otworz_port: Callable[[], object] | None = None, okres_ponowienia: float = 2.0,
                 okres_zycia: float | None = None, proby_zycia: int = 2) -> None:
        self.mapa = mapa
        self.zglos = zglos
        self._ostatnie: dict[tuple, bytes] = {}
        self._blokada = threading.Lock()
        self._dotkniete: set[int] = set()
        self._utracony = False
        self.suwak_wymaga_dotyku = bool(mapa.suwak_wymaga_dotyku)
        self.otworz_port = otworz_port
        self.okres_ponowienia = float(okres_ponowienia)
        self._port_zgubiony = False          # port do ponownego otwarcia
        self._ost_proba = float("-inf")
        self.proby_otwarcia = 0
        self.okres_zycia = None if not okres_zycia else float(okres_zycia)
        self.proby_zycia = max(1, int(proby_zycia))
        self._ost_zapytanie = float("-inf")
        self._czeka_odpowiedz = False
        self._bez_odpowiedzi = 0
        self._odpowiedz_zapisana = False
        self._ponowne_zgloszone = False
        # Diagnoza zawieszeń stołu (Michał, 23.10.2026 19:11: stół milczał
        # minutę, pomógł dopiero jego restart): chwila i treść ostatniego
        # komunikatu ze stołu oraz liczba komunikatów od startu portu.
        self.ost_komunikat: float | None = None
        self.ost_komunikat_zegar: str = ""
        self.ost_komunikat_bajty: bytes = b""
        self.komunikaty = 0
        self._blokada_portu = threading.Lock()
        self.port = _BrakPortu()
        if port_midi is None:
            self._port_zgubiony = self._utracony = True    # port nie otworzył się przy starcie
        else:
            self._podepnij(port_midi)

    def _podepnij(self, port) -> None:
        self.port = port
        port.przy_komunikacie = self._wejscie
        port.przy_zamknieciu = self._zamkniecie_portu
        port.przy_otwarciu = self.powrot

    @property
    def utracony(self) -> bool:
        return self._utracony

    def _zamkniecie_portu(self, powod: str = "port MIDI zamknięty") -> None:
        """MIM_CLOSE: port zgubiony (np. USB odłączony). Utrata kontrolera
        i ponawianie otwarcia, gdy adapter umie otworzyć port od nowa."""
        if self.otworz_port is not None:
            with self._blokada_portu:
                self._port_zgubiony = True
        self.utrata(powod)

    def ponow_otwarcie(self, teraz: float) -> bool:
        """Woła pętla mostka (Rdzen.tick). Przy zgubionym porcie co
        okres_ponowienia sekund jedna próba otwarcia. Udana: nowy port,
        powrót kontrolera (silniki według miksera, potem uzbrojenie); przy
        zapytaniach MC powrót dopiero po odpowiedzi stołu. Przy czynnym porcie
        zapytanie MC co okres_zycia sekund. Zwraca, czy port wrócił w tym
        wywołaniu."""
        if not self._port_zgubiony:
            self._sprawdz_zycie(teraz)
            return False
        if self.otworz_port is None:
            return False
        if teraz - self._ost_proba < self.okres_ponowienia:
            return False
        self._ost_proba = teraz
        self.proby_otwarcia += 1
        try:
            nowy = self.otworz_port()
        except Exception as e:  # noqa: BLE001 - brak urządzenia to zwykły wynik próby
            if self.proby_otwarcia == 1:
                log.warning("port MIDI niedostępny (%s), ponawiam co %.1f s", e, self.okres_ponowienia)
            else:
                log.debug("port MIDI nadal niedostępny: %s", e)
            return False
        with self._blokada_portu:
            stary = self.port
            for nazwa in ("przy_komunikacie", "przy_zamknieciu", "przy_otwarciu"):
                try:
                    setattr(stary, nazwa, None)     # spóźnione zdarzenia starego portu przepadają
                except Exception:  # noqa: BLE001
                    pass
            try:
                stary.zamknij()
            except Exception:  # noqa: BLE001 - uchwyt zgubionego urządzenia
                log.debug("zamknięcie starego portu MIDI", exc_info=True)
            self._podepnij(nowy)
            self._port_zgubiony = False
            self._czeka_odpowiedz = False
            self._bez_odpowiedzi = 0
            self._ost_zapytanie = float("-inf")
        if self.okres_zycia is not None:
            # Powrót ogłosi pierwsza odpowiedź stołu (_wejscie), nie samo otwarcie.
            if not self._ponowne_zgloszone:
                self._ponowne_zgloszone = True
                log.warning("port MIDI otwarty ponownie po %d próbach, czekam na odpowiedź X-TOUCH",
                            self.proby_otwarcia)
            self.proby_otwarcia = 0
            return False
        log.warning("port MIDI otwarty ponownie po %d próbach", self.proby_otwarcia)
        self.proby_otwarcia = 0
        self.powrot("port MIDI otwarty ponownie")
        return True

    def _sprawdz_zycie(self, teraz: float) -> None:
        """Zapytanie MC co okres_zycia sekund; brak odpowiedzi na proby_zycia
        kolejnych zapytań to utrata stołu i ponowne otwarcie portu."""
        if self.okres_zycia is None or teraz - self._ost_zapytanie < self.okres_zycia:
            return
        if self._czeka_odpowiedz:
            self._bez_odpowiedzi += 1
            if self._bez_odpowiedzi >= self.proby_zycia:
                if not self._utracony:
                    log.warning("X-TOUCH nie odpowiada na zapytanie MC od %.1f s: stół wyłączony, "
                                "inny tryb niż MC albo nowe urządzenie w Windows; otwieram port od nowa",
                                self._bez_odpowiedzi * self.okres_zycia)
                    log.warning("X-TOUCH: %s", self.opis_ostatniego())
                self._czeka_odpowiedz = False
                self._bez_odpowiedzi = 0
                if self.otworz_port is not None:
                    self._zamkniecie_portu("kontroler nie odpowiada")  # POPRAWKA ZYCIE: milczący stół to utrata
                else:
                    self.utrata("kontroler nie odpowiada")
                return
        self._czeka_odpowiedz = True
        self._ost_zapytanie = teraz
        try:
            self.port.zapytaj()
        except Exception:  # noqa: BLE001 - uchwyt zgubionego urządzenia
            log.debug("zapytanie MC", exc_info=True)

    def utrata(self, powod: str = "port MIDI zamknięty") -> None:
        """Kontroler zniknął: wciśnięte przyciski nie dostaną puszczenia, a rdzeń
        rozbraja powierzchnię do powrotu kontrolera (L01). Pamięć wysłanych
        diod i silników jest czyszczona: po powrocie wszystko idzie od nowa."""
        self._dotkniete.clear()
        self._utracony = True
        with self._blokada:
            self._ostatnie.clear()
        try:
            self.zglos(("kontroler", powod))
        except Exception:  # noqa: BLE001
            log.exception("obsługa utraty kontrolera")

    def powrot(self, powod: str = "port MIDI otwarty ponownie") -> None:
        """Kontroler znowu połączony (ponowne otwarcie portu albo koniec
        restartu X-TOUCH): rdzeń ustawia silniki i diody według odczytu, potem
        uzbraja powierzchnię. LUKA: co X-TOUCH wysyła po restarcie, do pomiaru."""
        self._dotkniete.clear()
        self._utracony = False
        self._ponowne_zgloszone = False
        with self._blokada:
            self._ostatnie.clear()
        try:
            self.zglos(("kontroler_powrot", powod))
        except Exception:  # noqa: BLE001
            log.exception("obsługa powrotu kontrolera")

    def opis_ostatniego(self, teraz: float | None = None) -> str:
        """Do dziennika przy utracie stołu: kiedy przyszedł ostatni komunikat."""
        if self.ost_komunikat is None:
            return f"od otwarcia portu nie przyszedł żaden komunikat ze stołu (komunikatów: {self.komunikaty})"
        teraz = time.monotonic() if teraz is None else teraz
        return (f"ostatni komunikat ze stołu {teraz - self.ost_komunikat:.1f} s temu, "
                f"o {self.ost_komunikat_zegar}: {self.ost_komunikat_bajty.hex(' ')}; "
                f"komunikatów od startu: {self.komunikaty}")

    def _wejscie(self, bajty) -> None:
        self.ost_komunikat = time.monotonic()
        self.ost_komunikat_zegar = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.ost_komunikat_bajty = bytes(bajty[:12])
        self.komunikaty += 1
        if self._port_zgubiony:
            return              # port czeka na ponowne otwarcie: powrót tylko przez nowy port
        self._czeka_odpowiedz = False       # każdy komunikat stołu dowodzi, że żyje
        self._bez_odpowiedzi = 0
        if bytes(bajty[:6]) == ODPOWIEDZ_MC and not self._odpowiedz_zapisana:
            self._odpowiedz_zapisana = True
            log.info("X-TOUCH odpowiada na zapytanie MC: tryb MC przez USB")
        if self._utracony:
            log.warning("X-TOUCH znowu wysyła MIDI: %s (komunikat nr %d)",
                        self.ost_komunikat_bajty.hex(' '), self.komunikaty)
            # Pierwszy komunikat po utracie (X-TOUCH po restarcie znowu wysyła
            # MIDI): powrót kontrolera. Sam komunikat nie jest wykonywany, bo
            # stan przycisków i suwaków jest jeszcze nieuzgodniony (L01).
            self.powrot("kontroler znowu wysyła MIDI")
            return
        z = self.mapa.zdarzenie(bajty)
        if z is None:
            return
        if not isinstance(z, list) and z[0] == "dotyk":
            (self._dotkniete.add if z[2] else self._dotkniete.discard)(z[1])
        if not isinstance(z, list) and z[0] == "suwak" and self.suwak_wymaga_dotyku \
                and z[1] not in self._dotkniete:
            # Ruch bez dotyku to silnik, nie Michał (plan, rozdz. 8, kontrakt pkt 10).
            log.debug("pominięty ruch suwaka %s bez dotyku", z[1])
            return
        if not isinstance(z, list) and z[0] == "suwak":
            # Mackie Control: host odsyła pozycję suwaka. Bez echa X-TOUCH po
            # puszczeniu wraca silnikiem do ostatniej pozycji od hosta (pomiar,
            # 18.10.2026: „po puszczeniu idzie z powrotem do góry”; forum MIDI-OX,
            # „faders return to their initial position”). Echo zapamiętujemy,
            # żeby późniejsze ustaw_suwak z odczytu miksera nie zostało pominięte.
            dane = bytes(bajty[:3])
            with self._blokada:
                self._ostatnie[("s", z[1])] = dane
            try:
                self.port.wyslij(dane)
            except Exception:  # noqa: BLE001
                log.debug("echo suwaka", exc_info=True)
        for zd in (z if isinstance(z, list) else [z]):
            try:
                self.zglos(zd)
            except Exception:  # noqa: BLE001 - błąd obsługi nie może zatrzymać odbioru MIDI
                log.exception("obsługa zdarzenia %s", zd)

    def _wyslij(self, klucz: tuple, dane: bytes | None) -> None:
        if dane is None:
            return
        with self._blokada:
            if self._ostatnie.get(klucz) == dane:
                return
            self._ostatnie[klucz] = dane
        self.port.wyslij(dane)

    def ustaw_diode(self, pasek, indeks, stan) -> None:
        self._wyslij(("d", pasek, indeks), self.mapa.dioda(pasek, indeks, stan))

    def ustaw_klawisz(self, nazwa, stan) -> None:
        self._wyslij(("k", nazwa), self.mapa.dioda_klawisza(nazwa, stan))

    def ustaw_suwak(self, pasek, pozycja) -> None:
        self._wyslij(("s", pasek), self.mapa.silnik(pasek, pozycja))

    def ustaw_pierscien(self, pasek, wartosc) -> None:
        self._wyslij(("p", pasek), self.mapa.pierscien(pasek, wartosc))


# --- porty MIDI ----------------------------------------------------------------

class AtrapaPortuMIDI:
    """Port MIDI w pamięci. Do testów i do pracy z symulatorem.
    odlacz() udaje odłączenie USB: MIM_CLOSE do adaptera."""

    def __init__(self) -> None:
        self.wyslane: list[bytes] = []
        self.zamkniety = False
        self.przy_komunikacie: Callable | None = None
        self.przy_zamknieciu: Callable | None = None
        self.przy_otwarciu: Callable | None = None

    def wyslij(self, dane: bytes) -> None:
        self.wyslane.append(bytes(dane))

    def wstrzyknij(self, *bajty: int) -> None:
        if self.przy_komunikacie:
            self.przy_komunikacie(bytes(bajty))

    def odlacz(self) -> None:
        if self.przy_zamknieciu:
            self.przy_zamknieciu()

    def zapytaj(self) -> None:
        """Zapytanie MC; atrapa tylko je zapisuje (odpowiedź wstrzykuje test)."""
        self.wyslane.append(ZAPYTANIE_MC)

    def zamknij(self) -> None:
        self.zamkniety = True


class BrakMIDI(RuntimeError):
    pass


class PortWinMM:
    """MIDI w Windows przez winmm.dll (ctypes). Import strzeżony: tylko Windows.

    Funkcje: midiInGetNumDevs, midiInGetDevCapsW, midiInOpen (CALLBACK_FUNCTION),
    midiInStart, midiOutOpen, midiOutShortMsg; dokumentacja Microsoft
    „Multimedia Input/Output” (mmeapi.h). Krótkie komunikaty (MIM_DATA) są
    przekazywane dalej. SysEx służy tylko zapytaniu MC i odpowiedzi stołu:
    wysyłka midiOutLongMsg, odbiór MIM_LONGDATA do dwóch buforów, które
    wątek pomocniczy oddaje z powrotem przez midiInAddBuffer (nie wolno tego
    robić w samej funkcji zwrotnej winmm).
    Sprawdzone na Windows 11 z X-TOUCH (Michał, 21.10.2026): krótkie
    komunikaty, zapytanie MC i odpowiedź z numerem seryjnym.
    """

    MIM_DATA = 0x3C3
    MIM_LONGDATA = 0x3C4
    MIM_CLOSE = 0x3C2
    MIM_OPEN = 0x3C1
    MHDR_DONE = 0x01
    CALLBACK_FUNCTION = 0x00030000
    BUFOR_SYSEX = 256

    def __init__(self, nazwa: str = "X-TOUCH") -> None:
        if sys.platform != "win32":
            raise BrakMIDI("winmm działa tylko w Windows")
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        self._ct = ctypes
        self._winmm = ctypes.WinDLL("winmm")
        self.przy_komunikacie: Callable | None = None
        self.przy_zamknieciu: Callable | None = None
        self.przy_otwarciu: Callable | None = None

        class MIDIINCAPSW(ctypes.Structure):
            _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                        ("szPname", wintypes.WCHAR * 32), ("dwSupport", wintypes.DWORD)]

        class MIDIOUTCAPSW(ctypes.Structure):
            _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                        ("szPname", wintypes.WCHAR * 32), ("wTechnology", wintypes.WORD),
                        ("wVoices", wintypes.WORD), ("wNotes", wintypes.WORD),
                        ("wChannelMask", wintypes.WORD), ("dwSupport", wintypes.DWORD)]

        self._wejscie_nr = self._znajdz(self._winmm.midiInGetNumDevs, self._winmm.midiInGetDevCapsW,
                                        MIDIINCAPSW, nazwa)
        self._wyjscie_nr = self._znajdz(self._winmm.midiOutGetNumDevs, self._winmm.midiOutGetDevCapsW,
                                        MIDIOUTCAPSW, nazwa)
        class MIDIHDR(ctypes.Structure):
            _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                        ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                        ("dwFlags", wintypes.DWORD), ("lpNext", ctypes.c_void_p),
                        ("reserved", ctypes.c_size_t), ("dwOffset", wintypes.DWORD),
                        ("dwReserved", ctypes.c_size_t * 8)]

        self._MIDIHDR = MIDIHDR
        PROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.UINT, ctypes.c_size_t,
                                  ctypes.c_size_t, ctypes.c_size_t)
        self._proc = PROC(self._callback)       # referencja chroni przed zwolnieniem
        self._hin = wintypes.HANDLE()
        self._hout = wintypes.HANDLE()
        self._zamykanie = False
        self._naglowki_we: list = []
        self._naglowek_wy = None
        if self._winmm.midiInOpen(ctypes.byref(self._hin), self._wejscie_nr, self._proc, 0,
                                  self.CALLBACK_FUNCTION):
            raise BrakMIDI("midiInOpen nie powiodło się")
        if self._winmm.midiOutOpen(ctypes.byref(self._hout), self._wyjscie_nr, 0, 0, 0):
            # Wejście już otwarte: zamknąć, inaczej ponawianie otwarcia co kilka
            # sekund zostawiałoby zajęte uchwyty (kolejne midiInOpen by odmawiało).
            self.przy_zamknieciu = None
            self._winmm.midiInClose(self._hin)
            raise BrakMIDI("midiOutOpen nie powiodło się")
        self._przygotuj_sysex()
        self._winmm.midiInStart(self._hin)

    def _przygotuj_sysex(self) -> None:
        """Dwa bufory odbioru SysEx i jeden stały nagłówek zapytania MC.
        Błąd przygotowania nie blokuje krótkich komunikatów: stół działa,
        tylko bez sprawdzania życia (zapytaj nic nie wyśle)."""
        ct = self._ct
        rozmiar = ct.sizeof(self._MIDIHDR)
        try:
            for _ in range(2):
                bufor = ct.create_string_buffer(self.BUFOR_SYSEX)
                h = self._MIDIHDR()
                h.lpData = ct.cast(bufor, ct.c_void_p)
                h.dwBufferLength = self.BUFOR_SYSEX
                if self._winmm.midiInPrepareHeader(self._hin, ct.byref(h), rozmiar):
                    raise BrakMIDI("midiInPrepareHeader nie powiodło się")
                self._naglowki_we.append((h, bufor))
                self._winmm.midiInAddBuffer(self._hin, ct.byref(h), rozmiar)
            dane = ct.create_string_buffer(ZAPYTANIE_MC, len(ZAPYTANIE_MC))
            h = self._MIDIHDR()
            h.lpData = ct.cast(dane, ct.c_void_p)
            h.dwBufferLength = len(ZAPYTANIE_MC)
            if self._winmm.midiOutPrepareHeader(self._hout, ct.byref(h), rozmiar):
                raise BrakMIDI("midiOutPrepareHeader nie powiodło się")
            self._naglowek_wy = (h, dane)
        except Exception as e:  # noqa: BLE001
            log.warning("SysEx X-TOUCH niedostępny (%s): bez sprawdzania, czy stół odpowiada", e)

    def zapytaj(self) -> None:
        """Zapytanie MC (F0 00 00 66 14 00 F7). Nagłówek jest stały; gdy
        poprzednie wysyłanie jeszcze trwa, winmm odmawia i pytanie przepada."""
        if self._naglowek_wy is None or self._zamykanie:
            return
        h, _ = self._naglowek_wy
        self._winmm.midiOutLongMsg(self._hout, self._ct.byref(h), self._ct.sizeof(self._MIDIHDR))

    def _oddaj_bufor(self, h) -> None:
        if not self._zamykanie:
            self._winmm.midiInAddBuffer(self._hin, self._ct.byref(h), self._ct.sizeof(self._MIDIHDR))

    def _sysex(self, h, dane: bytes) -> None:
        try:
            if dane and self.przy_komunikacie is not None:
                self.przy_komunikacie(dane)
        finally:
            self._oddaj_bufor(h)

    def _znajdz(self, liczba, caps, struktura, nazwa: str) -> int:
        nazwy = []
        for i in range(liczba()):
            c = struktura()
            nazwy.append(c.szPname if caps(i, self._ct.byref(c), self._ct.sizeof(c)) == 0 else "")
        i = wybierz_port(nazwy, nazwa)
        if i is None:
            raise BrakMIDI(f"nie znaleziono urządzenia MIDI zawierającego „{nazwa}” (są: {', '.join(nazwy) or 'brak'})")
        log.info("port MIDI %s: %r spośród %r", struktura.__name__, nazwy[i], nazwy)
        return i

    def _callback(self, _h, komunikat, _inst, param1, _param2) -> None:
        # MIM_CLOSE: urządzenie zamknięte (dokumentacja mmeapi.h). Czy pada przy
        # odłączeniu X-TOUCH, nie sprawdzono (luka, README).
        if komunikat == self.MIM_CLOSE and self.przy_zamknieciu is not None:
            threading.Thread(target=self.przy_zamknieciu, daemon=True).start()
            return
        # MIM_OPEN: urządzenie otwarte. Pada przy midiInOpen (wtedy powierzchnia
        # nie jest jeszcze podpięta). Ponowne otwarcie po odłączeniu wymaga
        # osobnej obsługi w Windows (luka, README); wtedy to jest powrót kontrolera.
        if komunikat == self.MIM_OPEN and self.przy_otwarciu is not None:
            threading.Thread(target=self.przy_otwarciu, daemon=True).start()
            return
        if komunikat == self.MIM_LONGDATA:
            if self._zamykanie:
                return          # midiInReset oddaje bufory przy zamknięciu
            for h, bufor in self._naglowki_we:
                if self._ct.addressof(h) == param1:
                    dane = bufor.raw[:h.dwBytesRecorded]
                    threading.Thread(target=self._sysex, args=(h, dane), daemon=True).start()
                    break
            return
        if komunikat != self.MIM_DATA or self.przy_komunikacie is None:
            return
        if not getattr(self, "_pierwszy_zapisany", False):
            self._pierwszy_zapisany = True
            log.info("pierwszy komunikat MIDI z X-TOUCH: 0x%06X", param1 & 0xFFFFFF)
        status = param1 & 0xFF
        dlugosc = 2 if (status & 0xF0) in (0xC0, 0xD0) else 3
        dane = bytes(((param1 >> (8 * i)) & 0xFF) for i in range(dlugosc))
        # Callback winmm nie może blokować: przekazanie do osobnego wątku.
        threading.Thread(target=self.przy_komunikacie, args=(dane,), daemon=True).start()

    def wyslij(self, dane: bytes) -> None:
        slowo = 0
        for i, b in enumerate(dane[:3]):
            slowo |= b << (8 * i)
        self._winmm.midiOutShortMsg(self._hout, slowo)

    def zamknij(self) -> None:
        ct = self._ct
        rozmiar = ct.sizeof(self._MIDIHDR)
        self._zamykanie = True
        self._winmm.midiInStop(self._hin)
        self._winmm.midiInReset(self._hin)              # oddaje bufory SysEx
        for h, _ in self._naglowki_we:
            self._winmm.midiInUnprepareHeader(self._hin, ct.byref(h), rozmiar)
        self._winmm.midiInClose(self._hin)
        if self._naglowek_wy is not None:
            self._winmm.midiOutReset(self._hout)
            self._winmm.midiOutUnprepareHeader(self._hout, ct.byref(self._naglowek_wy[0]), rozmiar)
        self._winmm.midiOutClose(self._hout)


def wybierz_port(nazwy: list[str], nazwa: str = "X-TOUCH") -> int | None:
    """Indeks portu sterującego X-TOUCH w trybie MC.

    X-TOUCH przez USB wystawia w Windows DWA porty o nazwie z „X-TOUCH”:
    sterujący („X-TOUCH”, w nowych nazwach Windows MIDI Services „X-TOUCH
    INT”) i drugi, przelotkę gniazd MIDI DIN („MIDIIN2 (X-TOUCH)” /
    „MIDIOUT2 (X-TOUCH)”, nowe nazwy „X-TOUCH EXT”). Źródło: forum Steinberg,
    wątek „X-Touch (+Extender) MIDI Remote Script”, s. 24, i instrukcja
    konfiguracji Cubase („X-Touch INT”). Dawniej braliśmy pierwszy port
    z nazwą, co mogło trafić w przelotkę: stół milczy, a suwaki wracają."""
    pasujace = [i for i, n in enumerate(nazwy) if nazwa.lower() in n.lower()]
    if not pasujace:
        return None

    def kara(i: int) -> int:
        n = nazwy[i].upper().replace("_", " ")
        if n.startswith(("MIDIIN", "MIDIOUT")) or " EXT" in n or n.endswith("EXT"):
            return 2
        if " INT" in n or n.endswith("INT") or n.strip() == nazwa.upper():
            return 0
        return 1
    return min(pasujace, key=lambda i: (kara(i), i))


def lista_urzadzen_winmm() -> list[str]:
    if sys.platform != "win32":
        return []
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class MIDIINCAPSW(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                    ("szPname", wintypes.WCHAR * 32), ("dwSupport", wintypes.DWORD)]

    w = ctypes.WinDLL("winmm")
    nazwy = []
    for i in range(w.midiInGetNumDevs()):
        c = MIDIINCAPSW()
        if w.midiInGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0:
            nazwy.append(c.szPname)
    return nazwy
