#!/usr/bin/env python3
"""Rejestrujący model OSC miksera MR18, WYŁĄCZNIE loopback.
To model protokołu, NIE emulator DSP/firmware.
Źródła: publiczna lista OSC X AIR, schemat dane_sceny/schemat-mr18.json, format /node.
Nie importuje mostka. Każdy datagram RX/TX ma zapis hex i rozkodowaną treść.
Nieznane zapisy zapamiętuje, nieznanych odczytów nie wymyśla.
"""
from __future__ import annotations
import argparse
import base64
import json
import math
from pathlib import Path
import shlex
import socket
import struct
import sys
import time
import traceback
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narzedzia.format_scn import Schemat, czytaj_scn, num
from format_node import format_value


def oscstr(s):
    b = s.encode('utf-8') + b'\0'
    return b + b'\0' * (-len(b) % 4)


def pack(address, args=(), types=None):
    if types is None:
        types = ''.join('s' if isinstance(x,str) else 'b' if isinstance(x,bytes) else 'i' if isinstance(x,int) else 'f' for x in args)
    out = oscstr(address) + oscstr(',' + types)
    for t, x in zip(types,args):
        if t == 's': out += oscstr(x)
        elif t == 'i': out += struct.pack('>i',int(x))
        elif t == 'f': out += struct.pack('>f',float(x))
        elif t == 'b': out += struct.pack('>i',len(x)) + x + b'\0'*(-len(x)%4)
        else: raise ValueError(t)
    return out


def unpack(data):
    if data.startswith(b'#bundle\0'):
        pos = 16
        result = []
        while pos < len(data):
            size = struct.unpack_from('>i',data,pos)[0]
            pos += 4
            result.extend(unpack(data[pos:pos+size]))
            pos += size
        return result
    def string(pos):
        end = data.index(0,pos)
        return data[pos:end].decode('utf-8'), (end+4) & ~3
    address, pos = string(0)
    if pos == len(data): return [(address,'',[])]
    types, pos = string(pos)
    if not types.startswith(','): raise ValueError('OSC bez przecinka typów')
    args = []
    for t in types[1:]:
        if t == 's': x,pos = string(pos)
        elif t in ('i','f'):
            x = struct.unpack_from('>'+t,data,pos)[0]; pos += 4
        elif t == 'b':
            n = struct.unpack_from('>i',data,pos)[0];pos += 4
            x = data[pos:pos+n];pos += (n+3)&~3
        else: raise ValueError('Nieobsługiwany typ OSC '+t)
        args.append(x)
    return [(address,types[1:],args)]


def jsonable(x):
    if isinstance(x,bytes): return {'base64':base64.b64encode(x).decode('ascii')}
    if isinstance(x,(tuple,list)): return [jsonable(a) for a in x]
    return x


def suffixes(path, n):
    parts = path.strip('/').split('/')
    last = parts[-1]
    if parts[0] == 'config':
        return {'chlink':[f'{i}-{i+1}' for i in range(1,16,2)], 'buslink':['1-2','3-4','5-6'],
                'linkcfg':['preamp','eq','dyn','fdrmute'],
                'solo':['level','source','sourcetrim','chmode','busmode','dimatt','dim','mono','mute','dimpfl'],
                'amixenable':['X','Y'],'amixlock':['X','Y'],'mute':['1','2','3','4']}[last]
    if parts[0] == 'headamp': return ['gain','phantom'][:n]
    if parts[0] == 'routing': return ['src','pos'][:n]
    if parts[0] == 'fx': return [f'{i:02d}' for i in range(1,n+1)] if last == 'par' else ['type','insert']
    if last == 'config': return ['name','color','insrc','rtnsrc'] if parts[0]=='ch' else ['name','color','rtnsrc'][:n]
    if last == 'preamp': return ['rtntrim','rtnsw','invert','hpon','hpf'] if parts[0]=='ch' else ['rtntrim','rtnsw']
    if last == 'gate': return ['on','mode','thr','range','attack','hold','release','keysrc']
    if last == 'dyn': return ['on','mode','det','env','thr','ratio','knee','mgain','attack','hold','release','mix'] + ([] if parts[0]=='lr' else ['keysrc']) + ['auto']
    if last == 'filter': return ['on','type','f']
    if last == 'insert': return ['on','sel']  # MR18V2 fw 1.19: fxslot bez odpowiedzi
    if last == 'eq': return ['on','mode'][:n]
    if 'eq' in parts and last.isdigit(): return ['type','f','g','q']
    if last == 'geq':
        return ['20','25','31.5','40','50','63','80','100','125','160','200','250','315','400','500','630','800','1k','1k25','1k6','2k','2k5','3k15','4k','5k','6k3','8k','10k','12k5','16k','20k']
    if last == 'mix': return (['on','fader','pan'] if parts[0]=='lr' else ['on','fader','lr','pan'])[:n]
    if 'mix' in parts and last.isdigit(): return ['level','grpon','tap','pan'][:n]
    if last == 'grp': return ['dca','mute']
    if last == 'automix': return ['group','weight']
    if parts[0] == 'dca' and last.isdigit(): return ['on','fader']
    raise ValueError('Brak opisu węzła: '+path)


