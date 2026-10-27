"""Nadzorca: osobny proces pilnujący mostka (plan, rozdz. 13).

Uruchamia mostek jako proces potomny i nasłuchuje jego sygnału życia na
lokalnym porcie UDP (127.0.0.1). Mostek wysyła sygnał z pętli roboczej,
więc zawieszenie pętli zatrzymuje sygnał. Po przekroczeniu limitu ciszy
albo zakończeniu procesu nadzorca:
  1. mówi przez NVDA „Sterowanie nie odpowiada, mikrofon może być na antenie”,
  2. kończy zawieszony proces,
  3. uruchamia mostek ponownie; nowy mostek zaczyna od ODCZYTU miksera.
Nadzorca nie łączy się z MR18 i niczego w nim nie zmienia. Limit restartów
w oknie czasu chroni przed pętlą; po jego przekroczeniu nadzorca mówi
komunikat i przestaje restartować.

Przykład:  python -m mostek.nadzorca -- --mr18 192.168.1.50 --mowa nvda --midi winmm --bez-konsoli
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from collections import deque

from . import mowa as mowa_mod
from . import ustawienia


class Nadzorca:
    def __init__(self, polecenie: list[str], mowa, port: int = 0, limit_ciszy_s: float = 2.0,
                 maks_restartow: int = 5, okno_restartow_s: float = 300.0, teksty=None,
                 uruchom=subprocess.Popen, zegar=time.monotonic) -> None:
        self.polecenie = polecenie
        self.mowa = mowa
        self.limit_ciszy = limit_ciszy_s
        self.maks_restartow = maks_restartow
        self.okno = okno_restartow_s
        self.teksty = teksty or {}
        self._uruchom = uruchom
        self.zegar = zegar
        self._gniazdo = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._gniazdo.bind(("127.0.0.1", port))
        self._gniazdo.settimeout(0.1)
        self.port = self._gniazdo.getsockname()[1]
        self.proces = None
        self.ostatni_sygnal = 0.0
        self.restarty: deque[float] = deque()
        self.zatrzymany = False

    def _tekst(self, klucz: str, domyslny: str) -> str:
        return self.teksty.get(klucz, domyslny)

    def uruchom_mostek(self) -> None:
        self.proces = self._uruchom(self.polecenie + ["--nadzorca-port", str(self.port)])
        self.ostatni_sygnal = self.zegar()

    def _odbierz(self) -> None:
        try:
            while True:
                dane, nadawca = self._gniazdo.recvfrom(64)
                if nadawca[0] == "127.0.0.1" and dane == b"zyje":
                    self.ostatni_sygnal = self.zegar()
        except (socket.timeout, BlockingIOError):
            pass

    def krok(self) -> str:
        """Jeden cykl nadzoru. Zwraca 'ok', 'restart' albo 'zatrzymany'."""
        if self.zatrzymany:
            return "zatrzymany"
        self._odbierz()
        teraz = self.zegar()
        zakonczony = self.proces is not None and self.proces.poll() is not None
        if not zakonczony and teraz - self.ostatni_sygnal <= self.limit_ciszy:
            return "ok"
        self.mowa.powiedz(self._tekst("sterowanie_nie_odpowiada",
                                      "Sterowanie nie odpowiada, mikrofon może być na antenie"),
                          mowa_mod.Priorytet.BEZPIECZENSTWO)
        if self.proces is not None and self.proces.poll() is None:
            self.proces.kill()
            try:
                self.proces.wait(timeout=2)
            except Exception:  # noqa: BLE001
                pass
        while self.restarty and teraz - self.restarty[0] > self.okno:
            self.restarty.popleft()
        if len(self.restarty) >= self.maks_restartow:
            self.zatrzymany = True
            self.mowa.powiedz(self._tekst("nadzorca_stop", "Za dużo restartów sterowania, nadzorca przestaje"),
                              mowa_mod.Priorytet.BEZPIECZENSTWO)
            return "zatrzymany"
        self.restarty.append(teraz)
        self.mowa.powiedz(self._tekst("nadzorca_restart", "Uruchamiam sterowanie ponownie, odczyt od miksera"),
                          mowa_mod.Priorytet.BEZPIECZENSTWO)
        self.uruchom_mostek()
        return "restart"

    def zamknij(self) -> None:
        if self.proces is not None and self.proces.poll() is None:
            self.proces.terminate()
        self._gniazdo.close()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        i = argv.index("--")
        wlasne, mostka = argv[:i], argv[i + 1:]
    else:
        wlasne, mostka = argv, []
    p = argparse.ArgumentParser(prog="nadzorca", description="Nadzorca procesu mostka")
    p.add_argument("--mowa", choices=("konsola", "nvda"), default="konsola")
    a = p.parse_args(wlasne)
    u = ustawienia.wczytaj()
    try:
        wyjscie = mowa_mod.utworz_wyjscie(a.mowa)
    except mowa_mod.BrakNVDA:
        wyjscie = mowa_mod.MowaKonsola()
    kolejka = mowa_mod.KolejkaMowy(wyjscie).start()
    n = u.nadzorca
    nadzorca = Nadzorca([sys.executable, "-m", "mostek"] + mostka, kolejka,
                        port=int(n.get("port", 0)), limit_ciszy_s=float(n.get("limit_ciszy_s", 2.0)),
                        maks_restartow=int(n.get("maks_restartow", 5)),
                        okno_restartow_s=float(n.get("okno_restartow_s", 300)), teksty=u.komunikaty)
    nadzorca.uruchom_mostek()
    try:
        while nadzorca.krok() != "zatrzymany":
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        nadzorca.zamknij()
        kolejka.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
