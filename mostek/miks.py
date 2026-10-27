"""Sesja punktów SARY, używana wyłącznie przez wątek TorEmisji.

Osobne trwałe TCP jest konieczne: SARA porzuca sesję przy rozłączeniu jej
właściciela. Transport antenowy i Hold nadal mają swoje krótkie połączenia.
Nie odtwarzamy semantyki punktów w kliencie: wartości pochodzą z SARY.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import time

from .emisja import BladEmisji, NiePolaczono, WymagaSary
from .liczniki import czas_slownie

log = logging.getLogger("mostek.miks")
PUNKTY = ("cue", "intro", "outro", "segue", "segue_fade", "overlap", "loop_start", "loop_end")
NAZWY: dict[str, str] = dict(zip(PUNKTY, ("miks_nazwa_cue", "miks_nazwa_intro", "miks_nazwa_outro",
    "miks_nazwa_segue", "miks_nazwa_segue_fade", "miks_nazwa_overlap",
    "miks_nazwa_loop_start", "miks_nazwa_loop_end")))
ODSLUCHY = {"brak": "miks_odsluch_brak", "pozycja": "miks_odsluch_pozycja",
            "punkt": "miks_odsluch_punkt", "przejscie": "miks_odsluch_przejscie"}


def czas(ms, ulamek=True):
    minuty, sekundy = divmod(ms // 1000, 60)
    return f"{minuty}:{sekundy:02d}" + (f",{ms % 1000 // 100}" if ulamek else "")


def przesuniecie(ms):
    """Dziesiętne sekundy bez błędów sumowania zmiennoprzecinkowego."""
    calosc, reszta = divmod(abs(ms), 1000)
    return ("+" if ms >= 0 else "-") + str(calosc) + (f".{reszta:03d}".rstrip("0") if reszta else "")


@dataclass(frozen=True)
class StanMiksu:
    pozycja: int
    punkt: str
    wartosc: int | None
    zmiany: bool
    odsluch: str

    @classmethod
    def czytaj(cls, linia, dlugosc):
        p = linia.split("|")
        if (len(p) != 5 or not re.fullmatch(r"[0-9]+", p[0]) or p[1] not in PUNKTY
                or not re.fullmatch(r"-|[0-9]+", p[2]) or p[3] not in ("0", "1")
                or p[4] not in ("brak", "pozycja", "punkt", "przejscie")):
            raise BledneDaneMiksu("nieprawidłowy stan Mix")
        pozycja = int(p[0])
        wartosc = None if p[2] == "-" else int(p[2])
        if pozycja > dlugosc or (wartosc is not None and wartosc > dlugosc):
            raise BledneDaneMiksu("czas Mix poza utworem")
        return cls(pozycja, p[1], wartosc, p[3] == "1", p[4])


class OdmowaMiksu(Exception):
    pass


class BledneDaneMiksu(BladEmisji):
    """SARA odpowiedziała, ale treść odpowiedzi jest niezgodna z protokołem."""


class TrybMiksu:
    def __init__(self, ustawienia):
        self.t = ustawienia.tekst
        self.sesja = None
        self.stan = None
        self.dlugosc = 0
        self.sprawdz_o = float("inf")

    @property
    def aktywny(self):
        return self.sesja is not None and self.stan is not None

    def zamknij(self):
        s, self.sesja = self.sesja, None
        self.stan = None
        self.sprawdz_o = float("inf")
        if s is not None:
            s.zamknij()  # także porzuca niezapisane punkty i kończy PFL w SARZE

    def pytaj(self, polecenie):
        assert self.sesja is not None
        self.sesja.wyslij(polecenie)
        tekst = self.sesja.linia()
        if tekst.startswith("ERR "):
            raise OdmowaMiksu(tekst[4:])
        return tekst

    def punkt(self, ustawiony=False):
        s = self.stan
        assert s is not None
        nazwa = self.t(NAZWY[s.punkt])
        if s.wartosc is None:
            return self.t("miks_nieustawione", punkt=nazwa)
        return self.t("miks_ustawione" if ustawiony else "miks_punkt", punkt=nazwa, czas=czas(s.wartosc))

    def pozycja(self):
        assert self.stan is not None
        return self.t("miks_pozycja", czas=czas(self.stan.pozycja))

    def wykonaj(self, polecenie, program=None, cicho=False):
        """Tekst albo None. Błąd transportu zamyka sesję, nigdy nie ponawia akcji."""
        bylo = self.aktywny
        try:
            if self.sesja is not None:
                # Limit całej OPERACJI zostaje 3 s. Nie ograniczamy życia sesji.
                self.sesja.termin = time.monotonic() + 3.0
            tekst = self._wykonaj(polecenie, program)
            return None if cicho else tekst
        except (WymagaSary, NiePolaczono):
            self.zamknij()
            return self.t("miks_utrata" if bylo else "miks_tylko_sara")
        except OdmowaMiksu as e:
            blad = str(e)
            klucz = {"busy": "miks_busy", "empty": "miks_empty", "pfl": "miks_pfl",
                     "session": "miks_session", "invalid|kolejnosc": "miks_kolejnosc",
                     "invalid|petla": "miks_petla", "nosession": "miks_utrata"}.get(blad)
            if not bylo or blad == "nosession" or klucz is None:
                self.zamknij()
            return self.t(klucz or "miks_niepotwierdzone")
        except BledneDaneMiksu:
            # SARA żyje, ale podała wartość, której nie wolno zgadywać (np. czas za końcem).
            log.exception("Błędna odpowiedź SARY na polecenie punktów miksu: %s", polecenie)
            self.zamknij()
            return self.t("miks_bledne_dane")
        except Exception:
            log.exception("Niepotwierdzone polecenie punktów miksu: %s", polecenie)
            self.zamknij()
            return self.t("miks_utrata" if bylo else "miks_niepotwierdzone")
        finally:
            if self.aktywny:
                self.sprawdz_o = time.monotonic() + 1.0

    def _wykonaj(self, polecenie, program):
        if polecenie == "przelacz":
            if self.aktywny:
                self.stan = StanMiksu.czytaj(self.pytaj("MixInfo"), self.dlugosc)
                if self.stan.zmiany:
                    return self.t("miks_niezapisane")
                polecenie = "MixCancel"
            else:
                if program is None:
                    raise WymagaSary
                self.sesja = program.polacz_miks()
                if not self.sesja.sara:  # niezależnie od nazwy wybranego adaptera
                    raise WymagaSary
                p = self.pytaj("MixOpen").split("|")
                if (len(p) != 6 or p[0] != "OK" or not re.fullmatch(r"[0-9]+", p[1])
                        or p[2] not in ("0", "1") or not re.fullmatch(r"[0-9]+", p[3])):
                    raise BladEmisji("nieprawidłowe MixOpen")
                self.dlugosc = int(p[3])
                self.stan = StanMiksu.czytaj(self.pytaj("MixInfo"), self.dlugosc)
                nazwa = self.t("emisja_artysta_tytul", artysta=p[4], tytul=p[5]) if p[4] else (
                    p[5] or self.t("emisja_bez_tytulu"))
                return self.t("miks_otwarte", utwor=nazwa, czas=czas(self.dlugosc, False), punkt=self.punkt())
        if not self.aktywny:
            return None  # zaległe klawisze po zamknięciu nie otwierają nowej sesji
        tekst = self.pytaj(polecenie)
        if polecenie == "MixCancel":
            if tekst != "OK":
                raise BladEmisji("niepotwierdzone MixCancel")
            self.zamknij()
            return self.t("miks_porzucone")
        if polecenie == "MixSave":
            if tekst == "OK|nie_gra":
                komunikat = self.t("miks_zapisano")
            elif tekst == "OK|brak_przejscia":
                komunikat = self.t("miks_zapisano_bez_przejscia")
            elif tekst == "OK|przejscie_teraz":
                komunikat = self.t("miks_przejscie_teraz")
            elif re.fullmatch(r"OK\|przejscie_za=[0-9]+", tekst):
                ms = int(tekst.split("=")[1])
                komunikat = self.t("miks_przejscie_za", czas=czas_slownie(ms / 1000, "mianownik") or self.t("emisja_zero_sekund"))
            else:
                raise BledneDaneMiksu("niepotwierdzone MixSave")
            self.zamknij()
            return komunikat
        self.stan = StanMiksu.czytaj(tekst, self.dlugosc)
        if polecenie == "MixInfo":
            return self.t("miks_info", pozycja=self.pozycja(), punkt=self.punkt())
        if polecenie.startswith(("MixPos=", "MixNudge=")):
            return None  # MIX_CISZA_ZMIAN: kółko, REWIND/FFWD, góra/dół bez czasu
        if polecenie == "MixSet":
            return self.t("miks_ustawione", punkt=self.t(NAZWY[self.stan.punkt]))
        if polecenie == "MixClear":
            return self.t("miks_usuniete", punkt=self.t(NAZWY[self.stan.punkt]))
        if polecenie in ("MixPlay", "MixPlayPoint", "MixPlayMix", "MixStop"):
            return self.t(ODSLUCHY[self.stan.odsluch])
        return self.punkt(ustawiony=polecenie == "MixSet")
