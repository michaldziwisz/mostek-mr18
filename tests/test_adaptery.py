"""Adaptery za interfejsami: X-TOUCH MC, mowa, StationPlaylist, nadzorca, ustawienia."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from pomoc import KATALOG, TestZSymulatorem, sciezki, wczytaj_ustawienia
from mostek import emisja, ustawienia
from mostek.mowa import AtrapaMowy, BladMowy, BrakNVDA, KolejkaMowy, MowaNVDA, Priorytet
from mostek.nadzorca import Nadzorca
from mostek.xtouch import AtrapaPortuMIDI, MapaMC, PowierzchniaXTouch


class TestMapaMC(unittest.TestCase):
    def setUp(self):
        self.mapa = MapaMC(ustawienia.wczytaj().xtouch)

    def test_przyciski_paskow(self):
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x00, 0x7F))), ("przycisk", 1, 0))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x09, 0x7F))), ("przycisk", 2, 1))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x12, 0x7F))), ("przycisk", 3, 2))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x1B, 0x7F))), ("przycisk", 4, 3))

    def test_zwolnienie_nie_jest_zdarzeniem(self):
        self.assertIsNone(self.mapa.zdarzenie(bytes((0x90, 0x00, 0x00))))
        self.assertIsNone(self.mapa.zdarzenie(bytes((0x80, 0x00, 0x40))))
        self.assertIsNone(self.mapa.zdarzenie(bytes((0x90, 0x36, 0x00))))

    def test_klawisze_f_i_transport(self):
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x36, 0x7F))), ("klawisz", "F1_mikrofon"))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x3D, 0x7F))), ("klawisz", "F8_odczytaj_powierzchnie"))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x5E, 0x7F))), ("klawisz", "transport_play"))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x5D, 0x7F))), ("klawisz", "transport_stop"))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x2E, 0x7F))), ("klawisz", "bank_lewo_odtwarzacz"))

    def test_galka_i_wcisniecie(self):
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x21, 0x7F))), ("galka_wcisnij", 2))
        self.assertEqual(self.mapa.zdarzenie(bytes((0xB0, 0x11, 0x01))), [("galka", 2, 1)])
        self.assertEqual(self.mapa.zdarzenie(bytes((0xB0, 0x12, 0x43))), [("galka", 3, -1)] * 3)

    def test_suwaki_i_dotyk(self):
        self.assertEqual(self.mapa.zdarzenie(bytes((0xE0, 0x7F, 0x7F))), ("suwak", 1, 1.0))
        self.assertEqual(self.mapa.zdarzenie(bytes((0xE8, 0x00, 0x00))), ("suwak", 9, 0.0))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x68, 0x7F))), ("dotyk", 1, True))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x68, 0x00))), ("dotyk", 1, False))
        self.assertEqual(self.mapa.zdarzenie(bytes((0x90, 0x70, 0x7F))), ("dotyk", 9, True))

    def test_wyjscie_diody_silniki_pierscienie(self):
        self.assertEqual(self.mapa.dioda(1, 0, True), bytes((0x90, 0x00, 0x7F)))
        self.assertEqual(self.mapa.dioda(2, 3, False), bytes((0x90, 0x19, 0x00)))
        self.assertEqual(self.mapa.dioda(1, 0, None), bytes((0x90, 0x00, 0x01)))
        self.assertEqual(self.mapa.silnik(1, 1.0), bytes((0xE0, 0x7F, 0x7F)))
        self.assertEqual(self.mapa.silnik(9, 0.0), bytes((0xE8, 0x00, 0x00)))
        self.assertEqual(self.mapa.pierscien(2, 0.5), bytes((0xB0, 0x31, 0x06)))


class TestXTouchZRdzeniem(TestZSymulatorem):
    def test_midi_do_miksera_i_diody(self):
        port = AtrapaPortuMIDI()
        self.r.powierzchnia = PowierzchniaXTouch(MapaMC(self.u.xtouch), port, self.r.zglos)
        port.wstrzyknij(0x90, 0x36, 0x7F)        # F1
        port.wstrzyknij(0x90, 0x36, 0x00)        # zwolnienie: bez drugiej operacji
        self.assertTrue(self.suma("mikrofon"))
        self.assertIn(bytes((0x90, 0x18, 0x7F)), port.wyslane, "dioda SELECT paska 1")
        self.zegar.przesun(0.2)
        przed = self.m(sciezki.fader(9))
        port.wstrzyknij(0xE0, 0x00, 0x00)        # ruch bez dotyku (silnik): pomijany
        self.assertEqual(self.m(sciezki.fader(9)), przed)
        port.wstrzyknij(0x90, 0x68, 0x7F)        # dotyk suwaka 1
        port.wstrzyknij(0xE0, 0x00, 0x00)        # suwak 1 na dół
        port.wstrzyknij(0x90, 0x68, 0x00)
        self.assertEqual(float(self.m(sciezki.fader(9))), 0.0)


class TestMowa(unittest.TestCase):
    def test_bezpieczenstwo_przed_reszta(self):
        a = AtrapaMowy()
        k = KolejkaMowy(a, alarm=None)
        k.powiedz("informacja", Priorytet.INFORMACJA)
        k.powiedz("stan", Priorytet.STAN)
        k.powiedz("uwaga", Priorytet.BEZPIECZENSTWO)
        k.oproznij()
        self.assertEqual(a.powiedziane, ["uwaga", "stan", "informacja"])

    def test_nowy_komunikat_zastepuje_stary_o_tym_samym_kluczu(self):
        a = AtrapaMowy()
        k = KolejkaMowy(a, alarm=None)
        k.powiedz("Mikrofon włączony", klucz="m")
        k.powiedz("Mikrofon wyłączony", klucz="m")
        k.oproznij()
        self.assertEqual(a.powiedziane, ["Mikrofon wyłączony"])

    def test_awaria_mowy_to_alarm_nie_wyjatek(self):
        a = AtrapaMowy()
        a.awaria = True
        alarmy = []
        k = KolejkaMowy(a, alarm=lambda: alarmy.append(1))
        k.powiedz("x")
        k.oproznij()
        self.assertEqual(k.bledy_mowy, 1)
        self.assertEqual(alarmy, [1])

    def test_watek_mowy(self):
        a = AtrapaMowy()
        k = KolejkaMowy(a, alarm=None).start()
        k.powiedz("raz")
        koniec = time.monotonic() + 2
        while not a.powiedziane and time.monotonic() < koniec:
            time.sleep(0.01)
        k.stop()
        self.assertEqual(a.powiedziane, ["raz"])

    @unittest.skipIf(sys.platform == "win32", "sprawdza strażnik importu poza Windows")
    def test_nvda_poza_windows_niedostepne(self):
        with self.assertRaises(BrakNVDA):
            MowaNVDA()


class TestStationPlaylist(unittest.TestCase):
    def test_kody_sendmessage(self):
        wyslane = []

        def wyslij(w, l):
            wyslane.append((w, l))
            return 1

        spl = emisja.StationPlaylist(wyslij)
        spl.start_nastepnego()
        spl.stop_wyciszenie()
        spl.stop_natychmiast()
        self.assertEqual(spl.stan(), "gra")
        self.assertEqual(wyslane, [(0, 14), (0, 13), (1, 13), (0, 104)])

    def test_brak_okna(self):
        spl = emisja.StationPlaylist(lambda w, l: None)
        self.assertIsNone(spl.stan())

    def test_sara_ma_adapter_tcp(self):
        self.assertIsInstance(emisja.SARA(), emisja.ProgramTCP)


class TestTransportZRdzeniem(TestZSymulatorem):
    def test_play_i_podwojny_stop(self):
        self.r.emisja = emisja.AtrapaEmisji()
        od = len(self.sym.dziennik)
        self.klawisz("transport_play")
        self.assertEqual(self.slowa(), ["Gra"])
        self.klawisz("transport_stop")
        self.slowa()
        self.zegar.przesun(0.3)
        self.r.zglos(("klawisz", "transport_stop"))
        self.slowa()
        self.assertEqual(self.r.emisja.polecenia, ["play", "stop_wyciszenie", "stop_natychmiast"])
        self.assertEqual(self.zapisy(od), [], "transport nie zmienia miksera")

    def test_sara_niedostepna(self):
        from tests.atrapa_playoutu import zamkniety_port
        self.r.emisja = emisja.SARA(zamkniety_port())
        self.klawisz("transport_play")
        self.assertEqual(self.slowa(), ["Program emisyjny nie potwierdził wyniku. Sprawdź jego stan"])

    def test_bez_programu_emisyjnego(self):
        self.r.emisja = None
        self.klawisz("transport_play")
        self.assertEqual(self.slowa(), ["Nie wybrano programu emisyjnego"])
        self.klawisz("transport_stop")
        self.assertEqual(self.slowa(), [], "brak programu nie zalewa komunikatami")

    def test_program_nie_odpowiada(self):
        self.r.emisja = emisja.AtrapaEmisji()
        self.r.emisja.odpowiada = False
        self.klawisz("transport_play")
        self.assertEqual(self.slowa(), ["Program emisyjny nie potwierdził wyniku. Sprawdź jego stan"])


class AtrapaProcesu:
    def __init__(self, polecenie):
        self.polecenie = polecenie
        self.kod = None
        self.zabity = False

    def poll(self):
        return self.kod

    def kill(self):
        self.zabity = True
        self.kod = -9

    def terminate(self):
        self.kod = 0

    def wait(self, timeout=None):
        return self.kod


class TestNadzorca(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]
        self.procesy = []
        self.a = AtrapaMowy()
        self.k = KolejkaMowy(self.a, alarm=None)

        def uruchom(pol):
            p = AtrapaProcesu(pol)
            self.procesy.append(p)
            return p

        self.n = Nadzorca(["mostek"], self.k, limit_ciszy_s=2.0, maks_restartow=2, okno_restartow_s=100,
                          uruchom=uruchom, zegar=lambda: self.t[0])
        self.n.uruchom_mostek()

    def tearDown(self):
        self.n.zamknij()

    def test_sygnal_zycia_przez_udp(self):
        import socket
        g = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.t[0] = 1.9
        g.sendto(b"zyje", ("127.0.0.1", self.n.port))
        time.sleep(0.05)
        self.assertEqual(self.n.krok(), "ok")
        self.t[0] = 3.5
        self.assertEqual(self.n.krok(), "ok", "sygnał przesunął limit")
        g.close()

    def test_zawieszenie_ogloszenie_i_restart(self):
        self.t[0] = 2.5
        self.assertEqual(self.n.krok(), "restart")
        self.assertTrue(self.procesy[0].zabity)
        self.assertEqual(len(self.procesy), 2)
        self.assertIn("--nadzorca-port", self.procesy[1].polecenie)
        self.k.oproznij()
        self.assertEqual(self.a.powiedziane[0], "Sterowanie nie odpowiada, mikrofon może być na antenie")

    def test_limit_restartow(self):
        for i in range(3):
            self.t[0] += 3
            wynik = self.n.krok()
        self.assertEqual(wynik, "zatrzymany")
        self.assertEqual(len(self.procesy), 3)


class TestAwaryjnyMikrofon(unittest.TestCase):
    def test_zdejmuje_mikrofon_z_anteny_wobec_symulatora(self):
        sys.path.insert(0, str(KATALOG / "narzedzia"))
        import mikrofon_poza_antena as mpa
        from mostek.klient import KlientMR18
        from mostek.symulator import SerwerSymulatora
        from mostek.transport import TransportUDP
        s = SerwerSymulatora(port=0).start()
        try:
            s.rdzen.wartosci[sciezki.lr(9)] = 1
            k = KlientMR18(TransportUDP(*s.adres), limit_odpowiedzi_s=0.2)
            ok, tekst = mpa.wykonaj(k, [9])
            k.zamknij()
            self.assertTrue(ok)
            self.assertEqual(s.rdzen.wartosci[sciezki.lr(9)], 0)
            self.assertEqual(s.rdzen.wartosci[sciezki.mute_kanalu(9)], 1, "bez --wycisz rozmowa zostaje")
            self.assertEqual(tekst, "Mikrofon poza anteną, potwierdzone przez mikser")
            s.rdzen.awarie.rozlaczony = True
            k = KlientMR18(TransportUDP(*s.adres), limit_odpowiedzi_s=0.05)
            ok, tekst = mpa.wykonaj(k, [9])
            k.zamknij()
            self.assertFalse(ok)
            self.assertIn("może być na antenie", tekst)
        finally:
            s.stop()


class TestUstawienia(unittest.TestCase):
    def test_plik_poprawny_i_czytelny(self):
        u = ustawienia.wczytaj()
        self.assertEqual(u.zrodla["mikrofon"].kanaly, (9,))
        self.assertEqual(u.odbiorcy["zoom"].szyny, (3, 4))
        self.assertEqual(u.szyna_podsluchu, 2)

    def _odrzuca(self, zmiana):
        dane = json.loads(ustawienia.DOMYSLNE_USTAWIENIA.read_text(encoding="utf-8"))
        zmiana(dane)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(dane), encoding="utf-8")
            with self.assertRaises(ustawienia.BladUstawien):
                ustawienia.wczytaj(p, ustawienia.DOMYSLNE_POZIOMY)

    def test_mapa_paska_v20(self):
        u = ustawienia.wczytaj()
        self.assertEqual(u.paski[1]["select"], "antena_mikrofonu")
        self.assertEqual(u.paski[1]["rec"], "alarm_ciszy")
        self.assertEqual(u.paski[2]["select"], "cue")
        self.assertEqual(u.paski[3]["select"], "cue")
        self.assertEqual(u.paski[4]["select"], "pfl")
        self.assertEqual(u.prog_suwaka_db, -50.0)
        self.assertEqual(u.przyciszenie_muzyki_db, -15.0)
        self.assertNotIn("tryby", u.surowe, "bez trybów S1-S7")
        for nazwa in u.xtouch["klawisze"].values():
            self.assertFalse(nazwa.startswith(("F4_r", "F5_p", "F6_r", "F7_t")), nazwa)

    def test_suwak_maks_mikrofonu_i_zakres(self):
        u = ustawienia.wczytaj()
        self.assertEqual(u.zrodla["mikrofon"].suwak_maks_db, 10.0)
        for zr in ("telefon", "zoom", "muzyka1", "muzyka2", "muzyka3"):
            self.assertEqual(u.zrodla[zr].suwak_maks_db, 0.0, zr)
        self._odrzuca(lambda d: d["zrodla"]["mikrofon"].update(suwak_maks_db=12.0))
        self._odrzuca(lambda d: d["zrodla"]["telefon"].update(suwak_maks_db=-3.0))

    def test_usb_suche_nigdy_na_emisji_ani_zoomie(self):
        u = ustawienia.wczytaj()
        self.assertEqual(u.profil["usb_suche_dozwolone"], list(range(5, 19)))
        for wy in (1, 2, 3, 4):
            self._odrzuca(lambda d, wy=wy: d["profil"]["usb_suche_dozwolone"].append(wy))
        self._odrzuca(lambda d: d["profil"].update(usb_suche_dozwolone=[19]))

    def test_odrzuca_alarm_ciszy_poza_rec(self):
        self._odrzuca(lambda d: d["paski"][1].update(select="alarm_ciszy"))

    def test_odrzuca_cue_na_pasku_muzyki(self):
        self._odrzuca(lambda d: d["paski"][3].update(select="cue"))

    def test_odrzuca_rec_anteny_poza_mikrofonem(self):
        self._odrzuca(lambda d: d["paski"][1].update(rec="antena_mikrofonu"))

    def test_odrzuca_select_anteny_poza_mikrofonem(self):
        self._odrzuca(lambda d: d["paski"][1].update(select="antena_mikrofonu"))

    def test_odrzuca_zle_zycie_kontrolera(self):
        self._odrzuca(lambda d: d["xtouch"].update(zycie_s=0.05))
        self._odrzuca(lambda d: d["xtouch"].update(zycie_proby=0))

    def test_plan_v22_szyny_i_mechanizmy(self):
        u = ustawienia.wczytaj()
        self.assertEqual(u.szyny_glosnikow, (6,))
        self.assertEqual(u.szyna_klucza, 5)
        self.assertEqual(u.zrodla_klucza, ("mikrofon", "zoom"))
        self.assertEqual(u.sluchacz, "telefon")
        self.assertEqual(u.paski[1]["mute"], "kaszel")
        self.assertEqual(u.przypomnienie_mikrofonu_min, 0, "przypomnienie domyślnie wyłączone")
        self.assertEqual(u.alarm_ciszy["prog_dbfs"], -50.0)
        self.assertEqual(u.alarm_ciszy["czas_s"], 10.0)
        self.assertEqual(u.alarm_ciszy["powtorka_s"], 30.0)

    def test_odrzuca_klucz_na_glosnikach(self):
        self._odrzuca(lambda d: d["szyny"].update(glosniki=[5, 6]))

    def test_odrzuca_kaszel_poza_mikrofonem(self):
        self._odrzuca(lambda d: d["paski"][1].update(mute="kaszel"))

    def test_odrzuca_sluchacza_w_kluczu(self):
        self._odrzuca(lambda d: d["przyciszanie"].update(zrodla_klucza=["mikrofon", "telefon"]))

    def test_odrzuca_zly_prog_ciszy(self):
        self._odrzuca(lambda d: d["zachowanie"]["alarm_ciszy"].update(prog_dbfs=10.0))

    def test_odrzuca_przyciszenie_poza_zakresem(self):
        self._odrzuca(lambda d: d["zachowanie"].update(przyciszenie_muzyki_cue_db=-80.0))

    def test_odrzuca_podwojny_kanal(self):
        dane = json.loads(ustawienia.DOMYSLNE_USTAWIENIA.read_text(encoding="utf-8"))
        dane["zrodla"]["muzyka3"]["kanaly"] = [9, 6]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(dane), encoding="utf-8")
            with self.assertRaises(ustawienia.BladUstawien):
                ustawienia.wczytaj(p, ustawienia.DOMYSLNE_POZIOMY)

    def test_wszystkie_klucze_komunikatow_istnieja(self):
        import re
        u = ustawienia.wczytaj()
        kod = "".join(p.read_text(encoding="utf-8") for p in (KATALOG / "mostek").glob("*.py"))
        uzyte = set(re.findall(r'self\.t\("([a-z_0-9]+)"', kod)) | set(re.findall(r'u\.tekst\("([a-z_0-9]+)"', kod))
        brak = sorted(k for k in uzyte if k not in u.komunikaty)
        self.assertEqual(brak, [])


class TestPunktWejscia(unittest.TestCase):
    def test_mostek_z_symulatorem_startuje_i_konczy(self):
        with tempfile.TemporaryDirectory() as d:
            poziomy = Path(d) / "p.json"
            poziomy.write_text(ustawienia.DOMYSLNE_POZIOMY.read_text(encoding="utf-8"), encoding="utf-8")
            wynik = subprocess.run(
                [sys.executable, "-m", "mostek", "--symulator", "--dziennik", str(Path(d) / "m.log"),
                 "--poziomy", str(poziomy)],
                input="f2\nkoniec\n", capture_output=True, text=True, timeout=30, cwd=KATALOG)
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertIn("SYMULATOR MR18", wynik.stdout)
        self.assertIn("[mowa] Mikrofon wyłączony. Słuchacz czeka. Zoom czeka.", wynik.stdout)


if __name__ == "__main__":
    unittest.main()