def to_osc(spec, token):
    k,a = spec
    if k == 's': return 's',token
    if k == 'b': return 'i',int(token=='ON')
    if k == 'm': return 'i',a.split(';').index(token)
    if k == 'g': return 'i',int(token[1:],2)
    if k == 'z': return 'f',0.0
    val = num(token)
    if k == 'x':
        if val == float('-inf'): v = 0.0
        elif val >= -10: v = (val+30)/40
        elif val >= -30: v = (val+50)/80
        elif val >= -60: v = (val+70)/160
        else: v = (val+90)/480
        return 'f',v
    lo,hi,steps = map(float,a.split(','))
    if k in ('l', 'e'):
        v = (val-lo)/(hi-lo) if k == 'l' else math.log(val/lo)/math.log(hi/lo)
        return 'f',(math.floor(v*steps+.5)/steps if steps else v)
    raise ValueError(spec)


def from_osc(spec, value):
    k,a = spec
    if k == 's': return str(value)
    if k == 'b': return 'ON' if value else 'OFF'
    if k == 'm': return a.split(';')[int(value)]
    if k == 'g': return '%'+format(int(value),'04b')
    if k == 'z': return '0'
    v = float(value)
    if k == 'x':
        if v <= 0: return '-oo'
        if v >= .5: out = v*40-30
        elif v >= .25: out = v*80-50
        elif v >= .0625: out = v*160-70
        else: out = v*480-90
    else:
        lo,hi,_ = map(float,a.split(','))
        out = lo+(hi-lo)*v if k=='l' else lo*(hi/lo)**v
    return format(round(out,5),'.8g')


class Model:
    def __init__(self, factory, schema):
        self.rows = czytaj_scn(factory.read_text(encoding='utf-8-sig'))
        self.schema = Schemat(schema.read_text(encoding='utf-8'))
        self.schema.sprawdz(self.rows)
        self.values = {}
        self.origins = {}
        self.node_writes = []
        self.unknown = set()
        for path in self.rows: self.expand(path)
    def expand(self,path):
        values = self.rows[path]
        specs = self.schema.pola(path,self.rows)
        pairs = [to_osc(s,t) for s,t in zip(specs,values)]
        self.values[path] = (''.join(t for t,_ in pairs), tuple(v for _,v in pairs))
        for i,(name,spec,token) in enumerate(zip(suffixes(path,len(values)),specs,values)):
            leaf = path+'/'+name
            self.values[leaf] = to_osc(spec,token)
            self.origins[leaf] = (path,i,spec)
    def node(self,path):
        specs = self.schema.pola(path,self.rows)
        _, values = self.values[path]
        fx = self.rows[path.rsplit('/', 1)[0]][0] if path.startswith('/fx/') and path.endswith('/par') else None
        tokens = [format_value(path, i, spec, value, fx)
                  for i, (spec, value) in enumerate(zip(specs, values))]
        return path+' '+' '.join(tokens)+'\n'
    def respond(self,path,types,args):
        if path in ('/xinfo','/info'):
            return [(path,'ssss',['127.0.0.1' if path=='/xinfo' else '0.0','SYMULATOR MR18 AOSC','MR18','symulator'])]
        if path == '/status': return [(path,'sss',['active','127.0.0.1','SYMULATOR MR18 AOSC'])]
        if path in ('/xremote','/meters'): return []
        if path == '/node' and args:
            node = '/'+str(args[0]).lstrip('/')
            if node in self.rows: return [('node','s',[self.node(node)])]
            self.unknown.add(node);return []
        if path == '/' and args and isinstance(args[0],str):
            line = args[0].strip()
            if not line.startswith('/'):line='/'+line
            parsed = czytaj_scn(line)
            for node,val in parsed.items():
                self.node_writes.append({'node':node,'values':val})
                self.rows[node] = val
                try: self.expand(node)
                except Exception: pass  # arbitralny węzeł też zapamiętany, jawnie w logu
            return []
        if args:
            if path in self.rows:
                specs=self.schema.pola(path,self.rows)
                if len(args)!=len(specs):
                    raise ValueError(f'{path}: argumenty {len(args)}, schemat {len(specs)}')
                self.rows[path]=[from_osc(spec,v) for spec,v in zip(specs,args)]
                self.node_writes.append({'node':path,'types':types,'args':args,'values':list(self.rows[path])})
                self.expand(path)
                self.values[path]=(types,tuple(args))
            elif len(args)==1:
                self.values[path]=(types,args[0])
                if path in self.origins:
                    node,i,spec=self.origins[path]
                    self.rows[node][i]=from_osc(spec,args[0])
                    self.expand(node)
                    self.values[path]=(types,args[0])
            else:
                self.values[path]=(types,tuple(args))
            # Dokument producenta, wiadomości serwera 1.3, wiersze 60–63:
            # echo po SET. AOSC wymaga go, co pokazuje sesja1 bez odpowiedzi.
            return [(path,types,args)]
        if path in self.values:
            typ,v = self.values[path]
            return [(path,typ,list(v) if isinstance(v,tuple) else [v])]
        if path in self.rows:
            return [(path,'s',[self.node(path)])]
        self.unknown.add(path)
        return []


