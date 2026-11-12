"""Test: tijdens een scan is voortgang zichtbaar en verschijnen modellen al in batches. Gebruik: python tests/test_scan_progress.py"""
import os, shutil, sys, tempfile, time
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-prog')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
N = 1300
for d in range(13):
    os.makedirs(f'{ROOT}/m/d{d}')
    for i in range(100):
        p = f'{ROOT}/m/d{d}/f{i}.stl'; open(p, 'wb').write(b'x' * 10); os.utime(p, (time.time() - 600,) * 2)
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
commits = [0]
class Px:  # telt de tussentijdse commits van de scan
    def __init__(self, c): self.c = c
    def __getattr__(self, k): return getattr(self.c, k)
    def __setattr__(self, k, v): object.__setattr__(self, k, v) if k == 'c' else setattr(self.c, k, v)
    def __enter__(self): self.c.__enter__(); return self
    def __exit__(self, *a): return self.c.__exit__(*a)
    def commit(self): commits[0] += 1; return self.c.commit()
_conn = A.sqlite3.connect
class SQ:  # alleen sqlite3.connect vervangen
    def __getattr__(self, k): return getattr(A.sqlite3_real, k)
    def connect(self, *a, **k): return Px(_conn(*a, **k))
A.sqlite3_real = A.sqlite3; A.sqlite3 = SQ()
c = A.app.test_client(); seen = []; counts = []
orig = A.bump
def spy():
    orig()
    if A.T['scan']['running']:
        with A.db() as d: counts.append(d.execute('SELECT COUNT(*) FROM models').fetchone()[0])
        seen.append(c.get('/api/rev').get_json()['scan'])
A.bump = spy
A.time.sleep(0)
A.scan()
with A.db() as d: total = d.execute('SELECT COUNT(*) FROM models').fetchone()[0]
check('alle 1300 bestanden uit 13 submappen zijn opgenomen', total == N, total)
check('de scan legt tussentijds vast (elke 500 modellen), niet pas aan het eind', commits[0] >= 2, commits[0])
check('/api/rev geeft tijdens de scan voortgang mee (fase, bestanden, mappen)', any(s and s['phase'] == 'bijwerken' and s['total'] == N for s in seen), seen[:2])
check('na de scan is de voortgang weg (scan = null)', c.get('/api/rev').get_json()['scan'] is None)
check('de teller telde alle mappen en bestanden', A.SCANP['files'] == N and A.SCANP['dirs'] == 14, dict(A.SCANP))
print('\nALLES OK' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
