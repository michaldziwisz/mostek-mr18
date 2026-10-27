"""Liczniki czasu i polska odmiana liczebników (plan v21, rozdz. 8, pkt 3).

Status mówi czas od potwierdzonej zmiany stanu, np. „Mikrofon na antenie od
2 minut 10 sekund. Słuchacz czeka od 40 sekund”. Po przyimku „od” liczebnik
stoi w dopełniaczu: od 1 minuty, od 2 minut, od 5 minut, od 22 minut. Bez
przyimka (mianownik) obowiązuje zwykła reguła: 1 minuta, 2 minuty, 5 minut,
12 minut, 22 minuty.
"""

from __future__ import annotations

# Formy: (jeden, dwa do cztery, pięć i więcej) w mianowniku.
GODZINA = ("godzina", "godziny", "godzin")
MINUTA = ("minuta", "minuty", "minut")
SEKUNDA = ("sekunda", "sekundy", "sekund")

# Dopełniacz po „od”: liczba pojedyncza tylko dla jedności, reszta to
# dopełniacz liczby mnogiej (od dwóch minut, od dwudziestu dwóch minut).
DOPELNIACZ = {GODZINA: ("godziny", "godzin"), MINUTA: ("minuty", "minut"), SEKUNDA: ("sekundy", "sekund")}


def odmiana(n: int, formy: tuple[str, str, str]) -> str:
    """Forma rzeczownika po liczebniku w mianowniku (1 minuta, 3 minuty, 5 minut)."""
    n = abs(int(n))
    if n == 1:
        return formy[0]
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return formy[1]
    return formy[2]


def odmiana_dopelniacz(n: int, formy: tuple[str, str, str]) -> str:
    """Forma po przyimku „od” (od 1 minuty, od 3 minut, od 22 minut)."""
    pojedyncza, mnoga = DOPELNIACZ[formy]
    return pojedyncza if abs(int(n)) == 1 else mnoga


def czas_slownie(sekundy: float, przypadek: str = "dopelniacz") -> str:
    """Czas trwania słownie: godziny i minuty, a poniżej godziny minuty i sekundy.

    przypadek „dopelniacz” (po „od”) albo „mianownik”. Poniżej sekundy pusty
    napis: status mówi wtedy sam stan, bez czasu.
    """
    calk = int(max(0.0, float(sekundy)))
    odm = odmiana_dopelniacz if przypadek == "dopelniacz" else odmiana
    if calk < 1:
        return ""
    g, reszta = divmod(calk, 3600)
    m, s = divmod(reszta, 60)
    czesci = []
    if g:
        czesci.append(f"{g} {odm(g, GODZINA)}")
        if m:
            czesci.append(f"{m} {odm(m, MINUTA)}")
        return " ".join(czesci)
    if m:
        czesci.append(f"{m} {odm(m, MINUTA)}")
    if s:
        czesci.append(f"{s} {odm(s, SEKUNDA)}")
    return " ".join(czesci)
