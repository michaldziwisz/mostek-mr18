"""Symulator MR18: lokalny serwer OSC odpowiadający jak mikser.

TO JEST SYMULATOR, NIE DOWÓD ZACHOWANIA SPRZĘTU. Odpowiada wyłącznie na
parametry używane przez mostek, według dokumentu protokołu producenta
(dokument producenta „X AIR Mixer Series Remote Control Protocol”) i listy parametrów z forum. Rzeczy,
których nie wiemy o prawdziwym MR18 (czy zapis jest odsyłany do nadawcy,
czy link par sprzęga wysyłki, kwantyzacja wartości), są tu jawnymi opcjami,
a nie odwzorowaniem sprzętu. Link par (Awarie.linki_par) jest już zmierzony
na MR18 Michała: zapis jednego kanału pary zmienia drugi.

Zachowanie domyślne:
  * zapytanie (adres bez argumentu) -> odpowiedź z bieżącą wartością do nadawcy,
  * zapis (adres z argumentem) -> zmiana wartości; BEZ odpowiedzi do nadawcy
    (opcja odpowiadaj_na_zapis), powiadomienie do pozostałych subskrybentów,
  * /xremote -> subskrypcja ważna 10 s (PROTO 1.2), najwyżej 8 klientów,
  * /xinfo -> adres, nazwa „SYMULATOR MR18”, model „MR18”, wersja „symulator”,
  * /meters ,s ID -> subskrypcja mierników ważna 10 s; emituj_mierniki() wysyła
    blob pod adres ID (PROTO 1.5): liczba wartości (int32) i 44 wartości int16
    (1/256 dB) jak /meters/5, Main LR na pozycjach 6 i 7. Poziom sumy NIE jest
    liczony z miksu: to wartość poziom_lr_db, którą test albo konsola ustawia
    (np. „cisza”). Kolejność bajtów jak w mostku (little-endian), co jest luką,
  * nieznana ścieżka -> brak odpowiedzi (jak dla parametru, którego nie ma).

Awarie do wstrzyknięcia: utrata pakietów (losowa z ziarnem albo „n kolejnych”),
opóźnienie odpowiedzi, rozłączenie (cisza), ignorowanie zapisów wybranych
ścieżek, zmiana „z innego klienta”, wczytanie sceny z innego klienta.
"""

from __future__ import annotations

import argparse
import random
import socket
import threading
import time
from dataclasses import dataclass, field

from . import osc, sciezki
from .konwersje import ZERO_DB, gain_db_na_float, poziom_db_na_float, trim_db_na_float
from .mierniki import db_na_int16, koduj_blok

LIMIT_XREMOTE_S = 10.0   # PROTO 1.2
MAKS_KLIENTOW = 8        # PROTO 1.2
LICZBA_MIERNIKOW_WYJSC = 44   # PROTO /meters/5: 6 aux, lr, 16 p16, 18 usb, headphones
OKRES_MIERNIKOW_S = 0.05      # założenie symulatora, nie pomiar MR18


