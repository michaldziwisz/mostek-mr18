"""Zmiany z innego klienta, gałki, suwaki, PFL, podsłuch prawego ucha, status."""

import unittest

from pomoc import TestZSymulatorem, sciezki, ZERO_DB
from mostek.konwersje import gain_db_na_float, gain_float_na_db, trim_float_na_db


class TestInnyKlient(TestZSymulatorem):
    def test_zmiana_ogloszona_nie_cofnieta(self):
        self.inny(sciezki.mute_szyny(6), 0)
        od = len(self.sym.dziennik)
        self.inny(sciezki.lr(9), 1)
        mowa = self.slowa()
        self.assertIn("Mikrofon włączony z innego urządzenia", mowa)
        self.assertNotIn((sciezki.lr(9), 0), self.zapisy(od), "mostek nie cofa zmian innego klienta")
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        # Mikrofon na antenie: czekający słyszą antenę, także mikrofon.
        self.assertIn("mikrofon", self.slyszy("telefon"))

    def test_zmiana_z_innego_w_rozmowie_nie_otwiera_rozmowy_na_antene(self):
        self.cue("telefon")
        self.slowa()
        self.inny(sciezki.lr(9), 1)
        self.assertEqual(self.m(sciezki.lr(9)), 1, "nie cofamy cudzej zmiany")
        self.assertNotIn("mikrofon", self.slyszy("zoom"), "Zoom bez CUE dalej nie słyszy mikrofonu")
        self.assertIn("Mikrofon włączony z innego urządzenia", self.slowa())

    def test_suwak_rozmowcy_z_innego_urzadzenia(self):
        self.inny(sciezki.fader(10), ZERO_DB)
        mowa = self.slowa()
        self.assertIn("Słuchacz na antenie z innego urządzenia", mowa)
        self.assertIn("telefon", self.slyszy("zoom"), "powrót Zooma idzie za anteną")
        self.inny(sciezki.fader(10), 0.0)
        self.assertNotIn("telefon", self.slyszy("zoom"))
        self.assertIn("Słuchacz czeka z innego urządzenia", self.slowa())

    def test_wysylka_z_innego_urzadzenia(self):
        self.inny(sciezki.wysylka(7, 1), 0.5)
        self.inny(sciezki.wysylka(8, 1), 0.5)
        self.assertIn("Wysyłka Zooma do telefonu włączona z innego urządzenia", self.slowa())

    def test_nowy_poziom_wysylki_staje_sie_bazowy(self):
        self.inny(sciezki.wysylka(1, 1), 0.625)  # -5 dB wg krzywej
        self.inny(sciezki.wysylka(2, 1), 0.625)
        self.assertAlmostEqual(self.u.poziom_bazowy("muzyka1", "telefon"), -5.0, places=1)
        import json
        zapisane = json.loads(self.u.plik_poziomow.read_text(encoding="utf-8"))
        self.assertAlmostEqual(zapisane["wysylki"]["muzyka1"]["telefon"], -5.0, places=1)

    def test_poziom_muzyki_przy_cue_uczy_bez_przyciszenia(self):
        self.cue("telefon")
        from mostek.konwersje import poziom_db_na_float
        self.inny(sciezki.wysylka(1, 1), poziom_db_na_float(-25.0))
        self.inny(sciezki.wysylka(2, 1), poziom_db_na_float(-25.0))
        self.assertAlmostEqual(self.u.poziom_bazowy("muzyka1", "telefon"), -10.0, places=1)

    def test_zmiana_routingu_wymusza_pelny_odczyt(self):
        od = len(self.sym.dziennik)
        self.inny(sciezki.usb_zrodlo(3), 8)       # suchy mikrofon na wyjściu emisji
        mowa = self.slowa()
        self.assertEqual(mowa[0], "Zmiana routingu z innego urządzenia, odczytuję stan")
        self.assertTrue(any("Profil miksera niezgodny" in s for s in mowa), mowa)
        self.assertTrue(self.r.zapora.profil_blokuje)
        self.assertEqual(self.zapisy(od), [])

    def test_scena_z_innego_unieważnia_stan(self):
        zmiany = {sciezki.lr(9): 0, sciezki.fader(9): 0.5}
        self.transport.rozeslij(self.sym.wczytaj_scene_z_innego(zmiany))
        self.r.przetworz_zgloszenia()
        mowa = self.slowa()
        self.assertEqual(mowa[0], "Wczytano scenę z innego urządzenia, odczytuję stan")
        self.assertTrue(self.r.stan.zsynchronizowany)

    def test_xremote_odnawiany_przed_10_s(self):
        self.assertGreaterEqual(len(self.sym.subskrybenci), 1)
        for _ in range(30):
            self.tick(0.6)
        self.assertGreaterEqual(len(self.sym._aktywni()), 1, "subskrypcja nie wygasła po 18 s")
        self.assertLess(self.r.okres_xremote, 10.0)


