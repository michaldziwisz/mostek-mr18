"""Tryby informacji zwrotnej (mowa, dźwięki, dźwięki z mową), F4, F5, odtwarzanie
dźwięków i ponowne otwarcie portu MIDI (decyzja Michała z 17.10.2026).

Oracle: to, co powiedziała atrapa NVDA, lista kluczy odtworzonych przez atrapę
dźwięków i wartości w symulatorze („mikser”), nie stan, który mostek sam
sobie zapisał.
"""

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from pomoc import KATALOG, TestZSymulatorem, sciezki, wczytaj_ustawienia
from mostek import informacja as inf
from mostek import ustawienia
from mostek.informacja import (KOMUNIKATY_DZWIEKIEM, AtrapaDzwiekow, InformacjaZwrotna, Komunikat,
                               OdtwarzaczWinsound, Tryb)
from mostek.mowa import AtrapaMowy, KolejkaMowy, Priorytet
from mostek.rdzen import Rdzen
from mostek.xtouch import AtrapaPortuMIDI, BrakMIDI, MapaMC, PowierzchniaXTouch

NUTA_F1 = 54
TRYB_TEKST = {Tryb.MOWA: "Tryb: mowa", Tryb.DZWIEKI: "Tryb: dźwięki",
              Tryb.DZWIEKI_Z_MOWA: "Tryb: dźwięki z mową"}

# Komunikaty, które według zlecenia ZAWSZE mają mowę: ostrzeżenia i odmowy,
# liczby i liczniki, status F2, gałka, kontroler, profil, ochronne zamknięcia,
# błędy. Lista niezależna od kodu (informacja.KOMUNIKATY_DZWIEKIEM).
ZAWSZE_MOWA = (
    "mikrofon_nie_wlaczony", "mikrofon_moze_byc_wlaczony", "moze_byc_wlaczony", "stan_nieznany_wylaczam_mikrofon",
    "stan_nieznany_zamykam_rozmowe", "utrata_lacznosci", "powrot_lacznosci", "stan_nieznany",
    "z_innego_urzadzenia", "scena_z_innego", "profil_zmieniony", "najpierw_zwolnij_cue", "suwak_trzymany",
    "rozmowca_czeka_poza_suma", "rozmowca_poza_suma", "rozmowca_moze_byc_na_antenie", "przejscie_niepelne",
    "przejscie_przerwane_obce", "odsluch_niepotwierdzony", "granica_wzmocnienia", "wzmocnienie",
    "glosniki_odrzucone", "glosniki_moga_grac", "profil_niezgodny", "pary_rozbiezne", "licznik",
    "mikrofon_licznik", "mikrofon_kaszel", "kaszel_bez_anteny", "kaszel_przerwany", "cisza_na_antenie",
    "mierniki_niedostepne", "kontroler_utracony", "kontroler_powrot", "kontroler_otwieranie",
    "kontroler_odlaczony", "glosniki_odrzucone_profil", "glosniki_odrzucone_nieznany",
    "glosniki_odrzucone_kontroler", "status_profil", "profil_zgodny", "ochronne_zamkniecie",
    "ochronne_zamkniecie_niepotwierdzone", "emisja_nie_odpowiada", "sterowanie_nie_odpowiada",
    "synchronizacja_brak", "suwak_na_dole", "suwak_db", "tryb_niezapisany", "brak_powtorzenia",
)


class ZTrybem(TestZSymulatorem):
    """Mostek z symulatorem w zadanym trybie informacji zwrotnej."""

    tryb = Tryb.DZWIEKI

    def setUp(self) -> None:
        super().setUp()
        self.info.tryb = self.tryb

    def nowy_rdzen(self, u=None, odtwarzacz=None):
        """Restart mostka na tym samym symulatorze (ten sam plik trybu)."""
        u = u or self.u
        self.dzwieki = odtwarzacz or AtrapaDzwiekow()
        self.info = InformacjaZwrotna(u, self.dzwieki)
        self.mowa = KolejkaMowy(self.wyjscie, alarm=None, dzwieki=self.info)
        self.r = Rdzen(u, self.klient, self.mowa, powierzchnia=self.pow, zegar=self.zegar, sen=self.zegar.sen)
        self.assertTrue(self.r.synchronizuj(nowa_baza_galek=True))
        self.slowa()
        return self.r


