"""Atrapa protokołu na prawdziwym TCP/loopback, nie atrapa klienta.

SPL: pola i numeracja z opt_comms.html (0 = Hour Marker); opcjonalny ACK
z opt_commtcp.html. SARA: uzgodnione TrackInfoEx, 0 = pierwszy utwór.
Dane utworów są celowo syntetyczne. Ta atrapa nie dowodzi zachowania aplikacji.
"""
from __future__ import annotations
import csv
import io
import socket
import socketserver
import threading
import time
from tests.atrapa_miksu import AtrapaMiksu


class SerwerPlayoutu:
    def __init__(self, sara=False):
        self.sara = sara
        self.miks = AtrapaMiksu()
        self.polaczenia = set()
        self.helo = "SARA v1.2.3" if sara else "StationPlaylist Studio v6.11"
        self.polecenia = []
        self.czasy = []
        self.hold = False
        self.hold_stan = 'brak'
        self.przejscie = False
        self.gra = False
        self.auto = False
        self.pauza = False
        self.indeks = 0 if sara else 1
        self.curr = -1
        self.checked = {}
        self.statusy = {}
        self.rem = "135000"
        self.players = "-"
        self.this = "Artysta - Tytuł"
        self.next = "Inny - Następny"
        self.ack = "1"
        self.odpowiedzi = {}
        self.opoznienie = {}
        self.zerwij = set()
        self.milcz = set()
        self.fragmentuj = False
        self.podawaj_bajty_s = 0
        self.kodowanie = "utf-8"
        self.koniec = threading.Event()
        self.warunek = threading.Condition()
        model = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(None)
                with model.warunek:
                    model.polaczenia.add(self.request)
                try:
                    while not model.koniec.is_set():
                        surowe = self.rfile.readline(4096)
                        if not surowe:
                            return
                        p = surowe.decode("ascii").rstrip("\r\n")
                        with model.warunek:
                            model.polecenia.append(p)
                            model.czasy.append((p, time.monotonic()))
                            model.warunek.notify_all()
                        key = p.lower()
                        if key in model.zerwij:
                            return
                        if key in model.milcz:
                            model.koniec.wait(2)
                            return
                        if model.koniec.wait(model.opoznienie.get(key, 0)):
                            return
                        with model.warunek:
                            odpowiedz = model.odpowiedz(p, self)
                        if odpowiedz is None:
                            continue
                        data = (odpowiedz + "\r\n").encode(model.kodowanie)
                        if model.fragmentuj:
                            for bajt in data:
                                self.request.sendall(bytes([bajt]))
                                if model.koniec.wait(model.podawaj_bajty_s):
                                    return
                        else:
                            self.request.sendall(data)
                except (OSError, UnicodeError, ValueError, IndexError):
                    return
                finally:
                    with model.warunek:
                        model.miks.zamknij(self)
                        model.polaczenia.discard(self.request)
                        model.warunek.notify_all()

        class TCP(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.serwer = TCP(("127.0.0.1", 0), Handler)
        self.port = self.serwer.server_address[1]
        self.watek = threading.Thread(target=self.serwer.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.watek.start()

    def odpowiedz(self, polecenie, klient=None):
        p = polecenie.lower()
        if p in self.odpowiedzi:
            odpowiedz = self.odpowiedzi[p]
            if p in ("mixsave", "mixcancel") and odpowiedz.startswith("OK"):
                self.miks.zamknij(klient)
            return odpowiedz
        if p.startswith("mix") and self.sara:
            return self.miks.odpowiedz(p, klient, self)
        if p == "helo":
            return self.helo
        if self.sara and (p == 'hold' or p.startswith('hold=')):
            if p not in ('hold', 'hold=0', 'hold=1'):
                return 'ERR syntax'
            if p == 'hold=1' and not self.hold:
                self.hold = True
                self.hold_stan = ('za_pozno' if self.przejscie else
                                  'trzyma' if self.gra else 'brak')
            elif p == 'hold=0':
                self.hold = False
                # Stan zatrzymane zostaje w odpowiedzi zwalniającej.
            return f'{int(self.hold)},{self.hold_stan}'
        if p == "stat":
            # SPL 6.20 Michała (pomiar 24.10.2026) zwraca 8 cyfr, SARA 7.
            return f"{int(self.gra)}{int(self.auto)}00{int(self.pauza)}01" + ("" if self.sara else "0")
        if p == "this":
            if not (self.gra or self.pauza):
                # SPL 6.20 przy ciszy w ogóle nie odpowiada na This (pomiar).
                return "" if self.sara else None
            return self.this
        if p == "next":
            return self.next
        if p == "players" and self.sara:
            return self.players
        if p == "rem":
            return self.rem
        if p == "elap":
            return "90000"
        if p == "selectindex":
            return str(self.indeks)
        if p == "currindex":
            return str(self.curr if self.gra else -1)
        if p == "lastindex":
            return "29"
        if p.startswith("selectindex="):
            v = p.split("=", 1)[1]
            self.indeks = min(29, max(0, self.indeks + (1 if v == "+" else -1))) if v in ("+", "-") else int(v)
            return self.ack
        if p in ("play", "skip"):
            if p == "skip":
                self.indeks = min(29, self.curr + 1) if self.curr >= 0 else self.indeks
                self.this = "Drugi - Kolejny"
            self.gra, self.pauza, self.curr = True, False, self.indeks
            return self.ack
        if p in ("stop", "instant stop"):
            self.gra, self.pauza, self.curr = False, False, -1
            return self.ack
        if p in ("auto", "autoon", "autooff"):
            self.auto = not self.auto if p == "auto" else p == "autoon"
            return self.ack
        if p == "pause":
            self.pauza = not self.pauza
            return self.ack
        if p == "checktoggle":
            self.checked[self.indeks] = not self.checked.get(self.indeks, True)
            return self.ack
        if p.startswith("trackinfoex=") and self.sara:
            n = int(p.split("=")[1].split("-")[0])
            status = self.statusy.get(n, "playing" if n == self.curr and self.gra else "pending")
            return f"{n}|{int(self.checked.get(n, True))}|{status}|Żółć|Utwór {n}|225000|0"
        if p.startswith("trackinfo="):
            n = int(p.split("=")[1].split("-")[0])
            out = io.StringIO()
            csv.writer(out, lineterminator="").writerow([
                # Format jak SPL 6.20 (pomiar 24.10.2026): typ liczbą (4 = Hour
                # Marker), czasy w milisekundach, brak intro/outro = -1.
                n, 4 if n == 0 else 0, "------------- Hour Marker -------------" if n == 0 else "Artysta, Zespół",
                "0200 (2am 24.10.2026)" if n == 0 else f"Utwór {n}", "" if n == 0 else "Album",
                0 if n == 0 else 225000, -1, -1, "Hour Marker" if n == 0 else "<Manual Track>",
                "" if n == 0 else "E:\\ccmusic\\utwor.flac"])
            return out.getvalue()
        return "ERR unknown" if self.sara else "SCRIPT EXECUTED"

    def skoncz_utwor(self):
        self.gra = False
        if self.hold:
            self.hold_stan = 'zatrzymane'

    def czekaj_na(self, polecenie, ile=1, timeout=1.0):
        with self.warunek:
            return self.warunek.wait_for(lambda: self.polecenia.count(polecenie) >= ile, timeout)

    def zamknij(self):
        self.koniec.set()
        with self.warunek:
            for g in list(self.polaczenia):
                try:
                    g.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.serwer.shutdown()
        self.serwer.server_close()
        self.watek.join(1)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.zamknij()


def zamkniety_port():
    with socket.socket() as g:
        g.bind(("127.0.0.1", 0))
        return g.getsockname()[1]
