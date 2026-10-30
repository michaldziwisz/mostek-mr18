# Mostek MR18 i X-TOUCH: instrukcja i opis działania

## Prosty start dla próby stanowiska

Paczka `mostek-mr18-prosty-start-<commit>.zip` ma tylko START.bat, PRZYWROC.bat, krótką instrukcję TXT/HTML i katalog programu na wierzchu. START po adresie i zgodzie TAK robi pełną kopię, wczytuje BAZĘ oddzielnym narzędziem, weryfikuje 693 węzły i wyłącza solo, a dopiero potem uruchamia mostek z NVDA i WinMM. PRZYWROC odtwarza ostatnią kopię sprzed BAZY. Brak NVDA uruchamia istniejący fallback konsolowy. To próba poza emisją, z odłączonymi lub ściszonymi wyjściami; BAZA włącza phantom na wejściu 9.

Transport, ograniczenia, źródła i sposób cichego odbioru: [dokumentacja/prosty-start.md](prosty-start.md). W szczególności zapis to typowane SET zgodne bajtowo z pomiarem AOSC, nie niepotwierdzony tekstowy adres `/` z pierwotnej specyfikacji. Zapora mostka i jej zakaz scen/akcji pozostają bez zmian. Zaawansowane narzędzia i dawna instrukcja są w program/dodatki.

## Jak działa rozmowa: CUE i suwak

Telefon (pasek 2) i Zoom (pasek 3) mają trzy stany. Mostek wylicza je z odczytu MR18, nie z pamięci.

1. Czeka. CUE wyłączone, suwak na dole. Rozmówca słyszy całą antenę bez siebie, na właściwej głośności: muzykę, mikrofon, gdy jest na antenie, i drugiego rozmówcę, gdy jest na antenie. Słyszy to samo co antena, także ściszanie muzyki suwakiem pod głos.
2. Rozmowa poza anteną. CUE włączone (przycisk SELECT paska). Rozmówca słyszy mikrofon i każdego innego rozmówcę z CUE na pełnym poziomie, a pod spodem muzykę ciszej (o 15 dB, wartość w pliku ustawień). Nie słyszy rozmówcy, który jest na antenie bez CUE. Antena nie słyszy nikogo z rozmowy.
3. Na antenie. CUE wyłączone, suwak podniesiony. Rozmówca jest w programie i słyszy antenę bez siebie.

Co robią przyciski i suwak:

1. SELECT przy czekającym rozmówcy: rozmowa poza anteną.
2. Drugie SELECT: rozmówca wraca do oczekiwania i słyszy antenę.
3. Podniesienie suwaka czekającego rozmówcy: wejście na antenę. Ściągnięcie suwaka na dół: znowu czeka.
4. Podniesienie suwaka rozmówcy, który ma CUE: koniec jego CUE i wejście na antenę, jak „Auto CUE Reset by FADER” w konsoletach D&R. Mostek najpierw zamyka drogi rozmowy do jego powrotu (mikrofon i uczestników przed suwakiem), potem włącza mu powrót programu, a na końcu Main On. Inni uczestnicy CUE zostają w rozmowie poza anteną. NVDA: „Słuchacz na antenie” albo „Zoom na antenie”. F1 albo SELECT mikrofonu może zakończyć również pozostałe CUE i włączyć mikrofon na antenę. Liczy się podniesienie suwaka z dołu: suwak poniżej progu minus 50 dB nie kończy CUE.
5. SELECT przy rozmówcy na antenie: mostek najpierw zdejmuje go z sumy i sprawdza to odczytem, potem silnik ściąga suwak. Rozmówca dołącza do rozmowy poza anteną. Po zwolnieniu CUE czeka; na antenę wraca dopiero ponownym podniesieniem suwaka.
6. Gdy trzymasz suwak ręką i silnik nie może go ściągnąć, kanał zostaje poza sumą. NVDA mówi wtedy „Suwak trzymany, kanał poza sumą do ściągnięcia suwaka”. Ruch trzymanego suwaka w górze nie kończy CUE. Dopiero zejście suwaka na dół i ponowne podniesienie wpuszcza rozmówcę na antenę.
7. SELECT przy obu rozmówcach: rozmowa we troje poza anteną.
8. F3 „Koniec rozmowy”: zwalnia wszystkie CUE naraz. Rozmówcy wracają do oczekiwania.

### Mikrofon: suwak i Fader Start

Mikrofon nie ma osobnego CUE. Jest w każdej rozmowie poza anteną, przed suwakiem.

1. Suwak paska 1 na samym dole oznacza mikrofon poza anteną. Pierwszy krok nad dołem włącza antenę, bez progu minus 50 dB. Głośność rośnie według skali suwaka do `zrodla.mikrofon.suwak_maks_db`, domyślnie plus 10 dB. Kolejne ruchy nad dołem zmieniają tylko głośność, bez komunikatów. Decyzja następuje po ustaniu ruchu i potwierdzeniu, z dotychczasową zwłoką suwaków.
2. Podniesienie mikrofonu kończy wszystkie CUE i trzymany talkback. Najpierw mostek zamyka drogi rozmowy i wycisza głośniki, potwierdza zamknięcia, dopiero potem ustawia dodatni fader, włącza Main On mikrofonu i powroty programu. Rozmówcy z CUE wracają do oczekiwania. Samo puszczenie MUTE po przerwanym talkbacku niczego już nie odtwarza.
3. F1 i SELECT paska 1 robią to samo: mikrofon poza anteną oznacza silnik na samą górę i wejście na antenę, także przy CUE. Mikrofon na antenie oznacza wyłączenie Main On i silnik na sam dół. NIEZNANY oznacza wyłącznie próbę zamknięcia i zjazdu na dół, nigdy otwarcie.
4. Silnik nie walczy z ręką. F1 zmienia fader w MR18 także przy dotyku; po puszczeniu nieruchomej ręki silnik dogania potwierdzoną pozycję. Nowy ruch ręki po F1 jest nową decyzją, a ruch oczekujący sprzed F1 przepada. Echo silnika bez dotyku nie jest ruchem ręki.
5. Zejście na dół zamyka mikrofon. Mute-Act może potem odciszyć głośniki zgodnie ze swoimi warunkami. Nieudane wejście na antenę powoduje zamknięcie mikrofonu i próbę powrotu suwaka na dół. Brak potwierdzenia miksera nie jest ogłaszany jako sukces.
6. SELECT rozmówcy przy mikrofonie na antenie: najpierw zdjęcie mikrofonu z anteny, potem fader mikrofonu na dół i otwarcie rozmowy. NVDA: „Mikrofon poza anteną, rozmowa ze słuchaczem” albo „Mikrofon poza anteną, rozmowa z Zoomem”. Poziom rozmowy przy mikrofonie na dole jest taki jak przy pełnej górze, z limitem wysyłki plus 10 dB.
7. Stan ogłasza się zgodnie z F4, a F5 powtarza go mową: „Mikrofon włączony” albo „Mikrofon wyłączony”. Gdy wejście na antenę kończy rozmowę CUE albo talkback: „Mikrofon włączony, koniec rozmowy”. Nie dochodzi nowy dźwięk; najpierw są dźwięki stanów rozmówców, potem mikrofonu, w jednej kolejce opisanej niżej.
8. Obca zmiana fadera, np. z AOSC, nie uruchamia Fader Start i nie jest cofana. Podniesienie przy Main Off nie włącza anteny; dół przy Main On oznacza cichy mikrofon, ale nie zmienia Main On ani Hold. Mostek mówi odczytany stan i pozycję, np. „Mikrofon włączony, suwak na dole z innego urządzenia”. Pierwszy świadomy ruch ręki lub F1 rozstrzyga stan.
9. Start i powrót łączności nie ustawiają mikrofonu automatycznie. Niespójność Main On i fadera jest ogłaszana raz po pełnym odczycie, np. „Mikrofon włączony, suwak na dole” albo „Mikrofon wyłączony, suwak w górze”.

SELECT na paskach muzyki to tylko odsłuch kontrolny dla Ciebie w słuchawkach. Nie trafia do rozmówców.

Muzyka: w scenie BAZA wszystkie trzy pary muzyki mają Main On stale włączone, a o tym, co gra na antenie, decyduje suwak. Wysyłki muzyki do rozmówców idą za anteną same. Parę muzyki bez Main On mostek zgłasza w dzienniku, bez blokowania pracy.

Głośniki grają mono z szyny Bus 6 (wyjście AUX 6). Są wyciszone, gdy mikrofon jest na antenie, w trakcie kaszlu i przy każdym CUE rozmówcy. Włączenie głośników jest wtedy odrzucane. Jeśli masz dwa głośniki, sygnał z AUX 6 trzeba rozdzielić na oba (rozgałęźnik albo wejście mono w głośniku).

Głośniki włączają się same, jak Mute-Act w konsoletach D&R: po wyłączeniu mikrofonu i po końcu rozmowy poza anteną, czyli po zwolnieniu ostatniego CUE (F3, SELECT albo podniesienie suwaka rozmówcy z CUE). Mostek robi to dopiero wtedy, gdy odczyt z miksera potwierdzi, że mikrofon nie ma żadnego otwartego toru i nie trwa żadne CUE. Nigdy w trakcie kaszlu ani talkbacku, przy stanie nieznanym, przy niezgodnym profilu miksera ani przy odłączonym kontrolerze. Klawisz „Głośniki włącz” podlega tym samym warunkom i NVDA mówi powód odmowy: „Głośniki nie włączone, profil miksera niezgodny”, „Głośniki nie włączone, stan nieznany” albo „Głośniki nie włączone, mikrofon ma otwarty tor”. NVDA dopisuje wtedy do komunikatu „Głośniki włączone”, na przykład „Mikrofon wyłączony. Głośniki włączone”. Gdy nie chcesz tego, ustaw `odciszaj_glosniki_po_wylaczeniu_mikrofonu` na `false` w ustawieniach; głośniki czekają wtedy na klawisz „Głośniki włącz”.

Podsłuch telefonu w prawym uchu (Bus 2) gra, gdy słuchacz czeka. Przy CUE telefonu i przy telefonie na antenie mostek go wyłącza, bo telefon jest wtedy w obu uszach.

W słuchawkach przy CUE: mostek włącza odsłuch kontrolny mikrofonu i rozmówców z CUE oraz przycisza program o 10 dB (funkcja MR18). Po zwolnieniu ostatniego CUE odsłuch kontrolny znika, a program wraca do pełnego poziomu.

## Kaszel i talkback

