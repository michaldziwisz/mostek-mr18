"""Klient OSC miksera MR18 (UDP 10024).

Interfejs synchroniczny dla jednego wątku roboczego mostka („jedna kolejka
zapisów”, plan rozdz. 8, kontrakt pkt 3):

  odczytaj_wiele(adresy)  zapytania bez argumentu, odpowiedzi do słownika,
  ustaw(adres, wartosc)   zapis jawnej wartości, potem osobny odczyt
                          i porównanie; najwyżej `dodatkowe_proby` ponowień,
  odnow_subskrypcje()     /xremote na kanale subskrypcji,
  subskrybuj_mierniki(id) /meters ,s id na kanale subskrypcji (PROTO 1.5);
                          blok mierników trafia do `przy_miernikach(blob)`.

Zgłoszenia zmian przychodzące przez /xremote trafiają do wywołania
`przy_zgloszeniu(adres, wartosc)`, wołanego z wątku sieciowego. Mostek nie
ufa im wprost: przekazuje je do wątku roboczego, który robi świeży odczyt.

Brak odpowiedzi po wszystkich próbach zgłasza BrakOdpowiedzi: mostek
przechodzi wtedy w stan NIEZNANY. Klient nigdy nie wysyła wartości „odwróć”.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from . import osc, sciezki

log = logging.getLogger("mostek.klient")


class BrakOdpowiedzi(RuntimeError):
    """Mikser nie odpowiedział mimo ponowień."""


@dataclass
class WynikZapisu:
    adres: str
    zadana: object
    odczytana: object           # wartość potwierdzona odczytem (albo None przy braku odpowiedzi)
    proby: int

    @property
    def potwierdzony(self) -> bool:
        return self.odczytana is not None and zgodne(self.zadana, self.odczytana)


TOLERANCJA = 0.005


def zgodne(a, b, tolerancja: float = TOLERANCJA) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= tolerancja
        except (TypeError, ValueError):
            return False
    return a == b


class _Oczekiwanie:
    def __init__(self, adresy: Iterable[str]) -> None:
        self.brakujace = set(adresy)
        self.wszystkie = frozenset(self.brakujace)
        self.odebrane: dict[str, int] = {}      # odpowiedzi na adres, także powtórzone
        self.wyniki: dict[str, object] = {}
        self.start = time.monotonic()
        self.ostatnia: float | None = None
        self.czasy: dict[str, float] = {}       # chwila pierwszej odpowiedzi na adres
        self.zdarzenie = threading.Event()
        # Budzik okna wysyłania: każda odpowiedź zwalnia miejsce na kolejne pytanie.
        self.odpowiedz = threading.Event()
        if not self.brakujace:
            self.zdarzenie.set()

    def przyjmij(self, adres: str, wartosc) -> None:
        if adres in self.wszystkie:
            self.odebrane[adres] = self.odebrane.get(adres, 0) + 1
        if adres in self.brakujace:
            self.brakujace.discard(adres)
            self.wyniki[adres] = wartosc
            self.ostatnia = time.monotonic()
            self.czasy[adres] = self.ostatnia
            self.odpowiedz.set()
            if not self.brakujace:
                self.zdarzenie.set()


class KlientMR18:
    def __init__(self, transport, limit_odpowiedzi_s: float = 0.15, dodatkowe_proby: int = 2,
                 przy_zgloszeniu: Callable[[str, object], None] | None = None,
                 przy_miernikach: Callable[[bytes], None] | None = None,
                 tolerancja: float = TOLERANCJA, zegar=time.monotonic, porcja: int = 24,
                 okno: int = 16, szybka_powtorka_s: float = 0.03,
                 przerwa_ponowienia_s: float = 0.0, cisza_utraty_s: float = 0.0,
                 dopasuj_do_opoznienia: bool = True, maks_limit_rundy_s: float = 3.0) -> None:
        self.transport = transport
        self.limit = float(limit_odpowiedzi_s)
        self.dodatkowe_proby = int(dodatkowe_proby)
        # Okno wysyłania (pomiar 20.10.2026): seria 24 pytań naraz gubiła ok. 10%
        # odpowiedzi, a każda zguba kosztowała pełny limit (262 ms). Najwyżej
        # `okno` pytań bez odpowiedzi naraz, a pytanie bez odpowiedzi po
        # `szybka_powtorka_s` idzie drugi raz, zanim minie limit. 0 = jak dawniej.
        self.okno = max(0, int(okno))
        self.szybka_powtorka = float(szybka_powtorka_s)
        # Pomiar na MR18V2 fw 1.19 (22.10.2026): mikser co ok. 1 s milknie na
        # 0,2-0,3 s, a czasem na 1-6 s. Ponowienie zaraz po pustej rundzie
        # trafiało w tę samą ciszę: trzy rundy w 1,5 s i utrata łączności.
        # `przerwa_ponowienia_s`: odstęp przed kolejną rundą po pustej rundzie.
        # `cisza_utraty_s`: rundy powtarzane, dopóki od pierwszej pustej rundy
        # nie minie tyle sekund; dopiero potem BrakOdpowiedzi. 0 = jak dawniej.
        self.przerwa_ponowienia = max(0.0, float(przerwa_ponowienia_s))
        self.cisza_utraty = max(0.0, float(cisza_utraty_s))
        self.maks_wyslan = 4
        # Dziennik Michała 23.10.2026 03:12, MR18V2 fw 1.26: mikser przez 17 s
        # odpowiadał po ok. 350 ms zamiast 16 ms. Powtórka po 30 ms słała każde
        # pytanie 4 razy (1316 powtórek w minucie), a limit rundy maleje z
        # liczbą brakujących (4 pytania: 169 ms), więc ostatnie 4 pytania nie
        # miały szans i mostek ogłosił utratę. Klient mierzy opóźnienie
        # odpowiedzi (`opoznienie`), powtarza dopiero po 2x opóźnieniu i czeka
        # na rundę co najmniej tyle, ile mikser potrzebuje teraz na odpowiedź.
        # False = jak dawniej.
        self.dopasuj = bool(dopasuj_do_opoznienia)
        self.maks_limit_rundy = max(0.0, float(maks_limit_rundy_s))
        self.opoznienie = 0.0
        self._wolny = False
        self._pusta_runda = False
        self.przy_zgloszeniu = przy_zgloszeniu
        self.przy_miernikach = przy_miernikach
        self.id_miernikow: str | None = None
        self.tolerancja = tolerancja
        self.zegar = zegar
        self.porcja = porcja
        self.ostatnia_odpowiedz = float("-inf")
        self.wyslane_pakiety = 0
        self.wymiany_kanalu = 0
        self._blokada = threading.Lock()          # jeden zapis/odczyt naraz
        self._oczekiwanie: _Oczekiwanie | None = None
        self._ost_lock = threading.Lock()
        self._subskrypcja = transport.otworz_kanal(self._odbior_subskrypcji)
        self._weryfikacja = transport.otworz_kanal(self._odbior_weryfikacji)

    # --- odbiór -----------------------------------------------------------
    def _znacznik(self) -> None:
        with self._ost_lock:
            self.ostatnia_odpowiedz = self.zegar()

    def _odbior_weryfikacji(self, dane: bytes, _nadawca) -> None:
        try:
            komunikaty = osc.dekoduj(dane)
        except osc.BladOSC:
            log.warning("niepoprawny pakiet OSC na kanale weryfikacji")
            return
        self._znacznik()
        ocz = self._oczekiwanie
        for k in komunikaty:
            if ocz is not None:
                ocz.przyjmij(k.adres, k.wartosc if k.argumenty else None)

    def _odbior_subskrypcji(self, dane: bytes, _nadawca) -> None:
        try:
            komunikaty = osc.dekoduj(dane)
        except osc.BladOSC:
            log.warning("niepoprawny pakiet OSC na kanale subskrypcji")
            return
        self._znacznik()
        for k in komunikaty:
            if not k.argumenty:
                continue
            if k.typy.startswith("b"):
                # Blok mierników nie jest zmianą parametru (PROTO 1.5).
                if self.przy_miernikach is not None and k.adres == self.id_miernikow:
                    self.przy_miernikach(bytes(k.wartosc))
                continue
            if self.przy_zgloszeniu is not None:
                self.przy_zgloszeniu(k.adres, k.wartosc)

    # --- kanały -----------------------------------------------------------
    def _wymien_kanal_weryfikacji(self) -> None:
        """Nowe gniazdo: spóźnione odpowiedzi trafią do zamkniętego (kontrakt pkt 4)."""
        stary = self._weryfikacja
        self._weryfikacja = self.transport.otworz_kanal(self._odbior_weryfikacji)
        stary.zamknij()
        self.wymiany_kanalu += 1

    def _wyslij(self, dane: bytes) -> None:
        self.wyslane_pakiety += 1
        self._weryfikacja.wyslij(dane)

    def odnow_subskrypcje(self) -> None:
        self._subskrypcja.wyslij(osc.koduj(sciezki.XREMOTE))

    def subskrybuj_mierniki(self, identyfikator: str) -> None:
        """/meters ,s "<id>": mikser wysyła bloki pod adres id (PROTO 1.5, wiersz 79).
        Ważność jak /xremote; mostek odnawia razem z nim. Odpowiedzi idą do
        nadawcy, więc wysyłamy z kanału subskrypcji."""
        self.id_miernikow = identyfikator
        self._subskrypcja.wyslij(osc.koduj(sciezki.METERS, identyfikator, typy="s"))

    def zamknij(self) -> None:
        self._subskrypcja.zamknij()
        self._weryfikacja.zamknij()

    # --- odczyt -----------------------------------------------------------
    def _runda(self, adresy: list[str], limit: float) -> tuple["_Oczekiwanie", int, bool]:
        """Jedna runda pytań na bieżącym kanale weryfikacji.

        Zwraca (oczekiwanie, liczba szybkich powtórek, czy wszystkie wysłane
        pakiety dostały odpowiedź). Okno: najwyżej self.okno pytań bez
        odpowiedzi naraz; kolejne idzie, gdy przyjdzie odpowiedź. Pytanie bez
        odpowiedzi przez self.szybka_powtorka idzie jeszcze raz, najwyżej
        self.maks_wyslan razy w rundzie (przy losowej utracie 10% cztery
        wysłania zawodzą raz na 10 000 pytań).
        Odpowiedź na zapytanie bez argumentu podaje bieżącą wartość, więc
        obie odpowiedzi na powtórzone pytanie są świeże."""
        ocz = _Oczekiwanie(adresy)
        self._oczekiwanie = ocz
        wyslania: dict[str, int] = {}

        def wyslij(a: str) -> None:
            wyslania[a] = wyslania.get(a, 0) + 1
            self._wyslij(osc.koduj(a))

        if self.okno <= 0:
            for a in adresy:
                wyslij(a)
            ocz.zdarzenie.wait(limit)
            self._oczekiwanie = None
            return ocz, 0, all(ocz.odebrane.get(a, 0) >= n for a, n in wyslania.items())
        kolejka = list(adresy)
        wyslane: dict[str, float] = {}
        powtorki = 0
        koniec = ocz.start + limit
        odstep = self._odstep_powtorki()
        krok = odstep / 2 if odstep > 0 else limit
        while not ocz.zdarzenie.is_set():
            teraz = time.monotonic()
            if teraz >= koniec:
                break
            w_locie = [a for a in wyslane if a in ocz.brakujace]
            while kolejka and len(w_locie) < self.okno:
                a = kolejka.pop(0)
                wyslij(a)
                wyslane[a] = time.monotonic()
                w_locie.append(a)
            if odstep > 0:
                for a in w_locie:
                    if wyslania[a] < self.maks_wyslan and teraz - wyslane[a] >= odstep:
                        wyslij(a)
                        wyslane[a] = time.monotonic()
                        powtorki += 1
            if ocz.zdarzenie.is_set():
                break
            ocz.odpowiedz.wait(max(0.001, min(krok, koniec - teraz)))
            # Czyszczenie PO przebudzeniu, przed sprawdzeniem stanu: odpowiedź,
            # która przyjdzie teraz, ustawi budzik na następne czekanie.
            ocz.odpowiedz.clear()
        self._oczekiwanie = None
        self._zmierz_opoznienie(ocz, wyslane)
        return ocz, powtorki, all(ocz.odebrane.get(a, 0) >= n for a, n in wyslania.items())

    # --- dopasowanie do opóźnienia miksera ---------------------------------
    def _odstep_powtorki(self) -> float:
        if self.szybka_powtorka <= 0:
            return 0.0
        if not self.dopasuj:
            return self.szybka_powtorka
        return max(self.szybka_powtorka, 2 * self.opoznienie)

    def _limit_rundy(self, n: int) -> float:
        bazowy = self.limit * (1 + n / 32)
        if not self.dopasuj or self.opoznienie <= 0:
            return bazowy
        okna = -(-n // self.okno) if self.okno > 0 else 1
        if self._pusta_runda:
            # Po rundzie bez odpowiedzi czekamy tylko na pierwsze okno: wolny
            # mikser zdąży odpowiedzieć, a cisza nie wydłuża ogłoszenia utraty.
            okna = 1
        potrzebny = self.opoznienie * (1.5 * okna + 1)
        return max(bazowy, min(self.maks_limit_rundy, potrzebny))

    def _zmierz_opoznienie(self, ocz: "_Oczekiwanie", wyslane: dict[str, float]) -> None:
        """Próbka = odpowiedź minus OSTATNIE wysłanie tego pytania. Przy
        powtórce to dolne oszacowanie (odpowiedź mogła być na pierwsze
        wysłanie), więc klient nigdy nie zawyża opóźnienia przez zgubiony
        pakiet. Wzrost od razu, spadek o połowę na rundę. Runda bez żadnej
        odpowiedzi zostawia opóźnienie bez zmian: wyzerowanie przy wolnym
        mikserze skracało limit poniżej czasu odpowiedzi i dawało tę samą
        spiralę co 23.10 o 03:12. Utratę przy ciszy i tak ogłasza
        cisza_utraty_s, najwyżej o jedną rundę (maks_limit_rundy_s) później."""
        if not self.dopasuj:
            return
        probki = sorted(ocz.czasy[a] - wyslane[a] for a in ocz.czasy if a in wyslane)
        self._pusta_runda = bool(ocz.wszystkie) and not ocz.wyniki
        if not probki:
            return
        p90 = max(0.0, probki[int(len(probki) * 0.9) if len(probki) > 1 else 0])
        self.opoznienie = max(p90, self.opoznienie * 0.5)
        if self.opoznienie < 0.002:
            self.opoznienie = 0.0
        wolny = self.opoznienie > 2 * self.szybka_powtorka > 0
        if wolny != self._wolny:
            self._wolny = wolny
            log.info("mikser odpowiada %s: opóźnienie %.0f ms, powtórka po %.0f ms",
                     "wolno" if wolny else "znów szybko", self.opoznienie * 1000,
                     self._odstep_powtorki() * 1000)

    def _odczytaj_porcje(self, adresy: list[str]) -> dict[str, object]:
        wyniki: dict[str, object] = {}
        brak = list(dict.fromkeys(adresy))
        proba = 0
        poczatek_ciszy: float | None = None
        while True:
            limit = self._limit_rundy(len(brak))
            ocz, powtorki, domkniete = self._runda(brak, limit)
            wyniki.update(ocz.wyniki)
            pytane = len(brak)
            brak = [a for a in brak if a not in wyniki]
            self._pomiar(pytane, len(brak), ocz, limit, powtorki)
            if not brak:
                if not domkniete:
                    # Odpowiedź na powtórzone albo zgubione pytanie może jeszcze
                    # dojść. Nowe gniazdo, żeby nie wzięto jej za odpowiedź na
                    # pytanie po następnym zapisie (kontrakt pkt 4).
                    self._wymien_kanal_weryfikacji()
                return wyniki
            # Pomiar opóźnień (pomiar 18.10.2026): ile pytań, ile bez odpowiedzi,
            # po jakim czasie przyszła ostatnia odpowiedź i jaki był limit.
            ost = "brak" if ocz.ostatnia is None else f"{(ocz.ostatnia - ocz.start) * 1000:.0f} ms"
            log.info("brak odpowiedzi na %d zapytań z %d (próba %d, ostatnia odpowiedź po %s, limit %.0f ms), np. %s",
                     len(brak), pytane, proba + 1, ost, limit * 1000, brak[0])
            self._wymien_kanal_weryfikacji()
            proba += 1
            if len(brak) < pytane:
                poczatek_ciszy = None            # część odpowiedzi doszła: mikser żyje
            elif poczatek_ciszy is None:
                poczatek_ciszy = ocz.start
            cisza = 0.0 if poczatek_ciszy is None else time.monotonic() - poczatek_ciszy
            if proba > self.dodatkowe_proby and cisza >= self.cisza_utraty:
                break
            if proba > self.dodatkowe_proby + 40:
                break                            # bezpiecznik: odpowiedzi kapią bez końca
            if self.przerwa_ponowienia > 0:
                time.sleep(self.przerwa_ponowienia)
        raise BrakOdpowiedzi(f"brak odpowiedzi dla {len(brak)} parametrów, np. {brak[0]}")

    def _pomiar(self, pytane: int, brak: int, ocz: "_Oczekiwanie", limit: float, powtorki: int = 0) -> None:
        """Zbiorczy pomiar co 60 s do dziennika: czasy pełnych odpowiedzi porcji
        i odsetek porcji z brakami. Rozstrzyga, czy limit jest za krótki
        (odpowiedzi tuż za limitem), czy mikser gubi pytania."""
        s = self.__dict__.setdefault("_staty", {"porcje": 0, "z_brakami": 0, "pytania": 0, "braki": 0,
                                               "powtorki": 0, "czasy": [], "od": time.monotonic()})
        s["porcje"] += 1
        s["powtorki"] = s.get("powtorki", 0) + powtorki
        s["pytania"] += pytane
        s["braki"] += brak
        if brak:
            s["z_brakami"] += 1
        elif ocz.ostatnia is not None:
            s["czasy"].append((ocz.ostatnia - ocz.start) * 1000)
        if time.monotonic() - s["od"] >= 60:
            cz = sorted(s["czasy"]) or [0.0]
            log.info("pomiar odczytów 60 s: porcji %d, z brakami %d, pytań %d, bez odpowiedzi %d, szybkich powtórek %d; "
                     "pełna porcja: mediana %.0f ms, 90%% %.0f ms, maks. %.0f ms; limit dla 24 pytań %.0f ms; "
                     "okno %d, powtórka po %.0f ms; opóźnienie miksera %.0f ms",
                     s["porcje"], s["z_brakami"], s["pytania"], s["braki"], s["powtorki"], cz[len(cz) // 2],
                     cz[int(len(cz) * 0.9)], cz[-1], self.limit * (1 + 24 / 32) * 1000,
                     self.okno, self._odstep_powtorki() * 1000, self.opoznienie * 1000)
            self._staty = {"porcje": 0, "z_brakami": 0, "pytania": 0, "braki": 0, "powtorki": 0, "czasy": [],
                           "od": time.monotonic()}

    def odczytaj_wiele(self, adresy: Iterable[str]) -> dict[str, object]:
        adresy = list(dict.fromkeys(adresy))
        wynik: dict[str, object] = {}
        # Z oknem jedna runda na całą listę: zgubione pytania z różnych porcji
        # czekają na powtórkę równocześnie, nie jedna porcja po drugiej.
        porcja = self.porcja if self.okno <= 0 else max(1, len(adresy))
        with self._blokada:
            for i in range(0, len(adresy), porcja):
                wynik.update(self._odczytaj_porcje(adresy[i:i + porcja]))
        return wynik

    def odczytaj(self, adres: str):
        return self.odczytaj_wiele([adres])[adres]

    def identyfikuj(self) -> tuple:
        """/xinfo: zwraca argumenty odpowiedzi (adres, nazwa, model, wersja)."""
        with self._blokada:
            start = time.monotonic()
            proba = 0
            while True:
                proba += 1
                zebrane: list[tuple] = []
                zd = threading.Event()

                def odb(dane, _nadawca, _z=zebrane, _zd=zd):
                    try:
                        komunikaty = osc.dekoduj(dane)
                    except osc.BladOSC:
                        return
                    self._znacznik()
                    for k in komunikaty:
                        if k.adres in ("/xinfo", "/info"):
                            _z.append(k.argumenty)
                            _zd.set()

                kanal = self.transport.otworz_kanal(odb)   # osobny kanał na każdą próbę
                try:
                    kanal.wyslij(osc.koduj(sciezki.XINFO))
                    self.wyslane_pakiety += 1
                    czekaj = self.limit * 2
                    if self.dopasuj:
                        czekaj = max(czekaj, min(self.maks_limit_rundy, 3 * self.opoznienie))
                    if zd.wait(czekaj):
                        return zebrane[0]
                finally:
                    kanal.zamknij()
                if proba > self.dodatkowe_proby and time.monotonic() - start >= self.cisza_utraty:
                    break
                if self.przerwa_ponowienia > 0:
                    time.sleep(self.przerwa_ponowienia)
        raise BrakOdpowiedzi("brak odpowiedzi na /xinfo")

    # --- zapis ------------------------------------------------------------
    def wyslij(self, adres: str, wartosc) -> None:
        """Zapis bez czekania na potwierdzenie. Tylko dla suwaków: ruch daje
        wiele kolejnych wartości, potwierdza je późniejszy odczyt."""
        typ = sciezki.typ_sciezki(adres)
        with self._blokada:
            self._wyslij(osc.koduj(adres, wartosc, typy=typ))

    def ustaw(self, adres: str, wartosc) -> WynikZapisu:
        """Zapis jawnej wartości z potwierdzeniem odczytem.

        Zwraca wynik także wtedy, gdy mikser odpowiedział inną wartością
        (zapis nieprzyjęty). Zgłasza BrakOdpowiedzi, gdy mikser milczy.
        """
        typ = sciezki.typ_sciezki(adres)
        pakiet = osc.koduj(adres, wartosc, typy=typ)
        odczytana = None
        proby = 0
        for proby in range(1, self.dodatkowe_proby + 2):
            with self._blokada:
                self._wyslij(pakiet)
            odczytana = self.odczytaj(adres)   # BrakOdpowiedzi przerywa
            if zgodne(wartosc, odczytana, self.tolerancja):
                break
            log.info("zapis %s=%r nieprzyjęty, odczyt %r (próba %d)", adres, wartosc, odczytana, proby)
        return WynikZapisu(adres, wartosc, odczytana, proby)
