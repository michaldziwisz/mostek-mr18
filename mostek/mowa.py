"""Mowa: kolejka komunikatów z priorytetem i wyjścia (NVDA, konsola, atrapa).

Zasady z planu (rozdział 8 i 11):
  * komunikat stanu powstaje dopiero z odczytu miksera (pilnuje tego rdzeń),
  * komunikaty bezpieczeństwa mają pierwszeństwo przed resztą kolejki,
  * nowy komunikat o tym samym kluczu zastępuje stary, który jeszcze nie padł,
  * mowa idzie przez NVDA (syntezator sprzętowy), nigdy przez urządzenie MR18,
  * utrata mowy nie wycisza programu; jest osobnym alarmem w dzienniku
    i krótkim dźwiękiem przez domyślną kartę Windows.

NVDA: biblioteka NVDA Controller Client, funkcje nvdaController_testIfRunning
i nvdaController_speakText, wywołanie przez ctypes. Źródło: README
extras/controllerClient w repozytorium NVDA (kopia
dokumentacja nvdaControllerClient w repozytorium NVDA) oraz przykład
extras/controllerClient/examples/example_python.py. Wszystkie funkcje
zwracają 0 przy powodzeniu, inaczej kod błędu Windows.
"""

from __future__ import annotations

import itertools
import logging
import sys
import threading
import time
from enum import IntEnum
from pathlib import Path

log = logging.getLogger("mostek.mowa")


class Priorytet(IntEnum):
    BEZPIECZENSTWO = 0
    STAN = 1
    INFORMACJA = 2


class BladMowy(RuntimeError):
    pass


class BrakNVDA(BladMowy):
    """NVDA Controller Client niedostępny (np. system inny niż Windows)."""


# --- wyjścia ---------------------------------------------------------------

class AtrapaMowy:
    """Zapamiętuje wypowiedzi. Do testów."""

    def __init__(self) -> None:
        self.powiedziane: list[str] = []
        self.przerwania = 0
        self.awaria = False

    def przerwij(self) -> None:
        self.przerwania += 1

    def mow(self, tekst: str) -> None:
        if self.awaria:
            raise BladMowy("atrapa: symulowana awaria mowy")
        self.powiedziane.append(tekst)


class MowaKonsola:
    """Wypisuje komunikat w konsoli (czytanej przez NVDA). Do pracy z symulatorem."""

    def __init__(self, strumien=None) -> None:
        self.strumien = strumien or sys.stdout

    def mow(self, tekst: str) -> None:
        print(f"[mowa] {tekst}", file=self.strumien, flush=True)

    def przerwij(self) -> None:
        pass  # tekst w konsoli już wypisany; NVDA czyta go sama


class MowaNVDA:
    """NVDA przez nvdaControllerClient.dll. Tylko Windows; import strzeżony."""

    def __init__(self, sciezka_dll: str | Path | None = None) -> None:
        if sys.platform != "win32":
            raise BrakNVDA("NVDA Controller Client działa tylko w Windows")
        import ctypes  # noqa: PLC0415 - import tylko w Windows

        kandydaci = [sciezka_dll] if sciezka_dll else []
        from .ustawienia import KATALOG  # import lokalny: ustawienia używają Komunikat
        katalog = KATALOG / "biblioteki"
        bity = "x64" if ctypes.sizeof(ctypes.c_void_p) == 8 else "x86"
        kandydaci += [katalog / bity / "nvdaControllerClient.dll",
                      katalog / "nvdaControllerClient.dll", "nvdaControllerClient.dll"]
        ostatni_blad = None
        self._dll = None
        for k in kandydaci:
            try:
                self._dll = ctypes.windll.LoadLibrary(str(k))
                break
            except OSError as e:
                ostatni_blad = e
        if self._dll is None:
            raise BrakNVDA(f"nie znaleziono nvdaControllerClient.dll: {ostatni_blad}")
        self._dll.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
        self._dll.nvdaController_speakText.restype = ctypes.c_ulong
        self._dll.nvdaController_testIfRunning.restype = ctypes.c_ulong
        self._dll.nvdaController_cancelSpeech.restype = ctypes.c_ulong

    def dziala(self) -> bool:
        return self._dll.nvdaController_testIfRunning() == 0

    def mow(self, tekst: str) -> None:
        kod = self._dll.nvdaController_speakText(tekst)
        if kod != 0:
            raise BladMowy(f"nvdaController_speakText zwróciło kod {kod}")

    def przerwij(self) -> None:
        kod = self._dll.nvdaController_cancelSpeech()
        if kod != 0:
            raise BladMowy(f"nvdaController_cancelSpeech zwróciło kod {kod}")