Decyzja Michała z 25.10.2026. MUTE paska 1 to kaszel, MUTE paska 2 to talkback do telefonu, a MUTE paska 3 do Zooma. Wszystkie działają przez cały czas trzymania, bez limitu. Dawny `kaszel_maks_s`, także 30.0 w starym pliku, jest ignorowany.

### Kaszel

1. Przytrzymanie zamyka Main On mikrofonu, jego wysyłki do telefonu i Zooma oraz klucz Bus 5. Działa na antenie i w rozmowie poza anteną.
2. Puszczenie odtwarza odczytane przed wciśnięciem poziomy i punkty pobrania wysyłek oraz Main On mikrofonu, tylko gdy zapora na to pozwala. Gdy mikrofon nie ma ani otwartej drogi, ani solo w słuchawkach, kaszel nic nie robi i nie odzywa się.
3. W trakcie kaszlu NVDA milczy, także alarm ciszy czeka do puszczenia. Kaszel nie zmienia głośników: przy prawidłowej antenie i CUE są już wyciszone. Zapora i tak sprawdza wyciszenie: gdy ktoś odciszył głośniki z innego urządzenia, mikrofon nie wraca i NVDA mówi „Mikrofon nie włączony, głośniki niewyciszone, mikrofon zamknięty”.
4. Restart albo odłączenie X-TOUCH, utrata łączności z mikserem, stan nieznany i wykryta obca zmiana unieważniają powrót. Mostek zamyka drogi mikrofonu i mówi „Kaszel przerwany, mikrofon poza anteną”, a bez potwierdzenia „Kaszel przerwany, zamknięcie mikrofonu niepotwierdzone”. Przy niedostępnym mikserze zamknięcia są ponawiane po odczycie przy powrocie łączności. Spóźnione puszczenie niczego nie otwiera. Nie ma ochrony czasowej przed samym zgubieniem komunikatu puszczenia bez utraty urządzenia.
5. CUE w trakcie kaszlu zmienia rozmowę, ale mikrofon pozostaje zamknięty do puszczenia. Puszczenie nie wpuszcza go wtedy na antenę. Przełącznik mikrofonu (F1 albo SELECT paska 1) w trakcie kaszlu wyłącza mikrofon na dobre. Podniesienie lub korekta suwaka pod kaszlem nie otwiera anteny. Zejście na dół unieważnia powrót; późniejsze podniesienie pod nadal trzymanym MUTE też nie otwiera anteny. Po puszczeniu potrzebny jest nowy ruch ręki lub F1.
6. Status w trakcie kaszlu: „Mikrofon poza anteną na czas kaszlu”. Po kaszlu licznik mikrofonu na antenie zaczyna od nowa, od ponownego potwierdzenia Main On (decyzja Michała z 18.10.2026).

7. Kaszel zdejmuje też solo mikrofonu ze słuchawek: w CUE nadal słyszysz rozmówcę i muzykę, ale nie siebie. Po potwierdzonym przywróceniu wysyłek wraca dokładny stan solo sprzed naciśnięcia. Dotyczy to również PFL mikrofonu i kaszlu podczas talkbacku. Sam talkback nie zmienia solo. Przy mikrofonie na antenie bez solo nie ma dodatkowych zapisów odsłuchu.
8. Kaszel zdejmuje solo mikrofonu także wtedy, gdy jest ono jedynym solo. PHONES przechodzą wtedy na program/Main LR, zgodnie z decyzją Michała „niech też znika”. Po puszczeniu wraca wcześniejsze solo na zwykłych zasadach migawki. Mostek nie włącza zastępczego solo, nie przestawia źródła monitora i nie zmienia z tego powodu Main LR, wysyłek ani Bus 6.
9. Po przerwaniu kaszlu, np. przez F1 albo utratę X-TOUCH, solo może wrócić, ponieważ nie wysyła głosu na antenę. Wymaga to znanego stanu i świeżego odczytu odsłuchu; przy utracie miksera lub stanie nieznanym powrót przepada, również po ponownym połączeniu. Wykryta obca zmiana solo i jawne polecenie odsłuchu na stole wygrywają z migawką: kaszel nie cofa ich po puszczeniu. Błąd potwierdzenia zdjęcia lub powrotu solo daje istniejące „Odsłuch niepotwierdzony”. Udany kaszel pozostaje bez mowy i dźwięków.

### Talkback

1. Przytrzymaj MUTE 2 albo MUTE 3. Mikrofon słychać tylko u adresata, przed suwakiem. Poziom jest ten sam co w rozmowie na CUE: poziom bazowy z `poziomy_bazowe.json` powiększony o decybele suwaka mikrofonu, najwyżej do plus 10 dB (sterowanie tym samym ustawieniem `mikrofon_w_rozmowie_jak_na_antenie`; przy suwaku na dole albo nieznanym korekta wynosi `suwak_maks_db`, a przy `false` zostaje sam poziom bazowy). Dzięki temu rozmówca słyszy Cię na talkbacku tak samo głośno jak na antenie i w CUE. Brak prawidłowego poziomu powoduje odmowę, bez zgadywania. Suwak mikrofonu nie jest przy tym ruszany, a korekta liczy się z jego pozycji sprzed talkbacku.
2. Muzyka, która jest na antenie, cichnie na ten czas w powrocie adresata o `przyciszenie_muzyki_cue_db`, dokładnie jak przy CUE. Rozmówca słyszy po tym, że mówisz tylko do niego. Przyciszenie dostaje wyłącznie adresat talkbacku: program drugiego rozmówcy i głosy innych rozmówców na antenie zostają bez zmian, a adresat, który i tak ma CUE, nic nie zmienia, bo jego muzyka jest już przyciszona. Muzyka cichnie przed otwarciem mikrofonu, nie po nim, i w trakcie podąża za anteną: utwór wchodzący z SARY dostaje od razu przyciszony poziom, a schodzący jest zamykany. Ustawienie `przyciszenie_muzyki_talkback` na `false` wyłącza tę część i zostawia dawne zachowanie.
3. Mikrofon znika na ten czas z anteny, od drugiego rozmówcy i z klucza Bus 5. Nie przycisza telefonu. Main On, suwaki i CUE rozmówców, PFL i podsłuch telefonu pozostają bez zmian.
4. Jeśli głośniki grają, talkback najpierw wycisza Bus 6 i potwierdza ciszę odczytem. Dopiero wtedy otwiera mikrofon. Po puszczeniu ostatniego przycisku i kaszlu najpierw przywraca mikrofon, a następnie głośniki, ale tylko gdy wcześniej grały i wyciszył je talkback. Powrót głośników wymaga potwierdzonego braku otwartego toru mikrofonu, CUE i blokady profilu. Wcześniej wyciszonych głośników talkback nie rusza. Ten powrót działa także przy Mute-Act wyłączonym; Mute-Act nie dubluje go.
5. Przytrzymanie obu MUTE pozwala mówić do telefonu i Zooma. Puszczenie jednego pozostawia drugiego i przywraca muzykę tylko jemu, a puszczenie ostatniego oddaje stan mikrofonu sprzed pierwszego wciśnięcia, przez zaporę. Muzyka wraca do poziomu, który daje zwykły cel dla bieżącego stanu anteny, z potwierdzeniem odczytem.
6. Kaszel ma pierwszeństwo. MUTE 1 zamyka mikrofon wszystkim, także podczas talkbacku, ale przyciszenia muzyki nie zdejmuje: zostaje ono do puszczenia samego talkbacku. Puszczenie MUTE 1 wraca do nadal trzymanych adresatów. Jeśli MUTE 2 i 3 puszczono wcześniej, po końcu kaszlu wraca stan sprzed całego trzymania.
7. Podniesienie suwaka mikrofonu albo F1 kończy talkback i wprowadza mikrofon na antenę po potwierdzeniu zamknięć. Głośniki pozostają wtedy wyciszone, a stare puszczenia MUTE niczego nie odtwarzają. Kaszel nadal ma pierwszeństwo. Zmiana CUE lub suwaka rozmówcy na stole jest nową świadomą decyzją: stan rozmówcy zmienia się jak zwykle, ale mikrofon pozostaje tylko u adresatów talkbacku, a w kaszlu jest zamknięty. Po puszczeniu nie wraca dawne Main On mikrofonu. Obca zmiana toru mikrofonu, Main On albo suwaka rozmówcy, utrata urządzenia przerywa chwilowe działanie i zamyka mikrofon bez odtwarzania migawki. Przyciszoną wysyłkę muzyki chroni ta sama zasada: zmiana z innego urządzenia (AOSC) przerywa talkback, a jej wartości mostek nie cofa i nie odtwarza. Po każdym innym przerwaniu — odmowie, utracie X-TOUCH, utracie miksera, niepotwierdzonym zamknięciu — muzyka albo wraca do zwykłego celu, albo zostaje przyciszona, nigdy głośniej niż przed talkbackiem; po powrocie łączności mostek nie otwiera niczego ponad zwykły cel. Po przerwaniu talkbacku głośniki zostają wyciszone. Świadomy klawisz głośników unieważnia późniejsze automatyczne przywrócenie, także ponowne „Głośniki wyłącz”. Wykryte odciszenie z AOSC przerywa talkback i wywołuje ochronne zamknięcie mikrofonu oraz głośników.
8. Udany talkback nie wywołuje mowy ani dodatkowego sygnału głośników. Automatyczne wyciszenie i przywrócenie Bus 6 pozostaje ciche; odmowa przywrócenia jest mówiona z powodem. Po potwierdzeniu otwarcia do adresata grają dwa krótkie tony w górę (`talkback_start.wav`), także po dołożeniu drugiego adresata. Po puszczeniu i potwierdzeniu przywrócenia grają dwa tony w dół (`talkback_koniec.wav`), również po puszczeniu jednego z dwóch przycisków. Każdy sygnał trwa 0,17 s. Grają w każdym trybie, także samej mowy. Brak pliku lub błąd odtwarzania oznacza ciszę i wpis w dzienniku, nigdy zastępczą mowę. Kaszel pozostaje bez mowy i dźwięków. Przytrzymany kaszel blokuje start sygnału talkbacku, bo adresat jeszcze nie słyszy mikrofonu; puszczenie kaszlu również pozostaje ciche. F2 i gałka mikrofonu nadal podają stan na żądanie, np. „Mikrofon do telefonu na czas talkbacku”. Dioda MUTE każdego trzymanego adresata świeci również wtedy, gdy kaszel chwilowo blokuje jego mikrofon. Ostrzeżenia bezpieczeństwa nie są wyciszane.

