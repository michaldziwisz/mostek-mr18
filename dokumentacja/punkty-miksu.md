# Punkty miksu w SARZE ze stołu X-TOUCH

Ta funkcja działa tylko z SARĄ obsługującą polecenia Mix*. Nie działa ze StationPlaylist. W trybie automatycznego wyboru programu mostek respektuje ustawioną preferencję. Gdy wybrany jest SPL, Scrub odmawia wejścia. Niczego do SPL nie wysyła poza ewentualnym rozpoznaniem programu przez Helo.

Brzmienie nowych komunikatów jest robocze. Przed wdrożeniem wymaga akceptacji Michała. Instrukcja opisuje implementację sprawdzoną z atrapą TCP, a nie odebrany już odsłuch na prawdziwym stanowisku.

## Wejście

Ustaw kursor głównej playlisty SARY na utworze. Naciśnij Scrub. Mostek mówi artystę, tytuł, długość utworu oraz Cue i jego wartość. Na przykład: „Punkty miksu: Artysta, Tytuł, 3:45. Cue 0:00,5”. Jeśli Cue nie ustawiono, pozycja startowa wynosi zero i słychać „Cue nieustawione”.

W trybie punktów kółko nie przesuwa kursora playlisty. Przesuwa pozycję wewnątrz utworu. Wolny obrót to 0,1 sekundy na ząbek, szybki to 1 sekunda. Mostek sumuje ruchy i wysyła je partiami. Kółko i REWIND najpierw zatrzymują się na początku utworu. Dalszy obrót w lewo przeskakuje na koniec, więc do punktu miksu przy końcu nie trzeba przewijać całego utworu. Tak samo dalszy obrót w prawo na końcu przeskakuje na początek. Kółko, REWIND, FFWD oraz góra i dół nie mówią czasu (decyzja Michała z 25 października 2026), słychać tylko odsłuch w PFL. Czas podaje F6 na żądanie oraz lewo i prawo przy wyborze punktu, na przykład „Intro 0:12,3”. Marker i OK mówią tylko „Intro ustawione”. Kolejna wypowiedź tego trybu może przerwać poprzednią, lecz nie ucina komunikatu mikrofonu ani wstrzymania automatu.

## Klawisze

Dotychczasowe numery nawigacji potwierdzono na X-TOUCH Michała w trybie nauki 24 października 2026 o 22:19. Bank 46/47 i Channel 48/49 pochodzą z mapy MC; nowe funkcje sprawdzono na surowych zdarzeniach MIDI w testach, nie na fizycznym stole.

Bank w lewo poza punktami miksu mówi „Odtwarzacz 2”, „Odtwarzacze 1 i 2”, „Odtwarzacze 1, 2 i 3” albo „Nic nie gra”. To numery odtwarzaczy głównej playlisty SARY, nie numery utworów ani odsłuch PFL. Odczyt nie czyta tytułu ani czasu, nie zmienia emisji i nie dodaje dźwięków. W trybie punktów Bank w lewo nadal wykonuje tylko MixSave, bez pytania o odtwarzacze. Bank w prawo poza punktami pozostaje wolny.

W StationPlaylist słychać „Numer odtwarzacza jest tylko w SARZE”, bez wysyłania Players. Przy jawnym wyborze SPL nie ma żadnego zapytania; automatyczny wybór może najpierw rozpoznać program przez Helo. Błędna odpowiedź SARY, także ERR ze starszej wersji, daje „SARA podała błędne numery odtwarzaczy”, a nie komunikat o zerwanym łączu. Brak wybranego programu, brak dostępnego programu i brak odpowiedzi podczas operacji zachowują istniejące komunikaty emisji. Robocze teksty SPL i błędu danych oraz opis nauki „Bank w lewo, w punktach miksu zapis, poza nimi odtwarzacz” wymagają akceptacji Michała przed wdrożeniem.

| Klawisz | MIDI | W punktach miksu | Poza punktami miksu |
| --- | --- | --- | --- |
| Bank w lewo | 46 / 0x2E | MixSave: zapisz punkty i wyjdź | Players: numery grających odtwarzaczy SARY |
| Bank w prawo | 47 / 0x2F | MixCancel: porzuć zmiany i wyjdź | „Klawisz wolny”, bez polecenia |
| Channel w lewo | 48 / 0x30 | Przełącz automat jak F7 | Przełącz automat jak F7 |
| Channel w prawo | 49 / 0x31 | Czas do końca utworu na antenie | Czas do końca utworu na antenie |
| OK (Zoom między strzałkami) | 100 / 0x64 | MixSet: ustaw wybrany punkt w bieżącej pozycji | Przełącz znacznik do emisji |

