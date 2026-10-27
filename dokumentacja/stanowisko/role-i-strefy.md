# Role i strefy stanowiska

## Zakres profilu v1

Profil zgodności opisuje istniejący mostek, nie nowy mikser ani nową politykę anteny. Jego źródło wykonawcze to `mostek/walidator.py`, stała `PROFIL_V1`; czytelna kopia jest w `profil-mr18-xtouch-v1.json`. Walidator i raport korzystają z kodu, więc paczka EXE nie potrzebuje dodatkowego pliku profilu. Brak `wersja_schematu` oznacza wersję 1. Jawna wersja 1 jest dopuszczalna, inna jest błędem sprawdzenia. Nie trzeba dopisywać wersji do obecnego pliku.

Obsługiwany układ to MR18 z protokołem X AIR, 16 konfigurowanych wejść kanałowych, sześć szyn, 18 wyjść USB, jeden X-TOUCH w MC z ośmioma paskami i masterem. AUX 17/18 nie jest dodatkowym konfigurowalnym źródłem tego profilu. Zgodności XR18, X32/M32 ani innych kontrolerów nie potwierdza samo użycie OSC lub MIDI.

## Źródła i odbiorcy

1. Lokalny mikrofon ma identyfikator `mikrofon`, `glos: true` i nie ma `odbiorca`. Lista `kanaly` może obejmować kilka kanałów jednego źródła logicznego. To nie są niezależni prowadzący: mają wspólne ON, kaszel i udział w rozmowie.
2. Rozmówca ma `glos: true`, wskazuje `odbiorca`, a odbiorca wskazuje go przez `wlasne_zrodlo`. Odbiorca posiada własną, niepustą listę szyn N-1. Jego własny sygnał jest wykluczony z powrotu. W profilu zgodności rozmówcami są `telefon` i `zoom`.
3. Muzyka ma `glos: false` i nie potrzebuje odbiorcy. Nazwy muzyki oraz kanały są parametrami. SELECT muzyki oznacza PFL, nie prywatną rozmowę. REC „suwakiem” jest informacją o wejściu na antenę, nie startem odtwarzacza.
4. Drugi niezależny lokalny głos jest wykrywany po `glos: true` i braku odbiorcy, nie po napisie na pasku. Jest projektem P02, nie obsługiwaną rolą. Zobacz `projekt-drugi-mikrofon.md`.

Każda para źródło/odbiorca wymaga poziomu w `poziomy.wysylki`, z wyjątkiem własnego powrotu odbiorcy. Jednostką jest dB, sprawdzany zakres od minus 90 do plus 10. Te wartości nie zastępują pomiaru słuchowego.

## Strefy i ich granice

Antena to Main LR. Jest jeden program. Szyny N-1 nie są drugim programem SUB i nie wolno otworzyć ich na Main LR.

CUE oznacza rozmowę poza anteną: głosy przed suwakami, muzyka za suwakami z przyciszeniem. Mikrofon jest wspólnym uczestnikiem. Podniesienie suwaka rozmówcy kończy tylko jego CUE, po zamknięciu prywatnych torów. Nie jest to dowolnie programowalna polityka każdego kanału.

PFL jest odsłuchem kontrolnym prezentera. Nie oznacza rozmowy ani startu playoutu. Opcja śledzenia CUE i opcja muzyki w słuchawkach podczas CUE nie zmieniają go w split stereo na wzór każdej konsolety D&R.

Głośniki tworzą jedną wspólną strefę. `szyny.glosniki` wskazuje jej szyny, a opcja automatycznego powrotu nie pozwala ominąć ochrony przy otwartym lub nieznanym torze mikrofonu. Osobna reżyserka wymaga modelu stref, nie tylko dodatkowej nazwy.

Słuchawki korzystają z monitora MR18. MASTER X-TOUCH reguluje monitor, nie antenę. Specjalny podsłuch telefonu wykorzystuje pierwszy kanał źródła `telefon` i osobną szynę; nie jest uniwersalnym podsłuchem dowolnego rozmówcy.

Klucz przyciszania jest niesłyszalnym sygnałem sterującym. `przyciszanie.sluchacz` wybiera jednego rozmówcę, `zrodla_klucza` wybiera głosy, a `szyny.klucz_przyciszania` jego szynę. W kluczu musi być mikrofon, nie może być samego słuchacza. Szyna klucza nie może być szyną N-1, podsłuchu ani głośników. Nie wolno wyprowadzić jej na antenę, USB ani AUX.

Mowa i dźwięki potwierdzeń pozostają poza anteną. Walidator nie potwierdza fizycznego okablowania karty dźwiękowej, USB, P16, AUX ani ustawień systemu operacyjnego.

## Budżet obecnego stanowiska