Odsłuch obu plików talkbacku zaakceptowany przez Michała 25.10.2026. Pliki i generator nie zostały zmienione przy dodawaniu automatu głośników. Gdy mikser nie potwierdza zamknięcia mikrofonu lub wyciszenia głośników, komunikat nie obiecuje ciszy. Po odzyskaniu połączenia ponawiane są tylko ochronne zamknięcia.

To nie jest zmiana trybu CUE. Mostek zachowuje jego stan logiczny podczas chwilowego przejęcia wysyłek mikrofonu. Nie można normalnie mieć jednocześnie mikrofonu na antenie i Zooma na CUE: dotychczasowy zakaz pozostaje. Gdy zapora odmawia powrotu, mikrofon nie wraca na antenę.

## Liczniki czasu

Mostek liczy czas od chwili potwierdzonej odczytem zmiany stanu: mikrofonu na antenie oraz każdego rozmówcy, który czeka, rozmawia na CUE albo jest na antenie. F2 i wciśnięcie gałki paska podają czas z polską odmianą, na przykład „Mikrofon na antenie od 2 minut 10 sekund. Słuchacz czeka od 40 sekund” albo „Słuchacz w rozmowie poza anteną od 1 minuty 5 sekund”. Przez pierwszą sekundę i po starcie albo powrocie łączności (gdy nie wiadomo, od kiedy stan trwa) status mówi sam stan, bez czasu.

Licznik mikrofonu podaje czas nieprzerwanego stanu antenowego: po kaszlu liczy od nowa. Gdy stan zmienił się z innego urządzenia i mostek zobaczył to dopiero przy F2, nowy stan nie dostaje czasu poprzedniego: status mówi sam stan („Słuchacz na antenie”), a czas liczy od tego odczytu.

Liczniki nie mówią same. Przypomnienie co kilka minut mikrofonu na antenie włącza się w ustawieniach: `przypomnienie_mikrofonu_min` w `ustawienia/stanowisko.json`, domyślnie 0, czyli wyłączone. Przy wartości 5 NVDA mówi „Mikrofon na antenie od 5 minut”, potem „od 10 minut” i tak dalej.

## Alarm ciszy na antenie

Mostek subskrybuje mierniki MR18 (`/meters/5`, wszystkie wyjścia) i patrzy na sumę Main LR. Gdy suma jest poniżej minus 50 dBFS dłużej niż 10 sekund, NVDA mówi „Cisza na antenie” i powtarza to co 30 sekund, dopóki cisza trwa. Gdy dźwięk wróci, NVDA mówi raz „Dźwięk na antenie wrócił”. Mostek nie startuje sam żadnego utworu. Próg, czas i przerwa są w ustawieniach (`zachowanie`, `alarm_ciszy`), tam też alarm można wyłączyć.

Brak danych z mierników to nie cisza. Gdy mierniki nie przychodzą dłużej niż 2 sekundy, NVDA mówi raz „Mierniki niedostępne, alarm ciszy nie działa”, a status F2 kończy się tym zdaniem. Alarmu ciszy wtedy nie ma. Po powrocie danych: „Mierniki dostępne”.

Alarm mierzy sumę miksera, nie stream. Ciszy za RadioCasterem nie wykryje.

Wyłączenie na chwilę (decyzja Michała z 21.10.2026): REC paska 1 albo polecenie `alarm` w oknie mostka. NVDA mówi „Alarm ciszy wyłączony” albo „Alarm ciszy włączony”, dioda REC świeci przy włączonym. Status F2 przy wyłączonym kończy się zdaniem „Alarm ciszy wyłączony”. Po ponownym włączeniu cisza liczy się od nowa. Przełącznik nie zapisuje pliku: po starcie obowiązuje `zachowanie.alarm_ciszy.wlaczony` z ustawień.

## Przyciszanie słuchacza

Słuchacz (telefon, kanał 10) jest ściszany, gdy mówisz Ty albo Zoom, ale tylko wtedy, gdy jesteście w tej samej rozmowie. Robi to wbudowany kompresor kanału 10 kluczowany szyną Bus 5 „KLUCZ PRZYCISZANIA”. Mostek przełącza wyłącznie wysyłki do Bus 5, razem z każdym przejściem (najpierw zamknięcia, potem otwarcia):

1. Mikrofon (kanał 9) jest w kluczu, gdy mikrofon i słuchacz są na antenie albo gdy słuchacz ma CUE, z wyjątkiem trwającego kaszlu lub talkbacku.
2. Zoom (kanały 7 i 8) jest w kluczu, gdy Zoom i słuchacz są na antenie albo gdy oboje mają CUE.
3. W każdym innym stanie wysyłki do Bus 5 są wyłączone. Głos Zooma nie jest ściszany przez mikrofon.

W sytuacjach z planu: A i B klucz pusty, C, D i E tylko mikrofon, F i G mikrofon i Zoom.

Bus 5 nie ma żadnego wyjścia: nie idzie na Main LR, nie jest źródłem USB, nie ma linku z Bus 6 i nie wraca do rozmówców. Ustawienia samego przyciszacza (kompresor kanału 10 z kluczem Bus 5, Combinatory w slotach FX, master Bus 5 na poziomie nominalnym) są w scenie BAZA i ustawiasz je w AOSC. Mostek ich nie zmienia i nie zapisuje. Odczytuje je przy pełnym odczycie i zgłasza niezgodność w dzienniku bez blokowania pracy, na przykład „kanał 10: klucz kompresora nie jest z Bus 5”. Blokuje otwieranie, gdy Bus 5 trafia na Main LR, na USB albo ma link z głośnikami.

Mostek czyta wszystkie wejścia Bus 5: wysyłki kanałów 1 do 16 oraz powrotów AUX i efektów 1 do 4. Wysyłka do Bus 5 z czegokolwiek poza mikrofonem i Zoomem (muzyka, telefon, kanał rezerwowy, powrót) to niezgodność blokująca. Mostek sam ją zamyka i mówi na przykład „Ochronne zamknięcie: zamknięta wysyłka do klucza przyciszania: kanał 11”.

## Informacja zwrotna: mowa, dźwięki, dźwięki z mową (F4, F5)

Decyzja Michała z 17.10.2026. Dźwięki dają szybszą informację o zmianie stanu niż mowa. Nie zastępują ostrzeżeń.

Trzy tryby:

1. Mowa: komunikaty mową. Wyjątkiem są sygnały potwierdzonego talkbacku: zawsze same dźwięki, bez mowy.
2. Dźwięki: komunikat zmiany stanu, który ma dźwięk, brzmi tylko dźwiękiem. Wszystko inne nadal mową.
3. Dźwięki z mową (domyślny): dźwięk, a zaraz po nim mowa.

F4 przełącza tryb po kolei: mowa, dźwięki, dźwięki z mową, znowu mowa. Nowy tryb jest zawsze ogłaszany mową, bez dźwięku: „Tryb: mowa”, „Tryb: dźwięki”, „Tryb: dźwięki z mową”. Tryb zapisuje się w `ustawienia/tryb_informacji.json` (zapis atomowy, plik poza repozytorium), więc przeżywa restart. Uszkodzony albo nieznany wpis daje tryb domyślny i jedno ostrzeżenie w dzienniku. Gdy zapis się nie uda, NVDA dodaje „Trybu nie zapisano, po restarcie wróci poprzedni”.

F5 powtarza mową ostatni komunikat stanu, także taki, który w trybie dźwięków zabrzmiał tylko dźwiękiem. Powtarza też ostatnie ostrzeżenie albo odmowę. Gdy nic jeszcze nie padło: „Brak komunikatu do powtórzenia”. F5 nie czyta miksera i niczego nie zapisuje; F4 też nie. Oba działają także przy stanie nieznanym. F5 nie powtarza komunikatów informacyjnych (np. „Klawisz wolny”), samego F4 ani „Czekam na mikser”.

Zdarzenia z dźwiękiem (mapowanie w `ustawienia/stanowisko.json`, sekcja `informacja_zwrotna.zdarzenia`, pliki w `dzwieki/`):

1. Mikrofon włączony: `mikrofon_na_antenie`. Mikrofon wyłączony: `mikrofon_poza_antena`.
2. Rozmowa poza anteną ze słuchaczem albo słuchacz w rozmowie: `sluchacz_cue`. Z Zoomem: `zoom_cue`. Gdy mikrofon schodzi przy tym z anteny: najpierw `mikrofon_poza_antena`, potem dźwięk rozmowy.
3. Słuchacz czeka: `sluchacz_czeka`, słuchacz na antenie: `sluchacz_na_antenie`. Zoom czeka: `zoom_czeka`, Zoom na antenie: `zoom_na_antenie`.
4. Koniec rozmowy (F3): dźwięki stanu każdego rozmówcy, sam „Koniec rozmowy” bez osobnego dźwięku.
5. Głośniki włączone: `glosniki_graja`, wyciszone: `glosniki_wyciszone`. Mute-Act po wyłączeniu mikrofonu dokłada `glosniki_graja`.
6. Program emisyjny: „Gra” `odtwarzacz_start`, „Zatrzymane” `odtwarzacz_stop`.
7. Czekam na mikser: `czekam_na_mikser`.
8. Odmowy, dźwięk `odmowa` i zawsze mowa z powodem: mikrofon nie włączony, głośniki nie włączone (każdy powód), kontroler odłączony przy otwieraniu, granica wzmocnienia.
9. Każdy inny komunikat bezpieczeństwa: dźwięk `alarm` i zawsze mowa. Dobre wiadomości o priorytecie bezpieczeństwa (łączność przywrócona, kontroler podłączony, profil zgodny) mają tylko mowę.

Komunikaty zawsze mówione, w każdym trybie: wszystkie ostrzeżenia i odmowy (z powodem), liczby i liczniki („od 2 minut”), status F2 i status paska (wciśnięcie gałki), gałka („Telefon, wzmocnienie plus 1”), utrata i powrót kontrolera, profil niezgodny i zgodny, ochronne zamknięcia, zmiany z innego urządzenia, stan nieznany i utrata łączności, przejście niepełne albo przerwane, kaszel, alarm ciszy i mierniki, suwak trzymany i rozmówca poza sumą, błędy programu emisyjnego, F4 i F5, komunikaty informacyjne (wolne przyciski i klawisze). Komunikat bez odpowiednika dźwięku zawsze idzie mową.

