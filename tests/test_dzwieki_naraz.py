"""Dźwięki jednego komunikatu naraz (decyzja Michała z 23.10.2026, opcja 2).

Było: dźwięki komunikatu po kolei, np. „mikrofon poza anteną” i „głośniki
włączone” razem 0,48 s. Jest: oba ruszają w tej samej chwili, każdy na osobnym
wyjściu waveOut Windows, mowa rusza razem z nimi.

Oracle: oś czasu odtwarzacza i mowy (atrapy), lista wywołań fałszywego winmm.
"""
from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path

from pomoc import KATALOG, TestZSymulatorem
from mostek.informacja import (AtrapaDzwiekow, InformacjaZwrotna, OdtwarzaczWaveOut, OdtwarzaczWinsound,
                               Tryb)
from mostek.mowa import KolejkaMowy, Priorytet
from mostek.rdzen import Rdzen

DZW = KATALOG / "dzwieki"


class OsCzasu:
    """Odtwarzacz z kilkoma głosami, zapisuje oś czasu."""

    wiele_glosow = True

    def __init__(self, os_czasu, zawodzi=()):
        self.os = os_czasu
        self.zawodzi = set(zawodzi)

    def odtworz_wiele(self, pozycje):
        t = time.monotonic()
        wyniki = []
        for k, _ in pozycje:
            if k in self.zawodzi:
                wyniki.append(RuntimeError("awaria"))
            else:
                self.os.append(("dzwiek", k, t))
                wyniki.append(None)
        return wyniki

    def odtworz(self, klucz, plik):
        blad = self.odtworz_wiele([(klucz, plik)])[0]
        if blad:
            raise blad

    def zatrzymaj(self):
        self.os.append(("stop", None, time.monotonic()))


class Mowa:
    def __init__(self, os_czasu):
        self.os = os_czasu

    def mow(self, tekst):
        self.os.append(("mowa", tekst, time.monotonic()))


class Ust:
    """Minimalne ustawienia dla InformacjaZwrotna."""

    def __init__(self, tmp, naraz=True, czasy=None):
        self.plik_trybu = str(Path(tmp) / "tryb.json")
        self.informacja = {"katalog_dzwiekow": str(DZW), "dzwieki_naraz": naraz, "zdarzenia": {}}


def czekaj_na(warunek, limit=2.0):
    koniec = time.monotonic() + limit
    while time.monotonic() < koniec:
        if warunek():
            return True
        time.sleep(0.005)
    return False