# =============================================================================
# 1. Trzy tryby, tryb domyślny i trwały zapis
# =============================================================================
class TestTrybZapis(TestZSymulatorem):
    def test_domyslny_dzwieki_z_mowa(self):
        self.assertFalse(self.u.plik_trybu.exists())
        self.assertIs(InformacjaZwrotna(self.u, AtrapaDzwiekow()).tryb, Tryb.DZWIEKI_Z_MOWA)
        self.assertIs(inf.DOMYSLNY, Tryb.DZWIEKI_Z_MOWA)

    def test_domyslny_plik_trybu_poza_repozytorium_w_gitignore(self):
        u = ustawienia.wczytaj()
        self.assertEqual(u.plik_trybu, KATALOG / "ustawienia" / "tryb_informacji.json")
        self.assertIn("/ustawienia/tryb_informacji.json", (KATALOG / ".gitignore").read_text(encoding="utf-8"))

    def test_tryb_przezywa_restart(self):
        self.klawisz("F4_tryb_informacji")              # dźwięki z mową -> mowa
        self.assertEqual(self.slowa(), ["Tryb: mowa"])
        self.klawisz("F4_tryb_informacji")              # mowa -> dźwięki
        self.assertEqual(self.slowa(), ["Tryb: dźwięki"])
        self.assertEqual(json.loads(self.u.plik_trybu.read_text(encoding="utf-8")), {"tryb": "dzwieki"})
        nowa = InformacjaZwrotna(self.u, AtrapaDzwiekow())
        self.assertIs(nowa.tryb, Tryb.DZWIEKI, "tryb wczytany po restarcie")

    def test_zapis_atomowy_bez_pliku_tymczasowego(self):
        self.klawisz("F4_tryb_informacji")
        pliki = sorted(p.name for p in self.u.plik_trybu.parent.iterdir() if p.name.startswith("tryb_"))
        self.assertEqual(pliki, ["tryb_informacji.json"])

    def test_nieudany_zapis_nie_psuje_starego_pliku(self):
        self.klawisz("F4_tryb_informacji")              # mowa, zapisany
        self.slowa()
        przed = self.u.plik_trybu.read_text(encoding="utf-8")
        with mock.patch("mostek.informacja.os.replace", side_effect=OSError("dysk pełny")):
            with self.assertLogs("mostek.informacja", logging.WARNING):
                self.klawisz("F4_tryb_informacji")
        self.assertEqual(self.slowa(), ["Tryb: dźwięki. Trybu nie zapisano, po restarcie wróci poprzedni"])
        self.assertEqual(self.u.plik_trybu.read_text(encoding="utf-8"), przed, "stary zapis nietknięty")

    def _wczytaj_z(self, tresc: str):
        self.u.plik_trybu.write_text(tresc, encoding="utf-8")
        with self.assertLogs("mostek.informacja", logging.WARNING) as logi:
            tryb = InformacjaZwrotna(self.u, AtrapaDzwiekow()).tryb
        self.assertEqual(len([r for r in logi.records if "tryb" in r.getMessage()]), 1, logi.output)
        return tryb

    def test_uszkodzony_plik_to_domyslny_z_ostrzezeniem(self):
        self.assertIs(self._wczytaj_z("{nie json"), Tryb.DZWIEKI_Z_MOWA)

    def test_nieznany_tryb_to_domyslny_z_ostrzezeniem(self):
        self.assertIs(self._wczytaj_z('{"tryb": "gwizdki"}'), Tryb.DZWIEKI_Z_MOWA)
        self.assertIs(self._wczytaj_z('["dzwieki"]'), Tryb.DZWIEKI_Z_MOWA)

    def test_mapowanie_w_ustawieniach_nie_w_kodzie(self):
        dane = json.loads(ustawienia.DOMYSLNE_USTAWIENIA.read_text(encoding="utf-8"))
        zd = dane["informacja_zwrotna"]["zdarzenia"]
        self.assertEqual(zd["mikrofon_stan:wlaczony"], "mikrofon_na_antenie")
        kod = (KATALOG / "mostek" / "informacja.py").read_text(encoding="utf-8")
        self.assertNotIn("mikrofon_na_antenie", kod, "klucze dźwięków tylko w ustawieniach")
        # Zmiana mapowania w pliku zmienia dźwięk bez zmiany kodu.
        self.u.informacja = dict(self.u.informacja, zdarzenia=dict(zd, **{"mikrofon_stan:wlaczony": "alarm"}))
        info = InformacjaZwrotna(self.u, AtrapaDzwiekow())
        self.assertEqual(info.plan(("mikrofon_stan:wlaczony",), Priorytet.STAN, Tryb.DZWIEKI), (["alarm"], False))

    def test_ustawienia_odrzucaja_zdarzenie_bez_komunikatu(self):
        dane = json.loads(ustawienia.DOMYSLNE_USTAWIENIA.read_text(encoding="utf-8"))
        dane["informacja_zwrotna"]["zdarzenia"]["nie_ma_takiego"] = "alarm"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(dane), encoding="utf-8")
            with self.assertRaises(ustawienia.BladUstawien):
                ustawienia.wczytaj(p, ustawienia.DOMYSLNE_POZIOMY)

    def test_ustawienia_odrzucaja_zly_okres_ponowienia_portu(self):
        dane = json.loads(ustawienia.DOMYSLNE_USTAWIENIA.read_text(encoding="utf-8"))
        dane["xtouch"]["ponowienie_portu_s"] = 0
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(dane), encoding="utf-8")
            with self.assertRaises(ustawienia.BladUstawien):
                ustawienia.wczytaj(p, ustawienia.DOMYSLNE_POZIOMY)

    def test_dzwieki_skopiowane_do_mostka(self):
        katalog = KATALOG / "dzwieki"
        opis = json.loads((katalog / "dzwieki.json").read_text(encoding="utf-8"))
        self.assertEqual(len(opis), 22)
        for klucz, d in opis.items():
            with self.subTest(dzwiek=klucz):
                self.assertTrue((katalog / d["plik"]).is_file())
        info = InformacjaZwrotna(ustawienia.wczytaj(), AtrapaDzwiekow())
        uzyte = {k for v in info.mapa.values() for k in v}
        self.assertLessEqual(uzyte, set(opis), "mapowanie używa tylko istniejących dźwięków")