Jak to jest pilnowane: lista komunikatów, które mogą zabrzmieć samym dźwiękiem, jest w kodzie (`mostek/informacja.py`, `KOMUNIKATY_DZWIEKIEM`), nie w ustawieniach. Przypisanie dźwięku ostrzeżeniu w ustawieniach dokłada dźwięk, ale nie zabiera mowy. Komunikat złożony z kilku części (np. „Rozmowa poza anteną ze słuchaczem. Suwak trzymany…”) traci mowę tylko wtedy, gdy każda część jest stanem z dźwiękiem. Test `test_kazdy_klucz_bezpieczenstwa_zawsze_z_mowa` przechodzi przez wszystkie klucze komunikatów w każdym priorytecie, z dźwiękiem przypisanym każdemu kluczowi, i dowodzi, że żaden komunikat bezpieczeństwa nie traci mowy.

Odtwarzanie: w Windows `winsound.PlaySound` z plikiem, asynchronicznie (`SND_ASYNC`, bez dźwięku domyślnego systemu), przez kartę domyślną, nigdy przez MR18. Pętla mostka nie czeka na dźwięk: dźwięki gra wątek kolejki mowy. Poza Windows i w testach atrapa zapisuje listę odtworzonych kluczy (konsola symulatora wypisuje `[dzwiek] klucz`). Brak pliku WAV albo błąd odtwarzania: mowa zamiast dźwięku i jedno ostrzeżenie w dzienniku na dźwięk; mostek działa dalej. Wyjątek: sygnały talkbacku po błędzie pozostają bez mowy. Powtarzalny generator: `python3 narzedzia/generuj_talkback.py` sprawdza pliki, `--zapisz` odtwarza tylko dwa WAV talkbacku.

### Kolejność dźwięku i mowy

1. Mowa komunikatu rusza razem z jego pierwszym dźwiękiem, bez czekania na koniec dźwięku (decyzja Michała z 20.10.2026: w radiu reakcja ma być natychmiastowa). Dźwięk i mowa tego samego zdarzenia mogą się nakładać. Każdy nowy komunikat ucina dźwięki komunikatu, którego mowa już poszła. Komunikat samym dźwiękiem (tryb dźwięków) gra do końca swojego czasu z `dzwieki.json`, jak wcześniej.
2. Komunikaty idą w kolejności priorytetu, jak wcześniej: bezpieczeństwo, stan, informacja. Nowszy komunikat o tym samym kluczu zastępuje stary, który jeszcze nie padł, razem z jego dźwiękami.
3. Ostrzeżenie o wyższym priorytecie przerywa trwający dźwięk komunikatu stanu (dźwięk jest zatrzymany), mówi się od razu, a przerwany komunikat wraca do kolejki za nim i zabrzmi od przerwanego dźwięku. Gdy w tym czasie przyszedł nowszy komunikat o tym samym kluczu, stary przepada, bo jest nieaktualny.
4. Mowa, która już trafiła do NVDA, nie jest przerywana, tak jak przed wprowadzeniem trybów.

## Co mówi NVDA

Mostek mówi stan odczytany z miksera, nigdy stan, który dopiero wysłał. Najważniejsze komunikaty (wszystkie są w `ustawienia/stanowisko.json` i można zmienić ich brzmienie bez zmiany kodu):

1. Mikrofon: „Mikrofon włączony”, „Mikrofon wyłączony”, „Mikrofon włączony, suwak na dole”, „Mikrofon nie włączony, głośniki niewyciszone, mikrofon zamknięty”, „Uwaga, mikrofon może być włączony”, „Stan był nieznany, wyłączam mikrofon”.
2. Rozmowa: „Rozmowa poza anteną ze słuchaczem”, „Rozmowa poza anteną z Zoomem”, „Rozmowa poza anteną ze słuchaczem i Zoomem”, „Mikrofon poza anteną, rozmowa ze słuchaczem”.
3. Rozmówcy: „Słuchacz czeka”, „Słuchacz na antenie”, „Słuchacz w rozmowie poza anteną”, „Zoom czeka”, „Zoom na antenie”, „Zoom czeka poza sumą, ściągnij suwak na dół”.
4. F3: „Koniec rozmowy. Słuchacz czeka. Zoom czeka”, bez rozmowy: „Nie ma rozmowy poza anteną”.
5. Błąd przejścia: „Przejście niepełne, prywatność niepotwierdzona”, „Przejście przerwane, zmiana z innego urządzenia”, utrata łączności: „Brak łączności z mikserem, stan mikrofonu nieznany”.
6. Status F2, krótki i zawsze w tej samej kolejności: mikrofon, telefon, Zoom, głośniki, a na końcu tylko ostrzeżenia o niepewnym stanie (niezgodny profil miksera, odłączony kontroler, cisza na antenie, brak mierników). Na przykład „Mikrofon wyłączony. Słuchacz w rozmowie poza anteną. Zoom na antenie. Głośniki wyciszone.” Poziomy suwaków F2 nie podaje: daje je wciśnięcie gałki paska (decyzja Michała z 18.10.2026).
7. Wciśnięcie gałki: status jednego paska, na przykład „Słuchacz czeka, suwak na dole. Telefon, wzmocnienie zero”.
8. Wolne elementy: „Przycisk wolny” (SOLO wszędzie, MUTE na paskach muzyki), „Na antenę wchodzi się suwakiem” (REC poza paskiem mikrofonu), „Klawisz wolny” (Bank w prawo, strzałki lewo/prawo i FFWD poza trybem punktów miksu), „Suwak wolny”, „Pasek wolny”.
9. Zmiany z innego urządzenia: „Mikrofon włączony z innego urządzenia”, „Słuchacz na antenie z innego urządzenia”, „Wysyłka Zooma do telefonu włączona z innego urządzenia”.
10. Program emisyjny: „Gra”, „Zatrzymane”, „StationPlaylist nie odpowiada”, „Nie odpowiada żaden program emisyjny”, a gdy nie wybrano programu: „Nie wybrano programu emisyjnego”.
11. Kaszel: „Kaszel przerwany, mikrofon poza anteną”, „Kaszel niedostępny, stan mikrofonu nieznany”, w statusie „Mikrofon poza anteną na czas kaszlu”.
12. Mierniki: „Cisza na antenie”, „Dźwięk na antenie wrócił”, „Mierniki niedostępne, alarm ciszy nie działa”, „Mierniki dostępne”.
13. Liczniki: „Mikrofon na antenie od 2 minut 10 sekund”, „Słuchacz czeka od 40 sekund”.
14. Kontroler: „Kontroler odłączony, stół tylko zamyka tory”, „Kontroler podłączony, suwaki według miksera”, „Kontroler odłączony, otwieranie zablokowane”, „Mikrofon nie włączony, kontroler odłączony”. Po odłączeniu USB każde z dwóch pierwszych pada raz, mimo ponawiania otwarcia portu co 2 sekundy.
15. Ochronne zamknięcia: „Ochronne zamknięcie: szyna 3 zdjęta z Main LR, klucz przyciszania zamknięty”, „Uwaga, ochronne zamknięcie niepotwierdzone: …”, „Profil miksera zgodny, otwieranie odblokowane”.
16. F4 i F5: „Tryb: mowa”, „Tryb: dźwięki”, „Tryb: dźwięki z mową”, „Trybu nie zapisano, po restarcie wróci poprzedni”, „Brak komunikatu do powtórzenia”.

## Zasady, których mostek pilnuje

