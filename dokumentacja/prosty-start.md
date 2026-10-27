# Prosty start: transport sceny i pochodzenie danych

## MUTE: kaszel i krótka rozmowa z wybraną osobą

MUTE na pasku 1 wycisza mikrofon na czas trzymania. Działa na antenie i w rozmowie poza anteną. W CUE znika także własny mikrofon ze słuchawek, a rozmówcę i muzykę nadal słychać. Puszczenie przywraca poprzednie drogi mikrofonu, jeśli nadal jest bezpiecznie, a po ich potwierdzeniu przywraca poprzednie solo. Nie ma dodatkowych dźwięków ani mowy. Gdy mikrofon nie ma otwartej drogi ani solo, nic się nie dzieje.

Tak samo działa kaszel przy PFL mikrofonu, również gdy jest to jedyne solo. Mikrofon znika wtedy ze słuchawek, a PHONES przechodzą na program/Main LR. Michał zaakceptował ten skutek: „niech też znika”. Puszczenie przywraca wcześniejsze solo, jeśli migawka jest nadal ważna. Nie jest włączane żadne zastępcze solo; Main LR, wysyłki i Bus 6 nie są zmieniane przez ten mechanizm odsłuchu. Sam talkback nie zabiera własnego mikrofonu z odsłuchu; zabiera go dopiero trzymany równocześnie kaszel.

Po F1 lub odłączeniu X-TOUCH solo mikrofonu może wrócić bez otwierania anteny, jeśli mikser nadal potwierdza stan. Po utracie miksera albo przy stanie nieznanym nie ma zaległego przywracania solo. Zmiana odsłuchu z innego programu lub świadome polecenie na stole wygrywa z migawką. Niepotwierdzony zapis odsłuchu daje dotychczasowe ostrzeżenie „Odsłuch niepotwierdzony”. Nowe zachowanie wymaga jeszcze odsłuchu na fizycznym MR18.

MUTE na pasku 2 to talkback do telefonu, na pasku 3 do Zooma. Przytrzymaj, powiedz, puść. Mikrofon znika na ten czas z anteny i od drugiej osoby. Telefon i Zoom pozostają na antenie lub poza nią tak jak wcześniej. Oba przyciski naraz pozwalają mówić do obu osób. Jeśli głośniki grają, talkback najpierw sam je wycisza i sprawdza potwierdzenie miksera. Po puszczeniu ostatniego przycisku i kaszlu wrócą, o ile mikrofon nie ma otwartego toru i nie trwa CUE. Głośników wyciszonych już przed talkbackiem nie włącza. Działa to także przy wyłączonym Mute-Act. Udany powrót nie dokłada mowy ani sygnału głośników.

Kaszel ma pierwszeństwo przed talkbackiem. Po puszczeniu kaszlu mikrofon wraca do osób, których MUTE nadal trzymasz. Diody MUTE pokazują trzymane przyciski. Talkback nie wywołuje mowy: dwa krótkie tony w górę oznaczają potwierdzone otwarcie do adresata, dwa w dół potwierdzone puszczenie i przywrócenie. Dotyczy to również dołożenia drugiego przycisku i puszczenia jednego z dwóch. Sygnały grają także w trybie samej mowy. Przytrzymany kaszel blokuje sygnał startu, bo adresat jeszcze nie słyszy mikrofonu. Sam kaszel przy wciśnięciu i puszczeniu nadal nie wywołuje mowy ani dźwięku. Błąd odtwarzania oznacza ciszę, bez zastępczej mowy. F2 i gałka mikrofonu podają stan na żądanie.

