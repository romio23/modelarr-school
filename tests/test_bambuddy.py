"""Bambuddy-koppeling tegen een nagebootste Bambuddy: model versturen (bibliotheek/wachtrij, multipart, API-sleutel), printgeschiedenis
overnemen (koppelen op naam, eenmalig, ook na verwijderen), foutmeldingen en dat de sleutel nooit naar de browser gaat."""
import json, os, re, sys, tempfile, threading, time, zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
d = tempfile.mkdtemp(); os.environ['CONFIG_DIR'] = os.path.join(d, 'cfg')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))

KEY = 'geheime-sleutel-123'
QMISS = [False]
LOG = []  # (methode, pad, body)
LIB = {}
PLOG = [
    dict(id=1, print_name='Rack bracket', printer_name='P1S', status='completed', completed_at='2026-10-01T10:00:00', filament_used_grams=12.5),
    dict(id=2, print_name='Rack bracket.gcode.3mf', printer_name='P1S', status='failed', completed_at='2026-10-02T10:00:00', failure_reason='spaghetti', filament_used_grams=3),
    dict(id=3, print_name='Dubbel', printer_name='P1S', status='completed', completed_at='2026-10-03T10:00:00'),
    dict(id=4, print_name='Onbekend model', printer_name='P1S', status='completed', completed_at='2026-10-03T11:00:00'),
    dict(id=5, print_name='Rack bracket', printer_name='P1S', status='printing'),
    dict(id=6, print_name='Rack bracket', printer_name='P1S', status='cancelled'),
]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def auth(self):
        if self.headers.get('X-API-Key') != KEY: self.send(401, {'detail': 'bad key'}); return False
        return True
    def body(self): return self.rfile.read(int(self.headers.get('Content-Length', 0)))
    def do_GET(self):
        if not self.auth(): return
        if self.path.startswith('/api/v1/queue/'): return self.send(404, {}) if self.path.endswith('/404') or QMISS[0] else self.send(200, dict(id=55, status='pending', printer_id=7, library_file_id=2))
        if self.path == '/api/v1/printers/7/status': return self.send(200, dict(id=7, connected=True, ams=[dict(id=0, is_ams_ht=False, tray=[dict(id=0, tray_color=None, tray_type=None, exists=False), dict(id=1, tray_color='FFFFFFFF', tray_type='PLA', tray_sub_brands='', remain=-1, exists=True), dict(id=2, tray_color='F98C36FF', tray_type='PLA', tray_sub_brands='Bambu PLA Basic', remain=64, exists=True), dict(id=3, tray_color='00000000', tray_type='PLA', exists=True)])]))
        if self.path == '/api/v1/printers/8/status': return self.send(200, dict(id=8, connected=True, ams=[dict(id=1, is_ams_ht=True, tray=[dict(id=0, tray_color='F98C36FF', tray_type='PLA', remain=-1, exists=True)])], vt_tray=dict(id=254, tray_color='1F4FD8FF', tray_type='PETG', exists=True)))
        if self.path.startswith('/api/v1/printers/'): return self.send(200, [dict(id=7, name='P1S werkplaats'), dict(id=8, name='X1C')])
        if self.path.startswith('/api/v1/print-log/'):
            q = dict(x.split('=') for x in self.path.split('?')[1].split('&')); o, l = int(q['offset']), int(q['limit'])
            return self.send(200, dict(items=PLOG[o:o + l], total=len(PLOG)))
        self.send(404, {})
    def do_POST(self):
        if not self.auth(): return
        b = self.body(); LOG.append((self.path, b))
        if self.path == '/api/v1/library/files':
            m = re.search(rb'filename="([^"]*)"\r\n.*?\r\n\r\n(.*)\r\n--', b, re.S); LIB[len(LIB) + 1] = (m.group(1).decode(), m.group(2))
            return self.send(200, dict(id=len(LIB), filename=m.group(1).decode(), file_type='3mf', file_size=len(m.group(2)), thumbnail_path='x', duplicate_of=None))
        if self.path == '/api/v1/library/files/add-to-queue':
            j = json.loads(b)
            if j.get('printer_id') == 99: return self.send(200, dict(added=[], errors=[dict(file_id=1, filename='x', error='printer offline')]))
            if j.get('printer_id') == 97: return self.send(400, dict(detail=dict(message='No files could be added to the queue.', errors=[dict(file_id=1, filename='x.stl', error='Not a sliced file. Only .gcode or .gcode.3mf files can be printed.')])))
            if j.get('printer_id') == 98: return self.send(200, dict(added=[], errors=[]))
            return self.send(200, dict(added=[dict(file_id=j['file_ids'][0], filename='x', queue_item_id=55)], errors=[]))
        self.send(404, {})
