"""Mutanty trybu miksu i klawiszy stołu, w pamięci; repo bez zmian."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MUTACJE = [
    ('bank_w_miksie_pyta_players', 'playout', [
        ('polecenie = mapa.get(zdarzenie[1])',
         'polecenie = None if zdarzenie[1] == "bank_lewo_odtwarzacz" else mapa.get(zdarzenie[1])')],
     'test_odtwarzacze.TestOdtwarzacze.test_bank_w_miksie_zapis_bez_players_a_po_wyjsciu_odczyt'),
    ('players_do_spl', 'emisja', [
        ('return sara  # PLAYERS_TYLKO_SARA', 'return True  # mutant wysyła Players do SPL')],
     'test_odtwarzacze.TestProtokolOdtwarzaczy.test_zapora_na_gniezdzie_spl'),
    ('bank_poza_trybem_zapis', 'playout', [
        ('if polecenie == "przelacz" or (polecenie and self.tryb_miksu):',
         'if polecenie == "przelacz" or zdarzenie[1] == "bank_lewo_odtwarzacz" or (polecenie and self.tryb_miksu):')],
     'test_odtwarzacze.TestOdtwarzacze.test_bank_poza_trybem_numery_bez_czasu_tytulu_i_miksera'),
    ('ok_w_miksie_znacznik', 'playout', [
        ('polecenie = mapa.get(zdarzenie[1])',
         'polecenie = None if zdarzenie[1] == "emisja_znacznik" else mapa.get(zdarzenie[1])')],
     'test_klawisze_bank_channel.TestBankChannel.test_ok_w_miksie_ustawia_punkt_po_jog_bez_znacznika'),
    ('channel_czas_pfl_zamiast_anteny', 'playout', [
        ('return None  # MIX_ANTENA_BEZ_ZMIAN',
         'return ("miks", "MixInfo") if self.tryb_miksu and zdarzenie[1] == "emisja_pozostalo" else None')],
     'test_klawisze_bank_channel.TestBankChannel.test_channel_prawo_czas_anteny_sara_i_spl_bez_zmian'),
    ('channel_czas_podczas_stop', 'emisja', [
        ('if stan != "gra":\n                return Odczyt(stan, auto)',
         'if False:  # mutant pyta Rem przy stop/pauzie\n                return Odczyt(stan, auto)')],
     'test_klawisze_bank_channel.TestBankChannel.test_channel_prawo_stop_i_pauza_bez_czasu_i_rem'),
    ('jog_rusza_kursor', 'playout', [
        ('if zdarzenie[0] == "jog" and self.tryb_miksu:  # MIX_JOG_BEZ_KURSORA',
         'if False:  # mutant kieruje jog do playlisty')],
     'test_punkty_miksu.TestPunktyMiksu.test_jog_w_trybie_nie_rusza_playlisty_po_wyjsciu_rusza'),
    ('mix_do_spl', 'emisja', [
        ('if not sara:  # MIX_TYLKO_SARA', 'if False:  # mutant pomija Helo')],
     'test_punkty_miksu.TestZaporaMiksu.test_zapora_na_gniezdzie_spl'),
    ('play_przechwycony', 'playout', [
        ('return None  # MIX_ANTENA_BEZ_ZMIAN',
         'return ("miks", "MixPlay") if self.tryb_miksu and zdarzenie[1] == "transport_play" else None')],
     'test_punkty_miksu.TestPunktyMiksu.test_transport_i_f1_f7_bez_zmian'),
    ('jog_bez_sumowania', 'playout', [
        ('self._miks_jog_suma += int(kierunek) * krok  # MIX_SUMOWANIE',
         'self._kolejka.append(("miks", "MixPos=" + przesuniecie(int(kierunek) * krok), True, teraz))')],
     'test_punkty_miksu.TestPunktyMiksu.test_szybki_jog_sumowany_mowi_tylko_koniec'),
    ('jog_mowi_czas', 'playout', [
        ('self._miks_mowa_termin = None  # MIX_CISZA_JOG',
         'self._miks_mowa_termin = teraz + self.zwloka  # mutant: czas po kółku')],
     'test_punkty_miksu.TestPunktyMiksu.test_zmiany_pozycji_i_punktu_bez_czytania_czasu'),
    ('nudge_mowi_czas', 'miks', [
        ('return None  # MIX_CISZA_ZMIAN: kółko, REWIND/FFWD, góra/dół bez czasu',
         'return self.pozycja()  # mutant: czas po każdej zmianie')],
     'test_punkty_miksu.TestPunktyMiksu.test_zmiany_pozycji_i_punktu_bez_czytania_czasu'),
]


def main():
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'tests') + os.pathsep + str(ROOT))
    wyniki = []
    for nazwa, modul, zamiany, test in MUTACJE:
        plik = ROOT / 'mostek' / f'{modul}.py'
        kod = plik.read_text(encoding='utf-8')
        for stare, nowe in zamiany:
            assert kod.count(stare) == 1, (nazwa, stare)
            kod = kod.replace(stare, nowe)
        kontrola = subprocess.run([sys.executable, '-m', 'unittest', test, '-v'], cwd=ROOT,
                                  env=env, capture_output=True, text=True, timeout=30)
        skrypt = (f'import mostek.{modul} as m, unittest\n'
                  f'exec(compile({kod!r}, {str(plik)!r}, "exec"), m.__dict__)\n'
                  f's=unittest.defaultTestLoader.loadTestsFromName({test!r})\n'
                  'r=unittest.TextTestRunner(verbosity=2).run(s)\n'
                  'raise SystemExit(0 if r.wasSuccessful() else 1)\n')
        mutant = subprocess.run([sys.executable, '-c', skrypt], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=30)
        wyniki.append(dict(mutant=nazwa, test=test, kontrola_rc=kontrola.returncode,
                           mutant_rc=mutant.returncode,
                           zabity=kontrola.returncode == 0 and mutant.returncode == 1 and
                           'FAIL:' in mutant.stderr and 'ERROR:' not in mutant.stderr,
                           kontrola=kontrola.stdout + kontrola.stderr,
                           wynik_mutanta=mutant.stdout + mutant.stderr))
    print(json.dumps(wyniki, ensure_ascii=False, indent=2))
    return 0 if all(w['zabity'] for w in wyniki) else 1


if __name__ == '__main__':
    raise SystemExit(main())
