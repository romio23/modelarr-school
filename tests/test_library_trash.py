"""Test: geselecteerde bestanden vanuit de bibliotheek naar .prullenbak (niet alleen duplicaten). Gebruik: python tests/test_library_trash.py"""
import os, shutil, sys, tempfile, time, zipfile
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-libtrash')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/rw/sub'); os.makedirs(f'{ROOT}/ro'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
def mk(path, dims):
    trimesh.creation.box(dims).export(path); os.utime(path, (time.time() - 600,) * 2)
mk(f'{ROOT}/rw/a.stl', (1, 2, 3)); mk(f'{ROOT}/rw/sub/b.stl', (2, 3, 4)); mk(f'{ROOT}/rw/c.stl', (3, 4, 5)); mk(f'{ROOT}/ro/d.stl', (4, 5, 6))
mk(f'{ROOT}/z.stl', (5, 6, 7))
with zipfile.ZipFile(f'{ROOT}/rw/pak.zip', 'w') as z: z.write(f'{ROOT}/z.stl', 'in_zip.stl')
os.utime(f'{ROOT}/rw/pak.zip', (time.time() - 600,) * 2)
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?, 1)', (f'{ROOT}/rw',)); d.execute('INSERT INTO roots(path, allow_write) VALUES(?, 0)', (f'{ROOT}/ro',))
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
c = A.app.test_client(); H = {'X-Requested-With': 'modelbib'}
lib = lambda: {(m['container'] + '!' if m['container'] else '') + m['name']: m for m in c.get('/api/library').get_json()['models']}
L = lib(); ids = {k: v['id'] for k, v in L.items()}
check('vijf modellen gevonden (waaronder één in een zip)', set(ids) == {'a', 'b', 'c', 'd', 'pak.zip!in_zip'}, list(ids))
r = c.post('/api/models/trash', json={'ids': [ids['a']]}, headers=H).get_json()
check('zonder "any": een niet-dubbel bestand wordt niet verplaatst (duplicatenweergave blijft veilig)', r['done'] == 0 and os.path.exists(f'{ROOT}/rw/a.stl'), r)
r = c.post('/api/models/trash', json={'ids': [ids['a'], ids['b'], ids['d'], ids['pak.zip!in_zip'], 99999], 'any': True}, headers=H).get_json()
check('met "any": a en b verplaatst; d (schrijven uit), de zip-inhoud en een onbekend id niet', r['done'] == 2 and len(r['failed']) == 3, r)
check('bestanden staan in .prullenbak van hun root, ook uit een submap, en zijn weg uit de map', not os.path.exists(f'{ROOT}/rw/a.stl') and not os.path.exists(f'{ROOT}/rw/sub/b.stl') and len(os.listdir(f'{ROOT}/rw/.prullenbak')) == 2, os.listdir(f'{ROOT}/rw/.prullenbak'))
check('niet verplaatste bestanden staan er nog', os.path.exists(f'{ROOT}/ro/d.stl') and os.path.exists(f'{ROOT}/rw/c.stl') and os.path.exists(f'{ROOT}/rw/pak.zip'))
L2 = lib(); check('de verplaatste modellen zijn uit de bibliotheek, de rest staat er nog', set(L2) == {'c', 'd', 'pak.zip!in_zip'}, list(L2))
msgs = [x['message'] for x in c.get('/api/history').get_json() if x['event'] == 'Prullenbak']
check('het logboek noemt de verplaatsing', any('a.stl naar .prullenbak verplaatst (via de bibliotheek)' in m for m in msgs), msgs)
A.scan(); check('een nieuwe scan haalt de prullenbak niet terug in de bibliotheek', set(lib()) == {'c', 'd', 'pak.zip!in_zip'})
sys.exit(1 if bad else 0)
