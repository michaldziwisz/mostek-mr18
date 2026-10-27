"""Ścieżki wydania i cichy odbiór, bez wywoływania NVDA ani karty dźwiękowej."""
import ctypes
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mostek import informacja, mowa, ustawienia


class PaczkaWindows(unittest.TestCase):
    def test_repo_bez_zmiany_sciezek(self):
        self.assertEqual(ustawienia.KATALOG, Path(ustawienia.__file__).resolve().parent.parent)

    def test_frozen_dane_i_zapis_obok_exe_z_innego_cwd(self):
        # Osobny interpreter, by symulacja frozen nie zmieniała innych testów.
        with tempfile.TemporaryDirectory() as tmp:
            kod = '''
import sys, json
from pathlib import Path
sys.frozen = True
sys.executable = str(Path(sys.argv[1]) / "mostek.exe")
from mostek import ustawienia, informacja
u = ustawienia.wczytaj(sys.argv[2], sys.argv[3])
i = informacja.InformacjaZwrotna(u, informacja.AtrapaDzwiekow())
assert i.zapisz_tryb()
print(json.dumps([str(ustawienia.KATALOG), str(ustawienia.DOMYSLNE_USTAWIENIA),
                  str(u.plik_trybu), str(i.katalog)]))
'''
            import os
            env = dict(os.environ, PYTHONPATH=str(ustawienia.KATALOG))
            r = subprocess.run([sys.executable, "-B", "-c", kod, tmp,
                                str(ustawienia.DOMYSLNE_USTAWIENIA), str(ustawienia.DOMYSLNE_POZIOMY)],
                               cwd=tmp, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), [str(Path(tmp)),
                str(Path(tmp) / "ustawienia/stanowisko.json"),
                str(Path(tmp) / "ustawienia/tryb_informacji.json"), str(Path(tmp) / "dzwieki")])
            self.assertTrue((Path(tmp) / "ustawienia/tryb_informacji.json").is_file())

    def test_dll_szukana_w_katalogu_danych_bez_ladowania_nvda(self):
        biblioteka = Mock()
        with patch.object(ustawienia, "KATALOG", Path("paczka")), \
             patch.object(sys, "platform", "win32"), \
             patch.object(ctypes, "windll", create=True) as loader:
            loader.LoadLibrary.return_value = biblioteka
            mowa.MowaNVDA()
            bity = "x64" if ctypes.sizeof(ctypes.c_void_p) == 8 else "x86"
            loader.LoadLibrary.assert_called_once_with(str(Path("paczka/biblioteki") / bity / "nvdaControllerClient.dll"))
            biblioteka.nvdaController_testIfRunning.assert_not_called()
            biblioteka.nvdaController_speakText.assert_not_called()

    def test_cicha_atrapa_na_windows_nie_dotyka_winsound(self):
        s = io.StringIO()
        with patch.object(sys, "platform", "win32"), patch.object(informacja, "OdtwarzaczWinsound") as ws:
            o = informacja.utworz_odtwarzacz(s, konsola=True)
            o.odtworz("alarm", Path("niepotrzebny.wav"))
            o.zatrzymaj()
            ws.assert_not_called()
        self.assertEqual(s.getvalue(), "[dzwiek] alarm\n")

    def test_domyslny_odtwarzacz_windows_bez_zmiany(self):
        with patch.object(sys, "platform", "win32"), patch.object(informacja, "OdtwarzaczWinsound") as ws:
            self.assertIs(informacja.utworz_odtwarzacz(), ws.return_value)

    def test_fallback_nvda_w_glownym_jedno_ostrzezenie(self):
        from mostek import glowny
        import contextlib
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mowa, 'MowaNVDA', side_effect=mowa.BrakNVDA('atrapa braku NVDA')), \
             patch.object(sys, 'stdin', io.StringIO('koniec\n')), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            rc = glowny.main(['--symulator', '--mowa', 'nvda', '--dzwieki-konsola', '--krotka-pomoc',
                              '--dziennik', str(Path(tmp) / 'mostek.log')])
        self.assertIn('Mostek działa.', out.getvalue())
        self.assertNotIn('Polecenia konsoli mostka (każde', out.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().count('NVDA niedostępne'), 1)
        self.assertIn('komunikaty w konsoli', out.getvalue())

    def test_restart_z_konsoli_mostka(self):
        """Michał, 23.10.2026: „restart” w oknie mostka dawał „Nieznane
        polecenie”. Teraz drugi przebieg w tym samym procesie: nowy klient,
        pełny odczyt (synchronizacja w dzienniku dwa razy), potem koniec."""
        from mostek import glowny
        import contextlib
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mowa, 'MowaNVDA', side_effect=mowa.BrakNVDA('atrapa braku NVDA')), \
             patch.object(sys, 'stdin', io.StringIO('restart\nkoniec\n')), \
             patch.object(glowny, '_przebieg', wraps=glowny._przebieg) as przebieg, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            rc = glowny.main(['--symulator', '--mowa', 'nvda', '--dzwieki-konsola', '--krotka-pomoc',
                              '--dziennik', str(Path(tmp) / 'mostek.log')])
        tekst = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertEqual(przebieg.call_count, 2)
        self.assertNotIn('Nieznane polecenie', tekst)
        self.assertIn('Restartuję mostek. Do miksera nic nie zapisuję.', tekst)
        self.assertIn('Mostek uruchamia się od nowa.', tekst)
        self.assertEqual(tekst.count('Mostek działa.'), 2)
        self.assertIn('Wpisz restart', tekst)
        self.assertIn('restart ', glowny.POMOC)

    def test_brak_nvda_sprawdzany_na_atrapie(self):
        with patch.object(mowa, "MowaNVDA") as nv:
            nv.return_value.dziala.return_value = False
            with self.assertRaises(mowa.BrakNVDA):
                mowa.utworz_wyjscie("nvda")
            nv.return_value.mow.assert_not_called()
