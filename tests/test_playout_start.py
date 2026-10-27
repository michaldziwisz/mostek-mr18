"""Rzeczywisty przebieg START -> main -> TCP, bez stołu/audio i poza MR18."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mostek import glowny, ustawienia
from narzedzia import prosty_start
from tests.atrapa_playoutu import SerwerPlayoutu


class TestStartPlayout(unittest.TestCase):
    def test_start_domyslnie_wlacza_auto_a_restart_zamyka_worker(self):
        with SerwerPlayoutu(True) as s, tempfile.TemporaryDirectory(prefix="playout-start-") as katalog:
            u = ustawienia.wczytaj()
            u.emisja.update(program="auto", preferowany="SARA", sara_port=s.port)
            dane = {}
            wyniki = Path(katalog)
            # Uruchomienie sceny nie jest częścią uruchom_mostek. Zastępujemy
            # wyłącznie adres MR18 lokalnym modelem przy zachowaniu reszty args START.
            real_main = glowny.main
            args_start = []
            def main_z_modelem(args):
                args_start.extend(args)
                return real_main(["--symulator"] + args[2:])
            krok = 0
            def wejscie(prompt):
                nonlocal krok
                krok += 1
                if krok == 1:
                    self.assertEqual(s.polecenia, [], "START nie startuje sam muzyki")
                    return "play"
                if krok == 2:
                    self.assertTrue(s.czekaj_na("Play", timeout=2))
                    return "coGra"
                if krok == 3:
                    self.assertTrue(s.czekaj_na("Rem", timeout=2))
                    return "restart"
                if krok == 4:
                    return "nastepny"
                if krok == 5:
                    self.assertTrue(s.czekaj_na("Skip", timeout=2))
                    return "koniec"
                raise AssertionError("nadmiarowe pytanie")
            with patch.object(glowny.ustawienia, "wczytaj", return_value=u), \
                 patch.object(prosty_start.glowny, "main", side_effect=main_z_modelem), \
                 patch("builtins.input", side_effect=wejscie), contextlib.redirect_stdout(io.StringIO()):
                rc = prosty_start.uruchom_mostek(dane, "127.0.0.1", True, wyniki, "test", wyniki / "raport.json")
            self.assertEqual(rc, 0)
            self.assertNotIn("--emisja", args_start)
            self.assertEqual(s.polecenia.count("Play"), 1)
            self.assertEqual(s.polecenia.count("Skip"), 1)
            self.assertEqual(krok, 5)
            import threading
            self.assertFalse(any(t.name == "playout" for t in threading.enumerate()))

    def test_jawne_brak_nie_tworzy_adaptera(self):
        with tempfile.TemporaryDirectory(prefix="playout-brak-") as katalog, \
             patch.object(glowny.emisja_mod, "utworz") as utworz, \
             patch("builtins.input", return_value="koniec"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(glowny.main(["--symulator", "--emisja", "brak", "--dzwieki-konsola",
                                          "--dziennik", str(Path(katalog) / "mostek.log")]), 0)
            utworz.assert_not_called()