srv = HTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_port}'

A.init()
c = A.app.test_client(); HDR = {'X-Requested-With': 'modelbib'}
def api(u, m='GET', b=None): r = c.open(u, method=m, json=b, headers=HDR); return r.status_code, (r.get_json(silent=True) or {})

os.makedirs(f'{d}/models/sub', exist_ok=True)
import io
def zipped(name, data):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z: z.writestr(name, data)
    return b.getvalue()
SLICED = zipped('Metadata/plate_1.gcode', 'G1 X1\n' * 200); UNSLICED = zipped('3D/3dmodel.model', '<model/>' * 20)
files = {'Rack bracket': ('3mf', SLICED), 'Plat': ('3mf', UNSLICED), 'Los': ('stl', b'solid x\nendsolid'), 'Dubbel': ('3mf', b'PK-dubbel' * 10), 'Dubbel ': ('3mf', b'PK-dubbel2'), 'Notitie': ('txt', b'hoi')}
ids = {}
with A.db() as cn:
    cn.execute("INSERT INTO roots(path) VALUES(?)", (f'{d}/models',))
    for i, (n, (ext, data)) in enumerate(files.items()):
        p = f'{d}/models/{i}-{n.strip()}.{ext}'; open(p, 'wb').write(data)
        nm = n.strip() if n != 'Dubbel ' else 'Dubbel'
        ids[n] = cn.execute("INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,thumb_status) VALUES(1,?,?,?,?,?,?,'ok')", (p, nm, ext, len(data), time.time(), time.time())).lastrowid

check('niet ingesteld: status zegt niet geconfigureerd, versturen en synchroniseren geven een duidelijke fout',
      api('/api/bambuddy/status')[1].get('configured') is False and api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'library'})[0] == 502 and api('/api/bambuddy/sync', 'POST')[0] == 502)
