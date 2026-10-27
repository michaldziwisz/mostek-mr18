"""Kodek OSC, klient MR18 i test całościowy przez prawdziwe gniazda UDP localhost."""

import struct
import threading
import time
import unittest
from pathlib import Path

from pomoc import AtrapaPowierzchni, Zegar, sciezki, wczytaj_ustawienia
from mostek import osc
from mostek.klient import BrakOdpowiedzi, KlientMR18
from mostek.mowa import AtrapaMowy, KolejkaMowy
from mostek.rdzen import Rdzen
from mostek.symulator import RdzenSymulatora, SerwerSymulatora
from mostek.transport import TransportPamieciowy, TransportUDP


class TestKodek(unittest.TestCase):
    def test_zapytanie_bez_argumentu(self):
        dane = osc.koduj("/ch/09/mix/lr")
        self.assertEqual(len(dane) % 4, 0)
        k = osc.dekoduj(dane)[0]
        self.assertEqual(k.adres, "/ch/09/mix/lr")
        self.assertIsNone(k.wartosc)

    def test_int_float_string_blob(self):
        dane = osc.koduj("/x", 1, 0.75, "MR18", b"\x01\x02\x03")
        k = osc.dekoduj(dane)[0]
        self.assertEqual(k.typy, "ifsb")
        self.assertEqual(k.argumenty[0], 1)
        self.assertAlmostEqual(k.argumenty[1], 0.75)
        self.assertEqual(k.argumenty[2], "MR18")
        self.assertEqual(k.argumenty[3], b"\x01\x02\x03")

    def test_big_endian_i_wyrownanie(self):
        dane = osc.koduj("/ch/01/mix/fader", 0.5, typy="f")
        self.assertEqual(dane[:16], b"/ch/01/mix/fader")
        self.assertEqual(dane[16:20], b"\x00\x00\x00\x00")
        self.assertEqual(dane[20:24], b",f\x00\x00")
        self.assertEqual(struct.unpack(">f", dane[24:28])[0], 0.5)

    def test_wymuszony_typ_float_dla_zera(self):
        k = osc.dekoduj(osc.koduj("/ch/01/mix/01/level", 0, typy="f"))[0]
        self.assertEqual(k.typy, "f")

    def test_bundle(self):
        a = osc.koduj("/a", 1)
        b = osc.koduj("/b", 2)
        dane = b"#bundle\x00" + b"\x00" * 8 + struct.pack(">i", len(a)) + a + struct.pack(">i", len(b)) + b
        self.assertEqual([k.adres for k in osc.dekoduj(dane)], ["/a", "/b"])

    def test_bledne_pakiety(self):
        for zly in (b"abc", b"abcd", b"/ab\x00,x\x00\x00", b"/ab\x00,i\x00\x00\x00"):
            with self.assertRaises(osc.BladOSC):
                osc.dekoduj(zly)


class TestKlient(unittest.TestCase):
    def setUp(self):
        self.sym = RdzenSymulatora()
        self.transport = TransportPamieciowy(self.sym)
        self.klient = KlientMR18(self.transport, limit_odpowiedzi_s=0.01, dodatkowe_proby=2)

    def test_ustaw_potwierdza_odczytem(self):
        w = self.klient.ustaw(sciezki.lr(9), 1)
        self.assertTrue(w.potwierdzony)
        self.assertEqual(w.proby, 1)
        self.assertIn(sciezki.lr(9), [z[2] for z in self.sym.zapytania])

    def test_powtorzenie_po_zgubionym_pakiecie(self):
        self.sym.awarie.zgub_nastepne = 1      # zgubiony zapis
        w = self.klient.ustaw(sciezki.lr(9), 1)
        self.assertTrue(w.potwierdzony)
        self.assertEqual(w.proby, 2)

    def test_najwyzej_dwie_dodatkowe_proby(self):
        self.sym.awarie.ignoruj_zapis = {sciezki.lr(9)}
        w = self.klient.ustaw(sciezki.lr(9), 1)
        self.assertFalse(w.potwierdzony)
        self.assertEqual(w.proby, 3)
        self.assertEqual(sum(1 for d in self.sym.dziennik if d[2] == sciezki.lr(9)), 3)

    def test_milczenie_to_brak_odpowiedzi(self):
        self.sym.awarie.rozlaczony = True
        with self.assertRaises(BrakOdpowiedzi):
            self.klient.ustaw(sciezki.lr(9), 0)
        with self.assertRaises(BrakOdpowiedzi):
            self.klient.identyfikuj()

    def test_wymiana_kanalu_po_przekroczeniu_czasu(self):
        self.sym.awarie.zgub_nastepne = 1
        self.klient.odczytaj(sciezki.lr(9))
        self.assertGreaterEqual(self.klient.wymiany_kanalu, 1)

    def test_identyfikacja(self):
        info = self.klient.identyfikuj()
        self.assertEqual(info[2], "MR18")


