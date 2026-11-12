"""Test: overlappende root folders breken de scan niet meer af en worden geweigerd/gemeld. Gebruik: python tests/test_roots_overlap.py"""
import logging, os, shutil, sys, tempfile, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-overlap')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/rack/sub'); os.makedirs(f'{ROOT}/rack/other'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
errors = []
class H(logging.Handler):
    def emit(self, rec):
        if rec.levelno >= logging.ERROR: errors.append(rec.getMessage())
A.log.addHandler(H())
for p, d in ((f'{ROOT}/rack/a.stl', (10, 10, 10)), (f'{ROOT}/rack/sub/b.stl', (20, 10, 5)), (f'{ROOT}/rack/other/c.stl', (5, 5, 5))):
    trimesh.creation.box(d).export(p); os.utime(p, (time.time() - 600,) * 2)
def add_raw(p):  # zoals een bestaande installatie: overlappende roots staan al in de database
    with A.db() as d: d.execute('INSERT OR IGNORE INTO roots(path) VALUES(?)', (p,)); return d.execute('SELECT id FROM roots WHERE path=?', (p,)).fetchone()['id']
parent, child = add_raw(f'{ROOT}/rack'), add_raw(f'{ROOT}/rack/sub')
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
with A.db() as d: n = {r['root_id']: r['n'] for r in d.execute('SELECT root_id, COUNT(*) n FROM models GROUP BY root_id')}
check('overlappende roots: de scan breekt niet af (geen ERROR in het log)', not errors, errors[:1])
check('alle 3 bestanden zijn opgenomen, elk één keer (de eerste root wint)', n.get(parent) == 3 and n.get(child) is None, n)
c = A.app.test_client()
check('een nieuwe root die overlapt met een bestaande wordt geweigerd (400, met de naam van de bestaande)', all((lambda r: r.status_code == 400 and 'overlapt' in r.get_json()['error'])(c.post('/api/roots', json={'path': p})) for p in (f'{ROOT}/rack/other', ROOT)))
check('dezelfde root nogmaals toevoegen blijft rustig werken (geen fout)', c.post('/api/roots', json={'path': f'{ROOT}/rack'}).status_code == 200)
os.makedirs(f'{ROOT}/apart'); check('een los staande map mag wel', c.post('/api/roots', json={'path': f'{ROOT}/apart'}).status_code == 200)
h = [x['msg'] for x in c.get('/api/status').get_json()['health']]
check('de statuspagina meldt de overlap tussen de bestaande roots', any('overlappen' in m and f'{ROOT}/rack/sub' in m for m in h), h)

import os as _os
if _os.name != 'nt':
    r = c.post('/api/roots', json={'path': '/'})
    check('de hoofdmap / wordt als root folder geweigerd', r.status_code == 400 and 'hoofdmap' in r.get_json()['error'], r.get_json())
    with A.db() as d: d.execute('INSERT OR IGNORE INTO roots(path) VALUES(?)', ('/',))
    h = [x for x in c.get('/api/status').get_json()['health'] if 'hoofdmap (/)' in x['msg']]
    check('een bestaande root / geeft een foutmelding op de statuspagina', bool(h) and h[0]['level'] == 'error', h)
    with A.db() as d: d.execute("DELETE FROM roots WHERE path='/'")
sys.exit(1 if bad else 0)
