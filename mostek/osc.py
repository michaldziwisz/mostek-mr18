"""Kodek OSC 1.0 w bibliotece standardowej.

Zakres zgodny z dokumentem producenta „X AIR Mixer Series Remote Control
Protocol (firmware 1.11 or higher)”, rozdział „Type rules”: parametry
big-endian, wyrównanie do 4 bajtów, float 32 bit, int 32 bit ze znakiem,
łańcuchy zakończone zerem. Kopia dokumentu:
dokument „X AIR Mixer Series Remote Control Protocol”, wiersze 70-75.

Obsługiwane typy: i (int32), f (float32), s (string), b (blob).
Pakiety „#bundle” są dekodowane (MR18 ich nie wymaga, ale kodek ich nie
odrzuca). Nieznany typ powoduje BladOSC, a nie zgadywanie.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


class BladOSC(ValueError):
    """Pakiet nie jest poprawnym komunikatem OSC."""


@dataclass(frozen=True)
class Komunikat:
    adres: str
    argumenty: tuple = field(default_factory=tuple)
    typy: str = ""

    @property
    def wartosc(self):
        """Pierwszy argument albo None (zapytanie bez argumentu)."""
        return self.argumenty[0] if self.argumenty else None


def _pad(dane: bytes) -> bytes:
    return dane + b"\x00" * ((4 - len(dane) % 4) % 4)


def _koduj_lancuch(tekst: str) -> bytes:
    surowe = tekst.encode("utf-8")
    if b"\x00" in surowe:
        raise BladOSC("łańcuch OSC nie może zawierać bajtu zerowego")
    return _pad(surowe + b"\x00")


def koduj(adres: str, *argumenty, typy: str | None = None) -> bytes:
    """Zakoduj komunikat. Bez argumentów powstaje zapytanie (get).

    `typy` wymusza znaczniki typów, np. "f" dla wartości 0, którą trzeba
    wysłać jako float. Bez `typy` int -> i, float -> f, str -> s, bytes -> b.
    """
    if not adres.startswith("/"):
        raise BladOSC(f"adres OSC musi zaczynać się od '/': {adres!r}")
    if typy is None:
        typy = ""
        for a in argumenty:
            if isinstance(a, bool):
                typy += "i"
            elif isinstance(a, int):
                typy += "i"
            elif isinstance(a, float):
                typy += "f"
            elif isinstance(a, str):
                typy += "s"
            elif isinstance(a, (bytes, bytearray)):
                typy += "b"
            else:
                raise BladOSC(f"nieobsługiwany typ argumentu: {type(a).__name__}")
    if len(typy) != len(argumenty):
        raise BladOSC("liczba typów nie zgadza się z liczbą argumentów")
    wynik = _koduj_lancuch(adres) + _koduj_lancuch("," + typy)
    for t, a in zip(typy, argumenty):
        if t == "i":
            wynik += struct.pack(">i", int(a))
        elif t == "f":
            wynik += struct.pack(">f", float(a))
        elif t == "s":
            wynik += _koduj_lancuch(str(a))
        elif t == "b":
            surowe = bytes(a)
            wynik += struct.pack(">i", len(surowe)) + _pad(surowe)
        else:
            raise BladOSC(f"nieobsługiwany znacznik typu: {t!r}")
    return wynik


def _czytaj_lancuch(dane: bytes, poz: int) -> tuple[str, int]:
    koniec = dane.find(b"\x00", poz)
    if koniec < 0:
        raise BladOSC("łańcuch bez zakończenia")
    tekst = dane[poz:koniec].decode("utf-8", errors="replace")
    nast = koniec + 1
    nast += (4 - nast % 4) % 4
    if nast > len(dane):
        raise BladOSC("łańcuch wychodzi poza pakiet")
    return tekst, nast


def dekoduj(dane: bytes) -> list[Komunikat]:
    """Zdekoduj pakiet do listy komunikatów (bundle daje wiele)."""
    if len(dane) % 4:
        raise BladOSC("długość pakietu OSC nie jest wielokrotnością 4")
    if dane.startswith(b"#bundle\x00"):
        if len(dane) < 16:
            raise BladOSC("za krótki bundle")
        poz = 16  # "#bundle\0" + 8 bajtów znacznika czasu
        wynik: list[Komunikat] = []
        while poz < len(dane):
            if poz + 4 > len(dane):
                raise BladOSC("urwany element bundle")
            (rozmiar,) = struct.unpack(">i", dane[poz:poz + 4])
            poz += 4
            if rozmiar < 0 or poz + rozmiar > len(dane):
                raise BladOSC("zły rozmiar elementu bundle")
            wynik.extend(dekoduj(dane[poz:poz + rozmiar]))
            poz += rozmiar
        return wynik
    adres, poz = _czytaj_lancuch(dane, 0)
    if not adres.startswith("/"):
        raise BladOSC(f"adres nie zaczyna się od '/': {adres!r}")
    if poz >= len(dane):
        return [Komunikat(adres, (), "")]
    typy, poz = _czytaj_lancuch(dane, poz)
    if not typy.startswith(","):
        raise BladOSC("brak znacznika typów")
    typy = typy[1:]
    argumenty = []
    for t in typy:
        if t == "i":
            if poz + 4 > len(dane):
                raise BladOSC("urwany int")
            argumenty.append(struct.unpack(">i", dane[poz:poz + 4])[0])
            poz += 4
        elif t == "f":
            if poz + 4 > len(dane):
                raise BladOSC("urwany float")
            argumenty.append(struct.unpack(">f", dane[poz:poz + 4])[0])
            poz += 4
        elif t == "s":
            tekst, poz = _czytaj_lancuch(dane, poz)
            argumenty.append(tekst)
        elif t == "b":
            if poz + 4 > len(dane):
                raise BladOSC("urwany blob")
            (rozmiar,) = struct.unpack(">i", dane[poz:poz + 4])
            poz += 4
            if rozmiar < 0 or poz + rozmiar > len(dane):
                raise BladOSC("zły rozmiar blob")
            argumenty.append(dane[poz:poz + rozmiar])
            poz += rozmiar + (4 - rozmiar % 4) % 4
        else:
            raise BladOSC(f"nieobsługiwany znacznik typu: {t!r}")
    return [Komunikat(adres, tuple(argumenty), typy)]