# Zmiany stanu startowego względem BAZY: START musi wtedy wczytać scenę.
ZMIANY_STARTU = (('/headamp/09/gain', 'f', .25), ('/ch/09/mix/fader', 'f', .5),
                 ('/ch/10/dyn/thr', 'f', .5), ('/ch/01/config/name', 's', 'START'),
                 ('/bus/5/mix/on', 'i', 0), ('/fx/3/insert', 'i', 1))


def stan_startowy(baza, schema):
    """Tekst sceny w zapisie modelu: BAZA z ZMIANY_STARTU. Zastępuje fabryczną
    scenę Air Access 18, której projekt nie rozpowszechnia."""
    model = Model(baza, schema)
    for adres, typ, wartosc in ZMIANY_STARTU:
        model.respond(adres, typ, [wartosc])
    return ''.join(model.node(p) for p in model.rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--factory',type=Path,required=True)
    p.add_argument('--schema',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--port',type=int,default=10024)
    p.add_argument('--seconds',type=float,default=3600)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    model=Model(a.factory,a.schema)
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1',a.port))
    sock.settimeout(.2)
    stop=a.out/'STOP'
    if stop.exists(): raise RuntimeError('Istnieje STOP: wybierz nowy katalog wyników')
    (a.out/'gotowy.json').write_text(json.dumps({'pid':__import__('os').getpid(),'adres':sock.getsockname(),'wezly':len(model.rows),'pola':len(model.values),'python':sys.version,'model':'SYMULATOR, NIE SPRZĘT'}),encoding='utf-8')
    start=time.monotonic();seq=0
    with (a.out/'pakiety.jsonl').open('w',encoding='utf-8',buffering=1) as log:
        def record(direction,peer,raw,decoded,error=None):
            nonlocal seq
            seq+=1
            log.write(json.dumps({'seq':seq,'dt':time.monotonic()-start,'direction':direction,'peer':peer,'hex':raw.hex(),'osc':jsonable(decoded),'error':error},ensure_ascii=False)+'\n')
        try:
            while time.monotonic()-start<a.seconds and not stop.exists():
                try:raw,peer=sock.recvfrom(65535)
                except socket.timeout:continue
                if peer[0]!='127.0.0.1':continue
                decoded = []
                try:
                    decoded=unpack(raw)
                    record('RX',peer,raw,decoded)
                    for path,types,args in decoded:
                        for outpath,outtypes,outargs in model.respond(path,types,args):
                            msg=pack(outpath,outargs,outtypes)
                            sock.sendto(msg,peer)
                            record('TX',peer,msg,[(outpath,outtypes,outargs)])
                except Exception as e:
                    record('ERROR',peer,raw,[],repr(e))
                # Plik punktu kontrolnego aktualizowany po pakiecie z zapisem węzła.
                if any(path=='/' or (args and path in model.rows) for path,_,args in decoded):
                    (a.out/'stan.json').write_text(json.dumps(model.rows,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            sock.close()
            (a.out/'stan-koniec.json').write_text(json.dumps(model.rows,ensure_ascii=False,indent=2),encoding='utf-8')
            (a.out/'wezly-zapisane.json').write_text(json.dumps(model.node_writes,ensure_ascii=False,indent=2),encoding='utf-8')
            (a.out/'wynik.json').write_text(json.dumps({'pakiety':seq,'czas_s':time.monotonic()-start,'nieznane_odczyty':sorted(model.unknown),'wezly_zapisane':len(model.node_writes),'zamkniety':True},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc()
        raise
