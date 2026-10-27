"""Transport do MR18: prawdziwe UDP albo pamięć (dla testów z symulatorem).

Klient używa dwóch kanałów:
  * kanał subskrypcji: /xremote i zgłoszenia zmian od miksera,
  * kanał weryfikacji: zapisy i zapytania potwierdzające.
Po przekroczeniu czasu odpowiedzi kanał weryfikacji jest wymieniany na nowy
(nowe gniazdo, nowy port), więc spóźniona odpowiedź na stare zapytanie
trafia do zamkniętego gniazda i nie może być wzięta za odpowiedź na nowe.
To realizuje zalecenie planu, rozdział 8, kontrakt pkt 4.
"""

from __future__ import annotations

import itertools
import socket
import threading
from typing import Callable

Odbior = Callable[[bytes, object], None]


class KanalUDP:
    def __init__(self, cel: tuple[str, int], odbior: Odbior, adres_lokalny: str = "") -> None:
        self.cel = cel
        self._odbior = odbior
        self._gniazdo = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._gniazdo.bind((adres_lokalny, 0))
        self._gniazdo.settimeout(0.1)
        self._dziala = True
        self._watek = threading.Thread(target=self._petla, name="mr18-odbior", daemon=True)
        self._watek.start()

    def _petla(self) -> None:
        while self._dziala:
            try:
                dane, nadawca = self._gniazdo.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                # Windows: komunikat ICMP „port nieosiągalny” po wcześniejszym
                # wysłaniu (np. mikser w trakcie restartu) zgłasza się przy
                # następnym odbiorze. To nie koniec gniazda; bez tego wątek
                # odbioru ginął po cichu i kanał zgłoszeń zmian milkł na stałe.
                continue
            except OSError:
                break
            # Kontrola nadawcy: tylko adres i port miksera.
            if nadawca[0] != self.cel[0] or nadawca[1] != self.cel[1]:
                continue
            try:
                self._odbior(dane, nadawca)
            except Exception:  # noqa: BLE001 - błąd obsługi nie może zabić odbioru
                import logging
                logging.getLogger("mostek.transport").exception("błąd obsługi pakietu")

    def wyslij(self, dane: bytes) -> None:
        if self._dziala:
            try:
                self._gniazdo.sendto(dane, self.cel)
            except OSError:
                pass

    def zamknij(self) -> None:
        self._dziala = False
        try:
            self._gniazdo.close()
        except OSError:
            pass


class TransportUDP:
    """Prawdziwe UDP. Adres miksera podaje użytkownik; brak wykrywania w sieci."""

    def __init__(self, host: str, port: int = 10024) -> None:
        # Rozwiązanie nazwy raz, żeby kontrola nadawcy porównywała adres IP.
        ip = socket.gethostbyname(host)
        self.cel = (ip, int(port))
        self.adres_lokalny = "127.0.0.1" if ip.startswith("127.") else ""

    def otworz_kanal(self, odbior: Odbior) -> KanalUDP:
        return KanalUDP(self.cel, odbior, self.adres_lokalny)


class KanalPamieciowy:
    def __init__(self, transport: "TransportPamieciowy", ident: str, odbior: Odbior) -> None:
        self.transport = transport
        self.ident = ident
        self._odbior = odbior
        self.otwarty = True

    def wyslij(self, dane: bytes) -> None:
        if self.otwarty:
            self.transport._wyslij(self.ident, dane)

    def dostarcz(self, dane: bytes) -> None:
        if self.otwarty:
            self._odbior(dane, ("symulator", 10024))

    def zamknij(self) -> None:
        self.otwarty = False


class TransportPamieciowy:
    """Połączenie z RdzenSymulatora w pamięci, bez gniazd. Tylko do testów."""

    def __init__(self, rdzen) -> None:
        self.rdzen = rdzen
        self._licznik = itertools.count(1)
        self._kanaly: dict[str, KanalPamieciowy] = {}
        self._blokada = threading.Lock()

    def otworz_kanal(self, odbior: Odbior) -> KanalPamieciowy:
        ident = f"pamiec-{next(self._licznik)}"
        kanal = KanalPamieciowy(self, ident, odbior)
        with self._blokada:
            self._kanaly[ident] = kanal
        return kanal

    def _wyslij(self, ident: str, dane: bytes) -> None:
        odpowiedzi = self.rdzen.przyjmij(dane, ident)
        for pakiet, odbiorca, opoznienie in odpowiedzi:
            self._dostarcz_pozniej(pakiet, odbiorca, opoznienie)

    def _dostarcz_pozniej(self, pakiet: bytes, odbiorca: str, opoznienie: float) -> None:
        kanal = self._kanaly.get(odbiorca)
        if kanal is None:
            return
        if opoznienie > 0:
            t = threading.Timer(opoznienie, kanal.dostarcz, args=(pakiet,))
            t.daemon = True
            t.start()
        else:
            kanal.dostarcz(pakiet)

    def rozeslij(self, odpowiedzi) -> None:
        """Dostarcz pakiety wygenerowane przez rdzeń poza zapytaniem (np. zmiana z innego klienta)."""
        for pakiet, odbiorca, opoznienie in odpowiedzi:
            self._dostarcz_pozniej(pakiet, odbiorca, opoznienie)
