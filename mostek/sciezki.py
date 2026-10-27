"""Jedno miejsce wszystkich ścieżek OSC używanych przez mostek.

Każda ścieżka ma źródło i status. Status „do potwierdzenia na MR18”
pochodzi z etapu projektu przed pomiarami na mikserze; ścieżki używane
przez mostek zostały potem sprawdzone na MR18V2.

Skróty źródeł:
  FORUM  lista parametrów X AIR z forum Gig Performer
         (xair-osc-paramlist-gigperformer.txt); numery wierszy kopii tekstowej.
  AOSC   układ Air Access 18 dla AZ Accessible OSC (azaosc.xml, paczka
         do pobrania ze strony azslow.com); numery wierszy pliku.
  PROTO  dokument producenta „X AIR Mixer Series Remote Control Protocol”.

Nie dopisywać tu ścieżek spoza tych źródeł. Brakujące funkcje są na liście
LUKI na końcu pliku.
"""

from __future__ import annotations

from dataclasses import dataclass

DO_POTWIERDZENIA = "do potwierdzenia na MR18"


@dataclass(frozen=True)
class OpisSciezki:
    wzor: str
    typ: str            # "i" albo "f" albo "s" albo "-" (bez argumentu)
    znaczenie: str
    zrodla: str
    status: str = DO_POTWIERDZENIA


