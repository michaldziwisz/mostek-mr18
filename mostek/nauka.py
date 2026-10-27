"""Tryb nauki klawiszy: naciśnięty element stołu mówi swoją nazwę i nic nie robi.

Michał (24.10.2026) nie wie, gdzie na X-TOUCH są Save, Undo, Marker i reszta.
W trybie nauki każdy przycisk, gałka i kółko jog tylko się przedstawia
(etykieta z panelu i obecna funkcja w mostku), a dziennik zapisuje numer MIDI.
Suwaki działają normalnie, więc ściągnięcie suwaka nadal zamyka tor.

Etykiety według Mackie Control w Ardourze (libs/surfaces/mackie/device_info.cc,
commit a9ea4a98a336729a69453edbcc29905a79ac75e1) i opisu panelu w skróconej
instrukcji X-TOUCH (MC USER MODE, BUTTON ASSIGNMENT OPTIONS).
"""

from __future__ import annotations

ETYKIETY_MC = {
    0x28: "Track", 0x29: "Send", 0x2A: "Pan", 0x2B: "Plug-in", 0x2C: "EQ", 0x2D: "Instrument",
    0x2E: "Bank w lewo", 0x2F: "Bank w prawo", 0x30: "Channel w lewo", 0x31: "Channel w prawo",
    0x32: "Flip", 0x33: "Global View", 0x34: "Name Value", 0x35: "SMPTE Beats",
    0x36: "F1", 0x37: "F2", 0x38: "F3", 0x39: "F4", 0x3A: "F5", 0x3B: "F6", 0x3C: "F7", 0x3D: "F8",
    0x3E: "MIDI Tracks", 0x3F: "Inputs", 0x40: "Audio Tracks", 0x41: "Audio Inst", 0x42: "Aux",
    0x43: "Busses", 0x44: "Outputs", 0x45: "User",
    0x46: "Shift", 0x47: "Option", 0x48: "Control", 0x49: "Alt",
    0x4A: "Read Off", 0x4B: "Write", 0x4C: "Trim", 0x4D: "Touch", 0x4E: "Latch", 0x4F: "Group",
    0x50: "Save", 0x51: "Undo", 0x52: "Cancel", 0x53: "Enter",
    0x54: "Marker", 0x55: "Nudge", 0x56: "Cycle", 0x57: "Drop", 0x58: "Replace", 0x59: "Click",
    0x5A: "Solo",
    0x5B: "Przewijanie do tyłu", 0x5C: "Przewijanie do przodu", 0x5D: "Stop", 0x5E: "Play",
    0x5F: "Record",
    0x60: "Strzałka w górę", 0x61: "Strzałka w dół", 0x62: "Strzałka w lewo",
    0x63: "Strzałka w prawo", 0x64: "Zoom", 0x65: "Scrub",
    0x66: "Przełącznik nożny 1", 0x67: "Przełącznik nożny 2",
}

FUNKCJE = {
    "F1_mikrofon": "mikrofon", "F2_status": "status", "F3_koniec_rozmowy": "koniec rozmowy",
    "F4_tryb_informacji": "tryb informacji", "F5_ostatni_komunikat": "powtórzenie komunikatu",
    "F6_co_gra": "co gra", "F7_automat": "automat", "F8_odczytaj_powierzchnie": "opis powierzchni",
    "channel_lewo_automat": "automat",
    "sluchaj_programu": "odsłuch programu", "sluchaj_rozmowy": "odsłuch rozmowy",
    "koniec_pfl": "koniec odsłuchu", "glosniki_wylacz": "wyłączenie głośników",
    "glosniki_wlacz": "włączenie głośników", "transport_play": "Play w programie",
    "transport_stop": "Stop w programie", "transport_nastepny": "następny utwór",
    "emisja_gora": "w górę po playliście", "emisja_dol": "w dół po playliście",
    "emisja_znacznik": "znacznik do emisji", "nauka_klawiszy": "koniec nauki klawiszy",
    "alarm_ciszy": "alarm ciszy", "scrub_wolny": "punkty miksu",
}

