"""Test: thumbnails herstellen (ontbrekend / verkeerd model / zonder kenmerk), back-up met thumbnails, bewaartermijn, herstel.
Gebruik: python tests/test_backup.py"""
import base64, glob, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile
import trimesh
from PIL import Image
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-bak'); PORT = 8794
shutil.rmtree(ROOT, ignore_errors=True); M = f'{ROOT}/models'; os.makedirs(M); TH = f'{ROOT}/cfg/thumbs'; BK = f'{ROOT}/cfg/backups'
trimesh.creation.box((40, 20, 10)).export(f'{M}/a.stl'); trimesh.creation.cylinder(8, 30).export(f'{M}/b.stl'); trimesh.creation.icosphere(radius=12).export(f'{M}/c.stl')
for f in os.listdir(M): os.utime(f'{M}/{f}', (time.time() - 600,) * 2)
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
def wait(c, t=40):
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            if c(): return True
        except Exception: pass
        time.sleep(.4)
    return False
lib = lambda: {m['name']: m for m in req('/api/library')[1]['models']}
allok = lambda: len(lib()) == 3 and all(m['status'] == 'ok' for m in lib().values())
png = lambda n: f"{TH}/{lib()[n]['id']}.png"
def expected_tag(n):
    r = sqlite3.connect(f'{ROOT}/cfg/library.db').execute('SELECT id,size,mtime FROM models WHERE name=?', (n,)).fetchone(); return f'{r[0]}:{r[1]}:{r[2]}'
tag = lambda p: Image.open(p).info.get('modelbib')
events = lambda: [h['message'] for h in req('/api/history')[1] if h['event'] == 'Hersteld']
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
srv = start()
try:
    check('eerste import', wait(allok, 60))
    check('elke thumbnail draagt een kenmerk (id:grootte:datum)', all(tag(png(n)) == expected_tag(n) for n in 'abc'), tag(png('a')))
    # 1. ontbrekend
    os.remove(png('a')); req('/api/tasks/scan/run', 'POST')
    check('ontbrekende thumbnail wordt vanzelf opnieuw gemaakt', wait(lambda: allok() and os.path.exists(png('a'))) and any('ontbrak' in e for e in events()), events())
    # 2. thumbnail van een ander model (zoals na terugzetten van een oudere database)
    shutil.copy(png('b'), png('a')); req('/api/tasks/thumbcheck/run', 'POST')
    check('thumbnail van ander model wordt herkend en vervangen', wait(lambda: allok() and tag(png('a')) == expected_tag('a'), 30), tag(png('a')))
    # 3. oude thumbnail zonder kenmerk blijft geldig
    pb = png('b'); Image.open(pb).convert('RGB').save(pb, 'PNG'); m0 = os.path.getmtime(pb); assert tag(pb) is None
    req('/api/tasks/thumbcheck/run', 'POST'); time.sleep(3)
    check('thumbnail zonder kenmerk (van vóór deze versie) blijft staan', lib()['b']['status'] == 'ok' and os.path.getmtime(pb) == m0)
    # 4. eigen opname verloren
    buf = io.BytesIO(); Image.new('RGB', (200, 100), (20, 200, 20)).save(buf, 'PNG')
    req(f"/api/models/{lib()['c']['id']}/thumb", 'POST', {'data': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()})
    check('eigen opname draagt ook een kenmerk', lib()['c']['thumb_custom'] and tag(png('c')) == expected_tag('c'))
    os.remove(png('c')); req('/api/tasks/scan/run', 'POST')
    check('verloren eigen opname: automatische thumbnail, markering gereset', wait(lambda: allok() and os.path.exists(png('c')) and not lib()['c']['thumb_custom']))
    # 5. back-ups met thumbnails, bewaartermijn 2
    s = req('/api/settings')[1]; check('instellingen bevatten back-upopties', s['backup_keep'] == 7 and s['backup_thumbs'] is False)
    req('/api/settings', 'POST', {'backup_thumbs': True, 'backup_keep': 2})
    for i in range(3):
        n0 = len(glob.glob(f'{BK}/library-*.db')); req('/api/tasks/backup/run', 'POST'); wait(lambda: len(glob.glob(f'{BK}/library-*-thumbs.zip')) >= min(i + 1, 2) and os.path.getsize(sorted(glob.glob(f'{BK}/library-*-thumbs.zip'))[-1]) > 0, 10); time.sleep(1.3)
    dbs, zs = sorted(glob.glob(f'{BK}/library-*.db')), sorted(glob.glob(f'{BK}/library-*-thumbs.zip'))
    check('bewaartermijn: 2 database-back-ups en 2 thumbnail-zips', len(dbs) == 2 and len(zs) == 2, (len(dbs), len(zs)))
    check('zip bevat alle thumbnails', sorted(zipfile.ZipFile(zs[-1]).namelist()) == sorted(os.listdir(TH)), zipfile.ZipFile(zs[-1]).namelist())
    check('database-back-up is leesbaar', sqlite3.connect(dbs[-1]).execute('select count(*) from models').fetchone()[0] == 3)
    req('/api/settings', 'POST', {'backup_thumbs': False}); req('/api/tasks/backup/run', 'POST'); time.sleep(2)
    dbs2 = sorted(glob.glob(f'{BK}/library-*.db')); newest = os.path.basename(dbs2[-1])[:-3]
    check('zonder optie geen zip bij de nieuwste back-up', not os.path.exists(f'{BK}/{newest}-thumbs.zip') and len(dbs2) == 2)
finally:
    srv.terminate(); srv.wait()
# 6. herstel: thumbnails uit de zip terugzetten -> niets hoeft opnieuw
zs = sorted(glob.glob(f'{BK}/library-*-thumbs.zip')); shutil.rmtree(TH); os.makedirs(TH); zipfile.ZipFile(zs[-1]).extractall(TH)
before = len(events()) if False else None
srv = start()
try:
    time.sleep(6); L = lib()
    check('thumbnails uit zip teruggezet: alles meteen ok, niets opnieuw', all(m['status'] == 'ok' for m in L.values()) and not any('3×' in e for e in events()), events())
finally:
    srv.terminate(); srv.wait()
# 7. alleen database terugzetten, geen thumbnails
shutil.rmtree(TH); os.makedirs(TH)
srv = start()
try:
    check('database zonder thumbnails: alles wordt vanzelf opnieuw gemaakt', wait(lambda: allok() and all(os.path.exists(png(n)) for n in 'abc'), 40) and any('3×' in e and 'ontbrak' in e for e in events()), events())
finally:
    srv.terminate(); srv.wait()
print('--- fouten in uitvoer:', [l for l in open(f'{ROOT}/out.txt') if 'Traceback' in l][:2])
sys.exit(1 if bad else 0)
