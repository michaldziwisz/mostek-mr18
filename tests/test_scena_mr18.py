"""Realne UDP do wiernego modelu repo scena @86316cb; bez sprzętu."""
import contextlib
import io
import json
from pathlib import Path
from typing import Callable
import socket
import tempfile
import threading
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narzedzia import scena_mr18 as s
from narzedzia import prosty_start as start
from mikser_rejestrujacy import Model, pack, unpack, stan_startowy as _stan_startowy

REPO = Path(__file__).resolve().parents[1]
SCHEMAT = REPO / 'dane_sceny/schemat-mr18.json'
# Scena w zapisie AOSC, z której nagrano tests/dane_sceny/aosc-v4-set.json.
BAZA_AOSC = REPO / 'tests/dane_sceny/baza-aosc-v4.scn'


def stan_startowy():
    """Stan modelu przed testem: BAZA_AOSC ze zmianami ZMIANY_STARTU, w zapisie
    modelu. Różni się od BAZY, więc START musi ją wczytać."""
    tekst = _stan_startowy(BAZA_AOSC, SCHEMAT)
    with tempfile.TemporaryDirectory() as d:
        plik = Path(d) / 'start.scn'
        plik.write_text(tekst, encoding='utf-8')
        Model(plik, SCHEMAT)          # model musi umieć wczytać własny zapis
    return tekst


START = stan_startowy().encode('utf-8')


