"""Test: meerdere thumbnail-workers pakken nooit hetzelfde model, en grote modellen worden uitgedund. Gebruik: python tests/test_parallel_workers.py"""
import os, shutil, sys, tempfile, threading, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-par')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A, render
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
N = 24
for i in range(N):
    p = f'{ROOT}/m/b{i}.stl'; trimesh.creation.box((10 + i, 10, 10)).export(p); os.utime(p, (time.time() - 600,) * 2)
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
made = []; orig = A.thumb_for
def spy(r, out):
    made.append(r['id']); time.sleep(.05); return orig(r, out)
A.thumb_for = spy
for i in range(4): threading.Thread(target=A.worker, args=(i == 0,), daemon=True).start()
for _ in range(150):
    with A.db() as d:
        if d.execute("SELECT COUNT(*) FROM models WHERE thumb_status='ok'").fetchone()[0] == N: break
    time.sleep(.2)
with A.db() as d: st = {r['thumb_status']: r['n'] for r in d.execute('SELECT thumb_status, COUNT(*) n FROM models GROUP BY 1')}
check('alle modellen krijgen een thumbnail met 4 workers', st.get('ok') == N, st)
check('elk model is precies één keer gerenderd (geen dubbel werk)', len(made) == N and len(set(made)) == N, (len(made), len(set(made))))
import numpy as np
n = 400_000; rng = np.random.default_rng(1); V = rng.random((n, 3)); F = rng.integers(0, n, (n, 3)); t = time.time(); render.render(V, F)
check('een model met 400k driehoeken wordt uitgedund en is snel klaar (< 15 s)', time.time() - t < 15, round(time.time() - t, 1))
check('de standaardlimiet staat op 250.000 driehoeken', render.MAX_TRIS == 250000, render.MAX_TRIS)
print('\nALLES OK' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
