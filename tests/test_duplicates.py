"""Test voor de dubbelen-check. Gebruik: python tests/test_duplicates.py"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-dup'); PORT = 8796
shutil.rmtree(ROOT, ignore_errors=True)
M = f'{ROOT}/models'; os.makedirs(f'{M}/sub'); os.makedirs(f'{ROOT}/cfg')
box = trimesh.creation.box((40, 20, 10))
box.export(f'{M}/a.stl'); shutil.copy(f'{M}/a.stl', f'{M}/sub/a_kopie.stl')               # identiek
open(f'{M}/sub/b_ascii.stl', 'wb').write(trimesh.exchange.stl.export_stl_ascii(box).encode())  # zelfde mesh, andere inhoud
trimesh.creation.box((30, 30, 5)).export(f'{M}/zelfde_grootte.stl')                         # zelfde bestandsgrootte, andere mesh
trimesh.creation.cylinder(8, 30).export(f'{M}/uniek.stl')
for d, _, fs in os.walk(M):
    for f in fs: os.utime(os.path.join(d, f), (time.time() - 600,) * 2)
env = dict(os.environ, CONFIG_DIR=f'{ROOT}/cfg', MODELS_DIR=M, PORT=str(PORT), ALLOW_ORGANIZE='1', YIELD_TO_USERS='0')
srv = subprocess.Popen([sys.executable, 'app.py'], cwd=APP, env=env, stdout=open(f'{ROOT}/out.txt', 'w'), stderr=subprocess.STDOUT)
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
        time.sleep(.5)
    return False
bad = []
def check(name, ok, extra=''):
    print('OK  ' if ok else 'FOUT', name, extra); (None if ok else bad.append(name))
try:
    wait(lambda: req('/ping') if False else urllib.request.urlopen(f'http://127.0.0.1:{PORT}/ping'))
    wait(lambda: len(req('/api/library')[1]['models']) == 5 and all(m['status'] == 'ok' for m in req('/api/library')[1]['models']) and req('/api/rev')[1]['dups'] == 1)
    lib = {m['name']: m for m in req('/api/library')[1]['models']}
    check('dup-vlag per model', [lib[n]['dup'] for n in ('a', 'a_kopie', 'b_ascii', 'zelfde_grootte', 'uniek')] == ['exact', 'exact', 'mesh', '', ''], [lib[n]['dup'] for n in lib])
    s, d = req('/api/duplicates')
    check('1 exacte groep met a + a_kopie', len(d['exact']) == 1 and {x['name'] for x in d['exact'][0]} == {'a', 'a_kopie'}, d['wasted'])
    check('mesh-groep bevat b_ascii maar niet zelfde_grootte', len(d['mesh']) == 1 and 'b_ascii' in {x['name'] for x in d['mesh'][0]} and 'zelfde_grootte' not in {x['name'] for x in d['mesh'][0]})
    check('zelfde grootte, andere inhoud = geen exact dubbel', all('zelfde_grootte' not in {x['name'] for x in g} for g in d['exact']))
    check('melding in geschiedenis', any(h['event'] == 'Dubbel' for h in req('/api/history')[1]))
    check('rev.dups = 1', req('/api/rev')[1]['dups'] == 1)
    s, r = req(f"/api/models/{lib['uniek']['id']}/trash", 'POST'); check('uniek bestand weigeren (409)', s == 409 and os.path.exists(f'{M}/uniek.stl'), s)
    s, r = req(f"/api/models/{lib['a_kopie']['id']}/trash", 'POST')
    check('dubbel naar prullenbak', s == 200 and not os.path.exists(f'{M}/sub/a_kopie.stl') and os.path.exists(r.get('dest', '')), r.get('dest'))
    req('/api/tasks/scan/run', 'POST'); time.sleep(3)
    names = {m['name'] for m in req('/api/library')[1]['models']}
    check('prullenbak wordt niet opnieuw ingelezen', names == {'a', 'b_ascii', 'zelfde_grootte', 'uniek'}, sorted(names))
    check('exacte groep weg, rev.dups = 0', req('/api/duplicates')[1]['exact'] == [] and req('/api/rev')[1]['dups'] == 0)
    s, r = req(f"/api/models/{lib['a']['id']}/trash", 'POST'); check('mesh-twin is nog wel dubbel (b_ascii)', s == 200)
    s, r = req(f"/api/models/{lib['b_ascii']['id']}/trash", 'POST'); check('laatste kopie wordt nooit verplaatst (409)', s == 409 and os.path.exists(f'{M}/sub/b_ascii.stl'), s)
finally:
    srv.terminate(); srv.wait()
print('--- fouten in uitvoer:', [l for l in open(f'{ROOT}/out.txt') if 'Traceback' in l][:2])
sys.exit(1 if bad else 0)
