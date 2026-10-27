"""Mierniki MR18 i alarm ciszy na antenie (plan v21, rozdz. 8, pkt 4).

Źródło formatu: dokument producenta „X AIR Mixer Series Remote Control
Protocol”, punkt 1.5 i „Meter subscriptions” (kopia
dokument „X AIR Mixer Series Remote Control Protocol”, wiersze 31-37, 65-67, 77-121):
  * subskrypcja: /meters ,s "<identyfikator>" (np. "/meters/5"), ważna
    jak /xremote (10 s), więc mostek odnawia ją razem z /xremote,
  * odpowiedź: blob pod adresem identyfikatora; w bloku jedna liczba
    całkowita (liczba wartości), potem wartości int16 ze znakiem,
    rozdzielczość 1/256 dB,
  * /meters/5 „ALL OUTPUTS”: 6 aux, lr, 16 p16, 18 usb, headphones
    (44 wartości). Main LR to wartości 6 i 7: układ Air Access 18 dla AOSC
    (azaosc.xml, wiersz 1599: Main LR „bvalue=H16+18”, bajty 16 i 18 bloku,
    gdzie bajt 4 to pierwsza wartość, Aux 1, wiersz 1681: „mbus1=4”).

LUKA do potwierdzenia na MR18: kolejność bajtów w bloku (PROTO jej nie
podaje; przyjmujemy little-endian jak w X32, opcja w ustawieniach), czy
liczba na początku to liczba wartości, czy bajtów, indeks Main LR i to, czy
wartość jest w dBFS. Narzędzie narzedzia/badanie_mr18.py --mierniki zapisuje
surowy blok do raportu.

Brak danych z mierników to NIE cisza: osobny stan „mierniki niedostępne”,
bez alarmu ciszy.
"""

from __future__ import annotations

import struct
import threading

INT16_MIN = -32768
INT16_MAX = 32767


def dekoduj_blok(blob: bytes, kolejnosc: str = "little") -> list[int]:
    """Blok mierników: liczba wartości (int32), potem wartości int16 ze znakiem."""
    f = "<" if kolejnosc == "little" else ">"
    if len(blob) < 4:
        raise ValueError("blok mierników bez nagłówka")
    (n,) = struct.unpack(f + "i", blob[:4])
    dostepne = (len(blob) - 4) // 2
    if n == len(blob) - 4 and n % 2 == 0:
        n //= 2                       # nagłówek w bajtach zamiast w wartościach
    if n < 0 or n > dostepne:
        raise ValueError(f"blok mierników: zapowiedziane {n} wartości, dostępne {dostepne}")
    return list(struct.unpack(f + "h" * n, blob[4:4 + 2 * n]))


def koduj_blok(wartosci: list[int], kolejnosc: str = "little") -> bytes:
    """Odwrotność dekoduj_blok (symulator i testy)."""
    f = "<" if kolejnosc == "little" else ">"
    return struct.pack(f + "i", len(wartosci)) + struct.pack(f + "h" * len(wartosci), *wartosci)


def db_na_int16(db: float) -> int:
    return max(INT16_MIN, min(INT16_MAX, int(round(float(db) * 256))))


def poziom_lr(wartosci: list[int], indeksy=(6, 7)) -> float:
    """Wyższy z kanałów Main L i R w dB (1/256 dB na jednostkę)."""
    if any(i >= len(wartosci) for i in indeksy):
        raise ValueError("blok mierników nie zawiera Main LR")
    return max(wartosci[i] for i in indeksy) / 256.0


class DetektorCiszy:
    """Stan sumy na antenie z mierników.

    Stany: „oczekiwanie” (po synchronizacji, jeszcze bez danych),
    „niedostepne” (brak danych dłużej niż limit), „dzwiek”, „cisza” (poniżej
    progu, jeszcze bez alarmu), „alarm”. krok() zwraca zdarzenia do
    ogłoszenia: „cisza” (pierwszy alarm i powtórki co `powtorka_s`),
    „powrot” (jednorazowo po alarmie), „niedostepne”, „dostepne”.
    Wywołania z wątku sieciowego (przyjmij) i roboczego (krok) są pod blokadą.
    """

    def __init__(self, prog_dbfs: float = -50.0, czas_s: float = 10.0, powtorka_s: float = 30.0,
                 limit_braku_s: float = 2.0) -> None:
        self.prog_dbfs = float(prog_dbfs)
        self.czas_s = float(czas_s)
        self.powtorka_s = float(powtorka_s)
        self.limit_braku_s = float(limit_braku_s)
        self._blokada = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Bez aktywnego pomiaru (start, utrata łączności): żadnych zdarzeń."""
        with self._blokada:
            self._start: float | None = None
            self._ost_dane: float | None = None
            self._cisza_od: float | None = None
            self._alarm = False
            self._ost_alarm: float | None = None
            self._niedostepne = False
            self.ostatni_db: float | None = None

    def oczekuj(self, teraz: float) -> None:
        """Początek pomiaru po synchronizacji: dane mają przyjść w limicie."""
        self.reset()
        with self._blokada:
            self._start = teraz

    def przyjmij(self, db: float, teraz: float) -> None:
        with self._blokada:
            self._ost_dane = teraz
            self.ostatni_db = db
            if db < self.prog_dbfs:
                if self._cisza_od is None:
                    self._cisza_od = teraz
            else:
                self._cisza_od = None

    @property
    def stan(self) -> str:
        with self._blokada:
            if self._start is None:
                return "wylaczony"
            if self._niedostepne:
                return "niedostepne"
            if self._ost_dane is None:
                return "oczekiwanie"
            if self._alarm:
                return "alarm"
            return "cisza" if self._cisza_od is not None else "dzwiek"

    def krok(self, teraz: float) -> list[str]:
        with self._blokada:
            if self._start is None:
                return []
            zdarzenia: list[str] = []
            odniesienie = self._ost_dane if self._ost_dane is not None else self._start
            if teraz - odniesienie > self.limit_braku_s:
                if not self._niedostepne:
                    self._niedostepne = True
                    zdarzenia.append("niedostepne")
                # Brak danych to nie cisza: kasujemy pomiar ciszy i alarm.
                self._cisza_od = None
                self._alarm = False
                return zdarzenia
            if self._niedostepne:
                self._niedostepne = False
                zdarzenia.append("dostepne")
            if self._cisza_od is not None and teraz - self._cisza_od >= self.czas_s:
                if not self._alarm:
                    self._alarm = True
                    self._ost_alarm = teraz
                    zdarzenia.append("cisza")
                elif self._ost_alarm is not None and teraz - self._ost_alarm >= self.powtorka_s:
                    self._ost_alarm = teraz
                    zdarzenia.append("cisza")
            elif self._cisza_od is None and self._alarm:
                self._alarm = False
                zdarzenia.append("powrot")
            return zdarzenia
