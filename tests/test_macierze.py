"""Sytuacje A-G z planu v20 (rozdz. 6) odczytane ze stanu symulatora i porównane
z macierzą planu v20 zapisaną niżej (PLAN).

Stan „kto co słyszy” liczy pomoc.TestZSymulatorem.slyszy() wprost z wartości
symulatora (poziom, punkt pobrania, suwak), a nie widokiem mostka.
"""

import json
import unittest
from pathlib import Path

from pomoc import TestZSymulatorem, sciezki


# Klucz przyciszania (plan v22, rozdz. 8, pkt 5; decyzja 5 z karty): kto jest
# w Bus 5 w każdej sytuacji. Mikrofon, gdy mikrofon i słuchacz są na antenie
# albo słuchacz ma CUE; Zoom, gdy Zoom i słuchacz są na antenie albo oboje mają CUE.
KLUCZ = {"A": set(), "B": set(), "C": {"mikrofon"}, "D": {"mikrofon"}, "E": {"mikrofon"},
         "F": {"mikrofon", "zoom"}, "G": {"mikrofon", "zoom"}}

# Kopia macierzy z planu v20, rozdz. 6, „Kto co słyszy” (zgodna z macierze-v20.json,
# sprawdza to test_plan_zgodny_z_macierze_v20). pfl: kanały w odsłuchu kontrolnym;
# prawe_ucho: podsłuch telefonu w Bus 2; glosniki_wyciszone: None = bez wymagania.
PLAN = {
    "A": {"antena": {"muzyka"}, "telefon": {"muzyka"}, "zoom": {"muzyka"},
          "pfl": set(), "prawe_ucho": True, "glosniki_wyciszone": None, "rec": True},
    "B": {"antena": {"mikrofon", "muzyka"}, "telefon": {"mikrofon", "muzyka"}, "zoom": {"mikrofon", "muzyka"},
          "pfl": set(), "prawe_ucho": True, "glosniki_wyciszone": True, "rec": True},
    "C": {"antena": {"muzyka"}, "telefon": {"mikrofon", "muzyka ciszej"}, "zoom": {"muzyka"},
          "pfl": {"mikrofon", "telefon"}, "prawe_ucho": False, "glosniki_wyciszone": True, "rec": False},
    "D": {"antena": {"mikrofon", "telefon", "muzyka"}, "telefon": {"mikrofon", "muzyka"},
          "zoom": {"mikrofon", "telefon", "muzyka"},
          "pfl": set(), "prawe_ucho": False, "glosniki_wyciszone": True, "rec": True},
    "E": {"antena": {"zoom", "muzyka"}, "telefon": {"mikrofon", "muzyka ciszej"}, "zoom": {"muzyka"},
          "pfl": {"mikrofon", "telefon"}, "prawe_ucho": False, "glosniki_wyciszone": True, "rec": False},
    "F": {"antena": {"muzyka"}, "telefon": {"mikrofon", "zoom", "muzyka ciszej"},
          "zoom": {"mikrofon", "telefon", "muzyka ciszej"},
          "pfl": {"mikrofon", "telefon", "zoom"}, "prawe_ucho": False, "glosniki_wyciszone": True, "rec": False},
    "G": {"antena": {"mikrofon", "telefon", "zoom", "muzyka"}, "telefon": {"mikrofon", "zoom", "muzyka"},
          "zoom": {"mikrofon", "telefon", "muzyka"},
          "pfl": set(), "prawe_ucho": False, "glosniki_wyciszone": True, "rec": True},
}


