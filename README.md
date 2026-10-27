# Mostek MR18

**English summary.** A bridge for radio broadcasting with a Midas MR18 digital mixer and a Behringer X-TOUCH controller (Mackie Control mode), designed for a blind presenter working with the NVDA screen reader. The bridge turns the MR18 into a broadcast desk: CUE talk-back with callers (phone and Zoom) like on D&R radio consoles, cough button, talkback, ducking the caller under the presenter, speaker muting, silence alarm and spoken status through NVDA or short sounds. It also drives the SARA and StationPlaylist playout systems from the desk (play, stop, automation, mix points, hold while the microphone is on air). The MR18 does all the audio mixing; the bridge only sends OSC commands and confirms every change by reading the mixer back. Python, standard library only. User interface and documentation are in Polish. The included scene is set up for a **Shure SM7B microphone with a Cloudlifter** (gain +32 dB, phantom power 48 V on input 9). License: BSD 3-Clause.

---

Mostek łączy mikser **Midas MR18** i kontroler **Behringer X-TOUCH** (tryb Mackie Control) w stanowisko radiowe dla niewidomego realizatora pracującego z czytnikiem ekranu **NVDA**. Mikser miksuje dźwięk sam, a mostek steruje nim przez OSC, sprawdza każdą zmianę odczytem z miksera i mówi stan przez NVDA albo krótkimi dźwiękami.

## Co potrafi

- **Rozmowy jak na konsoletach D&R:** telefon i Zoom czekają, rozmawiają poza anteną (CUE) albo są na antenie. Podniesienie suwaka rozmówcy z CUE wpuszcza go na antenę.
- **Kaszel i talkback:** przycisk kaszlu zamyka mikrofon na czas trzymania, talkback mówi tylko do wybranego rozmówcy.
- **Przyciszanie słuchacza:** telefon cichnie, gdy mówi prezenter albo Zoom w tej samej rozmowie (kompresor kanału kluczowany szyną Bus 5).
- **Głośniki:** wyciszają się przy mikrofonie na antenie i przy każdej rozmowie, a włączają same po jej końcu.
- **Liczniki czasu i alarm ciszy na antenie.**
- **Zapora bezpieczeństwa:** mostek nie wykona zapisu, który mógłby otworzyć rozmowę prywatną na antenę albo wpuścić mikrofon przy rozmowie poza anteną. Przy utracie łączności albo niepewnym stanie tylko zamyka.
- **Sterowanie emisją ze stołu:** SARA i StationPlaylist Studio (Play, Stop, automat, czas do końca, punkty miksu z odsłuchem PFL, wstrzymanie automatu, gdy mikrofon jest na antenie).
- **START, RESTART i PRZYWRÓĆ:** jedno uruchomienie porównuje mikser ze sceną BAZA, w razie różnic robi kopię i wczytuje scenę, a potem startuje mostek.

## Scena i ustawienia

W repozytorium są prawdziwe ustawienia stanowiska, dla którego mostek powstał:

- `dane_sceny/BAZA.scn`: scena MR18.
- `ustawienia/stanowisko.json` i `ustawienia/poziomy_bazowe.json`: przypisanie kanałów, szyn, pasków i przycisków stołu, poziomy wysyłek oraz treść wszystkich komunikatów. Wersja z dopisanymi maksimami suwaków i wyłączonym alarmem ciszy, jak na stanowisku autora: `dokumentacja/stanowisko/stanowisko-autora.json`.
- `dane_sceny/WCZYTANIE-BAZY.txt` i `.html`: jak zrobić własną kopię, wczytać scenę i wrócić.

### Mikrofon: Shure SM7B z Cloudlifterem

Scena jest ustawiona pod **Shure SM7B przez Cloudlifter** na wejściu 9:

- wzmocnienie +32 dB, **phantom 48 V włączony** (zasila Cloudliftera),
- filtr dolnozaporowy 79 Hz,
- korektor: +9 dB przy 65 Hz, −6 dB przy 202 Hz, −3,75 dB przy 590 Hz, półka +15 dB od 8,15 kHz,
- ekspander i kompresor na kanale mikrofonu, Combinator na insercie.

**Uwaga przed wczytaniem sceny:** jeśli masz inny mikrofon albo SM7B bez Cloudliftera, sprawdź phantom i wzmocnienie na wejściu 9. Nie podłączaj tam mikrofonu wstęgowego ani niesymetrycznych przejściówek przy włączonym phantomie. Korektor jest dobrany do tego jednego mikrofonu i tego głosu.

