"""Losowe ciągi naciśnięć i awarii w modelu CUE: niezmienniki planu na stanie symulatora.

Testy przykładowe sprawdzają scenariusze z planu. Ten plik sprawdza to, czego
scenariusze nie pokrywają: dowolną kolejność CUE, przełącznika mikrofonu, F3,
suwaków (także trzymanych ręką), gałek, klawiszy odsłuchu i wolnych przycisków,
z przerwami łączności, gubionymi pakietami i zmianami z innego klienta. Po
każdym kroku sprawdzamy stan „miksera” (symulatora), a nie stan, który mostek
sam sobie zapisał (pomoc.TestZSymulatorem.naruszenia_miksera).

Ciągi są losowane z ustalonym ziarnem, więc wynik jest powtarzalny. Przy
błędzie komunikat podaje ziarno i cały ciąg, żeby dało się go odtworzyć.
Zmiany z innego klienta dotyczą suwaków oraz odciszenia/impulsu Bus 6 podczas
trzymanego talkbacku. Inne obce zmiany routingu mogą legalnie złamać niezmiennik
i nie należą do tego generatora. Mute-Act zmienia się między ziarnami.

Plan v21 i v22: ciągi zawierają też przycisk kaszlu (wciśnięcie, puszczenie,
zgubione puszczenie przy restarcie kontrolera), ciszę i brak mierników
oraz ruchy suwaków rozmówców z CUE. Po każdym kroku dodatkowo: Bus 5 zawiera
tylko źródła z tej samej rozmowy co słuchacz (pomoc.naruszenia_klucza),
kaszel nigdy nie otwiera anteny przy CUE, puszczenie po zgubionym puszczeniu
nie otwiera anteny, alarm ciszy nie pada przy braku mierników.

Tryby informacji zwrotnej (karta t_399b15a2): ciąg zaczyna się w trybie
mowa, dźwięki albo dźwięki z mową (według ziarna), a F4 i F5 są w puli
klawiszy. Po każdym kroku: żaden komunikat bezpieczeństwa nie poszedł bez
mowy, a komunikat bez mowy ma dźwięk.

Domyślnie krótko (20 ciągów po 40 kroków). Długie badanie:
    MOSTEK_LOSOWE=500 nice -n 10 python3 -B -m unittest test_losowe
"""

import os
import random
import unittest

from pomoc import TestZSymulatorem, sciezki
from mostek.informacja import KOLEJNOSC
from mostek.mowa import Priorytet

CIAGI = int(os.environ.get("MOSTEK_LOSOWE", "20"))
KROKI = 40

KLAWISZE = ("F1_mikrofon", "F2_status", "F3_koniec_rozmowy", "F4_tryb_informacji", "F5_ostatni_komunikat",
            "kursor_lewo_wolny",
            "kursor_prawo_wolny", "F8_odczytaj_powierzchnie", "glosniki_wlacz", "glosniki_wylacz",
            "sluchaj_programu", "sluchaj_rozmowy", "koniec_pfl")