Można trzymać dowolnie długo. Stary limit 30 sekund nie obowiązuje, nawet jeśli został w pliku ustawień. Odłączenie albo restart stołu, utrata miksera i nieznany stan nadal przerywają działanie bez automatycznego powrotu mikrofonu. F1 w czasie talkbacku kończy go i zostawia mikrofon zamknięty oraz głośniki wyciszone. Tak samo jest po awaryjnym przerwaniu. Ręczne polecenie głośników wygrywa z automatem: po puszczeniu nie będzie automatycznego odciszenia. Wykryte odciszenie z innego programu przerywa talkback i wywołuje ochronne zamknięcie. Ostrzeżenia bezpieczeństwa nadal są mówione. Bez potwierdzenia z miksera mostek nie obiecuje, że zamknięcie się udało.

Michał zaakceptował odsłuch obu plików sygnałów talkbacku; pliki i generator pozostały bez zmian. Brzmienia nowych odmów i ostrzeżeń pozostają do akceptacji. Automat głośników nie został sprawdzony na prawdziwych wyjściach MR18. Przed użyciem na antenie trzeba odsłuchać obie strony i potwierdzić puszczanie przycisków oraz zachowanie po odłączeniu stołu. W tej pracy nie zbudowano ani nie dostarczono nowej paczki Windows.

## Wstrzymanie automatu SARY

Mikrofon, telefon i Zoom na antenie zatrzymują automatyczne uruchomienie następnego utworu, również w automiksie. Bieżący utwór gra do końca. Wyłączenie mikrofonu nie zwalnia wstrzymania, dopóki telefon albo Zoom pozostaje na antenie. Nie dotyczy to StationPlaylist.

Telefon i Zoom blokują automat tylko przy włączonym Main On, suwaku powyżej progu anteny (domyślnie minus 50 dB) i bez CUE. Suwak na dole albo CUE nie blokuje. Wejście suwakiem z CUE i zmiany z innego programu są rozpoznawane przy najbliższej obserwacji miksera, bez naciskania F1. Mikrofon liczy się jak wcześniej przez Main On, także gdy jego suwak jest na dole.

Wstrzymanie znika dopiero po zejściu ostatniej osoby z anteny. Kaszel i talkback nie zwalniają go chwilowo. Brak pewności co do stanu źródła również nie pozwala zwolnić wstrzymania. Jeśli utwór już się skończył, następny uruchamia się klawiszem Następny; mostek nie wysyła sam Play ani Skip.

Dotychczasowy komunikat „Automat czeka na mikrofon” pozostaje bez zmiany i dotyczy teraz również telefonu i Zooma. Ruchy suwaka w obrębie anteny ani zmiana osoby podtrzymującej wstrzymanie nie powtarzają komunikatu. Nie dodano nowych dźwięków.

Opcja `emisja.mikrofon_wstrzymuje_automat: false` wyłącza całą funkcję, również dla rozmówców. Ustawienia działają od restartu mostka. Wyłączenie opcji nie zwalnia już aktywnego Hold; przedtem trzeba zdjąć z anteny wszystkie blokujące źródła albo zamknąć serwer SARY. Rozszerzenie sprawdzono na symulatorze miksera i atrapie TCP, nie na fizycznym MR18 i rzeczywistej SARZE.

## Bank, Channel i OK na stole

Bank w lewo poza punktami miksu mówi „Odtwarzacz 2”, „Odtwarzacze 1 i 2”, „Odtwarzacze 1, 2 i 3” albo „Nic nie gra”. To numery odtwarzaczy głównej playlisty SARY, nie numery utworów ani odsłuch PFL. Odczyt nie czyta tytułu ani czasu, nie zmienia emisji i nie dodaje dźwięków. W trybie punktów Bank w lewo nadal wykonuje tylko MixSave, bez pytania o odtwarzacze. Bank w prawo poza punktami pozostaje wolny.

