"""Test: modellen in submappen worden gevonden; onleesbare mappen en symlinks worden gemeld. Gebruik: python tests/test_subfolders.py"""
import logging, os, shutil, sys, tempfile, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-sub')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/m/a/b/c'); os.makedirs(f'{ROOT}/elders/echt'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
msgs = []
class H(logging.Handler):
    def emit(self, rec): msgs.append(rec.getMessage())
A.log.addHandler(H())
for p in (f'{ROOT}/m/top.stl', f'{ROOT}/m/a/een.stl', f'{ROOT}/m/a/b/c/diep.stl', f'{ROOT}/elders/echt/via_link.stl'):
    trimesh.creation.box((5, 5, 5)).export(p); os.utime(p, (time.time() - 600,) * 2)
os.symlink(f'{ROOT}/elders/echt', f'{ROOT}/m/link')
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
def run():
    for _ in range(50):
        if A.scan() is not False: break
        time.sleep(.2)
    with A.db() as d: return sorted(r['name'] for r in d.execute('SELECT name FROM models'))
n = run()
check('modellen in submappen (ook 3 niveaus diep) worden gevonden', {'top', 'een', 'diep'} <= set(n), n)
check('een symbolische link wordt niet gevolgd maar wel gemeld', 'via_link' not in n and any('symbolische link' in m for m in msgs), msgs[-3:])
A.FOLLOW_LINKS = True; n = run()
check('met FOLLOW_SYMLINKS worden gelinkte mappen wel doorzocht', 'via_link' in n, n)
print('\nALLES OK' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
