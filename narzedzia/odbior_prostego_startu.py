"""Cichy odbiór prawdziwych BAT/EXE Windows z modelem repo sceny.
Nie otwiera NVDA, audio ani MIDI. Wszystkie UDP wyłącznie do 127.0.0.1.
Wyniki na dysku, nie wnioski z kodu procesu WSL interop.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def czekaj(warunek, proces, limit=120):
    koniec = time.monotonic() + limit
    while time.monotonic() < koniec:
        if warunek():
            return
        if proces.poll() is not None:
            raise RuntimeError(f'Proces zakończony przed gotowością: {proces.returncode}')
        time.sleep(.1)
    raise TimeoutError('Brak gotowości procesu')


def model(a):
    # Model z tests/ repo mostka. Jawne dane runtime, których nie ma w SCN.
    sys.path.insert(0, str(a.repo / 'tests'))
    import importlib
    m = importlib.import_module('mikser_rejestrujacy')
    oryginal = m.Model
    class ModelZRuntime(oryginal):
        def __init__(self, factory, schema):
            super().__init__(factory, schema)
            self.values['/-snap/index'] = ('i', 0)
            for n in list(range(1, 17)) + list(range(40, 46)):
                self.values[f'/-stat/solosw/{n:02d}'] = ('i', 0)
    m.Model = ModelZRuntime
    start = a.wyjscie.parent / (a.wyjscie.name + '-start.scn')
    # newline='': na Windows write_text zamienia \n na CRLF, a model zapisuje LF.
    start.write_text(m.stan_startowy(a.repo / 'tests/dane_sceny/baza-aosc-v4.scn', a.repo / 'dane_sceny/schemat-mr18.json'),
                     encoding='utf-8', newline='')
    sys.argv = [str(a.repo / 'tests/mikser_rejestrujacy.py'),
                '--factory', str(start),
                '--schema', str(a.repo / 'dane_sceny/schemat-mr18.json'), '--out', str(a.wyjscie), '--seconds', '600']
    m.main()


def odbior(a):
    import zipfile
    sys.path.insert(0, str(a.repo))
    from narzedzia import scena_mr18 as s
    if sys.platform != 'win32':
        raise RuntimeError('Odbiór wymaga Pythona Windows')
    a.wyjscie.mkdir(parents=True, exist_ok=False)
    paczka = a.wyjscie / 'paczka ze spacjami'
    with zipfile.ZipFile(a.zip) as z:
        z.extractall(paczka)
    symdir = a.wyjscie / 'symulator'
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1',
               MOSTEK_TEST_SYMULATOR='1')
    wynik = {'python': sys.version, 'platforma': sys.platform, 'zip': str(a.zip),
             'zip_md5': hashlib.md5(a.zip.read_bytes()).hexdigest(), 'ok': False,
             'runtime_modelu': 'Solo 01–16 i 40–45 = 0, /-snap/index = 0. Nie należą do sceny.',
             'tryb': 'MOSTEK_TEST_SYMULATOR=1: konsola, bez audio, bez MIDI i NVDA'}
    wezly = s.zakres(a.repo / 'dane_sceny/schemat-mr18.json')
    schema = s.Schemat((a.repo / 'dane_sceny/schemat-mr18.json').read_text(encoding='utf-8'))
    logmodel = (a.wyjscie / 'model.log').open('wb')
    proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--model',
        '--repo', str(a.repo), '--wyjscie', str(symdir)],
        stdout=logmodel, stderr=subprocess.STDOUT, env=env, cwd=a.wyjscie)
    bat = None
    try:
        czekaj(lambda: (symdir / 'gotowy.json').exists(), proc, 30)
        with s.Polaczenie('127.0.0.1', symulator=True) as c:
            przed = ''.join(c.node(p) for p in wezly).encode()
        (a.wyjscie / 'stan-przed.scn').write_bytes(przed)
        factory = (symdir.parent / (symdir.name + '-start.scn')).read_bytes()
        assert przed == factory, 'Model przed próbą różni się od stanu startowego'
        cmd = os.environ.get('COMSPEC', r'C:\Windows\System32\cmd.exe')
        with (a.wyjscie / 'START.log').open('wb') as output:
            bat = subprocess.Popen([cmd, '/d', '/c', 'START.bat'], cwd=paczka, env=env,
                                   stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
            bat.stdin.write(b'127.0.0.1\n'); bat.stdin.flush()    # START bez potwierdzania BAZY
            czekaj(lambda: 'Mostek działa.' in (a.wyjscie / 'START.log').read_text(encoding='utf-8', errors='replace'), bat)
            # Polecenia dopiero po gotowości, nie samo uruchomienie procesu.
            bat.stdin.write(b'f2\n'); bat.stdin.flush()
            time.sleep(2)
            bat.stdin.write(b'koniec\n'); bat.stdin.flush()
            wynik['start_rc'] = bat.wait(timeout=30)
            bat.stdin.close()
        assert wynik['start_rc'] == 0, 'START nie zakończył się kodem 0'
        raport_start = next((paczka / 'program/wyniki').glob('start-*.json'))
        r = json.loads(raport_start.read_text(encoding='utf-8'))
        wynik['start'] = r
        assert r['zgodne'] == 693 and r['ok'] and r['mostek_kod'] == 0, r
        kopia = Path(r['kopia']).read_bytes()
        wynik['kopia_rowna_stanowi_przed_bajtowo'] = kopia == przed
        assert kopia == przed
        log = next((paczka / 'program/wyniki').glob('*-mostek.log')).read_text(encoding='utf-8')
        wynik['dziennik_mostka'] = log
        # Stan profilu dowodzimy również niezależną weryfikacją parametrów.
        from mostek.ustawienia import wczytaj
        from mostek.logika import sprawdz_profil, wszystkie_adresy_odczytu, Widok
        from mostek.stan import NIEZNANY
        u = wczytaj(a.repo / 'ustawienia/stanowisko.json', a.repo / 'ustawienia/poziomy_bazowe.json')
        class StanOdczytany:
            def __init__(self, dane): self.dane = dane
            def wartosc(self, adres): return self.dane.get(adres, NIEZNANY)
        with s.Polaczenie('127.0.0.1', symulator=True) as c:
            dane_profilu = {p: c.pytaj(p).wartosc for p in wszystkie_adresy_odczytu(u)}
            po = ''.join(c.node(p) for p in wezly)
        wynik['naruszenia_profilu'] = [vars(n) for n in sprawdz_profil(u, Widok(u, StanOdczytany(dane_profilu)))]
        wynik['odczytane_sciezki_profilu'] = len(dane_profilu)
        assert not wynik['naruszenia_profilu'], wynik['naruszenia_profilu']
        assert 'synchronizacja' in log, 'Mostek nie potwierdził pełnej synchronizacji'
        (a.wyjscie / 'stan-po-start.scn').write_text(po, encoding='utf-8', newline='')
        # Pełny raport loadera jest rozstrzygający dla BAZY; dziennik zachowany.
        assert 'profil miksera niezgodny' not in log.lower(), log
        # RESTART i drugi START na mikserze już zgodnym z BAZĄ (23.10.2026):
        # oba mają uruchomić mostek bez ani jednego zapisu węzła sceny.
        # Oracle: dziennik pakietów modelu; zapis węzła sceny to ten sam warunek,
        # którym model odświeża stan.json: ścieżka '/' albo węzeł sceny z argumentami.
        rows_modelu = set(s.czytaj_scn(factory.decode('utf-8')))
        def zapisy_modelu():
            n = 0
            with (symdir / 'pakiety.jsonl').open(encoding='utf-8') as f:
                for linia in f:
                    p = json.loads(linia)
                    if p.get('direction') != 'RX':
                        continue
                    for adres, _typ, argumenty in p['osc']:
                        if adres == '/' or (argumenty and adres in rows_modelu):
                            n += 1
            return n
        wynik['zapisy_sceny_po_start'] = zapisy_modelu()
        assert wynik['zapisy_sceny_po_start'] >= 693, 'oracle nie widzi zapisów pierwszego START'
        for tryb in ('RESTART', 'START'):
            przed_zapisy = zapisy_modelu()
            with (a.wyjscie / f'{tryb}-2.log').open('wb') as output:
                bat = subprocess.Popen([cmd, '/d', '/c', f'{tryb}.bat'], cwd=paczka, env=env,
                                       stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
                bat.stdin.write(b'127.0.0.1\n'); bat.stdin.flush()     # tryb symulatora pyta o adres
                czekaj(lambda: 'Mostek działa.' in (a.wyjscie / f'{tryb}-2.log').read_text(encoding='utf-8', errors='replace'), bat)
                if tryb == 'RESTART':
                    # Polecenie restart w oknie mostka (Michał, 23.10.2026):
                    # drugi przebieg w tym samym procesie, bez zapisu do miksera.
                    bat.stdin.write(b'restart\n'); bat.stdin.flush()
                    czekaj(lambda: (a.wyjscie / f'{tryb}-2.log').read_text(encoding='utf-8', errors='replace')
                           .count('Mostek działa.') >= 2, bat)
                bat.stdin.write(b'koniec\n'); bat.stdin.flush()
                wynik[f'{tryb.lower()}2_rc'] = bat.wait(timeout=30)
                bat.stdin.close()
            time.sleep(1.5)        # model dopisuje pakiety
            wynik[f'{tryb.lower()}2_zapisy_sceny'] = zapisy_modelu() - przed_zapisy
            tekst = (a.wyjscie / f'{tryb}-2.log').read_text(encoding='utf-8', errors='replace')
            assert wynik[f'{tryb.lower()}2_rc'] == 0, tekst
            assert 'Weryfikacja sceny' not in tekst and 'Kopia gotowa' not in tekst, tekst
            if tryb == 'START':
                assert 'Mikser zgodny z BAZĄ (693/693)' in tekst, tekst
        assert wynik['restart2_zapisy_sceny'] == 0 and wynik['start2_zapisy_sceny'] == 0, wynik
        with (a.wyjscie / 'PRZYWROC.log').open('wb') as output:
            bat = subprocess.Popen([cmd, '/d', '/c', 'PRZYWROC.bat'], cwd=paczka, env=env,
                                   stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
            bat.communicate(b'127.0.0.1\nTAK\n', timeout=120)
            wynik['przywroc_rc'] = bat.returncode
        assert bat.returncode == 0
        rp = json.loads(next((paczka / 'program/wyniki').glob('przywroc-*.json')).read_text(encoding='utf-8'))
        wynik['przywroc'] = rp
        assert rp['ok'] and rp['zgodne'] == 693
        with s.Polaczenie('127.0.0.1', symulator=True) as c:
            po = ''.join(c.node(p) for p in wezly)
        (a.wyjscie / 'stan-po-przywroc.scn').write_text(po, encoding='utf-8', newline='')
        rows = s.czytaj_scn(przed.decode()); actual = s.czytaj_scn(po)
        rozbieznosci = [p for p in wezly if not s.zgodne(p, rows[p], actual[p], schema, rows)]
        wynik['przywrocenie_rozbieznosci'] = rozbieznosci
        assert not rozbieznosci
        wynik['przywrocenie_roznice_formatu'] = [p for p in wezly if rows[p] != actual[p]]
        wynik['ok'] = True
    except BaseException as e:
        wynik['blad'] = repr(e)
        raise
    finally:
        if bat is not None and bat.poll() is None:
            bat.kill(); bat.wait(10)
        symdir.mkdir(exist_ok=True)
        (symdir / 'STOP').write_text('koniec', encoding='utf-8')
        try:
            wynik['model_rc'] = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); wynik['model_rc'] = proc.wait(10)
        logmodel.close()
        (a.wyjscie / 'wynik.json').write_text(json.dumps(wynik, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', action='store_true')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--zip', type=Path)
    p.add_argument('--wyjscie', type=Path, required=True)
    a = p.parse_args()
    model(a) if a.model else odbior(a)


if __name__ == '__main__':
    main()
