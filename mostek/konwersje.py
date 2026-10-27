"""Przeliczenia wartości OSC (0.0-1.0) na decybele i z powrotem.

Każda funkcja ma podane źródło. Wszystkie mają status „do potwierdzenia na
MR18”: żadna nie została zmierzona na egzemplarzu Michała.
"""

from __future__ import annotations

import math

MINUS_NIESKONCZONOSC = float("-inf")


# --- Suwak i poziom wysyłki: zakres „-oo - +10” ---------------------------
# Źródło zakresu: lista parametrów X AIR z forum Gig Performer
# (xair-osc-paramlist-gigperformer.txt, wiersze 157 i 160:
# /ch/01/mix/01/level oraz /ch/01/mix/fader, „-oo - +10”).
# Źródło krzywej (czteroodcinkowa, jak w X32): biblioteka xair-api-python,
# plik xair_api/util.py, funkcje db_to/db_from, gałąź dev, commit a2396590
# (autor deklaruje testy na MR18). Krzywa NIE pochodzi od producenta.
# Status: do potwierdzenia na MR18 (etap 1, odczyt wartości w M-AIR Edit).

def poziom_db_na_float(db: float) -> float:
    if db == MINUS_NIESKONCZONOSC or db < -90:
        return 0.0
    if db >= 10:
        return 1.0
    if db >= -10:
        return (db + 30) / 40
    if db >= -30:
        return (db + 50) / 80
    if db >= -60:
        return (db + 70) / 160
    return (db + 90) / 480


def poziom_float_na_db(wartosc: float) -> float:
    if wartosc <= 0.0:
        return MINUS_NIESKONCZONOSC
    if wartosc >= 1.0:
        return 10.0
    if wartosc >= 0.5:
        return wartosc * 40 - 30
    if wartosc >= 0.25:
        return wartosc * 80 - 50
    if wartosc >= 0.0625:
        return wartosc * 160 - 70
    return wartosc * 480 - 90


ZERO_DB = poziom_db_na_float(0.0)  # 0.75: górne położenie suwaka mostka


# --- Wzmocnienie przedwzmacniacza /headamp/NN/gain -------------------------
# AOSC Air Access 18 (azaosc.xml, wiersz 14): typ „Gain”, vtext
# „number;dB;-12.0;60.0”, dla wejść 1-16; dla wejścia 17/18 osobny typ
# „AuxGain” -12..+20 (wiersz 15). Lista z forum (wiersz 206) podaje dla
# /headamp/01/gain zakres „-12 - +20”. Źródła się różnią. Mostek przyjmuje
# -12..+60 z AOSC: przy błędnym założeniu krok 1 dB staje się MNIEJSZY, nie
# większy, więc rozmówca nie zostanie przesterowany. Do potwierdzenia na MR18.
GAIN_MIN_DB = -12.0
GAIN_MAX_DB = 60.0


def gain_db_na_float(db: float) -> float:
    db = min(max(db, GAIN_MIN_DB), GAIN_MAX_DB)
    return (db - GAIN_MIN_DB) / (GAIN_MAX_DB - GAIN_MIN_DB)


def gain_float_na_db(wartosc: float) -> float:
    return GAIN_MIN_DB + (GAIN_MAX_DB - GAIN_MIN_DB) * min(max(wartosc, 0.0), 1.0)


# --- USB Trim /ch/NN/preamp/rtntrim ----------------------------------------
# Lista z forum, wiersz 168: „-18 - +18”. AOSC, typ „Trim” (wiersz 18):
# „number;dB;-18.0;18.0”. Źródła zgodne. Do potwierdzenia na MR18.
TRIM_MIN_DB = -18.0
TRIM_MAX_DB = 18.0


def trim_db_na_float(db: float) -> float:
    db = min(max(db, TRIM_MIN_DB), TRIM_MAX_DB)
    return (db - TRIM_MIN_DB) / (TRIM_MAX_DB - TRIM_MIN_DB)


def trim_float_na_db(wartosc: float) -> float:
    return TRIM_MIN_DB + (TRIM_MAX_DB - TRIM_MIN_DB) * min(max(wartosc, 0.0), 1.0)


# --- Przyciszenie przy PFL /config/solo/dimatt -----------------------------
# Lista z forum, wiersz 183: „-40 - 0”. AOSC, typ „DimLevel” (wiersz 25):
# „-40.0;0.0”. Źródła zgodne. Do potwierdzenia na MR18.

def dimatt_db_na_float(db: float) -> float:
    db = min(max(db, -40.0), 0.0)
    return (db + 40.0) / 40.0


def dimatt_float_na_db(wartosc: float) -> float:
    return -40.0 + 40.0 * min(max(wartosc, 0.0), 1.0)


def opis_db(db: float) -> str:
    """Słowny opis poziomu dla NVDA, bez znaku minus jako symbolu."""
    if db == MINUS_NIESKONCZONOSC or math.isinf(db):
        return "minus nieskończoność"
    zaokr = round(db)
    if zaokr == 0:
        return "zero decybeli"
    if zaokr > 0:
        return f"plus {zaokr} decybeli"
    return f"minus {-zaokr} decybeli"