# =============================================================================
# 2. Komunikaty stanu w trzech trybach
# =============================================================================
class TestTrybDzwieki(ZTrybem):
    tryb = Tryb.DZWIEKI

    def test_mikrofon_tylko_dzwiekiem(self):
        self.klawisz("F1_mikrofon")
        self.assertTrue(self.suma("mikrofon"))
        self.assertEqual(self.dzwieki_i_slowa(), (["mikrofon_na_antenie"], []))
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), (["mikrofon_poza_antena", "glosniki_graja"], []))

    def test_cue_i_zwolnienie_tylko_dzwiekiem(self):
        self.cue("telefon")
        self.assertEqual(self.dzwieki_i_slowa(), (["sluchacz_cue"], []))
        self.cue("zoom")
        self.assertEqual(self.dzwieki_i_slowa(), (["zoom_cue"], []))
        self.cue("zoom")
        self.assertEqual(self.dzwieki_i_slowa(), (["zoom_czeka"], []))
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(self.dzwieki_i_slowa(), (["sluchacz_czeka", "zoom_czeka", "glosniki_graja"], []))

    def test_mikrofon_poza_antena_rozmowa_dwa_dzwieki(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.cue("telefon")
        self.assertEqual(self.dzwieki_i_slowa(), (["mikrofon_poza_antena", "sluchacz_cue"], []))

    def test_wejscie_na_antene_suwakiem(self):
        self.cue("telefon")
        self.cue("telefon")
        self.slowa()
        self.ruch("telefon", 1.0)
        self.assertEqual(self.dzwieki_i_slowa(), (["sluchacz_na_antenie"], []))

    def test_glosniki(self):
        self.klawisz("glosniki_wylacz")
        self.assertEqual(self.dzwieki_i_slowa(), (["glosniki_wyciszone"], []))
        self.klawisz("glosniki_wlacz")
        self.assertEqual(self.dzwieki_i_slowa(), (["glosniki_graja"], []))

    def test_odmowa_dzwiek_i_mowa_z_powodem(self):
        self.cue("telefon")
        self.slowa()
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), (["odmowa"], ["Rozmowa poza anteną, najpierw zwolnij CUE"]))

    def test_ostrzezenie_alarm_i_mowa(self):
        self.sym.awarie.rozlaczony = True
        self.tick()
        d, s = self.dzwieki_i_slowa()
        self.assertIn("alarm", d)
        self.assertIn("Brak łączności z mikserem, stan mikrofonu nieznany", s)
        self.sym.awarie.rozlaczony = False
        self.tick(1.5)
        d, s = self.dzwieki_i_slowa()
        self.assertTrue(any(t.startswith("Łączność z mikserem przywrócona") for t in s), s)
        self.assertNotIn("alarm", d, "dobra wiadomość bez dźwięku alarmu")

    def test_status_f2_zawsze_mowa(self):
        self.klawisz("F2_status")
        d, s = self.dzwieki_i_slowa()
        self.assertEqual(s, ["Mikrofon wyłączony. Słuchacz czeka. Zoom czeka. Głośniki włączone."])
        self.assertEqual(d, [])
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.klawisz("F2_status")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Mikrofon włączony. Słuchacz czeka. Zoom czeka. Głośniki wyciszone."]))

    def test_galka_zawsze_mowa(self):
        self.nacisnij("galka", 2, 1)
        self.tick(0.6)
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Telefon, wzmocnienie plus 1"]))
        self.nacisnij("galka_wcisnij", 2)
        d, s = self.dzwieki_i_slowa()
        self.assertEqual(len(s), 1)
        self.assertIn("wzmocnienie plus 1", s[0])

    def test_kontroler_utrata_i_powrot_zawsze_mowa(self):
        self.nacisnij("kontroler", "restart X-TOUCH")
        self.assertEqual(self.dzwieki_i_slowa(), (["alarm"], ["Kontroler odłączony, stół tylko zamyka tory"]))
        self.nacisnij("kontroler_powrot", "port MIDI otwarty")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Kontroler podłączony, suwaki według miksera"]))

    def test_profil_niezgodny_i_ochronne_zamkniecie_zawsze_mowa(self):
        self.inny(sciezki.szyna_lr(5), 1)
        d, s = self.dzwieki_i_slowa()
        self.assertTrue(any(t.startswith("Profil miksera niezgodny") for t in s), s)
        self.assertTrue(any(t.startswith("Ochronne zamknięcie") for t in s), s)
        self.assertIn("alarm", d)

    def test_zmiana_z_innego_urzadzenia_zawsze_mowa(self):
        self.inny(sciezki.lr(9), 1)
        d, s = self.dzwieki_i_slowa()
        self.assertIn("Mikrofon włączony z innego urządzenia", s)

    def test_suwak_trzymany_dopisek_wymusza_mowe(self):
        self.ruch("telefon", 1.0)
        self.slowa()
        self.nacisnij("dotyk", 2, True)
        self.cue("telefon")
        d, s = self.dzwieki_i_slowa()
        self.assertEqual(s, ["Rozmowa poza anteną ze słuchaczem. Suwak trzymany, kanał poza sumą do ściągnięcia suwaka"])
        self.assertEqual(d, ["sluchacz_cue"], "dźwięk zmiany stanu i mowa ostrzeżenia")

    def test_klawisz_wolny_mowa(self):
        self.klawisz("kursor_lewo_wolny")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Klawisz wolny"]))

    def test_odtwarzacz_emisyjny(self):
        from mostek.emisja import AtrapaEmisji
        self.r.emisja = AtrapaEmisji()
        self.klawisz("transport_play")
        self.assertEqual(self.dzwieki_i_slowa(), (["odtwarzacz_start"], []))


class TestTrybDzwiekiZMowa(ZTrybem):
    tryb = Tryb.DZWIEKI_Z_MOWA

    def test_dzwiek_potem_mowa(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), (["mikrofon_na_antenie"], ["Mikrofon włączony"]))
        self.cue("telefon")
        d, s = self.dzwieki_i_slowa()
        self.assertEqual(d, ["mikrofon_poza_antena", "sluchacz_cue"])
        self.assertEqual(s, ["Mikrofon poza anteną, rozmowa ze słuchaczem"])


