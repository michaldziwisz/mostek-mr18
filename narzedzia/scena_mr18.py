"""Kopia i wczytywanie scen MR18, oddzielone od zapory mostka (stdlib).

Odczyt: XAirGetScene.c 137–156, /node z nazwą bez początkowego '/'.
Odpowiedź ma adres 'node' i jeden string, zachowywany w kopii bez formatowania.
Zapis domyślny: typowane SET węzłów według własnego schematu
dane_sceny/schemat-mr18.json (pomiar na MR18), zgodne z datagramami AOSC
zapisanymi w tests/dane_sceny/aosc-v4-set.json.
Opcjonalny zapis tekstowy wyłącznie w symulatorze: '/' + string. Obsługuje go
model tests/mikser_rejestrujacy.py. Zapis tekstowy wymaga osobnego odbioru na
firmware MR18.
Nie wywołujemy /snap, /-snap ani /-action. Mostek nie importuje tego narzędzia.

Kopia obejmuje 693 węzły z listy "wezly" schematu, nie pamięć snapshotów ani stany
runtime solo. Wczytywanie nie jest transakcją. Po błędzie nie ma automatycznego
rollbacku. Zachowana kopia umożliwia jawne przywrócenie poza anteną.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mostek import sciezki
from mostek.osc import koduj, dekoduj, BladOSC
from narzedzia.format_scn import BladSceny as BladFormatu, Schemat, czytaj_scn, num

KATALOG = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
DANE = KATALOG / ('scena' if getattr(sys, 'frozen', False) else 'dane_sceny')


class BladSceny(RuntimeError):
    pass


SCHEMAT = 'schemat-mr18.json'


def zakres(plik=None):
    """Lista węzłów sceny w kolejności zapisu: z pola "wezly" schematu JSON
    albo z pliku tekstowego, jedna ścieżka w wierszu."""
    plik = Path(plik) if plik else DANE / SCHEMAT
    tekst = plik.read_text(encoding='utf-8-sig')
    if tekst.lstrip().startswith('{'):
        wezly = json.loads(tekst).get('wezly', [])
    else:
        wezly = tekst.splitlines()
    if len(wezly) != 693 or len(set(wezly)) != 693 or any(not re.fullmatch(r'/[A-Za-z0-9/-]+', w) for w in wezly):
        raise BladSceny('Uszkodzony zakres sceny. Oczekiwano 693 różnych węzłów.')
    return wezly


def solo_adresy():
    # Zakres wynika z rejestru, nie z nieudokumentowanej komendy clearsolo.
    return [sciezki.solo(n) for n in range(100) if sciezki.w_rejestrze(sciezki.solo(n))]


def sprawdz_adres(adres, symulator=False):
    ip = ipaddress.IPv4Address(adres)
    if ip.is_unspecified or ip.is_multicast or str(ip) == '255.255.255.255':
        raise ValueError('Podaj adres jednego miksera, nie adres rozgłoszeniowy.')
    if symulator and str(ip) != '127.0.0.1':
        raise ValueError('Tryb symulatora działa wyłącznie na 127.0.0.1.')
    return str(ip)


def adresy_rozgloszeniowe():
    """Cele zapytania /xinfo przy wyszukiwaniu: 255.255.255.255 z każdego
    lokalnego adresu IPv4 oraz adres x.y.z.255 tej sieci (typowe /24)."""
    lokalne = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            lokalne.add(info[4][0])
    except OSError:
        pass
    lokalne = sorted(a for a in lokalne if not a.startswith('127.') and not a.startswith('169.254.'))
    cele = []
    for a in lokalne:
        cele.append((a, '255.255.255.255'))
        cele.append((a, a.rsplit('.', 1)[0] + '.255'))
    if not cele:
        cele.append(('', '255.255.255.255'))
    return cele


def znajdz_miksery(czas=1.5, port=10024, cele=None):
    """Wysyła /xinfo (odczyt, bez argumentów) jak AOSC i zbiera odpowiedzi.

    Zwraca listę (adres_ip, argumenty) bez powtórzeń. `cele` to lista par
    (adres_lokalny, adres_docelowy); domyślnie adresy rozgłoszeniowe.
    Niczego nie zapisuje w żadnym urządzeniu."""
    cele = cele if cele is not None else adresy_rozgloszeniowe()
    gniazda, znalezione = [], {}
    try:
        for lokalny, cel in cele:
            g = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            g.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                g.bind((lokalny, 0))
                g.sendto(koduj('/xinfo'), (cel, port))
            except OSError:
                g.close()
                continue
            g.setblocking(False)
            gniazda.append(g)
        koniec = time.monotonic() + czas
        while gniazda and time.monotonic() < koniec:
            for g in gniazda:
                try:
                    raw, (ip, _port) = g.recvfrom(65535)
                except (BlockingIOError, ConnectionResetError, OSError):
                    continue
                try:
                    for w in dekoduj(raw):
                        if w.adres in ('/xinfo', '/info') and ip not in znalezione:
                            znalezione[ip] = [str(a) for a in w.argumenty]
                except BladOSC:
                    continue
            time.sleep(.02)
    finally:
        for g in gniazda:
            g.close()
    return sorted(znalezione.items())


def opis_miksera(ip, argumenty):
    reszta = [a for a in argumenty if a and a != ip]
    return f'{ip} ({", ".join(reszta)})' if reszta else ip


class Polaczenie:
    def __init__(self, adres, port=10024, *, symulator=False, timeout=.6, proby=3, odstep=.01, tekstowy=False):
        if tekstowy and not symulator:
            raise ValueError("Zapis tekstowy jest niepotwierdzony dla MR18. Tylko --symulator.")
        self.tekstowy = tekstowy
        self.pakiety = {}
        self.adres = sprawdz_adres(adres, symulator)
        self.port, self.timeout, self.proby, self.odstep = port, timeout, proby, odstep
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # connect filtruje źródło odpowiedzi. Bez broadcastu i skanowania sieci.
        self.sock.connect((self.adres, port))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.sock.close()

    def wyslij(self, adres, *args):
        self.sock.send(koduj(adres, *args))

    def pytaj(self, adres, args=(), pasuje=None):
        # Usuń stare odpowiedzi/echo, żeby nie uznać ich za nowy odczyt.
        self.sock.setblocking(False)
        try:
            while self.sock.recv(65535):
                pass
        except (BlockingIOError, ConnectionResetError, ConnectionRefusedError):
            pass
        for _ in range(self.proby):
            self.wyslij(adres, *args)
            koniec = time.monotonic() + self.timeout
            while time.monotonic() < koniec:
                self.sock.settimeout(max(.001, koniec - time.monotonic()))
                try:
                    raw = self.sock.recv(65535)
                    # Wyjątek protokołu X AIR lokalny dla narzędzia. Kodek
                    # i zapora mostka nadal wymagają adresu z '/'.
                    if raw.startswith(b'node\0\0\0\0'):
                        raw = b'/node\0\0\0' + raw[8:]
                    wiadomosci = dekoduj(raw)
                except (socket.timeout, ConnectionResetError, ConnectionRefusedError):
                    break
                except BladOSC:
                    continue
                for w in wiadomosci:
                    if (pasuje(w) if pasuje else w.adres == adres):
                        return w
        raise BladSceny(f'Brak odpowiedzi: {adres} {" ".join(map(str, args))}'.strip())

    def xinfo(self):
        """Odpowiedź /xinfo potwierdza tylko, że pod adresem jest mikser X AIR.

        Nie wymagamy dokładnego modelu ani liczby pól: prawdziwy MR18 z pomiaru
        (18.10.2026) odpowiedział inaczej niż symulator i dawny warunek
        'ssss' z modelem 'MR18' przerwał start. Rzeczywistą tożsamość sprawdza
        kopia: 693 odczyty /node przed jakimkolwiek zapisem. Urządzenie, które
        nie zna /node, przerywa kopię bez zapisu.
        """
        w = self.pytaj('/xinfo')
        self.xinfo_surowe = {'typy': w.typy, 'argumenty': [str(a) for a in w.argumenty]}
        return [str(a) for a in w.argumenty]

    def node(self, path):
        """Odczyt jednego węzła przez /node.

        Prawdziwy MR18 (pomiar 18.10.2026, MR18V2 fw 1.19) na /node ch/01/gate
        odsyła w jednym pakiecie DWIE linie: węzeł i jego /filter. Autor AOSC
        opisał to samo (forum azslow.com, temat 595, 27.04.2024: „mixer is
        sending filter for Gate and Compressor when not asked explicitly”).
        Bierzemy linię pytanego węzła, dodatkowe linie zapisujemy w
        self.dodatkowe_linie (każdy z tych węzłów i tak czytamy osobno)."""
        def linie(w):
            return [l for l in w.argumenty[0].replace('\r', '').split('\n') if l.strip()]

        def pasuje(w):
            return (w.adres == '/node' and w.typy == 's' and len(w.argumenty) == 1
                    and any(l.split(maxsplit=1)[0:1] == [path] for l in linie(w)))
        w = self.pytaj('/node', (path.lstrip('/'),), pasuje)
        if '\x00' in w.argumenty[0]:
            raise BladSceny(f'Uszkodzona odpowiedź węzła {path}')
        wlasne = [l for l in linie(w) if l.split(maxsplit=1)[0:1] == [path]]
        if len(wlasne) != 1:
            raise BladSceny(f'Niejednoznaczna odpowiedź węzła {path}')
        inne = [l for l in linie(w) if l not in wlasne]
        if inne:
            if not hasattr(self, 'dodatkowe_linie'):
                self.dodatkowe_linie = {}
            self.dodatkowe_linie[path] = inne
        return wlasne[0] + '\n'

    def zapisz_linie(self, linia):
        if self.tekstowy:
            self.wyslij('/', linia.rstrip('\r\n'))
        else:
            self.sock.send(self.pakiety[linia.split(maxsplit=1)[0]])
        time.sleep(self.odstep)

    def aktywne_solo(self):
        """Tylko odczyt: adresy solo włączone w mikserze (albo bez odpowiedzi)."""
        wlaczone = []
        for adres in solo_adresy():
            try:
                w = self.pytaj(adres)
                if w.typy != 'i' or w.argumenty != (0,):
                    wlaczone.append(adres)
            except BladSceny:
                wlaczone.append(adres)
        return wlaczone

    def wylacz_solo(self):
        bledy = []
        for adres in solo_adresy():
            self.wyslij(adres, 0)
            time.sleep(self.odstep)
            try:
                w = self.pytaj(adres)
                if w.typy != 'i' or w.argumenty != (0,):
                    bledy.append(adres)
            except BladSceny:
                bledy.append(adres)
        return bledy


def wczytaj_schemat():
    return Schemat((DANE / SCHEMAT).read_text(encoding='utf-8'))


def wartosc_osc(spec, token):
    """Skale ze schematu sceny; zaokrąglenie do kroków zmierzonych na MR18.

    Kroki 0 albo brak: wartość dokładna, zaokrągla sam mikser. Dla FX
    schemat zależy od typu. Test porównuje pełne datagramy z zapisem AOSC.
    """
    kind, param = spec
    if kind == 's': return 's', token
    if kind == 'b': return 'i', int(token == 'ON')
    if kind == 'm': return 'i', param.split(';').index(token)
    if kind == 'g': return 'i', int(token[1:], 2)
    if kind == 'z': return 'f', 0.0
    v = num(token)
    if kind == 'x':
        if v == float('-inf'): val = 0.0
        elif v >= -10: val = (v + 30) / 40
        elif v >= -30: val = (v + 50) / 80
        elif v >= -60: val = (v + 70) / 160
        else: val = (v + 90) / 480
        if not param:
            return 'f', val
        steps = int(param)
    else:
        lo, hi, steps = map(float, param.split(','))
        val = (v - lo) / (hi - lo) if kind == 'l' else math.log(v / lo) / math.log(hi / lo)
        if not steps:
            return 'f', val
    return 'f', round(val * steps) / steps


def pakiet_wezla(path, rows, schemat):
    pary = [wartosc_osc(spec, token) for spec, token in zip(schemat.pola(path, rows), rows[path])]
    return koduj(path, *(v for _, v in pary), typy=''.join(t for t, _ in pary))


def pelna_scena(tekst, wezly, schemat):
    rows = czytaj_scn(tekst)
    if set(rows) != set(wezly):
        raise BladSceny('Plik nie obejmuje dokładnie 693 węzłów sceny MR18.')
    schemat.sprawdz(rows)
    return rows


def liczba(token):
    if token == '-oo':
        return Decimal('-Infinity')
    if 'k' in token:
        return Decimal(token.replace('k', '.')) * 1000
    return Decimal(token)


def zgodne(path, oczekiwane, odczyt, schemat, rows):
    """Białe znaki poza nazwą oraz zapis liczb, bez tolerancji wartości.

    FORMAT-NODE.md: +0.0, -0.0 i 0 to to samo; 1k97 = 1970 Hz.
    Enumy (także ratio '2.0'), nazwy i maski porównujemy DOSŁOWNIE.
    Nie zamieniamy niezgodnego kroku/zaokrąglenia w sukces.
    """
    fields = schemat.pola(path, rows)
    if len(oczekiwane) != len(odczyt) or len(fields) != len(odczyt):
        return False

    def rowne(spec, a, b):
        if spec[0] in 'sbmgz':
            return a == b
        if liczba(a) == liczba(b):
            return True
        # Prawdziwy MR18 (pomiar 18.10.2026) odczytuje ten sam krok skali
        # innym tekstem: 1k97 jako 1k98, 79 jako 79.3, 200.5 jako 200.
        # Rozstrzyga wartość OSC po kwantyzacji schematu, czyli to, co mikser
        # faktycznie trzyma. Inny krok skali nadal jest rozbieżnością.
        return wartosc_osc(spec, a) == wartosc_osc(spec, b)
    return all(rowne(spec, a, b) for spec, a, b in zip(fields, oczekiwane, odczyt))


def kopia(polaczenie, katalog, wezly, schemat, *, przed='BAZA'):
    # Cały odczyt i walidacja muszą się udać przed utworzeniem pliku i SET.
    tekst = ''.join(polaczenie.node(path) for path in wezly)
    pelna_scena(tekst, wezly, schemat)
    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)
    nazwa = 'KOPIA-PRZED-' + przed + '-' + datetime.now().strftime('%Y%m%d-%H%M%S')
    for n in range(10000):
        plik = katalog / (nazwa + (f'-{n:04d}' if n else '') + '.scn')
        try:
            f = plik.open('xb')  # BEZ_NADPISANIA
        except FileExistsError:
            continue
        try:
            with f:
                f.write(tekst.encode('utf-8'))
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            plik.unlink(missing_ok=True)  # wyłącznie własny niedokończony plik
            raise
        return plik
    raise BladSceny('Nie udało się wybrać nowej nazwy kopii. Niczego nie zapisano do miksera.')


def weryfikuj(polaczenie, rows, wezly, schemat):
    raport = {'oczekiwane': len(wezly), 'zgodne': 0, 'rozbieznosci': []}
    for path in wezly:
        try:
            linia = polaczenie.node(path)
            odczyt = czytaj_scn(linia)[path]
            ok = zgodne(path, rows[path], odczyt, schemat, rows)
            blad = None
        except (BladSceny, ValueError, KeyError, ArithmeticError) as e:
            ok, linia, blad = False, None, str(e)
        if ok:
            raport['zgodne'] += 1
        else:
            raport['rozbieznosci'].append({'wezel': path, 'oczekiwane': rows[path],
                                          'odczyt': linia, 'blad': blad})
    return raport


class BladPlikuSceny(BladSceny):
    """Plik sceny odrzucony przed kopią i przed jakimkolwiek zapisem do miksera."""


def wiersze_pliku(plik, wezly, schemat):
    """Plik sceny sprawdzony jak przy wczytaniu, bez kontaktu z mikserem."""
    try:
        tekst = Path(plik).read_text(encoding='utf-8-sig')
        return pelna_scena(tekst, wezly, schemat)
    except (OSError, UnicodeError, BladSceny, BladFormatu) as e:
        raise BladPlikuSceny(f'plik {Path(plik).name}: {e}') from e


def wczytaj(polaczenie, plik, katalog_kopii, wezly, schemat, *, przywracanie=False, mow=print):
    rows = wiersze_pliku(plik, wezly, schemat)
    tekst = Path(plik).read_text(encoding='utf-8-sig')
    polaczenie.pakiety = {p: pakiet_wezla(p, rows, schemat) for p in wezly}
    zapisane = kopia(polaczenie, katalog_kopii, wezly, schemat,
                     przed='PRZYWROC' if przywracanie else 'BAZA')  # KOPIA_PRZED_ZAPISEM
    mow(f'Kopia gotowa: {zapisane.name}')
    # Wysyłamy tylko pełne, zwalidowane węzły, w kolejności schematu (typ FX przed par).
    linie = {}
    for w in tekst.splitlines():
        if w.startswith('/'):
            linie.setdefault(w.split(maxsplit=1)[0], w)    # powtórzenia są identyczne (czytaj_scn)
    for path in wezly:
        polaczenie.zapisz_linie(linie[path])
    raport = weryfikuj(polaczenie, rows, wezly, schemat)  # WERYFIKACJA_PO_ZAPISIE
    raport.update(kopia=str(zapisane), plik=str(plik), adres=polaczenie.adres)
    mow(f'Weryfikacja sceny: {raport["zgodne"]}/{raport["oczekiwane"]} zgodnych.')
    mow('Wyłączam solo kanałów 1 do 16 i szyn 1 do 6. To osobny krok poza sceną.')
    raport['solo_bledy'] = polaczenie.wylacz_solo()
    raport['ok'] = not raport['rozbieznosci'] and not raport['solo_bledy']
    mow('Solo wyłączone i sprawdzone.' if not raport['solo_bledy'] else 'Nie potwierdzono wyłączenia wszystkich solo.')
    return raport


def ostatnia_kopia(katalog):
    # Kopia przed PRZYWROC zabezpiecza bieżący stan, ale nie przesłania
    # oryginalnej kopii sprzed BAZY przy następnym PRZYWROC.
    pliki = list(Path(katalog).glob('KOPIA-PRZED-BAZA-*.scn'))
    if not pliki:
        raise BladSceny('Nie ma kopii sprzed BAZY. Niczego nie zmieniono.')
    return max(pliki, key=lambda p: (p.stat().st_mtime_ns, p.name))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operacja', choices=('polaczenie', 'kopia', 'wczytaj', 'przywroc'))
    p.add_argument('plik', nargs='?', type=Path)
    p.add_argument('--mr18', required=True)
    p.add_argument('--port', type=int, default=10024)
    p.add_argument('--symulator', action='store_true', help='osobny model na 127.0.0.1, nie sprzęt')
    p.add_argument('--tekstowy', action='store_true', help='eksperyment tylko z --symulator')
    p.add_argument('--kopie', type=Path, default=KATALOG / 'kopie')
    p.add_argument('--raport', type=Path)
    p.add_argument('--zapisz', action='store_true', help='zezwól na kopię i zmianę miksera')
    a = p.parse_args(argv)
    try:
        wezly = zakres()
        schemat = wczytaj_schemat()
        if a.operacja != 'polaczenie' and not a.zapisz:
            print('Bez --zapisz: niczego nie zmieniono. Wczytanie zmienia routing i phantom.')
            return 2
        with Polaczenie(a.mr18, a.port, symulator=a.symulator, tekstowy=a.tekstowy) as c:
            c.xinfo()
            if a.operacja == 'polaczenie':
                print('MR18 odpowiada. Połączenie działa.')
                return 0
            if a.operacja == 'kopia':
                print('Kopia: ' + str(kopia(c, a.kopie, wezly, schemat)))
                return 0
            plik = a.plik or (ostatnia_kopia(a.kopie) if a.operacja == 'przywroc' else None)
            if plik is None:
                raise BladSceny('Podaj plik sceny.')
            r = wczytaj(c, plik, a.kopie, wezly, schemat, przywracanie=a.operacja == 'przywroc')
        raport = a.raport or KATALOG / 'wyniki' / ('scena-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        raport.parent.mkdir(parents=True, exist_ok=True)
        with raport.open('x', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print('Raport: ' + str(raport))
        return 0 if r['ok'] else 3
    except (OSError, ValueError, BladSceny, KeyError) as e:
        print(f'Przerwano: {e}. Jeśli trwał zapis, stan może być częściowy. Zachowaj kopię.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
