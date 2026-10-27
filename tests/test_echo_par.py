"""Echo linkowanych par (Michał, 23/24.10.2026).

Objaw na antenie: przy szybkim naciskaniu CUE „Przejście niepełne,
prywatność niepotwierdzona”, a zaraz po nim „Wysyłka muzyki 2 do telefonu
wyłączona z innego urządzenia”, choć innego urządzenia nie było.

Przyczyna z dziennika: kanały 1/2, 3/4, 5/6, 7/8 i szyny 3/4 są w BAZIE
linkowane, więc zapis /ch/03/mix/01/level mikser powiela sam na
/ch/04/mix/01/level. Mostek trzymał w modelu starą wartość kanału 4. Gdy
odczyt przed otwarciem (limit świeżości) trafił między zapis kanału 3
a kanału 4, porównanie widziało „obcą zmianę” i przerywało przejście.
"""
from __future__ import annotations

import unittest

from pomoc import TestZSymulatorem, sciezki

from mostek.rdzen import Krok


def _linki_bazy(a: str) -> bool:
    return a in {sciezki.chlink(1), sciezki.chlink(3), sciezki.chlink(5), sciezki.chlink(7),
                 sciezki.buslink(3)}


class TestPartnerzyPary(unittest.TestCase):
    def test_wysylka_kanalu_pary(self):
        self.assertEqual(sciezki.partnerzy_pary("/ch/03/mix/01/level", _linki_bazy), ["/ch/04/mix/01/level"])
        self.assertEqual(sciezki.partnerzy_pary("/ch/04/mix/01/level", _linki_bazy), ["/ch/03/mix/01/level"])

    def test_wysylka_do_pary_szyn(self):
        self.assertEqual(sciezki.partnerzy_pary("/ch/09/mix/03/level", _linki_bazy), ["/ch/09/mix/04/level"])
        self.assertEqual(sciezki.partnerzy_pary("/ch/09/mix/04/tap", _linki_bazy), ["/ch/09/mix/03/tap"])

    def test_para_kanalow_do_pary_szyn(self):
        self.assertEqual(sorted(sciezki.partnerzy_pary("/ch/07/mix/03/level", _linki_bazy)),
                         ["/ch/07/mix/04/level", "/ch/08/mix/03/level", "/ch/08/mix/04/level"])

    def test_suma_suwak_mute_solo(self):
        self.assertEqual(sciezki.partnerzy_pary("/ch/07/mix/lr", _linki_bazy), ["/ch/08/mix/lr"])
        self.assertEqual(sciezki.partnerzy_pary("/ch/01/mix/fader", _linki_bazy), ["/ch/02/mix/fader"])
        self.assertEqual(sciezki.partnerzy_pary("/ch/06/mix/on", _linki_bazy), ["/ch/05/mix/on"])
        self.assertEqual(sciezki.partnerzy_pary("/-stat/solosw/08", _linki_bazy), ["/-stat/solosw/07"])

    def test_bez_linku_bez_partnerow(self):
        # Mikrofon (9) i telefon (10) nie są w parze, Bus 1 i Bus 5 też nie.
        self.assertEqual(sciezki.partnerzy_pary("/ch/09/mix/lr", _linki_bazy), [])
        self.assertEqual(sciezki.partnerzy_pary("/ch/10/mix/01/level", _linki_bazy), [])
        self.assertEqual(sciezki.partnerzy_pary("/ch/09/mix/05/level", _linki_bazy), [])
        self.assertEqual(sciezki.partnerzy_pary("/-stat/solosw/09", _linki_bazy), [])
        self.assertEqual(sciezki.partnerzy_pary("/bus/6/mix/on", _linki_bazy), [])
        self.assertEqual(sciezki.partnerzy_pary("/ch/03/mix/pan", _linki_bazy), [], "pan w parze jest lustrzany")


class TestSymulatorPowielaPare(TestZSymulatorem):
    def test_zapis_kanalu_zmienia_drugi_kanal_pary(self):
        self.klient.ustaw(sciezki.wysylka(3, 1), 0.6)
        self.assertAlmostEqual(self.m(sciezki.wysylka(4, 1)), 0.6)

    def test_zapis_do_szyny_zmienia_druga_szyne_pary(self):
        self.klient.ustaw(sciezki.wysylka(9, 3), 0.75)
        self.assertAlmostEqual(self.m(sciezki.wysylka(9, 4)), 0.75)

    def test_kanal_bez_linku_nie_rusza_sasiada(self):
        przed = self.m(sciezki.wysylka(10, 1))
        self.klient.ustaw(sciezki.wysylka(9, 1), 0.75)
        self.assertEqual(self.m(sciezki.wysylka(10, 1)), przed)