def scena_audycja_pelna() -> dict[str, object]:
    """Stan startowy zgodny z projektem sceny „BAZA” (plan v22, rozdz. 5, 6, 8 i 12).

    Sytuacja A: muzyka 1 na antenie, mikrofon poza anteną (suwak w górze),
    telefon i Zoom czekają (Main On włączone, suwaki na dole) i słyszą
    antenę, czyli muzykę 1 za suwakiem na poziomie bazowym. Podsłuch
    telefonu w prawym uchu (Bus 2, przed suwakiem), głośniki czynne.
    Poziomy bazowe jak w ustawienia/poziomy_bazowe.json (muzyka minus 6 dB).
    Plan v22: Bus 5 klucz przyciszania bez wyjścia (link 5/6 wyłączony, master
    na 0 dB, bez Main LR i bez USB), w sytuacji A pusty, bo słuchacz czeka.
    Głośniki mono na Bus 6. Kanał 10: kompresor kluczowany Bus 5, inserty FX1A
    (mikrofon) i FX1B (słuchacz). To projekt sceny, nie odczyt z MR18.
    """
    s: dict[str, object] = {}
    for k in range(1, 17):
        s[sciezki.lr(k)] = 0
        s[sciezki.mute_kanalu(k)] = 1
        s[sciezki.fader(k)] = ZERO_DB if k <= 10 else 0.0
        for b in range(1, 11):
            s[sciezki.wysylka(k, b)] = 0.0
        for b in range(1, 7):
            s[sciezki.tap(k, b)] = sciezki.TAP_POST
    # Rozmówcy: Main On stale włączone, o antenie decyduje suwak (plan, rozdz. 6).
    for k in (7, 8, 10):
        s[sciezki.lr(k)] = 1
        s[sciezki.fader(k)] = 0.0
    s[sciezki.tap(10, 2)] = sciezki.TAP_PRE
    # Czekający słyszą antenę: muzyka 1 za suwakiem do Bus 1 (mono) i Bus 3/4 (stereo).
    muzyka = poziom_db_na_float(-6.0)
    s[sciezki.wysylka(1, 1)] = muzyka
    s[sciezki.wysylka(2, 1)] = muzyka
    s[sciezki.wysylka(1, 3)] = muzyka
    s[sciezki.wysylka(2, 4)] = muzyka
    for k in range(1, 17):
        s[sciezki.dca(k)] = 0
        s[sciezki.grupa_mute(k)] = 0
        s[sciezki.rtntrim(k)] = trim_db_na_float(0.0)
        s[sciezki.solo(k)] = 0
        s[sciezki.gain(k)] = gain_db_na_float(20.0)
    for b in range(40, 46):
        s[f"/-stat/solosw/{b:02d}"] = 0
    s[sciezki.SOLO_MAIN_LR] = 0
    s[sciezki.gain(10)] = gain_db_na_float(30.0)
    for para in (1, 3, 5, 7, 9, 11, 13, 15):
        s[sciezki.chlink(para)] = 1 if para in (1, 3, 5, 7) else 0
    for para in (1, 3, 5):
        s[sciezki.buslink(para)] = 1 if para == 3 else 0
    for b in range(1, 7):
        s[sciezki.mute_szyny(b)] = 1
        s[sciezki.szyna_lr(b)] = 0
        s[sciezki.fader_szyny(b)] = ZERO_DB
        # Powroty AUX i efektów do szyn: w BAZIE wyłączone (plan v22, L05).
        for p in sciezki.POWROTY:
            s[sciezki.wysylka_powrotu(p, b)] = 0.0
    # Przyciszacz słuchacza (plan v22, rozdz. 8, pkt 5): keysrc Bus 5 = 21
    # (SELF, Ch01-16, Bus1-6), kompresor kanału 10 włączony, Combinator dual
    # FX1: A mikrofon, B słuchacz. Wysyłki do klucza przed suwakiem.
    for k in range(1, 17):
        s[sciezki.keysrc(k)] = 0
        s[sciezki.dyn_on(k)] = 0
        s[sciezki.insert_fxslot(k)] = 0
        s[sciezki.insert_on(k)] = 0
    s[sciezki.keysrc(10)] = sciezki.KEYSRC_SZYNA[5]
    s[sciezki.dyn_on(10)] = 1
    s[sciezki.insert_fxslot(9)], s[sciezki.insert_on(9)] = 1, 1
    s[sciezki.insert_fxslot(10)], s[sciezki.insert_on(10)] = 2, 1
    for k in (7, 8, 9):
        s[sciezki.tap(k, 5)] = sciezki.TAP_PRE
    # Podsłuch telefonu: kanał 10 do Bus 2.
    s[sciezki.wysylka(10, 2)] = poziom_db_na_float(0.0)
    # USB do komputera: 1/2 = Bus 3/4, reszta kopia Main L/R (plan, rozdz. 5).
    for w in range(1, 19):
        if w == 1:
            s[sciezki.usb_zrodlo(w)] = 28
        elif w == 2:
            s[sciezki.usb_zrodlo(w)] = 29
        else:
            s[sciezki.usb_zrodlo(w)] = 36 if w % 2 else 37
    s[sciezki.MONITOR_ZRODLO] = sciezki.ZRODLO_LRPFL
    s[sciezki.MONITOR_TRYB_KANALOW] = 0
    s[sciezki.MONITOR_DIMPFL] = 0
    s[sciezki.MONITOR_DIMATT] = 0.75
    s[sciezki.MONITOR_POZIOM] = 0.5
    s[sciezki.SCENA_INDEKS] = 1
    # Muzyka: Main On wszystkich par włączone, o antenie decyduje suwak
    # (REC na paskach muzyki nie ma funkcji, plan v20, rozdz. 8). Muzyka 1 gra
    # (suwak w górze), muzyka 2 i 3 mają suwaki na dole. Powroty rozmówców
    # biorą muzykę za suwakiem, więc słychać tylko to, co gra na antenie.
    for k in range(1, 7):
        s[sciezki.lr(k)] = 1
    for k in range(3, 7):
        s[sciezki.fader(k)] = 0.0
    for k in (3, 4, 5, 6):
        s[sciezki.wysylka(k, 1)] = muzyka
        s[sciezki.wysylka(k, 3 if k % 2 else 4)] = muzyka
    return s


