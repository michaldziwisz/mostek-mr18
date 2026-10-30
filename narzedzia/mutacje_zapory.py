"""Test mutacyjny reguł zapory z wyłącznikiem (model CUE plan v20, klucz przyciszania plan v22).

Dla każdej nowej reguły z mostek/logika.py (NOWE_REGULY) narzędzie:
  1. kopiuje katalog mostka do katalogu tymczasowego (oryginał nietknięty),
  2. w kopii wyłącza tę jedną regułę: na początku jej funkcji wstawia
     powrót „brak naruszenia”,
  3. uruchamia w kopii wybrane testy i zapisuje, które padły.

Mutant jest „zabity”, gdy pada test tej reguły (test_regula_NAZWA), a powód
to brak odrzucenia zapisu („not raised”): znaczy to, że w ustawionym stanie
żadna inna reguła nie odrzuca zapisu, więc test sprawdza właśnie tę regułę.

Mutanty poprawek (MUTANTY_POPRAWEK) cofają w kopii jeden fragment poprawki
spoza funkcji reguł, np. przeliczanie profilu po zmianie szyny na Main LR
z innego urządzenia. Mutant jest zabity, gdy pada wskazany test regresji.

Niezmienniki złożone (REGULY_ZLOZONE, np. kaszel_bez_cue) nie mają własnej
funkcji: pilnują ich istniejące reguły. Dla każdej reguły-strażnika mutant
ma wywrócić test test_ZLOZONA_STRAZNIK z powodem „not raised”. Raport
pokazuje, która reguła pilnuje którego niezmiennika.

    python narzedzia/mutacje_zapory.py                  testy zapory (szybko)
    python narzedzia/mutacje_zapory.py --pelne          cały zestaw testów na każdym mutancie

Nie łączy się z niczym poza symulatorem w testach. Uruchamia mutanty po kolei.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KATALOG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KATALOG))

from mostek.logika import NOWE_REGULY, REGULY_ZLOZONE  # noqa: E402

# Reguły zwracające prawdę przy naruszeniu (zamiast listy naruszeń).
POWROT = {"tap_wartosci": "False", "tap_przy_otwartej": "False", "glosniki_przy_mikrofonie": "False",
          "klucz_przy_niezgodnym_profilu": "False", "glosniki_bez_mikrofonu": "False",
          "klucz_tylko_glosy": "False", "klucz_bez_wyjscia": "False",
          "sciezka_w_rejestrze": "False", "glosniki_przy_niezgodnym_profilu": "False",
          "sciezka_tylko_do_odczytu": "False",
          "chwilowy_bez_anteny": "False", "chwilowy_bez_klucza": "False",
          "talkback_tylko_adresaci": "False", "talkback_przed_suwakiem": "False",
          "kaszel_bez_wysylek": "False", "talkback_izolacja": "False"}

# Poprawka przed odbiorem (szyna na Main LR z innego urządzenia): każdy
# fragment cofnięty osobno ma wywrócić własny test regresji.
# nazwa: (plik względem katalogu mostka, tekst oryginalny, tekst mutanta, test).
# Moduł testów w trybie szybkim: MODUL_TESTU (domyślnie test_niezmienniki).
MUTANTY_POPRAWEK = {
    'mikrofon_suwak_zostawia_cue': (
        'mostek/rdzen.py',
        '            self._wlacz_mikrofon(fader=wartosc)',
        '            if self._jest_rozmowa_cue():\n                return  # MUTANT: CUE uniemożliwia Fader Start\n            self._wlacz_mikrofon(fader=wartosc)',
        'test_podniesienie_konczy_wszystkie_cue',
    ),
    'mikrofon_f1_odmawia_cue': (
        'mostek/rdzen.py',
        '        byl_talkback = bool(self._talkback)',
        '        if cue:\n            return  # MUTANT: dawna odmowa F1\n        byl_talkback = bool(self._talkback)',
        'test_f1_przy_cue_konczy_i_wlacza',
    ),
    'mikrofon_otwarcie_przed_cue': (
        'mostek/rdzen.py',
        '        zamk = self._plan_zamkniec(c, zakres)',
        '        if fader_mikrofonu is not None:\n            return WynikPrzejscia(self._otworz(self._plan_otwarc(c, zakres)).ok)  # MUTANT: otwarcia przed zamknięciami\n        zamk = self._plan_zamkniec(c, zakres)',
        'test_f1_przy_cue_konczy_i_wlacza',
    ),
    'mikrofon_bez_wyciszenia_glosnikow': (
        'mostek/rdzen.py',
        '        zamk = self._plan_zamkniec(c, zakres)',
        '        zamk = [k for k in self._plan_zamkniec(c, zakres) if k.adres not in self.widok.adresy_glosnikow()]  # MUTANT',
        'test_glosniki_przed_faderem_i_main_on',
    ),
    'mikrofon_wylaczenie_bez_silnika': (
        'mostek/rdzen.py',
        '        fader_ok = self._ustaw_fader_mikrofonu(0.0)',
        '        fader_ok = True  # MUTANT: silnik i fader nie schodzą na dół',
        'test_f1_select_silnik_gora_dol',
    ),
    'mikrofon_dol_korekta_zero': (
        'mostek/rdzen.py',
        '            return self.u.zrodla[MIKROFON].suwak_maks_db',
        '            return 0.0  # MUTANT: rozmowa cichsza niż pełna antena',
        'test_poziomy_dol_rowne_dawnym_gora_cue_i_talkback',
    ),
    'mikrofon_obcy_fader_otwiera': (
        'mostek/rdzen.py',
        '            # Obcy fader nie wywołuje Fader Start ani nie jest cofany.',
        '            if self.widok.suwak_na_dole(MIKROFON) is False:\n                self._wlacz_mikrofon()  # MUTANT: obca zmiana otwiera antenę\n            # Obcy fader nie wywołuje Fader Start ani nie jest cofany.',
        'test_obce_podniesienie_nie_wlacza_i_nie_cofa',
    ),
    'mikrofon_fader_przed_zamknieciami': (
        'mostek/rdzen.py',
        '        zamk = self._plan_zamkniec(c, zakres)',
        '        if fader_mikrofonu is not None:\n            self._ustaw_fader_mikrofonu(fader_mikrofonu)  # MUTANT: dodatni fader przed CUE\n        zamk = self._plan_zamkniec(c, zakres)',
        'test_podniesienie_konczy_wszystkie_cue',
    ),
    'mikrofon_brak_konca_talkbacku': (
        'mostek/rdzen.py',
        '            if byl_talkback:\n                self._przerwij_kaszel(oglos=False)',
        '            if False:\n                self._przerwij_kaszel(oglos=False)  # MUTANT',
        'test_podniesienie_przerywa_trzymany_talkback',
    ),
    'mikrofon_tolerancja_pierwszego_kroku': (
        'mostek/rdzen.py',
        'ok = ok and zgodne(v, wartosc) and ((float(v) > 0) == (wartosc > 0))',
        'ok = ok and zgodne(v, wartosc)  # MUTANT: pierwszy krok mylony z zerem',
        'test_niepotwierdzony_pierwszy_krok_nie_otwiera',
    ),
    'mikrofon_kaszel_dol_gora': (
        'mostek/rdzen.py',
        'self._kaszel_suwak_zamkniety = self._kaszel is not None',
        'self._kaszel_suwak_zamkniety = False  # MUTANT: trzymany kaszel zapomniany',
        'test_kaszel_trzymany_dol_gora_nie_otwiera',
    ),
    'mikrofon_brak_okresowego_fadera': (
        'mostek/rdzen.py',
        '        adresy += [sciezki.fader(k) for k in self.u.zrodla[MIKROFON].kanaly]  # MIKROFON_ODCZYT',
        '        pass  # MUTANT: zgubione xremote zostawia stary fader',
        'test_zgubione_obce_zgloszenie_czyta_fader_bez_otwarcia',
    ),
    "kaszel_solo_zakres": (
        "mostek/rdzen.py",
        "s is not self._solo_kaszlu or adres not in self._solo_mikrofonu()",
        "s is not self._solo_kaszlu",
        "test_zapora_sesji_i_adresow_nawet_przy_zatrutej_migawce"),
    "kaszel_solo_sesja": (
        "mostek/rdzen.py",
        "s is not self._solo_kaszlu or adres not in self._solo_mikrofonu()",
        "adres not in self._solo_mikrofonu()",
        "test_zapora_sesji_i_adresow_nawet_przy_zatrutej_migawce"),
    "kaszel_solo_bez_zdjecia": (
        "mostek/rdzen.py",
        "            self._zdejmij_solo_kaszlu()",
        "            pass  # MUTANT: mikrofon nadal w PHONES",
        "test_cue_telefon_i_zoom_migawka_i_nietkniete_trasy"),
    "kaszel_solo_bez_powrotu": (
        "mostek/rdzen.py",
        "            self._przywroc_solo_kaszlu()",
        "            pass  # MUTANT: brak powrotu solo po puszczeniu",
        "test_cue_telefon_i_zoom_migawka_i_nietkniete_trasy"),
    "kaszel_solo_jedyne": (
        "mostek/rdzen.py",
        "        s = SoloKaszlu({a: dane[a] for a in mikrofon}, dict(dane))",
        "        if not any(v == 1 for a, v in dane.items() if a not in mikrofon and a != sciezki.SOLO_MAIN_LR):\n"
        "            return  # MUTANT: jedyne solo mikrofonu zostaje\n"
        "        s = SoloKaszlu({a: dane[a] for a in mikrofon}, dict(dane))",
        "test_jedyne_solo_mikrofonu_znika_i_wraca"),
    "kaszel_solo_bez_potwierdzenia": (
        "mostek/rdzen.py",
        "ok = ok and not zle and not s.obca_zmiana",
        "ok = ok and not s.obca_zmiana",
        "test_brak_dwoch_odczytow_solo_nie_udaje_sukcesu"),
    "kaszel_solo_impuls": (
        "mostek/rdzen.py",
        "s.obca_zmiana = True  # także obcy impuls ON -> OFF między odczytami",
        "pass  # MUTANT: zgubiony obcy impuls solo",
        "test_obce_solo_impuls_nie_jest_cofany"),
    "kaszel_solo_przerwanie": (
        "mostek/rdzen.py",
        '        self._przywroc_solo_kaszlu()\n        self._dz(rodzaj, "przerwany")',
        '        self._dz(rodzaj, "przerwany")',
        "test_przerwanie_kontroler_f1_obca_wysylka_i_synchronizacja"),
    "talkback_glosniki_bez_potwierdzenia": (
        "mostek/rdzen.py",
        "if not w.ok or zle or self._glosniki_talkback is not g or g.obca_zmiana:",
        "if not w.ok or self._glosniki_talkback is not g or g.obca_zmiana:",
        "test_brak_koncowego_potwierdzenia_wyciszenia_bez_otwarcia"),
    "talkback_glosniki_bez_powrotu": (
        "mostek/rdzen.py",
        "        g.przywroc = True\n",
        "        g.przywroc = False\n",
        "test_aktywne_wycisza_przed_otwarciem_i_przywraca_bez_mowy"),
    "talkback_glosniki_cudze_off": (
        "mostek/rdzen.py",
        "            self._glosniki_talkback.przywroc = False\n",
        "            pass  # MUTANT: świadome OFF nie unieważnia powrotu\n",
        "test_reczne_wyciszenie_uniewaznia_powrot_takze_gdy_juz_cisza"),
    "talkback_glosniki_impuls": (
        "mostek/rdzen.py",
        "            g.obca_zmiana = True\n\n    def zglos(",
        "            pass  # MUTANT: gubi obce ON -> OFF przed odczytem\n\n    def zglos(",
        "test_obce_odciszenie_i_wyciszenie_przed_odczytem_uniewaznia"),
    "talkback_glosniki_bez_odczytu_przed_powrotem": (
        "mostek/rdzen.py",
        "        self._odczyt_krytyczny()\n        if self._glosniki_talkback is not g:\n",
        "        if self._glosniki_talkback is not g:\n",
        "test_obce_otwarcie_mikrofonu_tuz_przed_odciszeniem"),
    "talkback_glosniki_f1_pod_kaszlem": (
        "mostek/rdzen.py",
        "            talkback = self._glosniki_talkback is not None\n",
        "            talkback = bool(self._talkback)\n",
        "test_f1_po_puszczeniu_talkbacku_pod_kaszlem_nie_odcisza"),
    "talkback_glosniki_powrot_wczesniej_wyciszonych": (
        "mostek/rdzen.py",
        "        if not g.aktywne:\n            return self.widok.glosniki_wyciszone() is True\n",
        "        if not g.aktywne:\n            g.aktywne = True  # MUTANT: przejmuje cudze wyciszenie\n",
        "test_wczesniej_wyciszone_nietkniete_takze_mute_act"),
    "scena_zapis_przed_kopia": (
        "narzedzia/scena_mr18.py",
        "    zapisane = kopia(polaczenie, katalog_kopii, wezly, schemat,",
        "    polaczenie.zapisz_linie(tekst.splitlines()[0])  # MUTANT: SET przed kopią\n"
        "    zapisane = kopia(polaczenie, katalog_kopii, wezly, schemat,",
        "test_zapis_dopiero_po_kompletnej_kopii"),
    "scena_bez_weryfikacji": (
        "narzedzia/scena_mr18.py",
        "    raport = weryfikuj(polaczenie, rows, wezly, schemat)  # WERYFIKACJA_PO_ZAPISIE",
        "    raport = {'oczekiwane': len(wezly), 'zgodne': len(wezly), 'rozbieznosci': []}  # MUTANT",
        "test_weryfikacja_wykrywa_zepsuta_linie"),
    "scena_nadpisana_kopia": (
        "narzedzia/scena_mr18.py",
        "plik.open('xb')  # BEZ_NADPISANIA",
        "plik.open('wb')  # MUTANT: nadpisuje istniejącą kopię",
        "test_kopia_nigdy_nie_nadpisuje"),
    "profil_szyna_lr": (
        "mostek/sciezki.py",
        'return len(czesci) == 4 and czesci[0] == "bus" and czesci[2] == "mix" and czesci[3] == "lr"',
        "return False  # MUTANT: szyna na Main LR nie zmienia profilu",
        "test_w_trakcie_cue"),
    "profil_po_odczycie": (
        "mostek/rdzen.py",
        "        if self._profil_po_odczycie(zmienione):\n            return\n",
        "",
        "test_inne_blokujace_naruszenie_w_trakcie_cue"),
    "klucz_zamykany_przy_blokadzie": (
        "mostek/rdzen.py",
        "blokuje = self.zapora.profil_blokuje   # POPRAWKA",
        "blokuje = False   # MUTANT",
        "test_w_trakcie_cue"),
    "cel_bez_klucza_przy_blokadzie": (
        "mostek/rdzen.py",
        "            if self.zapora.profil_blokuje:\n                wl = False\n",
        "            if False:  # MUTANT\n                wl = False\n",
        "test_mikrofon_i_sluchacz_na_antenie"),
    "odczyt_okresowy_szyn_lr": (
        "mostek/logika.py",
        "    a += [sciezki.szyna_lr(b) for b in range(1, 7)]\n    # Wszystkie wejścia klucza",
        "    # Wszystkie wejścia klucza",
        "test_zgubione_zgloszenie_lapie_odczyt_okresowy"),
    # Mute-Act (decyzja Michała z 17.10.2026, plan v22, rozdz. 6a).
    "mute_act_domyslnie": (
        "ustawienia/stanowisko.json",
        '"odciszaj_glosniki_po_wylaczeniu_mikrofonu": true,',
        '"odciszaj_glosniki_po_wylaczeniu_mikrofonu": false,',
        "test_po_wylaczeniu_mikrofonu"),
    "mute_act_po_select": (
        "mostek/rdzen.py",
        "            self.powiedz(self._z_mute_act(self._dopisz_odsluch(self._opis_rozmowcy(r), w)),\n"
        "                         Priorytet.STAN, \"przejscie\", dzwiek=True)",
        "            self.powiedz(self._dopisz_odsluch(self._opis_rozmowcy(r), w),\n"
        "                         Priorytet.STAN, \"przejscie\", dzwiek=True)",
        "test_po_select_ostatniego_cue"),
    "mute_act_po_f3": (
        "mostek/rdzen.py",
        "self.powiedz(self._z_mute_act(self._dopisz_odsluch(tekst, w)), Priorytet.STAN, \"przejscie\", dzwiek=True)",
        "self.powiedz(self._dopisz_odsluch(tekst, w), Priorytet.STAN, \"przejscie\", dzwiek=True)",
        "test_po_f3"),
    "mute_act_po_suwaku": (
        "mostek/rdzen.py",
        "        self.powiedz(self._z_mute_act(self._dopisz_odsluch(self._opis_rozmowcy(r), w)),\n"
        "                     Priorytet.STAN, f\"rozmowca-{r}\", dzwiek=True)",
        "        self.powiedz(self._dopisz_odsluch(self._opis_rozmowcy(r), w),\n"
        "                     Priorytet.STAN, f\"rozmowca-{r}\", dzwiek=True)",
        "test_po_suwaku_konczacym_ostatnie_cue"),
    "mute_act_profil": (
        "mostek/rdzen.py",
        "if (not self._gotowy() or self.zapora.profil_blokuje or self._kaszel is not None",
        "if (not self._gotowy() or self._kaszel is not None",
        "test_nie_przy_blokujacym_profilu"),
    "mute_act_kaszel": (
        "mostek/rdzen.py",
        "if (not self._gotowy() or self.zapora.profil_blokuje or self._kaszel is not None",
        "if (not self._gotowy() or self.zapora.profil_blokuje",
        "test_nie_w_trakcie_kaszlu"),
    "mute_act_tor_i_cue": (
        "mostek/rdzen.py",
        "        if self.widok.mikrofon_ma_otwarty_tor() is not False or self.widok.cue_zbior() != frozenset():\n"
        "            return \"\"\n        w = self._otworz(",
        "        w = self._otworz(",
        "test_po_select_ostatniego_cue"),
    # Luki z analizy v22 (L01-L06) i decyzje Michała z 18.10.2026 (P01, P02).
    # L03 i L06 mają też mutanty reguł zapory (glosniki_przy_niezgodnym_profilu,
    # sciezka_w_rejestrze) w NOWE_REGULY.
    "l01_kontroler_rozbraja": (
        "mostek/rdzen.py",
        "self.kontroler_polaczony = False  # POPRAWKA L01",
        "pass  # MUTANT L01",
        "test_utrata_kontrolera_rozbraja_powierzchnie"),
    "l02_limit_swiezosci": (
        "mostek/rdzen.py",
        "return self.zegar() - self._ost_swiezy <= limit + 1e-9  # POPRAWKA L02",
        "return True  # MUTANT L02",
        "test_otwarcie_po_limicie_swiezosci_wymaga_odczytu"),
    # Michał, 26.10.2026: komunikat po suwaku przepadał, gdy odczyt krytyczny
    # był tuż przed limitem świeżości. Mutant przywraca próg równy limitowi.
    "suwak_zapas_swiezosci": (
        "mostek/rdzen.py",
        "and not self._swiezy(prog)):  # POPRAWKA SUWAK",
        "and not self._swiezy(min(self.okres_krytyczny, self.limit_swiezosci))):  # MUTANT SUWAK",
        "test_komunikat_gdy_odczyt_tuz_przed_limitem"),
    "l03_glosniki_profil_rdzen": (
        "mostek/rdzen.py",
        "elif self.zapora.profil_blokuje:  # POPRAWKA L03",
        "elif False:  # MUTANT L03",
        "test_glosniki_wlacz_przy_blokujacym_profilu"),
    "l04_licznik_przed_opisem": (
        "mostek/rdzen.py",
        "self._aktualizuj_liczniki()  # POPRAWKA L04",
        "pass  # MUTANT L04",
        "test_pierwszy_odczyt_nowego_stanu_bez_czasu_poprzedniego"),
    "l05_odczyt_wejsc_klucza": (
        "mostek/logika.py",
        "    a += sciezki.wejscia_szyny(u.szyna_klucza)\n    a += [sciezki.MONITOR_ZRODLO,",
        "    a += [sciezki.MONITOR_ZRODLO,",
        "test_obca_wysylka_do_klucza_blokuje_i_jest_zamykana"),
    "l05_profil_blokuje": (
        "mostek/logika.py",
        "w kluczu przyciszania\", True))  # POPRAWKA L05",
        "w kluczu przyciszania\", False))  # MUTANT L05",
        "test_obca_wysylka_do_klucza_blokuje_i_jest_zamykana"),
    "l05_zamkniecie_obcego_wejscia": (
        "mostek/rdzen.py",
        "for a in obce_wejscia_klucza(self.u, w):   # POPRAWKA L05",
        "for a in []:   # MUTANT L05",
        "test_obca_wysylka_do_klucza_blokuje_i_jest_zamykana"),
    "p01_licznik_po_kaszlu": (
        "mostek/rdzen.py",
        'stany = {"mikrofon": self.widok.suma(MIKROFON)}  # POPRAWKA P01',
        'stany = {"mikrofon": True if self._kaszel is not None else self.widok.suma(MIKROFON)}  # MUTANT P01',
        "test_licznik_mikrofonu_po_kaszlu_liczy_od_nowa"),
    "p02_odczyt_bez_otwarc": (
        "mostek/rdzen.py",
        "            self._ochronne_zamkniecia()\n            return\n        # Zgłoszenie zmiany",
        "            pass  # MUTANT P02\n        # Zgłoszenie zmiany",
        "test_odczyt_okresowy_tylko_zamyka"),
    "p02_szyna_lr_zamykana": (
        "mostek/rdzen.py",
        "if w.stan.wartosc(sciezki.szyna_lr(b)) == 1:  # POPRAWKA P02",
        "if False:  # MUTANT P02",
        "test_pelny_odczyt_zamyka_szyne_na_main_lr_i_ostrzega"),
    # Tryby informacji zwrotnej, F4, F5 i ponowne otwarcie portu MIDI
    # (decyzja Michała z 17.10.2026, karta t_399b15a2).
    "tryb_ostrzezenie_traci_mowe": (
        "mostek/informacja.py",
        "mow = tryb is Tryb.DZWIEKI_Z_MOWA or priorytet == Priorytet.BEZPIECZENSTWO  # POPRAWKA",
        "mow = tryb is Tryb.DZWIEKI_Z_MOWA  # MUTANT: ostrzeżenie w trybie dźwięków bez mowy",
        "test_kazdy_klucz_bezpieczenstwa_zawsze_z_mowa"),
    "tryb_komunikat_spoza_stanow_traci_mowe": (
        "mostek/informacja.py",
        "if baza_zdarzenia(z) not in KOMUNIKATY_DZWIEKIEM:  # POPRAWKA",
        "if False:  # MUTANT: każdy komunikat z dźwiękiem może stracić mowę",
        "test_kazdy_klucz_bezpieczenstwa_zawsze_z_mowa"),
    "f5_wykonuje_zapis": (
        "mostek/rdzen.py",
        "self.mowa.powiedz(self._ostatni, Priorytet.STAN, \"powtorz\")  # POPRAWKA F5",
        "self.przelacz_mikrofon()  # MUTANT F5: zapis do miksera",
        "test_powtarza_mowa_komunikat_ktory_byl_tylko_dzwiekiem"),
    "f5_czyta_mikser": (
        "mostek/rdzen.py",
        "rodzaj == \"klawisz\" and z[1] in KLAWISZE_BEZ_MIKSERA):  # POPRAWKA F5",
        "False):  # MUTANT F5: odczyt miksera przed F4 i F5",
        "test_powtarza_mowa_komunikat_ktory_byl_tylko_dzwiekiem"),
    "f4_nie_oglasza_trybu": (
        "mostek/rdzen.py",
        "self.mowa.powiedz(tekst, Priorytet.STAN, \"tryb\")  # POPRAWKA F4",
        "pass  # MUTANT F4: tryb bez ogłoszenia",
        "test_cykl_i_ogloszenie_mowa_w_kazdym_trybie"),
    "tryb_blad_dzwieku_bez_mowy": (
        "mostek/mowa.py",
        "mow = True  # POPRAWKA: brak pliku albo błąd odtwarzania",
        "pass  # MUTANT: nieudany dźwięk bez mowy",
        "test_po_kolei_zawiedziony_dzwiek_daje_mowe"),
    "tryb_blad_dzwieku_naraz_bez_mowy": (
        "mostek/mowa.py",
        "mow = True  # POPRAWKA NARAZ: brak pliku albo błąd odtwarzania",
        "pass  # MUTANT: nieudany dźwięk naraz bez mowy",
        "test_blad_odtwarzania_mowa_i_jedno_ostrzezenie"),
    "tryb_ostrzezenie_nie_przerywa_dzwieku": (
        "mostek/mowa.py",
        "if any(kazdy or w[0] < priorytet for w in self._oczekujace):  # POPRAWKA: ostrzeżenie przerywa",
        "if False:  # MUTANT: ostrzeżenie czeka do końca dźwięku stanu",
        "test_ostrzezenie_przerywa_dzwiek_stanu_i_stan_nie_ginie"),
    "midi_bez_ponawiania": (
        "mostek/rdzen.py",
        "ponow(self.zegar())  # POPRAWKA MIDI",
        "pass  # MUTANT MIDI: brak ponawiania otwarcia portu",
        "test_utrata_proby_powrot"),
    "midi_milczacy_stol_bez_utraty": (
        "mostek/xtouch.py",
        "self._zamkniecie_portu(\"kontroler nie odpowiada\")  # POPRAWKA ZYCIE",
        "pass  # MUTANT ZYCIE: milczący stół bez utraty",
        "test_milczacy_port_to_utrata_i_powrot_bez_restartu_mostka"),
    # Talkback głośno jak w CUE i przyciszona muzyka u adresata
    # (zlecenie Michała z 26.10.2026).
    "talkback_poziom_bez_korekty": (
        "mostek/rdzen.py",
        "p = poziom_db_na_float(self._mikrofon_w_rozmowie_db(self.u.poziom_bazowy(MIKROFON, odb)))",
        "p = poziom_db_na_float(self.u.poziom_bazowy(MIKROFON, odb))  # MUTANT: talkback ciszej niż CUE",
        "test_suwak_w_gorze_talkback_tak_glosno_jak_cue"),
    "talkback_bez_przyciszenia_muzyki": (
        "mostek/rdzen.py",
        "        cel.update(self._muzyka_chwilowa(adresaci, przyciszona=True))",
        "        pass  # MUTANT: muzyka u adresata zostaje na pełnym poziomie",
        "test_przyciszona_w_trakcie_i_dokladnie_przywrocona_po"),
    "talkback_bez_przywrocenia_muzyki": (
        "mostek/rdzen.py",
        "            cel.update(self._muzyka_chwilowa(self._muzyka_przyciszona, przyciszona=False))\n"
        "            return cel",
        "            return cel  # MUTANT: po puszczeniu muzyka zostaje przyciszona",
        "test_przyciszona_w_trakcie_i_dokladnie_przywrocona_po"),
    "talkback_przyciszenie_przez_zero": (
        "mostek/rdzen.py",
        "            elif float(v) > float(cel[a]) + TOL:\n"
        "                zamknij.append(Krok(a, cel[a]))   # muzyka ciszej bez przerwy w dźwięku",
        "            elif float(v) > float(cel[a]) + TOL:\n"
        "                zamknij.append(Krok(a, 0.0))  # MUTANT: muzyka urwana na czas sekwencji",
        "test_przyciszenie_bez_przerwy_w_dzwieku"),
    "talkback_przycisza_nieadresata": (
        "mostek/rdzen.py",
        "        return set(self._talkback)\n",
        "        return set(self.widok.rozmowcy())  # MUTANT: przyciszenie u wszystkich\n",
        "test_tylko_adresat_drugi_rozmowca_bez_zmian"),
    "talkback_przyciszenie_wylaczalne": (
        "mostek/rdzen.py",
        "if not self._talkback or not self.u.przyciszenie_muzyki_talkback:",
        "if not self._talkback:  # MUTANT: ustawienie false nic nie zmienia",
        "test_ustawienie_false_zachowuje_dzisiejsze_zachowanie"),
    "talkback_obca_zmiana_muzyki_cofana": (
        "mostek/rdzen.py",
        "            chronione |= muzyka_adresatow\n",
        "            pass  # MUTANT: obca zmiana wysyłki muzyki nie przerywa talkbacku\n",
        "test_obca_zmiana_wysylki_muzyki_przerywa_bez_przywracania"),
    "talkback_muzyka_nie_podaza_za_antena": (
        "mostek/rdzen.py",
        "                elif a in chwilowy:\n"
        "                    # Muzyka adresata talkbacku zostaje przyciszona także wtedy,\n"
        "                    # gdy w trakcie trzymania weszła na antenę albo z niej zeszła\n"
        "                    # (SARA, suwak muzyki): wysyłka podąża za stanem, ale ciszej.\n"
        "                    cw.poziom = chwilowy[a]",
        "                elif False:  # MUTANT: muzyka wchodząca na antenę na pełnym poziomie\n"
        "                    cw.poziom = chwilowy[a]",
        "test_muzyka_wchodzi_i_schodzi_z_anteny_w_trakcie"),
}
MODUL_TESTU = {n: "test_przelaczniki" for n in MUTANTY_POPRAWEK if n.startswith("mute_act")}
MODUL_TESTU.update({n: "test_kaszel_solo" for n in MUTANTY_POPRAWEK if n.startswith("kaszel_solo_")})
MODUL_TESTU.update({n: "test_talkback_glosniki" for n in MUTANTY_POPRAWEK if n.startswith("talkback_glosniki_")})
# Talkback: poziom jak w CUE i przyciszona muzyka u adresata (26.10.2026).
MODUL_TESTU.update({n: "test_talkback_muzyka" for n in MUTANTY_POPRAWEK
                    if n.startswith("talkback_") and not n.startswith("talkback_glosniki_")})
MODUL_TESTU.update({n: "test_luki_v22" for n in MUTANTY_POPRAWEK if n[:3] in ("l01", "l02", "l03", "l04", "l05",
                                                                              "p02")})
MODUL_TESTU.update({n: 'test_scena_mr18.ScenaMR18.' + v[3]
                   for n, v in MUTANTY_POPRAWEK.items() if n.startswith('scena_')})
MODUL_TESTU["p01_licznik_po_kaszlu"] = "test_dr_v21"
MODUL_TESTU.update({n: "test_tryby_dzwiekow" for n in MUTANTY_POPRAWEK if n.startswith(("tryb_", "f4_", "f5_", "midi_"))})
# Dźwięki po kolei (dzwieki_naraz false albo winsound): test w test_dzwieki_naraz.
MODUL_TESTU["tryb_blad_dzwieku_bez_mowy"] = "test_dzwieki_naraz"
MODUL_TESTU["suwak_zapas_swiezosci"] = "test_dzwiek_suwaka"
MODUL_TESTU.update({n: "test_mikrofon_suwak" for n in MUTANTY_POPRAWEK if n.startswith("mikrofon_")})


def mutuj(zrodlo: str, regula: str) -> str:
    """Kod logika.py z wyłączoną regułą. Rzuca ValueError, gdy reguły nie ma."""
    wzor = re.compile(rf'^def regula_{regula}\([^\n]*\)[^\n]*:\n(\s+"""(?:.|\n)*?"""\n)', re.M)
    m = wzor.search(zrodlo)
    if not m:
        raise ValueError(f"nie znaleziono funkcji regula_{regula}")
    wstawka = f"    return {POWROT.get(regula, '[]')}  # MUTANT: reguła wyłączona\n"
    return zrodlo[:m.end()] + wstawka + zrodlo[m.end():]


def uruchom(katalog: Path, pelne: bool, modul: str = "test_niezmienniki") -> tuple[int, str]:
    polecenie = [sys.executable, "-B", "-m", "unittest"]
    if pelne:
        polecenie += ["discover", "-s", "tests"]
    else:
        polecenie += [modul]
    wynik = subprocess.run(polecenie, cwd=katalog if pelne else katalog / "tests",
                           capture_output=True, text=True, timeout=900)
    return wynik.returncode, wynik.stdout + wynik.stderr


def padniete(wyjscie: str) -> list[tuple[str, str]]:
    """(nazwa testu, pierwsza linia błędu) dla każdego FAIL/ERROR."""
    wynik = []
    for blok in wyjscie.split("=" * 70)[1:]:
        naglowek = blok.strip().splitlines()[0] if blok.strip() else ""
        m = re.match(r"(FAIL|ERROR): (\S+)", naglowek)
        if not m:
            continue
        bledy = [w for w in blok.splitlines() if w.startswith(("AssertionError", "Error", "Exception"))
                 or "Error:" in w]
        wynik.append((m.group(2), bledy[-1].strip() if bledy else ""))
    return wynik


def zbadaj(pelne: bool = False) -> dict:
    zrodlo = (KATALOG / "mostek" / "logika.py").read_text(encoding="utf-8")
    raport = {"pelne": pelne, "reguly": {}}
    with tempfile.TemporaryDirectory(prefix="mostek-mutacje-") as tmp:
        kopia = Path(tmp) / "mostek"
        shutil.copytree(KATALOG, kopia, ignore=shutil.ignore_patterns(".git", "__pycache__", "dziennik"))
        kod, wyj = uruchom(kopia, pelne)
        raport["oryginal_ok"] = kod == 0
        raport["zlozone"] = {z: {} for z in REGULY_ZLOZONE}
        for regula in NOWE_REGULY:
            (kopia / "mostek" / "logika.py").write_text(mutuj(zrodlo, regula), encoding="utf-8")
            kod, wyj = uruchom(kopia, pelne)
            pad = padniete(wyj)
            wlasny = [p for p in pad if p[0] == f"test_regula_{regula}"]
            raport["reguly"][regula] = {
                "kod_wyjscia": kod,
                "padniete": [p[0] for p in pad],
                "wlasny_test_padl": bool(wlasny),
                "powod": wlasny[0][1] if wlasny else "",
                "zabity": kod != 0 and bool(wlasny) and "not raised" in (wlasny[0][1] if wlasny else ""),
            }
            for zlozona, straznicy in REGULY_ZLOZONE.items():
                if regula in straznicy:
                    t = [p for p in pad if p[0] == f"test_{zlozona}_{regula}"]
                    raport["zlozone"][zlozona][regula] = {
                        "test_padl": bool(t), "powod": t[0][1] if t else "",
                        "zabity": bool(t) and "not raised" in t[0][1],
                    }
        (kopia / "mostek" / "logika.py").write_text(zrodlo, encoding="utf-8")
        raport["poprawki"] = {}
        for nazwa, (plik, stary, nowy, test) in MUTANTY_POPRAWEK.items():
            sciezka = kopia / plik
            oryginal = sciezka.read_text(encoding="utf-8")
            if oryginal.count(stary) != 1:
                raise ValueError(f"mutant {nazwa}: fragment nie występuje dokładnie raz w {plik}")
            sciezka.write_text(oryginal.replace(stary, nowy), encoding="utf-8")
            try:
                kod, wyj = uruchom(kopia, pelne, MODUL_TESTU.get(nazwa, "test_niezmienniki"))
            finally:
                sciezka.write_text(oryginal, encoding="utf-8")
            pad = padniete(wyj)
            wlasny = [p for p in pad if p[0] == test]
            raport["poprawki"][nazwa] = {"kod_wyjscia": kod, "test": test,
                                         "padniete": sorted({p[0] for p in pad}),
                                         "zabity": kod != 0 and bool(wlasny)}
    return raport


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Test mutacyjny reguł zapory modelu CUE")
    p.add_argument("--pelne", action="store_true", help="cały zestaw testów na każdym mutancie")
    p.add_argument("--json", action="store_true", help="raport JSON zamiast streszczenia")
    a = p.parse_args(argv)
    r = zbadaj(a.pelne)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(f"Oryginał: {'testy przechodzą' if r['oryginal_ok'] else 'TESTY PADAJĄ'}")
        for regula, w in r["reguly"].items():
            stan = "zabity" if w["zabity"] else "PRZEŻYŁ"
            print(f"{regula}: {stan}; padło testów {len(w['padniete'])}: {', '.join(w['padniete'])}; {w['powod']}")
        for zlozona, straznicy in r["zlozone"].items():
            for regula, w in straznicy.items():
                stan = "zabity" if w["zabity"] else "PRZEŻYŁ"
                print(f"{zlozona} pilnowany przez {regula}: {stan}; test_{zlozona}_{regula}: {w['powod']}")
        for nazwa, w in r["poprawki"].items():
            stan = "zabity" if w["zabity"] else "PRZEŻYŁ"
            print(f"poprawka {nazwa}: {stan}; {w['test']}; padło testów {len(w['padniete'])}: "
                  f"{', '.join(w['padniete'])}")
    zlozone_ok = all(w["zabity"] for s in r["zlozone"].values() for w in s.values()) and all(
        set(r["zlozone"][z]) == set(s) for z, s in REGULY_ZLOZONE.items())
    poprawki_ok = all(w["zabity"] for w in r["poprawki"].values())
    return 0 if r["oryginal_ok"] and zlozone_ok and poprawki_ok and all(
        w["zabity"] for w in r["reguly"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