class TestTrybMowa(ZTrybem):
    tryb = Tryb.MOWA

    def test_tylko_mowa_jak_przed_zmiana(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Mikrofon włączony"]))
        self.cue("telefon")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Mikrofon poza anteną, rozmowa ze słuchaczem"]))
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Rozmowa poza anteną, najpierw zwolnij CUE"]))


# =============================================================================
# 3. Żaden komunikat bezpieczeństwa nie traci mowy w trybie DZWIEKI
# =============================================================================
class TestMowaZawsze(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="mostek-test-")
        self.u = wczytaj_ustawienia(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _parametry(self, wzor: str) -> dict:
        return {p: "x" for p in re.findall(r"{(\w+)}", wzor)}

    def _komunikat(self, klucz: str) -> Komunikat:
        return self.u.tekst(klucz, **self._parametry(self.u.komunikaty[klucz]))

    def test_lista_zawsze_mowionych_rozlaczna_z_dzwiekowymi(self):
        self.assertEqual(sorted(set(ZAWSZE_MOWA) & KOMUNIKATY_DZWIEKIEM), [])
        for k in ZAWSZE_MOWA:
            self.assertIn(k, self.u.komunikaty, k)

    def test_kazdy_klucz_bezpieczenstwa_zawsze_z_mowa(self):
        """Wszystkie klucze komunikatów z ustawień, każdy w każdym wariancie
        z mapowania, każdy priorytet, z dźwiękiem przypisanym WSZYSTKIM
        kluczom (najgorszy przypadek ustawień): w trybie DZWIEKI mowę może
        stracić wyłącznie komunikat stanu z KOMUNIKATY_DZWIEKIEM o priorytecie
        innym niż bezpieczeństwo."""
        info = InformacjaZwrotna(self.u, AtrapaDzwiekow())
        warianty = {}
        for z in info.mapa:
            warianty.setdefault(inf.baza_zdarzenia(z), set()).add(z)
        info.mapa = {k: ["odmowa"] for k in self.u.komunikaty if not k.startswith("_")}
        for k in list(info.mapa):
            for w in warianty.get(k, ()):
                info.mapa[w] = ["odmowa"]
        sprawdzone = 0
        for klucz in self.u.komunikaty:
            if klucz.startswith("_"):
                continue
            tekst = self._komunikat(klucz)
            self.assertEqual(tekst.zdarzenia, (klucz,))
            for zdarzenie in {klucz} | warianty.get(klucz, set()):
                for prio in Priorytet:
                    with self.subTest(klucz=zdarzenie, priorytet=prio.name):
                        dzw, mow = info.plan((zdarzenie,), prio, Tryb.DZWIEKI)
                        if prio == Priorytet.BEZPIECZENSTWO or klucz not in KOMUNIKATY_DZWIEKIEM:
                            self.assertTrue(mow, "komunikat bezpieczeństwa stracił mowę")
                        sprawdzone += 1
                        # Część spoza stanów dokleja się do komunikatu stanu: mowa zostaje.
                        dzw2, mow2 = info.plan(("mikrofon_stan:wlaczony", zdarzenie), prio, Tryb.DZWIEKI)
                        if prio == Priorytet.BEZPIECZENSTWO or klucz not in KOMUNIKATY_DZWIEKIEM:
                            self.assertTrue(mow2)
        self.assertGreater(sprawdzone, 3 * 100)

    def test_klucze_wolane_z_priorytetem_bezpieczenstwa_nie_sa_dzwiekowe(self):
        """Każdy klucz komunikatu, który rdzeń wypowiada z priorytetem
        bezpieczeństwa (odczyt kodu), jest poza listą stanów bez mowy."""
        import ast
        drzewo = ast.parse((KATALOG / "mostek" / "rdzen.py").read_text(encoding="utf-8"))
        bezp = set()
        for w in ast.walk(drzewo):
            if not (isinstance(w, ast.Call) and isinstance(w.func, ast.Attribute) and w.func.attr == "powiedz"):
                continue
            prio = w.args[1:2] + [k.value for k in w.keywords if k.arg == "priorytet"]
            if not any(isinstance(a, ast.Attribute) and a.attr == "BEZPIECZENSTWO" for a in prio):
                continue
            for x in ast.walk(w.args[0]):
                if (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "t"
                        and x.args and isinstance(x.args[0], ast.Constant)):
                    bezp.add(x.args[0].value)
        self.assertGreater(len(bezp), 15)
        self.assertEqual(sorted(bezp & KOMUNIKATY_DZWIEKIEM), [])

    def test_tekst_bez_zdarzen_zawsze_mowa(self):
        info = InformacjaZwrotna(self.u, AtrapaDzwiekow())
        self.assertEqual(info.plan((), Priorytet.STAN, Tryb.DZWIEKI), ([], True))
        self.assertEqual(info.plan((None,), Priorytet.STAN, Tryb.DZWIEKI), ([], True))
        k = self.u.tekst("mikrofon_stan", stan="włączony").wariant("wlaczony")
        self.assertEqual((k + ", jakiś dopisek").zdarzenia, ("mikrofon_stan:wlaczony", None))
        self.assertEqual(k.lower(), "mikrofon włączony")
        self.assertFalse(hasattr(k.lower(), "zdarzenia") and k.lower().zdarzenia)

    def test_kolejka_bez_dzwieku_nigdy_cicha(self):
        a = AtrapaMowy()
        k = KolejkaMowy(a, alarm=None, dzwieki=None)
        k.powiedz("x", Priorytet.STAN, dzwieki=["mikrofon_na_antenie"], mow=False)
        k.oproznij()
        self.assertEqual(a.powiedziane, ["x"], "bez odtwarzacza dźwięków zawsze mowa")


class TestScenariuszeBezpieczenstwaWTrybieDzwiekow(ZTrybem):
    """Scenariusze z planu w trybie DZWIEKI: ostrzeżenia, odmowy, F2, gałka,
    kontroler, profil i ochronne zamknięcia mają mowę."""

    tryb = Tryb.DZWIEKI

    def test_kazde_ostrzezenie_z_mowa(self):
        oryginal = self.mowa.powiedz
        wpisy = []

        def zapisz(tekst, priorytet=Priorytet.STAN, klucz=None, dzwieki=(), mow=True, zastepcza_mowa=True):
            wpisy.append((str(tekst), priorytet, list(dzwieki), mow))
            return oryginal(tekst, priorytet, klucz, dzwieki=dzwieki, mow=mow, zastepcza_mowa=zastepcza_mowa)

        self.mowa.powiedz = zapisz
        # ciąg zdarzeń wywołujących ostrzeżenia i odmowy
        self.cue("telefon")
        self.klawisz("F1_mikrofon")                       # odmowa: CUE
        self.klawisz("glosniki_wlacz")                    # odmowa: tor mikrofonu
        self.klawisz("F3_koniec_rozmowy")
        self.inny(sciezki.szyna_lr(3), 1)                 # profil + ochronne zamknięcie
        self.klawisz("F2_status")
        self.nacisnij("galka", 2, 1)
        self.tick(0.6)
        self.nacisnij("kontroler", "restart")
        self.klawisz("F1_mikrofon")                       # odmowa: kontroler
        self.nacisnij("kontroler_powrot", "powrót")
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.klawisz("F1_mikrofon")                       # stan nieznany
        self.slowa()
        bez_mowy = [w for w in wpisy if not w[3]]
        for tekst, prio, dzw, mow in bez_mowy:
            self.assertNotEqual(prio, Priorytet.BEZPIECZENSTWO, tekst)
            self.assertTrue(dzw, f"komunikat bez mowy musi mieć dźwięk: {tekst}")
        ostrzezenia = [w for w in wpisy if w[1] == Priorytet.BEZPIECZENSTWO]
        self.assertGreater(len(ostrzezenia), 5)
        self.assertTrue(all(w[3] for w in ostrzezenia))


# =============================================================================
# 4. F4: przełącznik trybu
# =============================================================================
class TestF4(ZTrybem):
    tryb = Tryb.MOWA

    def test_cykl_i_ogloszenie_mowa_w_kazdym_trybie(self):
        od = len(self.sym.dziennik)
        zapytania = len(self.sym.zapytania)
        for oczekiwany in (Tryb.DZWIEKI, Tryb.DZWIEKI_Z_MOWA, Tryb.MOWA, Tryb.DZWIEKI):
            self.klawisz("F4_tryb_informacji")
            self.assertIs(self.info.tryb, oczekiwany)
            self.assertEqual(self.dzwieki_i_slowa(), ([], [TRYB_TEKST[oczekiwany]]),
                             "F4 zawsze ogłasza tryb mową, bez dźwięku")
        self.assertEqual(self.zapisy(od), [], "F4 nic nie zapisuje do miksera")
        self.assertEqual(len(self.sym.zapytania), zapytania, "F4 nie czyta miksera")

    def test_f4_przy_stanie_nieznanym(self):
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.slowa()
        self.klawisz("F4_tryb_informacji")
        self.assertEqual(self.slowa(), ["Tryb: dźwięki"])

    def test_f4_z_konsoli_i_midi(self):
        from mostek.glowny import polecenie_konsoli
        self.assertEqual(polecenie_konsoli("f4"), ("klawisz", "F4_tryb_informacji"))
        self.assertEqual(polecenie_konsoli("f5"), ("klawisz", "F5_ostatni_komunikat"))
        mapa = MapaMC(self.u.xtouch)
        self.assertEqual(mapa.zdarzenie([0x90, 57, 0x7F]), ("klawisz", "F4_tryb_informacji"))
        self.assertEqual(mapa.zdarzenie([0x90, 58, 0x7F]), ("klawisz", "F5_ostatni_komunikat"))
        self.assertEqual(mapa.zdarzenie([0x90, 59, 0x7F]), ("klawisz", "F6_co_gra"))
        self.assertEqual(mapa.zdarzenie([0x90, 60, 0x7F]), ("klawisz", "F7_automat"))


# =============================================================================
# 5. F5: powtórzenie ostatniego komunikatu
# =============================================================================
class TestF5(ZTrybem):
    tryb = Tryb.DZWIEKI

    def test_brak_komunikatu(self):
        self.klawisz("F5_ostatni_komunikat")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Brak komunikatu do powtórzenia"]))

    def test_powtarza_mowa_komunikat_ktory_byl_tylko_dzwiekiem(self):
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), (["mikrofon_na_antenie"], []))
        od = len(self.sym.dziennik)
        zapytania = len(self.sym.zapytania)
        self.zegar.przesun(5.0)                 # odczyt nieświeży: F5 i tak nie czyta
        self.klawisz("F5_ostatni_komunikat")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Mikrofon włączony"]))
        self.assertEqual(self.zapisy(od), [], "F5 nic nie zapisuje do miksera")
        self.assertEqual(len(self.sym.zapytania), zapytania, "F5 nie czyta miksera")

    def test_powtarza_ostatni_nie_wolne_klawisze_ani_f4(self):
        self.cue("telefon")
        self.slowa()
        self.klawisz("kursor_lewo_wolny")
        self.klawisz("F4_tryb_informacji")
        self.slowa()
        for _ in range(2):
            self.klawisz("F5_ostatni_komunikat")
            self.assertEqual(self.slowa(), ["Rozmowa poza anteną ze słuchaczem"])

    def test_powtarza_ostrzezenie(self):
        self.cue("telefon")
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.klawisz("F5_ostatni_komunikat")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Rozmowa poza anteną, najpierw zwolnij CUE"]))

    def test_f5_przy_stanie_nieznanym_bez_odczytu(self):
        self.klawisz("F1_mikrofon")
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.slowa()
        zapytania = len(self.sym.zapytania)
        self.klawisz("F5_ostatni_komunikat")
        self.assertEqual(len(self.sym.zapytania), zapytania)
        self.assertEqual(len(self.slowa()), 1)