class TestSpoznionaOdpowiedz(unittest.TestCase):
    """Opóźnione potwierdzenie starego ON nie może unieważnić nowszego OFF (kontrakt pkt 4 i 7)."""

    def test_spozniony_pakiet_trafia_do_zamknietego_kanalu(self):
        sym = RdzenSymulatora()
        transport = TransportPamieciowy(sym)
        klient = KlientMR18(transport, limit_odpowiedzi_s=0.02, dodatkowe_proby=0)
        sym.wartosci[sciezki.lr(9)] = 1
        sym.awarie.opoznienie_s = 0.06          # odpowiedź przyjdzie po limicie
        with self.assertRaises(BrakOdpowiedzi):
            klient.odczytaj(sciezki.lr(9))
        sym.awarie.opoznienie_s = 0.0
        sym.wartosci[sciezki.lr(9)] = 0
        self.assertEqual(klient.odczytaj(sciezki.lr(9)), 0)
        time.sleep(0.08)                        # spóźniona „1” dociera teraz
        self.assertEqual(klient.odczytaj(sciezki.lr(9)), 0)
        klient.zamknij()


class TestUDPMostekKontraSymulator(unittest.TestCase):
    """Test całościowy przez prawdziwe gniazda UDP na 127.0.0.1 (wolny port).

    Symulator to nie mikser: test dowodzi zachowania mostka wobec
    symulatora, nie zachowania MR18.
    """

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="mostek-udp-")
        self.u = wczytaj_ustawienia(Path(self._tmp.name))
        self.serwer = SerwerSymulatora(port=0).start()
        host, port = self.serwer.adres
        self.klient = KlientMR18(TransportUDP(host, port), limit_odpowiedzi_s=0.2, dodatkowe_proby=2)
        self.wyjscie = AtrapaMowy()
        self.mowa = KolejkaMowy(self.wyjscie, alarm=None)
        self.r = Rdzen(self.u, self.klient, self.mowa, powierzchnia=AtrapaPowierzchni(), zegar=time.monotonic)
        self.inny = KlientMR18(TransportUDP(host, port), limit_odpowiedzi_s=0.2)

    def tearDown(self):
        self.klient.zamknij()
        self.inny.zamknij()
        self.serwer.stop()
        self._tmp.cleanup()

    def slowa(self):
        self.mowa.oproznij()
        w = list(self.wyjscie.powiedziane)
        self.wyjscie.powiedziane.clear()
        return w

    def czekaj_na_zgloszenie(self, limit=2.0):
        koniec = time.monotonic() + limit
        while time.monotonic() < koniec:
            if not self.r._zgloszenia.empty():
                return True
            time.sleep(0.01)
        return False

    def test_caly_przebieg_przez_udp(self):
        w = self.serwer.rdzen.wartosci
        self.assertTrue(self.r.start())
        mowa = self.slowa()
        self.assertIn("Mikrofon wyłączony. Słuchacz czeka. Zoom czeka. Głośniki włączone.", mowa)
        koniec = time.monotonic() + 2.0
        while not self.serwer.rdzen._aktywni() and time.monotonic() < koniec:
            time.sleep(0.01)    # /xremote nie ma odpowiedzi; serwer przetwarza go w swoim wątku
        self.assertEqual(len(self.serwer.rdzen._aktywni()), 1, "subskrypcja /xremote")

        self.r.zglos(("klawisz", "F1_mikrofon"))
        self.assertEqual(w[sciezki.lr(9)], 1)
        self.assertEqual(w[sciezki.mute_szyny(6)], 0, "głośniki mono Bus 6 wyciszone")
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])

        # CUE telefonu przy mikrofonie na antenie (sytuacja B -> C, decyzja 5).
        time.sleep(0.1)
        self.r.zglos(("przycisk", 2, 3))
        self.assertEqual(w[sciezki.lr(9)], 0, "mikrofon zszedł z anteny")
        self.assertEqual(w[sciezki.lr(10)], 0, "telefon poza sumą na czas CUE")
        self.assertGreater(float(w[sciezki.wysylka(9, 1)]), 0)
        self.assertEqual(w[sciezki.tap(9, 1)], sciezki.TAP_PRE)
        self.assertEqual(float(w[sciezki.wysylka(9, 3)]), 0.0, "Zoom nie słyszy rozmowy")
        self.assertEqual(float(w[sciezki.wysylka(10, 2)]), 0.0, "podsłuch prawego ucha wyłączony")
        self.assertEqual(self.slowa(), ["Mikrofon poza anteną, rozmowa ze słuchaczem"])

        # Przełącznik mikrofonu przy CUE nie otwiera anteny (decyzja 6).
        time.sleep(0.1)
        self.r.zglos(("klawisz", "F1_mikrofon"))
        self.assertEqual(w[sciezki.lr(9)], 0)
        self.assertEqual(self.slowa(), ["Rozmowa poza anteną, najpierw zwolnij CUE"])

        # Zmiana z innego klienta przez prawdziwe UDP: ogłoszona, nie cofnięta.
        self.inny.wyslij(sciezki.lr(1), 0)
        self.inny.wyslij(sciezki.lr(2), 0)
        self.assertTrue(self.czekaj_na_zgloszenie())
        time.sleep(0.05)
        self.r.tick()
        self.assertEqual(w[sciezki.lr(1)], 0)
        mowa = self.slowa()
        self.assertIn("Muzyka 1 na sumie wyłączona z innego urządzenia", mowa)
        self.assertEqual(float(w[sciezki.wysylka(1, 1)]), 0.0, "powrót idzie za anteną")

        # F3: koniec rozmowy, słuchacz czeka.
        time.sleep(0.1)
        self.r.zglos(("klawisz", "F3_koniec_rozmowy"))
        self.assertEqual(float(w[sciezki.wysylka(9, 1)]), 0.0)
        self.assertEqual(w[sciezki.lr(10)], 1)
        self.assertGreater(float(w[sciezki.wysylka(10, 2)]), 0.0)
        self.assertEqual(self.slowa(), ["Koniec rozmowy. Słuchacz czeka. Zoom czeka. Głośniki włączone"])

        # Utrata łączności i powrót bez nadpisania miksera.
        self.serwer.rdzen.awarie.rozlaczony = True
        self.r._ost_krytyczny = float("-inf")
        self.r.tick()
        self.assertFalse(self.r.stan.polaczony)
        self.assertIn("Brak łączności z mikserem, stan mikrofonu nieznany", self.slowa())
        przed = len(self.serwer.rdzen.dziennik)
        self.serwer.rdzen.awarie.rozlaczony = False
        self.r._ost_proba = float("-inf")
        self.r.tick()
        self.assertTrue(self.r.stan.polaczony)
        zapisy = [d for d in self.serwer.rdzen.dziennik[przed:]]
        self.assertEqual(zapisy, [], "reconnect bez zapisów")
        self.assertTrue(self.slowa()[-1].startswith("Łączność z mikserem przywrócona"))

    def test_mierniki_przez_udp(self):
        """Subskrypcja /meters przez prawdziwe UDP, blok z symulatora, alarm ciszy,
        powrót dźwięku i brak mierników (to nie cisza). Czas prawdziwy, więc
        progi czasu skrócone w ustawieniach testu."""
        self.u.zachowanie["alarm_ciszy"].update(czas_s=0.4, powtorka_s=30.0)
        self.u.mierniki["limit_braku_s"] = 0.5
        self.r = Rdzen(self.u, self.klient, self.mowa, powierzchnia=AtrapaPowierzchni(), zegar=time.monotonic)
        self.assertTrue(self.r.start())
        self.slowa()

        def kreci(sekundy):
            koniec = time.monotonic() + sekundy
            mowa = []
            while time.monotonic() < koniec:
                self.r.tick()
                mowa += self.slowa()
                time.sleep(0.05)
            return mowa

        kreci(0.5)
        self.assertEqual(self.r.detektor.stan, "dzwiek")
        self.assertAlmostEqual(self.r.detektor.ostatni_db, -18.0, places=2)
        self.assertEqual(len(self.serwer.rdzen.subskrybenci_miernikow), 1)
        self.serwer.rdzen.cisza()
        self.assertIn("Cisza na antenie", kreci(1.0))
        self.serwer.rdzen.cisza(False)
        self.assertIn("Dźwięk na antenie wrócił", kreci(0.5))
        self.serwer.rdzen.mierniki_wylaczone = True
        mowa = kreci(1.2)
        self.assertIn("Mierniki niedostępne, alarm ciszy nie działa", mowa)
        self.assertNotIn("Cisza na antenie", mowa)
        self.assertEqual(self.r.bledy_miernikow, 0)

    def test_utrata_pakietow_udp(self):
        self.assertTrue(self.r.start())
        self.slowa()
        self.serwer.rdzen.awarie.zgub_nastepne = 2
        self.r.zglos(("klawisz", "F1_mikrofon"))
        self.assertEqual(self.serwer.rdzen.wartosci[sciezki.lr(9)], 1)
        self.assertEqual(self.slowa(), ["Mikrofon włączony"])

    def test_kontrola_nadawcy(self):
        """Pakiet z innego portu niż mikser jest ignorowany."""
        import socket
        self.assertTrue(self.r.start())
        obcy = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            gn = self.klient._subskrypcja._gniazdo.getsockname()
            obcy.sendto(osc.koduj(sciezki.lr(9), 1), gn)
            time.sleep(0.2)
            self.assertTrue(self.r._zgloszenia.empty())
        finally:
            obcy.close()


class TestSymulatorTylkoLokalnie(unittest.TestCase):
    def test_odmowa_adresu_nielokalnego(self):
        with self.assertRaises(ValueError):
            SerwerSymulatora(host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