Save 80, Cancel 82, Marker 84 i F7 60 pozostają bez zmian. OK ustawia bieżący punkt, nie zapisuje całego zestawu do pliku. Zapis całego zestawu i wyjście to Bank w lewo albo Save. Bank i OK korzystają z tych samych ścieżek co stare klawisze.

Channel w lewo przełącza automat w obu trybach, tak jak F7. Channel w prawo czyta wyłącznie antenowy czas przez Stat/Rem, także podczas odsłuchu innego utworu w PFL. Przykład: „Zostało 1 minuta 23 sekundy”. Przy stopie: „Nic nie gra”, przy pauzie: „Pauza”, bez czasu. Bez wybranego programu: „Nie wybrano programu emisyjnego”, bez odpowiedzi: „Nie odpowiada żaden program emisyjny”. Odczyt niczego nie zmienia i działa także przez TCP StationPlaylist poza edycją.

Nowy komunikat „Zostało {czas}” i opisy nauki wymagają akceptacji Michała przed wdrożeniem. Nauka mówi: „Bank w lewo, w punktach miksu zapis, poza nimi odtwarzacz”, „Bank w prawo, w punktach miksu anulowanie, poza nimi wolny”, „Channel w lewo, automat”, „Channel w prawo, czas do końca utworu na antenie” i „Zoom, w punktach miksu ustaw punkt, poza nimi znacznik do emisji”. W nauce te klawisze niczego nie wykonują.

| Klawisz | Numer MIDI | Działanie w trybie punktów |
| --- | --- | --- |
| Scrub | 101 | Wejście lub wyjście bez zmian |
| Kółko jog | CC 60 | Przesuwanie pozycji w utworze |
| REWIND | 91 | Cofnięcie pozycji o 5 sekund |
| FFWD | 92 | Przesunięcie pozycji o 5 sekund dalej |
| Lewo | 98 | Poprzedni punkt |
| Prawo | 99 | Następny punkt |
| Góra | 96 | Korekta punktu o 0,1 sekundy później i odsłuch |
| Dół | 97 | Korekta punktu o 0,1 sekundy wcześniej i odsłuch |
| OK (Zoom) lub Marker | 100 lub 84 | Ustawienie punktu na bieżącej pozycji |
| Drop | 87 | Usunięcie ustawienia punktu |
| Enter | 83 | Włączenie lub wyłączenie odsłuchu od pozycji |
| Nudge | 85 | Odsłuch wybranego punktu |
| Cycle | 86 | Odsłuch przejścia do następnego utworu |
| Undo | 81 | Cofnięcie ostatniej zmiany punktu |
| Bank w lewo lub Save | 46 lub 80 | Zapis punktów i wyjście |
| Bank w prawo lub Cancel | 47 lub 82 | Porzucenie zmian i wyjście |
| F6 | 59 | Odczyt pozycji, wybranego punktu i jego wartości |

Punkty przechodzą kolejno: Cue, Intro, Outro, Segue, Segue fade, Overlap, Początek pętli, Koniec pętli. Po ostatnim wraca pierwszy. Wartości Cue, Intro, Outro, Segue i końców pętli są czasami od początku pliku. Segue fade i Overlap są długościami. Ich znaczenie i ograniczenia oblicza SARA tak jak w swoim oknie punktów miksu.

Play, Stop, Następny, F1, F7, oba Channel i suwaki działają tak samo jak poza trybem. Stop nadal zatrzymuje antenę, a nie odsłuch PFL. Odsłuch można wyłączyć przez Enter. Mikrofon nadal wstrzymuje automat zgodnie z ustawieniami Hold. Start utworu na antenie nie kończy edycji. REWIND w trybie punktów nie włącza nauki klawiszy. Po wyjściu znów ją włącza.

## Zapis i porzucenie

Jeśli są niezapisane zmiany, ponowny Scrub nie wychodzi z trybu. Mostek mówi: „Niezapisane zmiany. Save zapisuje, Cancel porzuca”.

Bank w lewo albo Save zapisuje i kończy tryb. Błędna kolejność Cue, Intro i Outro albo niewłaściwa pętla powoduje odmowę zapisu z opisem. Tryb pozostaje aktywny, więc można poprawić punkt albo nacisnąć Cancel.

Można edytować utwór, który już gra. Zapis od razu wpływa na jego przejście na antenie. Mostek mówi „Zapisano. Przejście za 12 sekund” albo „Zapisano. Punkt przejścia już minął, przejście następuje teraz”, zgodnie z odpowiedzią SARY. Jeśli utwór nie gra, mówi „Zapisano punkty miksu”. Tak samo mówi, gdy utwór gra, ale SARA nie ma zaplanowanego wyzwalacza przejścia, na przykład przy aktywnym Hold. To poprawny zapis bez obietnicy przejścia, nie błąd. Zapis nie zwalnia Hold ani nie kasuje przerwy za utworem.