# =============================================================================
# 6. Odtwarzanie: winsound, brak pliku, błąd odtwarzania
# =============================================================================
class FalszywyWinsound:
    SND_FILENAME, SND_ASYNC, SND_NODEFAULT = 0x20000, 0x1, 0x2

    def __init__(self):
        self.wywolania = []

    def PlaySound(self, dzwiek, flagi):  # noqa: N802 - nazwa jak w winsound
        self.wywolania.append((dzwiek, flagi))


class TestOdtwarzanie(ZTrybem):
    tryb = Tryb.DZWIEKI

    def test_winsound_asynchronicznie_z_plikiem(self):
        ws = FalszywyWinsound()
        o = OdtwarzaczWinsound(ws)
        plik = KATALOG / "dzwieki" / "alarm.wav"
        o.odtworz("alarm", plik)
        o.zatrzymaj()
        self.assertEqual(ws.wywolania[0], (str(plik), ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_NODEFAULT))
        self.assertEqual(ws.wywolania[1], (None, 0))

    def test_poza_windows_atrapa(self):
        if os.name == "nt":
            self.skipTest("tylko poza Windows")
        self.assertIsInstance(inf.utworz_odtwarzacz(), AtrapaDzwiekow)

    def test_brak_pliku_wav_mowa_zamiast_dzwieku(self):
        katalog = Path(self._tmp.name) / "dzwieki"
        shutil.copytree(KATALOG / "dzwieki", katalog)
        (katalog / "mikrofon_na_antenie.wav").unlink()
        self.u.informacja = dict(self.u.informacja, katalog_dzwiekow=str(katalog))
        with self.assertLogs("mostek.informacja", logging.WARNING) as logi:
            self.nowy_rdzen()
            self.info.tryb = Tryb.DZWIEKI
            self.klawisz("F1_mikrofon")
            self.assertEqual(self.dzwieki_i_slowa(), ([], ["Mikrofon włączony"]))
            self.klawisz("F1_mikrofon")
            self.klawisz("F1_mikrofon")
            self.assertEqual(self.dzwieki_i_slowa()[1][-1], "Mikrofon włączony")
        self.assertEqual(len([r for r in logi.records if "mikrofon_na_antenie" in r.getMessage()]), 1, logi.output)

    def test_blad_odtwarzania_mowa_i_jedno_ostrzezenie(self):
        with self.assertLogs("mostek.informacja", logging.WARNING) as logi:
            self.dzwieki.awaria = True
            self.klawisz("F1_mikrofon")
            self.assertEqual(self.slowa(), ["Mikrofon włączony"])
            self.klawisz("F1_mikrofon")
            self.klawisz("F1_mikrofon")
            self.assertEqual(self.slowa()[-1], "Mikrofon włączony")
        self.assertEqual(len([r for r in logi.records if "mikrofon_na_antenie" in r.getMessage()]), 1, logi.output)
        self.assertTrue(self.suma("mikrofon"), "mostek działa dalej")

    def test_brak_zestawu_dzwiekow_wszystko_mowa(self):
        self.u.informacja = dict(self.u.informacja, katalog_dzwiekow=str(Path(self._tmp.name) / "nie_ma"))
        with self.assertLogs("mostek.informacja", logging.WARNING):
            self.nowy_rdzen()
        self.info.tryb = Tryb.DZWIEKI
        self.klawisz("F1_mikrofon")
        self.assertEqual(self.dzwieki_i_slowa(), ([], ["Mikrofon włączony"]))