class TestEchoParWPrzejsciu(TestZSymulatorem):
    """Odtworzenie zdarzenia z 24.10.2026 01:08:08 na symulatorze."""

    def setUp(self) -> None:
        super().setUp()
        # Każdy zapis trwa 50 ms, a limit świeżości jest krótki: odczyt przed
        # otwarciem pada co kilka zapisów, więc trafia też między kanały pary
        # (na stanowisku: limit 1 s i przejścia blisko siebie).
        oryginal = self.klient.ustaw

        def ustaw(adres, wartosc):
            self.zegar.przesun(0.05)
            return oryginal(adres, wartosc)

        self.klient.ustaw = ustaw
        self.r.limit_swiezosci = 0.12

    def _mowa_cyklu(self, zr: str, cykle: int = 3) -> list[str]:
        mowa = []
        for _ in range(cykle):
            self.cue(zr)
            mowa += self.slowa()
            self.cue(zr)
            mowa += self.slowa()
        return mowa

    def test_cue_telefonu_bez_falszywej_obcej_zmiany(self):
        mowa = self._mowa_cyklu("telefon")
        self.assertNotIn("Przejście niepełne, prywatność niepotwierdzona", mowa)
        self.assertFalse([s for s in mowa if "innego urządzenia" in s], mowa)
        self.assertFalse(self.cue_sym("telefon"))
        self.assertTrue(self.wysylka("muzyka2", "telefon"), "muzyka 2 wróciła do telefonu")
        self.assertTrue(self.wysylka("muzyka3", "telefon"))

    def test_cue_zooma_bez_falszywej_obcej_zmiany(self):
        mowa = self._mowa_cyklu("zoom")
        self.assertNotIn("Przejście niepełne, prywatność niepotwierdzona", mowa)
        self.assertFalse([s for s in mowa if "innego urządzenia" in s], mowa)
        self.assertFalse(self.cue_sym("zoom"))

    def test_w_dzienniku_echo_pary(self):
        self._mowa_cyklu("telefon", cykle=1)
        self.assertTrue([d for d in self.r.dziennik if d[1] == "echo-pary"],
                        "odczyt między kanałami pary trafił na echo (inaczej test niczego nie mierzy)")


class TestPrawdziwaObcaZmianaPartnera(TestZSymulatorem):
    """Kontrola pozytywna: echo przyjmuje wyłącznie wartość własnego zapisu."""

    def test_inna_wartosc_partnera_dalej_jest_obca(self):
        self.r._zapis(Krok(sciezki.wysylka(3, 1), 0.6, 0.0))
        self.slowa()
        # Inne urządzenie od razu wyłącza parę (kanał 4 inną wartością niż echo).
        self.transport.rozeslij(self.sym.zmien_z_innego(sciezki.wysylka(3, 1), 0.0))
        self.inny(sciezki.wysylka(4, 1), 0.0)
        self.assertIn("Wysyłka muzyki 2 do telefonu wyłączona z innego urządzenia", self.slowa())
        self.assertEqual(self.r.stan.wartosc(sciezki.wysylka(4, 1)), 0.0)
        self.assertFalse([d for d in self.r.dziennik if d[1] == "echo-pary"])

    def test_echo_wygasa(self):
        self.r._zapis(Krok(sciezki.wysylka(3, 1), 0.6, 0.0))
        self.zegar.przesun(self.r.okno_echa_par + 0.5)
        self.assertFalse(self.r._przyjmij_echo(sciezki.wysylka(4, 1), 0.6))

    def test_echo_jednorazowe(self):
        self.r._zapis(Krok(sciezki.wysylka(3, 1), 0.6, 0.0))
        self.assertTrue(self.r._przyjmij_echo(sciezki.wysylka(4, 1), 0.6))
        self.assertFalse(self.r._przyjmij_echo(sciezki.wysylka(4, 1), 0.6))

    def test_bez_linku_bez_echa(self):
        self.r.stan.potwierdz(sciezki.chlink(3), 0, self.zegar())
        self.r._zapis(Krok(sciezki.wysylka(3, 1), 0.6, 0.0))
        self.assertFalse(self.r._przyjmij_echo(sciezki.wysylka(4, 1), 0.6))


if __name__ == "__main__":
    unittest.main()
