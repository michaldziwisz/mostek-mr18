"""Walidacja surowych danych, bez urządzeń, konwersji ani zapisu.

Profil v1 opisuje obecny kod, nie nowy adapter sprzętu. Tryb instalatora
odrzuca nowe niespójności. Start zachowuje dotychczasową funkcję konwersji
oraz jej reguły; nowe problemy trafiają tylko do dziennika.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


PROFIL_V1 = {
    'nazwa': 'MR18 + X-TOUCH MC v1', 'wersja_schematu': 1,
    'mikser': 'MR18, protokół X AIR (inne modele wymagają kwalifikacji)',
    'wejscia': 16, 'szyny': 6, 'usb': 18,
    'kontroler': 'X-TOUCH MC', 'paski': 8, 'master': 'monitor/słuchawki',
    'mikrofony_lokalne': 1, 'rozmowcy': ['telefon', 'zoom'],
    'przyciszani_sluchacze': 1, 'playout': ['sara', 'stationplaylist', 'auto', 'brak'],
    'playout_bez_programu': 'wyłącznie --emisja brak, nie emisja.program w JSON',
    'usb_stale': {'1': 'N-1 Zoom, lewy', '2': 'N-1 Zoom, prawy',
                  '3': 'antena Main L', '4': 'antena Main R'},
    'usb_pozostale': 'projekt BAZA: kopia Main L/R POST; dopuszczalny suchy głos tylko według profil.usb_suche_dozwolone',
}
BRAK = object()


@dataclass(frozen=True)
class Problem:
    sciezka: str
    komunikat: str
    poziom: str = 'błąd'


@dataclass(frozen=True)
class Pole:
    typ: str
    wymagane: bool = False
    domyslne: object = BRAK
    minimum: float | None = None
    maksimum: float | None = None
    wartosci: tuple | None = None
    element: Pole | None = None
    pola: dict | None = None
    niepuste: bool = False
    null: bool = False


def tekst(**kw):
    return Pole('tekst', **kw)


def liczba(minimum=None, maksimum=None, **kw):
    return Pole('liczba', minimum=minimum, maksimum=maksimum, **kw)


def calkowita(minimum=None, maksimum=None, **kw):
    return Pole('całkowita', minimum=minimum, maksimum=maksimum, **kw)


def logiczna(**kw):
    return Pole('logiczna', **kw)


def lista(element, **kw):
    return Pole('lista', element=element, **kw)


def obiekt(pola, **kw):
    return Pole('obiekt', pola=pola, **kw)


def mapa(element, **kw):
    return Pole('mapa', element=element, **kw)


# Lista komunikatów i znanych komentarzy jest zamrożona dla profilu v1,
# a nie odczytywana z walidowanego pliku. Nie potrzeba danych obok EXE.
KOMUNIKATY_V1 = ('wlaczony_m',
 'wylaczony_m',
 'wlaczony_z',
 'wylaczony_z',
 'mikrofon_stan',
 'mikrofon_talkback',
 'talkback_obaj',
 'nauka_talkback',
 'talkback_odmowa',
 'talkback_glosniki',
 'talkback_glosniki_powrot',
 'zapora_glosniki_bez_mikrofonu',
 'zapora_chwilowy_bez_anteny',
 'zapora_chwilowy_bez_klucza',
 'zapora_talkback_tylko_adresaci',
 'zapora_talkback_przed_suwakiem',
 'zapora_talkback_izolacja',
 'zapora_kaszel_bez_wysylek',
 'talkback_brak_bazy',
 'talkback_przerwany',
 'talkback_niepotwierdzony',
 'kaszel_nieznany',
 'kaszel_niepotwierdzony',
 'suma_stan',
 'wysylka_stan',
 'pfl_stan',
 'mikrofon_nie_wlaczony',
 'mikrofon_moze_byc_wlaczony',
 'moze_byc_wlaczony',
 'stan_nieznany_wylaczam_mikrofon',
 'stan_nieznany_zamykam_rozmowe',
 'czekam',
 'powod_glosniki',
 'powod_brak_lacznosci',
 'powod_profil',
 'powod_niepotwierdzone',
 'utrata_lacznosci',
 'powrot_lacznosci',
 'stan_nieznany',
 'z_innego_urzadzenia',
 'scena_z_innego',
 'profil_zmieniony',
 'najpierw_zwolnij_cue',
 'rozmowa_poza_antena',
 'mikrofon_poza_antena_rozmowa',
 'rozmowa_wszyscy',
 'suwak_trzymany',
 'rozmowca_czeka',
 'rozmowca_czeka_poza_suma',
 'rozmowca_poza_suma',
 'rozmowca_na_antenie',
 'rozmowca_w_rozmowie',
 'rozmowca_moze_byc_na_antenie',
 'koniec_rozmowy',
 'brak_rozmowy',
 'przejscie_niepelne',
 'przejscie_przerwane_obce',
 'odsluch_niepotwierdzony',
 'suwak_wolny',
 'pasek_wolny',
 'przycisk_wolny',
 'klawisz_wolny',
 'na_antene_suwakiem',
 'mikrofon_bez_cue',
 'funkcja_techniczna',
 'granica_wzmocnienia',
 'wzmocnienie',
 'glosniki_wyciszone',
 'glosniki_wlaczone',
 'glosniki_odrzucone',
 'glosniki_moga_grac',
 'profil_niezgodny',
 'pary_rozbiezne',
 'sluchasz_programu',
 'sluchasz_rozmowy',
 'koniec_pfl',
 'monitor',
 'powierzchnia',
 'synchronizacja_zgodna',
 'synchronizacja_brak',
 'solo_aktywne',
 'solo_brak',
 'suwak_na_dole',
 'suwak_w_gorze',
 'suwak_db',
 'emisja_nie_znaleziono',
 'emisja_niepotwierdzona',
 'emisja_wymaga_tcp',
 'emisja_kolejka_pelna',
 'emisja_polecenie_przeterminowane',
 'emisja_gra_utwor',
 'emisja_co_gra',
 'emisja_pozostalo',
 'emisja_odtwarzacz',
 'emisja_odtwarzacze',
 'emisja_odtwarzacze_spojnik',
 'emisja_odtwarzacz_spl',
 'emisja_odtwarzacz_bledne_dane',
 'nauka_bank_lewo',
 'nauka_bank_prawo',
 'nauka_channel_prawo',
 'nauka_zoom',
 'emisja_pauza_utworu',
 'emisja_nic_nie_gra',
 'emisja_nastepny',
 'emisja_automat_wlaczony',
 'emisja_automat_wylaczony',
 'emisja_automat_wstrzymany',
 'emisja_automat_zwolniony',
 'emisja_automat_zwolniony_zatrzymane',
 'emisja_automat_zatrzymane',
 'emisja_automat_za_pozno',
 'emisja_automat_blad',
 'miks_otwarte',
 'miks_pozycja',
 'miks_punkt',
 'miks_nieustawione',
 'miks_ustawione',
 'miks_usuniete',
 'miks_info',
 'miks_niezapisane',
 'miks_porzucone',
 'miks_zapisano',
 'miks_zapisano_bez_przejscia',
 'miks_przejscie_za',
 'miks_przejscie_teraz',
 'miks_kolejnosc',
 'miks_petla',
 'miks_tylko_sara',
 'miks_busy',
 'miks_empty',
 'miks_pfl',
 'miks_session',
 'miks_utrata',
 'miks_niepotwierdzone',
 'miks_bledne_dane',
 'miks_odsluch_brak',
 'miks_odsluch_pozycja',
 'miks_odsluch_punkt',
 'miks_odsluch_przejscie',
 'miks_nazwa_cue',
 'miks_nazwa_intro',
 'miks_nazwa_outro',
 'miks_nazwa_segue',
 'miks_nazwa_segue_fade',
 'miks_nazwa_overlap',
 'miks_nazwa_loop_start',
 'miks_nazwa_loop_end',
 'emisja_brak_utworu',
 'emisja_utwor',
 'emisja_artysta_tytul',
 'emisja_bez_tytulu',
 'emisja_zero_sekund',
 'emisja_zaznaczony',
 'emisja_niezaznaczony',
 'emisja_utwor_gra',
 'emisja_utwor_pauza',
 'emisja_utwor_zagrany',
 'emisja_przerwa_po',
 'emisja_znacznik_przelaczony',
 'emisja_gra',
 'emisja_pauza',
 'emisja_stop',
 'emisja_nie_odpowiada',
 'emisja_brak',
 'emisja_nie_wybrano',
 'sterowanie_nie_odpowiada',
 'sterowanie_uruchomione',
 'nadzorca_restart',
 'wyciszony_wszedzie',
 'odciszony',
 'licznik',
 'mikrofon_licznik',
 'mikrofon_kaszel',
 'kaszel_bez_anteny',
 'kaszel_przerwany',
 'cisza_na_antenie',
 'alarm_ciszy_wlaczony',
 'alarm_ciszy_wylaczony',
 'dzwiek_na_antenie',
 'mierniki_niedostepne',
 'mierniki_dostepne',
 'kontroler_utracony',
 'kontroler_powrot',
 'kontroler_otwieranie',
 'kontroler_odlaczony',
 'powod_kontroler',
 'powod_nieswiezy',
 'glosniki_odrzucone_profil',
 'glosniki_odrzucone_nieznany',
 'glosniki_odrzucone_kontroler',
 'status_profil',
 'profil_zgodny',
 'ochronne_zamkniecie',
 'ochronne_zamkniecie_niepotwierdzone',
 'ochrona_szyna_lr',
 'ochrona_klucz_obce',
 'ochrona_klucz',
 'ochrona_klucz_poza_rozmowa',
 'tryb_mowa',
 'tryb_dzwieki',
 'tryb_dzwieki_z_mowa',
 'tryb_niezapisany',
 'brak_powtorzenia')
KOMENTARZE_V1 = frozenset(['_bank_channel_opis',
 '_bez_alarmu_opis',
 '_cisza_opis',
 '_d_r_opis',
 '_dzwiek_ostrzezenia_opis',
 '_dzwieki_naraz_opis',
 '_emisja_hold_opis',
 '_emisja_tcp_opis',
 '_klawisze_opis',
 '_krotko_gdy_gra_opis',
 '_mikrofon_rozmowa_opis',
 '_mikrofon_wstrzymuje_automat_opis',
 '_miks_opis',
 '_nawigacja_status',
 '_odciszaj_opis',
 '_odmowy_opis',
 '_odtwarzacze_opis',
 '_okno_opis',
 '_okres_opis',
 '_opis',
 '_opoznienie_opis',
 '_paski_opis',
 '_pfl_opis',
 '_ponowienie_opis',
 '_prog_opis',
 '_program_cue_opis',
 '_przyciszenie_opis',
 '_przyciszenie_talkback_opis',
 '_suwak_opis',
 '_talkback_opis',
 '_tap_opis',
 '_transport_status',
 '_tryby_opis',
 '_usb_suche_opis',
 '_v22_opis',
 '_zycie_opis'])


ZRODLO = obiekt({
    'nazwa': tekst(wymagane=True, niepuste=True),
    'rodzaj': tekst(wartosci=('m', 'z'), domyslne='m'),
    'kanaly': lista(calkowita(1, PROFIL_V1['wejscia']), wymagane=True, niepuste=True),
    'glos': logiczna(domyslne=False), 'odbiorca': tekst(null=True),
    'dopelniacz': tekst(), 'rozmowca': tekst(), 'z_kim': tekst(),
    'suwak_maks_db': liczba(0, 10, domyslne=0.0),
    'galka': obiekt({'typ': tekst(wartosci=('gain', 'rtntrim'), wymagane=True),
                     'wejscie': calkowita(1, 16)}, null=True),
})
ODBIORCA = obiekt({
    'nazwa': tekst(wymagane=True, niepuste=True), 'do': tekst(wymagane=True),
    'szyny': lista(calkowita(1, PROFIL_V1['szyny']), wymagane=True, niepuste=True),
    'wlasne_zrodlo': tekst(wymagane=True, niepuste=True),
})
PASEK = obiekt({
    'pasek': calkowita(1, PROFIL_V1['paski'], wymagane=True),
    'zrodlo': tekst(null=True),
    'rec': tekst(wartosci=('antena_mikrofonu', 'suwakiem', 'alarm_ciszy'), null=True),
    'select': tekst(wartosci=('cue', 'pfl', 'bez_cue', 'antena_mikrofonu'), null=True),
    'mute': tekst(wartosci=('kaszel', 'talkback'), null=True),
})
SCHEMAT = obiekt({
    # Brak wersji jest normalną postacią v1, bez ostrzeżenia o migracji.
    'wersja_schematu': calkowita(wartosci=(1,)),
    'zrodla': mapa(ZRODLO, wymagane=True), 'odbiorcy': mapa(ODBIORCA, wymagane=True),
    'paski': lista(PASEK, wymagane=True),
    'szyny': obiekt({
        'podsluch_telefonu': calkowita(1, 6, wymagane=True),
        'klucz_przyciszania': calkowita(1, 6, wymagane=True),
        'glosniki': lista(calkowita(1, 6), wymagane=True, niepuste=True),
        'nazwy': mapa(tekst()),
    }, wymagane=True),
    'profil': obiekt({
        'wyjscia_usb': calkowita(1, PROFIL_V1['usb'], domyslne=18),
        'usb_suche_dozwolone': lista(calkowita(1, 18), domyslne=[]),
        'linki_kanalow': lista(calkowita(wartosci=tuple(range(1, 16, 2)))),
        'linki_szyn': lista(calkowita(wartosci=(1, 3, 5))),
    }, wymagane=True),
    'przyciszanie': obiekt({
        'sluchacz': tekst(domyslne='telefon'),
        'zrodla_klucza': lista(tekst(), niepuste=True, domyslne=['mikrofon', 'zoom']),
        'profil': obiekt({'inserty': mapa(tekst())}),
    }, domyslne={}),
    'mikser': obiekt({
        'port': calkowita(1, 65535, domyslne=10024),
        'limit_odpowiedzi_s': liczba(0, wymagane=True),
        'dodatkowe_proby': calkowita(0, wymagane=True),
        'tolerancja_float': liczba(0, 1, wymagane=True),
        'odnowienie_xremote_s': liczba(0), 'okres_odczytu_krytycznego_s': liczba(0),
        'limit_swiezosci_s': liczba(0), 'przerwa_podwojnego_odczytu_s': liczba(0),
        'okres_ponowienia_polaczenia_s': liczba(0),
        'okno_zapytan': calkowita(0, domyslne=16),
        'szybka_powtorka_s': liczba(0, domyslne=0.03),
        'przerwa_ponowienia_s': liczba(0, domyslne=0.0),
        'cisza_utraty_s': liczba(0, domyslne=0.0),
        'dopasuj_do_opoznienia': logiczna(domyslne=True),
        'maks_limit_rundy_s': liczba(0, domyslne=3.0),
    }, wymagane=True),
    'zachowanie': obiekt({
        'prog_suwaka_na_antenie_db': liczba(-90, 10, domyslne=-50.0),
        # Stary loader stosuje -abs; dodatnia wartość jest dopuszczalna.
        'przyciszenie_muzyki_cue_db': liczba(-60, 60, domyslne=-15.0),
        'przyciszenie_pfl_cue_db': liczba(-40, 0, domyslne=-10.0),
        'mikrofon_w_rozmowie_jak_na_antenie': logiczna(domyslne=True),
        'przyciszenie_muzyki_talkback': logiczna(domyslne=True),
        'program_w_sluchawkach_przy_cue': logiczna(domyslne=True),
        'pfl_podaza_za_cue': logiczna(domyslne=True),
        'odciszaj_glosniki_po_wylaczeniu_mikrofonu': logiczna(domyslne=True),
        'krok_galki_db': liczba(0, domyslne=1.0),
        'zakres_galki_db': liczba(0, domyslne=12.0),
        'zwloka_komunikatu_galki_s': liczba(0, domyslne=0.5),
        'zwloka_potwierdzenia_suwaka_s': liczba(0), 'debounce_s': liczba(0),
        'drugi_stop_w_ciagu_s': liczba(0, domyslne=1.0),
        'kaszel_maks_s': liczba(),  # pole ignorowane przez rdzeń
        'przypomnienie_mikrofonu_min': liczba(0, domyslne=0),
        'alarm_ciszy': obiekt({'wlaczony': logiczna(),
            'prog_dbfs': liczba(-90, 0, domyslne=-50.0),
            'czas_s': liczba(0, domyslne=10.0), 'powtorka_s': liczba(0, domyslne=30.0)}),
    }, wymagane=True),
    'xtouch': obiekt({
        'status': tekst(), 'nazwa_urzadzenia_midi': tekst(domyslne='X-TOUCH'),
        'pasek_nuty': obiekt({k: calkowita(0, 120, wymagane=True) for k in
            ('rec', 'solo', 'mute', 'select', 'galka_wcisnij', 'dotyk_suwaka')}, wymagane=True),
        'dotyk_master': calkowita(0, 127, wymagane=True),
        'galka_cc': calkowita(0, 120, wymagane=True),
        'jog_cc': calkowita(0, 127, domyslne=60),
        'pierscien_cc': calkowita(0, 120, wymagane=True),
        'kanal_master_pitchbend': calkowita(0, 15, wymagane=True),
        'suwak_wymaga_dotyku': logiczna(domyslne=True),
        'ponowienie_portu_s': liczba(0.2, 60, domyslne=2.0),
        'zycie_s': liczba(0, 30, domyslne=1.0),
        'zycie_proby': calkowita(1, 10, domyslne=2),
        'klawisze': mapa(tekst(), wymagane=True), 'punkty_miksu': mapa(tekst()),
    }, wymagane=True),
    'komunikaty': mapa(tekst(), wymagane=True),
    'informacja_zwrotna': obiekt({
        'katalog_dzwiekow': tekst(), 'plik_trybu': tekst(domyslne='ustawienia/tryb_informacji.json'),
        'dzwiek_ostrzezenia': tekst(null=True, niepuste=True), 'dzwieki_naraz': logiczna(),
        'zdarzenia': mapa(Pole('dźwięk'), domyslne={}),
    }, domyslne={}),
    'emisja': obiekt({
        'program': tekst(domyslne='auto'), 'preferowany': tekst(),
        'spl_port': calkowita(1, 65535), 'sara_port': calkowita(1, 65535),
        'limit_odpowiedzi_s': liczba(0), 'jog_zwloka_s': liczba(0),
        'mikrofon_wstrzymuje_automat': logiczna(domyslne=True),
        'krotko_gdy_gra': logiczna(), 'spl_kodowanie': tekst(),
    }, wymagane=True),
    'mierniki': obiekt({
        'identyfikator': tekst(), 'indeksy_main_lr': lista(calkowita(0), niepuste=True),
        'kolejnosc_bajtow': tekst(wartosci=('little', 'big')),
        'odnowienie_s': liczba(0), 'limit_braku_s': liczba(0),
    }),
    'nadzorca': obiekt({
        'port': calkowita(1, 65535), 'okres_sygnalu_s': liczba(0),
        'limit_ciszy_s': liczba(0), 'maks_restartow': calkowita(0), 'okno_restartow_s': liczba(0),
    }, wymagane=True),
    'dziennik': obiekt({'plik': tekst()}),
})
POZIOMY = obiekt({
    'wysylki': mapa(mapa(liczba(-90, 10)), wymagane=True),
    'podsluch_telefonu_db': liczba(-90, 10, domyslne=0.0),
    'klucz_przyciszania_db': liczba(-90, 10, domyslne=0.0),
})


def _sciezka(rodzic, klucz):
    return f'{rodzic}.{klucz}' if rodzic else str(klucz)


class _Kontrola:
    def __init__(self):
        self.problemy = []
        self.bledne = set()

    def dodaj(self, sciezka, komunikat, poziom='błąd'):
        self.problemy.append(Problem(sciezka or '$', komunikat, poziom))
        if poziom == 'błąd':
            self.bledne.add(sciezka)

    def sprawdz(self, v: Any, s: Pole, path=''):
        if v is BRAK:
            if s.wymagane:
                self.dodaj(path, 'brak wymaganego pola')
            elif s.domyslne is not BRAK:
                self.dodaj(path, 'brak pola; wartość domyślna: ' +
                           json.dumps(s.domyslne, ensure_ascii=False), 'ostrzeżenie')
            return
        if v is None and s.null:
            return
        poprawny = {
            'tekst': lambda: isinstance(v, str),
            'liczba': lambda: type(v) is int or (type(v) is float and math.isfinite(v)),
            'całkowita': lambda: type(v) is int,
            'logiczna': lambda: type(v) is bool,
            'lista': lambda: isinstance(v, list),
            'obiekt': lambda: isinstance(v, dict),
            'mapa': lambda: isinstance(v, dict),
            'dźwięk': lambda: (isinstance(v, str) and bool(v)) or
                (isinstance(v, list) and all(isinstance(x, str) and x for x in v)),
        }[s.typ]()
        if not poprawny:  # WAL_TYPY
            self.dodaj(path, f'niewłaściwy typ; wymagany: {s.typ}' + (' albo null' if s.null else ''))
            return
        if s.niepuste and not v:
            self.dodaj(path, 'wartość nie może być pusta')
        if s.wartosci is not None and v not in s.wartosci:
            self.dodaj(path, 'dozwolone wartości: ' + ', '.join(map(str, s.wartosci)))
        if s.minimum is not None and not s.minimum <= v:  # WAL_ZAKRES_MIN
            self.dodaj(path, f'wartość poniżej minimum {s.minimum}')
        if s.maksimum is not None and not v <= s.maksimum:  # WAL_ZAKRES_MAX
            self.dodaj(path, f'wartość powyżej maksimum {s.maksimum}')
        if s.typ == 'lista':
            assert s.element is not None
            for i, x in enumerate(v):
                self.sprawdz(x, s.element, f'{path}[{i}]')
        elif s.typ in ('obiekt', 'mapa'):
            if s.typ == 'obiekt':
                assert s.pola is not None
                for k, spec in s.pola.items():
                    self.sprawdz(v.get(k, BRAK), spec, _sciezka(path, k))
            for k, x in v.items():
                p = _sciezka(path, k)
                if not isinstance(k, str):
                    self.dodaj(p, 'nazwa pola musi być tekstem')
                elif k.startswith('_'):
                    if k not in KOMENTARZE_V1:
                        self.dodaj(p, 'nieznany klucz komentarza; ignorowany przez mostek', 'ostrzeżenie')
                elif s.typ == 'mapa':
                    assert s.element is not None
                    self.sprawdz(x, s.element, p)
                elif s.pola is not None and k not in s.pola:
                    self.dodaj(p, 'nieznany klucz; ignorowany przez mostek', 'ostrzeżenie')

    def mozna(self, path):
        return not any(path == p or path.startswith(p + '.') or path.startswith(p + '[')
                       for p in self.bledne)


def _obiekt(v):
    return v if isinstance(v, dict) else {}


def _lista(v):
    return v if isinstance(v, list) else []


def _wpisy(v):
    return {k: x for k, x in _obiekt(v).items() if isinstance(k, str) and not k.startswith('_')}


def waliduj(dane, poziomy) -> list[Problem]:
    """Zbierz wszystkie niezależne problemy; nie konwertuj i nie zmieniaj danych."""
    k = _Kontrola()
    k.sprawdz(dane, SCHEMAT)
    k.sprawdz(poziomy, POZIOMY, 'poziomy')
    d, po = _obiekt(dane), _obiekt(poziomy)
    zrodla = {n: z for n, z in _wpisy(d.get('zrodla')).items() if isinstance(z, dict)}
    odbiorcy = {n: o for n, o in _wpisy(d.get('odbiorcy')).items() if isinstance(o, dict)}
    szyny = _obiekt(d.get('szyny'))
    prz = _obiekt(d.get('przyciszanie'))
    sluchacz = prz.get('sluchacz', 'telefon')
    klucz = _lista(prz.get('zrodla_klucza', ['mikrofon', 'zoom']))
    # Drugi lokalny głos nie staje się muzyką ani rozmówcą przez samą nazwę.
    dodatkowe = {n for n, z in zrodla.items() if n != 'mikrofon' and
                 z.get('glos') is True and z.get('odbiorca') is None}
    for n in sorted(dodatkowe):
        k.dodaj('zrodla.' + n, 'drugi mikrofon lokalny nie jest jeszcze obsługiwany; '
                'zobacz dokumentacja/stanowisko/projekt-drugi-mikrofon.md')
    for n in ('mikrofon', 'telefon', 'zoom'):
        if n not in _wpisy(d.get('zrodla')) and k.mozna('zrodla'):
            k.dodaj('zrodla.' + n, f'brak źródła {n!r}')
    zajete = {}
    for n, z in zrodla.items():
        path = 'zrodla.' + n
        for i, ch in enumerate(_lista(z.get('kanaly'))):
            p = f'{path}.kanaly[{i}]'
            if type(ch) is int and k.mozna(p):
                if ch in zajete:
                    k.dodaj(p, f'kanał {ch} przypisany dwa razy: {zajete[ch]} i {n}')
                zajete[ch] = n
        odb = z.get('odbiorca')
        if odb is not None and k.mozna(path + '.odbiorca'):
            if odb not in odbiorcy or odbiorcy[odb].get('wlasne_zrodlo') != n:
                k.dodaj(path + '.odbiorca', 'źródło musi wskazywać własnego odbiorcę, który wskazuje je z powrotem')
        if n in ('mikrofon', 'telefon', 'zoom') and z.get('glos', False) is not True:
            k.dodaj(path + '.glos', 'profil v1 wymaga głosu dla mikrofonu i rozmówców')
        galka = _obiekt(z.get('galka'))
        if galka.get('typ') == 'gain' and 'wejscie' not in galka:
            k.dodaj(path + '.galka.wejscie', 'gałka gain wymaga numeru wejścia')
    zajete_szyny = {}

    def rezerwuj(bus, path, rola):
        if type(bus) is not int or not k.mozna(path):
            return
        if bus in zajete_szyny:  # WAL_ROZLACZNOSC
            k.dodaj(path, f'szyna {bus} musi być osobna; zajmuje ją {zajete_szyny[bus]}, konflikt z {rola}')
        else:
            zajete_szyny[bus] = rola

    for n, o in odbiorcy.items():
        wlasne = o.get('wlasne_zrodlo')
        path = 'odbiorcy.' + n
        if k.mozna(path + '.wlasne_zrodlo'):
            if wlasne not in zrodla:
                k.dodaj(path + '.wlasne_zrodlo', 'nieznane własne źródło odbiorcy')
            elif zrodla[wlasne].get('odbiorca') != n:  # WAL_POWIAZANIE
                k.dodaj(path + '.wlasne_zrodlo', 'własne źródło musi wskazywać tego odbiorcę z powrotem')
        if n not in PROFIL_V1['rozmowcy']:
            k.dodaj(path, 'profil v1 obsługuje odbiorców telefon i zoom; inny układ wymaga osobnego odbioru')
        for i, b in enumerate(_lista(o.get('szyny'))):
            rezerwuj(b, f'{path}.szyny[{i}]', path)
    for nazwa in ('podsluch_telefonu', 'glosniki', 'klucz_przyciszania'):
        v = szyny.get(nazwa)
        for i, b in enumerate(_lista(v) if nazwa == 'glosniki' else [v]):
            rezerwuj(b, 'szyny.' + nazwa + (f'[{i}]' if nazwa == 'glosniki' else ''), nazwa)
    rozmowcy = [o.get('wlasne_zrodlo') for o in odbiorcy.values()]
    if k.mozna('przyciszanie.sluchacz') and sluchacz not in rozmowcy:
        k.dodaj('przyciszanie.sluchacz', 'przyciszany słuchacz musi być rozmówcą')
    if 'mikrofon' not in klucz or sluchacz in klucz:
        k.dodaj('przyciszanie.zrodla_klucza', 'klucz przyciszania: mikrofon tak, słuchacz nigdy')
    for i, n in enumerate(klucz):
        if isinstance(n, str) and (n not in zrodla or zrodla[n].get('glos') is not True):
            k.dodaj(f'przyciszanie.zrodla_klucza[{i}]', f'klucz przyciszania: {n!r} nie jest głosem')
    paski = set()
    for i, p in enumerate(_lista(d.get('paski'))):
        p = _obiekt(p)
        path = f'paski[{i}]'
        numer, zr = p.get('pasek'), p.get('zrodlo')
        if type(numer) is int:
            if numer in paski:  # WAL_PASKI
                k.dodaj(path + '.pasek', f'numer paska {numer} przypisany dwa razy')
            paski.add(numer)
        if not isinstance(zr, str) or not k.mozna(path + '.zrodlo'):
            continue
        if zr not in zrodla:
            k.dodaj(path + '.zrodlo', 'nieznane źródło na pasku')
            continue
        if zr in dodatkowe:
            continue  # nie mnożymy wtórnych błędów nieobsługiwanej roli
        if p.get('mute') == 'kaszel' and zr != 'mikrofon':
            k.dodaj(path + '.mute', 'przycisk kaszlu tylko na pasku mikrofonu')
        if p.get('mute') == 'talkback':
            odb = zrodla[zr].get('odbiorca')
            if (zr == 'mikrofon' or zrodla[zr].get('glos') is not True or
                not isinstance(odb, str) or odb not in odbiorcy or odbiorcy[odb].get('wlasne_zrodlo') != zr):
                k.dodaj(path + '.mute', 'talkback tylko na pasku rozmówcy z własnym odbiorcą')
        for przycisk in ('rec', 'select'):
            if p.get(przycisk) == 'antena_mikrofonu' and zr != 'mikrofon':
                k.dodaj(path + '.' + przycisk, 'przełączanie anteny tylko na pasku mikrofonu')
        if p.get('select') == 'cue' and zr not in rozmowcy:
            k.dodaj(path + '.select', 'CUE tylko na paskach rozmówców')
        if p.get('select') == 'pfl' and zrodla[zr].get('glos') is True:
            k.dodaj(path + '.select', 'SELECT jako PFL tylko na paskach muzyki')
    profil = _obiekt(d.get('profil'))
    usb = _lista(profil.get('usb_suche_dozwolone'))
    if any(type(x) is int and x in (1, 2, 3, 4) for x in usb):
        k.dodaj('profil.usb_suche_dozwolone', 'wyjścia 1/2 (Zoom) i 3/4 (emisja) nigdy nie niosą suchego głosu')
    maks = profil.get('wyjscia_usb', 18)
    for i, x in enumerate(usb):
        if type(x) is int and type(maks) is int and x > maks:
            k.dodaj(f'profil.usb_suche_dozwolone[{i}]', 'numer przekracza profil.wyjscia_usb')
    zach = _obiekt(d.get('zachowanie'))
    alarm = _obiekt(zach.get('alarm_ciszy'))
    for n in ('czas_s', 'powtorka_s'):
        if type(alarm.get(n)) in (float, int) and alarm[n] <= 0:
            k.dodaj('zachowanie.alarm_ciszy.' + n, 'czas alarmu ciszy i przerwa powtórki muszą być dodatnie')
    xt = _obiekt(d.get('xtouch'))
    zycie = xt.get('zycie_s', 1.0)
    if type(zycie) in (int, float) and 0 < zycie < 0.2:
        k.dodaj('xtouch.zycie_s', '0 albo od 0,2 do 30 sekund')
    for n in _wpisy(xt.get('klawisze')):
        if not n.isdecimal() or not 0 <= int(n) <= 127:
            k.dodaj('xtouch.klawisze.' + n, 'numer nuty MIDI od 0 do 127')
    emisja = _obiekt(d.get('emisja'))
    program = emisja.get('program', 'auto')
    if isinstance(program, str) and program.lower() not in ('sara', 'stationplaylist', 'auto', 'spl'):
        k.dodaj('emisja.program', 'w JSON: sara, stationplaylist albo auto; bez playoutu uruchom z --emisja brak')
    preferowany = emisja.get('preferowany', 'StationPlaylist')
    if isinstance(preferowany, str) and preferowany.lower() not in ('sara', 'stationplaylist', 'spl'):
        k.dodaj('emisja.preferowany', 'preferowany program: sara albo stationplaylist')
    komunikaty = _obiekt(d.get('komunikaty'))
    if k.mozna('komunikaty'):
        for n in KOMUNIKATY_V1:
            if n not in komunikaty:
                k.dodaj('komunikaty.' + n, f'brak komunikatu {n!r}')
    info = _obiekt(d.get('informacja_zwrotna'))
    for n in _wpisy(info.get('zdarzenia')):
        if n not in ('talkback_start', 'talkback_koniec') and n.split(':', 1)[0] not in komunikaty:
            k.dodaj('informacja_zwrotna.zdarzenia.' + n, 'zdarzenie dźwięku: nie ma takiego komunikatu')
    wysylki = _obiekt(po.get('wysylki'))
    if k.mozna('poziomy.wysylki'):
        for zr in zrodla:
            if zr in dodatkowe:
                continue
            for n, o in odbiorcy.items():
                if o.get('wlasne_zrodlo') == zr:
                    continue
                if n not in _obiekt(wysylki.get(zr)):
                    k.dodaj(f'poziomy.wysylki.{zr}.{n}', f'brak poziomu bazowego wysyłki {zr} -> {n}')
    return k.problemy  # WAL_ZBIERANIE


def czytaj_pliki(sciezka, poziomy):
    """Oba pliki niezależnie: nieczytelny plik ma kod 2, nie błąd topologii."""
    dane, problemy = [], []
    for nazwa, path in [('ustawienia', sciezka), ('poziomy', poziomy)]:
        try:
            dane.append(json.loads(Path(path).read_text(encoding='utf-8')))
        except (OSError, UnicodeError, ValueError, RecursionError) as e:
            dane.append(None)
            problemy.append(Problem(nazwa, f'nie można odczytać pliku {path}: {e}'))
    return dane[0], dane[1], problemy


def wczytaj_zgodnie(sciezka, poziomy, konwertuj):
    """Brama zgodności: nowy błąd nie blokuje dawnego poprawnego pliku.

    Jedynym arbitrem startu pozostaje dotychczasowa konwersja i sprawdz().
    Walidacja jest przed nią, a wyjątek techniczny dostaje opis pól. Nie
    wolno zastąpić tej bramy prostym `if bledy: raise`.
    """
    from .ustawienia import BladUstawien
    d, p, problemy = czytaj_pliki(sciezka, poziomy)
    if problemy:
        raise BladUstawien('; '.join(x.sciezka + ': ' + x.komunikat for x in problemy))
    problemy = waliduj(d, p)
    try:
        return konwertuj(d, p, Path(poziomy))
    except BladUstawien:
        raise  # stara reguła i jej sens pozostają w całości
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError) as e:
        bledy = [x for x in problemy if x.poziom == 'błąd']
        opis = '; '.join(x.sciezka + ': ' + x.komunikat for x in bledy)
        raise BladUstawien(opis or f'ustawienia: nie można przeliczyć danych ({e})') from e


def ostrzezenia_startu(u):
    """Wywoływane po otwarciu dziennika i przed tworzeniem urządzeń."""
    return [replace(p, poziom='ostrzeżenie') for p in waliduj(u.surowe, u.poziomy)]


def raport_zasobow(dane):
    """Inwentaryzacja deklaracji, nie potwierdzenie routingu miksera/sceny."""
    d = _obiekt(dane)
    kanaly = {str(i): [] for i in range(1, PROFIL_V1['wejscia'] + 1)}
    szyny = {str(i): [] for i in range(1, PROFIL_V1['szyny'] + 1)}
    for n, z in _wpisy(d.get('zrodla')).items():
        for ch in _lista(_obiekt(z).get('kanaly')):
            if type(ch) is int and str(ch) in kanaly:
                kanaly[str(ch)].append(n)
    for n, o in _wpisy(d.get('odbiorcy')).items():
        for b in _lista(_obiekt(o).get('szyny')):
            if type(b) is int and str(b) in szyny:
                szyny[str(b)].append('odbiorcy.' + n)
    for n in ('podsluch_telefonu', 'klucz_przyciszania', 'glosniki'):
        v = _obiekt(d.get('szyny')).get(n)
        for b in _lista(v) if n == 'glosniki' else [v]:
            if type(b) is int and str(b) in szyny:
                szyny[str(b)].append(n)
    profil = _obiekt(d.get('profil'))
    suche = _lista(profil.get('usb_suche_dozwolone'))
    usb = {str(i): {'rola': PROFIL_V1['usb_stale'].get(str(i), PROFIL_V1['usb_pozostale']),
                    'suchy_glos_dozwolony': i in suche} for i in range(1, PROFIL_V1['usb'] + 1)}
    prz = _obiekt(d.get('przyciszanie'))
    return {'profil': PROFIL_V1['nazwa'], 'kanaly': kanaly, 'szyny': szyny,
        'wolne_kanaly': [int(n) for n, v in kanaly.items() if not v],
        'wolne_szyny': [int(n) for n, v in szyny.items() if not v],
        'usb': usb, 'usb_uwaga': 'Role USB to projekt profilu BAZA, nie odczyt urządzenia. Zmiana szyn wymaga uzgodnienia sceny.',
        'sluchacz': prz.get('sluchacz', 'telefon'),
        'zrodla_klucza': prz.get('zrodla_klucza', ['mikrofon', 'zoom']),
        'paski': [dict(p, solo=None) for p in _lista(d.get('paski')) if isinstance(p, dict)],
        'master': PROFIL_V1['master'],
        'playout': _obiekt(d.get('emisja')).get('program', 'auto')}


def _linia(v):
    """Dane użytkownika nie mogą rozbić numerowanego raportu na nowe linie."""
    return ' '.join(str(v).split())


def tekst_zasobow(r):
    linie = ['Raport zasobów: ' + r['profil'] + '. Deklaracje, nie pomiar sprzętu.']
    for n, v in r['kanaly'].items():
        linie.append(f'Kanał {n}: ' + (', '.join(v) or 'wolny'))
    for n, v in r['szyny'].items():
        linie.append(f'Szyna {n}: ' + (', '.join(v) or 'wolna'))
    for nazwa, pole in [('Wolne kanały', 'wolne_kanaly'), ('Wolne szyny', 'wolne_szyny')]:
        linie.append(nazwa + ': ' + (', '.join(map(str, r[pole])) or 'brak'))
    linie.append(r['usb_uwaga'])
    for n, v in r['usb'].items():
        linie.append(f'USB {n}: {v["rola"]}; suchy głos: ' + ('dozwolony' if v['suchy_glos_dozwolony'] else 'zabroniony'))
    linie += [f'Przyciszany słuchacz: {r["sluchacz"]}',
              'Źródła klucza: ' + ', '.join(map(str, _lista(r['zrodla_klucza'])))]
    for p in r['paski']:
        linie.append(f'Pasek {p.get("pasek")}: {p.get("zrodlo") or "wolny"}; ' +
                     '; '.join(n.upper() + ': ' + str(p.get(n) or 'wolny') for n in ('rec', 'solo', 'mute', 'select')))
    linie += ['MASTER: ' + r['master'], 'Playout: ' + str(r['playout'])]
    return '\n'.join(_linia(l) for l in linie)


def sprawdz_pliki(sciezka, poziomy, *, jako_json=False):
    d, p, nieczytelne = czytaj_pliki(sciezka, poziomy)
    problemy = nieczytelne if nieczytelne else waliduj(d, p)
    bledy = sum(x.poziom == 'błąd' for x in problemy)
    ostrzezenia = len(problemy) - bledy
    kod = 2 if nieczytelne else (1 if bledy else 0)
    zasoby = None if nieczytelne else raport_zasobow(d)
    if jako_json:
        print(json.dumps({'kod': kod, 'bledy': bledy, 'ostrzezenia': ostrzezenia,
                          'problemy': [asdict(x) for x in problemy], 'zasoby': zasoby},
                         ensure_ascii=False, indent=2))
    else:
        print('Stanowisko poprawne' if not bledy else f'Błędy: {bledy}, ostrzeżenia: {ostrzezenia}')
        for i, x in enumerate(problemy, 1):
            print(_linia(f'{i}. {x.poziom}: {x.sciezka}: {x.komunikat}'))
        if zasoby is not None:
            print(tekst_zasobow(zasoby))
    return kod