1. Mówi tylko to, co mikser potwierdził odczytem. Wysłany pakiet to jeszcze nie stan.
2. Na starcie i po utracie łączności wszystko jest NIEZNANE. Start tylko czyta mikser i niczego nie otwiera. Powrót łączności też. Odczyt torów krytycznych starszy niż sekunda (`limit_swiezosci_s` w ustawieniach) to także stan NIEZNANY: każde otwarcie najpierw czyta mikser jeszcze raz, a gdy odczyt nie przyjdzie, otwarcie jest odrzucone. Zamknięcia działają zawsze.
3. Przełącznik wysyła jawną wartość przeciwną do ostatniego potwierdzonego odczytu, nigdy „odwróć”. Przy stanie NIEZNANY przełącznik mikrofonu zawsze wyłącza, a CUE i F3 tylko zamykają rozmowę. Naciśnięcie w trakcie trwającej zmiany nie przełącza drugi raz, NVDA mówi „Czekam na mikser”. Zwolnienie przycisku i drganie styku nie robią nic.
4. Bramka anteny to Main On kanału (`/ch/NN/mix/lr`), nie Mute, a słyszalność zależy też od fadera. Suwak mikrofonu steruje Main On od pierwszego kroku nad dołem i wyłącza go na dole. Telefon i Zoom mają Main On stale włączone, o antenie decyduje suwak; mostek wyłącza ich Main On na czas CUE.
5. Każda zmiana rozmowy idzie w kolejności z rozdziału 7 planu: najpierw zamknięcia (Main On, głośniki, wysyłki do zamknięcia albo przyciszenia, podsłuch), dwa zgodne odczyty, ponowienie tylko brakujących zamknięć, potem otwarcia (rozmowa, program, Main On rozmówcy), znowu dwa zgodne odczyty, dopiero potem komunikat. Przy niepełnym przejściu mostek nie otwiera nowych dróg i nie wraca sam do dawnego stanu publicznego. Otwarcie, które się nie udało, zamyka to, co samo otworzyło.
6. Punkt pobrania wysyłki (przed albo za suwakiem) mostek zmienia tylko przy zamkniętej wysyłce, żeby przy zmianie nie było chwili, w której głos przechodzi niewłaściwą drogą.
7. Zapora sprawdza każdy zapis przed wysłaniem. Stałe niezmienniki: telefon nigdy w Bus 1, Zoom nigdy w Bus 3/4, do Bus 2 tylko telefon, mikrofon nigdy w głośnikach (Bus 6), żadnych wysyłek do efektów, żadna szyna na Main LR, otwarcie mikrofonu dopiero po potwierdzonym wyciszeniu głośników (także powrót po kaszlu), każde otwarcie zablokowane przy stanie NIEZNANY albo niezgodnym profilu miksera.
8. Niezmienniki klucza przyciszania: do Bus 5 trafia wyłącznie mikrofon i Zoom, przed suwakiem; Bus 5 nigdy na Main LR, nigdy źródłem USB, bez linku z Bus 6; wysyłka źródła do Bus 5 otwiera się tylko, gdy to źródło jest w tej samej rozmowie co słuchacz. Ustawień przyciszacza i mastera Bus 5 mostek nie zapisuje.
9. Niezmienniki rozmowy na CUE w zaporze: mikrofon nie może wejść na antenę, dopóki jakiekolwiek CUE nadal trwa. Fader Start najpierw kończy wszystkie CUE; rozmówca z CUE nie wchodzi na sumę; rozmówca bez CUE nie dostaje mikrofonu ani rozmówcy z CUE; rozmówca z CUE nie dostaje rozmówcy bez CUE; głos rozmówcy przed suwakiem tylko między uczestnikami CUE; muzyka do rozmowy na CUE najwyżej na poziomie bazowym minus przyciszenie; punkt pobrania tylko „przed suwakiem” albo „za suwakiem”, muzyka zawsze za suwakiem, zmiana punktu tylko przy zamkniętej wysyłce.
10. Zmiany z innego klienta (AOSC, M-AIR Edit) są ogłaszane, nie cofane. Zgłoszona zmiana anteny albo suwaka rozmówcy przestawia powroty za anteną, ale rozmowa poza anteną nigdy się przy tym nie otwiera. Zmiana routingu, linku, sceny albo przypisania szyny do Main LR unieważnia stan, przerywa trwające przejście i wymusza pełny odczyt. Nowy poziom włączonej wysyłki z AOSC staje się poziomem bazowym.
11. Ochronne zamknięcia (decyzja Michała z 18.10.2026): pełny odczyt, odczyt okresowy i status mogą wykonać wyłącznie zamknięcie niebezpiecznej drogi wykrytej w odczycie: szyny na Main LR, obcego wejścia klucza przyciszania oraz klucza przy niezgodnym profilu albo poza rozmową słuchacza. NVDA zawsze ostrzega. Odczyt nigdy niczego nie otwiera, nie przywraca sceny ani dawnych stanów. Status zgodnego miksera nie wykonuje żadnego zapisu. Blokada otwarć zostaje do pełnego odczytu zgodnego profilu; przy blokadzie F2 robi taki odczyt.
12. Utrata kontrolera (zamknięcie portu MIDI, restart albo odłączenie X-TOUCH) rozbraja stół. Po zgubieniu portu (MIM_CLOSE, wyjęty kabel USB) mostek sam ponawia otwarcie portu co 2 sekundy (`xtouch.ponowienie_portu_s`). Nieudane próby nie trafiają do mowy, a do dziennika tylko pierwsza. Gdy X-TOUCH nie ma przy starcie, mostek ponawia otwarcie tak samo. Co sekundę (`xtouch.zycie_s`) mostek wysyła do stołu zapytanie Mackie Control (`F0 00 00 66 14 00 F7`). X-TOUCH w trybie MC odpowiada numerem seryjnym. Dwa zapytania bez odpowiedzi (`xtouch.zycie_proby`) to utrata kontrolera i ponowne otwarcie portu, a powrót ogłasza dopiero pierwsza odpowiedź stołu. Powód, zmierzony 21.10.2026 na Windows 11: po wyłączeniu i włączeniu X-TOUCH Windows wystawia nowe urządzenie MIDI, a stary uchwyt milczy bez MIM_CLOSE, więc mostek słuchał martwego portu. Stół włączony w trybie innym niż MC nie odpowiada i nie jest ogłaszany jako podłączony. Spóźnione MIDI ze starego uchwytu portu nic nie robi. Do powrotu kontrolera przyciski, suwaki i gałki niczego nie otwierają, a wyłączenie mikrofonu, CUE przy rozmówcy w rozmowie i „Głośniki wyłącz” działają. Trwający kaszel kończy się z mikrofonem poza anteną. Powrót kontrolera: najpierw silniki i diody według odczytu, potem uzbrojenie; pierwszy komunikat MIDI po utracie tylko uzgadnia kontroler i sam nie jest wykonywany. W konsoli mostka powrót kontrolera to polecenie `kontroler`.
13. Zapora przyjmuje zapis wyłącznie na pełną ścieżkę z rejestru `mostek/sciezki.py` z zakresem kanałów i szyn. Adres, który tylko kończy się znajomo (np. `/obce/mix/lr` albo `/ch/17/mix/lr`), jest odrzucany regułą `sciezka_w_rejestrze`.

## Mapa stołu

Suwaki: 1 mikrofon (kanał 9), 2 telefon (10), 3 Zoom (7/8), 4 do 6 muzyka 1 do 3 (pary 1/2, 3/4, 5/6), 7 i 8 wolne, MASTER słuchawki (PHONES). Suwak w górze to 0 dB, czyli poziom ze sceny, na dole minus nieskończoność. Wyjątek: suwak mikrofonu sięga plus 10 dB, a 0 dB ma w trzech czwartych drogi (decyzja Michała z 21.10.2026, `zrodla.mikrofon.suwak_maks_db`). Suwak mikrofonu steruje anteną od pierwszego kroku nad samym dołem; pozostałe jego ruchy to głośność. Ruch silnika nie jest brany za ruch ręki: pozycja liczy się tylko przy dotkniętym suwaku. Rozmówca jest „na antenie”, gdy jego suwak jest powyżej minus 50 dB (próg w pliku ustawień).

Przyciski paska:

1. REC: na pasku mikrofonu przełącza alarm ciszy. Na paskach rozmówców i muzyki mówi „Na antenę wchodzi się suwakiem”.
2. MUTE: pasek 1 kaszel, pasek 2 talkback do telefonu, pasek 3 talkback do Zooma. Przytrzymanie bez limitu czasu. Na paskach muzyki wolny.
3. SOLO: wolny.
4. SELECT: na pasku mikrofonu Fader Start, tak jak F1: antena i suwak silnikiem na górę albo wyłączenie i dół. CUE na paskach telefonu i Zooma, odsłuch kontrolny na paskach muzyki.
5. Wciśnięcie gałki: status paska, z licznikiem czasu. Obrót gałki: wzmocnienie telefonu (`/headamp/10/gain`) i Zooma (`/ch/07` i `/ch/08` `/preamp/rtntrim`), 1 dB na ząbek, najwyżej 12 dB w górę albo w dół od wartości ze sceny, komunikat po pół sekundy bez ruchu.

Klawisze: F1 mikrofon, F2 status, F3 koniec rozmowy, F4 tryb informacji zwrotnej (mowa, dźwięki, dźwięki z mową), F5 powtórzenie ostatniego komunikatu, F6 co gra i ile zostało, F7 automat, F8 powierzchnia i odsłuch. MIDI TRACKS „słuchaj programu”, INPUTS „słuchaj rozmowy”, AUDIO TRACKS „koniec odsłuchu kontrolnego”, OUTPUTS „głośniki wyłącz”, USER „głośniki włącz”. Transport i kursor opisano poniżej. Pozostałe klawisze mówią „Funkcja techniczna niedostępna w emisji”.

## Sterowanie SPL Pro i SARĄ ze stołu

START/RESTART włącza obsługę playoutu z ustawień, bez dopisywania `--emisja`. Domyślnie `emisja.program` to `auto`, a `emisja.preferowany` to `StationPlaylist`. Można wybrać `StationPlaylist` albo `SARA`; opcja konsoli `--emisja auto|stationplaylist|sara` nadpisuje ustawienia, `--emisja brak` wyłącza playout. Samo uruchomienie mostka nie rozpoczyna muzyki. Klawisze playoutu nie odczytują ani nie zapisują MR18. Nie zmieniono dotychczasowego START: przy różnicy wobec BAZY nadal może ją wczytać, podczas gdy RESTART uruchamia tylko mostek.

StationPlaylist Studio Pro: View > Options > Communications > TCP/UDP, włącz TCP Server. Port ustaw na 443 (lub ten sam wolny port co `emisja.spl_port`), IP Restriction na `127.0.0.1`. Pole Send Response pozostaw puste. Nie włączaj UPnP ani przekierowania portu. To zwykły tekst TCP, nie HTTPS mimo numeru 443. Mostek łączy się tylko z `127.0.0.1`. Jeśli Studio wysyła metadane w ANSI, zamiast UTF-8 wybierz odpowiednie `emisja.spl_kodowanie`, np. `cp1250` dla polskiego Windows. Bez TCP pozostaje lokalny zapas SendMessage dla PLAY, STOP i stanu; bogatsze funkcje powiedzą, że trzeba włączyć TCP Server.

SARA: potrzebna jest wersja z nowym serwerem TCP (osobne zadanie w SARZE). W jej opcjach włącz „Enable local TCP control (127.0.0.1)” i ustaw „TCP control port” na 51443, tak samo jak `emisja.sara_port` w mostku. Zmiany zastosuj przyciskiem OK. W rozwijanej wersji `remote.enabled` jest domyślnie `true`, a `remote.port` to 51443; te nazwy sprawdzono w kodzie, nie w wydanym EXE. Nie zmieniaj zapory Windows. Ta karta testuje atrapę SARY, nie steruje uruchomioną emisją.

Mapa transportu (QSG X-TOUCH, pozycja 8; Ardour a9ea4a98). Pięć dużych klawiszy od lewej: REWIND 91 nauka klawiszy poza trybem punktów, FFWD 92 wolny poza trybem punktów, STOP 93 stop z wyciszeniem, PLAY 94 Play, RECORD 95 następny. Skrajny prawy jest najczęściej używanym NASTĘPNYM: wysyła Skip, a nazwę czyta z This po Stat. PLAY startuje podświetlony/następny utwór według programu. Drugi STOP w czasie `drugi_stop_w_ciagu_s` (1 s) wysyła Instant Stop. Położenie i numery wymagają potwierdzenia podsłuchem MIDI na egzemplarzu stołu.

Poza trybem punktów F6 (59) mówi bieżący utwór, pozostały czas i następny. F7 (60) przełącza automat, w SARZE automix, i ogłasza odczytany stan. Góra 96 i dół 97 przesuwają kursor playlisty. Jog CC 60 robi jeden krok na ząbek, bez lawiny mowy: opis końcowego utworu po 0,3 s bez ruchu. Strzałki lewo 98 i prawo 99 są wtedy wolne. Scrub 101 otwiera punkty miksu w SARZE; w tym trybie F6 czyta pozycję i wybrany punkt, a strzałki i kółko służą edycji. Pełna mapa: [punkty miksu](punkty-miksu.md).

Bank w lewo poza punktami miksu mówi „Odtwarzacz 2”, „Odtwarzacze 1 i 2”, „Odtwarzacze 1, 2 i 3” albo „Nic nie gra”. To numery odtwarzaczy głównej playlisty SARY, nie numery utworów ani odsłuch PFL. Odczyt nie czyta tytułu ani czasu, nie zmienia emisji i nie dodaje dźwięków. W trybie punktów Bank w lewo nadal wykonuje tylko MixSave, bez pytania o odtwarzacze. Bank w prawo poza punktami pozostaje wolny.