check('adres zonder http(s) wordt geweigerd', api('/api/settings', 'POST', {'bambuddy_url': 'ftp://x'})[0] == 400)
api('/api/settings', 'POST', {'bambuddy_url': URL + '/', 'bambuddy_key': 'verkeerd'})
s = api('/api/settings')[1]
check('adres opgeslagen zonder slot-slash; sleutel wordt nooit teruggegeven, alleen dat hij er is', s['bambuddy_url'] == URL and s['bambuddy_key_set'] is True and 'verkeerd' not in json.dumps(s))
st = api('/api/bambuddy/status')[1]
check('verkeerde sleutel: duidelijke melding over de API-sleutel', st['configured'] and not st['ok'] and 'API-sleutel' in st['error'], st.get('error', '')[:60])
api('/api/settings', 'POST', {'bambuddy_url': URL, 'bambuddy_key': KEY})
st = api('/api/bambuddy/status')[1]
check('juiste sleutel: printers komen terug', st['ok'] and [p['name'] for p in st['printers']] == ['P1S werkplaats', 'X1C'], str(st)[:80])
api('/api/settings', 'POST', {'bambuddy_url': URL})
check('opslaan zonder sleutel behoudt de opgeslagen sleutel', api('/api/bambuddy/status')[1]['ok'])
check('de bibliotheek meldt dat Bambuddy aanstaat (voor de knop)', api('/api/library')[1]['bambuddy'] is True)
cl = api('/api/bambuddy/colors')[1]
check('kleuren: alleen slots met een echte spoel (leeg en doorzichtig tellen niet)', cl['ok'] and [len(p['slots']) for p in cl['printers']] == [2, 2], str([len(p['slots']) for p in cl['printers']]))
cs = {(c['name'], c['material']): c for c in cl['colors']}
check('kleuren: namen, materiaal en samengevoegd over printers (oranje zit in twee printers)', set(cs) == {('Wit', 'PLA'), ('Oranje', 'PLA'), ('Blauw', 'PETG')} and sorted(cs[('Oranje', 'PLA')]['printers']) == ['P1S werkplaats', 'X1C'], str(sorted(cs)))
check('kleuren: resterend alleen als bekend (-1 = onbekend), externe spoel meegenomen', cs[('Wit', 'PLA')]['remain'] is None and cs[('Oranje', 'PLA')]['remain'] == 64 and any(x['slot'] == 'Externe spoel' for p in cl['printers'] for x in p['slots']))
check('kleuren: één printer opvragen', [p['id'] for p in api('/api/bambuddy/colors?printer=8')[1]['printers']] == [8])
import app as _A
check('kleurnamen kloppen bij echte AMS-kleuren uit de praktijk', [_A.bb_color_name(x) for x in ('FFFFFF', '161616', 'F98C36', '00AE42', '1F4FD8')] == ['Wit', 'Zwart', 'Oranje', 'Groen', 'Blauw'])

r = api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'library'})
check('naar bibliotheek: bestand komt ongewijzigd aan met de juiste naam', r[0] == 200 and LIB[1][0] == '0-Rack bracket.3mf' or LIB[1][0].endswith('Rack bracket.3mf'), str(LIB.get(1, ('?',))[0]))
check('  inhoud is byte-voor-byte gelijk', LIB[1][1] == files['Rack bracket'][1])
check('  bibliotheek-actie zet niets in de wachtrij', not any(p.endswith('add-to-queue') for p, _ in LOG))
r = api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 7})
q = [json.loads(b) for p, b in LOG if p.endswith('add-to-queue')]
check('naar wachtrij: juiste bestand en printer, queue-id terug', r[0] == 200 and r[1]['queue_item_id'] == 55 and q == [dict(file_ids=[2], printer_id=7)], str(r))
check('wachtrij: de status van het item wordt gecontroleerd en teruggegeven', r[1]['queue_status'] == 'pending')
r = api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 98})
check('leeg antwoord (niets aangemaakt, geen fout) wordt nooit als gelukt gemeld', r[0] == 502 and 'niets in de wachtrij' in r[1]['error'], str(r))
QMISS[0] = True; r = api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 7}); QMISS[0] = False
check('item niet terug te vinden in de wachtrij: duidelijke melding', r[0] == 502 and 'niet terug te vinden' in r[1]['error'], str(r))
n_up = len(LIB)
r = api(f"/api/models/{ids['Los']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 7})
check('STL in de wachtrij: vooraf geweigerd met uitleg, er wordt niets geüpload', r[0] == 400 and 'geslicede' in r[1]['error'] and len(LIB) == n_up, str(r))
r = api(f"/api/models/{ids['Plat']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 7})
check('3MF zonder G-code (niet gesliced) in de wachtrij: ook vooraf geweigerd', r[0] == 400 and len(LIB) == n_up)
check('maar naar de bibliotheek mogen STL en ongeslicede 3MF wel', api(f"/api/models/{ids['Los']}/bambuddy", 'POST', {'action': 'library'})[0] == 200 and api(f"/api/models/{ids['Plat']}/bambuddy", 'POST', {'action': 'library'})[0] == 200)
r = api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 97})
check('foutantwoord van Bambuddy wordt leesbaar getoond (geen ruwe JSON)', r[0] == 502 and 'Not a sliced file' in r[1]['error'] and '{' not in r[1]['error'], r[1].get('error', ''))
check('wachtrij zonder printer wordt geweigerd', api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'queue'})[0] == 400)
r = api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'queue', 'printer_id': 99})
check('fout van Bambuddy bij de wachtrij komt als melding terug', r[0] == 502 and 'printer offline' in r[1]['error'])
check('niet-ondersteund bestandstype (txt) wordt geweigerd', api(f"/api/models/{ids['Notitie']}/bambuddy", 'POST', {'action': 'library'})[0] == 400)
check('onbekende actie wordt geweigerd; er is geen "start print"-actie', api(f"/api/models/{ids['Rack bracket']}/bambuddy", 'POST', {'action': 'print', 'printer_id': 7})[0] == 400
      and not any('/print' in p for p, _ in LOG))
