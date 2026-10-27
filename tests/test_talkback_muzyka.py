"""Talkback: poziom mikrofonu jak w CUE i przyciszona muzyka u adresata.

Zlecenie Michała z 26.10.2026. Wszystko mierzone na surowych wartościach
symulatora, nie przez Widok ani reguły produkcji.
"""

import unittest

from pomoc import TestZSymulatorem, sciezki, poziom_db_na_float

MUZYKA = ("muzyka1", "muzyka2", "muzyka3")


class BazaMuzyki(TestZSymulatorem):
    def wcisnij(self, pasek=2):
        self.nacisnij("przycisk", pasek, 2)

    def pusc(self, pasek=2):
        self.nacisnij("puszczenie", pasek, 2)

    def przygotuj(self, antena=False):
        self.klawisz("F1_mikrofon" if antena else "glosniki_wylacz")
        self.slowa()

    # --- pomiary ----------------------------------------------------------
    def poziom_mikrofonu(self, r: str) -> float:
        poziomy = [float(self.m(a)) for a in self.r.widok.adresy_wysylki("mikrofon", r)]
        self.assertEqual(len(set(poziomy)), 1, f"rozbieżne wysyłki mikrofonu do {r}")
        return poziomy[0]

    def poziomy_muzyki(self, r: str) -> dict[str, float]:
        """Najwyższy poziom każdego źródła muzyki w powrocie rozmówcy."""
        wynik = {}
        for z in MUZYKA:
            wynik[z] = max(float(self.m(a)) for a in self.r.widok.adresy_wysylki(z, r))
        return wynik

    def oczekiwana_muzyka(self, r: str, przyciszona: bool) -> dict[str, float]:
        dod = self.u.przyciszenie_muzyki_db if przyciszona else 0.0
        return {z: poziom_db_na_float(self.u.poziom_bazowy(z, r) + dod) for z in MUZYKA}

    def sprawdz_muzyke(self, r: str, przyciszona: bool, opis: str = "") -> None:
        oczek = self.oczekiwana_muzyka(r, przyciszona)
        maja = self.poziomy_muzyki(r)
        for z in MUZYKA:
            self.assertAlmostEqual(maja[z], oczek[z], places=5,
                                   msg=f"{z} do {r} ({opis}): {maja[z]} zamiast {oczek[z]}")
        for z in MUZYKA:
            for a in self.r.widok.adresy_wysylki(z, r):
                kanal, szyna = int(a.split("/")[2]), int(a.split("/")[4])
                self.assertEqual(int(self.m(sciezki.tap(kanal, szyna))), sciezki.TAP_POST,
                                 f"{z} do {r} nie za suwakiem")

    def sprawdz_bez_naruszen(self, opis: str) -> None:
        self.assertEqual(self.naruszenia_miksera(), [], opis)

    def suwak_mikrofonu(self, pozycja: float) -> None:
        self.ruch("mikrofon", pozycja)
        self.slowa()