W StationPlaylist słychać „Numer odtwarzacza jest tylko w SARZE”, bez wysyłania Players. Przy jawnym wyborze SPL nie ma żadnego zapytania; automatyczny wybór może najpierw rozpoznać program przez Helo. Błędna odpowiedź SARY, także ERR ze starszej wersji, daje „SARA podała błędne numery odtwarzaczy”, a nie komunikat o zerwanym łączu. Brak wybranego programu, brak dostępnego programu i brak odpowiedzi podczas operacji zachowują istniejące komunikaty emisji. Robocze teksty SPL i błędu danych oraz opis nauki „Bank w lewo, w punktach miksu zapis, poza nimi odtwarzacz” wymagają akceptacji Michała przed wdrożeniem.

| Klawisz | MIDI | W punktach miksu | Poza punktami miksu |
| --- | --- | --- | --- |
| Bank w lewo | 46 / 0x2E | MixSave: zapisz punkty i wyjdź | Players: numery grających odtwarzaczy SARY |
| Bank w prawo | 47 / 0x2F | MixCancel: porzuć zmiany i wyjdź | „Klawisz wolny”, bez polecenia |
| Channel w lewo | 48 / 0x30 | Przełącz automat jak F7 | Przełącz automat jak F7 |
| Channel w prawo | 49 / 0x31 | Czas do końca utworu na antenie | Czas do końca utworu na antenie |
| OK (Zoom między strzałkami) | 100 / 0x64 | MixSet: ustaw wybrany punkt w bieżącej pozycji | Przełącz znacznik do emisji |

Save 80, Cancel 82, Marker 84 i F7 60 zostają bez zmian. Bank używa tych samych ścieżek zapisu i porzucenia, a OK tej samej ścieżki ustawienia punktu co Marker. OK nie zapisuje całego zestawu na dysku: zatwierdza bieżący punkt, mówiąc np. „Intro ustawione”. Zapis całego zestawu to Bank w lewo albo Save. Ruchy pozycji nadal nie mówią czasu.

Channel w lewo działa również podczas edycji, tak jak F7. Channel w prawo zawsze czyta antenę, nigdy odsłuch PFL: wyłącznie Stat i Rem, bez zmiany odtwarzania, kursora czy punktów. Przy graniu mówi np. „Zostało 1 minuta 23 sekundy”, przy stopie „Nic nie gra”, przy pauzie „Pauza”. Bez wybranego programu: „Nie wybrano programu emisyjnego”; gdy nie odpowiada: „Nie odpowiada żaden program emisyjny”. Wymaga TCP zarówno w SARZE, jak i SPL. Nowy tekst „Zostało {czas}” i rozszerzone opisy nauki wymagają akceptacji Michała przed wdrożeniem.

SPL: indeks 0 to znacznik godziny, pierwszy utwór ma indeks 1; TrackInfo nie zawiera checkboxa ani historii zagrań. Po Zoom mostek mówi jedynie „znacznik przełączony”. SARA: pierwszy element ma w protokole indeks 0, ale w komunikacie numer 1; TrackInfoEx daje stan znacznika, grania/pauzy/zagrania i przerwy po utworze. Nie potwierdzamy „gra”, gdy Stat tego nie potwierdza. Tytuły/czas/nawigacja pozostają mową także w trybie samych dźwięków, bo nie mają równoważnego sygnału. Potwierdzone PLAY/STOP zachowują istniejące dźwięki i tryby F4; F5 powtarza komunikat.

Konsola do testu bez stołu: `play`, `nastepny`, `stop`, `coGra`/`f6`, `automat`/`f7`, `gora`, `dol`, `znacznik`.

Technicznie: osobny wątek, najwyżej 0,5 s na całą linię odpowiedzi i 3 s na sesję. STOP usuwa zaległą kolejkę; polecenia inne niż STOP/Instant Stop czekające ponad 2 s są odrzucane z komunikatem, nie wykonywane po czasie. Wyjątkiem jest opisane niżej Hold, które pozostaje po STOP i nie wygasa. Kolejne polecenie łączy od nowa; akcja z niepewnym wynikiem nie jest powtarzana ani wysyłana zapasem (poza idempotentnym Hold). Brak programu i inne powtarzające się błędy ogłaszane najwyżej raz na 5 s; udana odpowiedź zeruje dławienie. Nieznane polecenia SPL uruchamiają skrypty, więc klient filtruje każdą wysyłaną linię. TrackInfoEx wolno wysłać dopiero po Helo SARY.


### Mikrofon, telefon i Zoom wstrzymują automat SARY

Domyślne `emisja.mikrofon_wstrzymuje_automat: true` wstrzymuje automatyczny start następnego utworu (`Hold=1`), gdy na antenie jest mikrofon lub dowolny rozmówca. Rozmówcy pochodzą z istniejących ustawień `zrodla`: źródła z polem `odbiorca`, domyślnie telefon i Zoom. Rozmówca jest na antenie przy Main On włączonym, suwaku powyżej `zachowanie.prog_suwaka_na_antenie_db` i bez CUE. Mikrofon nadal liczy się przez Main On niezależnie od suwaka; F1/SELECT wysyła zamiar Hold przed potwierdzeniem miksera.

Bieżący utwór gra do końca, następny nie startuje sam, także w automiksie. Zamknięcie mikrofonu nie zwalnia Hold, jeżeli telefon lub Zoom nadal jest na antenie. `Hold=0` następuje dopiero po potwierdzonym zejściu wszystkich blokujących źródeł. Rozmówca schodzi suwakiem do progu lub niżej, przez Main On OFF albo CUE. Wejście suwakiem z CUE (Auto CUE Reset by FADER) oraz zmiana z innego urządzenia są uwzględniane przy najbliższej obserwacji stanu, bez naciskania mikrofonu. Jeżeli utwór już się skończył, następny trzeba uruchomić klawiszem Następny.

Kaszel i talkback zachowują mikrofonowe Hold z migawki sprzed trzymania; nie zdejmują też Hold rozmówcy, którego anteny nie zmieniają. Samo CUE, PFL i muzyka nie blokują automatu. Jeśli nie potwierdzono żadnego źródła na antenie, ale stan choć jednego jest NIEZNANY, mostek nie wysyła nowego polecenia i nie zwalnia wstrzymania. Potwierdzona antena któregokolwiek źródła wystarcza do Hold mimo nieznanego stanu pozostałych. Nieudane otwarcie mikrofonu zwalnia Hold tylko przy potwierdzonym braku wszystkich blokujących źródeł.

Wymagana SARA obsługująca `Hold`, `Hold=0`, `Hold=1` z odpowiedzią `0|1,brak|trzyma|zatrzymane|za_pozno`. SPL nigdy nie otrzymuje tego rozszerzenia. Hold wyprzedza czekające klawisze, zastępuje starsze czekające Hold, nie wygasa po 2 s i pozostaje w kolejce po Stop/Instant Stop. Trwająca już operacja TCP nie jest przerywana, więc limit 30 ms dotyczy próby z czekającą kolejką, nie zawieszonego serwera. Mikrofon nigdy nie czeka na odpowiedź SARY. Ponawiane jest tylko idempotentne Hold, nie Play/Skip.

Odczyt stanu Hold jest zlecany co sekundę przy rozstrzygniętym warunku wstrzymania: gdy choć jedno źródło jest na antenie albo wszystkie są potwierdzone poza nią. Wykrywa to uruchomienie SARY bez klawisza transportu. Odczyt ma niższy priorytet niż klawisze. Po błędzie odtwarzane jest ostatnie znane żądanie, a po restarcie SARY odczyt wykrywa utracone wstrzymanie. Błąd potwierdzenia ma alarm i komunikat bezpieczeństwa, najwyżej raz na 5 s, bez wpływu na zaporę, CUE i przejścia MR18.

Komunikaty oraz trzy nowe dźwięki rodziny „automat” są robocze, do akceptacji Michała przed wdrożeniem. W trybie dźwięków wstrzymanie, zwolnienie i koniec utworu mogą być samym dźwiękiem; „za późno” i błąd zawsze mają mowę. Potwierdzenie wstrzymania mówi po mikrofonie; przy `dzwieki_naraz` dołącza dźwięk do oczekującego lub jeszcze grającego mikrofonu, bez jego ucinania. Jeśli potwierdzenie sieciowe przyjdzie dopiero po zakończeniu dźwięku mikrofonu, zabrzmi osobno: mostek nie opóźnia mikrofonu dla oczekiwania na sieć.

`false` całkowicie wyłącza wysyłanie Hold dla mikrofonu i wszystkich rozmówców. Ustawienia wczytywane są przy uruchomieniu; wyłączenie opcji samo nie wysyła Hold=0, więc aktywne wstrzymanie trzeba wcześniej zwolnić zejściem wszystkich blokujących źródeł z anteny albo zamknięciem serwera SARY. Dotychczasowe teksty pozostają bez zmiany: „Automat czeka na mikrofon” obejmuje też telefon i Zoom. Ruchy suwaka powyżej progu ani wymiana źródła podtrzymującego Hold nie powtarzają potwierdzenia wstrzymania. Nie jest to potwierdzenie działania na prawdziwej SARZE, MR18 ani NVDA.

## Paczka testowa Windows

`narzedzia/zbuduj_paczke_windows.py` buduje trzy konsolowe programy onedir:
`mostek.exe`, `badanie_mr18.exe` i `podsluch_midi.exe`, ze wspólnym `_internal`.
Potrzebny jest Python Windows 64 bit oraz już zainstalowany PyInstaller. Bez
`--zapisz` skrypt tylko pokazuje plan. Przykład w PowerShell, z katalogu repo:

```powershell
python narzedzia/zbuduj_paczke_windows.py --katalog-pracy C:\mostek-budowa --wyjscie C:\mostek-wydanie --commit (git rev-parse HEAD)
```

Po sprawdzeniu planu dopisz `--zapisz`. Oba katalogi muszą być nowe. Budowa
odbywa się na natywnym dysku Windows, po niej własny katalog pracy jest usuwany.
Raporty procesów budowy zostają w `odbior/`. Nazwa ZIP zachowuje bazę `eaaacc4`,
a manifest podaje rzeczywisty commit źródeł, Python, PyInstaller i sumy MD5.
Instrukcja TXT z BOM i dostępny HTML powstają z jednego źródła
`narzedzia/windows/instrukcja.json`. Skrypty BAT mają ostrzeżenie i potwierdzenie
przed uruchomieniem mostka z mikserem.

W EXE katalogiem danych jest katalog samego programu, nie `_internal` ani
bieżący katalog terminala. Dotyczy to ustawień, poziomów, trybu F4, dźwięków,
bibliotek NVDA i domyślnego dziennika. W repo ścieżki pozostają bez zmian.
Opcja `--dzwieki-konsola` kieruje dźwięki i alarm awarii mowy do tekstu
`[dzwiek]`, bez winsound; domyślna obsługa audio pozostaje bez zmian.
Tryb `--mowa konsola` sam w sobie nie wyłącza dźwięków. `--mowa nvda`
sprawdza dostępność uruchomionego NVDA przed przekazaniem mowy; przy jego
braku program przechodzi na konsolę.