class TestMacierzeV20(TestZSymulatorem):
    def odczytaj(self) -> dict:
        return {"antena": self.antena(), "telefon": self.slyszy("telefon"), "zoom": self.slyszy("zoom"),
                "pfl": {z for z in ("mikrofon", "telefon", "zoom") if self.pfl(z)},
                "prawe_ucho": self.podsluch(), "glosniki_wyciszone": self.glosniki_wyciszone()}

    def sprawdz(self, nazwa: str) -> None:
        plan = PLAN[nazwa]
        m = self.odczytaj()
        for klucz in ("antena", "telefon", "zoom", "pfl", "prawe_ucho"):
            self.assertEqual(m[klucz], plan[klucz], f"sytuacja {nazwa}, {klucz}")
        if plan["glosniki_wyciszone"] is not None:
            self.assertEqual(m["glosniki_wyciszone"], plan["glosniki_wyciszone"], f"sytuacja {nazwa}, głośniki")
        self.assertEqual(self.w_kluczu(), KLUCZ[nazwa], f"sytuacja {nazwa}, klucz przyciszania (Bus 5)")
        self.assertEqual(self.naruszenia_klucza(), [], nazwa)
        if plan["pfl"]:
            self.assertEqual(self.m(sciezki.MONITOR_ZRODLO), sciezki.ZRODLO_LRPFL, nazwa)
            # Michał 22.10.2026: przyciszenie_pfl_cue_db = 0, rozmówcy w słuchawkach jak na antenie.
            self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0, f"{nazwa}: bez przyciszenia odsłuchu")
        else:
            self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0, f"{nazwa}: program bez przyciszenia")
        # Historyczna macierz opisuje tory, nie zachowanie F1. Osobny test
        # poniżej sprawdza Fader Start bez zmieniania stanu w tej asercji.

    def test_f1_konczy_cue_we_wszystkich_macierzach(self):
        for nazwa in ("C", "E", "F"):
            with self.subTest(sytuacja=nazwa):
                self.tearDown()
                self.setUp()
                self.do_sytuacji(nazwa)
                self.klawisz("F1_mikrofon")
                self.assertTrue(self.suma("mikrofon"))
                self.assertFalse(self.cue_sym("telefon"))
                self.assertFalse(self.cue_sym("zoom"))
                self.assertEqual(self.naruszenia_miksera(), [])

    # --- drogi do sytuacji ---------------------------------------------------
    def do_sytuacji(self, nazwa: str) -> None:
        if nazwa == "B":
            self.klawisz("F1_mikrofon")
        elif nazwa == "C":
            self.cue("telefon")
        elif nazwa == "D":
            self.klawisz("F1_mikrofon")
            self.ruch("telefon", 1.0)
        elif nazwa == "E":
            self.ruch("zoom", 1.0)
            self.cue("telefon")
        elif nazwa == "F":
            self.cue("telefon")
            self.cue("zoom")
        elif nazwa == "G":
            self.klawisz("F1_mikrofon")
            self.ruch("telefon", 1.0)
            self.ruch("zoom", 1.0)

    def test_kazda_sytuacja_ze_stanu_startowego(self):
        for nazwa in PLAN:
            with self.subTest(sytuacja=nazwa):
                self.tearDown()
                self.setUp()
                self.do_sytuacji(nazwa)
                self.sprawdz(nazwa)

    def test_nikt_nie_slyszy_siebie_w_zadnej_sytuacji(self):
        for nazwa in PLAN:
            with self.subTest(sytuacja=nazwa):
                self.tearDown()
                self.setUp()
                self.do_sytuacji(nazwa)
                self.assertNotIn("telefon", self.slyszy("telefon"))
                self.assertNotIn("zoom", self.slyszy("zoom"))

    def test_droga_przez_wszystkie_sytuacje(self):
        """A, B, D, G, potem E, F, C i z powrotem do A, bez wczytywania sceny."""
        self.sprawdz("A")
        self.klawisz("F1_mikrofon")
        self.sprawdz("B")
        self.ruch("telefon", 1.0)
        self.sprawdz("D")
        self.ruch("zoom", 1.0)
        self.sprawdz("G")
        self.klawisz("F1_mikrofon")
        self.ruch("telefon", 0.0)
        self.cue("telefon")              # mikrofon już poza anteną, Zoom prowadzi
        self.sprawdz("E")
        self.cue("zoom")                 # Zoom schodzi z anteny i dołącza
        self.assertEqual(self.pow.suwaki[3], 0.0, "silnik ściągnął suwak Zooma")
        self.sprawdz("F")
        self.cue("zoom")                 # Zoom czeka
        self.sprawdz("C")
        self.klawisz("F3_koniec_rozmowy")
        self.sprawdz("A")


if __name__ == "__main__":
    unittest.main()