# =============================================================================
# 7. Kolejność dźwięku i mowy; ostrzeżenie przerywa dźwięk stanu
# =============================================================================
class WolneDzwieki:
    """Odtwarzacz z czasem dźwięku, zapisuje oś czasu zdarzeń."""

    def __init__(self, czas: float, os_czasu: list):
        self.czas = czas
        self.os = os_czasu

    def odtworz(self, klucz):
        self.os.append(("dzwiek", klucz, time.monotonic()))
        return self.czas

    def zatrzymaj(self):
        self.os.append(("stop", None, time.monotonic()))


class MowaZCzasem:
    def __init__(self, os_czasu):
        self.os = os_czasu

    def mow(self, tekst):
        self.os.append(("mowa", tekst, time.monotonic()))


class TestKolejnosc(unittest.TestCase):
    def test_mowa_razem_z_dzwiekiem(self):
        """Michał, 20.10.2026: mowa nie czeka na koniec dźwięku, „jesteśmy w radiu”."""
        os_czasu = []
        k = KolejkaMowy(MowaZCzasem(os_czasu), alarm=None, dzwieki=WolneDzwieki(0.3, os_czasu)).start()
        try:
            k.powiedz("Mikrofon włączony", Priorytet.STAN, "p", dzwieki=["mikrofon_na_antenie"], mow=True)
            for _ in range(100):
                if any(e[0] == "mowa" for e in os_czasu):
                    break
                time.sleep(0.01)
        finally:
            k.stop()
        self.assertEqual([e[0] for e in os_czasu], ["dzwiek", "mowa"])
        self.assertLess(os_czasu[1][2] - os_czasu[0][2], 0.05, "mowa czeka na koniec dźwięku")

    def test_nastepny_komunikat_nie_czeka_na_dzwiek_poprzedniego(self):
        """Stan z mową i dźwiękiem, zaraz po nim informacja: druga mowa bez
        czekania na koniec dźwięku pierwszego komunikatu, dźwięk ucięty."""
        os_czasu = []
        k = KolejkaMowy(MowaZCzasem(os_czasu), alarm=None, dzwieki=WolneDzwieki(0.5, os_czasu)).start()
        try:
            k.powiedz("Mikrofon włączony", Priorytet.STAN, "p", dzwieki=["mikrofon_na_antenie"], mow=True)
            for _ in range(100):
                if any(e[0] == "mowa" for e in os_czasu):
                    break
                time.sleep(0.01)
            k.powiedz("Klawisz wolny", Priorytet.INFORMACJA, "k", mow=True)
            for _ in range(100):
                if ("mowa", "Klawisz wolny") in [(e[0], e[1]) for e in os_czasu]:
                    break
                time.sleep(0.01)
        finally:
            k.stop()
        rodzaje = [(e[0], e[1]) for e in os_czasu]
        self.assertEqual(rodzaje[:4], [("dzwiek", "mikrofon_na_antenie"), ("mowa", "Mikrofon włączony"),
                                       ("stop", None), ("mowa", "Klawisz wolny")])
        self.assertLess(os_czasu[3][2] - os_czasu[0][2], 0.2, "drugi komunikat czeka na dźwięk pierwszego")

    def test_tryb_dzwiekow_bez_mowy_gra_do_konca(self):
        """Komunikat samym dźwiękiem nie jest ucinany przez następny komunikat
        tego samego priorytetu (jak dotąd)."""
        os_czasu = []
        k = KolejkaMowy(MowaZCzasem(os_czasu), alarm=None, dzwieki=WolneDzwieki(0.3, os_czasu)).start()
        try:
            k.powiedz("Słuchacz czeka", Priorytet.STAN, "a", dzwieki=["sluchacz_czeka"], mow=False)
            for _ in range(100):
                if os_czasu:
                    break
                time.sleep(0.01)
            k.powiedz("Zoom czeka", Priorytet.STAN, "b", dzwieki=["zoom_czeka"], mow=False)
            for _ in range(100):
                if sum(1 for e in os_czasu if e[0] == "dzwiek") >= 2:
                    break
                time.sleep(0.01)
        finally:
            k.stop()
        rodzaje = [(e[0], e[1]) for e in os_czasu]
        self.assertEqual(rodzaje[:2], [("dzwiek", "sluchacz_czeka"), ("dzwiek", "zoom_czeka")])
        self.assertGreaterEqual(os_czasu[1][2] - os_czasu[0][2], 0.28)

    def test_ostrzezenie_przerywa_dzwiek_stanu_i_stan_nie_ginie(self):
        os_czasu = []
        k = KolejkaMowy(MowaZCzasem(os_czasu), alarm=None, dzwieki=WolneDzwieki(0.6, os_czasu)).start()
        try:
            k.powiedz("Słuchacz czeka", Priorytet.STAN, "przejscie", dzwieki=["sluchacz_czeka"], mow=False)
            for _ in range(100):
                if os_czasu:
                    break
                time.sleep(0.01)
            k.powiedz("Brak łączności z mikserem", Priorytet.BEZPIECZENSTWO, "lacznosc", dzwieki=[], mow=True)
            for _ in range(200):
                if sum(1 for e in os_czasu if e[0] == "dzwiek") >= 2:
                    break
                time.sleep(0.02)
        finally:
            k.stop()
        rodzaje = [(e[0], e[1]) for e in os_czasu]
        self.assertEqual(rodzaje[:3], [("dzwiek", "sluchacz_czeka"), ("stop", None), ("mowa", "Brak łączności z mikserem")])
        self.assertLess(os_czasu[2][2] - os_czasu[0][2], 0.5, "ostrzeżenie nie czeka do końca dźwięku stanu")
        self.assertIn(("dzwiek", "sluchacz_czeka"), rodzaje[3:], "przerwany komunikat stanu wraca po ostrzeżeniu")

    def test_nowszy_stan_zastepuje_przerwany(self):
        os_czasu = []
        k = KolejkaMowy(MowaZCzasem(os_czasu), alarm=None, dzwieki=WolneDzwieki(0.4, os_czasu)).start()
        try:
            k.powiedz("A", Priorytet.STAN, "x", dzwieki=["a"], mow=True)
            for _ in range(100):
                if os_czasu:
                    break
                time.sleep(0.01)
            k.powiedz("B", Priorytet.STAN, "x", dzwieki=["b"], mow=True)
            k.powiedz("Uwaga", Priorytet.BEZPIECZENSTWO, "u", mow=True)
            for _ in range(200):
                if ("mowa", "B") in [(e[0], e[1]) for e in os_czasu]:
                    break
                time.sleep(0.02)
        finally:
            k.stop()
        mowa = [e[1] for e in os_czasu if e[0] == "mowa"]
        # A mówione razem ze swoim dźwiękiem (20.10.2026), więc nie wraca do
        # kolejki; B zastępuje je w kolejce i pada po ostrzeżeniu, A nie powtarza się.
        self.assertEqual(mowa, ["A", "Uwaga", "B"])


