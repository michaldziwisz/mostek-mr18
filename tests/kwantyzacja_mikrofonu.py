"""Model offline zgodny z parami z logu, NIE pomiar algorytmu firmware.

Obcinamy float32 OSC do 1023 odstępów. Zwykły symulator nadal obsługuje
zapisy, awarie i odpowiedzi; nie zmieniamy wyniku klient.ustaw na sukces.
"""
import math
import struct
from contextlib import contextmanager
from unittest.mock import patch
from mostek.osc import Komunikat


def float32(v):
    return struct.unpack('!f', struct.pack('!f', v))[0]


def kwantyzuj(v):
    return float32(math.floor(float32(v) * 1023) / 1023)


@contextmanager
def model(test):
    fader = '/ch/09/mix/fader'
    zdarzenia = []
    obsluz = test.sym._obsluz
    odczytaj = test.klient.odczytaj_wiele
    def odbior(k, nadawca):
        if k.argumenty:
            zdarzenia.append(dict(typ='zapis', t=test.zegar(), adres=k.adres, wartosc=k.wartosc))
            if k.adres == fader:
                k = Komunikat(k.adres, (kwantyzuj(k.wartosc),), k.typy)
        return obsluz(k, nadawca)
    def odczyt(adresy, *args, **kwargs):
        wynik = odczytaj(adresy, *args, **kwargs)
        zdarzenia.append(dict(typ='odczyt', t=test.zegar(), dane=dict(wynik)))
        return wynik
    with patch.object(test.sym, '_obsluz', side_effect=odbior), patch.object(
            test.klient, 'odczytaj_wiele', side_effect=odczyt):
        yield zdarzenia
