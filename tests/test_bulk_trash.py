"""Test: meerdere dubbele bestanden in één keer naar de prullenbak; nooit de laatste kopie; geen overschrijven bij gelijke namen. Gebruik: python tests/test_bulk_trash.py"""
import os, shutil, sys, tempfile, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-bulktrash')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
trimesh.creation.box((10, 10, 10)).export(f'{ROOT}/src.stl'); trimesh.creation.box((4, 5, 6)).export(f'{ROOT}/src2.stl')
for d in ('A', 'B', 'C', 'D'):
    os.makedirs(f'{ROOT}/m/{d}')
    shutil.copy(f'{ROOT}/src.stl', f'{ROOT}/m/{d}/zelfde_naam.stl')   # 4 identieke kopieën met dezelfde naam
    shutil.copy(f'{ROOT}/src2.stl', f'{ROOT}/m/{d}/tweede.stl')       # tweede groep van 4
    for f in os.listdir(f'{ROOT}/m/{d}'): os.utime(f'{ROOT}/m/{d}/{f}', (time.time() - 600,) * 2)
with A.db() as d: d.execute('INSERT INTO roots(path, allow_write) VALUES(?, 0)', (f'{ROOT}/m',))
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
with A.db() as d:
    for r in d.execute('SELECT * FROM models').fetchall(): A.hash_model(r)
c = A.app.test_client(); H = {'X-Requested-With': 'modelbib'}
dups = lambda: c.get('/api/duplicates').get_json()
ids = [m['id'] for g in dups()['exact'] for m in g]
check('twee groepen van 4 identieke bestanden', len(dups()['exact']) == 2 and len(ids) == 8, len(ids))
r = c.post('/api/models/trash', json={'ids': ids}, headers=H).get_json()
check('met "verplaatsen" uit voor de root: niets gebeurt en elke fout wordt gemeld', r['done'] == 0 and len(r['failed']) == 8 and 'staat uit' in r['failed'][0]['error'], r)
with A.db() as d: d.execute('UPDATE roots SET allow_write=1')
r = c.post('/api/models/trash', json={'ids': ids}, headers=H).get_json()
left = dups()
n_left = len(os.listdir(f'{ROOT}/m/A')) + len(os.listdir(f'{ROOT}/m/B')) + len(os.listdir(f'{ROOT}/m/C')) + len(os.listdir(f'{ROOT}/m/D'))
with A.db() as d: n_db = d.execute('SELECT COUNT(*) FROM models').fetchone()[0]
check('alles geselecteerd: van elke groep blijft precies één kopie staan (6 van 8 verplaatst)', r['done'] == 6 and len(r['failed']) == 2 and n_db == 2, (r['done'], n_db))
check('op schijf zijn 2 bestanden over (1 per groep), de rest staat in .prullenbak', n_left == 2 and len(os.listdir(f'{ROOT}/m/.prullenbak')) == 6, (n_left, len(os.listdir(f'{ROOT}/m/.prullenbak'))))
names = os.listdir(f'{ROOT}/m/.prullenbak')
check('bestanden met dezelfde naam in dezelfde seconde overschrijven elkaar niet (alle 6 aanwezig)', len(set(names)) == 6, names)
check('de laatste kopies zijn niet meer als dubbel gemarkeerd', not left['exact'])
check('ongeldige invoer wordt geweigerd (400)', c.post('/api/models/trash', json={'ids': ['x']}, headers=H).status_code == 400)
print('\nALLES OK' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
