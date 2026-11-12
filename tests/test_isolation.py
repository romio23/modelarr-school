"""Zware modelverwerking draait in een apart, begrensd proces: werkt normaal, herstelt na een crash en houdt de server heel."""
import os, sys, tempfile, time
d = tempfile.mkdtemp()
os.environ['CONFIG_DIR'] = os.path.join(d, 'cfg')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A, render

n = 0
def ok(c, m):
    global n
    assert c, m
    n += 1
    print('OK  ', m)

stl = os.path.join(d, 'k.stl')
open(stl, 'w').write('solid b\n' + ''.join(f'facet normal 0 0 1\nouter loop\nvertex {a} {b} {c}\nvertex {a+1} {b} {c}\nvertex {a} {b+1} {c+1}\nendloop\nendfacet\n' for a, b, c in [(0, 0, 0), (1, 1, 0), (2, 0, 1), (0, 2, 2)]) + 'endsolid b\n')
out = os.path.join(d, 't.png')
info = A.heavy('make_thumb', stl, 'stl', out, 128, True, None)
ok(info['tris'] == 4 and os.path.getsize(out) > 100, 'thumbnail via hulpproces')
ok(A.heavy('mesh_stl', stl, 'stl', plate=None, view=True)[:5] == b'solid' or len(A.heavy('mesh_stl', stl, 'stl', view=True)) > 100, 'viewer-mesh via hulpproces')

try:
    A.heavy('make_thumb', os.path.join(d, 'x.xyz'), 'xyz', out, 128, True, None); ok(False, 'NoPreview verwacht')
except render.NoPreview:
    ok(True, 'NoPreview komt als zodanig door')
try:
    A.heavy('make_thumb', os.path.join(d, 'weg.stl'), 'stl', out, 128, True, None); ok(False, 'fout verwacht')
except OSError:
    ok(True, 'OSError komt door')

iso = A._ISO_LOCAL.iso
iso.p.kill(); iso.p.wait()
ok(A.heavy('make_thumb', stl, 'stl', out, 128, True, None)['tris'] == 4, 'na een gestorven hulpproces start er vanzelf een nieuw')

real0 = A.Isolated._read
def die(self, k):
    self.p.kill(); self.p.wait(); return real0(self, k)
A.Isolated._read = die
try:
    A.heavy('make_thumb', stl, 'stl', out, 128, True, None); ok(False, 'crash verwacht')
except RuntimeError as e:
    ok('afgebroken' in str(e), 'crash tijdens verwerking geeft melding: ' + str(e)[:50])
A.Isolated._read = real0
ok(A.heavy('make_thumb', stl, 'stl', out, 128, True, None)['tris'] == 4, 'daarna werkt het weer')

A.ISO_RECYCLE_JOBS = 2
pid = iso.p.pid
A.heavy('make_thumb', stl, 'stl', out, 128, True, None)
ok(iso.p is None or iso.p.pid != pid, 'hulpproces wordt na N modellen vervangen')

A.THUMB_TIMEOUT = 1
fifo = os.path.join(d, 'hangt.3mf')
os.mkfifo(fifo)  # openen blokkeert: het hulpproces hangt
t0 = time.time()
try:
    A.heavy('info_3mf', fifo); ok(False, 'timeout verwacht')
except RuntimeError as e:
    ok('langer dan' in str(e) and time.time() - t0 < 10, 'timeout stopt het hulpproces: ' + str(e)[:40])
A.THUMB_TIMEOUT = 600
ok(A.heavy('make_thumb', stl, 'stl', out, 128, True, None)['tris'] == 4, 'na een timeout werkt het weer')

A.THUMB_MEM_MB = 64
A._ISO_LOCAL.iso._stop()
try:
    A.heavy('make_thumb', stl, 'stl', out, 128, True, None); ok(False, 'geheugenlimiet verwacht')
except RuntimeError as e:
    ok(True, 'geheugenlimiet stopt alleen het hulpproces')
A.THUMB_MEM_MB = 4096

A.ISOLATE = False
ok(A.heavy('make_thumb', stl, 'stl', out, 128, True, None)['tris'] == 4, 'THUMB_ISOLATE=0: in hetzelfde proces')
print('ALLES GOED', n)
