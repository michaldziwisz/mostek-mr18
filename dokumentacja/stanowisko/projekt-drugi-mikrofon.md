# Projekt drugiego mikrofonu lokalnego

## Status i przykład

To projekt P02, nie konfiguracja do uruchomienia na antenie. Plik `przyklad-dwa-mikrofony.json` jest kompletnym plikiem stanowiska z dotychczasowymi sekcjami. Dodaje źródło `mikrofon2` na wejściu 11 i przypisuje mu pasek 7, SELECT anteny oraz MUTE kaszlu. Zachowuje obecny mikrofon na kanale 9 i pasku 1, oba powroty rozmówców, szyny, playout i komunikaty. Nie należy dopisywać nowego kanału do listy `mikrofon.kanaly`: oznaczałoby to jeden wspólnie sterowany mikrofon logiczny, a nie niezależnego gościa.

Sprawdzenie:

    python -B -m mostek --sprawdz --ustawienia dokumentacja/stanowisko/przyklad-dwa-mikrofony.json

Wynikiem jest jeden błąd roli przy `zrodla.mikrofon2`: „drugi mikrofon lokalny nie jest jeszcze obsługiwany”, z odsyłaczem do tego dokumentu. Ostrzeżenia o domyślnych wartościach obecnych źródeł mogą nadal wystąpić. Dla nieobsługiwanej roli walidator nie mnoży wtórnych odmów przypisania kaszlu, przełącznika anteny i brakujących poziomów jej wysyłek. Inne, niezależne błędy pliku nadal są raportowane.

Przykład używa dotychczasowego pliku poziomów. Gdy rdzeń będzie obsługiwał tę rolę, potrzebne będą również jawne poziomy `wysylki.mikrofon2.telefon` i `wysylki.mikrofon2.zoom`, osobne komunikaty oraz uzgodniona scena. Nie są dziś interpretowane ani dopisywane automatycznie. Ten dokument nie wprowadza nowej wersji schematu, pola roli ani nowej wersji sceny.

## Zasoby MR18

1. Wejście 11 i pasek 7 są wolne w obecnym stanowisku. Drugi lokalny mikrofon w tej samej strefie głośników nie potrzebuje nowej szyny N-1.
2. Bus 1 pozostaje telefonem, Bus 2 podsłuchem telefonu, Bus 3/4 powrotem Zooma, Bus 5 kluczem, Bus 6 głośnikami. Nie ma wolnej szyny.
3. Wspólny klucz mógłby obejmować oba mikrofony i Zoom, lecz uczestnictwo musi wynikać z tej samej rozmowy co przyciszany słuchacz. Sam wpis do listy źródeł nie wystarcza.
4. Oddzielna strefa odsłuchowa gościa albo dodatkowy niezależny N-1 może wymagać odzyskania szyny: świadomej rezygnacji z osobnego podsłuchu, powrotu Zooma mono albo zmiany miksera. Nie wolno samoczynnie współdzielić szyn ani wyłączyć ochrony klucza.
5. Potrzebne są osobno: potwierdzenie wejścia analogowego 11, gain i filtra, ewentualnego phantom zgodnie ze sprzętem, wszystkich wyjść oraz drogi mowy i dźwięków programu. Nie wolno skopiować phantom z mikrofonu 9 bez sprawdzenia podłączonego urządzenia.

## Zmiany wymagane w rdzeniu