@dataclass
class Awarie:
    utrata_losowa: float = 0.0          # prawdopodobieństwo zgubienia pakietu przychodzącego
    zgub_nastepne: int = 0              # tyle kolejnych pakietów przychodzących zostanie zgubionych
    opoznienie_s: float = 0.0           # opóźnienie każdej odpowiedzi
    rozlaczony: bool = False            # cisza: nic nie odbiera, nic nie wysyła
    ignoruj_zapis: set = field(default_factory=set)   # ścieżki, których zapis jest ignorowany
    odpowiadaj_na_zapis: bool = False   # czy zapis jest odsyłany nadawcy
    powiadamiaj_nadawce: bool = False   # czy /xremote dostaje też nadawca zapisu
    rozlacz_po_zapisach: int = 0        # >0: po tylu przyjętych zapisach symulator milknie
    # Link par jak w MR18 (zmierzone 23/24.10.2026): zapis kanału albo szyny
    # z linkowanej pary mikser powiela sam na drugi kanał/szynę pary.
    linki_par: bool = True
    ziarno: int = 1


class RdzenSymulatora:
    """Logika symulatora bez gniazd. przyjmij() zwraca listę (pakiet, odbiorca, opóźnienie)."""

    def __init__(self, scena: dict | None = None, zegar=time.monotonic) -> None:
        self.wartosci: dict[str, object] = dict(scena if scena is not None else scena_audycja_pelna())
        self.awarie = Awarie()
        self._los = random.Random(self.awarie.ziarno)
        self._zegar = zegar
        self.subskrybenci: dict[object, float] = {}
        # Mierniki: odbiorca -> (identyfikator, ważność). Poziom sumy wstrzykiwany.
        self.subskrybenci_miernikow: dict[object, tuple[str, float]] = {}
        self.poziom_lr_db: float = -18.0          # „gra program”; cisza: np. -90
        self.mierniki_wylaczone = False           # mikser nie wysyła mierników
        self.dziennik: list[tuple[float, object, str, object]] = []   # zapisy
        self.zapytania: list[tuple[float, object, str]] = []
        self._blokada = threading.RLock()

    # --- pomocnicze -------------------------------------------------------
    def _typ(self, adres: str) -> str:
        try:
            return sciezki.typ_sciezki(adres)
        except KeyError:
            return "i" if isinstance(self.wartosci.get(adres), int) else "f"

    def _pakiet(self, adres: str) -> bytes:
        wartosc = self.wartosci[adres]
        if isinstance(wartosc, str):
            return osc.koduj(adres, wartosc, typy="s")
        return osc.koduj(adres, wartosc, typy=self._typ(adres))

    def _aktywni(self) -> list:
        teraz = self._zegar()
        for k in [k for k, t in self.subskrybenci.items() if t < teraz]:
            del self.subskrybenci[k]
        return list(self.subskrybenci)

    def _rozeslij(self, adres: str, pomin) -> list:
        pakiet = self._pakiet(adres)
        return [(pakiet, k, self.awarie.opoznienie_s) for k in self._aktywni() if k != pomin]

    # --- wejście ----------------------------------------------------------
    def przyjmij(self, dane: bytes, nadawca) -> list:
        with self._blokada:
            a = self.awarie
            if a.rozlaczony:
                return []
            if a.zgub_nastepne > 0:
                a.zgub_nastepne -= 1
                return []
            if a.utrata_losowa and self._los.random() < a.utrata_losowa:
                return []
            try:
                komunikaty = osc.dekoduj(dane)
            except osc.BladOSC:
                return []
            wynik = []
            for k in komunikaty:
                wynik.extend(self._obsluz(k, nadawca))
            return wynik

    def _obsluz(self, k: osc.Komunikat, nadawca) -> list:
        teraz = self._zegar()
        if k.adres == "/xremote":
            if nadawca in self.subskrybenci or len(self._aktywni()) < MAKS_KLIENTOW:
                self.subskrybenci[nadawca] = teraz + LIMIT_XREMOTE_S
            return []
        if k.adres == sciezki.METERS:
            if k.argumenty and isinstance(k.wartosc, str):
                self.subskrybenci_miernikow[nadawca] = (k.wartosc, teraz + LIMIT_XREMOTE_S)
            return []
        if k.adres in ("/xinfo", "/info"):
            pakiet = osc.koduj(k.adres, "127.0.0.1", "SYMULATOR MR18", "MR18", "symulator")
            return [(pakiet, nadawca, self.awarie.opoznienie_s)]
        if k.adres == "/status":
            pakiet = osc.koduj("/status", "active", "127.0.0.1", "SYMULATOR MR18")
            return [(pakiet, nadawca, self.awarie.opoznienie_s)]
        if k.adres not in self.wartosci:
            return []
        if not k.argumenty:
            self.zapytania.append((teraz, nadawca, k.adres))
            return [(self._pakiet(k.adres), nadawca, self.awarie.opoznienie_s)]
        # zapis
        self.dziennik.append((teraz, nadawca, k.adres, k.wartosc))
        if k.adres in self.awarie.ignoruj_zapis:
            return []
        self.wartosci[k.adres] = self._normalizuj(k.adres, k.wartosc)
        partnerzy = []
        if self.awarie.linki_par:
            partnerzy = [p for p in sciezki.partnerzy_pary(k.adres, lambda a: self.wartosci.get(a) == 1)
                         if p in self.wartosci]
            for p in partnerzy:
                self.wartosci[p] = self._normalizuj(p, k.wartosc)
        if self.awarie.rozlacz_po_zapisach > 0:
            self.awarie.rozlacz_po_zapisach -= 1
            if self.awarie.rozlacz_po_zapisach == 0:
                self.awarie.rozlaczony = True
                return []
        wynik = []
        if self.awarie.odpowiadaj_na_zapis:
            wynik.append((self._pakiet(k.adres), nadawca, self.awarie.opoznienie_s))
        pomin = None if self.awarie.powiadamiaj_nadawce else nadawca
        wynik.extend(self._rozeslij(k.adres, pomin))
        for p in partnerzy:
            wynik.extend(self._rozeslij(p, pomin))
        return wynik

    def _normalizuj(self, adres: str, wartosc):
        if self._typ(adres) == "i":
            return int(wartosc)
        return min(max(float(wartosc), 0.0), 1.0)

    # --- sterowanie z testów i konsoli ----------------------------------------
    def zmien_z_innego(self, adres: str, wartosc) -> list:
        """Zmiana wykonana przez „inny klient” (np. AOSC). Powiadamia subskrybentów."""
        with self._blokada:
            self.wartosci[adres] = self._normalizuj(adres, wartosc)
            self.dziennik.append((self._zegar(), "inny-klient", adres, wartosc))
            if self.awarie.rozlaczony:
                return []
            return self._rozeslij(adres, pomin="inny-klient")

    def wczytaj_scene_z_innego(self, zmiany: dict, indeks: int = 2) -> list:
        """Wczytanie sceny z innego klienta: wiele zmian i nowy /-snap/index."""
        wynik = []
        with self._blokada:
            for adres, wartosc in zmiany.items():
                wynik.extend(self.zmien_z_innego(adres, wartosc))
            wynik.extend(self.zmien_z_innego(sciezki.SCENA_INDEKS, indeks))
        return wynik

    def cisza(self, wlacz: bool = True) -> None:
        """Wstrzyknięcie ciszy na antenie (albo powrót do grającego programu)."""
        self.poziom_lr_db = -90.0 if wlacz else -18.0

    def blok_miernikow(self) -> bytes:
        wartosci = [db_na_int16(-90.0)] * LICZBA_MIERNIKOW_WYJSC
        wartosci[6] = wartosci[7] = db_na_int16(self.poziom_lr_db)
        return koduj_blok(wartosci)

    def emituj_mierniki(self) -> list:
        """Jedna porcja mierników do każdego aktywnego subskrybenta (pakiet, odbiorca, opóźnienie)."""
        with self._blokada:
            if self.awarie.rozlaczony or self.mierniki_wylaczone:
                return []
            teraz = self._zegar()
            for k in [k for k, (_, t) in self.subskrybenci_miernikow.items() if t < teraz]:
                del self.subskrybenci_miernikow[k]
            blob = self.blok_miernikow()
            return [(osc.koduj(ident, blob, typy="b"), k, self.awarie.opoznienie_s)
                    for k, (ident, _) in self.subskrybenci_miernikow.items()]

    def zapisy_od(self, od_czasu: float) -> list:
        return [d for d in self.dziennik if d[0] >= od_czasu and d[1] != "inny-klient"]


