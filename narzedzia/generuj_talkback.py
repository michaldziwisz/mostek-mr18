"""Powtarzalne sygnały talkbacku. Tylko biblioteka standardowa.

    python3 narzedzia/generuj_talkback.py
    python3 narzedzia/generuj_talkback.py --zapisz

Bez --zapisz porównuje pliki z generatorem, bez zmiany danych.
Zapisuje tylko talkback_start.wav i talkback_koniec.wav, nie cały zestaw.
Format zgodny z istniejącymi WAV: PCM 48 kHz, mono, 16 bitów. Szczyt
7616 jak w mikrofon_na_antenie.wav (pomiar zestawu z 25.10.2026).
Dwa czyste tony 900/1800 Hz, oktawa zamiast kwinty starszych rodzin,
po 70 ms, przerwa 20 ms, cisza końcowa 10 ms. Miękka obwiednia.
"""

import argparse
import io
import math
from pathlib import Path
import struct
import wave

FS = 48000
SZCZYT = 7616


def ton(hz):
    n, brzeg = round(0.07 * FS), round(0.004 * FS)
    return [min(1.0, i / brzeg, (n - 1 - i) / brzeg)
            * math.exp(-i / (0.025 * FS)) * math.sin(2 * math.pi * hz * i / FS)
            for i in range(n)]


def pliki():
    wynik = {}
    for nazwa, hz in (("talkback_start", (900, 1800)), ("talkback_koniec", (1800, 900))):
        probki = ton(hz[0]) + [0.0] * round(0.02 * FS) + ton(hz[1]) + [0.0] * round(0.01 * FS)
        skala = SZCZYT / max(map(abs, probki))
        dane = b"".join(struct.pack("<h", round(v * skala)) for v in probki)
        bufor = io.BytesIO()
        with wave.open(bufor, "wb") as w:
            w.setparams((1, 2, FS, 0, "NONE", "not compressed"))
            w.writeframes(dane)
        wynik[nazwa + ".wav"] = bufor.getvalue()
    return wynik


def generuj(katalog):
    katalog.mkdir(parents=True, exist_ok=True)
    for nazwa, dane in pliki().items():
        (katalog / nazwa).write_bytes(dane)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zapisz", action="store_true")
    p.add_argument("--katalog", type=Path, default=Path(__file__).resolve().parents[1] / "dzwieki")
    a = p.parse_args()
    if a.zapisz:
        generuj(a.katalog)
    for nazwa, dane in pliki().items():
        plik = a.katalog / nazwa
        if not plik.is_file() or plik.read_bytes() != dane:
            p.exit(1, f"Niezgodny albo brakujący plik {plik}\n")
        print(f"OK {plik}: PCM 48000 Hz, mono, 16 bitów, 0,17 s, szczyt {SZCZYT}")


if __name__ == "__main__":
    main()