class TestLosoweCiagi(TestZSymulatorem):
    def losuj_krok(self, los: random.Random):
        r = los.random()
        if r < 0.10:
            return ("klawisz", "F1_mikrofon")
        if r < 0.15:
            return ("klawisz", "F3_koniec_rozmowy")
        if r < 0.24:
            return ("klawisz", los.choice(KLAWISZE))
        if r < 0.42:
            return ("przycisk", los.choice((2, 3)), 3)           # CUE
        if r < 0.50:
            return ("przycisk", los.randint(1, 6), los.randint(0, 3))
        if r < 0.56:
            return ("galka", los.choice((2, 3)), los.choice((1, -1)))
        if r < 0.58:
            return ("galka_wcisnij", los.randint(1, 6))
        if r < 0.65:
            return ("ruch", 1, los.choice((0.0, 1 / 16383, 0.5, 1.0)), los.random() < 0.8)
        if r < 0.70:
            return ("ruch", los.randint(2, 6), los.choice((0.0, 0.1, 0.5, 1.0)), los.random() < 0.8)
        if r < 0.72:
            return ("tick",)
        if r < 0.73:
            return ("obce_solo", los.choice((9, 10, 7)), los.choice((0, 1)))
        if r < 0.76:
            return ("obce_glosniki", los.choice(("odcisz", "impuls")))
        if r < 0.80:
            return ("rozlacz",)
        if r < 0.85:
            return ("polacz",)
        if r < 0.89:
            return ("gub", los.randint(1, 3))
        if r < 0.92:
            return ("inny_suwak", los.choice((1, 3, 7, 9, 10)), los.choice((0.0, 0.3, 0.75)))
        if r < 0.95:
            return ("przycisk", los.choice((1, 2, 3)), 2)           # kaszel lub talkback
        if r < 0.97:
            return ("puszczenie", los.choice((1, 2, 3)), 2)         # kaszel lub talkback
        if r < 0.98:
            return ("kontroler", "restart")                        # zgubione puszczenie
        return (los.choice(("cisza", "dzwiek", "bez_miernikow", "z_miernikami")),)

    def wykonaj(self, krok) -> None:
        rodzaj = krok[0]
        if rodzaj == "klawisz":
            self.klawisz(krok[1])
        elif rodzaj in ("przycisk", "galka", "galka_wcisnij", "puszczenie", "kontroler"):
            self.nacisnij(*krok)
        elif rodzaj in ("cisza", "dzwiek"):
            self.sym.cisza(rodzaj == "cisza")
            self.tick(0.6)
        elif rodzaj in ("bez_miernikow", "z_miernikami"):
            self.sym.mierniki_wylaczone = rodzaj == "bez_miernikow"
            self.tick(0.6)
        elif rodzaj == "ruch":
            _, pasek, poz, pusc = krok
            self.nacisnij("dotyk", pasek, True)
            self.nacisnij("suwak", pasek, poz)
            if pusc:
                self.nacisnij("dotyk", pasek, False)
            self.tick(0.6)
        elif rodzaj == "tick":
            self.tick(0.6)
        elif rodzaj == "rozlacz":
            self.sym.awarie.rozlaczony = True
            self.tick(0.6)
        elif rodzaj == "polacz":
            self.sym.awarie.rozlaczony = False
            self.tick(1.5)
        elif rodzaj == "gub":
            self.sym.awarie.zgub_nastepne = krok[1]
        elif rodzaj == "obce_glosniki":
            # Poza talkbackiem obce ON mogłoby celowo złamać niezmiennik,
            # a nie testowałoby nowej ochrony trzymania.
            if self.r._talkback and not self.sym.awarie.rozlaczony:
                for v in ((1, 0) if krok[1] == "impuls" else (1,)):
                    self.transport.rozeslij(self.sym.zmien_z_innego(sciezki.mute_szyny(6), v))
                self.r.przetworz_zgloszenia()
        elif rodzaj == "obce_solo":
            if not self.sym.awarie.rozlaczony:
                self.inny(sciezki.solo(krok[1]), krok[2])
        elif rodzaj == "inny_suwak":
            if not self.sym.awarie.rozlaczony:
                kanaly = (krok[1], krok[1] + 1) if krok[1] in (1, 3, 7) else (krok[1],)
                for k in kanaly:
                    self.inny(sciezki.fader(k), krok[2])
        self.ostatnia_mowa = self.slowa()

    def test_losowe_ciagi_nie_lamia_niezmiennikow(self):
        self.tearDown()           # każdy ciąg ma własny, świeży symulator
        try:
            self._ciagi()
        finally:
            self.setUp()          # unittest sam wywoła tearDown

    def _ciagi(self) -> None:
        for ziarno in range(CIAGI):
            with self.subTest(ziarno=ziarno):
                self.setUp()
                try:
                    los = random.Random(ziarno)
                    historia = []
                    self.info.tryb = KOLEJNOSC[ziarno % len(KOLEJNOSC)]
                    self.u.zachowanie["odciszaj_glosniki_po_wylaczeniu_mikrofonu"] = bool(ziarno % 2)
                    bez_mowy = []
                    oryginal = self.mowa.powiedz

                    def zapisz(tekst, priorytet=Priorytet.STAN, klucz=None, dzwieki=(), mow=True,
                               zastepcza_mowa=True, _o=oryginal, _b=bez_mowy):
                        if not mow and (priorytet == Priorytet.BEZPIECZENSTWO or not dzwieki):
                            _b.append((str(tekst), priorytet.name, list(dzwieki)))
                        return _o(tekst, priorytet, klucz, dzwieki=dzwieki, mow=mow, zastepcza_mowa=zastepcza_mowa)

                    self.mowa.powiedz = zapisz
                    talkback_fizyczny, kaszel_fizyczny = set(), False
                    for _ in range(KROKI):
                        krok = self.losuj_krok(los)
                        historia.append(krok)
                        cue_przed = {r for r in ("telefon", "zoom") if self.cue_sym(r)}
                        mik_przed = self.m(sciezki.lr(9))
                        kaszel_przed = self.r._kaszel is not None or bool(self.r._talkback)
                        wartosci_przed = dict(self.sym.wartosci)
                        self.wykonaj(krok)
                        if self.sym.awarie.rozlaczony:
                            # Bez transportu nie da się wykonać zamknięcia. Nie
                            # udajemy, że wyzerowane flagi rdzenia zamknęły DSP.
                            self.assertEqual(self.sym.wartosci, wartosci_przed)
                        else:
                            talkback_fizyczny = set(self.r._talkback)
                            kaszel_fizyczny = self.r._kaszel is not None
                        zle = self.naruszenia_miksera(talkback_fizyczny, kaszel_fizyczny)
                        mik_po = self.m(sciezki.lr(9))
                        if talkback_fizyczny and not self.glosniki_wyciszone():
                            zle.append("talkback trzymany, a głośniki nie są wyciszone")
                        # Fader Start: przełącznik lub ręka kończy całe CUE.
                        start_mikrofonu = (krok in (("klawisz", "F1_mikrofon"), ("przycisk", 1, 3))
                                           or krok[0] == "ruch" and krok[1] == 1)
                        if start_mikrofonu and mik_po == 1 and any(self.cue_sym(r) for r in ("telefon", "zoom")):
                            zle.append("Fader Start zostawił CUE po otwarciu anteny")
                        # Decyzja 2: kaszel nie otwiera anteny przy CUE, a puszczenie
                        # bez trwającego kaszlu (np. po zgubionym puszczeniu) nic nie otwiera.
                        if krok[0] in ("puszczenie", "kontroler") and mik_przed == 0 and mik_po == 1 \
                                and (cue_przed or not kaszel_przed or krok[0] == "kontroler"):
                            zle.append("kaszel otworzył antenę bez prawa")
                        if krok == ("przycisk", 1, 2) and mik_po == 1 and mik_przed == 1 and not cue_przed \
                                and self.r._kaszel is not None:
                            zle.append("kaszel trwa, a mikrofon jest na antenie")
                        # Decyzja 4: brak mierników to nie cisza.
                        if self.sym.mierniki_wylaczone and "Cisza na antenie" in self.ostatnia_mowa \
                                and self.r.detektor.stan == "niedostepne":
                            zle.append("alarm ciszy przy braku mierników")
                        solo = self.r._solo_kaszlu
                        if solo is not None and not solo.obca_zmiana and not self.sym.awarie.rozlaczony:
                            if any(self.m(a) != 0 for a in solo.sprzed):
                                zle.append("kaszel przejął solo mikrofonu, ale go nie zdjął")
                        if krok in (("przycisk", 1, 2), ("puszczenie", 1, 2), ("kontroler", "restart")):
                            for a, v in wartosci_przed.items():
                                if a.startswith("/-stat/solosw/") and a != sciezki.solo(9) and self.m(a) != v:
                                    zle.append(f"kaszel zmienił cudze solo: {a}")
                        if bez_mowy:
                            zle.append(f"komunikat bezpieczeństwa albo bez dźwięku poszedł bez mowy: {bez_mowy}")
                        self.assertEqual(zle, [], f"ziarno {ziarno}, krok {len(historia)}: {historia}")
                finally:
                    self.tearDown()


if __name__ == "__main__":
    unittest.main()
