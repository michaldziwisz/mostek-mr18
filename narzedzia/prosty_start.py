"""Rozmowa prostego START/PRZYWROC. Bez powłoki dla adresu ani zgody.

MOSTEK_TEST_SYMULATOR=1 służy wyłącznie do cichego odbioru na 127.0.0.1:
bez NVDA, audio i portu MIDI, z normalnym połączeniem OSC do osobnego modelu.
Nie zastępuje testu prawdziwego kontrolera. Normalny start: NVDA i WinMM.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narzedzia import scena_mr18 as scena
from mostek import glowny


@contextmanager
def blokada(katalog):
    """Blokada systemowa, zwalniana również po śmierci procesu."""
    p = Path(katalog) / 'prosty-start.lock'
    with p.open('a+b') as f:
        f.seek(0, 2)
        if f.tell() == 0:
            f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise scena.BladSceny('START lub PRZYWROC już działa. Najpierw zakończ mostek poleceniem koniec') from e
        try:
            yield
        finally:
            f.seek(0)
            if sys.platform == 'win32':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def pytanie(tekst):
    try:
        return input(tekst + '\n').strip()
    except EOFError:
        return ''


def wybierz_adres(dane, test, bez_pytania=True):
    """Jak AOSC: najpierw szukamy miksera w sieci, adres ręczny zostaje zapasem.

    Jeden znaleziony mikser bierzemy od razu (Michał, 23.10.2026: bez pytań
    przy START i RESTART). Pytamy tylko przy kilku albo żadnym."""
    if test:
        return pytanie('Adres IP MR18:')
    print('Szukam miksera w sieci...')
    znalezione = scena.znajdz_miksery()
    dane['znalezione'] = [{'ip': ip, 'xinfo': a} for ip, a in znalezione]
    if len(znalezione) == 1:
        ip, a = znalezione[0]
        print('Znalazłem mikser: ' + scena.opis_miksera(ip, a))
        if bez_pytania:
            return ip
        odp = pytanie('Naciśnij Enter, aby go użyć, albo wpisz inny adres IP:')
        return odp or ip
    if znalezione:
        print('Znalazłem kilka mikserów:')
        for n, (ip, a) in enumerate(znalezione, 1):
            print(f'{n}. {scena.opis_miksera(ip, a)}')
        odp = pytanie('Wpisz numer miksera albo jego adres IP:')
        if odp.isdigit() and 1 <= int(odp) <= len(znalezione):
            return znalezione[int(odp) - 1][0]
        return odp
    print('Nie znalazłem miksera automatycznie.')
    print('Adres MR18 znajdziesz w oknie połączenia M-AIR Edit albo AOSC.')
    return pytanie('Adres IP MR18:')


def opis_roznic(rozbieznosci, ile=12):
    """Różnice mikser kontra BAZA po ludzku: węzeł, teraz w mikserze, w BAZIE."""
    linie = []
    for r in rozbieznosci[:ile]:
        teraz = ' '.join((r.get('odczyt') or 'brak odczytu').split()[1:]) or 'brak odczytu'
        baza = ' '.join(r['oczekiwane'])
        linie.append(f"  {r['wezel']}: w mikserze {teraz}, w BAZIE {baza}")
    if len(rozbieznosci) > ile:
        linie.append(f'  i jeszcze {len(rozbieznosci) - ile}.')
    return '\n'.join(linie)


def uruchom_mostek(dane, adres, test, wyniki, nazwa, raport):
    # Raport utrwalamy zanim użytkownik zacznie pracę z mostkiem.
    raport.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Uruchamiam mostek. Aby zakończyć, wpisz koniec i naciśnij Enter.')
    args = ['--mr18', adres, '--krotka-pomoc', '--mowa', 'konsola' if test else 'nvda',
            '--midi', 'brak' if test else 'winmm', '--dziennik', str(wyniki / (nazwa + '-mostek.log'))]
    if test:
        args.append('--dzwieki-konsola')
        print('Odbiór na symulatorze: bez NVDA, dźwięku i MIDI.')
    dane['mostek_argumenty'] = args
    rc = glowny.main(args)
    dane['mostek_kod'] = rc
    print('Mostek zakończony. Do ponownego uruchomienia w trakcie audycji użyj RESTART.bat.')
    return rc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (['start'], ['przywroc'], ['restart']):
        print('Użyj START.bat, RESTART.bat lub PRZYWROC.bat.')
        return 2
    przywroc = argv == ['przywroc']
    # RESTART (Michał, 23.10.2026): po zawieszeniu stołu dwa START w trakcie
    # audycji wczytały BAZĘ; pierwszy zmienił w mikserze 12 węzłów (suwaki
    # muzyki, Zooma). RESTART tylko uruchamia mostek i niczego nie zapisuje
    # do miksera, ani sceny, ani solo. Mostek sam wyłącznie czyta stan.
    restart = argv == ['restart']
    test = os.environ.get('MOSTEK_TEST_SYMULATOR') == '1'
    katalog = scena.KATALOG
    wyniki, kopie = katalog / 'wyniki', katalog / 'kopie'
    wyniki.mkdir(exist_ok=True)
    nazwa = argv[0] + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    raport = wyniki / (nazwa + '.json')
    dane = {'operacja': argv[0], 'test_symulator': test, 'ok': False}
    try:
        with blokada(katalog):
            if restart:
                print('RESTART: uruchamiam sam mostek. Niczego nie zapisuję do miksera.')
            adres = scena.sprawdz_adres(wybierz_adres(dane, test), test)
            with scena.Polaczenie(adres, symulator=test) as c:
                dane['xinfo'] = c.xinfo()
                dane['xinfo_surowe'] = getattr(c, 'xinfo_surowe', None)
                print('Mikser odpowiada: ' + ' '.join(dane['xinfo']))
                if restart:
                    dane.update(zapis_do_miksera=False, ok=True)
                    wynik = None
                else:
                    wynik = przygotuj_mikser(c, dane, przywroc, kopie)
            if wynik is not None:
                return wynik
            # Raport utrwalamy zanim użytkownik zacznie pracę z mostkiem.
            raport.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding='utf-8')
            if przywroc:
                print('Przywrócono ustawienia z kopii.' if dane['ok'] else 'Przywracanie niepełne. Sprawdź raport w program\\wyniki.')
                return 0 if dane['ok'] else 3
            if not dane['ok']:
                print('Są rozbieżności. Stan miksera nie jest w pełni potwierdzony.')
                if pytanie('Uruchomić mostek mimo to? Domyślnie nie. Aby uruchomić, wpisz TAK:') != 'TAK':
                    return 3
            return uruchom_mostek(dane, adres, test, wyniki, nazwa, raport)
    except scena.BladPlikuSceny as e:
        dane['blad'] = str(e)
        dane['zapis_do_miksera'] = False
        print(f'Plik sceny odrzucony: {e}.')
        print('Niczego nie zapisano do miksera. Mostek nie wystartował.')
        print('Popraw plik albo przywróć poprzedni BAZA.scn i uruchom START ponownie.')
        return 1
    except (OSError, ValueError, scena.BladSceny, KeyError) as e:
        dane['blad'] = str(e)
        print(f'Przerwano: {e}.')
        if restart:
            print('RESTART niczego nie zapisuje do miksera.')
        else:
            print('Jeśli rozpoczął się zapis, ustawienia mogą być częściowo zmienione.')
            print('Zachowaj kopię i raport. Nie uruchamiaj emisji.')
        return 1
    finally:
        raport.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Raport: program\\wyniki\\' + raport.name)


def przygotuj_mikser(c, dane, przywroc, kopie):
    """START i PRZYWROC przed uruchomieniem mostka. Zwraca kod wyjścia, gdy
    mostek nie ma ruszyć, albo None. dane['ok'] mówi, czy stan potwierdzony."""
    wezly = scena.zakres()
    schemat = scena.wczytaj_schemat()
    if not przywroc:
        # Najpierw porównanie bez żadnego zapisu: mikser zgodny z BAZĄ nie
        # dostaje ani jednego węzła (START po zwykłym zamknięciu mostka niczego
        # nie rusza). Solo nie należy do sceny, ale START je wyłącza: też liczymy.
        plik = scena.DANE / 'BAZA.scn'
        rows = scena.wiersze_pliku(plik, wezly, schemat)
        print('Porównuję mikser z BAZĄ, bez zapisu...')
        porownanie = scena.weryfikuj(c, rows, wezly, schemat)
        solo = c.aktywne_solo()
        dane['porownanie_z_baza'] = {'zgodne': porownanie['zgodne'],
                                     'rozbieznosci': porownanie['rozbieznosci'],
                                     'solo_wlaczone': solo}
        if not porownanie['rozbieznosci'] and not solo:
            print(f'Mikser zgodny z BAZĄ ({porownanie["zgodne"]}/{porownanie["oczekiwane"]}). '
                  'Niczego nie wczytuję.')
            dane.update(zapis_do_miksera=False, ok=True)
            return None
        # Michał, 23.10.2026: START wczytuje BAZĘ bez potwierdzania. W trakcie
        # audycji służy do tego RESTART, który niczego nie zapisuje.
        n = len(porownanie['rozbieznosci'])
        if n:
            print(f'Mikser różni się od BAZY w {n} miejscach:')
            print(opis_roznic(porownanie['rozbieznosci']))
        if solo:
            print('Włączone solo: ' + ', '.join(solo) + '.')
        print('Wczytuję BAZĘ. Najpierw zapisuję kopię bieżącego ustawienia miksera.')
        dane['wczytanie_bez_pytania'] = True
        dane.update(scena.wczytaj(c, plik, kopie, wezly, schemat))
        return None
    else:
        plik = scena.ostatnia_kopia(kopie)
        print('Przywrócę: ' + plik.name)
        zgoda = pytanie('Mostek ma być zamknięty. Zapiszę też kopię obecnego stanu. Wpisz TAK:')
    if zgoda != 'TAK':
        print('Anulowano. Nie zapisano niczego do miksera.')
        dane['anulowano'] = True
        return 2
    dane.update(scena.wczytaj(c, plik, kopie, wezly, schemat, przywracanie=przywroc))
    return None


if __name__ == '__main__':
    raise SystemExit(main())
