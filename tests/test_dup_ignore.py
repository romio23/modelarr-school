"""Test: een dubbelen-groep negeren, terugzetten en weer laten verschijnen bij een nieuwe kopie. Gebruik: python tests/test_dup_ignore.py"""
import os, shutil, sys, tempfile, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-dupign')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
def mk(name, dims=(10, 10, 10)):
    p = f'{ROOT}/m/{name}.stl'; trimesh.creation.box(dims).export(p); os.utime(p, (time.time() - 600,) * 2); return p
mk('a'); shutil.copy(f'{ROOT}/m/a.stl', f'{ROOT}/m/b.stl'); os.utime(f'{ROOT}/m/b.stl', (time.time() - 600,) * 2); mk('x', (3, 4, 5))
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
with A.db() as d:
    for r in d.execute('SELECT * FROM models').fetchall(): A.hash_model(r)
c = A.app.test_client(); H = {'X-Requested-With': 'modelbib'}
dups = lambda: c.get('/api/duplicates').get_json()
d = dups(); ids = [m['id'] for m in d['exact'][0]] if d['exact'] else []
check('een groep identieke bestanden wordt gevonden', len(d['exact']) == 1 and len(ids) == 2, d['exact'])
lib = lambda: {m['name']: m['dup'] for m in c.get('/api/library').get_json()['models']}
check('beide kopieën staan als dubbel gemarkeerd in de bibliotheek', lib().get('a') == 'exact' and lib().get('b') == 'exact', lib())
check('de teller (/api/rev) telt 1 groep', c.get('/api/rev').get_json()['dups'] == 1)
r = c.post('/api/duplicates/ignore', json={'ids': ids, 'ignore': True}, headers=H)
d = dups()
check('negeren lukt', r.status_code == 200, r.get_json())
check('genegeerde groep staat niet meer bij de duplicaten, wel onder "genegeerd"', not d['exact'] and len(d['ignored']) == 1, (len(d['exact']), len(d['ignored'])))
check('de dubbel-markering in de bibliotheek is weg', lib().get('a') == '' and lib().get('b') == '', lib())
check('de teller staat op 0', c.get('/api/rev').get_json()['dups'] == 0)
check('er is niets verplaatst of gewist', os.path.exists(f'{ROOT}/m/a.stl') and os.path.exists(f'{ROOT}/m/b.stl'))
check('een ongeldige groep wordt geweigerd (409)', c.post('/api/duplicates/ignore', json={'ids': [ids[0], 9999]}, headers=H).status_code == 409)
shutil.copy(f'{ROOT}/m/a.stl', f'{ROOT}/m/c.stl'); os.utime(f'{ROOT}/m/c.stl', (time.time() - 600,) * 2)
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
with A.db() as d_:
    for r_ in d_.execute('SELECT * FROM models').fetchall(): A.hash_model(r_)
d = dups()
check('komt er een derde kopie bij, dan verschijnt de groep weer', len(d['exact']) == 1 and len(d['exact'][0]) == 3, [len(g) for g in d['exact']])
ids3 = [m['id'] for m in d['exact'][0]]
c.post('/api/duplicates/ignore', json={'ids': ids3, 'ignore': True}, headers=H)
c.post('/api/duplicates/ignore', json={'ids': ids3, 'ignore': False}, headers=H)
d = dups()
check('"niet meer negeren" zet de groep terug in de lijst', len(d['exact']) == 1 and not d['ignored'], (len(d['exact']), len(d['ignored'])))
print('\nALLES OK' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