class Serwer:
    def __init__(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'start.scn'
            p.write_bytes(START)
            self.model = Model(p, SCHEMAT)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(.05)
        self.stop = threading.Event()
        self.pakiety = []
        self.pomin: str | None = None
        self.zmien: str | None = None
        self.przed_zapisem: Callable[[], None] | None = None
        self.watek = threading.Thread(target=self.run)
        self.watek.start()

    def run(self):
        while not self.stop.is_set():
            try:
                raw, peer = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            for path, typ, args in unpack(raw):
                self.pakiety.append((path, typ, args))
                if path == '/node' and '/' + args[0] == self.pomin:
                    continue
                zapis = args and (path == '/' or path in self.model.rows)
                if zapis and self.przed_zapisem:
                    self.przed_zapisem()
                if zapis and self.zmien and (path == self.zmien or (path == '/' and args[0].startswith(self.zmien + ' '))):
                    # Odtwarzalna awaria: mikser nie przyjmuje węzła.
                    continue
                for a, t, v in self.model.respond(path, typ, args):
                    self.sock.sendto(pack(a, v, t), peer)

    def close(self):
        self.stop.set(); self.watek.join(2); self.sock.close()

    def zapisy(self):
        return [p for p in self.pakiety if p[0] == '/' or (p[2] and p[0] != '/node')]


class ScenaMR18(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.srv = Serwer()
        self.addCleanup(self.srv.close)
        # Nie zalewamy UDP, zwłaszcza gdy serwer zapisuje dowody na dysk.
        # Produkcja ma 10 ms, w tej kontrolce 3 ms i większy limit na planistę.
        self.c = s.Polaczenie('127.0.0.1', self.srv.port, symulator=True, timeout=.3, proby=3, odstep=.003)
        self.addCleanup(self.c.sock.close)
        self.wezly = s.zakres()
        self.schema = s.wczytaj_schemat()

    def wczytaj(self, plik=None, **kwargs):
        return s.wczytaj(self.c, plik or REPO / 'dane_sceny/BAZA.scn', self.dir,
                         self.wezly, self.schema, mow=lambda x: None, **kwargs)

    def test_datagramy_bazy_identczne_z_prawdziwym_aosc(self):
        dane = json.loads((REPO / 'tests/dane_sceny/aosc-v4-set.json').read_text())['pakiety']
        rows = s.czytaj_scn(BAZA_AOSC.read_text())
        self.assertEqual(len(dane), 693)
        self.assertEqual(set(dane), set(rows))
        # Po pomiarze na MR18V2 fw 1.19 (18.10.2026) BAZA ma -6 dB także na drugiej
        # szynie linkowanej pary Bus 3/4. Zapis AOSC pochodzi ze starszej BAZY,
        # więc te 6 węzłów porównujemy z nowym poziomem, resztę bajt w bajt.
        po_pomiarze = {f'/ch/{k:02d}/mix/{4 if k % 2 else 3:02d}' for k in range(1, 7)}
        for path, pakiet in dane.items():
            nowy = s.pakiet_wezla(path, rows, self.schema)
            if path in po_pomiarze:
                self.assertEqual(nowy.hex()[:48], pakiet['hex'][:48], path)
                self.assertEqual(nowy.hex()[48:56], '3f19999a', path)   # 0.6 = -6 dB
                self.assertEqual(nowy.hex()[56:], pakiet['hex'][56:], path)
            else:
                self.assertEqual(nowy.hex(), pakiet['hex'], path)

    def test_tekstowy_tylko_symulator_i_pelna_weryfikacja(self):
        with self.assertRaises(ValueError):
            s.Polaczenie('127.0.0.1', tekstowy=True)
        self.c.tekstowy = True
        r = self.wczytaj()
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['zgodne'], 693)
        self.assertEqual(len([x for x in self.srv.pakiety if x[0] == '/']), 693)

    def test_factory_kopia_bajt_w_bajt(self):
        self.assertEqual(self.c.xinfo()[2], 'MR18')
        p = s.kopia(self.c, self.dir, self.wezly, self.schema)
        self.assertEqual(p.read_bytes(), START)
        self.assertEqual(self.srv.zapisy(), [])
        self.assertEqual(len([p for p in self.srv.pakiety if p[0] == '/node']), 693)

    def test_zapis_dopiero_po_kompletnej_kopii(self):
        stan_przy_zapisie = []
        def sprawdz():
            kopie = list(self.dir.glob('*.scn'))
            stan_przy_zapisie.append(len(kopie) == 1 and kopie[0].read_bytes() == START)
        self.srv.przed_zapisem = sprawdz
        r = self.wczytaj()
        self.assertTrue(stan_przy_zapisie and all(stan_przy_zapisie))
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['zgodne'], 693)
        self.assertEqual(r['oczekiwane'], 693)
        self.assertEqual(Path(r['kopia']).read_bytes(), START)
        self.assertEqual(len(self.srv.model.node_writes), 693)
        for a in s.solo_adresy():
            self.assertEqual(self.srv.model.values[a], ('i', 0))

    def test_przywrocenie_odtwarza_stan_sprzed(self):
        r = self.wczytaj()
        kopia = s.ostatnia_kopia(self.dir)
        r2 = self.wczytaj(kopia, przywracanie=True)
        self.assertTrue(r2['ok'], r2)
        self.assertEqual(r2['zgodne'], 693)
        odczyt = ''.join(self.c.node(p) for p in self.wezly).encode()
        aktualne = s.czytaj_scn(odczyt.decode())
        pierwotne = s.czytaj_scn(START.decode('utf-8'))
        self.assertEqual(set(aktualne), set(pierwotne))
        for path in self.wezly:
            self.assertTrue(s.zgodne(path, pierwotne[path], aktualne[path], self.schema, pierwotne), path)
        self.assertEqual(s.ostatnia_kopia(self.dir), kopia)
        self.assertNotEqual(r['kopia'], r2['kopia'])

    def test_brak_odpowiedzi_przerywa_bez_jakiegokolwiek_zapisu(self):
        self.srv.pomin = self.wezly[10]
        with self.assertRaisesRegex(s.BladSceny, 'Brak odpowiedzi'):
            self.wczytaj()
        self.assertEqual(self.srv.zapisy(), [])
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_weryfikacja_wykrywa_zepsuta_linie(self):
        self.srv.zmien = '/ch/10/dyn'
        r = self.wczytaj()
        self.assertFalse(r['ok'])
        self.assertEqual(r['zgodne'], 692)
        self.assertEqual([w['wezel'] for w in r['rozbieznosci']], ['/ch/10/dyn'])
        self.assertEqual(len([p for p in self.srv.pakiety if p[0] == '/node']), 1386)

    def test_kopia_nigdy_nie_nadpisuje(self):
        with patch.object(s, 'datetime') as d:
            d.now.return_value.strftime.return_value = '20261018-120000'
            pierwsza = s.kopia(self.c, self.dir, self.wezly, self.schema)
            przed = pierwsza.read_bytes()
            self.srv.model.respond('/ch/01/config/name', 's', ['INNA NAZWA'])
            druga = s.kopia(self.c, self.dir, self.wezly, self.schema)
        self.assertNotEqual(pierwsza, druga)
        self.assertEqual(pierwsza.read_bytes(), przed)
        self.assertNotEqual(druga.read_bytes(), przed)

    def test_blad_zapisu_kopii_nie_zmienia_miksera(self):
        with patch.object(s.os, 'fsync', side_effect=OSError('pełny dysk')):
            with self.assertRaises(OSError):
                self.wczytaj()
        self.assertEqual(self.srv.zapisy(), [])
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_uszkodzony_plik_odrzucony_przed_kopia_i_set(self):
        p = self.dir / 'uszkodzona.scn'
        p.write_text((BAZA_AOSC).read_text().replace('COMP', 'NIEISTNIEJACY', 1))
        with self.assertRaises(s.BladPlikuSceny):
            self.wczytaj(p)
        self.assertEqual(self.srv.zapisy(), [])
        self.assertEqual(len(self.srv.pakiety), 0)

    def test_scena_z_aosc_z_powtorzonymi_wierszami_wczytuje_sie(self):
        """Scena zapisana w AOSC z prawdziwym MR18 (Michał, 21.10.2026):
        1076 wierszy, 383 identyczne powtórzenia (np. /ch/01/gate/filter po
        /ch/01/gate). Stary kod odrzucał ją: „powtórzony adres”."""
        p = REPO / 'tests/dane_sceny/aosc-mr18-michal-powtorzenia.scn'
        wiersze = [w for w in p.read_text(encoding='utf-8-sig').splitlines() if w.strip()]
        self.assertEqual(len(wiersze), 1076)
        r = self.wczytaj(p)
        self.assertTrue(r['ok'], r['rozbieznosci'][:3])
        self.assertEqual(r['zgodne'], 693)
        adresy = [a for a, _, args in self.srv.zapisy() if a != '/node']
        self.assertEqual(len(adresy), len(set(adresy)), "każdy węzeł wysłany raz")
        self.assertEqual(float(self.srv.model.rows['/headamp/09'][0]), 41.5, "gain Michała w mikserze")

    def test_powtorzony_adres_z_inna_wartoscia_odrzucony_bez_zapisu(self):
        p = self.dir / 'sprzeczna.scn'
        tekst = (BAZA_AOSC).read_text(encoding='utf-8-sig')
        linia = next(w for w in tekst.splitlines() if w.startswith('/headamp/09 '))
        p.write_text(tekst + '/headamp/09 +10.0 ON\n', encoding='utf-8')
        with self.assertRaises(s.BladPlikuSceny) as e:
            self.wczytaj(p)
        self.assertIn('inną wartością', str(e.exception))
        self.assertTrue(linia)
        self.assertEqual(len(self.srv.pakiety), 0, "odrzucony przed połączeniem z mikserem")

    def test_start_zly_plik_mowi_ze_nic_nie_zapisal(self):
        zly = self.dir / 'scena'
        zly.mkdir()
        (zly / 'schemat-mr18.json').write_bytes(SCHEMAT.read_bytes())
        (zly / 'BAZA.scn').write_text('/ch/01/config "x" 0 In01 U01\n', encoding='utf-8')
        wyjscie = io.StringIO()
        with patch.object(s, 'KATALOG', self.dir), patch.object(s, 'DANE', zly), \
             patch.object(s, 'Polaczenie', return_value=self.c), \
             patch.object(s, 'znajdz_miksery', return_value=[]), \
             patch.object(start, 'pytanie', side_effect=['127.0.0.1', 'TAK']), \
             patch.object(s, 'zakres', return_value=self.wezly), \
             patch.object(s, 'Schemat', return_value=self.schema), \
             contextlib.redirect_stdout(wyjscie):
            self.assertEqual(start.main(['start']), 1)
        self.assertIn('Niczego nie zapisano do miksera', wyjscie.getvalue())
        self.assertEqual(self.srv.zapisy(), [])
        self.assertFalse(list((self.dir / 'kopie').glob('*.scn')) if (self.dir / 'kopie').exists() else [])

    def test_normalizacja_nie_zmienia_nazw_enumow_ani_wartosci(self):
        rows = s.czytaj_scn(START.decode('utf-8'))
        path = '/ch/01/mix'
        a = rows[path].copy(); a[1] = '0.0'
        b = a.copy(); b[1] = '-0.0'
        self.assertTrue(s.zgodne(path, a, b, self.schema, rows))
        b[1] = '0.1'
        self.assertFalse(s.zgodne(path, a, b, self.schema, rows))
        path = '/ch/01/dyn'; a = rows[path]; b = a.copy(); b[5] = '2'
        self.assertFalse(s.zgodne(path, a, b, self.schema, rows))
        path = '/ch/01/config'; a = rows[path]; b = a.copy(); b[0] = 'inna nazwa'
        self.assertFalse(s.zgodne(path, a, b, self.schema, rows))

    def test_symulator_nie_pozwala_wyjsc_poza_loopback(self):
        with self.assertRaises(ValueError):
            s.Polaczenie('192.0.2.1', symulator=True)

    def test_blokada_wspolnego_startu_i_przywracania(self):
        with start.blokada(self.dir):
            with self.assertRaises(s.BladSceny):
                with start.blokada(self.dir):
                    self.fail('druga blokada')
        with start.blokada(self.dir):
            pass

    def test_przywroc_anulowanie_nie_zapisuje(self):
        self.wczytaj()
        przed = len(self.srv.zapisy())
        with patch.object(s, 'KATALOG', self.dir), patch.object(s, 'Polaczenie', return_value=self.c), \
             patch.object(s, 'znajdz_miksery', return_value=[]), \
             patch.object(start, 'pytanie', side_effect=['127.0.0.1', '']), \
             patch.object(start.scena, 'ostatnia_kopia', return_value=s.ostatnia_kopia(self.dir)), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(start.main(['przywroc']), 2)
        self.assertEqual(len(self.srv.zapisy()), przed)

    def test_rozbieznosci_domyslnie_nie_uruchamiaja_mostka(self):
        self.srv.zmien = '/ch/10/dyn'
        with patch.object(s, 'KATALOG', self.dir), patch.object(s, 'Polaczenie', return_value=self.c), \
             patch.object(s, 'znajdz_miksery', return_value=[]), \
             patch.object(start, 'pytanie', side_effect=['127.0.0.1', '']), \
             patch.object(start.glowny, 'main') as mostek, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(start.main(['start']), 3)
            mostek.assert_not_called()


    # --- RESTART i START bez zbędnego wczytania (Michał, 23.10.2026 19:13) ---
    def _start(self, tryb, odpowiedzi):
        wyjscie = io.StringIO()
        pyt = contextlib.nullcontext() if odpowiedzi is None else patch.object(start, 'pytanie', side_effect=odpowiedzi)
        with patch.object(s, 'KATALOG', self.dir), patch.object(s, 'Polaczenie', return_value=self.c), \
             patch.object(s, 'znajdz_miksery', return_value=[]), pyt, \
             patch.object(start.glowny, 'main', return_value=0) as mostek, contextlib.redirect_stdout(wyjscie):
            kod = start.main([tryb])
        raport = json.loads(next((self.dir / 'wyniki').glob(tryb + '-*.json')).read_text(encoding='utf-8'))
        return kod, mostek, wyjscie.getvalue(), raport

    def test_restart_uruchamia_mostek_bez_zadnego_zapisu(self):
        """Objaw: dwa START w trakcie audycji wczytały BAZĘ. RESTART nie pyta
        o zgodę, nie robi kopii i nie wysyła do miksera ani jednego zapisu."""
        kod, mostek, out, raport = self._start('restart', ['127.0.0.1'])
        self.assertEqual(kod, 0)
        mostek.assert_called_once()
        self.assertEqual(self.srv.zapisy(), [])
        self.assertEqual([p for p in self.srv.pakiety if p[0] == '/node'], [])
        self.assertFalse((self.dir / 'kopie').exists() and list((self.dir / 'kopie').iterdir()))
        self.assertIn('Niczego nie zapisuję do miksera', out)
        self.assertEqual(raport['operacja'], 'restart')
        self.assertIs(raport['zapis_do_miksera'], False)

    def test_start_mikser_zgodny_z_baza_niczego_nie_wczytuje(self):
        self.wczytaj()                                 # mikser już na BAZIE
        przed = len(self.srv.zapisy())
        kod, mostek, out, raport = self._start('start', ['127.0.0.1'])
        self.assertEqual(kod, 0)
        mostek.assert_called_once()
        self.assertEqual(len(self.srv.zapisy()), przed, 'zgodny mikser nie dostaje zapisu')
        self.assertIn('Mikser zgodny z BAZĄ (693/693)', out)
        self.assertEqual(len(list(self.dir.glob('KOPIA-*.scn'))), 1, 'tylko kopia z self.wczytaj()')
        self.assertEqual(raport['porownanie_z_baza']['rozbieznosci'], [])

    def test_start_rozny_od_bazy_wczytuje_bez_pytania(self):
        """Michał, 23.10.2026: START wczytuje BAZĘ bez potwierdzania. Jedyne
        pytanie to adres, gdy nie ma jednego miksera w sieci (tu: zero)."""
        with patch.object(start, 'pytanie', side_effect=['127.0.0.1']) as pyt:
            kod, mostek, out, raport = self._start('start', None)
        self.assertEqual(pyt.call_count, 1)
        self.assertEqual(kod, 0)
        mostek.assert_called_once()
        self.assertIn('Mikser różni się od BAZY', out)
        self.assertEqual(len(self.srv.model.node_writes), 693)
        self.assertTrue(raport['ok'])
        self.assertTrue(raport['wczytanie_bez_pytania'])
        self.assertEqual(raport['zgodne'], 693)
        self.assertEqual(len(list(self.dir.glob('kopie/KOPIA-PRZED-BAZA-*.scn'))), 1, 'kopia przed zapisem')

    def test_start_zgodny_ale_wlaczone_solo_wczytuje_i_wylacza(self):
        self.wczytaj()
        adres = s.solo_adresy()[0]
        self.srv.model.respond(adres, 'i', [1])
        kod, mostek, out, raport = self._start('start', ['127.0.0.1'])
        self.assertEqual(kod, 0)
        mostek.assert_called_once()
        self.assertIn('Włączone solo: ' + adres, out)
        self.assertEqual(raport['porownanie_z_baza']['solo_wlaczone'], [adres])
        self.assertEqual(self.srv.model.values[adres], ('i', 0))

    def test_jeden_mikser_bez_pytania_przy_start_i_restart(self):
        for tryb in ('start', 'restart'):
            # Każdy przebieg zamyka swoje połączenie: osobne gniazdo na tryb.
            c = s.Polaczenie('127.0.0.1', self.srv.port, symulator=True, timeout=.3, proby=3, odstep=.003)
            self.addCleanup(c.sock.close)
            with patch.object(s, 'znajdz_miksery', return_value=[('127.0.0.1', ['127.0.0.1', 'MR18', 'MR18', '1.26'])]), \
                 patch.object(s, 'KATALOG', self.dir), patch.object(s, 'Polaczenie', return_value=c), \
                 patch.object(start, 'pytanie') as pyt, \
                 patch.object(start.glowny, 'main', return_value=0) as mostek, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(start.main([tryb]), 0, tryb)
            pyt.assert_not_called()
            mostek.assert_called_once()

    def test_opis_roznic_czytelny(self):
        tekst = start.opis_roznic([{'wezel': '/ch/07/mix', 'oczekiwane': ['ON', '-oo', 'ON', '-100.0000'],
                                    'odczyt': '/ch/07/mix ON -22.2 ON -100.0000\n', 'blad': None}])
        self.assertEqual(tekst, '  /ch/07/mix: w mikserze ON -22.2 ON -100.0000, w BAZIE ON -oo ON -100.0000')

    def test_xinfo_nie_wymaga_modelu_mr18(self):
        """Prawdziwy MR18 (pomiar 18.10.2026) nie przeszedł dawnego warunku
        'ssss' + 'MR18'. Identyfikację potwierdza dopiero pełna kopia /node."""
        for odp in (('s', ['192.168.1.21']), ('ssss', ['V1.17', 'MR18-0A-1B-2C', 'XR18', '1.17'])):
            self.srv.model.respond = (lambda orig, o: lambda path, typ, args:
                [('/xinfo', o[0], o[1])] if path == '/xinfo' else orig(path, typ, args))(Model.respond.__get__(self.srv.model), odp)
            self.assertEqual(self.c.xinfo(), odp[1])

    def test_wyszukiwanie_znajduje_mikser_po_xinfo(self):
        z = s.znajdz_miksery(czas=.5, port=self.srv.port, cele=[('127.0.0.1', '127.0.0.1')])
        self.assertEqual([ip for ip, _ in z], ['127.0.0.1'])
        self.assertEqual(z[0][1][2], 'MR18')
        self.assertEqual(self.srv.zapisy(), [])
        self.assertEqual([p[0] for p in self.srv.pakiety], ['/xinfo'])

    def test_wyszukiwanie_bez_odpowiedzi_zwraca_pusto(self):
        wolny = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); wolny.bind(('127.0.0.1', 0))
        port = wolny.getsockname()[1]; wolny.close()
        self.assertEqual(s.znajdz_miksery(czas=.2, port=port, cele=[('127.0.0.1', '127.0.0.1')]), [])

    def test_wybor_adresu_jeden_mikser_enter(self):
        dane = {}
        with patch.object(s, 'znajdz_miksery', return_value=[('192.168.1.21', ['192.168.1.21', 'MR18', 'MR18', '1.17'])]), \
             patch.object(start, 'pytanie') as pyt, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(start.wybierz_adres(dane, False), '192.168.1.21')
        pyt.assert_not_called()
        self.assertIn('Znalazłem mikser: 192.168.1.21 (MR18, MR18, 1.17)', out.getvalue())
        self.assertEqual(dane['znalezione'][0]['ip'], '192.168.1.21')

    def test_wybor_adresu_kilka_numer_i_brak(self):
        z = [('192.168.1.21', ['a']), ('192.168.1.22', ['b'])]
        with patch.object(s, 'znajdz_miksery', return_value=z), patch.object(start, 'pytanie', side_effect=['2']), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(start.wybierz_adres({}, False), '192.168.1.22')
        with patch.object(s, 'znajdz_miksery', return_value=[]), patch.object(start, 'pytanie', side_effect=['10.0.0.5']), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(start.wybierz_adres({}, False), '10.0.0.5')
        self.assertIn('Nie znalazłem miksera automatycznie.', out.getvalue())


    def test_node_dwie_linie_jak_prawdziwy_mr18(self):
        """MR18V2 fw 1.19 w pomiarze (18.10.2026) na /node ch/01/gate odsyła też
        linię /ch/01/gate/filter w tym samym pakiecie. Kopia i weryfikacja
        mają przejść, a kopia zostać bajt w bajt równa stanowi miksera."""
        orig = Model.respond.__get__(self.srv.model)
        def respond(path, typ, args):
            w = orig(path, typ, args)
            if path == '/node' and args and str(args[0]).rstrip('/').endswith(('/gate', '/dyn')):
                filtr = orig('/node', 's', [str(args[0]) + '/filter'])
                if w and filtr:
                    a, t, v = w[0]
                    return [(a, t, [v[0] + filtr[0][2][0]])]
            return w
        self.srv.model.respond = respond
        self.assertIn('/ch/01/gate/filter', self.c.dodatkowe_linie.get('/ch/01/gate', [''])[0]
                      if self.c.node('/ch/01/gate') else '')
        p = s.kopia(self.c, self.dir, self.wezly, self.schema)
        self.assertEqual(p.read_bytes(), START)
        r = self.wczytaj()
        self.assertTrue(r['ok'], r['rozbieznosci'][:3])
        self.assertEqual(r['zgodne'], 693)


    def test_zgodnosc_tego_samego_kroku_skali_jak_mr18(self):
        """MR18V2 fw 1.19 (pomiar 18.10.2026) odczytuje 1k97 jako 1k98, 79 jako
        79.3, 200.5 jako 200. To ten sam krok skali i nie jest rozbieżnością."""
        rows = s.czytaj_scn((BAZA_AOSC).read_text())
        for path, linia in (('/ch/01/eq/3', '/ch/01/eq/3 PEQ 1k98  0.00 2.0'),
                            ('/ch/09/preamp', '/ch/09/preamp 0.0 OFF OFF ON 79.3'),
                            ('/ch/10/preamp', '/ch/10/preamp 0.0 OFF OFF ON 100')):
            odczyt = s.czytaj_scn(linia + '\n')[path]
            self.assertTrue(s.zgodne(path, rows[path], odczyt, self.schema, rows), path)
        # Inny krok skali nadal jest rozbieżnością.
        odczyt = s.czytaj_scn('/ch/01/eq/3 PEQ 2k05  0.00 2.0\n')['/ch/01/eq/3']
        self.assertFalse(s.zgodne('/ch/01/eq/3', rows['/ch/01/eq/3'], odczyt, self.schema, rows))
        odczyt = s.czytaj_scn('/ch/01/mix/04  -6.0 OFF POST\n')['/ch/01/mix/04']
        zle = dict(rows); zle['/ch/01/mix/04'] = ['-oo', 'OFF', 'POST']
        self.assertFalse(s.zgodne('/ch/01/mix/04', zle['/ch/01/mix/04'], odczyt, self.schema, zle))


if __name__ == '__main__':
    unittest.main()
