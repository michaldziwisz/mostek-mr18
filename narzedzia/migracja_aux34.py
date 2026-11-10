"""Minimalna migracja sceny do opt-in AUX34 mono, bez kanonizacji innych pól."""
import re
import shlex


def przygotuj(tekst):
    linie = tekst.splitlines(keepends=True)
    wezly = {}
    for i, linia in enumerate(linie):
        cz = shlex.split(linia)
        if cz and cz[0].startswith('/'):
            wezly.setdefault(cz[0], []).append((i, cz[1:]))
    # Sprawdź WSZYSTKIE adresy przed podmianami, nie tylko zmieniane pola.
    # Identyczne tokeny mogą mieć inne odstępy; ich bajty pozostają nietknięte.
    for a, wystapienia in wezly.items():
        if any(args != wystapienia[0][1] for _, args in wystapienia[1:]):
            raise ValueError(f'Sprzeczne duplikaty adresu: {a}')
    wymagane = ['/config/solo', '/fxsend/3/mix', '/routing/aux/03', '/routing/aux/04']
    wymagane += [f'/ch/{k:02d}/mix/09' for k in range(1, 17)]
    wymagane += [f'/rtn/{p}/mix/09' for p in ('aux', 1, 2, 3, 4)]
    if any(a not in wezly for a in wymagane):
        raise ValueError('Brak wymaganych węzłów odsłuchu')
    for n in (5, 6):
        if not wezly.get(f'/routing/aux/{n:02d}') or any(args != ['Bus6', 'POST'] for _, args in wezly[f'/routing/aux/{n:02d}']):
            raise ValueError('Wymagane oba głośniki Bus6 POST, migracja ich nie zmienia')
    # Nie naprawiamy rezerwy ani powrotów. Muszą już być zamknięte.
    for a in wymagane:
        if a.startswith('/rtn/') or any(a.startswith(f'/ch/{k:02d}/') for k in range(11, 17)):
            if any(cz[0] != '-oo' for _, cz in wezly[a]):
                raise ValueError(f'Tor zajęty: {a}')
    zmiany = []

    def zmien(a, pola):
        for nr, args in wezly[a]:
            # Lokalna podmiana tokenów zachowuje odstępy, CRLF i pozostałe pola.
            spans = list(re.finditer(r'"[^"\\]*(?:\\.[^"\\]*)*"|[^\s]+', linie[nr]))
            nowa = linie[nr]
            for indeks, wartosc in sorted(pola.items(), reverse=True):
                if indeks >= len(args):
                    raise ValueError(f'Za mało pól: {a}')
                m = spans[indeks + 1]
                nowa = nowa[:m.start()] + wartosc + nowa[m.end():]
            if nowa != linie[nr]:
                zmiany.append({'wiersz': nr + 1, 'przed': linie[nr].rstrip(), 'po': nowa.rstrip()})
                linie[nr] = nowa

    zmien('/config/solo', {1: 'LR'})  # Stan bazowy bez CUE: normalne stereo PHONES.
    zmien('/fxsend/3/mix', {0: 'ON', 1: '-30.0'})  # Poziom zaakceptowany w bramce mono.
    for n in (3, 4):
        zmien(f'/routing/aux/{n:02d}', {0: 'Send3', 1: 'POST'})
    for k in range(1, 11):
        # BAZA to stan bez runtime PFL; przy Main Off wysyłka zamknięta.
        miks = wezly.get(f'/ch/{k:02d}/mix')
        if not miks:
            raise ValueError(f'Brak miksu kanału {k}')
        level = '-oo'  # AUX otwiera dopiero kontroler po potwierdzonym CUE.
        zmien(f'/ch/{k:02d}/mix/09', {0: level, 1: 'OFF', 2: 'POST'})
    return ''.join(linie), zmiany