W StationPlaylist słychać „Numer odtwarzacza jest tylko w SARZE”, bez wysyłania Players. Przy jawnym wyborze SPL nie ma żadnego zapytania; automatyczny wybór może najpierw rozpoznać program przez Helo. Błędna odpowiedź SARY, także ERR ze starszej wersji, daje „SARA podała błędne numery odtwarzaczy”, a nie komunikat o zerwanym łączu. Brak wybranego programu, brak dostępnego programu i brak odpowiedzi podczas operacji zachowują istniejące komunikaty emisji. Robocze teksty SPL i błędu danych oraz opis nauki „Bank w lewo, w punktach miksu zapis, poza nimi odtwarzacz” wymagają akceptacji Michała przed wdrożeniem.

| Klawisz | MIDI | W punktach miksu | Poza punktami miksu |
| --- | --- | --- | --- |
| Bank w lewo | 46 / 0x2E | MixSave: zapisz punkty i wyjdź | Players: numery grających odtwarzaczy SARY |
| Bank w prawo | 47 / 0x2F | MixCancel: porzuć zmiany i wyjdź | „Klawisz wolny”, bez polecenia |
| Channel w lewo | 48 / 0x30 | Przełącz automat jak F7 | Przełącz automat jak F7 |
| Channel w prawo | 49 / 0x31 | Czas do końca utworu na antenie | Czas do końca utworu na antenie |
| OK (Zoom między strzałkami) | 100 / 0x64 | MixSet: ustaw wybrany punkt w bieżącej pozycji | Przełącz znacznik do emisji |

Scrub 101 włącza punkty miksu w SARZE. Stare Save 80, Cancel 82, Marker 84 i F7 60 działają nadal. OK mówi np. „Intro ustawione”; zapis całego zestawu i wyjście to dopiero Bank w lewo albo Save. Bank w prawo i Cancel porzucają zmiany. Ruchy kółka i korekty pozostają bez czytania czasu. Pełna mapa i ograniczenia: [punkty miksu](punkty-miksu.md).

Channel w lewo włącza albo wyłącza automat także podczas edycji, tak jak F7. Channel w prawo jest tylko odczytem anteny, nie czasu odsłuchu PFL. Mówi np. „Zostało 1 minuta 23 sekundy”, a bez grania „Nic nie gra” lub „Pauza”. Bez programu mówi „Nie wybrano programu emisyjnego” albo „Nie odpowiada żaden program emisyjny”. Odczyt wymaga TCP w SPL i SARZE. Nowy tekst czasu i rozszerzone opisy nauki są do akceptacji przed wdrożeniem. Próby wykonano na atrapie TCP, nie na fizycznym stole.

## Zapis sceny

Domyślnie scena_mr18 wysyła typowane komunikaty SET całych węzłów, jak rzeczywisty AOSC z Air Access 18. Każdy z 693 datagramów wygenerowanych naszym schematem dla sceny `tests/dane_sceny/baza-aosc-v4.scn` jest identyczny bajtowo z importem tej sceny przez AOSC 2.2r1b82. Wyciąg z numerami sekwencyjnymi i surowymi bajtami jest w `tests/dane_sceny/aosc-v4-set.json`. Test nie generuje sobie wzorca loaderem.

Specyfikacja karty mylnie przypisała zapis tekstowy przez adres `/` do XAirSetScene.c. Ten plik wywołuje SetSceneParse (wiersz 144), który generuje typowane OSC. W XAir_Command.c opcja `-s` przeniesiona z X32 jest zakomentowana. Nie ma tu podstaw do gwarancji obsługi tekstowego `/` przez MR18. Dlatego `--tekstowy` jest eksperymentem dostępnym wyłącznie z `--symulator` na 127.0.0.1. START go nie używa. Realny sprzęt pozostaje nieodebrany również dla metody typowanej.

Odczyt przez `/node`: XAirGetScene.c 137–156, odpowiedź `node` bez początkowego ukośnika, argument tekstowy. Wyjątek dekodowania jest lokalny dla narzędzia. Nie zmieniono kodeka ani zapory mostka.

## Dane i model