def dzwiek_alarmu() -> None:
    """Krótki dźwięk przez domyślne urządzenie Windows (zintegrowana karta)."""
    if sys.platform == "win32":
        try:
            import winsound  # noqa: PLC0415
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:  # noqa: BLE001
            log.exception("nie udało się odtworzyć dźwięku alarmu")


# --- kolejka -----------------------------------------------------------------

class KolejkaMowy:
    """Kolejka komunikatów: dźwięk (tryby z dźwiękami), potem mowa.

    Wpis: [priorytet, numer, tekst, klucz, dźwięki, mówić, mowa zastępcza]. Reguła kolejności
    (README, „Kolejność dźwięku i mowy”): mowa komunikatu rusza razem z jego
    pierwszym dźwiękiem (Michał, 20.10.2026: reakcja maksymalnie szybka);
    dźwięki komunikatu grają po kolei, a każdy nowy komunikat ucina dźwięki
    komunikatu, którego mowa już poszła. Komunikat bez mowy (tryb dźwięków)
    gra dźwięki do końca jak dotąd. Dźwięk nieudany albo
    niedostępny: mowa zamiast niego. Komunikat o wyższym priorytecie (np.
    ostrzeżenie w trakcie dźwięku stanu) przerywa dźwięk; przerwany komunikat
    wraca do kolejki za ostrzeżeniem i zabrzmi od przerwanego dźwięku, chyba
    że zastąpił go nowszy komunikat o tym samym kluczu. Mowa, która już
    trafiła do NVDA, nie jest przerywana, z jednym wyjątkiem: komunikat
    o kluczu z PRZERYWALNE ucina w NVDA poprzedni komunikat o tym samym
    kluczu (Michał, 24.10.2026: szybkie chodzenie po playliście ma czytać
    bieżącą pozycję, a nie kolejkować poprzednie). Inny komunikat, który
    zabrzmiał w międzyczasie, nigdy nie jest ucinany.
    Sygnały talkbacku nie mają mowy także po błędzie audio. Przerwane przez
    ostrzeżenie nie wracają do kolejki jako spóźnione potwierdzenie.
    """

    PRZERYWALNE = frozenset({"emisja-kursor", "emisja-miks", "nauka"})

    def __init__(self, wyjscie, alarm=dzwiek_alarmu, dzwieki=None) -> None:
        self.wyjscie = wyjscie
        self.alarm = alarm
        # Odtwarzacz dźwięków komunikatów: obiekt z odtworz(klucz) -> czas albo
        # None i zatrzymaj() (informacja.InformacjaZwrotna). None = bez dźwięków.
        self.dzwieki = dzwieki
        self._licznik = itertools.count()
        self._oczekujace: list[list] = []   # [priorytet, numer, tekst, klucz, dzwieki, mow, zastepcza_mowa]
        self._blokada = threading.Condition()
        self._watek: threading.Thread | None = None
        self._dziala = False
        self.bledy_mowy = 0
        self._ostatni_klucz: str | None = None
        self._aktywny = None
        self._dolaczone = []

    def powiedz(self, tekst: str, priorytet: Priorytet = Priorytet.STAN,
                klucz: str | None = None, dzwieki=(), mow: bool = True,
                zastepcza_mowa: bool = True) -> None:
        dzwieki = list(dzwieki) if self.dzwieki is not None else []
        if not dzwieki and zastepcza_mowa:
            mow = True          # zwykły komunikat bez dźwięku zawsze ma mowę
        if dzwieki:
            log.info("komunikat [%s] dzwieki=%s%s: %s", priorytet.name, ",".join(dzwieki),
                     "" if mow else " bez mowy", tekst)
        else:
            log.info("komunikat [%s]: %s", priorytet.name, tekst)
        with self._blokada:
            if klucz is not None:
                for wpis in self._oczekujace:
                    if wpis[3] == klucz:
                        wpis[0] = min(wpis[0], int(priorytet))
                        wpis[2], wpis[4], wpis[5], wpis[6] = tekst, dzwieki, mow, zastepcza_mowa
                        self._blokada.notify()
                        return
            self._oczekujace.append([int(priorytet), next(self._licznik), tekst, klucz, dzwieki, mow, zastepcza_mowa])
            self._blokada.notify()

    def sygnal(self, zdarzenie: str) -> None:
        """Potwierdzony sygnał bez tekstu NVDA, także po błędzie dźwięku.
        Nie zmienia ostatniego komunikatu F5. Gra w wątku kolejki, nie OSC."""
        if self.dzwieki is None:
            log.warning("sygnał %s niedostępny: brak odtwarzacza, bez zastępczej mowy", zdarzenie)
            return
        klucze = self.dzwieki.plan_sygnalu(zdarzenie)
        if klucze:
            self.powiedz(zdarzenie, dzwieki=klucze, mow=False, zastepcza_mowa=False)

    def dolacz(self, tekst, zdarzenie, dzwieki=(), mow=True) -> bool:
        """Potwierdzenie powiązane z mikrofonem: tekst po nim, dźwięki naraz.

        Bez czekania na sieć. Gdy dźwięk mikrofonu już trwa, dołożony głos
        odbiera wątek mowy; nigdy wątek MR18/TCP. Zapas winsound zostaje
        sekwencyjny. Zwraca False, gdy nie ma już czego łączyć.
        """
        with self._blokada:
            for w in reversed(self._oczekujace):
                if w[0] == Priorytet.STAN and zdarzenie in getattr(w[2], "zdarzenia", ()):
                    w[2] = w[2] + ". " + tekst
                    w[3] = "mikrofon-hold"
                    w[4] = list(dict.fromkeys(w[4] + list(dzwieki)))
                    w[5] = w[5] or mow
                    self._blokada.notify_all()
                    return True
            w = self._aktywny
            if (self._naraz() and w is not None and w[0] == Priorytet.STAN
                    and zdarzenie in getattr(w[2], "zdarzenia", ())):
                self._dolaczone.append([int(Priorytet.STAN), next(self._licznik), tekst,
                                       "emisja-hold", list(dzwieki), mow, True])
                self._blokada.notify_all()
                return True
        return False

    def _pobierz(self):
        if not self._oczekujace:
            return None
        self._oczekujace.sort(key=lambda w: (w[0], w[1]))
        return self._oczekujace.pop(0)

    def oczekujace(self) -> list[str]:
        with self._blokada:
            return [w[2] for w in sorted(self._oczekujace, key=lambda w: (w[0], w[1]))]

    def _wypowiedz(self, tekst: str, klucz: str | None = None) -> None:
        tekst = str(tekst)
        if klucz in self.PRZERYWALNE and self._ostatni_klucz == klucz:
            przerwij = getattr(self.wyjscie, "przerwij", None)
            if przerwij is not None:
                try:
                    przerwij()
                except Exception:  # noqa: BLE001 - nieudane ucięcie nie blokuje mowy
                    log.debug("przerwanie mowy", exc_info=True)
        self._ostatni_klucz = klucz
        try:
            self.wyjscie.mow(tekst)
        except Exception as e:  # noqa: BLE001
            self.bledy_mowy += 1
            log.error("ALARM: mowa niedostępna (%s), komunikat: %s", e, tekst)
            if self.alarm:
                self.alarm()

    def _odtworz(self, klucz: str):
        try:
            return self.dzwieki.odtworz(klucz)
        except Exception:  # noqa: BLE001 - błąd dźwięku nie wywraca mostka
            log.exception("odtwarzanie dźwięku %s", klucz)
            return None

    def _czekaj(self, czas: float, priorytet: int, kazdy: bool = False) -> bool:
        """Czeka do końca dźwięku. Zwraca prawdę, gdy w kolejce pojawił się
        komunikat o wyższym priorytecie (dźwięk trzeba przerwać), a przy
        kazdy=True dowolny nowy komunikat."""
        koniec = time.monotonic() + max(0.0, float(czas))
        with self._blokada:
            while True:
                if self._dolaczone:
                    wpisy, self._dolaczone = self._dolaczone, []
                    # waveOut otwiera osobne głosy; bez zatrzymania mikrofonu.
                    for wpis in wpisy:
                        self._wykonaj(wpis, czekaj=False)
                if any(kazdy or w[0] < priorytet for w in self._oczekujace):  # POPRAWKA: ostrzeżenie przerywa
                    return True
                zostalo = koniec - time.monotonic()
                if zostalo <= 0 or not self._dziala:
                    return False
                self._blokada.wait(zostalo)

    def _naraz(self) -> bool:
        return bool(getattr(self.dzwieki, "naraz", False)) and hasattr(self.dzwieki, "odtworz_naraz")

    def _wykonaj_naraz(self, wpis: list, czekaj: bool) -> None:
        """Michał, 23.10.2026: wszystkie dźwięki komunikatu ruszają razem
        (osobne głosy, miksuje Windows), mowa rusza z nimi. Reszta zasad jak
        przy dźwiękach po kolei: po mowie każdy nowy komunikat ucina dźwięki,
        bez mowy ucina je tylko komunikat o wyższym priorytecie, a przerwany
        komunikat wraca do kolejki w całości."""
        priorytet, numer, tekst, klucz, dzwieki, mow, zastepcza_mowa = wpis
        try:
            czas, braki = self.dzwieki.odtworz_naraz(dzwieki)
        except Exception:  # noqa: BLE001 - błąd dźwięku nie wywraca mostka
            log.exception("odtwarzanie dźwięków %s", dzwieki)
            czas, braki = None, True
        if braki and zastepcza_mowa:
            mow = True  # POPRAWKA NARAZ: brak pliku albo błąd odtwarzania, mowa zamiast dźwięku
        if mow:
            self._wypowiedz(tekst, klucz)
        if braki and not zastepcza_mowa:
            log.warning("sygnał %s: błąd dźwięku, bez zastępczej mowy", tekst)
        if czas is None or not czekaj:
            return
        if self._czekaj(czas, priorytet, kazdy=mow):
            try:
                self.dzwieki.zatrzymaj()
            except Exception:  # noqa: BLE001
                log.debug("zatrzymanie dźwięku", exc_info=True)
            if not mow and zastepcza_mowa:
                with self._blokada:
                    if klucz is None or all(w[3] != klucz for w in self._oczekujace):
                        self._oczekujace.append([priorytet, numer, tekst, klucz, dzwieki, mow, zastepcza_mowa])

    def _wykonaj(self, wpis: list, czekaj: bool) -> None:
        priorytet, numer, tekst, klucz, dzwieki, mow, zastepcza_mowa = wpis
        if dzwieki and self._naraz():
            self._wykonaj_naraz(wpis, czekaj)
            return
        powiedziane = False
        for i, k in enumerate(dzwieki):
            czas = self._odtworz(k)
            if czas is None:
                if zastepcza_mowa:
                    mow = True  # POPRAWKA: brak pliku albo błąd odtwarzania, mowa zamiast dźwięku
                else:
                    log.warning("sygnał %s: błąd dźwięku, bez zastępczej mowy", tekst)
                continue
            if mow and not powiedziane:
                # Michał, 20.10.2026: „jesteśmy w radiu”. Mowa rusza razem
                # z pierwszym dźwiękiem, nie po jego końcu.
                self._wypowiedz(tekst, klucz)
                powiedziane = True
            if czekaj and powiedziane:
                # Treść już poszła do NVDA: dalsze dźwięki tego komunikatu nie
                # wstrzymują następnego, każdy nowy komunikat je ucina.
                if self._czekaj(czas, priorytet, kazdy=True):
                    try:
                        self.dzwieki.zatrzymaj()
                    except Exception:  # noqa: BLE001
                        log.debug("zatrzymanie dźwięku", exc_info=True)
                    return
                continue
            if czekaj and self._czekaj(czas, priorytet):
                try:
                    self.dzwieki.zatrzymaj()
                except Exception:  # noqa: BLE001
                    log.debug("zatrzymanie dźwięku", exc_info=True)
                with self._blokada:
                    if zastepcza_mowa and (klucz is None or all(w[3] != klucz for w in self._oczekujace)):
                        self._oczekujace.append([priorytet, numer, tekst, klucz, dzwieki[i:], mow, zastepcza_mowa])
                return
        if mow and not powiedziane:
            self._wypowiedz(tekst, klucz)

    def _wykonaj_grupe(self, wpis, czekaj):
        with self._blokada:
            self._aktywny = wpis
        try:
            self._wykonaj(wpis, czekaj)
        finally:
            with self._blokada:
                self._aktywny = None
                # Wynik odebrany dokładnie na końcu dźwięku nie może przepaść.
                self._oczekujace.extend(self._dolaczone)
                self._dolaczone = []

    def oproznij(self) -> None:
        """Wypowiedz wszystko teraz, w kolejności priorytetu (tryb bez wątku,
        bez czekania na koniec dźwięków)."""
        while True:
            with self._blokada:
                wpis = self._pobierz()
            if wpis is None:
                return
            self._wykonaj_grupe(wpis, czekaj=False)

    def start(self) -> "KolejkaMowy":
        self._dziala = True
        self._watek = threading.Thread(target=self._petla, name="mowa", daemon=True)
        self._watek.start()
        return self

    def _petla(self) -> None:
        while self._dziala:
            with self._blokada:
                while self._dziala and not self._oczekujace:
                    self._blokada.wait(0.2)
                wpis = self._pobierz() if self._dziala else None
            if wpis is not None:
                self._wykonaj_grupe(wpis, czekaj=True)

    def stop(self) -> None:
        self._dziala = False
        with self._blokada:
            self._blokada.notify_all()
        if self._watek:
            self._watek.join(timeout=1.0)


def utworz_wyjscie(rodzaj: str):
    if rodzaj == "nvda":
        wyjscie = MowaNVDA()
        if not wyjscie.dziala():
            raise BrakNVDA("NVDA nie jest uruchomione")
        return wyjscie
    if rodzaj == "konsola":
        return MowaKonsola()
    if rodzaj == "atrapa":
        return AtrapaMowy()
    raise ValueError(f"nieznane wyjście mowy: {rodzaj}")