class TestPoziomTalkbacku(BazaMuzyki):
    """(A) Wysyłka mikrofonu w talkbacku ma poziom jak mikrofon w rozmowie CUE."""

    def poziom_cue(self, r: str) -> float:
        """Ten sam pomiar wykonany przez istniejącą drogę CUE."""
        self.cue(r)
        self.slowa()
        poziom = self.poziom_mikrofonu(r)
        self.assertEqual(int(self.m(sciezki.tap(9, self.u.odbiorcy[r].szyny[0]))), sciezki.TAP_PRE)
        self.cue(r)
        self.slowa()
        return poziom

    def test_suwak_w_gorze_talkback_tak_glosno_jak_cue(self):
        self.przygotuj(antena=True)
        self.suwak_mikrofonu(1.0)
        self.assertEqual(self.r.widok.fader_db("mikrofon"), 10.0, "suwak mikrofonu w samej górze")
        w_cue = self.poziom_cue("telefon")
        self.przygotuj(antena=True)
        self.wcisnij()
        self.assertAlmostEqual(self.poziom_mikrofonu("telefon"), w_cue, places=5,
                               msg="talkback ciszej niż mikrofon w CUE")
        self.assertAlmostEqual(self.poziom_mikrofonu("telefon"), poziom_db_na_float(10.0), places=5)
        self.sprawdz_bez_naruszen("talkback z korektą suwaka")
        self.pusc()

    def test_suwak_na_zerze_i_na_dole_bez_korekty(self):
        self.przygotuj(antena=True)
        for pozycja, db in ((0.75, 0.0), (0.0, 0.0)):
            with self.subTest(pozycja=pozycja):
                self.suwak_mikrofonu(pozycja)
                self.wcisnij()
                self.assertAlmostEqual(self.poziom_mikrofonu("telefon"),
                                       poziom_db_na_float(self.u.poziom_bazowy("mikrofon", "telefon") + db),
                                       places=5)
                self.pusc()

    def test_oba_adresaci_dostaja_poziom_z_korekta(self):
        self.przygotuj(antena=True)
        self.suwak_mikrofonu(1.0)
        self.wcisnij(2)
        self.wcisnij(3)
        for r in ("telefon", "zoom"):
            self.assertAlmostEqual(self.poziom_mikrofonu(r), poziom_db_na_float(10.0), places=5, msg=r)
        self.sprawdz_bez_naruszen("obaj adresaci z korektą")
        self.pusc(2)
        self.pusc(3)

    def test_ustawienie_mikrofon_jak_na_antenie_false_bez_korekty(self):
        self.u.zachowanie["mikrofon_w_rozmowie_jak_na_antenie"] = False
        self.przygotuj(antena=True)
        self.suwak_mikrofonu(1.0)
        self.wcisnij()
        self.assertAlmostEqual(self.poziom_mikrofonu("telefon"),
                               poziom_db_na_float(self.u.poziom_bazowy("mikrofon", "telefon")), places=5)
        self.pusc()

    def test_korekta_z_suwaka_sprzed_talkbacku_bez_zmiany_fadera(self):
        self.przygotuj(antena=True)
        self.suwak_mikrofonu(1.0)
        przed = self.m(sciezki.fader(9))
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.fader(9)), przed, "talkback nie rusza suwaka mikrofonu")
        self.assertFalse([a for a, _ in self.zapisy(od) if a == sciezki.fader(9)])
        self.wcisnij(1)      # kaszel w trakcie też nie wolno
        self.assertEqual(self.m(sciezki.fader(9)), przed, "kaszel nie rusza suwaka mikrofonu")
        self.pusc(1)
        self.assertAlmostEqual(self.poziom_mikrofonu("telefon"), poziom_db_na_float(10.0), places=5)
        self.pusc()

    def test_maksimum_plus_10_db_przechodzi_zapore(self):
        self.przygotuj(antena=True)
        self.u.poziomy["wysylki"]["mikrofon"]["telefon"] = 5.0
        self.suwak_mikrofonu(1.0)
        self.wcisnij()
        self.assertAlmostEqual(self.poziom_mikrofonu("telefon"), poziom_db_na_float(10.0), places=5,
                               msg="poziom obcięty do plus 10 dB i przyjęty przez zaporę")
        self.sprawdz_bez_naruszen("poziom na maksimum")
        self.pusc()