- dane_sceny/schemat-mr18.json: własny schemat sceny MR18. Lista 693 węzłów w kolejności zapisu, budowa każdego węzła, skale i kroki pól oraz 61 typów efektów. Powstał 27.10.2026 z pomiaru na Midas MR18 (MR18V2, firmware 1.26): próbne zapisy na nieużywanych kanale 16, wejściu 16, Bus 5, DCA 4, Send 4 i slocie FX 4, odczyt typowany i tekst /node, przywrócenie stanu. Każde pole ma w "zrodlo" informację, czy zostało zmierzone, przyjęte z analogii do zmierzonej klasy, czy z publicznej listy OSC X AIR potwierdzonej odczytem. Pliki Air Access 18 (x.sct, scn.xnd, Factory Reset.scn) nie są częścią projektu.
- tests/dane_sceny/pomiar-mr18-probki.json: 13455 próbek tego pomiaru (zapis, odczyt, tekst). Test tests/test_schemat_wlasny.py sprawdza na nich skale schematu.
- dane_sceny/BAZA.scn: scena BAZA.
- tests/dane_sceny/baza-aosc-v4.scn: scena, z której nagrano datagramy AOSC w tests/dane_sceny/aosc-v4-set.json; stan startowy modelu w testach to ta scena z kilkoma zmianami (tests/mikser_rejestrujacy.py, ZMIANY_STARTU).
- narzedzia/format_scn.py: walidator sceny; czyta schemat JSON.
- tests/format_node.py, tests/mikser_rejestrujacy.py: model miksera do testów.

Reguły porównań: `scena/dowody/FORMAT-NODE.md`. Normalizowane są białe znaki między polami i zapis liczby, np. +0.0, -0.0, 0, 1k97 i 1970. Nie ma tolerancji różnicy wartości. Nazwy, enumy (także ratio 2.0), maski i przełączniki są dosłowne. 

## Bezpieczeństwo

Najpierw walidacja pliku i wszystkich pakietów. Potem pełny odczyt 693 węzłów do pamięci, walidacja kopii, zapis nowego pliku w trybie xb, flush i fsync. Dopiero wtedy zaczyna się SET. Przy kolizji sekundy dopisywany jest licznik, bez zastępowania starego pliku. Niepełny odczyt albo błąd zapisu dyskowego przerywa przed pierwszym SET, także solo.

Nie jest to transakcja. Inne programy sterujące mikserem należy zamknąć. Nie ma automatycznego rollbacku przy braku sieci. Raport wskazuje rozbieżności; domyślnie blokują uruchomienie mostka. Po każdym wczytaniu osobno zerowanych i odczytywanych jest 22 solo z rejestru mostka. Ich stan sprzed próby nie należy do sceny i nie jest przywracany. Snapshoty w pamięci miksera nie są dotykane.

PRZYWROC wybiera najnowszą kopię KOPIA-PRZED-BAZA według czasu pliku. Kopię bezpośrednio sprzed przywrócenia zapisuje jako KOPIA-PRZED-PRZYWROC, żeby kolejne przywracanie nie zaczęło przełączać wstecz do BAZY. Jawny plik można wskazać przez `program/scena_mr18.exe przywroc PLIK --mr18 ADRES --zapisz`.

START i PRZYWROC mają wspólną blokadę systemową zwalnianą po zakończeniu procesu. Nie wykrywa ona obcych programów ani osobno uruchomionego starego mostka, dlatego wymagają także zamknięcia innych okien i aplikacji.

## Odbiór cichy

`MOSTEK_TEST_SYMULATOR=1` ogranicza cel do 127.0.0.1 i uruchamia mostek z `--mowa konsola --midi brak --dzwieki-konsola`. Bez tej zmiennej START wybiera `--mowa nvda --midi winmm`. Nie wolno używać zmiennej testowej do próby sprzętowej. W odbiorze nie wywołuje się NVDA ani audio; potwierdzenie jego fallbacku odbywa się na atrapach. Repo sceny i plan pozostają tylko do odczytu.