with A.db() as cn: ev = [x[0] for x in cn.execute("SELECT message FROM history WHERE event='Bambuddy'")]
check('verzenden staat in de geschiedenis', len(ev) == 4 and any('in de wachtrij' in e for e in ev), str(ev))

r = api('/api/bambuddy/sync', 'POST')
x = r[1].get('result', {})
with A.db() as cn: pr = [dict(z) for z in cn.execute('SELECT * FROM prints ORDER BY ts')]
check('sync: gelukt en mislukt komen binnen op het juiste model', r[0] == 200 and x['added'] == 2 and [(p['model_id'], p['result']) for p in pr] == [(ids['Rack bracket'], 'ok'), (ids['Rack bracket'], 'failed')], str(x))
check('  gram, printer, tijd (UTC) en reden worden overgenomen', pr[0]['grams'] == 12.5 and pr[0]['printer'] == 'P1S' and abs(pr[0]['ts'] - 1790848800) < 1 and 'spaghetti' in pr[1]['notes'], str(pr[0]))
check('  dubbelzinnige naam (twee modellen) en onbekend model worden niet gekoppeld maar geteld', x['unmatched'] == 2 and 'Onbekend model' in x['examples'] and 'Dubbel' in x['examples'], str(x))
check('  bezig/afgebroken prints worden overgeslagen', x['other'] == 2)
check('  model krijgt de markering "geprint"', api('/api/library')[1]['models'][0] is not None and any(m['printed'] == 'printed' for m in api('/api/library')[1]['models'] if m['id'] == ids['Rack bracket']))
r = api('/api/bambuddy/sync', 'POST')
with A.db() as cn: n = cn.execute('SELECT COUNT(*) FROM prints').fetchone()[0]
check('tweede sync: niets dubbel', r[1]['result']['added'] == 0 and n == 2, str(r[1]['result']))
pid = pr[0]['id']; api(f'/api/prints/{pid}', 'DELETE'); api('/api/bambuddy/sync', 'POST')
with A.db() as cn: n = cn.execute('SELECT COUNT(*) FROM prints').fetchone()[0]
check('een hier verwijderde regel komt niet terug', n == 1)
PLOG.append(dict(id=9, print_name='Rack bracket', printer_name='X1C', status='completed', completed_at='2026-10-05T10:00:00'))
check('nieuwe regel in Bambuddy komt bij de volgende sync binnen', api('/api/bambuddy/sync', 'POST')[1]['result']['added'] == 1)
api('/api/settings', 'POST', {'bambuddy_key_clear': True})
check('sleutel wissen zet de koppeling uit', api('/api/bambuddy/status')[1]['configured'] is False and api('/api/library')[1]['bambuddy'] is False)
srv.shutdown()
api('/api/settings', 'POST', {'bambuddy_url': 'http://127.0.0.1:9', 'bambuddy_key': 'x'})
st = api('/api/bambuddy/status')[1]
check('Bambuddy onbereikbaar: duidelijke melding', not st['ok'] and 'niet bereikbaar' in st['error'], st.get('error', '')[:70])
print('ALLES GOED' if not bad else 'FOUT: ' + ', '.join(bad)); sys.exit(1 if bad else 0)
