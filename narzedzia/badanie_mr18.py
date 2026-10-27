"""Badanie MR18 w dniu dostawy: tylko odczyt, bez żadnego zapisu.

Pyta mikser o identyfikację (/xinfo, /status) i o każdą ścieżkę OSC, której
używa mostek (pełna lista odczytu profilu z mostek/logika.py). Zapisuje do
pliku JSON, co mikser odpowiedział: czy ścieżka istnieje, jaki ma typ i jaką
wartość. Porównuje typ z rejestrem w mostek/sciezki.py. Wynik zastępuje
punkty 1 i 2 listy „Czego nie sprawdzono” w README, ale tylko w części
„czy ścieżka istnieje i jaki ma typ”. Zakresów i znaczenia wartości nie
sprawdza, to dalej wymaga porównania z M-AIR Edit.

Narzędzie wysyła wyłącznie zapytania bez argumentów. W protokole X AIR to
odczyt; zapis wymaga argumentu, więc to narzędzie niczego w mikserze nie
zmienia. Nie wysyła też /xremote.

Plan v22: lista obejmuje Bus 5 (klucz przyciszania: mute, master, Main LR,
link 5/6, wysyłki mikrofonu i Zooma z punktem pobrania), Bus 6 (głośniki
mono), przyciszacz kanału 10 (/ch/10/dyn/keysrc, /ch/10/dyn/on) i inserty
mikrofonu i słuchacza (/ch/NN/insert/sel, /insert/on).

Opcja --mierniki dodatkowo wysyła subskrypcję /meters ,s "/meters/5"
(PROTO 1.5). To jedyny pakiet z argumentem: argument to identyfikator
subskrypcji, nie wartość parametru, więc niczego w mikserze nie ustawia
(tak samo robi AOSC). Raport zawiera surowy blok w szesnastkowym zapisie,
liczbę wartości w nagłówku przy obu kolejnościach bajtów i Main LR
(wartości 6 i 7) przy obu kolejnościach: na tej podstawie ustawia się
mierniki.kolejnosc_bajtow i indeksy_main_lr w pliku ustawień. Mostek nadal
nie wie, czy to dBFS: trzeba porównać z miernikiem M-AIR Edit przy tonie
o znanym poziomie.

    python narzedzia\\badanie_mr18.py --mr18 192.168.1.50 --plik badanie\\mr18.json
    python narzedzia\\badanie_mr18.py --mr18 192.168.1.50 --mierniki --plik badanie\\mr18.json
    python narzedzia\\badanie_mr18.py --symulator --mierniki   (próba bez sprzętu)
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

from mostek import osc, sciezki, ustawienia  # noqa: E402
from mostek.logika import wszystkie_adresy_odczytu  # noqa: E402
from mostek.mierniki import dekoduj_blok  # noqa: E402
from mostek.transport import TransportUDP  # noqa: E402

IDENTYFIKACJA = ("/xinfo", "/status")


class Zbieracz:
    """Odbiera odpowiedzi i zapamiętuje pierwszą dla każdego adresu."""

    def __init__(self) -> None:
        self.odpowiedzi: dict[str, osc.Komunikat] = {}
        self.nieznane: list[str] = []
        self.niepoprawne = 0
        self._blokada = threading.Lock()

    def __call__(self, dane: bytes, _nadawca) -> None:
        try:
            komunikaty = osc.dekoduj(dane)
        except osc.BladOSC:
            with self._blokada:
                self.niepoprawne += 1
            return
        with self._blokada:
            for k in komunikaty:
                self.odpowiedzi.setdefault(k.adres, k)


def oczekiwany_typ(adres: str) -> str | None:
    try:
        return sciezki.typ_sciezki(adres)
    except KeyError:
        return None


def zbadaj(transport, adresy: list[str], limit_s: float = 0.3, proby: int = 3,
           porcja: int = 16, przerwa_s: float = 0.01) -> dict:
    zb = Zbieracz()
    kanal = transport.otworz_kanal(zb)
    wyslane = 0
    try:
        wszystkie = list(IDENTYFIKACJA) + [a for a in dict.fromkeys(adresy) if a not in IDENTYFIKACJA]
        brak = list(wszystkie)
        for _ in range(proby):
            for i in range(0, len(brak), porcja):
                for a in brak[i:i + porcja]:
                    kanal.wyslij(osc.koduj(a))      # zapytanie bez argumentu = odczyt
                    wyslane += 1
                    time.sleep(przerwa_s)
                time.sleep(limit_s)
            brak = [a for a in brak if a not in zb.odpowiedzi]
            if not brak:
                break
    finally:
        kanal.zamknij()

    ident = {a: list(zb.odpowiedzi[a].argumenty) for a in IDENTYFIKACJA if a in zb.odpowiedzi}
    sciezki_wynik = []
    for a in wszystkie[len(IDENTYFIKACJA):]:
        k = zb.odpowiedzi.get(a)
        ocz = oczekiwany_typ(a)
        if k is None:
            sciezki_wynik.append({"adres": a, "odpowiedz": False, "typ_oczekiwany": ocz})
            continue
        typ = k.typy
        sciezki_wynik.append({
            "adres": a, "odpowiedz": True, "typ": typ, "typ_oczekiwany": ocz,
            "typ_zgodny": (ocz is None) or (typ == ocz),
            "wartosc": list(k.argumenty) if len(k.argumenty) != 1 else k.argumenty[0],
        })
    spodziewane = set(wszystkie)
    obce = sorted(a for a in zb.odpowiedzi if a not in spodziewane)
    return {
        "czas": time.strftime("%Y-%m-%d %H:%M:%S"),
        "identyfikacja": ident,
        "wyslane_zapytania": wyslane,
        "liczba_sciezek": len(sciezki_wynik),
        "bez_odpowiedzi": [s["adres"] for s in sciezki_wynik if not s["odpowiedz"]],
        "typ_niezgodny": [s["adres"] for s in sciezki_wynik if s.get("odpowiedz") and not s["typ_zgodny"]],
        "odpowiedzi_spoza_listy": obce,
        "pakiety_niepoprawne": zb.niepoprawne,
        "sciezki": sciezki_wynik,
    }


def zbadaj_mierniki(transport, identyfikator: str = "/meters/5", limit_s: float = 1.0) -> dict:
    """Subskrypcja mierników i zapis pierwszego bloku (PROTO 1.5). Bez /xremote."""
    bloki: list[osc.Komunikat] = []
    zd = threading.Event()

    def odb(dane, _nadawca):
        try:
            for k in osc.dekoduj(dane):
                if k.adres == identyfikator and k.typy.startswith("b"):
                    bloki.append(k)
                    zd.set()
        except osc.BladOSC:
            pass

    kanal = transport.otworz_kanal(odb)
    try:
        kanal.wyslij(osc.koduj(sciezki.METERS, identyfikator, typy="s"))
        zd.wait(limit_s)
    finally:
        kanal.zamknij()
    if not bloki:
        return {"identyfikator": identyfikator, "odpowiedz": False}
    blob = bytes(bloki[0].wartosc)
    wynik = {"identyfikator": identyfikator, "odpowiedz": True, "dlugosc_bajtow": len(blob),
             "surowe_hex": blob.hex(), "kolejnosci": {}}
    for kol in ("little", "big"):
        try:
            w = dekoduj_blok(blob, kol)
            wynik["kolejnosci"][kol] = {"liczba_wartosci": len(w),
                                        "main_lr_db": [w[6] / 256.0, w[7] / 256.0] if len(w) > 7 else None}
        except ValueError as e:
            wynik["kolejnosci"][kol] = {"blad": str(e)}
    return wynik


def streszczenie(r: dict) -> list[str]:
    w = []
    ident = r["identyfikacja"].get("/xinfo")
    w.append("Mikser: " + (" ".join(str(x) for x in ident) if ident else "brak odpowiedzi na /xinfo"))
    n = r["liczba_sciezek"]
    w.append(f"Ścieżek: {n}. Odpowiedziało {n - len(r['bez_odpowiedzi'])}, "
             f"bez odpowiedzi {len(r['bez_odpowiedzi'])}, typ niezgodny {len(r['typ_niezgodny'])}.")
    for a in r["bez_odpowiedzi"][:15]:
        w.append(f"  bez odpowiedzi: {a}")
    for a in r["typ_niezgodny"][:15]:
        s = next(x for x in r["sciezki"] if x["adres"] == a)
        w.append(f"  typ {s['typ']!r} zamiast {s['typ_oczekiwany']!r}: {a}")
    if r["odpowiedzi_spoza_listy"]:
        w.append(f"Odpowiedzi spoza listy: {len(r['odpowiedzi_spoza_listy'])}, "
                 f"np. {r['odpowiedzi_spoza_listy'][0]}")
    m = r.get("mierniki")
    if m is not None:
        if not m["odpowiedz"]:
            w.append(f"Mierniki {m['identyfikator']}: brak odpowiedzi")
        else:
            w.append(f"Mierniki {m['identyfikator']}: blok {m['dlugosc_bajtow']} bajtów")
            for kol, d in m["kolejnosci"].items():
                w.append(f"  {kol}: " + (d["blad"] if "blad" in d else
                                          f"{d['liczba_wartosci']} wartości, Main LR {d['main_lr_db']} dB"))
    return w


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Badanie MR18: tylko odczyt ścieżek mostka")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--mr18", metavar="ADRES")
    g.add_argument("--symulator", action="store_true", help="próba na symulatorze w tym procesie")
    p.add_argument("--port", type=int, default=10024)
    p.add_argument("--plik", default=None, help="raport JSON (domyślnie tylko streszczenie w konsoli)")
    p.add_argument("--mierniki", action="store_true", help="także subskrypcja /meters/5 i zapis surowego bloku")
    a = p.parse_args(argv)
    u = ustawienia.wczytaj()
    serwer = None
    if a.symulator:
        from mostek.symulator import SerwerSymulatora  # noqa: PLC0415
        serwer = SerwerSymulatora(port=0).start()
        host, port = serwer.adres
        print(f"SYMULATOR na {host}:{port}. To symulator, nie mikser.")
    else:
        host, port = a.mr18, a.port
    try:
        transport = TransportUDP(host, port)
        r = zbadaj(transport, wszystkie_adresy_odczytu(u))
        if a.mierniki:
            r["mierniki"] = zbadaj_mierniki(transport, str(u.mierniki.get("identyfikator", "/meters/5")))
    finally:
        if serwer:
            serwer.stop()
    r["cel"] = f"{host}:{port}" + (" (symulator)" if a.symulator else "")
    for wiersz in streszczenie(r):
        print(wiersz)
    if a.plik:
        Path(a.plik).parent.mkdir(parents=True, exist_ok=True)
        Path(a.plik).write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Raport: {a.plik}")
    return 0 if r["identyfikacja"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