class TestGalki(TestZSymulatorem):
    def test_krok_1_db_i_komunikat_po_zatrzymaniu(self):
        start = gain_float_na_db(float(self.m(sciezki.gain(10))))
        for _ in range(3):
            self.nacisnij("galka", 2, +1)
        self.assertAlmostEqual(gain_float_na_db(float(self.m(sciezki.gain(10)))), start + 3, places=3)
        self.assertEqual(self.slowa(), [], "bez komunikatu w trakcie obrotu")
        self.tick(0.6)
        self.assertEqual(self.slowa(), ["Telefon, wzmocnienie plus 3"])

    def test_granica_12_db(self):
        start = gain_float_na_db(float(self.m(sciezki.gain(10))))
        for _ in range(15):
            self.nacisnij("galka", 2, +1)
        self.assertAlmostEqual(gain_float_na_db(float(self.m(sciezki.gain(10)))), start + 12, places=3)
        self.assertIn("Granica wzmocnienia", self.slowa())
        for _ in range(30):
            self.nacisnij("galka", 2, -1)
        self.assertAlmostEqual(gain_float_na_db(float(self.m(sciezki.gain(10)))), start - 12, places=3)

    def test_galka_zooma_rtntrim_obu_kanalow(self):
        self.nacisnij("galka", 3, -1)
        for k in (7, 8):
            self.assertAlmostEqual(trim_float_na_db(float(self.m(sciezki.rtntrim(k)))), -1.0, places=3)
        self.tick(0.6)
        self.assertEqual(self.slowa(), ["Zoom, wzmocnienie minus 1"])

    def test_galka_dziala_w_rozmowie_na_cue(self):
        self.cue("telefon")
        self.slowa()
        start = gain_float_na_db(float(self.m(sciezki.gain(10))))
        self.nacisnij("galka", 2, +1)
        self.assertAlmostEqual(gain_float_na_db(float(self.m(sciezki.gain(10)))), start + 1, places=3)

    def test_galki_mikrofonu_i_muzyki_bez_funkcji(self):
        od = len(self.sym.dziennik)
        self.nacisnij("galka", 1, +1)
        self.nacisnij("galka", 4, +1)
        self.assertEqual(self.zapisy(od), [])

    def test_przy_nieznanym_galka_nic_nie_zmienia(self):
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.slowa()
        przed = self.m(sciezki.gain(10))
        self.nacisnij("galka", 2, +1)
        self.assertEqual(self.m(sciezki.gain(10)), przed)
        self.assertEqual(self.slowa(), ["Brak łączności z mikserem"])

    def test_zakres_liczony_od_sceny(self):
        self.sym.wartosci[sciezki.gain(10)] = gain_db_na_float(40.0)
        self.r.synchronizuj(nowa_baza_galek=True)
        self.nacisnij("galka", 2, +1)
        self.assertAlmostEqual(gain_float_na_db(float(self.m(sciezki.gain(10)))), 41.0, places=3)

    def test_wcisniecie_galki_status_paska(self):
        od = len(self.sym.dziennik)
        self.nacisnij("galka_wcisnij", 4)
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Muzyka 1 na sumie włączona, suwak w górze"])
        self.nacisnij("galka_wcisnij", 2)
        self.assertEqual(self.slowa(), ["Słuchacz czeka, suwak na dole. Telefon, wzmocnienie zero"])
        self.cue("telefon")
        self.slowa()
        self.nacisnij("galka_wcisnij", 2)
        self.assertEqual(self.slowa(), ["Słuchacz w rozmowie poza anteną, suwak na dole. Telefon, wzmocnienie zero"])


