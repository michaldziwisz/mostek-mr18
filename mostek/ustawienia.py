"""Wczytanie pliku ustawień stanowiska (JSON czytelny dla człowieka)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .informacja import Komunikat, SYGNALY_BEZ_MOWY

# W paczce dane edytowalne i wyniki są obok EXE, nigdy w _internal.
KATALOG = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent.parent)
DOMYSLNE_USTAWIENIA = KATALOG / "ustawienia" / "stanowisko.json"
DOMYSLNE_POZIOMY = KATALOG / "ustawienia" / "poziomy_bazowe.json"

# Znaczenia przycisków paska (plan v22, rozdz. 8, „Mapa paska B”).
REC_DOZWOLONE = ("antena_mikrofonu", "suwakiem", "alarm_ciszy", None)
SELECT_DOZWOLONE = ("cue", "pfl", "bez_cue", "antena_mikrofonu", None)
MUTE_DOZWOLONE = ("kaszel", "talkback", None)


class BladUstawien(ValueError):
    pass


@dataclass(frozen=True)
class Zrodlo:
    klucz: str
    nazwa: str
    rodzaj: str              # "m" albo "z": rodzaj gramatyczny do odmiany komunikatów
    kanaly: tuple[int, ...]
    glos: bool               # True: mikrofon, telefon, Zoom
    odbiorca: str | None = None   # klucz odbiorcy, którego to jest własny powrót
    galka: dict | None = None
    dopelniacz: str = ""     # „Wysyłka Zooma do telefonu”
    rozmowca: str = ""       # „Słuchacz czeka”
    z_kim: str = ""          # „Rozmowa poza anteną ze słuchaczem”
    suwak_maks_db: float = 0.0   # poziom przy suwaku w samej górze (Michał 21.10.2026: mikrofon +10)


@dataclass(frozen=True)
class Odbiorca:
    klucz: str
    nazwa: str
    do: str
    szyny: tuple[int, ...]
    wlasne_zrodlo: str


@dataclass
class Ustawienia:
    surowe: dict
    zrodla: dict[str, Zrodlo]
    odbiorcy: dict[str, Odbiorca]
    paski: dict[int, dict]
    komunikaty: dict[str, str]
    mikser: dict
    profil: dict
    zachowanie: dict
    szyna_podsluchu: int
    szyny_glosnikow: tuple[int, ...]
    xtouch: dict
    nadzorca: dict
    emisja: dict
    szyna_klucza: int                 # Bus 5 „KLUCZ PRZYCISZANIA” (plan v22)
    zrodla_klucza: tuple[str, ...]    # mikrofon i Zoom
    sluchacz: str                     # źródło przyciszane (telefon, kanał 10)
    przyciszanie: dict
    mierniki: dict
    plik_poziomow: Path
    poziomy: dict = field(default_factory=dict)
    # Tryby informacji zwrotnej (decyzja Michała z 17.10.2026): mapowanie
    # zdarzenie -> dźwięk i plik z zapisanym trybem (trwały między uruchomieniami).
    informacja: dict = field(default_factory=dict)
    plik_trybu: Path = KATALOG / "ustawienia" / "tryb_informacji.json"

    def tekst(self, klucz: str, **parametry) -> str:
        try:
            wzor = self.komunikaty[klucz]
        except KeyError as e:
            raise BladUstawien(f"brak komunikatu {klucz!r} w pliku ustawień") from e
        return Komunikat(wzor.format(**parametry), (klucz,))

    def stan_slowo(self, wlaczony: bool, rodzaj: str = "m") -> str:
        if rodzaj == "z":
            return self.komunikaty["wlaczony_z" if wlaczony else "wylaczony_z"]
        return self.komunikaty["wlaczony_m" if wlaczony else "wylaczony_m"]

    # --- progi i przyciszenia ---------------------------------------------
    @property
    def prog_suwaka_db(self) -> float:
        return float(self.zachowanie.get("prog_suwaka_na_antenie_db", -50.0))

    @property
    def przyciszenie_muzyki_db(self) -> float:
        """Ujemna liczba decybeli: muzyka do rozmówcy na CUE ciszej o tyle."""
        return -abs(float(self.zachowanie.get("przyciszenie_muzyki_cue_db", -15.0)))

    @property
    def przyciszenie_muzyki_talkback(self) -> bool:
        """Czy na czas talkbacku muzyka w powrocie adresata jest przyciszona
        tak samo jak przy CUE (zlecenie Michała z 26.10.2026)."""
        return bool(self.zachowanie.get("przyciszenie_muzyki_talkback", True))

    # --- poziomy bazowe ---------------------------------------------------
    def poziom_bazowy(self, zrodlo: str, odbiorca: str) -> float:
        return float(self.poziomy["wysylki"][zrodlo][odbiorca])

    def ustaw_poziom_bazowy(self, zrodlo: str, odbiorca: str, db: float) -> None:
        self.poziomy["wysylki"].setdefault(zrodlo, {})[odbiorca] = round(float(db), 2)
        self.zapisz_poziomy()

    def poziom_podsluchu(self) -> float:
        return float(self.poziomy.get("podsluch_telefonu_db", 0.0))

    def poziom_klucza(self) -> float:
        """Poziom wysyłki do klucza przyciszania (Bus 5), przed suwakiem."""
        return float(self.poziomy.get("klucz_przyciszania_db", 0.0))

    # --- mechanizmy D&R z wersji 21 -----------------------------------------
    @property
    def alarm_ciszy(self) -> dict:
        return self.zachowanie.get("alarm_ciszy", {})

    @property
    def przypomnienie_mikrofonu_min(self) -> float:
        """Co ile minut mikrofonu na antenie przypomnienie; 0 = wyłączone."""
        return float(self.zachowanie.get("przypomnienie_mikrofonu_min", 0))

    @property
    def kaszel_maks_s(self) -> float:
        """Zgodność ze starymi ustawieniami: trzymanie zawsze bez limitu."""
        return 0.0

    def zapisz_poziomy(self) -> None:
        tymczasowy = self.plik_poziomow.with_suffix(".json.tmp")
        tymczasowy.write_text(json.dumps(self.poziomy, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        os.replace(tymczasowy, self.plik_poziomow)


def wczytaj(sciezka: Path | str = DOMYSLNE_USTAWIENIA,
            poziomy: Path | str = DOMYSLNE_POZIOMY) -> Ustawienia:
    from .walidator import wczytaj_zgodnie
    return wczytaj_zgodnie(sciezka, poziomy, _z_danych)


def _z_danych(dane, pozi, poziomy):
    """Dotychczasowa konwersja i kontrola startu, bez nowych ograniczeń."""
    zrodla = {}
    for klucz, z in dane["zrodla"].items():
        if klucz.startswith("_"):
            continue
        zrodla[klucz] = Zrodlo(
            klucz=klucz, nazwa=z["nazwa"], rodzaj=z.get("rodzaj", "m"),
            kanaly=tuple(int(k) for k in z["kanaly"]), glos=bool(z.get("glos", False)),
            odbiorca=z.get("odbiorca"), galka=z.get("galka"),
            dopelniacz=z.get("dopelniacz", z["nazwa"]), rozmowca=z.get("rozmowca", z["nazwa"]),
            z_kim=z.get("z_kim", ""), suwak_maks_db=float(z.get("suwak_maks_db", 0.0)))
    odbiorcy = {}
    for klucz, o in dane["odbiorcy"].items():
        if klucz.startswith("_"):
            continue
        odbiorcy[klucz] = Odbiorca(klucz=klucz, nazwa=o["nazwa"], do=o["do"],
                                   szyny=tuple(int(s) for s in o["szyny"]),
                                   wlasne_zrodlo=o["wlasne_zrodlo"])
    paski = {int(p["pasek"]): p for p in dane["paski"]}
    prz = dane.get("przyciszanie", {})
    u = Ustawienia(
        surowe=dane, zrodla=zrodla, odbiorcy=odbiorcy, paski=paski,
        komunikaty=dane["komunikaty"], mikser=dane["mikser"],
        profil=dane["profil"], zachowanie=dane["zachowanie"],
        szyna_podsluchu=int(dane["szyny"]["podsluch_telefonu"]),
        szyny_glosnikow=tuple(int(s) for s in dane["szyny"]["glosniki"]),
        xtouch=dane["xtouch"], nadzorca=dane["nadzorca"], emisja=dane["emisja"],
        szyna_klucza=int(dane["szyny"]["klucz_przyciszania"]),
        zrodla_klucza=tuple(prz.get("zrodla_klucza", ("mikrofon", "zoom"))),
        sluchacz=str(prz.get("sluchacz", "telefon")), przyciszanie=prz,
        mierniki=dane.get("mierniki", {}),
        plik_poziomow=poziomy, poziomy=pozi,
        informacja=dane.get("informacja_zwrotna", {}))
    plik = Path(u.informacja.get("plik_trybu", "ustawienia/tryb_informacji.json"))
    u.plik_trybu = plik if plik.is_absolute() else KATALOG / plik
    sprawdz(u)
    return u


def sprawdz_informacje(u: Ustawienia) -> None:
    """Mapowanie zdarzenie -> dźwięk: zdarzenie to klucz komunikatu (z wariantem
    po dwukropku), wartość to klucz dźwięku albo lista kluczy. Brak pliku
    dźwięku nie jest błędem ustawień: mostek mówi wtedy zamiast dźwięku.
    Wyjątek: dwa sygnały talkbacku nie wymagają tekstu i nie mają mowy zastępczej."""
    cfg = u.informacja
    if not isinstance(cfg, dict):
        raise BladUstawien("informacja_zwrotna musi być obiektem")
    zdarzenia = cfg.get("zdarzenia", {})
    if not isinstance(zdarzenia, dict):
        raise BladUstawien("informacja_zwrotna.zdarzenia musi być obiektem")
    for z, v in zdarzenia.items():
        if z.startswith("_"):
            continue
        if z not in SYGNALY_BEZ_MOWY and z.split(":", 1)[0] not in u.komunikaty:
            raise BladUstawien(f"zdarzenie dźwięku {z!r}: nie ma takiego komunikatu")
        lista = [v] if isinstance(v, str) else v
        if not isinstance(lista, list) or not all(isinstance(x, str) and x for x in lista):
            raise BladUstawien(f"zdarzenie dźwięku {z!r}: wartość to klucz dźwięku albo lista kluczy")
    ost = cfg.get("dzwiek_ostrzezenia")
    if ost is not None and not (isinstance(ost, str) and ost):
        raise BladUstawien("informacja_zwrotna.dzwiek_ostrzezenia: klucz dźwięku albo null")
    for k in ("tryb_mowa", "tryb_dzwieki", "tryb_dzwieki_z_mowa", "brak_powtorzenia",
              "alarm_ciszy_wlaczony", "alarm_ciszy_wylaczony"):
        if k not in u.komunikaty:
            raise BladUstawien(f"brak komunikatu {k!r}")
    okres = float(u.xtouch.get("ponowienie_portu_s", 2.0))
    if not 0.2 <= okres <= 60.0:
        raise BladUstawien("xtouch.ponowienie_portu_s poza zakresem 0,2 do 60 sekund")
    zycie = float(u.xtouch.get("zycie_s", 1.0))
    if zycie != 0 and not 0.2 <= zycie <= 30.0:
        raise BladUstawien("xtouch.zycie_s: 0 albo od 0,2 do 30 sekund")
    if not 1 <= int(u.xtouch.get("zycie_proby", 2)) <= 10:
        raise BladUstawien("xtouch.zycie_proby poza zakresem 1 do 10")


def sprawdz(u: Ustawienia) -> None:
    """Kontrola spójności pliku ustawień z niezmiennikami planu."""
    for wymagane in ("mikrofon", "telefon", "zoom"):
        if wymagane not in u.zrodla:
            raise BladUstawien(f"brak źródła {wymagane!r}")
    for o in u.odbiorcy.values():
        if o.wlasne_zrodlo not in u.zrodla:
            raise BladUstawien(f"odbiorca {o.klucz}: nieznane własne źródło")
    zajete: dict[int, str] = {}
    for z in u.zrodla.values():
        for k in z.kanaly:
            if k in zajete:
                raise BladUstawien(f"kanał {k} przypisany dwa razy: {zajete[k]} i {z.klucz}")
            zajete[k] = z.klucz
    if u.szyna_podsluchu in [s for o in u.odbiorcy.values() for s in o.szyny]:
        raise BladUstawien("szyna podsłuchu nie może być szyną rozmówcy")
    rozmowcy = {o.wlasne_zrodlo for o in u.odbiorcy.values()}
    # Plan v22: Bus 5 klucz przyciszania, Bus 6 głośniki mono.
    szyny_rozm = {s for o in u.odbiorcy.values() for s in o.szyny}
    k = u.szyna_klucza
    if k in u.szyny_glosnikow or k == u.szyna_podsluchu or k in szyny_rozm:
        raise BladUstawien("szyna klucza przyciszania musi być osobną szyną, bez głośników i rozmówców")
    if not u.szyny_glosnikow or any(b in szyny_rozm or b == u.szyna_podsluchu for b in u.szyny_glosnikow):
        raise BladUstawien("szyna głośników musi być osobną szyną")
    if u.sluchacz not in rozmowcy:
        raise BladUstawien("przyciszany słuchacz musi być rozmówcą")
    if "mikrofon" not in u.zrodla_klucza or u.sluchacz in u.zrodla_klucza:
        raise BladUstawien("klucz przyciszania: mikrofon tak, słuchacz nigdy")
    for zr in u.zrodla_klucza:
        if zr not in u.zrodla or not u.zrodla[zr].glos:
            raise BladUstawien(f"klucz przyciszania: {zr!r} nie jest głosem")
    for p, opis in u.paski.items():
        zr = opis.get("zrodlo")
        if zr is None:
            continue
        if zr not in u.zrodla:
            raise BladUstawien(f"pasek {p}: nieznane źródło {zr}")
        rec, sel = opis.get("rec"), opis.get("select")
        if opis.get("mute") not in MUTE_DOZWOLONE:
            raise BladUstawien(f"pasek {p}: nieznane znaczenie MUTE {opis.get('mute')!r}")
        if opis.get("mute") == "kaszel" and zr != "mikrofon":
            raise BladUstawien(f"pasek {p}: przycisk kaszlu tylko na pasku mikrofonu")
        if opis.get("mute") == "talkback":
            odb = u.zrodla[zr].odbiorca
            if (zr == "mikrofon" or not u.zrodla[zr].glos or odb not in u.odbiorcy
                    or u.odbiorcy[odb].wlasne_zrodlo != zr):
                raise BladUstawien(f"pasek {p}: talkback tylko na pasku rozmówcy z własnym odbiorcą")
        if rec not in REC_DOZWOLONE:
            raise BladUstawien(f"pasek {p}: nieznane znaczenie REC {rec!r}")
        if sel not in SELECT_DOZWOLONE:
            raise BladUstawien(f"pasek {p}: nieznane znaczenie SELECT {sel!r}")
        if rec == "antena_mikrofonu" and zr != "mikrofon":
            raise BladUstawien(f"pasek {p}: REC przełącza antenę tylko na pasku mikrofonu")
        if sel == "antena_mikrofonu" and zr != "mikrofon":
            raise BladUstawien(f"pasek {p}: SELECT przełącza antenę tylko na pasku mikrofonu")
        if sel == "cue" and zr not in rozmowcy:
            raise BladUstawien(f"pasek {p}: CUE tylko na paskach rozmówców")
        if sel == "pfl" and u.zrodla[zr].glos:
            raise BladUstawien(f"pasek {p}: SELECT jako PFL tylko na paskach muzyki")
    if not isinstance(u.emisja.get("mikrofon_wstrzymuje_automat", True), bool):
        raise BladUstawien("emisja.mikrofon_wstrzymuje_automat: wymagane true albo false")
    usb = u.profil.get("usb_suche_dozwolone", [])
    if not isinstance(usb, list) or not all(isinstance(x, int) and 1 <= x <= int(u.profil.get("wyjscia_usb", 18)) for x in usb):
        raise BladUstawien("profil.usb_suche_dozwolone: lista numerów wyjść USB")
    if {1, 2, 3, 4} & set(usb):
        raise BladUstawien("profil.usb_suche_dozwolone: wyjścia 1/2 (Zoom) i 3/4 (emisja) nigdy nie niosą suchego głosu")
    for zr in u.zrodla.values():
        if not 0.0 <= zr.suwak_maks_db <= 10.0:
            raise BladUstawien(f"{zr.klucz}: suwak_maks_db poza zakresem 0 do plus 10 dB")
    if not -60.0 <= u.przyciszenie_muzyki_db <= 0.0:
        raise BladUstawien("przyciszenie muzyki przy CUE poza zakresem 0 do minus 60 dB")
    a = u.alarm_ciszy
    if a:
        if not -90.0 <= float(a.get("prog_dbfs", -50.0)) <= 0.0:
            raise BladUstawien("próg alarmu ciszy poza zakresem 0 do minus 90 dBFS")
        if float(a.get("czas_s", 10.0)) <= 0 or float(a.get("powtorka_s", 30.0)) <= 0:
            raise BladUstawien("czas alarmu ciszy i przerwa powtórki muszą być dodatnie")
    if u.przypomnienie_mikrofonu_min < 0:
        raise BladUstawien("przypomnienie mikrofonu: liczba minut nie może być ujemna")
    sprawdz_informacje(u)
    for zr in u.zrodla:
        for odb in u.odbiorcy.values():
            if odb.wlasne_zrodlo == zr:
                continue
            if zr not in u.poziomy.get("wysylki", {}) or odb.klucz not in u.poziomy["wysylki"][zr]:
                raise BladUstawien(f"brak poziomu bazowego wysyłki {zr} -> {odb.klucz}")