Bank w prawo albo Cancel porzuca zmiany. Po wyjściu kółko i góra/dół znów poruszają się po playliście.

## Odmowy i utrata połączenia

Otwarte okno punktów miksu w SARZE blokuje wejście ze stołu. Brak utworu pod kursorem również daje odmowę. Do odsłuchu trzeba skonfigurować urządzenie PFL w SARZE. Brak tego urządzenia nie kończy sesji edycji.

Podczas sesji mostek utrzymuje osobne połączenie TCP i sprawdza je także w bezczynności, mniej więcej co sekundę. Po utracie połączenia kończy tryb i mówi „Punkty miksu zamknięte, SARA nie odpowiada”. Nie ponawia niepotwierdzonej zmiany ani zapisu. SARA porzuca niezapisane zmiany po rozłączeniu właściciela sesji. Jeśli odpowiedź zaginęła podczas Save, zapis mógł się już wykonać. Wtedy trzeba sprawdzić stan w SARZE.

## Protokół odczytu odtwarzaczy

Po Helo identyfikującym SARĘ mostek wysyła `Players` bez znaku `=`. Odpowiedź to dodatnie numery 1-based, rosnąco i bez powtórzeń, rozdzielone przecinkiem, na przykład `2`, `1,2` albo `1,2,3`. `-` oznacza, że nic nie gra. Nie są akceptowane spacje, puste odpowiedzi, zera wiodące, zero, liczby ujemne ani inna kolejność. To błąd danych (`BledneDaneOdtwarzaczy`, podklasa `BladEmisji`), nie awaria połączenia. Przy braku odpowiedzi pozostaje „Program emisyjny nie potwierdził wyniku. Sprawdź jego stan”. Operacja nie jest automatycznie ponawiana ani przekazywana do SPL. Nie pyta o Stat, Rem, This, Next ani indeks kursora.

Przed wspólnym wdrożeniem SARY i mostka pozostaje odbiór zgodności z rzeczywistym serwerem SARY obsługującym Players oraz próba na stanowisku. Test z atrapą TCP nie zastępuje tych prób.

## Ustawienia i granice pomiaru

Mapa dodatkowych funkcji znajduje się w `xtouch.punkty_miksu` w `ustawienia/stanowisko.json`. Klucze odpowiadają nazwom zdarzeń mostka, wartości wskazują polecenia SARY. Nazwy `scrub_wolny` oraz `nuta_80` do `nuta_87` zachowano dla zgodności z wcześniejszą mapą MIDI. Nie oznaczają już wolnego klawisza w trybie punktów. Teksty punktów miksu są w `komunikaty`, pod kluczami `miks_*`. Bank w lewo ma nazwę `bank_lewo_odtwarzacz` w obu mapach: `xtouch.klawisze["46"]` i `xtouch.punkty_miksu` (wartość `MixSave`). Przy aktualizacji ustawień trzeba zachować zgodność tych nazw; zastępują dawną `bank_lewo_wolny`. Odczyt poza punktami używa kluczy `emisja_odtwarzacz`, `emisja_odtwarzacze`, `emisja_odtwarzacze_spojnik` (domyślnie „ i ”), `emisja_odtwarzacz_spl`, `emisja_odtwarzacz_bledne_dane` i istniejącego `emisja_nic_nie_gra`.

Wolny krok to 100 ms, szybki 1000 ms. Odstęp między ząbkami krótszy niż 80 ms uruchamia szybki krok. Partia ruchów czeka najwyżej 40 ms od pierwszego ząbka, o ile tor emisji nie wykonuje innego polecenia. Kolejne ruchy nie odkładają wysłania w nieskończoność. OK, Marker i inne klawisze sesji najpierw wysyłają oczekującą sumę, aby operować na najnowszej pozycji. Hold nadal wyprzedza kolejkę. Żadne polecenie Mix* nie korzysta z zapasu okienkowego SPL.

Testy nie potwierdzają jeszcze dźwięku PFL, rzeczywistego zapisu tagów, zachowania anteny prawdziwej SARY, przerwania mowy prawdziwego NVDA ani wygody kółka na sprzęcie. Te próby należą do odbioru z Michałem. Dotychczasową nawigację potwierdzono wcześniej pomiarem na jego stole; nowe przypisania Bank i Channel wymagają jeszcze próby fizycznej.