PRZYCISKI_PASKA = ("REC", "Solo", "Mute", "Select")
FUNKCJE_PASKA = {
    "antena_mikrofonu": "mikrofon", "alarm_ciszy": "alarm ciszy", "kaszel": "kaszel",
    "cue": "CUE", "pfl": "odsłuch kontrolny", "talkback": "talkback",
}

# Zdarzenia, które w trybie nauki tylko się przedstawiają. Suwak, dotyk,
# puszczenie (koniec kaszlu) i utrata kontrolera działają jak zawsze.
ZDARZENIA_NAUKI = ("przycisk", "galka_wcisnij", "klawisz", "galka", "jog")
KLAWISZ_NAUKI = "nauka_klawiszy"
LIMIT_BEZCZYNNOSCI_S = 60.0
TEKST_START = ("Nauka klawiszy. Każdy klawisz mówi swoją nazwę i nic nie robi. "
               "Suwaki działają. Koniec: ten sam klawisz")
TEKST_KONIEC = "Koniec nauki klawiszy"
TEKST_KONIEC_CZAS = "Koniec nauki klawiszy, minuta bez naciśnięcia"


def _nuta_klawisza(u, nazwa: str):
    if nazwa.startswith("nuta_"):
        return int(nazwa[5:])
    for k, v in u.xtouch["klawisze"].items():
        if v == nazwa:
            return int(k)
    return None


def opisz(u, z: tuple) -> tuple[str, str]:
    """(tekst do powiedzenia, opis do dziennika z numerem MIDI)."""
    rodzaj = z[0]
    if rodzaj == "klawisz":
        nazwa = str(z[1])
        nuta = _nuta_klawisza(u, nazwa)
        etykieta = ETYKIETY_MC.get(nuta, f"Klawisz numer {nuta}" if nuta is not None else nazwa)
        funkcja = FUNKCJE.get(nazwa)
        klucz = {"bank_lewo_odtwarzacz": "nauka_bank_lewo", "bank_prawo_wolny": "nauka_bank_prawo",
                 "emisja_pozostalo": "nauka_channel_prawo", "emisja_znacznik": "nauka_zoom"}.get(nazwa)
        if klucz:
            funkcja = u.tekst(klucz)
        tekst = f"{etykieta}, {funkcja}" if funkcja else f"{etykieta}, wolny"
        return tekst, f"nuta {nuta} (0x{nuta:02X}) {nazwa}" if nuta is not None else nazwa
    if rodzaj == "przycisk":
        pasek, indeks = int(z[1]), int(z[2])
        opis = u.paski.get(pasek) or {}
        klucz = ("rec", "solo", "mute", "select")[indeks]
        znaczenie = opis.get(klucz)
        funkcja = FUNKCJE_PASKA.get(znaczenie) if znaczenie else None
        zr = opis.get("zrodlo")
        tekst = f"Pasek {pasek}, {PRZYCISKI_PASKA[indeks]}"
        if funkcja in ("CUE", "odsłuch kontrolny") and zr in u.zrodla:
            tekst += f", {funkcja} {u.zrodla[zr].dopelniacz}"
        elif znaczenie == "talkback" and zr in u.zrodla:
            tekst += ", " + u.tekst("nauka_talkback", do=u.odbiorcy[u.zrodla[zr].odbiorca].do)
        elif funkcja:
            tekst += f", {funkcja}"
        baza = int(u.xtouch["pasek_nuty"][klucz])
        nuta = baza + pasek - 1
        return tekst, f"nuta {nuta} (0x{nuta:02X}) pasek {pasek} {klucz}"
    if rodzaj == "galka_wcisnij":
        pasek = int(z[1])
        nuta = int(u.xtouch["pasek_nuty"]["galka_wcisnij"]) + pasek - 1
        return f"Wciśnięcie gałki {pasek}", f"nuta {nuta} (0x{nuta:02X}) gałka {pasek}"
    if rodzaj == "galka":
        kier = "w prawo" if int(z[2]) > 0 else "w lewo"
        return f"Gałka {int(z[1])}, {kier}", f"CC gałka {int(z[1])} {kier}"
    if rodzaj == "jog":
        kier = "w prawo" if int(z[1]) > 0 else "w lewo"
        return f"Kółko, {kier}", f"jog {kier}"
    return str(rodzaj), str(z)