1. Tożsamość i stan mikrofonów. Lista lokalnych źródeł z osobnym potwierdzonym ON, nie tylko zamiana stałej `MIKROFON` na listę. Rozdzielić źródło, rolę i strefę. Zachować zgodność jednego mikrofonu.
2. CUE. Zdecydować, który mikrofon uczestniczy w każdej prywatnej rozmowie, kto może wejść na antenę oraz jak kończy się ostatnie CUE. Nie otwierać drugiego mikrofonu samym wejściem rozmówcy na CUE. Utrata wiedzy nie może usuwać blokady.
3. Hold. Ująć każdy lokalny mikrofon oraz rozmówców na antenie. Zamknięcie jednego nie zwalnia automatu, gdy drugi nadal mówi. Zachować migawki kaszlu i talkbacku, priorytet poleceń oraz wyłączność SARY.
4. Liczniki. Osobny licznik i przypomnienie każdego mikrofonu; ewentualny licznik grupy wymaga decyzji o znaczeniu. Kaszel jednego nie resetuje licznika drugiego.
5. Głośniki. Powiązać mikrofony ze strefami. Głośniki pozostają zamknięte, dopóki jakikolwiek należący do strefy mikrofon może mieć otwarty tor lub trwa odpowiednie CUE. Automatyczny powrót wymaga potwierdzenia całej grupy, nie pojedynczej flagi.
6. Sygnalizacja. Diody, odczyt paska, F2, opis nauki i ewentualna lampka muszą wskazywać konkretny mikrofon albo jasno nazwaną grupę. Nie potwierdzać stanu na podstawie samego polecenia.
7. Kaszel. Niezależne naciśnięcie i puszczenie, zapamiętanie własnych torów, równoczesne trzymanie obu przycisków i utrata kontrolera. Odtworzenie jednego nie może nadpisać obcej zmiany ani otworzyć drugiego mikrofonu.
8. Talkback. Jawny wybór mikrofonu nadawczego i adresatów. Zachować izolację anteny i klucza, poziom jak w CUE i przyciszenie muzyki u adresata. Rozstrzygnąć nakładanie talkbacku z kaszlem drugiego mikrofonu, bez wspólnej migawki `_mikrofon_sprzed` nadpisującej oba źródła.
9. Komunikaty. Odejść od pojedynczego słowa „Mikrofon”, jeśli nie identyfikuje nadawcy. Nowe brzmienia mowy wymagają akceptacji przed wdrożeniem; obecny walidator dodaje tylko tekst konsoli, nie dźwięki ani mowę.
10. Zapora i profil. Reguły kaszlu, talkbacku, prywatności, głośników, USB i klucza muszą sprawdzać każdy mikrofon i każdą strefę. Reconnect nie odtwarza prywatnej rozmowy. Żadnej obecnej reguły nie wolno wyłączyć w celu przepuszczenia nowego przykładu.

Punkty odniesienia na `cbb5a4b`: `mostek/logika.py:33,242-258,327-334,590-621,653-714,833-861`; `mostek/rdzen.py:758-818,1416-1421,1523-1554,1755-1906,2024-2046,2132-2153,2674-2703,2731-2742`; `mostek/ustawienia.py:265-279`. Opis obecnych ograniczeń i A01 do A12 znajduje się w `role-i-strefy.md`.

## Warunki odbioru P02

1. Stary profil daje identyczne cele routingu i komunikaty dla sytuacji A do G oraz wszystkich przejść. Złote testy ustawień pozostają zielone.
2. Każdy mikrofon ma niezależną antenę i kaszel. Naciśnięcie lub puszczenie jednego nie otwiera i nie zamyka drugiego. Sprawdzić obie kolejności, oba przyciski naraz i obcą zmianę miksera.
3. Dla wszystkich kombinacji mikrofonów, CUE i talkbacku sprawdzić Main LR, każdy N-1, głośniki, USB, AUX, P16 i klucz. Własny sygnał rozmówcy nigdy nie wraca do niego.
4. Głośniki pozostają wyciszone przy dowolnym nieznanym lub otwartym torze mikrofonu danej strefy. Zamknięcie jednego mikrofonu nie odcisza ich przy drugim.
5. Hold, liczniki i diody odpowiadają potwierdzonemu stanowi każdego mikrofonu. Hold nie trafia do SPL, stan nieznany go nie zwalnia.
6. Utrata miksera, kontrolera, zgubione puszczenie przycisku, opóźniony odczyt i reconnect pozostawiają bezpieczny stan bez odtwarzania prywatnych torów. Cudze zapisy nie są przywracane na ślepo.
7. Pełna regresja oraz mutanty każdej zmienionej reguły zapory. Odbiór na symulatorze nie zastępuje niezależnego odsłuchu wszystkich wyjść rzeczywistego stanowiska poza anteną.
8. Instalacja nowego profilu, sceny i poziomów jest osobnym zatwierdzonym krokiem z kopią i możliwością powrotu. Samo uruchomienie mostka ani walidatora nie wgrywa sceny.
