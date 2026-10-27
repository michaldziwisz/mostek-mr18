"""Okno zapytań i szybka powtórka (dziennik z pomiaru 20.10.2026, MR18V2 fw 1.19).

Pomiar: ok. 110 pytań na sekundę w seriach po 24 wysłanych naraz, ok. 10%
bez odpowiedzi, odpowiedzi w 0–16 ms, druga próba zawsze udana. Każda zguba
czekała pełny limit 262 ms, stąd opóźnienie reakcji ok. 0,3 s.

Symulator to nie mikser: testy dowodzą zachowania klienta wobec modelu
utraty, nie zachowania MR18.
"""
from __future__ import annotations

import statistics
import threading
import time
import unittest

from pomoc import sciezki
from mostek.ustawienia import wczytaj as wczytaj_ustawienia
from mostek.klient import BrakOdpowiedzi, KlientMR18
from mostek.logika import adresy_krytyczne
from mostek.symulator import RdzenSymulatora, SerwerSymulatora
from mostek.transport import TransportPamieciowy, TransportUDP


def _czasy(klient, adresy, n=15):
    wyniki = []
    for _ in range(n):
        t = time.monotonic()
        klient.odczytaj_wiele(adresy)
        wyniki.append(time.monotonic() - t)
    return wyniki


class TestOknoUDP(unittest.TestCase):
    """Prawdziwe gniazda UDP na 127.0.0.1, utrata 10% pytań jak w pomiarze."""

    def setUp(self):
        self.s = SerwerSymulatora(port=0).start()
        self.s.rdzen.awarie.utrata_losowa = 0.10
        self.adresy = adresy_krytyczne(wczytaj_ustawienia())

    def tearDown(self):
        self.s.stop()

    def _klient(self, **opcje):
        return KlientMR18(TransportUDP(*self.s.adres), limit_odpowiedzi_s=0.15, dodatkowe_proby=2, **opcje)

    def test_stary_sposob_odtwarza_objaw_z_pomiaru(self):
        k = self._klient(okno=0)
        try:
            cz = _czasy(k, self.adresy)
        finally:
            k.zamknij()
        # 68 adresów = 3 porcje; przy 10% utraty prawie każda czeka pełny limit.
        self.assertGreater(statistics.median(cz), 0.4, cz)

    def test_okno_i_szybka_powtorka_skracaja_odczyt(self):
        k = self._klient()
        try:
            cz = _czasy(k, self.adresy)
        finally:
            k.zamknij()
        self.assertLess(statistics.median(cz), 0.15, cz)
        self.assertLess(max(cz), 0.3, cz)

    def test_wynik_kompletny_i_zgodny_z_mikserem(self):
        self.s.rdzen.wartosci[sciezki.lr(9)] = 1
        k = self._klient()
        try:
            for _ in range(10):
                dane = k.odczytaj_wiele(self.adresy)
                self.assertEqual(set(dane), set(self.adresy))
                self.assertEqual(dane[sciezki.lr(9)], 1)
        finally:
            k.zamknij()


