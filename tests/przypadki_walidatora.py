"""Niezależne zniekształcenia kopii stanowiska, także dawniej akceptowane."""
from copy import deepcopy

USUN = object()
# Cel, ścieżka, nowa wartość. Każdy przypadek musi dać błąd tej ścieżki.
PRZYPADKI = [
    ('stanowisko', ('zrodla',), []),
    ('stanowisko', ('zrodla', 'mikrofon'), None),
    ('stanowisko', ('zrodla', 'mikrofon', 'nazwa'), USUN),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly'), []),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly'), '9'),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly', 0), 0),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly', 0), 17),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly', 0), True),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly', 0), '9'),
    ('stanowisko', ('zrodla', 'mikrofon', 'kanaly', 0), {}),
    ('stanowisko', ('zrodla', 'muzyka3', 'kanaly', 0), 9),
    ('stanowisko', ('zrodla', 'telefon', 'odbiorca'), 'zoom'),
    ('stanowisko', ('zrodla', 'telefon', 'glos'), 'tak'),
    ('stanowisko', ('zrodla', 'mikrofon', 'suwak_maks_db'), 11),
    ('stanowisko', ('odbiorcy', 'telefon', 'szyny'), []),
    ('stanowisko', ('odbiorcy', 'telefon', 'szyny', 0), 7),
    ('stanowisko', ('odbiorcy', 'zoom', 'szyny', 0), 1),
    ('stanowisko', ('odbiorcy', 'telefon', 'wlasne_zrodlo'), 'brak'),
    ('stanowisko', ('odbiorcy', 'telefon', 'wlasne_zrodlo'), 'zoom'),
    ('stanowisko', ('szyny', 'klucz_przyciszania'), 6),
    ('stanowisko', ('szyny', 'podsluch_telefonu'), 1),
    ('stanowisko', ('szyny', 'glosniki'), []),
    ('stanowisko', ('paski', 1, 'pasek'), 1),
    ('stanowisko', ('paski', 0, 'pasek'), 9),
    ('stanowisko', ('paski', 0, 'pasek'), None),
    ('stanowisko', ('paski', 0, 'zrodlo'), 'nie_ma'),
    ('stanowisko', ('paski', 1, 'mute'), 'kaszel'),
    ('stanowisko', ('paski', 0, 'rec'), 'nie_ma'),
    ('stanowisko', ('paski', 3, 'select'), 'cue'),
    ('stanowisko', ('przyciszanie', 'zrodla_klucza'), ['telefon']),
    ('stanowisko', ('przyciszanie', 'sluchacz'), 'muzyka1'),
    ('stanowisko', ('komunikaty', 'tryb_mowa'), USUN),
    ('stanowisko', ('komunikaty', 'mikrofon_stan'), USUN),
    ('stanowisko', ('komunikaty', 'mikrofon_stan'), 8),
    ('stanowisko', ('informacja_zwrotna', 'zdarzenia', 'obce'), 'alarm'),
    ('stanowisko', ('informacja_zwrotna', 'zdarzenia', 'talkback_start'), 0),
    ('stanowisko', ('informacja_zwrotna', 'dzwiek_ostrzezenia'), ''),
    ('stanowisko', ('xtouch', 'ponowienie_portu_s'), 0),
    ('stanowisko', ('xtouch', 'zycie_s'), 31),
    ('stanowisko', ('xtouch', 'zycie_proby'), 0),
    ('stanowisko', ('emisja', 'mikrofon_wstrzymuje_automat'), 1),
    ('stanowisko', ('emisja', 'program'), 'x32'),
    ('stanowisko', ('profil', 'usb_suche_dozwolone'), [1]),
    ('stanowisko', ('profil', 'wyjscia_usb'), 19),
    ('stanowisko', ('zachowanie', 'alarm_ciszy', 'prog_dbfs'), 1),
    ('stanowisko', ('zachowanie', 'alarm_ciszy', 'czas_s'), 0),
    ('stanowisko', ('zachowanie', 'alarm_ciszy', 'powtorka_s'), -1),
    ('stanowisko', ('zachowanie', 'przyciszenie_muzyki_cue_db'), -61),
    ('stanowisko', ('zachowanie', 'prog_suwaka_na_antenie_db'), 11),
    ('stanowisko', ('zachowanie', 'przypomnienie_mikrofonu_min'), -1),
    ('stanowisko', ('mikser', 'port'), 'nie'),
    ('stanowisko', ('wersja_schematu',), 2),
    ('poziomy', ('wysylki', 'mikrofon', 'telefon'), USUN),
    ('poziomy', ('wysylki', 'mikrofon', 'telefon'), 11),
    ('poziomy', ('wysylki', 'mikrofon', 'telefon'), 'ciszej'),
    ('poziomy', ('wysylki',), []),
]


def sciezka(cel, klucze):
    tekst = 'poziomy' if cel == 'poziomy' else ''
    for k in klucze:
        tekst += f'[{k}]' if isinstance(k, int) else ('.' if tekst else '') + k
    return tekst


def zmien(dane, poziomy, przypadek):
    d, p = deepcopy(dane), deepcopy(poziomy)
    cel, klucze, wartosc = przypadek
    miejsce = p if cel == 'poziomy' else d
    for k in klucze[:-1]:
        miejsce = miejsce[k]
    if wartosc is USUN:
        del miejsce[klucze[-1]]
    else:
        miejsce[klucze[-1]] = deepcopy(wartosc)
    return d, p