# =============================================================================
# 8. Ponowne otwarcie portu MIDI po odłączeniu USB X-TOUCH
# =============================================================================
class PortZUzbrojeniem(AtrapaPortuMIDI):
    """Port, który przy każdej wysyłce zapisuje, czy stół był już uzbrojony."""

    def __init__(self, rdzen):
        super().__init__()
        self.rdzen = rdzen
        self.uzbrojenie_przy_wysylce = []

    def wyslij(self, dane):
        super().wyslij(dane)
        self.uzbrojenie_przy_wysylce.append((bytes(dane), self.rdzen.uzbrojony))


class TestPonowienieMIDI(TestZSymulatorem):
    def setUp(self):
        super().setUp()
        self.proby = []
        self.dostepny = False
        self.stary = AtrapaPortuMIDI()
        self.nowe = []

        def otworz():
            self.proby.append(self.zegar())
            if not self.dostepny:
                raise BrakMIDI("nie znaleziono urządzenia MIDI zawierającego „X-TOUCH”")
            p = PortZUzbrojeniem(self.r)
            self.nowe.append(p)
            return p

        self.powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), self.stary, self.r.zglos,
                                               otworz_port=otworz,
                                               okres_ponowienia=float(self.u.xtouch["ponowienie_portu_s"]))
        self.r.powierzchnia = self.powierzchnia

    def test_okres_ponowienia_w_ustawieniach(self):
        self.assertEqual(self.u.xtouch["ponowienie_portu_s"], 2.0)

    def test_utrata_proby_powrot(self):
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.stary.odlacz()                                   # MIM_CLOSE: USB odłączony
        self.assertFalse(self.r.uzbrojony)
        with self.assertLogs("mostek.xtouch", logging.DEBUG) as logi:
            mowa = self.czekaj(9.0, krok=0.5)
            self.assertEqual(mowa, ["Kontroler odłączony, stół tylko zamyka tory"], "jeden komunikat utraty")
            self.assertGreaterEqual(len(self.proby), 4, "kilka nieudanych prób")
            odstepy = [b - a for a, b in zip(self.proby, self.proby[1:])]
            self.assertTrue(all(1.99 <= d <= 2.6 for d in odstepy), odstepy)
            self.stary.wstrzyknij(0x90, NUTA_F1, 0x7F)        # spóźnione MIDI starego portu nie wraca kontrolera
            self.assertFalse(self.r.kontroler_polaczony)
            self.dostepny = True
            mowa = self.czekaj(3.0, krok=0.5)
        ostrzezenia = [r for r in logi.records if r.levelno >= logging.WARNING]
        self.assertEqual(len(ostrzezenia), 2, [r.getMessage() for r in ostrzezenia])   # pierwsza próba i powrót
        self.assertEqual(mowa, ["Kontroler podłączony, suwaki według miksera"], "jeden komunikat powrotu")
        self.assertEqual(len(self.nowe), 1)
        self.assertTrue(self.stary.zamkniety, "stary uchwyt zamknięty")
        nowy = self.nowe[0]
        silniki = [(d, u) for d, u in nowy.uzbrojenie_przy_wysylce if d[0] & 0xF0 == 0xE0]
        self.assertTrue(silniki, "silniki wysłane na nowy port")
        self.assertTrue(all(u is False for _, u in silniki), "najpierw silniki, potem uzbrojenie")
        self.assertTrue(self.r.uzbrojony)
        self.assertEqual(self.m(sciezki.lr(9)), 1, "spóźniona nuta starego portu nic nie zrobiła")
        n = len(self.proby)
        self.czekaj(6.0, krok=0.5)
        self.assertEqual(len(self.proby), n, "po powrocie bez prób otwarcia")
        self.zegar.przesun(0.2)
        nowy.wstrzyknij(0x90, NUTA_F1, 0x7F)                  # nowy port działa
        self.assertEqual(self.m(sciezki.lr(9)), 0)

    def test_drugie_odlaczenie_po_powrocie(self):
        self.stary.odlacz()
        self.dostepny = True
        self.czekaj(2.5, krok=0.5)
        self.assertEqual(len(self.nowe), 1)
        self.dostepny = False
        self.nowe[0].odlacz()
        mowa = self.czekaj(5.0, krok=0.5)
        self.assertEqual(mowa, ["Kontroler odłączony, stół tylko zamyka tory"])
        self.dostepny = True
        mowa = self.czekaj(2.5, krok=0.5)
        self.assertEqual(mowa, ["Kontroler podłączony, suwaki według miksera"])

    def test_bez_portu_na_starcie(self):
        powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), None, self.r.zglos,
                                          otworz_port=lambda: self.nowe.append(AtrapaPortuMIDI()) or self.nowe[-1])
        self.r.powierzchnia = powierzchnia
        self.nacisnij("kontroler", "brak X-TOUCH przy starcie")
        self.assertEqual(self.slowa(), ["Kontroler odłączony, stół tylko zamyka tory"])
        mowa = self.czekaj(1.0, krok=0.5)
        self.assertEqual(mowa, ["Kontroler podłączony, suwaki według miksera"])
        self.assertTrue(self.r.uzbrojony)