class SerwerSymulatora:
    """Rdzeń symulatora na prawdziwym gnieździe UDP (tylko adres lokalny)."""

    def __init__(self, rdzen: RdzenSymulatora | None = None, host: str = "127.0.0.1",
                 port: int = 0) -> None:
        if not (host.startswith("127.") or host == "localhost"):
            raise ValueError("symulator słucha wyłącznie na adresie lokalnym")
        self.rdzen = rdzen or RdzenSymulatora()
        self._gniazdo = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._gniazdo.bind((host, port))
        self._gniazdo.settimeout(OKRES_MIERNIKOW_S)
        self.adres = self._gniazdo.getsockname()
        self._dziala = False
        self._watek: threading.Thread | None = None

    def start(self) -> "SerwerSymulatora":
        self._dziala = True
        self._watek = threading.Thread(target=self._petla, name="symulator-mr18", daemon=True)
        self._watek.start()
        return self

    def _petla(self) -> None:
        nastepne = time.monotonic()
        while self._dziala:
            if time.monotonic() >= nastepne:
                nastepne = time.monotonic() + OKRES_MIERNIKOW_S
                self.wyslij(self.rdzen.emituj_mierniki())
            try:
                dane, nadawca = self._gniazdo.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue        # Windows: ICMP po odpowiedzi do zamkniętego gniazda klienta
            except OSError:
                break
            self.wyslij(self.rdzen.przyjmij(dane, nadawca))

    def wyslij(self, odpowiedzi) -> None:
        for pakiet, odbiorca, opoznienie in odpowiedzi:
            if opoznienie > 0:
                t = threading.Timer(opoznienie, self._wyslij_teraz, args=(pakiet, odbiorca))
                t.daemon = True
                t.start()
            else:
                self._wyslij_teraz(pakiet, odbiorca)

    def _wyslij_teraz(self, pakiet: bytes, odbiorca) -> None:
        if self.rdzen.awarie.rozlaczony:
            return
        try:
            self._gniazdo.sendto(pakiet, odbiorca)
        except OSError:
            pass

    def zmien_z_innego(self, adres: str, wartosc) -> None:
        self.wyslij(self.rdzen.zmien_z_innego(adres, wartosc))

    def stop(self) -> None:
        self._dziala = False
        try:
            self._gniazdo.close()
        except OSError:
            pass
        if self._watek:
            self._watek.join(timeout=1.0)


