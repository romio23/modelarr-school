"""Test: printlogboek en Spoolman-koppeling. Standaard tegen een nagebootste Spoolman; met SPOOLMAN_URL=http://host:7912
(een echte Spoolman met spoel 1) tegen die. Gebruik: python tests/test_printlog.py"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-log'); PORT = 8792
shutil.rmtree(ROOT, ignore_errors=True); M = f'{ROOT}/models'; os.makedirs(M); os.makedirs(f'{ROOT}/cfg')
trimesh.creation.box((40, 20, 10)).export(f'{M}/a.stl'); trimesh.creation.cylinder(8, 30).export(f'{M}/b.stl')
for f in ('a.stl', 'b.stl'): os.utime(f'{M}/{f}', (time.time() - 600,) * 2)
SP = os.environ.get('SPOOLMAN_URL'); MOCK = SP is None
class Mock(BaseHTTPRequestHandler):
    remaining = 1000.0
    def log_message(self, *a): pass
    def _send(self, code, obj):
        d = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(d))); self.end_headers(); self.wfile.write(d)
    def spool(self): return dict(id=1, archived=False, remaining_weight=Mock.remaining, filament=dict(name='PLA Basic Groen', material='PLA', color_hex='00AE42', vendor=dict(name='Bambu Lab')))
    def do_GET(self):
        if self.path == '/api/v1/info': self._send(200, dict(version='mock-1.0'))
        elif self.path == '/api/v1/spool/1': self._send(200, self.spool())
        elif self.path.startswith('/api/v1/spool'): self._send(200, [self.spool(), dict(id=2, archived=True, remaining_weight=5, filament=dict(name='Oud', material='PETG'))])
        else: self._send(404, {})
    def do_PUT(self):
        n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}')
        if self.path == '/api/v1/spool/1/use' and ('use_weight' in b) != ('use_length' in b): Mock.remaining -= b['use_weight']; self._send(200, self.spool())
        else: self._send(400, dict(message='ongeldig'))
if MOCK:
    srv_mock = HTTPServer(('127.0.0.1', 0), Mock); threading.Thread(target=srv_mock.serve_forever, daemon=True).start(); SP = f'http://127.0.0.1:{srv_mock.server_port}'
def remaining(): return json.load(urllib.request.urlopen(f'{SP}/api/v1/spool/1'))['remaining_weight']
def start():
    env = dict(os.environ, CONFIG_DIR=f'{ROOT}/cfg', MODELS_DIR=M, PORT=str(PORT), YIELD_TO_USERS='0')
    p = subprocess.Popen([sys.executable, 'app.py'], cwd=APP, env=env, stdout=open(f'{ROOT}/out.txt', 'a'), stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen(f'http://127.0.0.1:{PORT}/ping'); return p
        except Exception: time.sleep(.2)
    raise SystemExit('start mislukt')
def req(u, m='GET', b=None):
    r = urllib.request.Request(f'http://127.0.0.1:{PORT}' + u, method=m, data=json.dumps(b).encode() if b is not None else None, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read() or b'{}')
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
def wait(c, t=45):
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            if c(): return True
        except Exception: pass
        time.sleep(.5)
    return False
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
print('Spoolman:', 'nagebootst' if MOCK else SP)
srv = start()
try:
    wait(lambda: len(req('/api/library')[1]['models']) == 2 and all(m['status'] == 'ok' for m in req('/api/library')[1]['models']), 40)
    mid = next(m['id'] for m in req('/api/library')[1]['models'] if m['name'] == 'a'); pid = req('/api/printers', 'POST', {'name': 'P1S', 'bed_x': 256, 'bed_y': 256, 'bed_z': 256})[1]['id']
    gm = lambda: next(m for m in req('/api/library')[1]['models'] if m['name'] == 'a')
    # ---- printlogboek zonder Spoolman
    check('Spoolman niet ingesteld: status en spoelen', req('/api/spoolman/status')[1] == {'configured': False} and req('/api/spoolman/spools')[0] == 502 and req('/api/library')[1]['spoolman'] is False)
    check('ongeldig resultaat / gewicht / waarde: 400', all(req(f'/api/models/{mid}/prints', 'POST', b)[0] == 400 for b in ({'result': 'misschien'}, {'result': 'ok', 'grams': -3}, {'result': 'ok', 'grams': 'veel'}, {'result': 'ok', 'plate': 'x'})))
    check('mislukte print loggen verandert de printstatus niet', req(f'/api/models/{mid}/prints', 'POST', {'result': 'failed', 'printer_id': pid, 'notes': 'warping'})[0] == 200 and gm()['printed'] == '' and gm()['prints_failed'] == 1)
    r = req(f'/api/models/{mid}/prints', 'POST', {'result': 'ok', 'printer_id': pid, 'grams': 12.5, 'plate': 2, 'notes': ' 0.2 mm ', 'ts': 1700000000})
    lg = req(f'/api/models/{mid}/prints')[1]
    check('geslaagde print: gelogd met printer, plaat, gewicht; model wordt "geprint"', r[0] == 200 and gm()['printed'] == 'printed' and gm()['prints_ok'] == 1 and lg[1]['printer'] == 'P1S' and lg[1]['plate'] == 2 and lg[1]['grams'] == 12.5 and lg[1]['notes'] == '0.2 mm', lg[1])
    check('logboek: nieuwste eerst, laatste printdatum in de bibliotheek', lg[0]['result'] == 'failed' and gm()['last_print'] > 1700000000)
    check('onbekende printer wordt genegeerd, niet opgeslagen', req(f'/api/models/{mid}/prints', 'POST', {'result': 'ok', 'printer_id': 999})[0] == 200 and req(f'/api/models/{mid}/prints')[1][0]['printer'] is None)
    req(f"/api/prints/{req(f'/api/models/{mid}/prints')[1][0]['id']}", 'DELETE'); check('logregel verwijderen', len(req(f'/api/models/{mid}/prints')[1]) == 2)
    # ---- Spoolman
    check('adres zonder http(s) geweigerd', req('/api/settings', 'POST', {'spoolman_url': 'ftp://x'})[0] == 400)
    req('/api/settings', 'POST', {'spoolman_url': 'http://127.0.0.1:1'}); st = req('/api/spoolman/status')[1]
    check('onbereikbaar adres: duidelijke melding, ook in de gezondheidscontrole', st['configured'] and not st['ok'] and 'niet bereikbaar' in st['error'] and any('Spoolman' in h['msg'] for h in req('/api/status')[1]['health']), st.get('error'))
    s, r = req(f'/api/models/{mid}/prints', 'POST', {'result': 'ok', 'grams': 5, 'spool_id': 1, 'deduct': True})
    check('aftrekken terwijl Spoolman onbereikbaar is: 502 en niets opgeslagen', s == 502 and 'Niets opgeslagen' in r['error'] and len(req(f'/api/models/{mid}/prints')[1]) == 2, r.get('error'))
    req('/api/settings', 'POST', {'spoolman_url': SP + '/'}); st = req('/api/spoolman/status')[1]
    check('verbonden met Spoolman (slash aan het eind wordt genegeerd)', st.get('ok') is True and st.get('version'), st)
    sp = req('/api/spoolman/spools')[1]
    check('spoelen: label, materiaal, kleur, restgewicht; gearchiveerde niet', sp and sp[0]['id'] == 1 and sp[0]['label'] == 'Bambu Lab PLA Basic Groen' and sp[0]['material'] == 'PLA' and sp[0]['color'] == '00AE42' and all(x['id'] != 2 for x in sp), sp)
    before = remaining(); r = req(f'/api/models/{mid}/prints', 'POST', {'result': 'ok', 'grams': 12.5, 'spool_id': 1, 'deduct': True, 'spool': 'Bambu Lab PLA Basic Groen'})
    entry = req(f'/api/models/{mid}/prints')[1][0]
    check('verbruik afgetrokken in Spoolman en gelogd', r[0] == 200 and r[1]['deducted'] and abs(before - remaining() - 12.5) < 1e-6 and entry['spool'] == 'Bambu Lab PLA Basic Groen' and entry['spool_id'] == 1, (before, remaining()))
    after = remaining(); req(f"/api/prints/{entry['id']}", 'DELETE')
    check('logregel verwijderen draait het verbruik in Spoolman niet terug', abs(remaining() - after) < 1e-9)
    check('spoel gekozen maar geen gewicht: niets afgetrokken, wel gelogd', req(f'/api/models/{mid}/prints', 'POST', {'result': 'ok', 'spool_id': 1, 'deduct': True})[0] == 200 and abs(remaining() - after) < 1e-9 and req(f'/api/models/{mid}/prints')[1][0]['spool'] is None)
    import sqlite3
    n0 = sqlite3.connect(f'{ROOT}/cfg/library.db').execute('select count(*) from prints').fetchone()[0]
    os.remove(f'{M}/a.stl'); req('/api/tasks/scan/run', 'POST'); wait(lambda: all(m['name'] != 'a' for m in req('/api/library')[1]['models']), 20)
    n1 = sqlite3.connect(f'{ROOT}/cfg/library.db').execute('select count(*) from prints').fetchone()[0]
    check('bestand verwijderd: model en bijbehorend logboek verdwijnen (cascade)', n0 > 0 and n1 == 0, (n0, n1))
finally:
    srv.terminate(); srv.wait()
print('--- fouten in uitvoer:', [l for l in open(f'{ROOT}/out.txt') if 'Traceback' in l][:2])
sys.exit(1 if bad else 0)
