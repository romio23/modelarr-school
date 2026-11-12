"""Test: ingebedde thumbnails, index-only formaten, eigen thumbnail, pauzeren, notities/favoriet/printstatus,
rechten per root, netwerkshare-detectie en de uitbreiding van de standaard extensielijst. Gebruik: python tests/test_features.py"""
import base64, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile
import trimesh
from PIL import Image
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-feat'); PORT = 8795
shutil.rmtree(ROOT, ignore_errors=True); M = f'{ROOT}/models'; os.makedirs(M); os.makedirs(f'{ROOT}/cfg')
def png(color, size=(256, 256)):
    b = io.BytesIO(); Image.new('RGB', size, color).save(b, 'PNG'); return b.getvalue()
box = trimesh.creation.box((40, 20, 10)); NS = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
mesh = ''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in box.vertices); tris = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in box.faces)
with zipfile.ZipFile(f'{M}/plate.3mf', 'w') as z:
    z.writestr('3D/3dmodel.model', f'<?xml version="1.0"?><model unit="millimeter" {NS}><resources><object id="1"><mesh><vertices>{mesh}</vertices><triangles>{tris}</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    z.writestr('Metadata/plate_1.png', png((220, 20, 20)))
box.export(f'{M}/plain.stl')
b64 = base64.b64encode(png((20, 20, 220), (100, 50))).decode(); lines = '\n'.join('; ' + b64[i:i + 60] for i in range(0, len(b64), 60))
open(f'{M}/print.gcode', 'w').write(f'; generated\n;\n; thumbnail begin 100x50 {len(b64)}\n{lines}\n; thumbnail end\nG28\n')
with zipfile.ZipFile(f'{M}/part.fcstd', 'w') as z: z.writestr('Document.xml', '<x/>'); z.writestr('thumbnails/Thumbnail.png', png((20, 200, 20)))
open(f'{M}/cad.step', 'w').write('ISO-10303-21;'); open(f'{M}/leeg.gcode', 'w').write('G28\nG1 X1\n')
for f in os.listdir(M): os.utime(f'{M}/{f}', (time.time() - 600,) * 2)
def start(extra=None):
    env = dict(os.environ, CONFIG_DIR=f'{ROOT}/cfg', MODELS_DIR=M, PORT=str(PORT), YIELD_TO_USERS='0', **(extra or {}))
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
lib = lambda: {m['name']: m for m in req('/api/library')[1]['models']}
def center(name):
    im = Image.open(f"{ROOT}/cfg/thumbs/{lib()[name]['id']}.png").convert('RGB'); return im.getpixel((im.width // 2, im.height // 2)), im.size
red = lambda p: p[0] > 180 and p[1] < 80; blue = lambda p: p[2] > 180 and p[0] < 80; green = lambda p: p[1] > 150 and p[0] < 80 and p[2] < 80
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
srv = start()
try:
    wait(lambda: len(lib()) == 6 and all(m['status'] in ('ok', 'unsupported', 'failed') for m in lib().values()))
    L = lib(); st = {n: m['status'] for n, m in L.items()}
    check('statussen: previews ok, index-only unsupported', st == dict(plate='ok', plain='ok', print='ok', part='ok', cad='unsupported', leeg='unsupported'), st)
    check('3MF: ingebedde afbeelding (rood) + afmetingen blijven bekend', red(center('plate')[0]) and L['plate']['dims'] and L['plate']['tris'] == 12, center('plate'))
    check('STL: zelf gerenderd (niet rood/blauw)', not red(center('plain')[0]) and not blue(center('plain')[0]))
    check('G-code: base64-afbeelding (blauw) uit commentaar', blue(center('print')[0]) and L['print']['dims'] is None, center('print'))
    check('FCStd: thumbnail uit zip (groen)', green(center('part')[0]))
    check('G-code zonder afbeelding: melding i.p.v. fout', 'ingebedde' in (L['leeg']['error'] or ''), L['leeg']['error'])
    s, w = req('/api/wanted'); check('Gewenst toont alleen mislukte; index-only als aantal', w['items'] == [] and w['unsupported'] == 2, w)
    # bron wisselen => alles opnieuw
    req('/api/settings', 'POST', {'thumb_source': 'render'}); wait(lambda: all(m['status'] != 'pending' and m['status'] != 'processing' for m in lib().values())); time.sleep(1)
    check('thumb_source=render: 3MF zelf gerenderd', not red(center('plate')[0]), center('plate')[0])
    req('/api/settings', 'POST', {'thumb_source': 'embedded'}); wait(lambda: red(center('plate')[0]), 20)
    check('terug naar ingebouwd: weer rood', red(center('plate')[0]))
    # notities, favoriet, bron, printstatus
    pid = lib()['plain']['id']
    check('bron zonder http(s) geweigerd', req(f'/api/models/{pid}', 'POST', {'source_url': 'javascript:alert(1)'})[0] == 400)
    check('ongeldige printstatus geweigerd', req(f'/api/models/{pid}', 'POST', {'printed': 'misschien'})[0] == 400)
    req(f'/api/models/{pid}', 'POST', {'notes': 'ABS, 0.2mm', 'favorite': True, 'printed': 'toprint', 'source_url': 'https://www.printables.com/model/1'}); m = lib()['plain']
    check('notities/favoriet/printstatus/bron opgeslagen', (m['notes'], m['favorite'], m['printed'], m['source_url']) == ('ABS, 0.2mm', True, 'toprint', 'https://www.printables.com/model/1'))
    ids = [lib()[n]['id'] for n in ('plate', 'print')]; req('/api/models/bulk', 'POST', {'model_ids': ids, 'favorite': True, 'printed': 'printed'})
    check('groepsactie favoriet + geprint', all(lib()[n]['favorite'] and lib()[n]['printed'] == 'printed' for n in ('plate', 'print')))
    # rechten per root: standaard alleen indexeren
    check('hernoemen geweigerd zonder toestemming (403)', req(f'/api/models/{pid}', 'POST', {'filename': 'nieuwe_naam'})[0] == 403 and os.path.exists(f'{M}/plain.stl'))
    check('weergavenaam wijzigen mag altijd', req(f'/api/models/{pid}', 'POST', {'display': 'Mijn doos'})[0] == 200 and lib()['plain']['display'] == 'Mijn doos' and lib()['plain']['can_rename'] is False)
    rid = req('/api/roots')[1][0]['id']; req(f'/api/roots/{rid}', 'PUT', {'allow_write': True})
    check('na toestemming wel hernoemen', req(f'/api/models/{pid}', 'POST', {'filename': 'nieuwe_naam'})[0] == 200 and os.path.exists(f'{M}/nieuwe_naam.stl') and lib()['nieuwe_naam']['can_rename'])
    # eigen thumbnail blijft staan bij herbouwen
    pid = lib()['nieuwe_naam']['id']; buf = io.BytesIO(); Image.new('RGB', (300, 200), (20, 200, 20)).save(buf, 'PNG')
    s, _ = req(f'/api/models/{pid}/thumb', 'POST', {'data': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()})
    check('eigen thumbnail (groen, vierkant gemaakt)', s == 200 and green(center('nieuwe_naam')[0]) and lib()['nieuwe_naam']['thumb_custom'] and center('nieuwe_naam')[1][0] == center('nieuwe_naam')[1][1])
    req('/api/tasks/rebuild/run', 'POST'); wait(lambda: all(m['status'] == 'ok' for n, m in lib().items() if n not in ('cad', 'leeg')), 20); time.sleep(1)
    check('herbouwen laat eigen thumbnail staan', green(center('nieuwe_naam')[0]))
    req(f'/api/models/{pid}/regen', 'POST'); wait(lambda: not green(center('nieuwe_naam')[0]), 15)
    check('"Thumbnail opnieuw" herstelt de automatische', not green(center('nieuwe_naam')[0]) and not lib()['nieuwe_naam']['thumb_custom'])
    check('ongeldige afbeelding geweigerd', req(f'/api/models/{pid}/thumb', 'POST', {'data': 'data:image/png;base64,AAAA'})[0] == 400)
    # pauzeren
    req('/api/queue/pause', 'POST', {'paused': True}); box.export(f'{M}/nieuw.stl'); os.utime(f'{M}/nieuw.stl', (time.time() - 600,) * 2); req('/api/tasks/scan/run', 'POST')
    appeared = wait(lambda: 'nieuw' in lib(), 30); time.sleep(4)
    check('gepauzeerd: nieuw model blijft pending', appeared and lib()['nieuw']['status'] == 'pending' and req('/api/queue')[1]['paused'] is True, lib().get('nieuw', {}).get('status'))
    req('/api/queue/pause', 'POST', {'paused': False}); check('hervat: thumbnail verschijnt', wait(lambda: lib()['nieuw']['status'] == 'ok', 20))
finally:
    srv.terminate(); srv.wait()
# standaard extensielijst: oude ongewijzigde standaard wordt vervangen
con = sqlite3.connect(f'{ROOT}/cfg/library.db'); con.execute("INSERT OR REPLACE INTO settings VALUES('extensions','stl,3mf,obj,ply,glb,gltf')"); con.commit(); con.close()
srv = start()
try:
    e = req('/api/settings')[1]['extensions']; check('oude standaard-extensies vervangen door ruimere lijst', 'step' in e and 'gcode' in e and 'zip' not in e, e[:60] + '…')
finally:
    srv.terminate(); srv.wait()
# netwerkshare-detectie (los, met nagebootste /proc/mounts)
os.environ['CONFIG_DIR'] = f'{ROOT}/cfg2'; sys.path.insert(0, APP); import app as A
mounts = '/dev/sda1 / ext4 rw 0 0\nserver:/export /mnt/nas nfs4 rw 0 0\n//nas/share /mnt/smb cifs rw 0 0\n/dev/md0 /volume1 btrfs rw 0 0\n/dev/sdb1 /mnt/nas/lokaal ext4 rw 0 0'
r = {p: A.fs_type(p, mounts) for p in ('/mnt/nas/config', '/mnt/smb/x/y', '/volume1/docker/config', '/mnt/nas/lokaal/db', '/mnt/nasty', '/home/x')}
check('fs_type herkent nfs/cifs/lokaal (langste mount wint)', r == {'/mnt/nas/config': 'nfs4', '/mnt/smb/x/y': 'cifs', '/volume1/docker/config': 'btrfs', '/mnt/nas/lokaal/db': 'ext4', '/mnt/nasty': 'ext4', '/home/x': 'ext4'}, r)
import time as _t
A.LAST_USER[0] = 0; t0 = _t.time(); A.yield_to_users(); idle = _t.time() - t0
A.LAST_USER[0] = _t.time(); t0 = _t.time(); A.yield_to_users(cap=0.6); busy = _t.time() - t0
check('wachten voor gebruikers: direct als het rustig is, hooguit de limiet als iemand de app gebruikt', idle < 0.2 and 0.5 < busy < 1.2, (round(idle, 2), round(busy, 2)))
c = A.app.test_client(); A.LAST_USER[0] = 0; c.get('/api/fs?path=/tmp', headers={'X-Auto': '1'}); auto = A.LAST_USER[0]; c.get('/api/fs?path=/tmp'); hand = A.LAST_USER[0]
check('automatisch herladen (X-Auto) telt niet als gebruik, een handmatige actie wel', auto == 0 and hand > 0)
print('--- fouten in uitvoer:', [l for l in open(f'{ROOT}/out.txt') if 'Traceback' in l][:2])
sys.exit(1 if bad else 0)