1. Kanały 1/2: Muzyka 1; 3/4: Muzyka 2; 5/6: Muzyka 3; 7/8: Zoom; 9: Mikrofon; 10: Telefon. Wolne wejścia profilu: 11, 12, 13, 14, 15, 16.
2. Bus 1: N-1 telefonu. Bus 2: podsłuch telefonu. Bus 3/4: N-1 Zooma stereo. Bus 5: klucz przyciszania. Bus 6: głośniki mono. Wolnych szyn nie ma.
3. USB 1/2: N-1 Zooma, w projekcie BAZA Bus 3/4 POST. USB 3/4: emisja Main L/R POST. USB 5 do 18: w projekcie BAZA kopie Main L/R POST. Lista `profil.usb_suche_dozwolone` dopuszcza tam suchy głos do oddzielnego nagrywania, ale nie deklaruje faktycznego sygnału. USB 1 do 4 nigdy nie należą do tej listy.
4. Słuchacz przyciszany: `telefon`. Źródła klucza: `mikrofon`, `zoom`. Obecność w kluczu zależy od wspólnej rozmowy, nie od samego zaznaczenia na liście.
5. Paski 1 do 6: mikrofon, telefon, Zoom, trzy muzyki. Paski 7/8 wolne. SOLO wolny. MUTE mikrofonu: kaszel, MUTE rozmówców: talkback, pozostałe MUTE wolne. SELECT mikrofonu: antena, rozmówców: CUE, muzyki: PFL. REC mikrofonu: alarm ciszy, pozostałych źródeł: informacja „suwakiem”.
6. Playout: `auto`, z preferencją StationPlaylist. Dostępne są też `sara` i `stationplaylist` (w JSON bez rozróżniania wielkości liter, starszy alias `spl` pozostaje rozpoznawany). Wyłączenie playoutu działa przez `--emisja brak`. Wartość `emisja.program: "brak"` nie jest obsługiwana przez obecny adapter i walidator ją odrzuca. Hold i edycja punktów miksu należą tylko do SARY.

Raport `--sprawdz` oblicza obsadę kanałów i szyn z podanego pliku, również przy konflikcie. Jawnie wymienia wolne zasoby. Role USB oznacza jako projekt BAZA, nie jako pomiar. Po przeniesieniu szyny powrotu trzeba osobno uzgodnić scenę; sam JSON jej nie przebuduje. Przy błędnej konfiguracji raport jest częściowy: pomija niewłaściwe typy i numery poza zakresem, nie przydziela ich automatycznie.

## Co jest parametrem, a co pozostaje stałą kodu

Odsyłacze poniżej dotyczą dokładnie `cbb5a4b860f6dbfefb208e2a23013aafa66f84be`. Ścieżki `mostek/...` są względne wobec repozytorium mostka, `../scena/...` wobec katalogu projektu. Numery linii nie odnoszą się do późniejszej integracji walidatora.

1. A01, mikrofon. Nazwa wyświetlana, kanały, poziom maksymalny są parametrami (`mostek/ustawienia.py:29-41`). Jedna tożsamość mikrofonu, wspólne CUE i ochrona głośników są stałe (`mostek/logika.py:33,242-258,327-334`; `mostek/rdzen.py:758-771,1416-1421`).
2. A02, rozmówcy. Powiązania i numery szyn są parametrami (`mostek/ustawienia.py:45-50,161-167`). Źródła `mikrofon`, `telefon`, `zoom` są wymagane przez loader (`mostek/ustawienia.py:225-229`). Szczególny podsłuch telefonu korzysta z pierwszego kanału (`mostek/logika.py:150-151,595-596,826-832`). Sama stała ZOOM nie dowodzi równie szczególnej logiki Zooma.
3. A03, przyciszanie. Słuchacz, źródła klucza i szyna są parametrami, ale słuchacz i klucz są pojedyncze, a mikrofon wymagany w kluczu (`mostek/ustawienia.py:68-71,177-179,249-255`; `mostek/logika.py:308-325,928-944`).
4. A04, zasoby. Numery szyn można zmieniać, lecz zakres MR18 to sześć szyn (`mostek/sciezki.py:369-384`). Obecny budżet zajmuje je wszystkie (`ustawienia/stanowisko.json:56-66`). Nowy numer nie tworzy nowego zasobu.
5. A05, topologia. N-1, izolacja prywatnych dróg, zakaz szyn na LR i mikrofonu w głośnikach nie są opcjami (`mostek/logika.py:590-598,616-621,833-861`). Zmiana PRE/POST nie jest swobodnym parametrem: stanowi także część modelu rozmowy (`mostek/rdzen.py:758-818`; `mostek/logika.py:869-889`).
6. A06, USB i scena. Dozwolone wyjścia suchego głosu są parametrem z bezwzględnym zakazem USB 1 do 4 (`mostek/ustawienia.py:286-290`; `mostek/logika.py:849-861`). Wejścia, phantom, efekty, AUX, USB i P16 projektu sceny są przypisaniami generatora (`../scena/generuj_baza.py:63-158`). Zmiana JSON nie jest zmianą sceny.
7. A07, mikser. Port i czasy są parametrami, adresy, skale, format mierników oraz zakresy urządzenia należą do adaptera MR18 (`mostek/sciezki.py:318-351,369-384`; `mostek/mierniki.py:35-63`). Port OSC nie przełącza na X32/M32.
8. A08, powierzchnia. Numery nut i CC są parametrami; osiem pasków, master 9, protokół MC oraz jeden port są stałe (`mostek/xtouch.py:62-74,94-109,138-152`; `mostek/glowny.py:200-212`; `mostek/rdzen.py:2660-2672`). Brak bankowania kanałów i agregacji Extendera.
9. A09, playout. Wybór i porty są parametrami, TCP jest lokalne, a zdolności adapterów różne (`mostek/emisja.py:34-74,281-291,544-560,583-608`; `mostek/glowny.py:155-156,196`). Wyłączenie przez CLI nie jest nową funkcją.
10. A10, Hold. Przełącznik `mikrofon_wstrzymuje_automat` jest parametrem. Stała reguła obejmuje mikrofon i rozmówców z odbiorcą na antenie; nieznany stan nie zwalnia Hold (`mostek/rdzen.py:2731-2742`; `mostek/playout.py:168-205`). Nie ma konfigurowalnej listy grup.
11. A11, dostępność. Teksty, tryb informacji i mapa dźwięków są parametrami. WinMM, NVDA, polska odmiana czasu i zasady zachowania mowy dla ostrzeżeń są cechami implementacji (`mostek/xtouch.py:484-491`; `mostek/mowa.py:65-91,403-413`; `mostek/liczniki.py:12-60`; `mostek/informacja.py:54-81,459-484`). Komunikaty typu „obaj” nie opisują dowolnej liczby rozmówców.
12. A12, walidacja. Dotychczasowe konwersje i kontrole są w `mostek/ustawienia.py:145-186,225-310`. Konwersja numerów i słownik pasków powstawały przed kontrolą, więc gubiły typ wejściowy i duplikaty pasków. Nowy moduł bada dane surowe przed konwersją. Nie zastępuje zapory ani nie zmienia routingu.

