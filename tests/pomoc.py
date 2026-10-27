"""Wspólne narzędzia testów: mostek kontra symulator w pamięci albo przez UDP."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

KATALOG = Path(__file__).resolve().parent.parent
if str(KATALOG) not in sys.path:
    sys.path.insert(0, str(KATALOG))

from mostek import sciezki, ustawienia  # noqa: E402
from mostek.klient import KlientMR18  # noqa: E402
from mostek.konwersje import ZERO_DB, poziom_db_na_float  # noqa: E402
from mostek.informacja import AtrapaDzwiekow, InformacjaZwrotna  # noqa: E402
from mostek.mowa import AtrapaMowy, KolejkaMowy  # noqa: E402
from mostek.rdzen import Rdzen  # noqa: E402
from mostek.symulator import RdzenSymulatora  # noqa: E402
from mostek.transport import TransportPamieciowy  # noqa: E402


class Zegar:
    """Sterowany zegar: testy nie czekają naprawdę (poza testami UDP)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def sen(self, s: float) -> None:
        self.t += s

    def przesun(self, s: float) -> None:
        self.t += s


def wczytaj_ustawienia(katalog_tymczasowy: Path):
    kopia = katalog_tymczasowy / "poziomy_bazowe.json"
    shutil.copy(ustawienia.DOMYSLNE_POZIOMY, kopia)
    u = ustawienia.wczytaj(ustawienia.DOMYSLNE_USTAWIENIA, kopia)
    # Tryb informacji zwrotnej zapisuje się w katalogu testu, nigdy w repozytorium.
    u.plik_trybu = katalog_tymczasowy / "tryb_informacji.json"
    # Testy logiki liczą zegarem w krokach dobranych do odczytu okresowego co
    # 0,5 s. Na stanowisku okres jest dłuższy (mniej ruchu do MR18); osobny
    # test sprawdza właśnie tę wartość z pliku ustawień.
    u.mikser["okres_odczytu_krytycznego_s"] = 0.5
    return u


class AtrapaPowierzchni:
    def __init__(self) -> None:
        self.suwaki: dict[int, float] = {}
        self.diody: dict[tuple[int, int], object] = {}
        self.pierscienie: dict[int, float] = {}
        self.klawisze: dict[str, object] = {}

    def ustaw_suwak(self, pasek, pozycja):
        self.suwaki[pasek] = pozycja

    def ustaw_diode(self, pasek, indeks, stan):
        self.diody[(pasek, indeks)] = stan

    def ustaw_pierscien(self, pasek, wartosc):
        self.pierscienie[pasek] = wartosc

    def ustaw_klawisz(self, nazwa, stan):
        self.klawisze[nazwa] = stan


