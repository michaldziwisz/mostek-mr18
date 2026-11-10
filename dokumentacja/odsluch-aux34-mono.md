# Odsłuch AUX 3/4 wyłącznie podczas CUE

Status: korekta kodu offline. Nie jest to zgoda na wdrożenie ani potwierdzenie dźwięku na sprzęcie. Historyczna próba mono potwierdzała podstawową drogę Send3 do obu AUX, nie nową automatykę. Nie instalować automatycznie ani podczas emisji.

## Włączenie

`zachowanie.tryb_odsluchu: "aux34_mono"` jest opt-in. Brak pola lub `"dotychczasowy"` zachowuje dotychczasowe działanie. Domyślne ustawienia, mapy klawiszy i teksty komunikatów pozostają bez zmian. Osobistych ustawień nie zastępujemy plikiem z repo.

Send3 to wysyłka kanałowa 09, nie Bus3. Jej miks mono trafia identycznie do AUX3 i AUX4. Bus3/4 nadal przenosi stereo N-1 Zooma. Rezerwa 11–16 nie jest zajmowana.

## Macierz odsłuchu

| Stan | PHONES | AUX3/4 |
| --- | --- | --- |
| Spoczynek, bez CUE | Program Main LR w stereo | Cisza |
| Mikrofon lub rozmówcy na antenie, bez CUE | Program Main LR w stereo, z głosami antenowymi | Cisza |
| CUE telefonu | Mikrofon i telefon przez PFL, bez automatycznej domieszki muzyki | Kontrolny program mono, bez mikrofonu i telefonu CUE |
| CUE Zooma | Mikrofon i Zoom przez PFL | Kontrolny program mono, bez mikrofonu i Zooma CUE |
| Wspólne CUE | Mikrofon i obaj rozmówcy przez PFL | Muzyka mono |
| Jeden rozmówca na antenie, drugi na CUE | Mikrofon i rozmówca CUE | Program mono z rozmówcą antenowym |
| Koniec CUE | Automatyczny powrót Main LR stereo | Automatyczna cisza |
| Sam chwilowy talkback, bez CUE | Dotychczas wybrany odsłuch, domyślnie Main LR stereo | Cisza |
| Kaszel | Mikrofon wyciszony; reszta według istniejącego CUE lub anteny | Tylko podczas istniejącego CUE, zawsze bez mikrofonu |

Talkback nie jest nowym trwałym CUE. Zachowuje zbiór CUE sprzed trzymania i istniejące wysyłki prywatne, bez otwierania AUX poza CUE. Kaszel nie zmienia tego zbioru.

Ręczne PFL pozostaje świadomą alternatywą operatora, również bez CUE. Podczas CUE najpierw zamyka i potwierdza kopię danego źródła na AUX, dopiero potem otwiera jego solo. „Słuchaj programu” zamyka AUX i wybiera Main LR stereo również podczas CUE. „Koniec PFL” wraca do rozmowy przy trwającym CUE, a bez CUE do stereo programu. Ręcznie pozostawione PFL jest jawnym wyjątkiem od zwykłego odsłuchu LR, nie automatycznym trybem mono.

Przy przełączeniu drogi najpierw następuje jej zamknięcie i potwierdzenie, następnie otwarcie docelowej. Brak potwierdzenia zamknięcia AUX blokuje własne przełączenie na LR. Koniec CUE odczytany z innego klienta również zdejmuje solo uczestników poprzedniej rozmowy. Zmian obcego klienta nie można wyprzedzić: dopasowanie następuje dopiero po odczycie. Nie jest to sprzętowa zapora dla innych klientów.

## Poziomy i tory chronione

AUX bierze tylko potwierdzony Main On bez PFL, przez POST. Fader, mute, trim, EQ i dynamika działają już w tym torze; mostek nie mnoży fadera drugi raz. Muzyka ma wysyłkę −6 dB, głosy antenowe 0 dB. Mikrofon nigdy nie trafia do Send3.

Master Send3 jest wyłącznie sprawdzany: ON i −30 dB, OSC 0.25. Sprzętowe 0.24926686 oraz 0.25024438 mieszczą się w tolerancji 0.005. NaN i nieskończoności są odrzucane. Mostek nie zapisuje mastera ani routingu.

Bez zmian pozostają: stereo anteny i N-1, AUX1/2, podsłuch telefonu, AUX5/6 przez Bus6 i automatyka głośników, Bus5 klucza, DSP, inserty, USB Trim −1 dB, poziomy SARY, rezerwa, mapy i komunikaty.

## Scena i bezpieczna migracja

BAZA jest stanem bez CUE: źródło PHONES LR, wszystkie wysyłki Send3 zamknięte. Kontroler otwiera je dopiero po potwierdzonym CUE. Samą zamianę pól sceny wykonuje `narzedzia/migracja_aux34.py`, funkcja `przygotuj(tekst)` — przyjmuje treść SCN i zwraca nową treść oraz listę zmian, bez zapisu na dysk. Domyślna BAZA i sceny nietknięte tą funkcją zachowują stary tryb.

Wzorcowa scena z tego trybu i pełny zestaw ustawień stanowiska leżą w `tests/dane_aux34/`. To fixture testowy, nie gotowa konfiguracja do wdrożenia.

Przygotowanie osobistej BAZY: najpierw kopia pliku sceny, potem migracja pokazująca plan bez zapisu, a zapis dopiero po sprawdzeniu różnicy. Narzędzie nie łączy się ze sprzętem i nie nadpisuje oryginałów. Duplikaty i format są zachowane, sprzeczne wartości odrzucane przed normalizacją. AUX5/6 muszą już mieć Bus6 POST, migracja ich nie naprawia.

## Start, utrata łączności i odbiór

Synchronizacja tylko zamyka niezgodne kopie, bez otwierania nowych wysyłek. Dopasowanie następuje w czynności operatora i cyklu pracy. Brak gotowości, rozbrojenie kontrolera i niezgodny profil nie uprawniają do nowych otwarć. Po utracie sieci mikser może zachować ostatni tor audio, dlatego nie obiecujemy sprzętowej ciszy bez łączności.

Testy modelu potwierdzają sterowanie, nie DSP ani słyszalne stereo. Do odbioru na sprzęcie należą: stereo PHONES poza CUE, prywatność rozmowy, mono AUX podczas CUE, brak dublowania w przejściach, automatyczny powrót, rzeczywisty POST/mute i brak wpływu na inserty. Podmiana i próba sprzętowa wymagają osobnej zgody i bezpiecznego okna, poza emisją.
