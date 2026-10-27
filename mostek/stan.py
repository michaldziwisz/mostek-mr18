"""Model stanu MR18 widzianego przez mostek.

Rozróżnia wartość POTWIERDZONĄ (przyszła od miksera: odpowiedź na zapytanie
albo zgłoszenie zmiany przez /xremote) od wartości WYSŁANEJ (pakiet poszedł,
mikser jeszcze nie odpowiedział). Mostek mówi i decyduje wyłącznie na
podstawie wartości potwierdzonych. Na starcie i po utracie łączności
wszystko jest NIEZNANE.
"""

from __future__ import annotations

from dataclasses import dataclass


class _Nieznany:
    _instancja = None

    def __new__(cls):
        if cls._instancja is None:
            cls._instancja = super().__new__(cls)
        return cls._instancja

    def __repr__(self) -> str:
        return "NIEZNANY"

    def __bool__(self) -> bool:  # NIEZNANY nigdy nie jest prawdą
        return False


NIEZNANY = _Nieznany()


@dataclass
class Wpis:
    wartosc: object
    czas: float


class StanMiksera:
    def __init__(self) -> None:
        self._potwierdzone: dict[str, Wpis] = {}
        self._wyslane: dict[str, Wpis] = {}
        self.polaczony = False
        self.zsynchronizowany = False
        self.ostatnia_odpowiedz = float("-inf")

    # --- odczyt -----------------------------------------------------------
    def wartosc(self, adres: str):
        if not self.polaczony:
            return NIEZNANY
        wpis = self._potwierdzone.get(adres)
        return NIEZNANY if wpis is None else wpis.wartosc

    def czy_znany(self, adres: str) -> bool:
        return self.wartosc(adres) is not NIEZNANY

    def wyslane(self, adres: str):
        wpis = self._wyslane.get(adres)
        return NIEZNANY if wpis is None else wpis.wartosc

    def w_toku(self) -> bool:
        return bool(self._wyslane)

    def adresy(self):
        return list(self._potwierdzone)

    # --- zapis ------------------------------------------------------------
    def potwierdz(self, adres: str, wartosc, czas: float) -> None:
        self._potwierdzone[adres] = Wpis(wartosc, czas)
        self.ostatnia_odpowiedz = max(self.ostatnia_odpowiedz, czas)

    def zapomnij(self, adres: str) -> None:
        self._potwierdzone.pop(adres, None)

    def zanotuj_wyslanie(self, adres: str, wartosc, czas: float) -> None:
        self._wyslane[adres] = Wpis(wartosc, czas)

    def zakoncz_wyslanie(self, adres: str) -> None:
        self._wyslane.pop(adres, None)

    def utrata(self) -> None:
        """Utrata łączności: wszystko NIEZNANE, nic nie jest przywracane."""
        self.polaczony = False
        self.zsynchronizowany = False
        self._potwierdzone.clear()
        self._wyslane.clear()

    def nowa_sesja(self) -> None:
        """Początek odczytu po (ponownym) połączeniu. Stare wartości nie wracają."""
        self._potwierdzone.clear()
        self._wyslane.clear()
        self.polaczony = True
        self.zsynchronizowany = False
