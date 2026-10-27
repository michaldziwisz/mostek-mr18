"""Wolno odpowiadający mikser (dziennik Michała 23.10.2026 03:12, MR18V2 fw 1.26).

Objaw: przez 17 s odpowiedzi po ok. 350 ms zamiast 16 ms. Powtórka po 30 ms
słała każde pytanie 4 razy (1316 powtórek w minucie), limit rundy dla kilku
brakujących pytań (169 ms) był krótszy niż odpowiedź miksera, więc mostek
ogłosił utratę łączności, choć mikser cały czas odpowiadał.

Symulator to nie mikser: test dowodzi zachowania klienta wobec stałego
opóźnienia, nie przyczyny spowolnienia MR18.
"""
from __future__ import annotations

import time
import unittest

from pomoc import sciezki  # noqa: F401  (ustawia ścieżkę importu)
from mostek.klient import BrakOdpowiedzi, KlientMR18
from mostek.logika import adresy_krytyczne
from mostek.symulator import RdzenSymulatora
from mostek.transport import TransportPamieciowy
from mostek.ustawienia import wczytaj as wczytaj_ustawienia

OPCJE = dict(limit_odpowiedzi_s=0.15, dodatkowe_proby=2, okno=16, szybka_powtorka_s=0.03,
             przerwa_ponowienia_s=0.35, cisza_utraty_s=4.0)


class TestWolnyMikser(unittest.TestCase):
    def setUp(self):
        self.sym = RdzenSymulatora()
        self.adresy = adresy_krytyczne(wczytaj_ustawienia())
        self.assertGreaterEqual(len(self.adresy), 60)

    def _klient(self, **opcje):
        o = dict(OPCJE)
        o.update(opcje)
        return KlientMR18(TransportPamieciowy(self.sym), **o)

    def test_stary_klient_traci_lacznosc_przy_wolnym_mikserze(self):
        k = self._klient(dopasuj_do_opoznienia=False)
        self.sym.awarie.opoznienie_s = 0.35
        try:
            with self.assertRaises(BrakOdpowiedzi):
                k.odczytaj_wiele(self.adresy)
        finally:
            k.zamknij()

    def test_nowy_klient_czyta_wszystko_bez_zasypywania(self):
        k = self._klient()
        try:
            k.odczytaj_wiele(self.adresy)            # mikser jeszcze szybki
            self.sym.awarie.opoznienie_s = 0.35
            for _ in range(3):
                przed = k.wyslane_pakiety
                t = time.monotonic()
                dane = k.odczytaj_wiele(self.adresy)
                czas = time.monotonic() - t
                self.assertEqual(set(dane), set(self.adresy))
                self.assertLess(czas, 4.0, czas)
            # Po dostrojeniu: najwyżej 1,5 wysłania na pytanie (dawniej 4).
            self.assertLessEqual(k.wyslane_pakiety - przed, int(len(self.adresy) * 1.5))
            self.assertGreater(k.opoznienie, 0.25)
        finally:
            k.zamknij()

    def test_po_spowolnieniu_wraca_do_szybkiej_powtorki(self):
        k = self._klient()
        try:
            self.sym.awarie.opoznienie_s = 0.35
            k.odczytaj_wiele(self.adresy)
            k.odczytaj_wiele(self.adresy)
            self.assertGreater(k._odstep_powtorki(), 0.4)
            self.sym.awarie.opoznienie_s = 0.0
            for _ in range(10):
                k.odczytaj_wiele(self.adresy)
            self.assertAlmostEqual(k._odstep_powtorki(), 0.03, places=3)
        finally:
            k.zamknij()

    def test_szybki_mikser_bez_zmian(self):
        k = self._klient()
        try:
            for _ in range(5):
                k.odczytaj_wiele(self.adresy)
            self.assertAlmostEqual(k._odstep_powtorki(), 0.03, places=3)
            self.assertAlmostEqual(k._limit_rundy(68), 0.15 * (1 + 68 / 32), places=6)
        finally:
            k.zamknij()

    def test_pusta_runda_przy_wolnym_mikserze_nie_skraca_limitu(self):
        """Jedna runda bez odpowiedzi (zgubione pakiety) przy wolnym mikserze
        nie może przywrócić krótkiego limitu: wtedy żadna odpowiedź już nie
        zdąży i mostek ogłasza utratę przy żywym mikserze."""
        k = self._klient()
        try:
            self.sym.awarie.opoznienie_s = 0.35
            k.odczytaj_wiele(self.adresy)
            przed = k.opoznienie
            self.sym.awarie.zgub_nastepne = 10 ** 6   # jedna runda: wszystko ginie
            k._runda(self.adresy[:4], k._limit_rundy(4))
            self.sym.awarie.zgub_nastepne = 0
            self.assertGreaterEqual(k.opoznienie, przed)
            self.assertGreater(k._limit_rundy(4), 0.35)
            dane = k.odczytaj_wiele(self.adresy)
            self.assertEqual(set(dane), set(self.adresy))
        finally:
            k.zamknij()

    def test_milczacy_mikser_dalej_daje_utrate(self):
        k = self._klient()
        try:
            self.sym.awarie.opoznienie_s = 0.35
            k.odczytaj_wiele(self.adresy)
            self.sym.awarie.rozlaczony = True
            t = time.monotonic()
            with self.assertRaises(BrakOdpowiedzi):
                k.odczytaj_wiele(self.adresy)
            # cisza_utraty_s 4 s plus najwyżej jedna długa runda (maks_limit_rundy_s 3 s).
            self.assertLess(time.monotonic() - t, 7.5)
        finally:
            k.zamknij()


class TestOdbiorPoResecie(unittest.TestCase):
    """Windows: ICMP „port nieosiągalny” (np. mikser w restarcie) zgłasza się
    jako ConnectionResetError przy następnym recvfrom. Wątek odbioru kanału
    nie może się przez to zakończyć."""

    def test_kanal_odbiera_dalej_po_connection_reset(self):
        import threading
        from mostek.transport import KanalUDP

        cel = ("127.0.0.1", 10024)
        odebrane = []
        gotowe = threading.Event()

        class Gniazdo:
            def __init__(self):
                self.kroki = [ConnectionResetError(10054, "WSAECONNRESET"), (b"x", cel)]

            def recvfrom(self, _n):
                if not self.kroki:
                    gotowe.wait(0.05)
                    import socket
                    raise socket.timeout()
                k = self.kroki.pop(0)
                if isinstance(k, BaseException):
                    raise k
                return k

            def close(self):
                pass

        kanal = KanalUDP.__new__(KanalUDP)
        kanal.cel = cel
        kanal._odbior = lambda d, n: (odebrane.append(d), gotowe.set())
        kanal._gniazdo = Gniazdo()
        kanal._dziala = True
        w = threading.Thread(target=kanal._petla, daemon=True)
        w.start()
        self.assertTrue(gotowe.wait(1.0), "wątek odbioru zginął po ConnectionResetError")
        kanal._dziala = False
        w.join(1.0)
        self.assertEqual(odebrane, [b"x"])


if __name__ == "__main__":
    unittest.main()
