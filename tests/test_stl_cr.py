"""ASCII-STL met alleen CR als regeleinde (oud Mac-formaat) moet laden."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import render

body = "solid box\n"
for a, b, c in [((0,0,0),(1,0,0),(0,1,0)), ((1,0,0),(1,1,0),(0,1,0)), ((0,0,0),(0,1,0),(0,0,1)), ((0,0,0),(0,0,1),(1,0,0))]:
    body += "facet normal 0 0 1\n outer loop\n" + "".join(f"  vertex {x} {y} {z}\n" for x, y, z in (a, b, c)) + " endloop\nendfacet\n"
body += "endsolid box\n"

d = tempfile.mkdtemp()
for name, eol in (('lf', '\n'), ('crlf', '\r\n'), ('cr', '\r')):
    p = os.path.join(d, name + '.stl')
    open(p, 'wb').write(body.replace('\n', eol).encode())
    V, F = render.load_mesh(p, 'stl')
    assert len(F) == 4, (name, len(F))
bad = os.path.join(d, 'bad.stl')
open(bad, 'wb').write(b'dit is geen stl\r\rlala')
try:
    render.load_mesh(bad, 'stl'); raise SystemExit('bad.stl had moeten falen')
except ValueError:
    pass
print('OK stl regeleinden')
