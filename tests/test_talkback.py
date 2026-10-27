"""Talkback i kaszel: surowe trasy symulatora, nie dowód działania MR18."""

import unittest
from unittest.mock import patch

from pomoc import TestZSymulatorem, sciezki, poziom_db_na_float
from mostek import nauka
from mostek.glowny import polecenie_konsoli
from mostek.ustawienia import BladUstawien, sprawdz


class TestTalkback(TestZSymulatorem):
    def wcisnij(self, pasek=2):
        self.nacisnij("przycisk", pasek, 2)

    def pusc(self, pasek=2):
        self.nacisnij("puszczenie", pasek, 2)

    def przygotuj(self, antena=False):
        self.klawisz("F1_mikrofon" if antena else "glosniki_wylacz")
        self.slowa()

    def mikrofon(self):
        adresy = [sciezki.lr(9)]
        for b in (1, 3, 4, 5):
            adresy += [sciezki.wysylka(9, b), sciezki.tap(9, b)]
        return {a: self.m(a) for a in adresy}

    def muzyka_do_rozmowcow(self):
        """Wysyłki muzyki do szyn rozmówców. Od 26.10.2026 talkback je
        przycisza i oddaje, więc „nietknięte” ich nie obejmuje: mierzy je
        test_talkback_muzyka.py. Wchodzi tu też partner linkowanej pary
        Bus 3/4, którego mikser wyrównuje przy każdym zapisie, tak samo jak
        przy zwykłym CUE."""
        szyny = {b for odb in self.u.odbiorcy.values() for b in odb.szyny}
        return {sciezki.wysylka(k, b) for z in self.u.zrodla.values() if not z.glos
                for k in z.kanaly for b in szyny}

    def nietkniete(self):
        poza = set(self.mikrofon()) | self.muzyka_do_rozmowcow()
        return {a: v for a, v in self.sym.wartosci.items() if a not in poza}

    def sprawdz_adresatow(self, *adresaci):
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertEqual(self.m(sciezki.wysylka(9, 5)), 0.0)
        for r in ("telefon", "zoom"):
            for b in self.u.odbiorcy[r].szyny:
                self.assertEqual(self.slyszalny(9, b), r in adresaci, (r, b))
                if r in adresaci:
                    self.assertEqual(self.m(sciezki.tap(9, b)), sciezki.TAP_PRE)
                    self.assertAlmostEqual(float(self.m(sciezki.wysylka(9, b))),
                                           poziom_db_na_float(self.u.poziom_bazowy("mikrofon", r)), places=5)

    def test_telefon_na_antenie_bez_klucza_i_bez_zmian_rozmowcow(self):
        self.przygotuj(antena=True)
        self.ruch("telefon", 1.0)
        self.ruch("zoom", 1.0)
        self.slowa()
        przed, inne = self.mikrofon(), self.nietkniete()
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.sprawdz_adresatow("telefon")
        self.ten_sam_stan(self.nietkniete(), inne)
        self.assertTrue(self.r.widok.na_antenie("telefon"))
        self.assertTrue(self.r.widok.na_antenie("zoom"))
        self.assertTrue(self.pow.diody[(2, 2)])
        self.assertEqual(self.slowa(), [])
        self.pusc()
        self.ten_sam_stan(self.mikrofon(), przed)
        self.ten_sam_stan(self.nietkniete(), inne)
        # Talkback pisze tylko po torze mikrofonu i po wysyłkach muzyki do
        # adresata (przyciszenie z 26.10.2026), nigdzie więcej.
        dozwolone = set(przed) | self.muzyka_do_rozmowcow()
        self.assertTrue(all(a in dozwolone for a, _ in self.zapisy(od)),
                        sorted({a for a, _ in self.zapisy(od)} - dozwolone))
        self.assertFalse(self.pow.diody[(2, 2)])
        self.assertEqual(self.slowa(), [])

    def test_telefon_gdy_zoom_w_cue_slyszy_tylko_telefon(self):
        self.cue("zoom")
        self.slowa()
        przed, inne = self.mikrofon(), self.nietkniete()
        self.wcisnij()
        self.sprawdz_adresatow("telefon")
        self.assertEqual(self.r.widok.cue_zbior(), frozenset({"zoom"}))
        self.ten_sam_stan(self.nietkniete(), inne)
        self.tick()
        self.ten_sam_stan(self.nietkniete(), inne)
        self.pusc()
        self.ten_sam_stan(self.mikrofon(), przed)
        self.ten_sam_stan(self.nietkniete(), inne)
        self.assertEqual(self.slowa(), [])

    def test_poza_antena_bez_rozmowy_bazowy_poziom_i_przywrocenie_tap(self):
        self.przygotuj()
        self.u.poziomy["wysylki"]["mikrofon"]["telefon"] = -7.0
        self.ruch("mikrofon", 0.0)
        self.slowa()
        przed, inne = self.mikrofon(), self.nietkniete()
        self.wcisnij()
        self.sprawdz_adresatow("telefon")
        self.pusc()
        self.ten_sam_stan(self.mikrofon(), przed)
        self.ten_sam_stan(self.nietkniete(), inne)

    def test_obaj_adresaci_i_obie_kolejnosci_puszczania(self):
        self.przygotuj(antena=True)
        for pierwszy, drugi in ((2, 3), (3, 2)):
            with self.subTest(pierwszy=pierwszy):
                przed, inne = self.mikrofon(), self.nietkniete()
                self.wcisnij(2)
                self.wcisnij(3)
                self.sprawdz_adresatow("telefon", "zoom")
                self.pusc(pierwszy)
                self.sprawdz_adresatow("telefon" if drugi == 2 else "zoom")
                self.pusc(drugi)
                self.ten_sam_stan(self.mikrofon(), przed)
                self.ten_sam_stan(self.nietkniete(), inne)

    def test_powtorzone_wcisniecie_nie_nadpisuje_migawki(self):
        self.przygotuj(antena=True)
        przed = self.mikrofon()
        self.wcisnij()
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.zapisy(od), [])
        self.pusc()
        self.ten_sam_stan(self.mikrofon(), przed)

    def test_kaszel_w_cue_zamyka_wszystkich_i_przywraca_dokladnie(self):
        self.cue("telefon")
        self.cue("zoom")
        self.slowa()
        przed, inne = self.mikrofon(), self.nietkniete()
        self.wcisnij(1)
        self.sprawdz_adresatow()
        self.assertEqual(self.r.widok.cue_zbior(), frozenset({"telefon", "zoom"}))
        self.tick()
        # Jedyny nowy wyjątek: solo mikrofonu zdjęte na czas kaszlu.
        w_kaszlu = dict(inne)
        w_kaszlu[sciezki.solo(9)] = 0
        self.ten_sam_stan(self.nietkniete(), w_kaszlu)
        self.assertEqual(self.slowa(), [])
        self.pusc(1)
        self.ten_sam_stan(self.mikrofon(), przed)
        self.ten_sam_stan(self.nietkniete(), inne)
        self.assertEqual(self.slowa(), [])

    def test_kaszel_wygrywa_i_oddaje_glos_trzymanemu_talkbackowi(self):
        self.przygotuj(antena=True)
        przed, inne = self.mikrofon(), self.nietkniete()
        for kaszel_pierwszy in (False, True):
            with self.subTest(kaszel_pierwszy=kaszel_pierwszy):
                if kaszel_pierwszy:
                    self.wcisnij(1)
                    self.wcisnij(2)
                else:
                    self.wcisnij(2)
                    self.wcisnij(1)
                self.wcisnij(3)
                self.sprawdz_adresatow()
                self.pusc(1)
                self.sprawdz_adresatow("telefon", "zoom")
                self.pusc(2)
                self.sprawdz_adresatow("zoom")
                self.pusc(3)
                self.ten_sam_stan(self.mikrofon(), przed)
                self.ten_sam_stan(self.nietkniete(), inne)

    def test_puszczenie_talkbacku_podczas_kaszlu_nie_otwiera(self):
        self.przygotuj(antena=True)
        przed = self.mikrofon()
        self.wcisnij()
        self.wcisnij(1)
        self.pusc()
        self.sprawdz_adresatow()
        self.pusc(1)
        self.ten_sam_stan(self.mikrofon(), przed)

    def test_120_sekund_bez_limitu_talkback_i_kaszel(self):
        self.przygotuj(antena=True)
        self.u.zachowanie["kaszel_maks_s"] = 30.0
        przed = self.mikrofon()
        for pasek in (1, 2, 3):
            with self.subTest(pasek=pasek):
                self.wcisnij(pasek)
                self.assertEqual(self.czekaj(120.0), [])
                self.assertTrue(self.pow.diody[(pasek, 2)])
                self.sprawdz_adresatow(*(() if pasek == 1 else ("telefon" if pasek == 2 else "zoom",)))
                self.pusc(pasek)
                self.ten_sam_stan(self.mikrofon(), przed)

    def test_przelacznik_w_trakcie_talkbacku_bez_powrotu(self):
        self.przygotuj(antena=True)
        inne = self.nietkniete()
        self.wcisnij()
        self.klawisz("F1_mikrofon")
        self.sprawdz_adresatow()
        self.pusc()
        self.sprawdz_adresatow()
        self.ten_sam_stan(self.nietkniete(), inne)
        self.assertTrue(any("Talkback przerwany" in x for x in self.slowa()))

    def test_utrata_kontrolera_zamyka_talkback_bez_przywracania(self):
        self.przygotuj(antena=True)
        self.wcisnij(2)
        self.wcisnij(3)
        self.nacisnij("kontroler", "restart")
        self.sprawdz_adresatow()
        self.pusc(2)
        self.pusc(3)
        self.sprawdz_adresatow()
        self.assertTrue(any("Talkback przerwany" in x for x in self.slowa()))

    def test_utrata_miksera_sprzata_po_powrocie_i_nie_otwiera(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.sym.awarie.rozlaczony = True
        self.tick()
        self.sym.awarie.rozlaczony = False
        self.tick(2.0)
        self.sprawdz_adresatow()
        self.pusc()
        self.sprawdz_adresatow()

    def test_obca_zmiana_wysylki_wygrywa_z_migawka(self):
        self.cue("zoom")
        self.wcisnij()
        self.inny(sciezki.wysylka(9, 1), 0.0)
        self.pusc()
        self.sprawdz_adresatow()
        self.assertTrue(any("Talkback przerwany" in x for x in self.slowa()))

    def test_obcy_suwak_zostaje_i_nie_przywraca_mikrofonu(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.inny(sciezki.fader(10), poziom_db_na_float(-12.0))
        self.pusc()
        self.assertAlmostEqual(float(self.m(sciezki.fader(10))), poziom_db_na_float(-12.0), places=5)
        self.sprawdz_adresatow()

    def test_cue_w_trakcie_nie_otwiera_innemu_do_puszczenia(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.cue("zoom")
        self.sprawdz_adresatow("telefon")
        self.assertTrue(self.r.widok.cue("zoom"))
        self.pusc()
        self.assertEqual(self.m(sciezki.lr(9)), 0)
        self.assertTrue(self.slyszalny(9, 3))
        self.assertFalse(self.slyszalny(9, 1))
        self.assertFalse(self.suma("zoom"))

    def test_suwak_konczy_cue_w_trakcie_talkbacku(self):
        self.cue("zoom")
        self.wcisnij()
        self.ruch("zoom", 1.0)
        self.sprawdz_adresatow("telefon")
        self.assertFalse(self.r.widok.cue("zoom"))
        self.assertTrue(self.suma("zoom"))
        self.pusc()
        self.sprawdz_adresatow()
        self.assertTrue(self.suma("zoom"))

    def test_nieznany_i_brak_bazy_odmawia_bez_zapisow(self):
        self.przygotuj()
        del self.u.poziomy["wysylki"]["mikrofon"]["telefon"]
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), ["Talkback niedostępny, brak poziomu wysyłki"])
        self.r.stan.zsynchronizowany = False
        self.wcisnij(3)
        self.assertEqual(self.zapisy(od), [])
        self.assertTrue(any("nieznany" in x for x in self.slowa()))

    def test_glosniki_niewyciszone_wracaja_po_talkbacku(self):
        przed = dict(self.sym.wartosci)
        self.wcisnij()
        self.assertTrue(self.glosniki_wyciszone())
        self.sprawdz_adresatow("telefon")
        self.pusc()
        self.ten_sam_stan(self.sym.wartosci, przed)
        self.assertEqual(self.slowa(), [])

    def test_niepotwierdzone_zamkniecie_nie_otwiera_adresata(self):
        self.przygotuj(antena=True)
        self.sym.awarie.ignoruj_zapis.add(sciezki.lr(9))
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertFalse(any(a == sciezki.tap(9, 1) and v == sciezki.TAP_PRE for a, v in self.zapisy(od)))
        self.assertTrue(any("niepotwierdzona" in x or "może być włączony" in x for x in self.slowa()))

    def test_niepotwierdzone_otwarcie_zamyka_i_nie_przywraca(self):
        self.przygotuj()
        # Bus 3/4 są linkowane: zapis partnera też musi być odrzucony,
        # inaczej symulator poprawnie potwierdzi zmianę przez echo pary.
        self.sym.awarie.ignoruj_zapis.update({sciezki.wysylka(9, 3), sciezki.wysylka(9, 4)})
        self.wcisnij(3)
        self.pusc(3)
        self.sprawdz_adresatow()
        self.assertTrue(any("niepotwierdzona" in x for x in self.slowa()))

    def test_podwojny_odczyt_przed_otwarciem_i_po_otwarciu(self):
        self.przygotuj(antena=True)
        with patch.object(self.r, "_dwa_odczyty", wraps=self.r._dwa_odczyty) as odczyt:
            self.wcisnij()
            self.assertGreaterEqual(odczyt.call_count, 2)
            self.sprawdz_adresatow("telefon")
        with patch.object(self.r, "_dwa_odczyty", wraps=self.r._dwa_odczyty) as odczyt:
            self.pusc()
            self.assertGreaterEqual(odczyt.call_count, 2)

    def test_status_i_nauka(self):
        self.przygotuj()
        tekst, _ = nauka.opisz(self.u, ("przycisk", 2, 2))
        self.assertIn("talkback", tekst.lower())
        self.wcisnij()
        self.klawisz("F2_status")
        self.assertIn("Mikrofon do telefonu na czas talkbacku", self.slowa()[0])

    def test_konfiguracja_tylko_odbiorcy(self):
        self.assertEqual(self.u.paski[2].get("mute"), "talkback")
        self.assertEqual(self.u.paski[3].get("mute"), "talkback")
        sprawdz(self.u)
        for p in (1, 4):
            stary = self.u.paski[p].get("mute")
            self.u.paski[p]["mute"] = "talkback"
            with self.assertRaises(BladUstawien):
                sprawdz(self.u)
            self.u.paski[p]["mute"] = stary

    def test_przerwanie_nie_zabiera_cue_rozmowcom(self):
        self.cue("telefon")
        self.cue("zoom")
        inne = self.nietkniete()
        self.wcisnij(1)
        self.nacisnij("kontroler", "restart")
        self.assertEqual(self.r.widok.cue_zbior(), frozenset({"telefon", "zoom"}))
        self.ten_sam_stan(self.nietkniete(), inne)
        self.tick()
        self.ten_sam_stan(self.nietkniete(), inne)
        self.sprawdz_adresatow()
        self.nacisnij("kontroler_powrot", "test")
        self.klawisz("F3_koniec_rozmowy")
        self.assertEqual(self.r.widok.cue_zbior(), frozenset())

    def test_zoom_nie_slyszany_przez_telefon_z_cue(self):
        self.cue("telefon")
        przed, inne = self.mikrofon(), self.nietkniete()
        self.wcisnij(3)
        self.sprawdz_adresatow("zoom")
        self.assertEqual(self.r.widok.cue_zbior(), frozenset({"telefon"}))
        self.pusc(3)
        self.ten_sam_stan(self.mikrofon(), przed)
        self.ten_sam_stan(self.nietkniete(), inne)

    def test_zastany_mikrofon_na_antenie_z_cue_nie_wraca_przez_zapore(self):
        self.cue("zoom")
        # Stan nieosiągalny z mostka: obcy klient złamał istniejący zakaz.
        self.sym.wartosci[sciezki.lr(9)] = 1
        self.r.stan.potwierdz(sciezki.lr(9), 1, self.zegar())
        self.slowa()
        self.wcisnij()
        self.sprawdz_adresatow("telefon")
        self.pusc()
        self.sprawdz_adresatow()
        self.assertTrue(any("Mikrofon nie włączony" in s for s in self.slowa()))

    def test_wszystkie_tryby_informacji_kaszel_cichy_talkback_dzwiek(self):
        from mostek.informacja import Tryb
        self.przygotuj(antena=True)
        for tryb in Tryb:
            with self.subTest(tryb=tryb):
                self.info.tryb = tryb
                self.wcisnij()
                self.wcisnij(3)
                self.wcisnij(1)
                self.pusc(1)
                self.pusc(2)
                self.pusc(3)
                self.assertEqual(self.dzwieki_i_slowa(),
                                 (["talkback_start", "talkback_start", "talkback_koniec", "talkback_koniec"], []))

    def test_obce_odciszenie_glosnikow_blokuje_powrot(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.inny(sciezki.mute_szyny(6), 1)
        self.pusc()
        self.sprawdz_adresatow()
        self.assertEqual(self.m(sciezki.mute_szyny(6)), 0)
        self.assertTrue(any("Talkback przerwany" in s and "głośniki wyciszone" in s for s in self.slowa()))

    def test_odmowa_przy_glosnikach_nie_udaje_zamkniecia(self):
        self.przygotuj(antena=True)
        self.sym.wartosci[sciezki.mute_szyny(6)] = 1
        self.r.stan.potwierdz(sciezki.mute_szyny(6), 1, self.zegar())
        self.sym.awarie.ignoruj_zapis.add(sciezki.mute_szyny(6))
        od = len(self.sym.dziennik)
        self.wcisnij()
        self.assertTrue(self.zapisy(od))
        self.assertTrue(all(a == sciezki.mute_szyny(6) and v == 0 for a, v in self.zapisy(od)))
        self.assertEqual(self.m(sciezki.lr(9)), 1)
        self.assertEqual(self.slowa(), ["Talkback niedostępny, nie udało się wyciszyć głośników"])

    def test_obcy_suwak_muzyki_nie_jest_cofany(self):
        self.przygotuj(antena=True)
        przed = self.mikrofon()
        self.wcisnij()
        self.inny(sciezki.fader(1), 0.5)
        self.pusc()
        self.assertEqual(self.m(sciezki.fader(1)), 0.5)
        self.ten_sam_stan(self.mikrofon(), przed)

    def test_brak_otwarcia_po_zmianie_profilu(self):
        self.przygotuj(antena=True)
        self.wcisnij()
        self.inny(sciezki.szyna_lr(3), 1)
        self.pusc()
        self.sprawdz_adresatow()

    def test_kaszel_poza_antena_bez_toru_nie_zmienia_niczego(self):
        przed = dict(self.sym.wartosci)
        od = len(self.sym.dziennik)
        self.wcisnij(1)
        self.pusc(1)
        self.ten_sam_stan(self.sym.wartosci, przed)
        self.assertEqual(self.zapisy(od), [])
        self.assertEqual(self.slowa(), [])

    def test_nieprawidlowe_bazy_odmawiaja_bez_zapisow(self):
        self.przygotuj()
        for v in (None, "abc", float("nan"), float("inf"), -90, 11):
            with self.subTest(v=v):
                self.u.poziomy["wysylki"]["mikrofon"]["telefon"] = v
                od = len(self.sym.dziennik)
                self.wcisnij()
                self.assertEqual(self.zapisy(od), [])
                self.assertEqual(self.slowa(), ["Talkback niedostępny, brak poziomu wysyłki"])

    def test_konsola(self):
        for p in (2, 3):
            self.assertEqual(polecenie_konsoli(f"talkback {p}"), ("przycisk", p, 2))
            self.assertEqual(polecenie_konsoli(f"pusc {p}"), ("puszczenie", p, 2))
        self.assertEqual(polecenie_konsoli("pusc"), ("puszczenie", 1, 2))


if __name__ == "__main__":
    unittest.main()