class PortZOdpowiedzia(PortZUzbrojeniem):
    """X-TOUCH w trybie MC: na zapytanie odpowiada numerem seryjnym, póki żyje."""
    ODPOWIEDZ = bytes((0xF0, 0x00, 0x00, 0x66, 0x14, 0x01, 0x30, 0x31, 0xF7))

    def __init__(self, rdzen):
        super().__init__(rdzen)
        self.zywy = True
        self.zapytania = 0

    def zapytaj(self):
        self.zapytania += 1
        if self.zywy:
            self.wstrzyknij(*self.ODPOWIEDZ)


class TestZycieKontrolera(TestZSymulatorem):
    """Pomiar 21.10.2026 u Michała (Windows 11, Windows MIDI Services): po
    wyłączeniu i włączeniu X-TOUCH stary port milczy bez MIM_CLOSE. Mostek pyta
    stół zapytaniem MC; brak odpowiedzi to utrata i ponowne otwarcie portu."""

    def setUp(self):
        super().setUp()
        self.stary = PortZOdpowiedzia(self.r)
        self.nowe = []
        self.dostepny = True
        self.nowy_w_mc = True

        def otworz():
            if not self.dostepny:
                raise BrakMIDI("nie znaleziono urządzenia MIDI zawierającego „X-TOUCH”")
            p = PortZOdpowiedzia(self.r)
            p.zywy = self.nowy_w_mc
            self.nowe.append(p)
            return p

        self.powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), self.stary, self.r.zglos,
                                               otworz_port=otworz, okres_ponowienia=2.0,
                                               okres_zycia=float(self.u.xtouch["zycie_s"]),
                                               proby_zycia=int(self.u.xtouch["zycie_proby"]))
        self.r.powierzchnia = self.powierzchnia

    def test_ustawienia_zycia(self):
        self.assertEqual(self.u.xtouch["zycie_s"], 1.0)
        self.assertEqual(self.u.xtouch["zycie_proby"], 2)

    def test_zywy_stol_bez_komunikatow(self):
        mowa = self.czekaj(10.0, krok=0.5)
        self.assertEqual(mowa, [])
        self.assertGreaterEqual(self.stary.zapytania, 8, "zapytanie co sekundę")
        self.assertEqual(self.nowe, [], "żywy port nie jest otwierany od nowa")
        self.assertTrue(self.r.kontroler_polaczony)

    def test_milczacy_port_to_utrata_i_powrot_bez_restartu_mostka(self):
        """Objaw Michała: stół wyłączony i włączony, mostek słucha martwego
        portu. Teraz: utrata po ok. 2 s ciszy, nowy port, powrót po odpowiedzi."""
        self.klawisz("F1_mikrofon")
        self.slowa()
        self.stary.zywy = False                       # stary uchwyt milczy, bez MIM_CLOSE
        with self.assertLogs("mostek.xtouch", logging.INFO) as logi:
            mowa = self.czekaj(4.0, krok=0.5)
        self.assertIn("Kontroler odłączony, stół tylko zamyka tory", mowa)
        self.assertIn("Kontroler podłączony, suwaki według miksera", mowa)
        self.assertEqual(mowa.index("Kontroler odłączony, stół tylko zamyka tory"), 0)
        self.assertTrue(any("nie odpowiada na zapytanie MC" in r.getMessage() for r in logi.records))
        self.assertTrue(self.stary.zamkniety, "martwy uchwyt zamknięty")
        self.assertEqual(len(self.nowe), 1)
        self.assertTrue(self.r.uzbrojony)
        self.zegar.przesun(0.2)
        self.nowe[0].wstrzyknij(0x90, NUTA_F1, 0x7F)   # nowy port działa
        self.assertEqual(self.m(sciezki.lr(9)), 0)

    def test_nowy_port_bez_mc_nie_oglasza_powrotu(self):
        """Stół po restarcie w trybie innym niż MC: port się otwiera, ale stół
        milczy, więc mostek nie mówi „Kontroler podłączony” i dalej ponawia."""
        self.nowy_w_mc = False
        self.stary.zywy = False
        mowa = self.czekaj(12.0, krok=0.5)
        self.assertEqual(mowa, ["Kontroler odłączony, stół tylko zamyka tory"], "jeden komunikat, bez powrotu")
        self.assertFalse(self.r.kontroler_polaczony)
        self.assertGreaterEqual(len(self.nowe), 2, "port otwierany ponownie")
        self.assertTrue(all(p.zamkniety for p in self.nowe[:-1]))
        self.nowe[-1].zywy = True                      # Michał przestawia stół na MC
        mowa = self.czekaj(5.0, krok=0.5)
        self.assertEqual(mowa, ["Kontroler podłączony, suwaki według miksera"])

    def test_dziennik_podaje_ostatni_komunikat_stolu(self):
        """Zawieszenie 23.10.2026 19:11: do odróżnienia stołu od Windows
        dziennik musi mówić, kiedy i co stół wysłał ostatnio."""
        self.czekaj(2.0, krok=0.5)                     # odpowiedzi MC przychodzą
        n = self.powierzchnia.komunikaty
        self.assertGreater(n, 0)
        self.stary.zywy = False
        with self.assertLogs("mostek.xtouch", logging.WARNING) as logi:
            self.czekaj(4.5, krok=0.5)
        wpis = next(l for l in logi.output if "ostatni komunikat ze stołu" in l)
        self.assertIn("f0 00 00 66 14 01", wpis)
        self.assertIn(f"komunikatów od startu: {n}", wpis)
        self.assertTrue(any("X-TOUCH znowu wysyła MIDI" in l for l in logi.output))

    def test_opis_bez_komunikatow(self):
        p = PowierzchniaXTouch(MapaMC(self.u.xtouch), AtrapaPortuMIDI(), self.r.zglos)
        self.assertIn("nie przyszedł żaden komunikat", p.opis_ostatniego())

    def test_bez_zapytan_gdy_wylaczone(self):
        p = PortZOdpowiedzia(self.r)
        pow = PowierzchniaXTouch(MapaMC(self.u.xtouch), p, self.r.zglos, okres_zycia=None)
        self.r.powierzchnia = pow
        self.czekaj(5.0, krok=0.5)
        self.assertEqual(p.zapytania, 0)


if __name__ == "__main__":
    unittest.main()