class TestPrzyciszenieMuzyki(BazaMuzyki):
    """(B) Muzyka w powrocie adresata talkbacku ciszej, jak przy CUE."""

    def test_przyciszona_w_trakcie_i_dokladnie_przywrocona_po(self):
        self.przygotuj(antena=True)
        przed = {a: v for a, v in self.sym.wartosci.items()}
        self.sprawdz_muzyke("telefon", False, "przed talkbackiem")
        self.wcisnij()
        self.sprawdz_muzyke("telefon", True, "w trakcie talkbacku")
        self.sprawdz_bez_naruszen("talkback z przyciszoną muzyką")
        self.pusc()
        self.sprawdz_muzyke("telefon", False, "po puszczeniu")
        # Poziom wraca przez decybele, jak przy zwykłym CUE, więc porównanie
        # wysyłek jest w tolerancji miksera; wszystko inne co do bajtu.
        from mostek.klient import zgodne
        for a, v in przed.items():
            self.assertTrue(zgodne(self.sym.wartosci[a], v),
                            f"{a}: {self.sym.wartosci[a]} zamiast {v}")
        self.assertEqual(set(self.sym.wartosci), set(przed))
        self.assertEqual(self.slowa(), [])

    def test_przyciszenie_przed_otwarciem_mikrofonu(self):
        self.przygotuj(antena=True)
        od = len(self.sym.dziennik)
        self.wcisnij()
        zapisy = self.zapisy(od)
        adresy_muzyki = {a for z in MUZYKA for a in self.r.widok.adresy_wysylki(z, "telefon")}
        pierwsze_otwarcie = next(i for i, (a, v) in enumerate(zapisy)
                                 if a in self.r.widok.adresy_wysylki("mikrofon", "telefon")
                                 and isinstance(v, (int, float)) and float(v) > 0)
        przyciszenia = [i for i, (a, _) in enumerate(zapisy) if a in adresy_muzyki]
        self.assertTrue(przyciszenia, "muzyka wcale nie została przyciszona")
        self.assertLess(max(przyciszenia), pierwsze_otwarcie,
                        "muzyka przyciszona dopiero po otwarciu mikrofonu")
        self.pusc()

    def test_przyciszenie_bez_przerwy_w_dzwieku(self):
        """Obniżenie poziomu wprost, nie przez zero: rozmówca nie traci muzyki
        na czas sekwencji, tak samo jak przy wejściu w CUE."""
        self.przygotuj(antena=True)
        adresy_muzyki = {a for z in MUZYKA for a in self.r.widok.adresy_wysylki(z, "telefon")}
        od = len(self.sym.dziennik)
        self.wcisnij()
        zera = [(a, v) for a, v in self.zapisy(od)
                if a in adresy_muzyki and isinstance(v, (int, float)) and float(v) == 0.0]
        self.assertEqual(zera, [], "muzyka adresata zamknięta zamiast przyciszona")
        self.sprawdz_muzyke("telefon", True, "w trakcie talkbacku")
        self.pusc()

    def test_tylko_adresat_drugi_rozmowca_bez_zmian(self):
        self.przygotuj(antena=True)
        self.wcisnij(2)
        self.sprawdz_muzyke("telefon", True, "adresat")
        self.sprawdz_muzyke("zoom", False, "nie adresat")
        self.assertEqual(self.poziom_mikrofonu("zoom"), 0.0, "nie adresat nie słyszy mikrofonu")
        self.sprawdz_bez_naruszen("tylko adresat przyciszony")
        self.pusc(2)

    def test_oba_adresaci_puszczenie_jednego_przywraca_tylko_jego(self):
        self.przygotuj(antena=True)
        self.wcisnij(2)
        self.wcisnij(3)
        self.sprawdz_muzyke("telefon", True, "oba: telefon")
        self.sprawdz_muzyke("zoom", True, "oba: zoom")
        self.pusc(2)
        self.sprawdz_muzyke("telefon", False, "telefon puszczony")
        self.sprawdz_muzyke("zoom", True, "zoom nadal trzymany")
        self.sprawdz_bez_naruszen("jeden adresat przywrócony")
        self.pusc(3)
        self.sprawdz_muzyke("zoom", False, "oba puszczone")

    def test_adresat_w_cue_bez_zmian_muzyki(self):
        self.cue("telefon")
        self.slowa()
        self.sprawdz_muzyke("telefon", True, "CUE samo przycisza")
        przed = dict(self.sym.wartosci)
        self.wcisnij()
        self.sprawdz_muzyke("telefon", True, "adresat w CUE")
        self.assertEqual({a: v for a, v in self.sym.wartosci.items()
                          if a in {x for z in MUZYKA for x in self.r.widok.adresy_wysylki(z, "telefon")}},
                         {a: v for a, v in przed.items()
                          if a in {x for z in MUZYKA for x in self.r.widok.adresy_wysylki(z, "telefon")}},
                         "muzyka adresata w CUE nietknięta")
        self.pusc()
        self.sprawdz_muzyke("telefon", True, "CUE trwa dalej")

    def test_kaszel_w_trakcie_zostawia_przyciszenie_do_puszczenia(self):
        self.przygotuj(antena=True)
        self.wcisnij(2)
        self.sprawdz_muzyke("telefon", True, "talkback")
        self.wcisnij(1)
        self.assertEqual(self.poziom_mikrofonu("telefon"), 0.0, "kaszel zamyka mikrofon")
        self.sprawdz_muzyke("telefon", True, "kaszel w trakcie talkbacku")
        self.pusc(1)
        self.sprawdz_muzyke("telefon", True, "po kaszlu talkback trwa")
        self.assertGreater(self.poziom_mikrofonu("telefon"), 0.0)
        self.pusc(2)
        self.sprawdz_muzyke("telefon", False, "po puszczeniu talkbacku")

    def muzyka_na_antenie(self, zr: str, wl: bool) -> None:
        """Wejście albo zejście muzyki z anteny z innego urządzenia (SARA)."""
        for k in self.u.zrodla[zr].kanaly:
            self.inny(sciezki.lr(k), 1 if wl else 0)
        self.slowa()

    def test_muzyka_wchodzi_i_schodzi_z_anteny_w_trakcie(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.sprawdz_muzyke("telefon", True, "wszystkie na antenie")
        self.muzyka_na_antenie("muzyka1", False)
        self.assertFalse(self.suma("muzyka1"), "muzyka1 zeszła z anteny")
        self.assertEqual(max(float(self.m(a)) for a in self.r.widok.adresy_wysylki("muzyka1", "telefon")), 0.0,
                         "muzyka poza anteną zamknięta w powrocie")
        self.assertGreater(self.poziom_mikrofonu("telefon"), 0.0, "talkback trwa mimo zmiany anteny muzyki")
        self.muzyka_na_antenie("muzyka1", True)
        self.assertTrue(self.suma("muzyka1"), "muzyka1 wróciła na antenę")
        self.sprawdz_muzyke("telefon", True, "muzyka wróciła, nadal przyciszona")
        self.sprawdz_bez_naruszen("wejście i zejście muzyki w trakcie")
        self.pusc()
        self.sprawdz_muzyke("telefon", False, "po puszczeniu zwykły cel")

    def test_obca_zmiana_wysylki_muzyki_przerywa_bez_przywracania(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        adres = self.r.widok.adresy_wysylki("muzyka1", "telefon")[0]
        self.inny(adres, poziom_db_na_float(-30.0))
        self.assertEqual(self.poziom_mikrofonu("telefon"), 0.0, "obca zmiana przerywa talkback")
        self.assertAlmostEqual(float(self.m(adres)), poziom_db_na_float(-30.0), places=5,
                               msg="obca wartość nie jest cofana na ślepo")
        self.pusc()
        self.assertEqual(self.poziom_mikrofonu("telefon"), 0.0)
        self.assertTrue(any("Talkback przerwany" in s for s in self.slowa()))

    def test_utrata_kontrolera_nie_zostawia_muzyki_glosniej(self):
        self.przygotuj(antena=True)
        oczek = self.oczekiwana_muzyka("telefon", False)
        self.wcisnij()
        self.nacisnij("kontroler", "restart")
        self.assertEqual(self.poziom_mikrofonu("telefon"), 0.0, "mikrofon zamknięty")
        for z, poziom in self.poziomy_muzyki("telefon").items():
            self.assertLessEqual(poziom, oczek[z] + 0.005, f"{z} głośniej niż przed talkbackiem")
        self.slowa()

    def test_utrata_miksera_po_powrocie_nie_otwiera_ponad_zwykly_cel(self):
        self.przygotuj(antena=True)
        oczek = self.oczekiwana_muzyka("telefon", False)
        self.wcisnij()
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.sym.awarie.rozlaczony = False
        self.tick(2.0)
        self.assertEqual(self.poziom_mikrofonu("telefon"), 0.0, "mikrofon zamknięty po powrocie")
        for z, poziom in self.poziomy_muzyki("telefon").items():
            self.assertLessEqual(poziom, oczek[z] + 0.005, f"{z} głośniej niż zwykły cel")
        self.pusc()
        self.assertEqual(self.poziom_mikrofonu("telefon"), 0.0)
        self.slowa()

    def test_odmowa_talkbacku_nie_przycisza(self):
        self.przygotuj()
        del self.u.poziomy["wysylki"]["mikrofon"]["telefon"]
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.zapisy(od), [], "odmowa bez żadnego zapisu")
        self.sprawdz_muzyke("telefon", False, "po odmowie muzyka bez zmian")
        self.assertEqual(self.slowa(), ["Talkback niedostępny, brak poziomu wysyłki"])

    def test_ustawienie_false_zachowuje_dzisiejsze_zachowanie(self):
        self.u.zachowanie["przyciszenie_muzyki_talkback"] = False
        self.przygotuj(antena=True)
        przed = dict(self.sym.wartosci)
        self.wcisnij()
        self.sprawdz_muzyke("telefon", False, "przyciszenie wyłączone")
        self.assertGreater(self.poziom_mikrofonu("telefon"), 0.0, "mikrofon nadal idzie do adresata")
        self.pusc()
        self.assertEqual(self.sym.wartosci, przed)

    def test_domyslnie_wlaczone_w_pliku_ustawien(self):
        from mostek import ustawienia
        dane = ustawienia.wczytaj(ustawienia.DOMYSLNE_USTAWIENIA, ustawienia.DOMYSLNE_POZIOMY)
        self.assertIs(dane.zachowanie["przyciszenie_muzyki_talkback"], True)
        self.assertTrue(dane.przyciszenie_muzyki_talkback)

    def test_glosniki_i_antena_bez_zmian_wzgledem_dzisiejszego_talkbacku(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.assertEqual(self.m(sciezki.lr(9)), 0, "mikrofon nie na antenie")
        self.assertEqual(float(self.m(sciezki.wysylka(9, 5))), 0.0, "klucz przyciszania zamknięty")
        self.assertTrue(self.glosniki_wyciszone())
        self.assertTrue(self.suma("telefon"), "Main On adresata bez zmian")
        self.assertEqual(self.w_kluczu(), set(), "klucz bez źródeł w talkbacku")
        self.sprawdz_bez_naruszen("izolacja talkbacku zachowana")
        self.pusc()

    def test_adresat_poza_antena_tez_dostaje_przyciszona_muzyke(self):
        self.przygotuj()
        self.ruch("telefon", 0.0)
        self.slowa()
        self.wcisnij()
        self.sprawdz_muzyke("telefon", True, "czekający adresat")
        self.sprawdz_bez_naruszen("adresat poza anteną")
        self.pusc()
        self.sprawdz_muzyke("telefon", False, "po puszczeniu")


if __name__ == "__main__":
    unittest.main()
