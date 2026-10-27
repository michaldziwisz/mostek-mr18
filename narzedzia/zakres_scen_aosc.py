"""Zakres scen AOSC bez routingu: sceny niosą brzmienie, antenę i wysyłki prowadzi mostek.

AOSC (AZ Accessible OSC) z układem Air Access 18 zapisuje i wczytuje scenę
według pliku x.sct: jedna ścieżka OSC w wierszu. Pliki scen (*.scn) mają ten
sam układ, z wartościami po ścieżce. Pełny x.sct obejmuje też sumę, suwaki,
wysyłki, routing USB i odsłuch, więc wczytanie sceny w trakcie emisji
przestawiłoby antenę (plan, rozdz. o AOSC).

Narzędzie usuwa z pliku wiersze, które należą do mostka albo do stałego
profilu stanowiska, a zostawia brzmienie: EQ, dynamikę, bramkę, gain,
insert, efekty. Działa na x.sct i na plikach scen. Bez --zapisz tylko
pokazuje, co by usunęło.

    python narzedzia\\zakres_scen_aosc.py x.sct
    python narzedzia\\zakres_scen_aosc.py x.sct --wyjscie x-bez-routingu.sct --zapisz
    python narzedzia\\zakres_scen_aosc.py "Moja scena.scn" --wyjscie "Moja scena bez routingu.scn" --zapisz

NIE SPRAWDZONO z AOSC i MR18: czy AOSC przyjmuje skrócony x.sct, czy przy
wczytaniu starej, pełnej sceny bierze tylko ścieżki z x.sct i czy kolejność
wierszy ma znaczenie. Do testu w etapie 4, poza anteną.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Każda reguła: (wzorzec ścieżki, powód). Ścieżka to pierwszy wyraz wiersza.
USUWANE: tuple[tuple[str, str], ...] = (
    (r"^/ch/\d\d/mix(/\d\d)?$", "suma, suwak, panorama i wysyłki kanału (mostek)"),
    (r"^/ch/\d\d/grp$", "przypisanie do DCA i grup wyciszeń (profil, mostek sprawdza brak)"),
    (r"^/ch/\d\d/config$", "źródło wejścia kanału (insrc): duplikat mikrofonu byłby drogą obejścia"),
    (r"^/rtn/(\d|aux)/mix(/\d\d)?$", "powroty FX i AUX na sumę i do szyn rozmówców"),
    (r"^/rtn/(\d|aux)/grp$", "grupy powrotów"),
    (r"^/bus/\d/mix$", "wyciszenie, poziom i LR szyn: głośniki, podsłuch, powroty (mostek)"),
    (r"^/bus/\d/grp$", "grupy szyn"),
    (r"^/fxsend/\d/grp$", "grupy szyn FX"),
    (r"^/lr/mix$", "suma główna: wyciszenie lub suwak na dole zdejmuje całą antenę"),
    (r"^/routing(/|$)", "routing USB i wyjść: IN 3-4 to tor do RadioCastera"),
    (r"^/config/(chlink|buslink|linkcfg)$", "łączenie par kanałów i szyn (profil)"),
    (r"^/config/solo$", "źródło odsłuchu i PFL (mostek)"),
    (r"^/config/mute$", "grupy wyciszeń"),
)
_REGULY = tuple((re.compile(w), p) for w, p in USUWANE)


def powod_usuniecia(sciezka: str) -> str | None:
    for wzorzec, powod in _REGULY:
        if wzorzec.search(sciezka):
            return powod
    return None


def filtruj(tekst: str) -> tuple[str, list[tuple[str, str]], int]:
    """Zwraca (nowy tekst, usunięte [(ścieżka, powód)], liczba zostawionych wierszy).

    Zachowuje końce wierszy i kolejność. Wiersze puste i niezaczynające się
    od „/” zostawia bez zmian (mogą być nagłówkiem pliku sceny).
    """
    wynik: list[str] = []
    usuniete: list[tuple[str, str]] = []
    zostawione = 0
    for wiersz in tekst.splitlines(keepends=True):
        tresc = wiersz.strip()
        if not tresc.startswith("/"):
            wynik.append(wiersz)
            continue
        sciezka = tresc.split()[0]
        powod = powod_usuniecia(sciezka)
        if powod:
            usuniete.append((sciezka, powod))
        else:
            wynik.append(wiersz)
            zostawione += 1
    return "".join(wynik), usuniete, zostawione


def sprawdz_wynik(tekst: str) -> list[str]:
    """Ścieżki objęte regułami, które mimo to zostały (powinna być pusta lista)."""
    zle = []
    for wiersz in tekst.splitlines():
        t = wiersz.strip()
        if t.startswith("/") and powod_usuniecia(t.split()[0]):
            zle.append(t.split()[0])
    return zle


def podsumowanie(usuniete: list[tuple[str, str]]) -> list[str]:
    licz: dict[str, int] = {}
    for _s, p in usuniete:
        licz[p] = licz.get(p, 0) + 1
    return [f"{n} wierszy: {p}" for p, n in licz.items()]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Zakres scen AOSC bez routingu i wysyłek")
    p.add_argument("plik", help="x.sct albo plik sceny .scn")
    p.add_argument("--wyjscie", help="plik wynikowy (nie może być tym samym plikiem)")
    p.add_argument("--zapisz", action="store_true", help="zapisz plik wynikowy; bez tego tylko podgląd")
    a = p.parse_args(argv)
    wej = Path(a.plik)
    dane = wej.read_bytes()
    tekst = dane.decode("utf-8", errors="surrogateescape")
    nowy, usuniete, zostawione = filtruj(tekst)
    print(f"{wej.name}: zostaje {zostawione} wierszy, usuniętych {len(usuniete)}.")
    for w in podsumowanie(usuniete):
        print("  " + w)
    zle = sprawdz_wynik(nowy)
    if zle:
        print("BŁĄD: w wyniku zostały ścieżki objęte regułami: " + ", ".join(zle[:5]))
        return 2
    if not a.zapisz:
        print("Podgląd. Nic nie zapisano; dodaj --wyjscie PLIK --zapisz.")
        return 0
    if not a.wyjscie:
        print("Brak --wyjscie. Plik źródłowy nie jest nadpisywany.")
        return 2
    wyj = Path(a.wyjscie)
    if wyj.resolve() == wej.resolve():
        print("Plik wynikowy musi być inny niż źródłowy.")
        return 2
    wyj.write_bytes(nowy.encode("utf-8", errors="surrogateescape"))
    print(f"Zapisano {wyj}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
