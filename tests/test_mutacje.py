"""Test mutacyjny w zestawie: każda nowa reguła zapory, wyłączona w kopii kodu,
wywraca własny test reguły (narzedzia/mutacje_zapory.py, tryb szybki)."""

import sys
import unittest

from pomoc import KATALOG

sys.path.insert(0, str(KATALOG / "narzedzia"))
import mutacje_zapory as mz  # noqa: E402


class TestMutacjeZapory(unittest.TestCase):
    def test_mutant_wymaga_istniejacej_reguly(self):
        with self.assertRaises(ValueError):
            mz.mutuj("def inna():\n    pass\n", "cue_mikrofon_na_antene")

    def test_kazda_nowa_regula_ma_zabitego_mutanta(self):
        raport = mz.zbadaj(pelne=False)
        self.assertTrue(raport["oryginal_ok"], "bez mutacji testy zapory przechodzą")
        self.assertEqual(set(raport["reguly"]), set(mz.NOWE_REGULY))
        for regula, w in raport["reguly"].items():
            with self.subTest(regula=regula):
                self.assertTrue(w["wlasny_test_padl"], w)
                self.assertIn("not raised", w["powod"], "zapis odrzuca tylko badana reguła")
                self.assertTrue(w["zabity"], w)
        for zlozona, straznicy in mz.REGULY_ZLOZONE.items():
            self.assertEqual(set(raport["zlozone"][zlozona]), set(straznicy))
            for regula, w in raport["zlozone"][zlozona].items():
                with self.subTest(zlozona=zlozona, regula=regula):
                    self.assertTrue(w["zabity"], w)
        self.assertEqual(set(raport["poprawki"]), set(mz.MUTANTY_POPRAWEK))
        for nazwa, w in raport["poprawki"].items():
            with self.subTest(poprawka=nazwa):
                self.assertTrue(w["zabity"], w)


if __name__ == "__main__":
    unittest.main()
