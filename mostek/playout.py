"""Niezależny tor playoutu: kolejka, wygładzenie jog i komunikaty z odczytu.

Nie ma dostępu do klienta MR18. Wątek nie woła rdzenia ani NVDA, odkłada
wyniki dla pętli rdzenia. STOP usuwa zaległą nawigację i starty; żadna akcja
nie jest automatycznie powtarzana po błędzie.
"""
from __future__ import annotations

from dataclasses import replace

from collections import deque
import logging
import queue
import re
import threading
import time

from .emisja import BledneDaneOdtwarzaczy, BrakProgramu, NiePolaczono, WymagaSary, WymagaTCP
from .liczniki import czas_slownie
from .miks import TrybMiksu, przesuniecie

log = logging.getLogger("mostek.playout")

# Komunikaty pozycji na playliście: nowy ucina poprzedni w NVDA (mowa.KolejkaMowy.PRZERYWALNE).
KURSOR = ("ruch", "utwor", "znacznik")


class TorEmisji:
    def __init__(self, ustawienia, program):
        self.u = ustawienia
        self.program = program  # funkcja: bieżący adapter, także po zmianie w teście
        self.wyniki = queue.SimpleQueue()
        self._warunek = threading.Condition()
        self._kolejka = deque()
        self._watek = None
        self._koniec = False
        self._zajety = False
        self._jog_termin = None
        self._jog_generacja = 0
        self._jog_program = None
        self._blad = None
        self._blad_czas = float("-inf")
        self.zwloka = float(self.u.emisja.get("jog_zwloka_s", 0.3))
        # Wołane z wątku playoutu zaraz po wyniku (rdzeń: odbierz_emisje), żeby
        # komunikat nie czekał do następnego obiegu pętli głównej (do 0,1 s).
        self.przy_wyniku = None
        self._hold_cel = None
        self._hold_wyslany = None
        self._hold_stan = None
        self._hold_program = None
        self._hold_odczyt_czas = float("-inf")
        self._hold_blad_czas = float("-inf")
        self.miks = TrybMiksu(ustawienia)
        self._miks_otwierany = False
        self._miks_jog_suma = 0
        self._miks_jog_termin = None
        self._miks_mowa_termin = None
        self._miks_generacja = 0
        self._miks_ostatni_jog = float("-inf")

    def zlec(self, akcja, kierunek=0, jog=False):
        with self._warunek:
            if self._koniec:
                return
            teraz = time.monotonic()
            if akcja == "miks_jog":
                krok = 1000 if teraz - self._miks_ostatni_jog < 0.08 else 100
                self._miks_ostatni_jog = teraz
                self._miks_jog_suma += int(kierunek) * krok  # MIX_SUMOWANIE
                if self._miks_jog_termin is None:
                    self._miks_jog_termin = teraz + 0.04
                # Decyzja Michała 25.10.2026: zmiana pozycji bez czytania czasu,
                # słychać tylko odsłuch PFL. Czas mówi F6 i wybór punktu.
                self._miks_mowa_termin = None  # MIX_CISZA_JOG
                self._miks_generacja += 1
                self._warunek.notify_all()
                return
            if akcja == "miks":
                self._miks_generacja += 1
                self._miks_mowa_termin = None
            hold = akcja in ("hold", "hold_odczyt")
            if hold and (not self.u.emisja.get("mikrofon_wstrzymuje_automat", True)
                         or self.program() is None):
                return
            if akcja == "hold":
                self._hold_program = self.program()
                self._hold_cel = bool(kierunek)
                self._hold_wyslany = bool(kierunek)
                self._hold_odczyt_czas = teraz
                self._kolejka = deque(z for z in self._kolejka if z[0] not in ("hold", "hold_odczyt"))
            if akcja in ("stop", "instant"):
                self._kolejka = deque(z for z in self._kolejka if z[0] == "hold")
                self._jog_termin = None
                self._jog_generacja += 1
                self._porzuc_miks_jog()
            if akcja != "hold" and len(self._kolejka) >= 128:
                if akcja != "hold_odczyt":
                    self._komunikat_bledu("emisja_kolejka_pelna")
                return
            if hold:
                pass  # Hold nie kasuje oczekującego końcowego odczytu jog.
            elif jog:
                self._jog_generacja += 1
                self._jog_termin = teraz + self.zwloka
            else:
                self._jog_termin = None
                self._jog_generacja += 1
            zadanie = (akcja, kierunek, jog, teraz)
            if akcja == "hold":
                self._kolejka.appendleft(zadanie)  # HOLD_PIERWSZENSTWO
            elif akcja == "hold_odczyt":
                if any(z[0] in ("hold", "hold_odczyt") for z in self._kolejka):
                    return
                self._kolejka.append(zadanie)
            else:
                # Odczyt wstrzymania zawsze za klawiszami, również nowymi.
                indeks = next((i for i, z in enumerate(self._kolejka) if z[0] == "hold_odczyt"), len(self._kolejka))
                self._kolejka.insert(indeks, zadanie)
            if self._watek is None:
                self._watek = threading.Thread(target=self._petla, name="playout", daemon=True)
                self._watek.start()
            self._warunek.notify_all()

    @property
    def tryb_miksu(self):
        with self._warunek:
            return self._miks_otwierany or self.miks.aktywny or any(
                z[0] == "miks" and z[1] == "przelacz" for z in self._kolejka)

    def akcja_miksu(self, zdarzenie):
        """Krótka kwalifikacja zdarzenia, bez TCP i bez blokady MR18."""
        if zdarzenie[0] == "jog" and self.tryb_miksu:  # MIX_JOG_BEZ_KURSORA
            return "miks_jog", int(zdarzenie[1])
        if zdarzenie[0] != "klawisz":
            return None
        mapa = self.u.xtouch.get("punkty_miksu", {})
        polecenie = mapa.get(zdarzenie[1])
        if polecenie == "przelacz" or (polecenie and self.tryb_miksu):
            return "miks", polecenie
        return None  # MIX_ANTENA_BEZ_ZMIAN

    def _zabierz_miks_jog(self, teraz):
        suma = self._miks_jog_suma
        self._miks_jog_suma = 0
        self._miks_jog_termin = None
        return ("miks", "MixPos=" + przesuniecie(suma), True, teraz)

    def _porzuc_miks_jog(self):
        self._miks_jog_suma = 0
        self._miks_jog_termin = self._miks_mowa_termin = None
        self._miks_ostatni_jog = float("-inf")
        self._miks_generacja += 1

    def _wykonaj_miks(self, akcja, polecenie, jog, generacja):
        tekst = self.miks.wykonaj(polecenie, self.program(), cicho=jog or akcja != "miks")
        with self._warunek:
            self._miks_otwierany = False
            if akcja == "miks_mowa" and self.miks.aktywny and tekst is None:
                if generacja == self._miks_generacja:
                    tekst = self.miks.pozycja()
            if not self.miks.aktywny:
                self._porzuc_miks_jog()
                # Odrzuć tylko polecenia zamkniętej sesji, nigdy antenę/Hold.
                self._kolejka = deque(z for z in self._kolejka if z[0] != "miks")
            if tekst is not None:
                self.wyniki.put((tekst, False, "emisja-miks"))

    def obserwuj_hold(self, aktywne):
        """Nieblokująca synchronizacja z odczytem MR18. None oznacza NIEZNANY.

        Hold jest bezsesyjne. Lekki odczyt także przy zamkniętym mikrofonie
        wykrywa start/restart SARY bez klawisza transportu. Nigdy nie sonduje SPL.
        """
        if aktywne is None or not self.u.emisja.get("mikrofon_wstrzymuje_automat", True):
            return
        with self._warunek:
            teraz = time.monotonic()
            program = self.program()
            zmiana_programu = program is not self._hold_program
            self._hold_program = program
            if zmiana_programu:
                self._hold_wyslany = None
                self._hold_stan = None
            if aktywne != self._hold_cel or zmiana_programu:
                self.zlec("hold", int(aktywne))
            elif teraz - self._hold_odczyt_czas >= 1.0:
                self._hold_odczyt_czas = teraz
                self.zlec("hold" if self._hold_wyslany is None else "hold_odczyt", int(aktywne))

    def _wykonaj_hold(self, akcja, kierunek):
        if not self.u.emisja.get("mikrofon_wstrzymuje_automat", True):
            return
        try:
            program = self.program()
            wynik = program.wykonaj(akcja, kierunek) if program is not None else None
            if wynik is None:
                self._hold_stan = None
                return  # brak wybranego programu albo SPL: bez komunikatu
            with self._warunek:
                # Stary wynik po zmianie mikrofonu nie może potwierdzić nowego.
                if bool(kierunek) != self._hold_cel:
                    return
                if wynik.aktywne != self._hold_cel or (akcja == "hold_odczyt" and self._hold_stan is None):
                    self._hold_wyslany = None
                    self.zlec("hold", int(self._hold_cel))
                    return
                poprzedni = self._hold_stan
                self._hold_wyslany = wynik.aktywne
                self._hold_stan = wynik
            klucz = None
            if wynik.aktywne:
                if wynik.stan == "zatrzymane" and (poprzedni is None or poprzedni.stan != "zatrzymane"):
                    klucz = "emisja_automat_zatrzymane"
                elif wynik.stan == "za_pozno" and (poprzedni is None or poprzedni.stan != "za_pozno"):
                    klucz = "emisja_automat_za_pozno"
                elif (wynik.stan in ("trzyma", "brak") and
                      (poprzedni is None or not poprzedni.aktywne)):
                    klucz = "emisja_automat_wstrzymany"
            elif poprzedni is not None and poprzedni.aktywne:
                klucz = ("emisja_automat_zwolniony_zatrzymane" if
                         wynik.stan == "zatrzymane" or poprzedni.stan == "zatrzymane" else
                         "emisja_automat_zwolniony")
            if klucz:
                log.info("Hold potwierdzone: %s, %s", wynik, klucz)
                self.wyniki.put((self.u.tekst(klucz), klucz != "emisja_automat_za_pozno", "emisja-hold"))
        except NiePolaczono:
            # SARA zamknięta: nie gra, więc nie ma czego wstrzymywać i nie ma
            # alarmu (główna 24.10.2026: alarm co 5 s przy wyłączonym mikrofonie).
            # Następna próba za ok. 5 s albo od razu przy zmianie mikrofonu:
            # połączenie do zamkniętego portu na stanowisku blokuje tor na 0,5 s.
            with self._warunek:
                self._hold_wyslany = None
                self._hold_stan = None
                self._hold_odczyt_czas = time.monotonic() + 4.0
            log.debug("Hold: SARA nie przyjmuje połączeń", exc_info=True)
        except Exception:
            with self._warunek:
                self._hold_wyslany = None
            # Nieznany efekt operacji. Ponawiamy tylko idempotentne Hold,
            # zgodnie z następnym znanym odczytem mikrofonu, najwcześniej za 1 s.
            teraz = time.monotonic()
            if teraz - self._hold_blad_czas >= 5.0:
                self._hold_blad_czas = teraz
                self.wyniki.put((self.u.tekst("emisja_automat_blad"), False, "emisja-hold-blad"))
            log.debug("Brak potwierdzenia Hold", exc_info=True)

    def _komunikat_bledu(self, klucz, **parametry):
        teraz = time.monotonic()
        if self._blad != klucz or teraz - self._blad_czas >= 5.0:
            self.wyniki.put((self.u.tekst(klucz, **parametry), False, "emisja"))
            self._blad = klucz
            self._blad_czas = teraz

    def _petla(self):
        while True:
            zadanie = None
            generacja = -1
            with self._warunek:
                while not self._koniec:
                    teraz = time.monotonic()
                    if self._kolejka:
                        if self.miks.aktywny and self._kolejka[0][0] == "miks" and self._miks_jog_termin is not None:
                            zadanie = self._zabierz_miks_jog(teraz)
                        else:
                            zadanie = self._kolejka.popleft()
                            if zadanie[:2] == ("miks", "przelacz"):
                                self._miks_otwierany = True
                        break
                    if self._miks_jog_termin is not None and teraz >= self._miks_jog_termin:
                        zadanie = self._zabierz_miks_jog(teraz)
                        break
                    if self._miks_mowa_termin is not None and teraz >= self._miks_mowa_termin:
                        zadanie = ("miks_mowa", "MixInfo", False, teraz)
                        generacja = self._miks_generacja
                        self._miks_mowa_termin = None
                        break
                    if self.miks.aktywny and teraz >= self.miks.sprawdz_o:
                        zadanie = ("miks_ping", "MixInfo", False, teraz)
                        break
                    if self._jog_termin is not None and teraz >= self._jog_termin:
                        zadanie = ("utwor", 0, False, teraz)
                        generacja = self._jog_generacja
                        self._jog_termin = None
                        break
                    terminy = [t for t in (self._jog_termin, self._miks_jog_termin,
                               self._miks_mowa_termin, self.miks.sprawdz_o if self.miks.aktywny else None) if t is not None]
                    self._warunek.wait(max(0, min(terminy) - teraz) if terminy else None)
                if self._koniec:
                    return
                self._zajety = True
            assert zadanie is not None
            akcja, kierunek, jog, zlecono = zadanie
            try:
                if akcja in ("hold", "hold_odczyt"):
                    self._wykonaj_hold(akcja, kierunek)
                    continue
                if akcja not in ("stop", "instant") and time.monotonic() - zlecono > 2.0:
                    self._przerwij_jog()
                    self._komunikat_bledu("emisja_polecenie_przeterminowane")
                    continue
                if akcja in ("miks", "miks_mowa", "miks_ping"):
                    self._wykonaj_miks(akcja, kierunek, jog, generacja)
                    continue
                # Końcowy odczyt jog od tego samego adaptera, nie od nowo wykrytego programu.
                program = self._jog_program if akcja == "utwor" else self.program()
                if program is None:
                    self._przerwij_jog()
                    self._komunikat_bledu("emisja_nie_wybrano")
                    continue
                wynik = program.wykonaj(akcja, kierunek)
                self._blad = None
                if jog:
                    self._jog_program = getattr(program, "wybrany", program)
                else:
                    with self._warunek:
                        if akcja == "utwor" and generacja != self._jog_generacja:
                            continue  # kolejny ruch podczas odczytu: nie mów starej pozycji
                        if akcja == "ruch" and any(z[0] in KURSOR for z in self._kolejka):
                            continue  # kolejne naciśnięcie już czeka: mów tylko ostatnią pozycję
                    klucz = "emisja-kursor" if akcja in KURSOR else "emisja"
                    self.wyniki.put((self.opisz(akcja, wynik), akcja in ("play", "stop", "instant", "stan"), klucz))
            except BledneDaneOdtwarzaczy:
                self._przerwij_jog()
                self._komunikat_bledu("emisja_odtwarzacz_bledne_dane")
            except WymagaSary:
                self._przerwij_jog()
                self._komunikat_bledu("emisja_odtwarzacz_spl")
            except WymagaTCP:
                self._przerwij_jog()
                self._komunikat_bledu("emisja_wymaga_tcp")
            except BrakProgramu:
                self._przerwij_jog()
                self._komunikat_bledu("emisja_nie_znaleziono")
            except Exception:
                self._przerwij_jog()
                log.exception("Niepotwierdzona operacja playoutu: %s", akcja)
                self._komunikat_bledu("emisja_niepotwierdzona")
            finally:
                with self._warunek:
                    self._zajety = False
                    self._miks_otwierany = False
                    self._warunek.notify_all()
                self._oddaj()

    def _oddaj(self):
        if self.przy_wyniku is not None and not self.wyniki.empty():
            try:
                self.przy_wyniku()
            except Exception:  # noqa: BLE001 - mowa nie może zatrzymać toru playoutu
                log.exception("przekazanie wyniku playoutu do mowy")

    def _przerwij_jog(self):
        with self._warunek:
            self._jog_termin = None
            self._jog_program = None
            self._jog_generacja += 1

    def opisz(self, akcja, wynik):
        t = self.u.tekst
        if akcja == "odtwarzacz":
            numery = wynik.odtwarzacze
            if not numery:
                return t("emisja_nic_nie_gra")
            if len(numery) == 1:
                return t("emisja_odtwarzacz", numer=numery[0])
            lista = ", ".join(str(n) for n in numery[:-1]) + t("emisja_odtwarzacze_spojnik") + str(numery[-1])
            return t("emisja_odtwarzacze", lista=lista)

        def _nazwa(tekst):
            # This/Next przychodzą jako „artysta - tytuł”. Michał 24.10.2026:
            # przecinek zamiast myślnika (NVDA czyta myślnik różnie).
            # SPL 6.20 dokleja do Next czas „(04:41)” (pomiar 24.10.2026):
            # mówimy go jak czas utworu na liście, „4:41”.
            m = re.fullmatch(r"(.*?)\s*\((\d{1,3}):(\d{2})\)", tekst or "")
            if m:
                tekst = f"{m[1]}, {int(m[2])}:{m[3]}"
            if " - " in (tekst or ""):
                artysta, tytul = tekst.split(" - ", 1)
                return t("emisja_artysta_tytul", artysta=artysta, tytul=tytul)
            return tekst

        wynik = replace(wynik, teraz=_nazwa(wynik.teraz), nastepny=_nazwa(wynik.nastepny))
        if akcja == "nastepny":
            if wynik.stan == "gra":
                return t("emisja_gra_utwor", utwor=wynik.teraz or t("emisja_bez_tytulu"))
            return t("emisja_pauza" if wynik.stan == "pauza" else "emisja_nic_nie_gra")
        if akcja == "pozostalo":
            if wynik.stan != "gra":
                return t("emisja_pauza" if wynik.stan == "pauza" else "emisja_nic_nie_gra")
            czas = czas_slownie(wynik.pozostalo_ms / 1000, "mianownik") or t("emisja_zero_sekund")
            return t("emisja_pozostalo", czas=czas)
        if akcja == "co_gra":
            if wynik.stan == "gra":
                czas = czas_slownie(wynik.pozostalo_ms / 1000, "mianownik") or t("emisja_zero_sekund")
                tekst = t("emisja_co_gra", utwor=wynik.teraz or t("emisja_bez_tytulu"), czas=czas)
            elif wynik.stan == "pauza":
                tekst = t("emisja_pauza_utworu", utwor=wynik.teraz or t("emisja_bez_tytulu"))
            else:
                tekst = t("emisja_nic_nie_gra")
            if wynik.nastepny:
                tekst += ". " + t("emisja_nastepny", utwor=wynik.nastepny)
            return tekst
        if akcja == "automat":
            return t("emisja_automat_wlaczony" if wynik.automat else "emisja_automat_wylaczony")
        if akcja in ("ruch", "utwor", "znacznik"):
            u = wynik.utwor
            if u is None:
                return t("emisja_brak_utworu")
            nazwa = t("emisja_artysta_tytul", artysta=u.artysta, tytul=u.tytul) if u.artysta else (
                u.tytul or t("emisja_bez_tytulu"))
            if wynik.stan in ("gra", "pauza") and self.u.emisja.get("krotko_gdy_gra", True):
                # Michał, 24.10.2026: gdy coś gra, sam artysta i tytuł. Po
                # przełączeniu znacznika zostaje jego stan, bo o niego chodzi.
                if akcja == "znacznik":
                    if u.zaznaczony is not None:
                        return nazwa + ", " + t("emisja_zaznaczony" if u.zaznaczony else "emisja_niezaznaczony")
                    if wynik.znacznik_przelaczony:
                        return nazwa + ", " + t("emisja_znacznik_przelaczony")
                return nazwa
            # SARA: pierwszy utwór mówi „1”, w protokole to indeks 0.
            # SPL: 0 pozostaje znacznikiem godziny, pierwszy utwór ma indeks 1.
            tekst = t("emisja_utwor", numer=u.indeks if u.numer is None else u.numer, utwor=nazwa, czas=u.czas)
            if u.zaznaczony is not None:
                tekst += ", " + t("emisja_zaznaczony" if u.zaznaczony else "emisja_niezaznaczony")
            if u.status in ("playing", "paused", "played"):
                tekst += ", " + t({"playing": "emisja_utwor_gra", "paused": "emisja_utwor_pauza",
                                    "played": "emisja_utwor_zagrany"}[u.status])
            if u.przerwa:
                tekst += ", " + t("emisja_przerwa_po")
            if akcja == "znacznik" and wynik.znacznik_przelaczony and u.zaznaczony is None:
                tekst += ", " + t("emisja_znacznik_przelaczony")
            return tekst
        return t({"gra": "emisja_gra", "pauza": "emisja_pauza"}.get(wynik.stan, "emisja_stop"))

    def czekaj(self, limit=5.0):
        """Bariera do testów i kontrolowanego zamknięcia, nigdy w pętli stołu."""
        with self._warunek:
            return self._warunek.wait_for(
                lambda: not self._kolejka and not self._zajety and self._jog_termin is None
                and self._miks_jog_termin is None and self._miks_mowa_termin is None, limit)

    def zamknij(self):
        with self._warunek:
            self._koniec = True
            self._kolejka.clear()
            self._jog_termin = None
            self._warunek.notify_all()
        if self._watek:
            # Operacja sieciowa ma 3 s; wykrywanie dwóch programów najwyżej 1 s.
            self._watek.join(timeout=4.5)
        self.miks.zamknij()