POMOC_KONSOLI = """Polecenia symulatora (wpisz i naciśnij Enter):
  stan ŚCIEŻKA           pokaż wartość, np. stan /ch/09/mix/lr
  inny ŚCIEŻKA WARTOŚĆ   zmiana z innego klienta, np. inny /ch/09/mix/lr 1
  rozlacz / polacz       symulacja utraty i powrotu łączności
  gub N                  zgub N kolejnych pakietów
  opoznienie S           opóźnienie odpowiedzi w sekundach
  cisza / dzwiek         mierniki: cisza na antenie albo grający program
  mierniki wlacz|wylacz  mierniki wysyłane albo nie (brak danych to nie cisza)
  koniec                 zakończ symulator"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Symulator MR18 (nie jest dowodem zachowania sprzętu)")
    p.add_argument("--port", type=int, default=10024)
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args(argv)
    serwer = SerwerSymulatora(host=a.host, port=a.port).start()
    print(f"Symulator MR18 słucha na {serwer.adres[0]}:{serwer.adres[1]}. To symulator, nie mikser.")
    print(POMOC_KONSOLI)
    try:
        while True:
            try:
                linia = input("> ").strip()
            except EOFError:
                break
            if not linia:
                continue
            cz = linia.split()
            r = serwer.rdzen
            if cz[0] == "koniec":
                break
            elif cz[0] == "stan" and len(cz) == 2:
                print(r.wartosci.get(cz[1], "brak takiej ścieżki"))
            elif cz[0] == "inny" and len(cz) == 3:
                wartosc = float(cz[2]) if "." in cz[2] else int(cz[2])
                serwer.zmien_z_innego(cz[1], wartosc)
                print("zmieniono z innego klienta")
            elif cz[0] == "rozlacz":
                r.awarie.rozlaczony = True
                print("symulator milczy")
            elif cz[0] == "polacz":
                r.awarie.rozlaczony = False
                print("symulator odpowiada")
            elif cz[0] == "gub" and len(cz) == 2:
                r.awarie.zgub_nastepne = int(cz[1])
            elif cz[0] == "opoznienie" and len(cz) == 2:
                r.awarie.opoznienie_s = float(cz[1])
            elif cz[0] in ("cisza", "dzwiek"):
                r.cisza(cz[0] == "cisza")
                print("mierniki: " + ("cisza na antenie" if cz[0] == "cisza" else "program gra"))
            elif cz[0] == "mierniki" and len(cz) == 2 and cz[1] in ("wlacz", "wylacz"):
                r.mierniki_wylaczone = cz[1] == "wylacz"
            else:
                print(POMOC_KONSOLI)
    except KeyboardInterrupt:
        pass
    finally:
        serwer.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