## Sprawdzenie i zgodność startu

Z katalogu mostka:

    python -B -m mostek --sprawdz
    python -B -m mostek --sprawdz --ustawienia stanowisko.json --poziomy poziomy_bazowe.json --json
    python -B narzedzia/sprawdz_stanowisko.py --ustawienia stanowisko.json --poziomy poziomy_bazowe.json

W paczce Windows odpowiednikiem jest `mostek.exe --sprawdz`. Dane domyślne pochodzą z katalogu EXE, nie z bieżącego katalogu powłoki. `-B` w przykładach z Pythonem wyłącza jego własny zapis pamięci podręcznej `.pyc`.

Kod 0: bez błędów, możliwe ostrzeżenia. Kod 1: błędy konfiguracji. Kod 2: pliku nie można odczytać, zdekodować jako UTF-8 lub rozpoznać jako JSON. Błędny kształt poprawnego składniowo JSON to kod 1. Każdy problem zawiera ścieżkę pola, tekst po polsku i poziom. Nieznane klucze, również komentarze z podkreślnikiem, są ostrzeżeniami; znane komentarze profilu są pomijane. Brak opcjonalnego pola z określoną wartością domyślną jest wskazywany bez dopisywania go do pliku. Nieznana wersja schematu jest błędem.

Sprawdzenie nie konstruuje klienta MR18, nie otwiera OSC ani MIDI, nie uruchamia playoutu, mowy, dźwięków ani dziennika. Nie zapisuje poziomów i trybu informacji. Nie wczytuje sceny do urządzenia i nie łączy się z komputerem studia. Nie ma tu opcji `--scena`; porównanie sceny pozostaje osobnym krokiem.

Zwykły start to celowo inny kontrakt niż sprawdzenie instalatorskie. Zachowuje wszystkie stare odmowy i wynik konwersji dawniej poprawnych plików. Nowe błędy wykryte w dawniej akceptowanym pliku są na razie ostrzeżeniami w dzienniku, nie nową blokadą. Dotychczasowy wyjątek techniczny zostaje czytelnym `BladUstawien`. Sam błąd walidatora nie daje uprawnienia do zmiany profilu aktywnego miksera.

Dlatego wynik `--sprawdz` trzeba potraktować jako obowiązkową bramkę instalatora. Nie należy omijać jego błędu przez zwykłe uruchomienie starego profilu. Podniesienie nowych kontroli do blokad startu wymaga osobnej decyzji o migracji.

## Dalszy kierunek

Fundament jest warstwą projektowania bez sprzętu. Następny niezależny etap P05 może wykorzystać ten raport w dostępnym kreatorze i procedurze okablowania, bez zapisu do miksera. P02 obejmuje pełny model drugiego mikrofonu opisany w osobnym dokumencie. P03, polityki kanałów, wymaga testów przejść i nie może być ukryte jako nowe opcje walidatora. Żaden z tych etapów nie jest tu wdrożony.