class TestKolejkaNaraz(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.os = []

    def kolejka(self, naraz=True, zawodzi=()):
        info = InformacjaZwrotna(Ust(self._tmp.name, naraz), OsCzasu(self.os, zawodzi))
        k = KolejkaMowy(Mowa(self.os), alarm=None, dzwieki=info).start()
        self.addCleanup(k.stop)
        return k, info

    def test_dwa_dzwieki_ruszaja_razem(self):
        k, info = self.kolejka()
        self.assertTrue(info.naraz)
        k.powiedz("Mikrofon wyłączony. Głośniki włączone", Priorytet.STAN, "p",
                  dzwieki=["mikrofon_poza_antena", "glosniki_graja"], mow=False)
        self.assertTrue(czekaj_na(lambda: sum(e[0] == "dzwiek" for e in self.os) >= 2))
        d = [e for e in self.os if e[0] == "dzwiek"]
        self.assertEqual([e[1] for e in d], ["mikrofon_poza_antena", "glosniki_graja"])
        self.assertLess(d[1][2] - d[0][2], 0.02, "drugi dźwięk czeka na pierwszy")

    def test_nastepny_komunikat_po_najdluzszym_nie_po_sumie(self):
        """Komunikat samym dźwiękiem: następny po czasie najdłuższego (0,23 s),
        nie po sumie (0,46 s)."""
        k, info = self.kolejka()
        k.powiedz("A", Priorytet.STAN, "a", dzwieki=["mikrofon_poza_antena", "glosniki_graja"], mow=False)
        k.powiedz("B", Priorytet.STAN, "b", dzwieki=["sluchacz_czeka"], mow=False)
        self.assertTrue(czekaj_na(lambda: any(e[1] == "sluchacz_czeka" for e in self.os)))
        t0 = self.os[0][2]
        t2 = next(e[2] for e in self.os if e[1] == "sluchacz_czeka")
        najdluzszy = max(info.czas("mikrofon_poza_antena"), info.czas("glosniki_graja"))
        self.assertGreaterEqual(t2 - t0, najdluzszy - 0.01)
        self.assertLess(t2 - t0, info.czas("mikrofon_poza_antena") + info.czas("glosniki_graja") - 0.1)

    def test_mowa_razem_z_dzwiekami(self):
        k, _ = self.kolejka()
        k.powiedz("Mikrofon wyłączony", Priorytet.STAN, "p", dzwieki=["mikrofon_poza_antena", "glosniki_graja"],
                  mow=True)
        self.assertTrue(czekaj_na(lambda: any(e[0] == "mowa" for e in self.os)))
        self.assertEqual([e[0] for e in self.os[:3]], ["dzwiek", "dzwiek", "mowa"])
        self.assertLess(self.os[2][2] - self.os[0][2], 0.05)

    def test_zawiedziony_dzwiek_daje_mowe_a_reszta_gra(self):
        k, _ = self.kolejka(zawodzi={"glosniki_graja"})
        k.powiedz("Mikrofon wyłączony. Głośniki włączone", Priorytet.STAN, "p",
                  dzwieki=["mikrofon_poza_antena", "glosniki_graja"], mow=False)
        self.assertTrue(czekaj_na(lambda: any(e[0] == "mowa" for e in self.os)))
        self.assertEqual([(e[0], e[1]) for e in self.os[:2]],
                         [("dzwiek", "mikrofon_poza_antena"), ("mowa", "Mikrofon wyłączony. Głośniki włączone")])

    def test_ostrzezenie_przerywa_i_stan_wraca_w_calosci(self):
        k, _ = self.kolejka()
        k.powiedz("Słuchacz czeka. Głośniki", Priorytet.STAN, "s", dzwieki=["sluchacz_czeka", "glosniki_graja"],
                  mow=False)
        self.assertTrue(czekaj_na(lambda: len(self.os) >= 2))
        k.powiedz("Brak łączności", Priorytet.BEZPIECZENSTWO, "l", mow=True)
        self.assertTrue(czekaj_na(lambda: sum(e[0] == "dzwiek" for e in self.os) >= 4))
        r = [(e[0], e[1]) for e in self.os]
        self.assertEqual(r[2:4], [("stop", None), ("mowa", "Brak łączności")])
        self.assertEqual(r[4:6], [("dzwiek", "sluchacz_czeka"), ("dzwiek", "glosniki_graja")])

    def test_wylaczone_w_ustawieniach_po_kolei(self):
        k, info = self.kolejka(naraz=False)
        self.assertFalse(info.naraz)
        k.powiedz("A", Priorytet.STAN, "a", dzwieki=["mikrofon_poza_antena", "glosniki_graja"], mow=False)
        self.assertTrue(czekaj_na(lambda: sum(e[0] == "dzwiek" for e in self.os) >= 2))
        d = [e for e in self.os if e[0] == "dzwiek"]
        self.assertGreaterEqual(d[1][2] - d[0][2], info.czas("mikrofon_poza_antena") - 0.01)

    def test_po_kolei_zawiedziony_dzwiek_daje_mowe(self):
        """Ścieżka po kolei (dzwieki_naraz false, winsound): nieudany dźwięk
        nadal daje mowę zamiast dźwięku."""
        k, info = self.kolejka(naraz=False, zawodzi={"mikrofon_poza_antena", "glosniki_graja"})
        k.powiedz("Mikrofon wyłączony. Głośniki włączone", Priorytet.STAN, "p",
                  dzwieki=["mikrofon_poza_antena", "glosniki_graja"], mow=False)
        self.assertTrue(czekaj_na(lambda: any(e[0] == "mowa" for e in self.os)))
        self.assertEqual([e[1] for e in self.os if e[0] == "mowa"], ["Mikrofon wyłączony. Głośniki włączone"])

    def test_winsound_jeden_glos_po_kolei(self):
        info = InformacjaZwrotna(Ust(self._tmp.name, True), OdtwarzaczWinsound(FalszywyWinsound()))
        self.assertFalse(info.naraz, "winsound gra jeden plik naraz")


class FalszywyWinsound:
    SND_FILENAME, SND_ASYNC, SND_NODEFAULT = 0x20000, 0x1, 0x2

    def PlaySound(self, *a):  # noqa: N802
        pass


class TestZRdzeniem(TestZSymulatorem):
    """Prawdziwa ścieżka komunikatu: rdzeń -> plan -> kolejka -> odtwarzacz."""

    def test_mikrofon_poza_antena_rozmowa_jedna_grupa(self):
        self.dzwieki = AtrapaDzwiekow()
        self.info = InformacjaZwrotna(self.u, self.dzwieki)
        self.info.tryb = Tryb.DZWIEKI
        self.mowa = KolejkaMowy(self.wyjscie, alarm=None, dzwieki=self.info)
        self.r = Rdzen(self.u, self.klient, self.mowa, powierzchnia=self.pow, zegar=self.zegar, sen=self.zegar.sen)
        self.assertTrue(self.r.synchronizuj(nowa_baza_galek=True))
        self.mowa.oproznij()
        self.dzwieki.naraz.clear()
        self.r.mowa.powiedz("Mikrofon poza anteną, rozmowa ze słuchaczem", Priorytet.STAN, "x",
                            dzwieki=["mikrofon_poza_antena", "sluchacz_cue"], mow=False)
        self.mowa.oproznij()
        self.assertIn(["mikrofon_poza_antena", "sluchacz_cue"], self.dzwieki.naraz)


# --- waveOut na fałszywym winmm ------------------------------------------------

class FalszywaFunkcja:
    def __init__(self, mm, nazwa):
        self.mm, self.nazwa = mm, nazwa
        self.argtypes = self.restype = None

    def __call__(self, *a):
        return self.mm.wywolaj(self.nazwa, a)


class FalszyweWinmm:
    def __init__(self, kody=None):
        self.wywolania = []
        self.kody = kody or {}
        self._n = 0
        for n in ("waveOutOpen", "waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite",
                  "waveOutReset", "waveOutClose"):
            setattr(self, n, FalszywaFunkcja(self, n))

    def wywolaj(self, nazwa, a):
        import ctypes
        if nazwa == "waveOutOpen":
            self._n += 1
            a[0]._obj.value = 1000 + self._n
            fmt = a[2]._obj
            self.wywolania.append((nazwa, 1000 + self._n, fmt.nSamplesPerSec, fmt.nChannels, fmt.wBitsPerSample))
        else:
            uchwyt = a[0].value if isinstance(a[0], ctypes.c_void_p) else a[0]
            self.wywolania.append((nazwa, uchwyt))
        kod = self.kody.get(nazwa, 0)
        return kod(self._n) if callable(kod) else kod


class TestWaveOut(unittest.TestCase):
    def test_dwa_wyjscia_najpierw_otwarte_potem_wyslane(self):
        mm = FalszyweWinmm()
        o = OdtwarzaczWaveOut(mm)
        w = o.odtworz_wiele([("a", DZW / "mikrofon_poza_antena.wav"), ("b", DZW / "glosniki_graja.wav")])
        self.assertEqual(w, [None, None])
        nazwy = [x[0] for x in mm.wywolania]
        self.assertEqual(nazwy, ["waveOutOpen", "waveOutPrepareHeader", "waveOutOpen", "waveOutPrepareHeader",
                                 "waveOutWrite", "waveOutWrite"])
        self.assertEqual(mm.wywolania[0][2:], (48000, 1, 16))
        self.assertNotEqual(mm.wywolania[0][1], mm.wywolania[2][1], "każdy dźwięk na osobnym wyjściu")

    def test_zatrzymaj_resetuje_i_zamyka_wszystkie(self):
        mm = FalszyweWinmm()
        o = OdtwarzaczWaveOut(mm)
        o.odtworz_wiele([("a", DZW / "mikrofon_poza_antena.wav"), ("b", DZW / "glosniki_graja.wav")])
        mm.wywolania.clear()
        o.zatrzymaj()
        nazwy = [x[0] for x in mm.wywolania]
        self.assertEqual(nazwy.count("waveOutReset"), 2)
        self.assertEqual(nazwy.count("waveOutClose"), 2)
        self.assertEqual(o._aktywne, [])

    def test_zakonczone_wyjscia_sprzatane_przy_nastepnym(self):
        mm = FalszyweWinmm()
        o = OdtwarzaczWaveOut(mm)
        o.odtworz("a", DZW / "alarm.wav")
        o._aktywne[0][1].dwFlags |= OdtwarzaczWaveOut.WHDR_DONE
        mm.wywolania.clear()
        o.odtworz("b", DZW / "odmowa.wav")
        self.assertEqual([x[0] for x in mm.wywolania][:2], ["waveOutUnprepareHeader", "waveOutClose"])
        self.assertEqual(len(o._aktywne), 1)

    def test_blad_otwarcia_jednego_nie_blokuje_drugiego(self):
        mm = FalszyweWinmm(kody={"waveOutOpen": lambda n: 2 if n == 1 else 0})
        o = OdtwarzaczWaveOut(mm)
        w = o.odtworz_wiele([("a", DZW / "mikrofon_poza_antena.wav"), ("b", DZW / "glosniki_graja.wav")])
        self.assertIsInstance(w[0], OSError)
        self.assertIsNone(w[1])
        self.assertEqual([x[0] for x in mm.wywolania].count("waveOutWrite"), 1)

    def test_plik_wczytany_raz(self):
        mm = FalszyweWinmm()
        o = OdtwarzaczWaveOut(mm)
        for _ in range(3):
            o.odtworz("a", DZW / "alarm.wav")
        self.assertEqual(len(o._pamiec), 1)

    def test_rownolegle_watki_bez_bledu(self):
        mm = FalszyweWinmm()
        o = OdtwarzaczWaveOut(mm)
        bledy = []

        def gra():
            try:
                for _ in range(20):
                    o.odtworz("a", DZW / "alarm.wav")
                    o.zatrzymaj()
            except Exception as e:  # noqa: BLE001
                bledy.append(e)
        w = [threading.Thread(target=gra) for _ in range(4)]
        for x in w:
            x.start()
        for x in w:
            x.join()
        self.assertEqual(bledy, [])


if __name__ == "__main__":
    unittest.main()