Mostek może wykonać ochronne zapisy także podczas odczytu niezgodnego profilu.
Tylko osobne `badanie_mr18.exe` i `podsluch_midi.exe` są narzędziami odczytowymi.
Paczka nie zakłada autostartu i nie uruchamia nadzorcy. `--scena KATALOG` dołącza
BAZA.scn i obie instrukcje WCZYTANIE-BAZY; bez tego scena/CZYTAJ.txt wyraźnie
ogranicza próby do kroków 1–4. Podstawowa droga z mikserem to 6_mostek_z_nvda.bat,
5_mostek_z_mikserem.bat jest zapasem konsolowym. Zapora blokuje wszystkie zapisy
rodzin /-snap/*, /snap/* i /-action/*; indeks sceny pozostaje tylko do odczytu.

## Jak uruchomić z symulatorem

Potrzebny jest Python 3.10 albo nowszy. Mostek używa tylko biblioteki standardowej.

W katalogu `mostek`:

```
python -m mostek --symulator
```

Mostek uruchamia wtedy symulator MR18 w tym samym procesie, na adresie lokalnym i wolnym porcie. Komunikaty, które w studiu mówi NVDA, są wypisywane w konsoli z przedrostkiem `[mowa]`, a dźwięki informacji zwrotnej z przedrostkiem `[dzwiek]` (poza Windows nic nie gra). Konsola przyjmuje polecenia równe przyciskom X-TOUCH, listę daje polecenie `pomoc`. Przykłady:

```
f1          mikrofon (przełącznik)
f2          status
f3          koniec rozmowy
f4          tryb informacji zwrotnej: mowa, dźwięki, dźwięki z mową
f5          powtórz ostatni komunikat
kaszel      przytrzymanie przycisku kaszlu (MUTE paska 1)
pusc        puszczenie przycisku kaszlu
talkback 2  przytrzymanie talkbacku do telefonu (3 do Zooma)
pusc 2      puszczenie talkbacku do telefonu (3 do Zooma)
cue 2       CUE telefonu (SELECT paska 2)
cue 3       CUE Zooma
suwak 2 100 suwak telefonu w górze
suwak 2 0   suwak telefonu na dole
g 2 +       gałka telefonu o jeden ząbek w prawo
s 2         status paska 2 (telefon)
sym cisza   symulator: cisza na antenie (sym dzwiek: program gra)
sym bezmiernikow   symulator: mierniki nie przychodzą (sym zmiernikami: wracają)
koniec      zakończ
```

Osobny symulator, z którym mostek łączy się przez sieć lokalną jak z mikserem:

```
python -m mostek.symulator --port 10024
python -m mostek --mr18 127.0.0.1
```

Konsola symulatora pozwala udawać zmianę z innego klienta (`inny /ch/09/mix/lr 1`), utratę łączności (`rozlacz`, `polacz`), gubienie pakietów (`gub 3`), opóźnienie (`opoznienie 0.3`), ciszę na antenie (`cisza`, `dzwiek`) i brak mierników (`mierniki wylacz`, `mierniki wlacz`). Symulator nie liczy poziomu sumy z miksu: wysyła mierniki z ustawionym poziomem minus 18 dB albo ciszę.

W studiu:

```
python -m mostek.nadzorca --mowa nvda -- --mr18 ADRES_MR18 --mowa nvda --midi winmm --emisja stationplaylist --bez-konsoli
```

Adres MR18 podaje się zawsze jawnie. Mostek nie szuka miksera w sieci.

Testy (w katalogu `mostek`):

```
python3 -B -m unittest discover -s tests
```

Długi przebieg ciągów losowych: `MOSTEK_LOSOWE=500 nice -n 10 python3 -B -m unittest discover -s tests -p test_losowe.py`. Test mutacyjny zapory: `python3 -B narzedzia/mutacje_zapory.py`, z `--pelne` na całym zestawie testów (każdy mutant uruchamia cały zestaw, łącznie kilkadziesiąt minut).

## Sprawdzenie stanowiska bez sprzętu

Przed podłączeniem innego stanowiska sprawdź konfigurację i zajęte zasoby:

```
python -B -m mostek --sprawdz
python -B -m mostek --sprawdz --ustawienia stanowisko.json --poziomy poziomy_bazowe.json --json
```

Odpowiednik w paczce Windows: `mostek.exe --sprawdz`. Cienkie narzędzie `python -B narzedzia/sprawdz_stanowisko.py` przyjmuje te same ścieżki i `--json`. `-B` wyłącza zapis pamięci podręcznej Pythona.

Pierwsza linia poprawnego wyniku to `Stanowisko poprawne`. Dalej są ponumerowane ostrzeżenia o przyjętych wartościach domyślnych, obsada wejść i szyn, jawna lista wolnych zasobów, projekt wyjść USB, klucz przyciszania, znaczenia przycisków oraz playout. Błędy są zbierane razem, ze ścieżkami, np. `zrodla.mikrofon.kanaly[0]`. Kod wyjścia: 0 bez błędów (ostrzeżenia dozwolone), 1 błędy konfiguracji, 2 nieczytelny plik lub niepoprawny JSON.

Tryb sprawdzający nie otwiera OSC ani MIDI, nie uruchamia mowy, dźwięków ani playoutu, nie zapisuje dziennika, poziomów i trybu informacji. Nie wgrywa sceny i nie potwierdza okablowania. Profile USB w raporcie opisują projekt BAZA, nie stan miksera.

Zwykły start zachowuje dotychczasowe odmowy i wyniki wczytywania. Nowe kontrole dla dawniej akceptowanych plików są na razie ostrzeżeniami w dzienniku. Dlatego nie należy omijać błędu `--sprawdz` przez normalny start. Brak wersji schematu oznacza obecny profil v1; pliku Michała nie trzeba zmieniać. Bez playoutu uruchom z `--emisja brak`, nie przez wpis `emisja.program: "brak"`.

[Role, strefy i profil zgodności](stanowisko/role-i-strefy.md) opisują możliwości i granice konfiguracji. [Projekt drugiego mikrofonu](stanowisko/projekt-drugi-mikrofon.md) zawiera przykład świadomie odrzucany jednym błędem nieobsługiwanej roli. Drugi mikrofon nie jest jeszcze zaimplementowany.

## Pliki

- `ustawienia/stanowisko.json`: kanały, szyny (Bus 5 klucz przyciszania, Bus 6 głośniki), mapa pasków i klawiszy (MUTE 1 kaszel, MUTE 2 i 3 talkback), próg suwaka „na antenie”, przyciszenie muzyki przy CUE i na talkbacku, przyciszenie programu w słuchawkach, alarm ciszy, przypomnienie licznika, ignorowany dawny limit kaszlu, mierniki (identyfikator, indeks Main LR, kolejność bajtów), oczekiwany profil przyciszacza, numery MIDI, treść wszystkich komunikatów NVDA, czasy.
- `ustawienia/tryb_informacji.json`: zapisany tryb informacji zwrotnej (tworzy go F4; poza repozytorium).
- `dzwieki/`: 15 plików WAV (48 kHz, 16 bit, mono) i `dzwieki.json` z kluczem, plikiem, opisem i czasem. Katalog wskazuje `informacja_zwrotna.katalog_dzwiekow`.
- `mostek/informacja.py`: tryby informacji zwrotnej, mapowanie zdarzeń na dźwięki, lista stanów, które mogą zabrzmieć samym dźwiękiem, odtwarzacz winsound i atrapa.
- `ustawienia/poziomy_bazowe.json`: poziomy bazowe wysyłek w decybelach. Mostek dopisuje tu nowy poziom, gdy włączona wysyłka zmieni się z AOSC.
- `mostek/rdzen.py`: przełącznik mikrofonu, CUE, F3, przejścia z rozdziału 7, suwaki rozmówców, gałki, odsłuch, status.
- `mostek/logika.py`: stany rozmówców (czeka, CUE, na antenie) z odczytu miksera, zapora niezmienników z regułami CUE, kontrola profilu.
- `mostek/stan.py`: wartości potwierdzone kontra wysłane, stan NIEZNANY.
- `mostek/liczniki.py`: czas słownie z polską odmianą (minuta, minuty, minut; po „od” dopełniacz).
- `mostek/mierniki.py`: blok mierników MR18 i detektor ciszy (cisza, powrót, mierniki niedostępne).
- `mostek/sciezki.py`: jedyne miejsce ścieżek OSC, każda ze źródłem i statusem, plus lista luk.
- `mostek/osc.py`, `mostek/transport.py`, `mostek/klient.py`: kodek OSC, UDP, klient MR18 (port 10024, `/xremote` co 5 s, odczyt zapytaniem bez argumentu, najwyżej dwie powtórki, wymiana gniazda po przekroczeniu czasu, kontrola nadawcy).
- `mostek/symulator.py`: symulator MR18. Stan startowy to projekt sceny BAZA w sytuacji A, z kluczem Bus 5, głośnikami na Bus 6 i przyciszaczem kanału 10. Wysyła mierniki z możliwością wstrzyknięcia ciszy.
- `mostek/xtouch.py`: adapter X-TOUCH w trybie MC, ponowne otwarcie portu po odłączeniu i dostęp do MIDI w Windows przez winmm.
- `mostek/mowa.py`: kolejka komunikatów z priorytetem bezpieczeństwa, dźwięki przed mową i NVDA Controller Client.
- `mostek/emisja.py`: wspólny klient TCP SPL Pro i SARY, wybór programu oraz zapas SPL przez SendMessage.
- `mostek/playout.py`: niezależny wątek playoutu, kolejka, wygładzenie jog i komunikaty z odpowiedzi programu.
- `mostek/nadzorca.py`: osobny proces pilnujący mostka.
- `mostek/glowny.py`: punkt wejścia i konsola.
- `narzedzia/badanie_mr18.py`: na dzień dostawy. Pyta MR18 o identyfikację i o każdą ścieżkę OSC mostka (w tym punkty pobrania `/ch/NN/mix/BB/tap`, Bus 5 i Bus 6, `/ch/10/dyn/keysrc`, inserty), wyłącznie zapytaniami bez argumentu, czyli bez zapisu i bez `/xremote`. Z `--mierniki` dodatkowo subskrybuje `/meters/5` i zapisuje surowy blok z Main LR przy obu kolejnościach bajtów. Raport JSON: które ścieżki odpowiadają, jaki mają typ.
- `narzedzia/mutacje_zapory.py`: test mutacyjny reguł zapory w kopii kodu.
- `narzedzia/podsluch_midi.py`: zapis na dzień dostawy, co X-TOUCH faktycznie wysyła.
- `narzedzia/mikrofon_poza_antena.py`: awaryjne zdjęcie mikrofonu z anteny, osobny program do podpięcia pod globalny skrót Windows.
- `narzedzia/skroty_windows.ps1`: skrót autostartu mostka pod nadzorcą i skrót „Mikrofon poza anteną” (Ctrl+Alt+M). Bez `-Zapisz` tylko pokazuje, co zrobi.
- `narzedzia/zakres_scen_aosc.py`: lista węzłów albo plik sceny bez routingu, sumy, suwaków, wysyłek i odsłuchu. Bez `--zapisz` tylko podgląd.
- `dane_sceny/schemat-mr18.json`: własny schemat sceny MR18 zmierzony na mikserze (węzły, skale, 61 efektów). Opis w [dokumentacja/prosty-start.md](prosty-start.md).
- `biblioteki/x64`, `biblioteki/x86`: `nvdaControllerClient.dll` z oficjalnej paczki NVDA 2026.2 (licencja LGPL 2.1).
- Reguły zapory opisuje `mostek/logika.py` (`OPISY_REGUL`).

## Skąd są ścieżki OSC i numery MIDI

Ścieżki OSC: lista parametrów X AIR z forum Gig Performer (xair-osc-paramlist-gigperformer.txt) i układ Air Access 18 dla AOSC (azaosc.xml). Punkt pobrania `/ch/NN/mix/BB/tap` to liczba całkowita 0 do 5: wejście, przed korekcją, za korekcją, przed suwakiem (3), za suwakiem (4), podgrupa; oba źródła podają to samo. Mostek używa wyłącznie 3 i 4. Transport i `/xremote`: dokument producenta „X AIR Mixer Series Remote Control Protocol”. Każda ścieżka w `mostek/sciezki.py` ma numer wiersza w tych plikach. Ścieżki używane przez mostek sprawdzono na MR18V2 (firmware 1.19 i 1.26).

Numery MIDI trybu MC: otwarty projekt Ardour, obsługa Mackie Control, commit `a9ea4a98a336729a69453edbcc29905a79ac75e1`. Potwierdzone podsłuchem MIDI na X-TOUCH.

StationPlaylist: kody z dodatku NVDA do StationPlaylist: komunikat 1024, odtwórz 12, stop 13, następny 14, pauza 15, automatyzacja 16, stan odtwarzania 104.

## Co jest sprawdzone na symulatorze

Pełny zestaw testów `unittest` przechodzi na symulatorze w WSL. Po każdym kroku testy sprawdzają wartości w symulatorze („kto co słyszy” liczone z poziomu, punktu pobrania i suwaka), a nie stan zapamiętany przez mostek.

1. Sytuacje A do G („kto co słyszy”): antena, powrót telefonu, powrót Zooma, odsłuch kontrolny, prawe ucho, głośniki, przełącznik mikrofonu działa albo jest zablokowany. Każda sytuacja osobno ze stanu startowego i cała droga A, B, D, G, E, F, C, A bez wczytywania sceny.
2. Kolejność kroków przy CUE, zwolnieniu CUE, podniesieniu i ściągnięciu suwaka rozmówcy, z dwoma zgodnymi odczytami między zamknięciami a otwarciami.
3. CUE przy mikrofonie na antenie (mikrofon schodzi pierwszy), CUE przy rozmówcy na antenie (Main On przed silnikiem), CUE przy trzymanym suwaku, dwa CUE naraz, F3, SELECT muzyki tylko jako odsłuch.
4. Blokada przełącznika mikrofonu przy CUE (F1 i SELECT paska 1), wyłączanie zawsze działa.
5. Awaria w połowie: zamknięcie nieprzyjęte (ponowienie tylko brakującego, nic nie otwarto), utrata łączności w trakcie zamykania, nieudane otwarcie z wycofaniem, scena z innego klienta w trakcie przejścia.
6. Utrata łączności: stan NIEZNANY, F1 tylko wyłącza, CUE i F3 tylko zamykają, powrót bez nadpisania miksera, silniki według odczytu.
7. Zmiany z innego klienta: ogłoszone, nie cofnięte; suwak rozmówcy z AOSC zmienia powrót drugiego rozmówcy; mikrofon włączony z AOSC w trakcie rozmowy nie trafia do rozmówcy bez CUE.
8. Podsłuch prawego ucha, głośniki przy mikrofonie i przy każdym CUE, gałki, suwaki, MASTER, odsłuch programu i rozmowy.
9. Wszystkie niezmienniki zapory, każda reguła z wyłącznikiem w stanie, w którym tylko ona może odrzucić zapis. Test mutacyjny: każda z 16 reguł (9 reguł CUE z wersji 20, `klucz_tylko_glosy`, `klucz_bez_wyjscia`, `klucz_ta_sama_rozmowa`, `klucz_przy_niezgodnym_profilu`, `glosniki_przy_mikrofonie`, `glosniki_przy_niezgodnym_profilu`, `sciezka_w_rejestrze`) wyłączona w kopii kodu wywraca własny test. Osobno cofany jest każdy fragment ochrony przed szyną na Main LR z innego urządzenia i każdy warunek automatycznego włączania głośników; każdy taki mutant wywraca swój test. Niezmiennik `kaszel_bez_cue` nie ma osobnej reguły: pilnują go `cue_mikrofon_na_antene` i `glosniki_przy_mikrofonie`, a test mutacyjny pokazuje, że wyłączenie każdej z nich wywraca osobny test kaszlu.
10. Ciągi losowe: domyślnie 20 ciągów po 40 kroków (CUE, F1, F3, suwaki trzymane i puszczane, także z CUE, gałki, kaszel z puszczeniem i bez, restart kontrolera, cisza i brak mierników, utrata łączności, gubione pakiety, suwaki z innego klienta), po każdym kroku wszystkie niezmienniki na stanie symulatora, w tym: Bus 5 zawiera tylko źródła z tej samej rozmowy co słuchacz.
11. Test całościowy przez prawdziwe gniazda UDP na 127.0.0.1: start, subskrypcja, mikrofon, CUE telefonu przy mikrofonie na antenie, blokada przełącznika, zmiana z drugiego klienta, F3, utrata i powrót łączności. Osobny test UDP mierników: subskrypcja `/meters/5`, blok z symulatora, cisza, powrót dźwięku, mierniki niedostępne.
12. Narzędzie badania czyta każdą ścieżkę, którą mostek zapisuje w ciągach losowych, i odczytuje blok mierników z symulatora bez żadnego zapisu.
13. Podniesienie suwaka rozmówcy z CUE (kolejność kroków, drugi uczestnik CUE zostaje, ostatni CUE odblokowuje przełącznik, trzymany suwak nie kończy CUE), kaszel (trzymanie, puszczenie, zgubione puszczenie przy restarcie X-TOUCH, zamknięciu portu MIDI, utracie łączności, trzymanie 120 s bez przerywania, kaszel przy mikrofonie poza anteną i przy CUE, odciszone głośniki), liczniki z odmianą, alarm ciszy (cisza, powtórka, powrót, brak mierników, zły blok, próg i czas z ustawień), klucz przyciszania w sytuacjach A do G i przy przejściach, głośniki mono, profil z niezgodnym kluczem i przyciszaczem.
14. Szyna 1 do 6 przypisana do Main LR z innego urządzenia przed CUE, w trakcie CUE i przy mikrofonie oraz słuchaczu na antenie: profil od razu blokuje otwarcia, klucz przyciszania się zamyka, także gdy zgłoszenie z miksera zginęło i zmianę wykrywa odczyt okresowy.
15. Głośniki włączają się same po wyłączeniu mikrofonu, po F3, po SELECT ostatniego CUE i po suwaku kończącym ostatnie CUE; nie włączają się przy trwającym CUE, przy mikrofonie na antenie, w trakcie kaszlu, przy stanie nieznanym ani przy niezgodnym profilu.
16. Luki L01 do L06 z analizy wersji 22 (`tests/test_luki_v22.py`): utrata i powrót kontrolera, limit świeżości odczytu, głośniki przy niezgodnym profilu i stanie nieznanym, licznik nowego stanu, wszystkie wejścia Bus 5 z zamknięciem obcych, zamknięty rejestr ścieżek. Do tego decyzje z 18.10.2026: licznik po kaszlu od nowa, ochronne zamknięcia bez otwarć i zero zapisów przy zgodnym mikserze, krótki F2. Każda poprawka ma mutant w `narzedzia/mutacje_zapory.py`, który wywraca jej test.
17. Tryby informacji zwrotnej (`tests/test_tryby_dzwiekow.py`): domyślny tryb, zapis i odczyt trybu (także uszkodzony i nieznany wpis, nieudany zapis), każdy komunikat stanu w trzech trybach, odmowy i ostrzeżenia z mową, F2, gałka, kontroler, profil i ochronne zamknięcia z mową w trybie dźwięków, przejście przez wszystkie klucze komunikatów, F4 w cyklu z ogłoszeniem, F5 bez odczytu i zapisu, brak pliku WAV i błąd odtwarzania (mowa zamiast dźwięku, jedno ostrzeżenie), kolejność dźwięku i mowy, ostrzeżenie przerywające dźwięk stanu. Ponowne otwarcie portu MIDI na atrapie portu: utrata, kilka nieudanych prób co 2 s, powrót, jeden komunikat utraty i jeden powrotu, silniki przed uzbrojeniem, drugie odłączenie, brak X-TOUCH przy starcie. Mutanty: komunikat bezpieczeństwa traci mowę w trybie dźwięków, komunikat spoza stanów traci mowę, F5 wykonuje zapis, F5 czyta mikser, F4 nie ogłasza trybu, nieudany dźwięk bez mowy, ostrzeżenie nie przerywa dźwięku, brak ponawiania otwarcia MIDI. Ciągi losowe zaczynają w każdym z trzech trybów, mają F4 i F5 w puli i sprawdzają po każdym kroku, że komunikat bezpieczeństwa nie poszedł bez mowy.
18. Talkback i kaszel poza anteną (`tests/test_talkback.py`): selektywni adresaci, Bus 5 zamknięty, niezmienione tory rozmówców, dokładny powrót, nakładanie przycisków, 120 s, utrata urządzeń, obca zmiana, niepotwierdzone zapisy i odmowy. Nowe reguły mają własne mutanty.
