"""Punkt wejścia mostka: z symulatorem albo z prawdziwym adresem MR18.

Przykłady (z katalogu mostek):
    python -m mostek --symulator                 symulator w tym samym procesie, konsola
    python -m mostek --mr18 192.168.1.50 --mowa nvda --midi winmm
    python -m mostek --mr18 127.0.0.1 --port 10024    osobny symulator: python -m mostek.symulator

Adres MR18 podaje się jawnie. Mostek nie szuka miksera w sieci.
Przy starcie mostek odczytuje mikser i nie otwiera torów. Odczyt może
wykonać ochronne zamknięcia niebezpiecznych dróg przy niezgodnym profilu.

Konsola (zawsze dostępna, czytelna dla NVDA) przyjmuje polecenia równoważne
przyciskom X-TOUCH, opis: polecenie „pomoc”.

Klawisze F4 i F5 (decyzja Michała z 17.10.2026):
  F4  tryb informacji zwrotnej po kolei: mowa, dźwięki, dźwięki z mową
      (domyślny). Nowy tryb jest zawsze ogłaszany mową i zapisany
      w ustawieniach (ustawienia/tryb_informacji.json), więc przeżywa restart.
  F5  powtarza mową ostatni komunikat stanu, także taki, który w trybie
      dźwięków zabrzmiał tylko dźwiękiem. Nie czyta miksera i nic nie zapisuje.
Dźwięki: w Windows winsound (asynchronicznie, karta domyślna), poza Windows
tylko wpis „[dzwiek] klucz” w konsoli. Ostrzeżenia zawsze mają mowę.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from pathlib import Path

from . import emisja as emisja_mod
from . import informacja as informacja_mod
from . import mowa as mowa_mod
from . import ustawienia
from .klient import KlientMR18
from .rdzen import Rdzen
from .symulator import SerwerSymulatora
from .transport import TransportUDP

log = logging.getLogger("mostek")

POMOC = """Polecenia konsoli mostka (każde jak przycisk X-TOUCH):
  F1 .. F8                 klawisze funkcyjne (F1 mikrofon, F2 status, F3 koniec rozmowy,
                           F4 tryb: mowa, dźwięki, dźwięki z mową; F5 powtórz ostatni
                           komunikat; F6 co gra i ile zostało; F7 automat; F8 powierzchnia i odsłuch)
  cue PASEK                SELECT paska: CUE telefonu (2) albo Zooma (3), PFL muzyki (4 do 6)
  p PASEK PRZYCISK         przycisk paska; PRZYCISK 1 REC, 2 SOLO, 3 MUTE, 4 SELECT
  kaszel | pusc            przytrzymanie i puszczenie przycisku kaszlu (MUTE paska 1)
  talkback PASEK | pusc PASEK   przytrzymanie i puszczenie talkbacku (2 telefon, 3 Zoom)
  kontroler                X-TOUCH znowu podłączony: silniki według miksera, stół uzbrojony
  g PASEK +|-              obrót gałki o jeden ząbek
  s PASEK                  status paska (wciśnięcie gałki)
  suwak PASEK POZYCJA      suwak 0 do 100 procent; pasek 9 to MASTER (słuchawki)
  glosniki wlacz|wylacz    głośniki odsłuchowe
  alarm                    alarm ciszy na antenie: włącz albo wyłącz (jak REC paska 1)
  program | rozmowa | koniecpfl   odsłuch: program, rozmowa na CUE, koniec PFL
  play | nastepny | stop   program emisyjny (drugi stop: natychmiast)
  nauka                    nauka klawiszy (jak REWIND): każdy klawisz mówi nazwę i nic nie robi
  coGra | automat          jak F6 i F7
  gora | dol | znacznik    playlista: kursor i znacznik do emisji
  sym cisza | sym dzwiek   tylko z --symulator: cisza na antenie w miernikach albo grający program
  sym bezmiernikow | sym zmiernikami   tylko z --symulator: mierniki wyłączone albo włączone
  restart                  uruchom mostek od nowa w tym oknie: od nowa ustawienia, mikser,
                           X-TOUCH i NVDA; do miksera nic nie zapisuje
  koniec                   zakończ mostek"""

KLAWISZE_KONSOLI = {
    "f1": "F1_mikrofon", "f2": "F2_status", "f3": "F3_koniec_rozmowy", "f4": "F4_tryb_informacji",
    "f5": "F5_ostatni_komunikat", "f6": "F6_co_gra", "f7": "F7_automat",
    "f8": "F8_odczytaj_powierzchnie", "program": "sluchaj_programu", "rozmowa": "sluchaj_rozmowy",
    "koniecpfl": "koniec_pfl", "play": "transport_play", "stop": "transport_stop",
    "alarm": "alarm_ciszy", "nauka": "nauka_klawiszy",
    "nastepny": "transport_nastepny",
    "cogra": "F6_co_gra", "automat": "F7_automat",
    "gora": "emisja_gora", "dol": "emisja_dol", "znacznik": "emisja_znacznik",
}


def polecenie_konsoli(linia: str):
    cz = linia.strip().lower().split()
    if not cz:
        return None
    if cz[0] in KLAWISZE_KONSOLI and len(cz) == 1:
        return ("klawisz", KLAWISZE_KONSOLI[cz[0]])
    if cz[0] == "kaszel" and len(cz) == 1:
        return ("przycisk", 1, 2)
    if cz[0] == "pusc" and len(cz) == 1:
        return ("puszczenie", 1, 2)
    if cz[0] in ("talkback", "pusc") and len(cz) == 2 and cz[1] in ("2", "3"):
        return ("przycisk" if cz[0] == "talkback" else "puszczenie", int(cz[1]), 2)
    if cz[0] == "kontroler" and len(cz) == 1:
        return ("kontroler_powrot", "konsola")
    if cz[0] == "glosniki" and len(cz) == 2 and cz[1] in ("wlacz", "wylacz"):
        return ("klawisz", f"glosniki_{cz[1]}")
    if cz[0] == "cue" and len(cz) == 2:
        return ("przycisk", int(cz[1]), 3)
    if cz[0] == "p" and len(cz) == 3:
        return ("przycisk", int(cz[1]), int(cz[2]) - 1)
    if cz[0] == "g" and len(cz) == 3:
        return ("galka", int(cz[1]), 1 if cz[2] == "+" else -1)
    if cz[0] == "s" and len(cz) == 2:
        return ("galka_wcisnij", int(cz[1]))
    if cz[0] == "suwak" and len(cz) == 3:
        return ("suwak", int(cz[1]), float(cz[2]) / 100.0)
    raise ValueError("nieznane polecenie")


class SygnalZycia:
    """Sygnał dla nadzorcy, wysyłany z pętli roboczej (nie z osobnego wątku),
    więc zawieszenie pętli zatrzymuje sygnał (plan, rozdz. 13)."""

    def __init__(self, port: int | None) -> None:
        self.port = port
        self._g = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if port else None

    def wyslij(self) -> None:
        if self._g:
            try:
                self._g.sendto(b"zyje", ("127.0.0.1", self.port))
            except OSError:
                pass


def main(argv=None) -> int:
    """Michał, 23.10.2026: polecenie restart w oknie mostka. Kolejny przebieg
    w tym samym procesie: ustawienia, klient MR18, port X-TOUCH i NVDA od
    nowa, pełny odczyt miksera; sceny ani ustawień miksera nie zapisuje."""
    while True:
        rc = _przebieg(argv)
        if rc != RESTART:
            return rc
        log.warning("restart mostka poleceniem z konsoli")
        print("Mostek uruchamia się od nowa.", flush=True)


RESTART = "restart"


def _przebieg(argv=None):
    p = argparse.ArgumentParser(prog="mostek", description="Mostek MR18 i X-TOUCH (warstwa radiowa)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sprawdz", action="store_true", help="sprawdź stanowisko bez sprzętu i bez zapisu")
    p.add_argument("--json", action="store_true", help="wynik --sprawdz w formacie JSON")
    g.add_argument("--symulator", action="store_true", help="uruchom symulator MR18 w tym procesie")
    g.add_argument("--mr18", metavar="ADRES", help="adres IP albo nazwa MR18 (bez wykrywania w sieci)")
    p.add_argument("--port", type=int, default=None, help="port OSC (domyślnie z ustawień, 10024)")
    p.add_argument("--ustawienia", default=str(ustawienia.DOMYSLNE_USTAWIENIA))
    p.add_argument("--poziomy", default=str(ustawienia.DOMYSLNE_POZIOMY))
    p.add_argument("--mowa", choices=("konsola", "nvda"), default="konsola")
    p.add_argument("--dzwieki-konsola", action="store_true",
                   help="bez odtwarzania audio: dźwięki i alarm tylko jako tekst w konsoli")
    p.add_argument("--midi", choices=("brak", "winmm"), default="brak")
    p.add_argument("--emisja", type=str.lower, choices=("brak", "auto", "stationplaylist", "sara"),
                   default=None, help="program playoutu; domyślnie emisja.program z ustawień (auto)")
    p.add_argument("--nadzorca-port", type=int, default=None, help="port sygnału życia (ustawia nadzorca)")
    p.add_argument("--bez-konsoli", action="store_true", help="bez poleceń z klawiatury (praca pod nadzorcą)")
    p.add_argument("--krotka-pomoc", action="store_true", help="krótkie powitanie dla START.bat")
    p.add_argument("--dziennik", default=None, help="plik dziennika; domyślnie z ustawień")
    a = p.parse_args(argv)

    if a.sprawdz:  # WAL_OFFLINE: przed dziennikiem i każdym urządzeniem
        from .walidator import sprawdz_pliki
        return sprawdz_pliki(a.ustawienia, a.poziomy, jako_json=a.json)
    if a.json:
        p.error("--json wymaga --sprawdz")

    u = ustawienia.wczytaj(a.ustawienia, a.poziomy)
    plik_dziennika = Path(a.dziennik or (ustawienia.KATALOG / u.surowe.get("dziennik", {}).get("plik", "dziennik/mostek.log")))
    plik_dziennika.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=plik_dziennika, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from .walidator import ostrzezenia_startu
    for problem in ostrzezenia_startu(u):
        log.warning("ustawienia %s: %s", problem.sciezka, problem.komunikat)

    serwer = None
    if a.symulator:
        serwer = SerwerSymulatora(port=0).start()
        host, port = serwer.adres
        print(f"SYMULATOR MR18 na {host}:{port}. To symulator, nie mikser.", flush=True)
    else:
        host, port = a.mr18, a.port or int(u.mikser.get("port", 10024))
    m = u.mikser
    klient = KlientMR18(TransportUDP(host, port), limit_odpowiedzi_s=float(m["limit_odpowiedzi_s"]),
                        dodatkowe_proby=int(m["dodatkowe_proby"]), tolerancja=float(m["tolerancja_float"]),
                        okno=int(m.get("okno_zapytan", 16)),
                        szybka_powtorka_s=float(m.get("szybka_powtorka_s", 0.03)),
                        przerwa_ponowienia_s=float(m.get("przerwa_ponowienia_s", 0.0)),
                        cisza_utraty_s=float(m.get("cisza_utraty_s", 0.0)),
                        dopasuj_do_opoznienia=bool(m.get("dopasuj_do_opoznienia", True)),
                        maks_limit_rundy_s=float(m.get("maks_limit_rundy_s", 3.0)))
    try:
        wyjscie = mowa_mod.utworz_wyjscie(a.mowa)
    except mowa_mod.BrakNVDA as e:
        print(f"NVDA niedostępne ({e}), komunikaty w konsoli.", flush=True)
        wyjscie = mowa_mod.MowaKonsola()
    informacja = informacja_mod.InformacjaZwrotna(
        u, informacja_mod.utworz_odtwarzacz(sys.stdout, konsola=a.dzwieki_konsola))
    opcje_mowy = {}
    if a.dzwieki_konsola:
        opcje_mowy["alarm"] = lambda: print("[dzwiek] alarm awarii mowy", flush=True)
    kolejka = mowa_mod.KolejkaMowy(wyjscie, dzwieki=informacja, **opcje_mowy).start()
    program = None if a.emisja == "brak" else emisja_mod.utworz(a.emisja, u.emisja)
    rdzen = Rdzen(u, klient, kolejka, emisja=program, informacja=informacja)
    powierzchnia = None
    port_brak = ""
    if a.midi == "winmm":
        from .xtouch import BrakMIDI, MapaMC, PortWinMM, PowierzchniaXTouch  # noqa: PLC0415
        nazwa_midi = u.xtouch.get("nazwa_urzadzenia_midi", "X-TOUCH")
        try:
            port_midi = PortWinMM(nazwa_midi)
        except BrakMIDI as e:
            port_midi, port_brak = None, str(e)    # mostek ponawia otwarcie co kilka sekund
            print(f"X-TOUCH niedostępny ({e}), ponawiam otwarcie portu.", flush=True)
        powierzchnia = PowierzchniaXTouch(MapaMC(u.xtouch), port_midi, rdzen.zglos,
                                          otworz_port=lambda: PortWinMM(nazwa_midi),
                                          okres_ponowienia=float(u.xtouch.get("ponowienie_portu_s", 2.0)),
                                          okres_zycia=float(u.xtouch.get("zycie_s", 1.0)) or None,
                                          proby_zycia=int(u.xtouch.get("zycie_proby", 2)))
        rdzen.powierzchnia = powierzchnia

    rdzen.start()
    if port_brak:
        rdzen.zglos(("kontroler", port_brak))
    sygnal = SygnalZycia(a.nadzorca_port)
    koniec = threading.Event()
    restart = threading.Event()

    def konsola() -> None:
        if a.krotka_pomoc:
            print('Mostek działa. F2 na stole odczytuje stan.\n'
                  'Wpisz restart, aby uruchomić mostek od nowa, albo koniec, aby zakończyć.\n'
                  'Pełna lista poleceń: wpisz pomoc.', flush=True)
        else:
            print(POMOC, flush=True)
        while not koniec.is_set():
            try:
                linia = input("> ")
            except (EOFError, KeyboardInterrupt):
                koniec.set()
                return
            if linia.strip() in ("koniec", "q"):
                koniec.set()
                return
            if linia.strip().lower() == "restart":
                print("Restartuję mostek. Do miksera nic nie zapisuję.", flush=True)
                restart.set()
                koniec.set()
                return
            if linia.strip() == "pomoc":
                print(POMOC, flush=True)
                continue
            if linia.strip().lower().startswith("sym "):
                polecenie = linia.strip().lower().split(maxsplit=1)[1]
                if serwer is None:
                    print("Polecenia sym działają tylko z --symulator.", flush=True)
                elif polecenie in ("cisza", "dzwiek"):
                    serwer.rdzen.cisza(polecenie == "cisza")
                    print("Symulator: " + ("cisza na antenie" if polecenie == "cisza" else "program gra"), flush=True)
                elif polecenie in ("bezmiernikow", "zmiernikami"):
                    serwer.rdzen.mierniki_wylaczone = polecenie == "bezmiernikow"
                    print("Symulator: mierniki " + ("wyłączone" if polecenie == "bezmiernikow" else "włączone"),
                          flush=True)
                else:
                    print("Nieznane polecenie. Wpisz pomoc.", flush=True)
                continue
            try:
                z = polecenie_konsoli(linia)
            except ValueError:
                print("Nieznane polecenie. Wpisz pomoc.", flush=True)
                continue
            if z:
                rdzen.zglos(z)      # konsola po kolei: wpisane polecenia nie nakładają się

    if not a.bez_konsoli:
        threading.Thread(target=konsola, name="konsola", daemon=True).start()
    okres = float(u.nadzorca.get("okres_sygnalu_s", 0.5))
    try:
        while not koniec.is_set():
            rdzen.tick()
            sygnal.wyslij()
            koniec.wait(min(0.1, okres))
    except KeyboardInterrupt:
        pass
    finally:
        rdzen.zamknij_emisje()
        kolejka.stop()
        klient.zamknij()
        if powierzchnia is not None:
            powierzchnia.port.przy_zamknieciu = None    # zamknięcie przy końcu to nie utrata
            powierzchnia.port.zamknij()
        if serwer:
            serwer.stop()
    return RESTART if restart.is_set() else 0


if __name__ == "__main__":
    sys.exit(main())