class TestZSymulatorem(unittest.TestCase):
    """Mostek połączony z symulatorem w pamięci, z sterowanym zegarem."""

    synchronizuj_na_starcie = True

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mostek-test-")
        self.u = wczytaj_ustawienia(Path(self._tmp.name))
        self.zegar = Zegar()
        self.sym = RdzenSymulatora(zegar=self.zegar)
        self.transport = TransportPamieciowy(self.sym)
        self.klient = KlientMR18(self.transport, limit_odpowiedzi_s=0.01, dodatkowe_proby=2)
        self.wyjscie = AtrapaMowy()
        # Pełny tor informacji zwrotnej z atrapą dźwięków, w trybie domyślnym
        # (dźwięki z mową): każdy test sprawdza mowę przy włączonych dźwiękach.
        self.dzwieki = AtrapaDzwiekow()
        self.info = InformacjaZwrotna(self.u, self.dzwieki)
        self.mowa = KolejkaMowy(self.wyjscie, alarm=None, dzwieki=self.info)
        self.pow = AtrapaPowierzchni()
        self.r = Rdzen(self.u, self.klient, self.mowa, powierzchnia=self.pow,
                       zegar=self.zegar, sen=self.zegar.sen)
        if self.synchronizuj_na_starcie:
            self.assertTrue(self.r.synchronizuj(nowa_baza_galek=True))
            self.slowa()

    def tearDown(self) -> None:
        self.r.zamknij_emisje()
        self.klient.zamknij()
        self._tmp.cleanup()

    # --- pomocnicze ---------------------------------------------------------
    def slowa(self) -> list[str]:
        """Wypowiedz kolejkę i zwróć, co padło od ostatniego wywołania."""
        self.assertTrue(self.r._tor_emisji.czekaj(), "worker emisji nie zakończył operacji")
        self.r.odbierz_emisje()
        self.mowa.oproznij()
        wynik = list(self.wyjscie.powiedziane)
        self.wyjscie.powiedziane.clear()
        self.ostatnie_dzwieki = list(self.dzwieki.odtworzone)
        self.dzwieki.odtworzone.clear()
        return wynik

    def dzwieki_i_slowa(self) -> tuple[list[str], list[str]]:
        """(odtworzone klucze dźwięków, wypowiedziane teksty) od ostatniego wywołania."""
        s = self.slowa()
        return self.ostatnie_dzwieki, s

    def m(self, adres: str):
        """Wartość w symulatorze (prawdziwy stan „miksera”)."""
        return self.sym.wartosci[adres]

    def zapisy(self, od: int = 0) -> list[tuple[str, object]]:
        return [(d[2], d[3]) for d in self.sym.dziennik[od:] if d[1] != "inny-klient"]

    def ten_sam_stan(self, maja: dict, przed: dict, opis: str = "") -> None:
        """Ten sam stan miksera: zestaw adresów dokładnie, a wartości z
        tolerancją miksera (klient.zgodne, 0,005).

        Wartości ze sceny są w pliku liczbami podwójnej precyzji, a wszystko,
        co przeszło przez OSC, jest float32 (np. 0,6 wraca jako
        0,6000000238418579). Każdy zapis tej samej wysyłki — także przy
        zwykłym CUE — daje więc inne bajty przy tym samym poziomie, o ponad
        rząd mniejszym niż rozdzielczość, którą mostek uznaje za zmianę.
        """
        from mostek.klient import zgodne
        self.assertEqual(set(maja), set(przed), f"inny zestaw adresów ({opis})")
        rozne = [(a, maja[a], przed[a]) for a in przed if not zgodne(maja[a], przed[a])]
        self.assertEqual(rozne, [], f"stan miksera inny niż oczekiwany ({opis})")

    def nacisnij(self, *zdarzenie) -> None:
        self.zegar.przesun(0.2)     # poza oknem debounce
        self.r.zglos(tuple(zdarzenie))

    def klawisz(self, nazwa: str) -> None:
        self.nacisnij("klawisz", nazwa)

    def inny(self, adres: str, wartosc) -> None:
        """Zmiana z „innego klienta”; mostek dostaje zgłoszenie /xremote."""
        self.transport.rozeslij(self.sym.zmien_z_innego(adres, wartosc))
        self.r.przetworz_zgloszenia()

    def ustaw_mikser(self, zmiany: dict) -> None:
        """Bezpośrednie ustawienie symulatora przed synchronizacją (bez zgłoszeń)."""
        self.sym.wartosci.update(zmiany)

    def czekaj(self, sekundy: float, krok: float = 5.0) -> list[str]:
        """Upływ czasu krokami (subskrypcje mierników i /xremote żyją 10 s);
        zwraca wszystko, co NVDA powiedziała po drodze."""
        mowa = []
        zostalo = sekundy
        while zostalo > 1e-9:
            d = min(krok, zostalo)
            self.tick(d)
            zostalo -= d
            mowa += self.slowa()
        return mowa

    def tick(self, s: float = 0.6) -> None:
        self.zegar.przesun(s)
        # Symulator w pamięci nie ma własnej pętli: porcja mierników przy każdym kroku.
        self.transport.rozeslij(self.sym.emituj_mierniki())
        self.r.tick()

    # --- stan logiczny w mikserze ---------------------------------------------
    def suma(self, zr: str) -> bool:
        return all(self.m(sciezki.lr(k)) == 1 for k in self.u.zrodla[zr].kanaly)

    def wysylka(self, zr: str, odb: str) -> bool:
        from mostek.logika import pary_wysylek
        pary = pary_wysylek(self.u.zrodla[zr].kanaly, self.u.odbiorcy[odb].szyny)
        wart = [float(self.m(sciezki.wysylka(k, b))) > 0 for k, b in pary]
        self.assertEqual(len(set(wart)), 1, f"rozbieżne wysyłki {zr}->{odb}")
        return wart[0]

    def pfl(self, zr: str) -> bool:
        return all(self.m(sciezki.solo(k)) == 1 for k in self.u.zrodla[zr].kanaly)

    def glosniki_wyciszone(self) -> bool:
        return all(self.m(sciezki.mute_szyny(b)) == 0 for b in self.u.szyny_glosnikow)

    def podsluch(self) -> bool:
        return float(self.m(sciezki.wysylka(10, 2))) > 0

    # --- model CUE liczony z surowych wartości symulatora ---------------------
    # Niezależnie od logika.Widok: test nie może sprawdzać logiki nią samą.
    GRUPY = {"mikrofon": "mikrofon", "telefon": "telefon", "zoom": "zoom",
             "muzyka1": "muzyka", "muzyka2": "muzyka", "muzyka3": "muzyka"}

    def slyszalny(self, kanal: int, szyna: int) -> bool:
        """Wysyłka daje dźwięk: poziom powyżej zera i (przed suwakiem albo suwak nie na dole)."""
        if float(self.m(sciezki.wysylka(kanal, szyna))) <= 0:
            return False
        return int(self.m(sciezki.tap(kanal, szyna))) == 3 or float(self.m(sciezki.fader(kanal))) > 0

    def na_antenie_sym(self, zr: str) -> bool:
        k = self.u.zrodla[zr].kanaly
        return all(self.m(sciezki.lr(x)) == 1 for x in k) and all(float(self.m(sciezki.fader(x))) > 0 for x in k)

    def antena(self) -> set:
        return {self.GRUPY[z] for z in self.u.zrodla if self.na_antenie_sym(z)}

    def slyszy(self, odb: str) -> set:
        """Kto trafia do powrotu rozmówcy; muzyka obniżona o co najmniej 10 dB to „muzyka ciszej”."""
        from mostek.konwersje import poziom_float_na_db
        from mostek.logika import pary_wysylek
        wynik = set()
        for z in self.u.zrodla:
            pary = pary_wysylek(self.u.zrodla[z].kanaly, self.u.odbiorcy[odb].szyny)
            if not any(self.slyszalny(k, b) for k, b in pary):
                continue
            grupa = self.GRUPY[z]
            if grupa == "muzyka":
                db = max(poziom_float_na_db(float(self.m(sciezki.wysylka(k, b)))) for k, b in pary)
                if db < self.u.poziom_bazowy(z, odb) - 10.0:
                    grupa = "muzyka ciszej"
            wynik.add(grupa)
        return wynik

    def cue_sym(self, r: str) -> bool:
        """Zwykle znacznik PRE mikrofonu; w chwilowym przejęciu CUE odczytane
        przed trzymaniem. Nie czytamy zbioru CUE z Widoku, tylko surowe
        poziomy symulatora.

        Do 26.10.2026 ślad CUE w trzymaniu dawała przyciszona muzyka, której
        kaszel i talkback nie mogły dotknąć. Od zlecenia Michała z tej daty
        talkback przycisza muzykę adresata dokładnie tak jak CUE, a po
        przerwaniu przy utracie miksera przyciszenie zostaje, więc z samych
        wartości miksera CUE rozmówcy nie da się już orzec: obraz tras jest
        identyczny. W trybie chwilowym CUE jest więc kontekstem wejściowym
        (`cue_chwilowe`, ustawione z potwierdzonego odczytu przed pierwszym
        zapisem), tak jak flagi talkbacku i kaszlu. Przy wyłączonym
        przyciszeniu talkbacku dawny, niezależny ślad działa dalej.
        """
        if self.r.widok.cue_chwilowe is not None:
            if self.u.przyciszenie_muzyki_talkback:
                return r in self.r.widok.cue_chwilowe
            return all(0 < float(self.m(sciezki.wysylka(k, b))) <= poziom_db_na_float(
                self.u.poziom_bazowy(z, r) + self.u.przyciszenie_muzyki_db) + 0.005
                for z in ("muzyka1", "muzyka2", "muzyka3")
                for k in self.u.zrodla[z].kanaly for b in self.u.odbiorcy[r].szyny
                if len(self.u.odbiorcy[r].szyny) == 1 or k % 2 == b % 2)
        return any(float(self.m(sciezki.wysylka(9, b))) > 0 and int(self.m(sciezki.tap(9, b))) == 3
                   for b in self.u.odbiorcy[r].szyny)

    def w_kluczu(self) -> set:
        """Kto jest w kluczu przyciszania (Bus 5): wysyłka powyżej zera, z surowych wartości."""
        kb = self.u.szyna_klucza
        wynik = set()
        for z in self.u.zrodla:
            if any(float(self.m(sciezki.wysylka(k, kb))) > 0 for k in self.u.zrodla[z].kanaly):
                wynik.add(self.GRUPY[z])
        return wynik

    def na_antenie_klucz(self, zr: str) -> bool:
        """„Na antenie” w sensie planu: mikrofon to Main On (przełącznik), rozmówca
        to Main On i suwak powyżej progu z ustawień (rozdz. 7)."""
        k = self.u.zrodla[zr].kanaly
        if not all(self.m(sciezki.lr(x)) == 1 for x in k):
            return False
        if zr == "mikrofon":
            return True
        prog = poziom_db_na_float(self.u.prog_suwaka_db)
        return all(float(self.m(sciezki.fader(x))) > prog for x in k)

    def rozmowa_sluchacza(self) -> set:
        """Źródła klucza w tej samej rozmowie co słuchacz, z surowych wartości (decyzja 5)."""
        cue = {r for r in ("telefon", "zoom") if self.cue_sym(r)}
        if "telefon" in cue:
            return {"mikrofon"} | ({"zoom"} if "zoom" in cue else set())
        if not self.na_antenie_klucz("telefon"):
            return set()
        return {z for z in ("mikrofon", "zoom") if self.na_antenie_klucz(z) and z not in cue}

    def naruszenia_klucza(self) -> list[str]:
        m = self.m
        kb = self.u.szyna_klucza
        n = []
        kto = self.w_kluczu()
        rozmowa = self.rozmowa_sluchacza()
        if kto - {"mikrofon", "zoom"}:
            n.append(f"w kluczu przyciszania coś poza głosami: {sorted(kto - {'mikrofon', 'zoom'})}")
        if kto - rozmowa - {"telefon", "muzyka"}:
            n.append(f"w kluczu źródło spoza rozmowy słuchacza: {sorted(kto - rozmowa)}")
        if m(sciezki.szyna_lr(kb)) == 1:
            n.append("klucz przyciszania na Main LR")
        for wy in range(1, 19):
            if m(sciezki.usb_zrodlo(wy)) == sciezki.USB_ZRODLO_SZYNA[kb]:
                n.append(f"klucz przyciszania na USB {wy}")
        if m(sciezki.buslink(5)) == 1:
            n.append("klucz przyciszania połączony z głośnikami")
        for k in (7, 8, 9):
            if float(m(sciezki.wysylka(k, kb))) > 0 and int(m(sciezki.tap(k, kb))) != 3:
                n.append(f"kanał {k} do klucza nie przed suwakiem")
        return n

    def pasek(self, zr: str) -> int:
        return {"mikrofon": 1, "telefon": 2, "zoom": 3, "muzyka1": 4, "muzyka2": 5, "muzyka3": 6}[zr]

    def cue(self, zr: str) -> None:
        """SELECT paska rozmówcy (CUE)."""
        self.nacisnij("przycisk", self.pasek(zr), 3)

    def ruch(self, zr: str, pozycja: float, puszczony: bool = True) -> None:
        """Ręczny ruch suwaka: dotyk, pozycja, puszczenie, potwierdzenie odczytem."""
        p = self.pasek(zr)
        self.nacisnij("dotyk", p, True)
        self.nacisnij("suwak", p, pozycja)
        if puszczony:
            self.nacisnij("dotyk", p, False)
        self.tick(0.6)

    def naruszenia_miksera(self, talkback=None, kaszel=None) -> list[str]:
        """Niezmienniki planu sprawdzane na wartościach symulatora (stan „miksera”)."""
        m = self.m
        poz = lambda k, b: float(m(sciezki.wysylka(k, b)))  # noqa: E731
        n = []
        if poz(10, 1) > 0:
            n.append("telefon wraca do telefonu (Bus 1)")
        for k in (7, 8):
            for b in (3, 4):
                if poz(k, b) > 0:
                    n.append(f"Zoom wraca do Zooma (kanał {k}, Bus {b})")
        for b in self.u.szyny_glosnikow:
            if poz(9, b) > 0:
                n.append(f"mikrofon w głośnikach (Bus {b})")
        for k in range(1, 17):
            if k != 10 and poz(k, 2) > 0:
                n.append(f"kanał {k} w podsłuchu telefonu (Bus 2)")
        for b in range(1, 7):
            if m(sciezki.szyna_lr(b)) == 1:
                n.append(f"Bus {b} na sumie")
        mik_otwarty = m(sciezki.lr(9)) == 1 or any(poz(9, b) > 0 for b in (1, 3, 4))
        if mik_otwarty and not self.glosniki_wyciszone():
            n.append("tor mikrofonu otwarty przy niewyciszonych głośnikach")
        talkback = self.r._talkback if talkback is None else talkback
        kaszel = self.r._kaszel is not None if kaszel is None else kaszel
        # Chwilowe tryby są kontekstem wejściowym; wyjścia nadal mierzymy
        # niezależnie w symulatorze, bez wywołania Widoku ani reguł produkcji.
        if talkback or kaszel:
            if m(sciezki.lr(9)) != 0 or poz(9, 5) != 0:
                n.append("chwilowy mikrofon na antenie albo w kluczu")
            for r, bs in (("telefon", (1,)), ("zoom", (3, 4))):
                for b in bs:
                    if kaszel or r not in talkback:
                        if poz(9, b) != 0:
                            n.append(f"mikrofon u niedozwolonego adresata {r}")
                    elif poz(9, b) > 0 and m(sciezki.tap(9, b)) != 3:
                        n.append(f"talkback do {r} nie przed suwakiem")
        # Model CUE (plan v20, rozdz. 6 i karta zlecenia, pkt 4).
        kanaly = {"mikrofon": (9,), "telefon": (10,), "zoom": (7, 8)}
        szyny = {"telefon": (1,), "zoom": (3, 4)}
        cue = {r for r in ("telefon", "zoom") if self.cue_sym(r)}
        bez = {"telefon", "zoom"} - cue
        if cue and m(sciezki.lr(9)) == 1:
            n.append("mikrofon na antenie przy CUE")
        for r in cue:
            if any(m(sciezki.lr(k)) == 1 for k in kanaly[r]):
                n.append(f"{r} na sumie przy własnym CUE")
            for inny in bez:
                if not talkback and any(poz(9, b) > 0 for b in szyny[inny]):
                    n.append(f"{inny} bez CUE dostaje mikrofon przy CUE {r}")
                if any(poz(k, b) > 0 for k in kanaly[r] for b in szyny[inny]):
                    n.append(f"{inny} bez CUE słyszy {r} z CUE")
                if any(poz(k, b) > 0 for k in kanaly[inny] for b in szyny[r]):
                    n.append(f"{r} z CUE słyszy {inny} bez CUE")
            limit = self.u.przyciszenie_muzyki_db
            for z in ("muzyka1", "muzyka2", "muzyka3"):
                gr = poziom_db_na_float(self.u.poziom_bazowy(z, r) + limit) + 0.005
                if any(poz(k, b) > gr for k in self.u.zrodla[z].kanaly for b in szyny[r]):
                    n.append(f"{z} do {r} z CUE głośniej niż przyciszenie")
        for x in ("telefon", "zoom"):
            for r in ("telefon", "zoom"):
                if r == x:
                    continue
                for k in kanaly[x]:
                    for b in szyny[r]:
                        if poz(k, b) > 0 and int(m(sciezki.tap(k, b))) != 4 and not (x in cue and r in cue):
                            n.append(f"głos {x} do {r} przed suwakiem poza rozmową")
        if "telefon" in cue and self.podsluch():
            n.append("podsłuch prawego ucha przy CUE telefonu")
        # Klucz przyciszania (plan v22, rozdz. 8, pkt 5), liczony z surowych wartości.
        n += self.naruszenia_klucza()
        for k in range(1, 17):
            for b in range(1, 7):
                t = int(m(sciezki.tap(k, b)))
                if k <= 6 and b in (1, 3, 4) and t != 4:
                    n.append(f"muzyka kanał {k} do Bus {b} nie za suwakiem")
        return n


__all__ = ["TestZSymulatorem", "Zegar", "wczytaj_ustawienia", "AtrapaPowierzchni", "sciezki",
           "ZERO_DB", "poziom_db_na_float", "KATALOG"]