class TestSuwaki(TestZSymulatorem):
    def test_gora_to_zero_db(self):
        self.nacisnij("suwak", 4, 1.0)
        self.assertAlmostEqual(float(self.m(sciezki.fader(1))), ZERO_DB, places=5)
        self.assertAlmostEqual(float(self.m(sciezki.fader(2))), ZERO_DB, places=5)

    def test_dol_to_minus_nieskonczonosc(self):
        self.nacisnij("suwak", 1, 0.0)
        self.assertEqual(float(self.m(sciezki.fader(9))), 0.0)

    def test_suwak_zawsze_czynny_takze_w_muzyce_i_w_rozmowie(self):
        self.nacisnij("suwak", 6, 0.5)
        self.assertAlmostEqual(float(self.m(sciezki.fader(5))), 0.5 * ZERO_DB, places=5)
        self.assertEqual(self.slowa(), [], "ruch suwaka nie jest komentowany")
        self.cue("zoom")
        self.slowa()
        self.ruch("zoom", 1.0)
        self.assertAlmostEqual(float(self.m(sciezki.fader(7))), ZERO_DB, places=5, msg="suwak działa przy CUE")
        # Plan v21: podniesienie suwaka z CUE kończy CUE i wpuszcza na antenę.
        self.assertEqual(self.m(sciezki.lr(7)), 1)
        self.assertEqual(self.antena(), {"muzyka", "zoom"})

    def test_master_to_poziom_sluchawek_nie_pgm(self):
        self.nacisnij("suwak", 9, 0.4)
        self.assertAlmostEqual(float(self.m(sciezki.MONITOR_POZIOM)), 0.4 * ZERO_DB, places=5)

    def test_wolne_suwaki(self):
        od = len(self.sym.dziennik)
        self.nacisnij("dotyk", 7, True)
        self.nacisnij("suwak", 7, 0.9)
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Suwak wolny"])

    def test_nieuzbrojone_przed_synchronizacja(self):
        self.sym.awarie.rozlaczony = True
        self.tick()
        od = len(self.sym.dziennik)
        self.nacisnij("suwak", 1, 0.0)
        self.assertEqual(self.zapisy(od), [])

    def test_rozbiezna_para_wstrzymuje_suwak(self):
        self.sym.wartosci[sciezki.fader(3)] = 0.2
        self.r.synchronizuj()
        self.slowa()
        od = len(self.sym.dziennik)
        self.nacisnij("suwak", 5, 0.9)
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Muzyka 2: kanały pary rozbieżne, suwak wstrzymany"])

    def test_silniki_po_synchronizacji_wedlug_odczytu(self):
        # Mikrofon na 0 dB, góra jego suwaka to +10 dB (Michał 21.10.2026).
        self.assertAlmostEqual(self.pow.suwaki[1], 0.75, places=3)
        self.assertAlmostEqual(self.pow.suwaki[4], 1.0, places=3, msg="muzyka 0 dB = góra")
        self.assertAlmostEqual(self.pow.suwaki[2], 0.0, places=3)
        self.assertTrue(self.r.uzbrojony)