### Reszta stanowiska

- Wejścia USB 1 do 6: trzy stereofoniczne źródła muzyki z komputera (trim −1 dB), USB 7/8: dźwięk z Zooma.
- Wejście 10: telefon przez BlueDriver-M3 (phantom wyłączony).
- Wyjście USB 9: suchy mikrofon do nagrań poza anteną (mostek zgłasza to jako ostrzeżenie, nie błąd).
- Bus 1: powrót do telefonu, Bus 2: podsłuch telefonu w prawym uchu, Bus 3/4: powrót do Zooma, Bus 5: klucz przyciszania (bez wyjścia audio), Bus 6: głośniki mono.
- FX1: Dual Combinator (mikrofon i telefon), FX2: Stereo Combinator (Zoom), FX3: limiter na sumie, FX4: limiter na powrocie Zooma.

Pełna tabela połączeń: `dane_sceny/WCZYTANIE-BAZY.txt`.

## Uruchomienie

### Paczka Windows

Gotowa paczka jest w [wydaniach](../../releases). Rozpakuj ją, uruchom `START.bat` i postępuj według `CZYTAJ-NAJPIERW.txt`. Wymagane: Windows 10 albo 11, uruchomione NVDA, MR18 w tej samej sieci, X-TOUCH przez USB w trybie MC.

Sprawdzenie samych ustawień, bez sprzętu: `mostek.exe --sprawdz` w katalogu `program`.

### Z kodu źródłowego

Potrzebny jest Python 3.10 albo nowszy, bez dodatkowych pakietów.

```
python -m mostek --symulator
```

uruchamia mostek z wbudowanym symulatorem MR18, a polecenia stołu wpisuje się w konsoli (`pomoc` wypisuje listę). Z prawdziwym mikserem:

```
python -m mostek --mr18 ADRES_MR18 --mowa nvda --midi winmm
```

Testy:

```
python -B -m unittest discover -s tests
```

## Dokumentacja

- [Instrukcja i opis działania](dokumentacja/instrukcja.md): rozmowy, kaszel, talkback, przyciszanie, głośniki, komunikaty NVDA, mapa stołu, sterowanie SARĄ i SPL.
- [Prosty start](dokumentacja/prosty-start.md): START, RESTART, PRZYWRÓĆ, schemat sceny.
- [Punkty miksu ze stołu](dokumentacja/punkty-miksu.md).
- [Role i strefy stanowiska](dokumentacja/stanowisko/role-i-strefy.md), [projekt drugiego mikrofonu](dokumentacja/stanowisko/projekt-drugi-mikrofon.md).

## Schemat sceny

Do wczytywania i sprawdzania scen mostek używa własnego schematu `dane_sceny/schemat-mr18.json`: lista 693 węzłów sceny, skale wszystkich parametrów i 61 typów efektów. Schemat powstał z pomiaru na Midas MR18 (firmware 1.26), a każde pole ma opisane pochodzenie. Projekt nie zawiera plików Air Access 18 ani AOSC. Do pracy ze sceną z poziomu czytnika ekranu polecamy [AOSC z Air Access 18](https://www.azslow.com/), które instaluje się osobno.

## Ograniczenia

- Mostek obsługuje jeden mikrofon lokalny, telefon, jednego gościa przez Zoom i trzy źródła muzyki. Drugi mikrofon jest zaprojektowany, ale nie wdrożony.
- Sprawdzony na MR18V2 z firmware 1.19 i 1.26 oraz X-TOUCH z firmware 1.25. Inne miksery z serii X AIR nie były testowane.
- Stan połączenia telefonicznego nie jest dostępny przez OSC: mostek mówi o torze telefonu, nie o rozmowie.
- X-TOUCH potrafi się czasem zawiesić (port USB widoczny, stół milczy). Pomaga wyłączenie i włączenie stołu; mostek przyjmuje go z powrotem sam.

## Licencja

Kod: [BSD 3-Clause](LICENSE). Biblioteka `nvdaControllerClient.dll` z projektu NVDA ma licencję LGPL 2.1 ([tekst](biblioteki/LICENSE-nvdaControllerClient.txt), [źródła](https://github.com/nvaccess/nvda)). Szczegóły: [NOTICE.txt](NOTICE.txt).

Mostek powstał z udziałem sztucznej inteligencji.
