"""Podsłuch MIDI na dzień dostawy: zapis, co X-TOUCH faktycznie wysyła.

Uruchomienie w Windows (X-TOUCH w trybie MC, po USB):
    python narzedzia\\podsluch_midi.py --lista
    python narzedzia\\podsluch_midi.py --urzadzenie X-TOUCH --plik podsluch\\xtouch.jsonl

Narzędzie niczego nie wysyła do X-TOUCH ani do MR18. Każdy komunikat trafia
do pliku JSON Lines (czas, bajty szesnastkowo, opis według mapy Ardoura
z ustawień) i jest wypisywany w konsoli jednym wierszem, czytelnym dla NVDA.
Procedura: naciskać po kolei każdy przycisk, każdą gałkę w obie strony,
dotykać i przesuwać każdy suwak; przy każdym elemencie wpisać jego nazwę
(polecenie „opis TEKST” w konsoli), żeby zapis dało się porównać z mapą.
Wynik porównuje się z plikiem ustawienia/stanowisko.json, sekcja xtouch.

Bez Windows (np. w WSL) działa tryb --odtworz PLIK, który dekoduje wcześniej
zapisany plik, oraz --test, który dekoduje kilka przykładowych komunikatów.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

KATALOG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KATALOG))

from mostek import ustawienia  # noqa: E402
from mostek.xtouch import BrakMIDI, MapaMC, PortWinMM, lista_urzadzen_winmm  # noqa: E402


def opisz(mapa: MapaMC, bajty: bytes) -> str:
    z = mapa.zdarzenie(bajty)
    if z is None:
        if bajty and (bajty[0] & 0xF0) in (0x80, 0x90):
            return "zwolnienie"
        return "nieznany komunikat"
    if isinstance(z, list):
        return f"gałka paska {z[0][1]}, {'w prawo' if z[0][2] > 0 else 'w lewo'}, ząbki {len(z)}"
    rodzaj = z[0]
    if rodzaj == "przycisk":
        return f"pasek {z[1]}, przycisk {('REC', 'SOLO', 'MUTE', 'SELECT')[z[2]]}"
    if rodzaj == "galka_wcisnij":
        return f"pasek {z[1]}, gałka wciśnięta"
    if rodzaj == "dotyk":
        return f"suwak {z[1]}, {'dotknięty' if z[2] else 'puszczony'}"
    if rodzaj == "suwak":
        return f"suwak {z[1]}, pozycja {z[2]:.3f}"
    return f"klawisz {z[1]}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Podsłuch MIDI X-TOUCH (tylko odczyt)")
    p.add_argument("--lista", action="store_true", help="wypisz wejścia MIDI Windows")
    p.add_argument("--urzadzenie", default="X-TOUCH")
    p.add_argument("--plik", default=str(ustawienia.KATALOG / "podsluch" / "xtouch.jsonl"))
    p.add_argument("--odtworz", help="zdekoduj wcześniej zapisany plik JSON Lines")
    p.add_argument("--test", action="store_true", help="zdekoduj przykładowe komunikaty i zakończ")
    a = p.parse_args(argv)
    mapa = MapaMC(ustawienia.wczytaj().xtouch)

    if a.test:
        for przyklad in ((0x90, 0x00, 0x7F), (0x90, 0x00, 0x00), (0x90, 0x36, 0x7F), (0xB0, 0x11, 0x41),
                         (0xE0, 0x7F, 0x7F), (0x90, 0x68, 0x7F)):
            print(" ".join(f"{b:02X}" for b in przyklad), "=", opisz(mapa, bytes(przyklad)))
        return 0
    if a.odtworz:
        for linia in Path(a.odtworz).read_text(encoding="utf-8").splitlines():
            wpis = json.loads(linia)
            if "bajty" in wpis:
                print(wpis.get("czas", ""), wpis["bajty"], "=", opisz(mapa, bytes.fromhex(wpis["bajty"])),
                      f"[{wpis.get('opis_uzytkownika', '')}]")
        return 0
    if a.lista:
        nazwy = lista_urzadzen_winmm()
        if not nazwy:
            print("Brak wejść MIDI albo system inny niż Windows.")
        for i, n in enumerate(nazwy):
            print(f"{i}: {n}")
        return 0

    plik = Path(a.plik)
    plik.parent.mkdir(parents=True, exist_ok=True)
    opis_uzytkownika = {"tekst": ""}
    blokada = threading.Lock()

    def zapisz(bajty: bytes) -> None:
        wpis = {"czas": round(time.time(), 4), "bajty": bajty.hex(" ").upper(),
                "opis_mapy": opisz(mapa, bajty), "opis_uzytkownika": opis_uzytkownika["tekst"]}
        with blokada, plik.open("a", encoding="utf-8") as f:
            f.write(json.dumps(wpis, ensure_ascii=False) + "\n")
        print(f"{wpis['bajty']} = {wpis['opis_mapy']}", flush=True)

    try:
        port = PortWinMM(a.urzadzenie)
    except BrakMIDI as e:
        print(f"Nie można otworzyć MIDI: {e}")
        return 2
    port.przy_komunikacie = zapisz
    print(f"Podsłuch {a.urzadzenie}, zapis do {plik}. Wpisz „opis TEKST” przed elementem, „koniec” kończy.")
    try:
        while True:
            linia = input("> ").strip()
            if linia == "koniec":
                break
            if linia.startswith("opis "):
                opis_uzytkownika["tekst"] = linia[5:]
                with blokada, plik.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"czas": round(time.time(), 4), "opis_uzytkownika": linia[5:]},
                                       ensure_ascii=False) + "\n")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        port.zamknij()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