class TestPFLiPodsluch(TestZSymulatorem):
    def test_select_muzyki_przelacza_pfl(self):
        self.nacisnij("przycisk", 5, 3)
        self.assertTrue(self.pfl("muzyka2"))
        self.assertEqual(self.slowa(), ["Odsłuch kontrolny, Muzyka 2, włączony"])
        self.nacisnij("przycisk", 5, 3)
        self.assertFalse(self.pfl("muzyka2"))

    def test_pfl_rozmowy_podaza_za_cue(self):
        self.cue("zoom")
        self.assertTrue(self.pfl("mikrofon") and self.pfl("zoom"))
        self.assertFalse(self.pfl("telefon"))
        self.assertEqual(self.m(sciezki.MONITOR_ZRODLO), sciezki.ZRODLO_LRPFL)
        self.assertEqual(self.m(sciezki.MONITOR_DIMPFL), 0, "bez przyciszenia odsłuchu (Michał 22.10.2026)")
        self.cue("telefon")
        self.assertTrue(self.pfl("telefon"))
        self.cue("zoom")
        self.assertFalse(self.pfl("zoom"))
        self.assertTrue(self.pfl("mikrofon"))

    def test_podsluch_prawego_ucha(self):
        """Bus 2 OFF przy CUE telefonu i telefonie na antenie, ON gdy czeka (rozdz. 6)."""
        self.assertTrue(self.podsluch())
        self.cue("telefon")
        self.assertFalse(self.podsluch())
        self.cue("telefon")
        self.assertTrue(self.podsluch())
        self.ruch("telefon", 1.0)
        self.assertFalse(self.podsluch())
        self.ruch("telefon", 0.0)
        self.assertTrue(self.podsluch())
        self.cue("zoom")
        self.assertTrue(self.podsluch(), "CUE Zooma nie rusza podsłuchu telefonu")
        self.assertEqual(self.m(sciezki.tap(10, 2)), sciezki.TAP_PRE, "podsłuch przed suwakiem")

    def test_podsluch_przy_nieznanym_bez_zmian(self):
        self.cue("telefon")
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.sym.awarie.rozlaczony = False
        self.cue("telefon")              # przy NIEZNANY tylko zamyka rozmowę
        self.assertFalse(self.podsluch(), "przy NIEZNANY podsłuch zostaje, jaki był")

    def test_sluchaj_programu_rozmowy_i_koniec_pfl(self):
        self.cue("zoom")
        self.slowa()
        self.klawisz("sluchaj_programu")
        self.assertEqual(self.m(sciezki.MONITOR_ZRODLO), sciezki.ZRODLO_LR)
        self.assertFalse(self.pfl("mikrofon"))
        self.assertEqual(self.slowa(), ["Słuchasz programu"])
        self.assertTrue(self.cue_sym("zoom"), "odsłuch nie zmienia rozmowy")
        self.klawisz("sluchaj_rozmowy")
        self.assertTrue(self.pfl("zoom") and self.pfl("mikrofon"))
        self.assertEqual(self.slowa(), ["Słuchasz rozmowy. To nie jest czysty program"])
        self.klawisz("koniec_pfl")
        self.assertFalse(self.pfl("zoom"))

    def test_sluchaj_rozmowy_bez_cue(self):
        self.klawisz("sluchaj_rozmowy")
        self.assertEqual(self.slowa(), ["Nie ma rozmowy poza anteną"])


class TestStatus(TestZSymulatorem):
    def test_status_bez_zapisow_w_stalej_kolejnosci(self):
        od = len(self.sym.dziennik)
        self.klawisz("F2_status")
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Słuchacz czeka. Zoom czeka. Głośniki włączone."])

    def test_status_w_sytuacji_e(self):
        self.ruch("zoom", 1.0)
        self.cue("telefon")
        self.slowa()
        self.klawisz("F2_status")
        self.assertEqual(self.slowa(), ["Mikrofon wyłączony. Słuchacz w rozmowie poza anteną. Zoom na antenie. "
                                        "Głośniki wyciszone."])

    def test_f8_powierzchnia(self):
        self.klawisz("F8_odczytaj_powierzchnie")
        self.assertEqual(self.slowa(), ["Warstwa radiowa, sześć źródeł, odsłuch. Monitor: program plus odsłuch "
                                        "kontrolny. Bez odsłuchu kontrolnego. Głośniki włączone. Synchronizacja zgodna"])

    def test_klawisz_techniczny(self):
        od = len(self.sym.dziennik)
        self.klawisz("bank_lewo")
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Funkcja techniczna niedostępna w emisji"])

    def test_diody_pokazuja_stan_potwierdzony(self):
        self.klawisz("F1_mikrofon")
        self.assertIs(self.pow.diody[(1, 3)], True, "dioda SELECT paska mikrofonu")
        self.assertIs(self.pow.diody[(1, 0)], True, "REC paska mikrofonu: alarm ciszy włączony")
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.assertIsNone(self.pow.diody[(1, 3)], "NIEZNANY: dioda miga, nie świeci")


if __name__ == "__main__":
    unittest.main()
