"""Test: instelbare back-upmap. Back-ups komen altijd in die map (ook thumbnails), een ongeldige of verdwenen map geeft een
duidelijke fout zonder terugval naar een andere map, BACKUP_DIR geldt als standaard en de app-instelling gaat voor.
Gebruik: python tests/test_backup_dir.py"""
import glob, json, os, shutil, socket, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-bkdir')
shutil.rmtree(ROOT, ignore_errors=True); M = f'{ROOT}/models'; os.makedirs(M)
trimesh.creation.box((40, 20, 10)).export(f'{M}/a.stl'); trimesh.creation.cylinder(8, 30).export(f'{M}/b.stl'); trimesh.creation.icosphere(radius=12).export(f'{M}/c.stl')
for f in os.listdir(M): os.utime(f'{M}/{f}', (time.time() - 600,) * 2)
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p
class Srv:
    def __init__(self, cfg, **env):
        self.cfg, self.port = cfg, free_port()
        e = dict(os.environ, CONFIG_DIR=cfg, MODELS_DIR=M, PORT=str(self.port), YIELD_TO_USERS='0'); e.pop('BACKUP_DIR', None); e.update(env)
        self.p = subprocess.Popen([sys.executable, 'app.py'], cwd=APP, env=e, stdout=open(f'{ROOT}/out-{self.port}.txt', 'a'), stderr=subprocess.STDOUT)
        for _ in range(80):
            try: urllib.request.urlopen(f'http://127.0.0.1:{self.port}/ping'); break
            except Exception: time.sleep(.2)
        else: raise SystemExit('start mislukt')
        wait(lambda: len(self.req('/api/library')[1]['models']) == 3 and all(m['status'] == 'ok' for m in self.req('/api/library')[1]['models']), 60)
    def req(self, u, m='GET', b=None):
        r = urllib.request.Request(f'http://127.0.0.1:{self.port}' + u, method=m, data=json.dumps(b).encode() if b is not None else None, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read() or b'{}')
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
    def stop(self): self.p.terminate(); self.p.wait(10)
def wait(c, t=20):
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            if c(): return True
        except Exception: pass
        time.sleep(.3)
    return False
dbs = lambda d: sorted(glob.glob(f'{d}/library-*.db')); zips = lambda d: sorted(glob.glob(f'{d}/library-*-thumbs.zip'))
backup_now = lambda s, n, d: (s.req('/api/tasks/backup/run', 'POST'), wait(lambda: len(dbs(d)) >= n, 15))[1]