REJESTR: dict[str, OpisSciezki] = {
    o.wzor: o
    for o in (
        OpisSciezki("/xremote", "-", "subskrypcja zmian, ważna 10 s, maks. 8 klientów",
                    "PROTO 1.2 (wiersze 19-22); AOSC wiersz 4 (ping co 4000 ms)"),
        OpisSciezki("/xinfo", "-", "identyfikacja miksera i firmware",
                    "PROTO 1.0 (wiersze 15-16, 46-51); FORUM wiersz 293"),
        OpisSciezki("/status", "-", "stan serwera active/standby",
                    "PROTO 1.1 (wiersze 17-18, 52-59)"),
        OpisSciezki("/ch/{kk}/mix/lr", "i", "Main On kanału (suma, antena), 0=OFF 1=ON",
                    "FORUM wiersz 161; AOSC wiersz 361"),
        OpisSciezki("/ch/{kk}/mix/on", "i", "mute kanału, 0=wyciszony 1=czynny",
                    "FORUM wiersz 162; AOSC wiersz 359 (typ Mute = odwrócony przełącznik)"),
        OpisSciezki("/ch/{kk}/mix/fader", "f", "suwak kanału, zakres -oo..+10 dB",
                    "FORUM wiersz 160; AOSC wiersz 362"),
        OpisSciezki("/ch/{kk}/mix/{ss}/level", "f",
                    "poziom wysyłki kanału do szyny 01-06 lub FX 07-10, -oo..+10 dB",
                    "FORUM wiersz 157 (szyny); AOSC wiersze 285-294 (szyny 01-06, FX 07-10)"),
        OpisSciezki("/ch/{kk}/mix/{ss}/tap", "i", "punkt pobrania wysyłki IN..POST..GRP",
                    "FORUM wiersz 159; AOSC wiersze 55 i 298-310"),
        OpisSciezki("/ch/{kk}/grp/dca", "i", "przypisanie do DCA (maska bitowa)",
                    "FORUM wiersz 151; AOSC wiersz 390"),
        OpisSciezki("/ch/{kk}/grp/mute", "i", "przypisanie do mute group (maska bitowa)",
                    "FORUM wiersz 152; AOSC wiersz 389"),
        OpisSciezki("/ch/{kk}/preamp/rtntrim", "f", "USB Trim, -18..+18 dB",
                    "FORUM wiersz 168; AOSC wiersze 18 i 383"),
        OpisSciezki("/ch/{kk}/preamp/rtnsw", "i", "źródło kanału: analog albo USB",
                    "FORUM wiersz 167; AOSC wiersz 381"),
        OpisSciezki("/headamp/{kk}/gain", "f",
                    "wzmocnienie przedwzmacniacza; AOSC -12..+60 dB, FORUM -12..+20 dB (rozbieżne)",
                    "FORUM wiersz 206; AOSC wiersze 14 i 323-338"),
        OpisSciezki("/config/chlink/{para}", "i", "link pary kanałów",
                    "FORUM wiersz 174; AOSC wiersz 391"),
        OpisSciezki("/config/buslink/{para}", "i", "link pary szyn",
                    "FORUM wiersz 173; AOSC wiersz 441"),
        OpisSciezki("/bus/{n}/mix/on", "i", "mute szyny, 0=wyciszona 1=czynna",
                    "FORUM wiersz 103; AOSC wiersz 417"),
        OpisSciezki("/bus/{n}/mix/lr", "i", "przypisanie szyny do Main LR",
                    "FORUM wiersz 102; AOSC wiersz 419"),
        OpisSciezki("/-stat/solosw/{kk}", "i",
                    "przełącznik solo (PFL); kanały 01-16, szyny 40-45, Main LR 50 "
                    "(Companion X Air, defSolo.js: Master LR offset 49; MR18 fw 1.19 odpowiada)",
                    "FORUM wiersz 53; AOSC wiersze 360, 418, 1681-1686"),
        OpisSciezki("/config/solo/source", "i",
                    "źródło monitora: 0 OFF, 1 LR, 2 LRPFL, 3 LRAFL, ...",
                    "FORUM wiersz 188; AOSC wiersze 66 i 1759"),
        OpisSciezki("/config/solo/chmode", "i", "tryb solo kanałów 0 PFL 1 AFL",
                    "FORUM wiersz 181; AOSC wiersz 1761"),
        OpisSciezki("/config/solo/dimpfl", "i", "przyciszenie programu przy PFL",
                    "FORUM wiersz 184; AOSC wiersz 1765"),
        OpisSciezki("/config/solo/dimatt", "f", "poziom przyciszenia -40..0 dB",
                    "FORUM wiersz 183; AOSC wiersze 25 i 1764"),
        OpisSciezki("/config/solo/level", "f", "głośność wyjścia PHONES",
                    "FORUM wiersz 185; AOSC wiersz 1758"),
        OpisSciezki("/routing/usb/{kk}/src", "i",
                    "źródło wysyłki USB do komputera; 0-15 Ch01-16, 36 Main L, 37 Main R",
                    "FORUM wiersz 254; AOSC wiersze 60 i 1731"),
        OpisSciezki("/-snap/index", "i", "numer ostatnio wczytanej sceny (tylko nasłuch)",
                    "FORUM wiersz 37; PROTO wiersz 161 podaje /snap/ bez minusa (rozbieżne)"),
        # Przyciszanie słuchacza (plan v22, rozdz. 8, „Mechanizmy z konsolet D&R”, pkt 5).
        # Mostek tylko je odczytuje; zapis odrzuca zapora.
        OpisSciezki("/ch/{kk}/dyn/keysrc", "i",
                    "źródło klucza kompresora kanału: 0 SELF, 1-16 Ch01-16, 17-22 Bus1-6",
                    "FORUM wiersz 123; AOSC wiersze 17 i 223 (Self, In 01-16, Bus 1-6, zgodne)"),
        OpisSciezki("/ch/{kk}/dyn/on", "i", "kompresor kanału włączony, 0=OFF 1=ON",
                    "FORUM wiersz 128"),
        OpisSciezki("/ch/{kk}/insert/sel", "i",
                    "insert kanału: 0 OFF, 1 Fx1A, 2 Fx1B, 3 Fx2A, 4 Fx2B, 5 Fx3A, 6 Fx3B, 7 Fx4A, 8 Fx4B",
                    "POMIAR MR18V2 fw 1.19 (pomiar 18.10.2026): /insert/fxslot bez odpowiedzi; "
                    "/insert/sel w xair-api-python (Insert.sel) i dlyz/mixer-assist (MR18 fw 1.25). "
                    "FORUM wiersz 153 podaje fxslot, co na MR18 nie działa"),
        OpisSciezki("/ch/{kk}/insert/on", "i", "insert kanału włączony",
                    "FORUM wiersz 155; AOSC wiersz 367"),
        OpisSciezki("/bus/{n}/mix/fader", "f", "master szyny, zakres -oo..+10 dB",
                    "FORUM wiersz 101"),
        # Powroty efektów i AUX do szyn (L05, plan v22): mostek je czyta, bo
        # wysyłka powrotu do Bus 5 też kluczuje przyciszanie słuchacza. Zapis
        # wyłącznie zamykający (zapora).
        OpisSciezki("/rtn/{fx}/mix/{ss}/level", "f",
                    "poziom wysyłki powrotu efektu 1-4 do szyny 01-06, -oo..+10 dB",
                    "FORUM wiersze 264-267 (Fx Return [1..4] mixbus sends level)"),
        OpisSciezki("/rtn/aux/mix/{ss}/level", "f",
                    "poziom wysyłki powrotu AUX (wejście AUX IN) do szyny 01-06, -oo..+10 dB",
                    "FORUM wiersze 283-286 (Aux Return mixbus sends level); AOSC wiersze 413 i 432"),
        OpisSciezki("/meters", "s",
                    "subskrypcja mierników, odpowiedź: blob pod adresem identyfikatora; "
                    "/meters/5 = wszystkie wyjścia (6 aux, LR, 16 P16, 18 USB, słuchawki)",
                    "PROTO 1.5 (wiersze 31-37, 65-67, 77-84, 117-121); AOSC wiersz 1599 "
                    "(Main LR: /meters/5, bajty 16 i 18)"),
    )
}