class TestCiszaMiksera(unittest.TestCase):
    """Pomiar na MR18V2 fw 1.19 (22.10.2026): mikser milknie na 0,2 do 0,3 s co
    sekundę, czasem na 1 do 6 s. Krótka cisza nie może dać utraty łączności,
    długa ma ją dać po cisza_utraty_s."""

    def setUp(self):
        self.s = SerwerSymulatora(port=0).start()
        self.adresy = adresy_krytyczne(wczytaj_ustawienia())

    def tearDown(self):
        self.s.stop()

    def _klient(self, **opcje):
        o = dict(limit_odpowiedzi_s=0.15, dodatkowe_proby=2, przerwa_ponowienia_s=0.35, cisza_utraty_s=2.5)
        o.update(opcje)
        return KlientMR18(TransportUDP(*self.s.adres), **o)

    def _cisza(self, sekundy):
        a = self.s.rdzen.awarie
        a.rozlaczony = True
        t = threading.Timer(sekundy, lambda: setattr(a, "rozlaczony", False))
        t.start()
        return t

    def test_cisza_1_5_s_bez_utraty(self):
        k = self._klient()
        try:
            t = self._cisza(1.5)
            dane = k.odczytaj_wiele(self.adresy)
            t.join()
            self.assertEqual(set(dane), set(self.adresy))
            t = self._cisza(1.5)
            self.assertTrue(str(k.identyfikuj()[2]).startswith("MR18"))
            t.join()
        finally:
            k.zamknij()

    def test_stare_ustawienia_traca_lacznosc_w_tej_samej_ciszy(self):
        k = self._klient(przerwa_ponowienia_s=0.0, cisza_utraty_s=0.0)
        try:
            t = self._cisza(1.5)
            with self.assertRaises(BrakOdpowiedzi):
                k.odczytaj_wiele(self.adresy)
            t.join()
        finally:
            k.zamknij()

    def test_dluga_cisza_daje_utrate_po_limicie(self):
        k = self._klient()
        try:
            t = self._cisza(5.0)
            start = time.monotonic()
            with self.assertRaises(BrakOdpowiedzi):
                k.odczytaj_wiele(self.adresy)
            czas = time.monotonic() - start
            t.cancel()
            self.s.rdzen.awarie.rozlaczony = False
            self.assertGreaterEqual(czas, 2.5)
            self.assertLess(czas, 4.0, "utrata ogłoszona niedługo po limicie")
        finally:
            k.zamknij()


class TestSpoznionaPowtorka(unittest.TestCase):
    """Druga odpowiedź na powtórzone pytanie nie może zostać wzięta za
    odpowiedź na pytanie zadane po zmianie (kontrakt pkt 4)."""

    def test_spozniona_odpowiedz_po_powtorce(self):
        sym = RdzenSymulatora()
        transport = TransportPamieciowy(sym)
        klient = KlientMR18(transport, limit_odpowiedzi_s=0.2, dodatkowe_proby=2,
                            okno=8, szybka_powtorka_s=0.01)
        sym.wartosci[sciezki.lr(9)] = 1
        # Pytanie po 0 ms i powtórka po 10 ms: dwie odpowiedzi „1”, po 30 i 40 ms.
        sym.awarie.opoznienie_s = 0.03
        self.assertEqual(klient.odczytaj(sciezki.lr(9)), 1)
        sym.wartosci[sciezki.lr(9)] = 0
        # Następne pytanie dostanie „0” po 30 ms, a spóźnione „1” dociera po 10 ms.
        self.assertEqual(klient.odczytaj(sciezki.lr(9)), 0)
        sym.awarie.opoznienie_s = 0.0
        time.sleep(0.06)
        self.assertEqual(klient.odczytaj(sciezki.lr(9)), 0)
        klient.zamknij()

    def test_okno_ogranicza_pytania_w_locie(self):
        sym = RdzenSymulatora()
        transport = TransportPamieciowy(sym)
        klient = KlientMR18(transport, limit_odpowiedzi_s=0.2, okno=4, szybka_powtorka_s=0.05)
        w_locie, maks = [0], [0]
        oryginal = transport._wyslij

        def licz(ident, dane):
            w_locie[0] += 1
            maks[0] = max(maks[0], w_locie[0])
            oryginal(ident, dane)

        oryg_przyjmij = klient._odbior_weryfikacji

        def odbior(dane, nadawca):
            w_locie[0] -= 1
            oryg_przyjmij(dane, nadawca)
        transport._wyslij = licz
        klient._weryfikacja._odbior = odbior
        sym.awarie.opoznienie_s = 0.005
        klient.odczytaj_wiele(adresy_krytyczne(wczytaj_ustawienia())[:24])
        time.sleep(0.02)
        self.assertLessEqual(maks[0], 4)
        klient.zamknij()


if __name__ == "__main__":
    unittest.main()