A, X = f'{ROOT}/cfgA', f'{ROOT}/uit/back-ups'  # X bestaat nog niet: de app maakt hem aan
s = Srv(A)
try:
    st = s.req('/api/settings')[1]
    check('standaard: lege instelling, map = <config>/backups', st['backup_dir'] == '' and st['backup_dir_now'] == os.path.join(A, 'backups'), st.get('backup_dir_now'))
    st, r = s.req('/api/settings', 'POST', {'backup_dir': 'relatief/pad'})
    check('relatief pad wordt geweigerd met uitleg', st == 400 and 'volledig pad' in r.get('error', ''), r)
    open(f'{ROOT}/bestand', 'w').write('x')
    st, r = s.req('/api/settings', 'POST', {'backup_dir': f'{ROOT}/bestand'})
    check('pad dat een bestand is wordt geweigerd', st == 400 and 'beschrijfbaar' in r.get('error', ''), r)
    check('geweigerde waarde is niet opgeslagen', s.req('/api/settings')[1]['backup_dir'] == '')
    s.req('/api/settings', 'POST', {'backup_thumbs': True, 'backup_keep': 2})
    st, r = s.req('/api/settings', 'POST', {'backup_dir': X})
    check('geldige nieuwe map (bestaat nog niet) wordt geaccepteerd', st == 200, r)
    check('meteen een back-up in de nieuwe map (database + thumbnails)', wait(lambda: len(dbs(X)) == 1 and len(zips(X)) == 1), (dbs(X), zips(X)))
    check('niets in de oude map', not glob.glob(f'{A}/backups/*'), glob.glob(f'{A}/backups/*'))
    n = sqlite3.connect(dbs(X)[-1]).execute('select count(*) from models').fetchone()[0]
    check('back-up is een leesbare database met alle modellen', n == 3, n)
    check('geen tijdelijke of .part-bestanden achtergebleven', not glob.glob(f'{X}/*.part') and not glob.glob(f'{A}/.backup-*'), os.listdir(X))
    st = s.req('/api/settings')[1]
    check('instellingen tonen map en laatste back-up', st['backup_dir'] == X and st['backup_dir_now'] == X and st['backup_last'] and not st['backup_error'], st)
    time.sleep(1.2); check('tweede back-up, bewaartermijn 2', backup_now(s, 2, X))
    time.sleep(1.2); oud = dbs(X)[-1]; s.req('/api/tasks/backup/run', 'POST')
    check('derde back-up ruimt de oudste op (2 bewaard)', wait(lambda: dbs(X)[-1] != oud and len(dbs(X)) == 2 and len(zips(X)) == 2 and not s.req('/api/tasks')[1][2]['running'] and glob.glob(f'{X}/*.part') == []) and len(dbs(X)) == 2, (len(dbs(X)), len(zips(X))))
    time.sleep(.5)
    t = {x['key']: x for x in s.req('/api/tasks')[1]}['backup']
    check('taak toont de map', t['dir'] == X and not t['error'], t)
    # map verdwijnt (bijv. NAS uit): fout, geen terugval
    shutil.rmtree(X); open(X, 'w').write('weg')
    s.req('/api/tasks/backup/run', 'POST')
    check('verdwenen map: duidelijke fout zichtbaar in taak en instellingen', wait(lambda: 'bestaat niet' in (s.req('/api/settings')[1]['backup_error'] or '')), s.req('/api/settings')[1]['backup_error'])
    t = {x['key']: x for x in s.req('/api/tasks')[1]}['backup']
    check('taak meldt de fout en blijft naar dezelfde map wijzen', t['error'] and t['dir'] == X, t)
    check('de verdwenen map is niet stilletjes opnieuw aangemaakt', os.path.isfile(X))
    check('geen terugval naar de standaardmap', not glob.glob(f'{A}/backups/*'), glob.glob(f'{A}/backups/*'))
    check('nieuwe poging gepland over ongeveer een uur', 3000 < t['next'] - time.time() < 3700, t['next'] - time.time())
    os.remove(X); os.makedirs(X); s.req('/api/tasks/backup/run', 'POST')
    check('map terug: back-up lukt weer en de fout verdwijnt', wait(lambda: dbs(X) and not s.req('/api/settings')[1]['backup_error']), s.req('/api/settings')[1]['backup_error'])
    # leeg = terug naar standaard
    st, r = s.req('/api/settings', 'POST', {'backup_dir': ''})
    check('leeg maken zet de standaardmap terug en maakt daar een back-up', st == 200 and wait(lambda: len(dbs(f'{A}/backups')) == 1), r)
finally:
    s.stop()
# BACKUP_DIR als standaard, app-instelling gaat voor
B, E_, Y = f'{ROOT}/cfgB', f'{ROOT}/uit/via-env', f'{ROOT}/uit/via-app'
s = Srv(B, BACKUP_DIR=E_)
try:
    st = s.req('/api/settings')[1]
    check('BACKUP_DIR is de standaard', st['backup_dir'] == '' and st['backup_dir_now'] == E_, st.get('backup_dir_now'))
    s.req('/api/tasks/backup/run', 'POST')
    check('BACKUP_DIR die nog niet bestaat: fout, de map wordt niet stilletjes aangemaakt', wait(lambda: 'bestaat niet' in (s.req('/api/settings')[1]['backup_error'] or '')) and not os.path.exists(E_))
    os.makedirs(E_)
    check('back-up gaat naar BACKUP_DIR (na aanmaken van de map)', backup_now(s, 1, E_) and not glob.glob(f'{B}/backups/*'))
    s.req('/api/settings', 'POST', {'backup_dir': Y})
    check('instelling in de app gaat voor op BACKUP_DIR', wait(lambda: len(dbs(Y)) == 1) and s.req('/api/settings')[1]['backup_dir_now'] == Y)
    s.req('/api/settings', 'POST', {'backup_dir': ''})
    check('leeg maken: terug naar BACKUP_DIR', s.req('/api/settings')[1]['backup_dir_now'] == E_)
finally:
    s.stop()
# instelling blijft na herstart
s = Srv(B, BACKUP_DIR=E_)
try:
    s.req('/api/settings', 'POST', {'backup_dir': Y}); time.sleep(.5); s.stop()
    s = Srv(B, BACKUP_DIR=E_)
    check('ingestelde map blijft bewaard na herstart', s.req('/api/settings')[1]['backup_dir_now'] == Y)
finally:
    s.stop()
print('\nALLES GOED' if not bad else f'\nFOUT: {bad}')
sys.exit(1 if bad else 0)