def kk(n: int) -> str:
    return f"{n:02d}"


# --- Generatory adresów -----------------------------------------------------

def lr(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/mix/lr"


def mute_kanalu(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/mix/on"


def fader(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/mix/fader"


def wysylka(kanal: int, szyna: int) -> str:
    """Poziom wysyłki do szyny 1-6 albo FX 7-10."""
    return f"/ch/{kk(kanal)}/mix/{kk(szyna)}/level"


def tap(kanal: int, szyna: int) -> str:
    return f"/ch/{kk(kanal)}/mix/{kk(szyna)}/tap"


def dca(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/grp/dca"


def grupa_mute(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/grp/mute"


def rtntrim(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/preamp/rtntrim"


def gain(wejscie: int) -> str:
    return f"/headamp/{kk(wejscie)}/gain"


def chlink(nieparzysty: int) -> str:
    return f"/config/chlink/{nieparzysty}-{nieparzysty + 1}"


def buslink(nieparzysta: int) -> str:
    return f"/config/buslink/{nieparzysta}-{nieparzysta + 1}"


# Parametry kanału, które MR18 przy linku pary ustawia na obu kanałach
# (Link Pref „Fader, Mute, Sends” w BAZIE włączone). Pan w parze jest
# lustrzany, nie równy, więc go tu nie ma.
_PARAMETRY_PARY = (("mix", "fader"), ("mix", "on"), ("mix", "lr"))


def _drugi(n: int) -> int:
    return n - 1 if n % 2 == 0 else n + 1


def partnerzy_pary(adres: str, w_parze) -> list[str]:
    """Adresy, które mikser ustawia sam po zapisie adresu, bo kanał albo
    szyna należy do linkowanej pary. w_parze(adres_linku) mówi, czy link
    (/config/chlink/N-M, /config/buslink/N-M) jest włączony.

    Zmierzone na MR18 (dziennik Michała 23/24.10.2026): zapis
    /ch/03/mix/01/level zmienia też /ch/04/mix/01/level, zapis
    /ch/09/mix/03/level zmienia /ch/09/mix/04/level (link szyn 3/4; pomiar
    18.10.2026: para szyn ma jeden poziom wysyłki)."""
    cz = adres.strip("/").split("/")
    if len(cz) == 3 and cz[0] == "-stat" and cz[1] == "solosw" and cz[2].isdigit():
        k = int(cz[2])
        if 1 <= k <= 16 and w_parze(chlink(min(k, _drugi(k)))):
            return [solo(_drugi(k))]
        return []
    if len(cz) < 4 or cz[0] != "ch" or not cz[1].isdigit():
        return []
    k = int(cz[1])
    if not 1 <= k <= 16:
        return []
    reszta = tuple(cz[2:])
    szyna = None
    if len(reszta) == 3 and reszta[0] == "mix" and reszta[1].isdigit() and reszta[2] in ("level", "tap"):
        szyna = int(reszta[1])
    elif reszta not in _PARAMETRY_PARY:
        return []
    kanaly = [k] + ([_drugi(k)] if w_parze(chlink(min(k, _drugi(k)))) else [])
    szyny = [szyna]
    if szyna is not None and 1 <= szyna <= 6 and w_parze(buslink(min(szyna, _drugi(szyna)))):
        szyny.append(_drugi(szyna))
    wynik = []
    for kan in kanaly:
        for b in szyny:
            a = (f"/ch/{kk(kan)}/" + "/".join(reszta) if b is None
                 else f"/ch/{kk(kan)}/mix/{kk(b)}/{reszta[2]}")
            if a != adres:
                wynik.append(a)
    return wynik


def mute_szyny(szyna: int) -> str:
    return f"/bus/{szyna}/mix/on"


def szyna_lr(szyna: int) -> str:
    return f"/bus/{szyna}/mix/lr"


def solo(kanal: int) -> str:
    return f"/-stat/solosw/{kk(kanal)}"


SOLO_MAIN_LR = "/-stat/solosw/50"


def usb_zrodlo(wyjscie: int) -> str:
    return f"/routing/usb/{kk(wyjscie)}/src"


def keysrc(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/dyn/keysrc"


def dyn_on(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/dyn/on"


def insert_fxslot(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/insert/sel"


def insert_on(kanal: int) -> str:
    return f"/ch/{kk(kanal)}/insert/on"


def fader_szyny(szyna: int) -> str:
    return f"/bus/{szyna}/mix/fader"


# Powroty: AUX IN i cztery powroty efektów (FORUM wiersze 264-286).
POWROTY = ("aux", 1, 2, 3, 4)


def wysylka_powrotu(powrot, szyna: int) -> str:
    """Poziom wysyłki powrotu ("aux" albo 1-4) do szyny 1-6."""
    return f"/rtn/{powrot}/mix/{kk(szyna)}/level"


def wejscia_szyny(szyna: int) -> list[str]:
    """Wszystkie wysyłki do szyny: kanały 1-16 i powroty (L05, plan v22)."""
    return [wysylka(k, szyna) for k in range(1, 17)] + [wysylka_powrotu(p, szyna) for p in POWROTY]


def kanal_wysylki(adres: str):
    """Numer kanału z /ch/NN/mix/BB/level albo None dla powrotu."""
    czesci = adres.strip("/").split("/")
    if len(czesci) == 5 and czesci[0] == "ch":
        return int(czesci[1])
    return None


MONITOR_ZRODLO = "/config/solo/source"
MONITOR_TRYB_KANALOW = "/config/solo/chmode"
MONITOR_DIMPFL = "/config/solo/dimpfl"
MONITOR_DIMATT = "/config/solo/dimatt"
MONITOR_POZIOM = "/config/solo/level"
SCENA_INDEKS = "/-snap/index"
XREMOTE = "/xremote"
XINFO = "/xinfo"

# Wartości wyliczeń wg FORUM wiersz 188 i AOSC wiersz 66 (zgodne).
ZRODLO_OFF = 0
ZRODLO_LR = 1
ZRODLO_LRPFL = 2
ZRODLO_NAZWY = {0: "wyłączone", 1: "program", 2: "program plus odsłuch kontrolny",
                3: "program plus odsłuch za suwakiem"}

# Punkt pobrania wysyłki /ch/NN/mix/BB/tap, typ „i”. FORUM wiersz 159:
# zakres 0-5 „IN, PREEQ, POSTEQ, PRE, POST, GRP”. AOSC wiersz 55 (typ BusTap):
# „Input;Pre EQ;Post EQ;Pre Fader;Post Fader;Subgroup”. Oba źródła są pośrednie
# i zgodne: 3 = przed suwakiem, 4 = za suwakiem. Status: luka do potwierdzenia
# na MR18 (lista LUKI niżej). Mostek zapisuje wyłącznie te dwie wartości.
TAP_PRE = 3
TAP_POST = 4
TAP_NAZWY = {0: "wejście", 1: "przed korekcją", 2: "za korekcją", 3: "przed suwakiem",
             4: "za suwakiem", 5: "podgrupa"}

# FX: wysyłki 07-10 wg AOSC wiersze 291-294.
SZYNY_FX = (7, 8, 9, 10)
# Źródła USB, wartości 8 i 9 to Ch09 i Ch10 (FORUM 254, AOSC 60).
USB_ZRODLO_KANAL = {k: k - 1 for k in range(1, 17)}
# Źródła USB szyn: FORUM wiersz 254 „Ch01-16, AuxL-R, Fx1L-Fx4R, Bus1-6, Send1-4, L, R”
# (0-37): Ch 0-15, Aux 16-17, Fx 18-25, Bus1-6 26-31, Send 32-35, L 36, R 37.
# Zgodne z symulatorem (Bus 3/4 = 28/29). Bus 5 = 30.
USB_ZRODLO_SZYNA = {b: 25 + b for b in range(1, 7)}
# Źródło klucza kompresora: FORUM wiersz 123 i AOSC wiersz 17, „SELF, Ch01-Ch16,
# Bus1-Bus6” (0-22). Bus 5 = 21.
KEYSRC_SZYNA = {b: 16 + b for b in range(1, 7)}

# Mierniki (PROTO 1.5): /meters z identyfikatorem; MR18 odsyła blob pod adres
# identyfikatora: liczba wartości (int32), potem wartości int16 ze znakiem,
# 1/256 dB. /meters/5 „ALL OUTPUTS”: 6 aux, lr, 16 p16, 18 usb, headphones =
# 44 wartości. Main LR to wartości 6 i 7 (AOSC wiersz 1599: bajty 16 i 18,
# a aux 1 to bajt 4, czyli pierwsza wartość po liczbie). Kolejność bajtów
# w bloku nie jest opisana w PROTO; mostek przyjmuje little-endian jak w X32
# (opcja w ustawieniach). Luka do potwierdzenia na MR18.
METERS = "/meters"

# Ścieżki, których zmiana z innego klienta unieważnia profil i wymaga
# pełnej synchronizacji (plan, rozdział 8, kontrakt pkt 8).
PREFIKSY_PROFILU = ("/config/chlink/", "/config/buslink/", "/routing/", "/-snap/", "/snap/")


def zmienia_profil(adres: str) -> bool:
    """Czy zmiana adresu z innego klienta unieważnia profil: linki, routing,
    scena oraz przypisanie szyny do Main LR (/bus/N/mix/lr). Szyna na Main LR
    wyprowadza na antenę rozmowę albo klucz przyciszania (plan v22)."""
    if adres.startswith(PREFIKSY_PROFILU):
        return True
    czesci = adres.strip("/").split("/")
    return len(czesci) == 4 and czesci[0] == "bus" and czesci[2] == "mix" and czesci[3] == "lr"


def typ_sciezki(adres: str) -> str:
    """Typ argumentu OSC dla adresu z rejestru: 'i', 'f', 's' albo '-'.

    Liczy się pełna ścieżka z zakresem kanałów i szyn (opis_sciezki), nie
    sam sufiks: /obce/mix/lr albo /ch/17/mix/lr są spoza rejestru (L06)."""
    opis = opis_sciezki(adres)
    if opis is None:
        raise KeyError(f"ścieżka spoza rejestru: {adres}")
    return opis.typ


def _dwucyfrowe(od: int, do: int) -> frozenset:
    return frozenset(kk(n) for n in range(od, do + 1))


# Zakresy pól wzorów rejestru. Domyślne: kanał 01-16, wysyłka 01-06 (szyny)
# i 07-10 (FX), szyna 1-6, powrót efektu 1-4. Wyjątki per wzór niżej.
_ZAKRES_DOMYSLNY = {
    "kk": _dwucyfrowe(1, 16),
    "ss": _dwucyfrowe(1, 10),
    "n": frozenset(str(n) for n in range(1, 7)),
    "fx": frozenset(str(n) for n in range(1, 5)),
}
_ZAKRES_WZORU = {
    "/-stat/solosw/{kk}": {"kk": _dwucyfrowe(1, 16) | _dwucyfrowe(40, 45) | {"50"}},
    "/routing/usb/{kk}/src": {"kk": _dwucyfrowe(1, 18)},
    "/config/chlink/{para}": {"para": frozenset(f"{p}-{p + 1}" for p in range(1, 16, 2))},
    "/config/buslink/{para}": {"para": frozenset(f"{p}-{p + 1}" for p in (1, 3, 5))},
    "/rtn/{fx}/mix/{ss}/level": {"ss": _dwucyfrowe(1, 6)},
    "/rtn/aux/mix/{ss}/level": {"ss": _dwucyfrowe(1, 6)},
}


def opis_sciezki(adres: str) -> OpisSciezki | None:
    """Wpis rejestru pasujący do PEŁNEJ ścieżki (każdy człon i zakres pól) albo None."""
    czesci = adres.split("/")
    for wzor, opis in REJESTR.items():
        wz = wzor.split("/")
        if len(wz) != len(czesci):
            continue
        for w, a in zip(wz, czesci):
            if w.startswith("{") and w.endswith("}"):
                pole = w[1:-1]
                dozwolone = _ZAKRES_WZORU.get(wzor, {}).get(pole, _ZAKRES_DOMYSLNY.get(pole))
                if dozwolone is None or a not in dozwolone:
                    break
            elif w != a:
                break
        else:
            return opis
    return None


def w_rejestrze(adres: str) -> bool:
    return opis_sciezki(adres) is not None


# --- Luki: funkcje bez ścieżki w źródłach ----------------------------------
LUKI = (
    "Stan połączenia telefonicznego BlueDrivera nie jest dostępny przez OSC "
    "miksera. Mostek mówi „tor telefonu poza anteną”, nigdy „telefon rozłączony”.",
    "Akcja /-action/clearsolo (FORUM wiersz 2, AOSC wiersz 1588) nie ma w źródłach "
    "opisu argumentu ani odpowiedzi. Mostek jej nie używa: zeruje każdy "
    "/-stat/solosw osobno i potwierdza odczytem.",
    "Wczytywanie scen: FORUM podaje /-snap/load, PROTO podaje /snap/load. "
    "Rozbieżne źródła, więc mostek scen nie wczytuje. Sceny wczytuje się w AOSC "
    "poza anteną; mostek tylko nasłuchuje /-snap/ i wtedy robi pełny odczyt.",
    "Zakres /headamp/NN/gain: AOSC -12..+60 dB, FORUM -12..+20 dB. Mostek "
    "przyjmuje AOSC (mniejszy krok przy błędzie). Do pomiaru w etapie 1.",
    "Krzywa dB suwaka i wysyłki pochodzi z biblioteki xair-api-python, nie od "
    "producenta. Do porównania z wartościami w M-AIR Edit.",
    "Wyliczenie /ch/NN/config/insrc jest rozbieżne (FORUM 0-15, AOSC 0-18), "
    "dlatego mostek nie sprawdza duplikatów fizycznego mikrofonu przez OSC.",
    "Zachowanie zapisu do parzystej szyny połączonej pary (Bus 4 przy linku 3/4) "
    "nie jest opisane. Mostek zapisuje obie szyny pary i obie potwierdza.",
    "Czy MR18 odsyła własny zapis klienta przez /xremote, nie wiadomo. Mostek "
    "potwierdza wyłącznie osobnym odczytem na drugim gnieździe.",
    "Mierniki /meters/5: liczba wartości (44), indeks Main LR (6 i 7) i kolejność "
    "bajtów w bloku (mostek przyjmuje little-endian jak w X32) wynikają z PROTO i AOSC, "
    "nie z pomiaru. Czy wartość to dBFS, też trzeba sprawdzić. Do potwierdzenia "
    "narzędziem badanie_mr18.py (sekcja mierniki) na MR18.",
    "Klucz kompresora kanału 10 kluczowany szyną Bus 5: nie wiadomo, czy bierze "
    "sygnał szyny przed masterem, czy za nim. Dlatego master Bus 5 zostaje na "
    "poziomie nominalnym, a mostek go nie zmienia. Głębokość i czasy przyciszania "
    "ustawia się na słuch w etapie 4.",
    "Insert efektu stereo na połączonej parze kanałów (Zoom 7/8, Combinator FX2): "
    "nie wiadomo, czy /ch/07/insert/sel obejmuje oba kanały. Mostek sprawdza "
    "w profilu tylko inserty mikrofonu i słuchacza (FX1 A i B).",
    "Punkt pobrania /ch/NN/mix/BB/tap: wartości 3 (przed suwakiem) i 4 (za "
    "suwakiem) podają zgodnie FORUM (wiersz 159) i AOSC (wiersz 55), oba źródła "
    "pośrednie. Do potwierdzenia na MR18: odczyt narzędziem badanie_mr18.py i "
    "porównanie z M-AIR Edit. Nie wiadomo też, czy zmiana punktu pobrania na żywo "
    "daje trzask (mostek zmienia go wyłącznie przy zamkniętej wysyłce) ani czy "
    "link szyn 3/4 sprzęga punkt pobrania obu szyn pary.",
)
