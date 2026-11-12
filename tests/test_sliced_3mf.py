"""Gesliced .gcode.3mf zonder build-items: thumbnail komt uit de ingebedde afbeelding. Gebruik: python tests/test_sliced_3mf.py"""
import io, os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import render
from PIL import Image
T = tempfile.mkdtemp(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
M = '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources/><build/></model>'
b = io.BytesIO(); Image.new('RGB', (64, 64), (200, 50, 50)).save(b, 'PNG')
with zipfile.ZipFile(f'{T}/a.gcode.3mf', 'w') as z: z.writestr('3D/3dmodel.model', M); z.writestr('Metadata/plate_1.png', b.getvalue())
r = render.make_thumb(f'{T}/a.gcode.3mf', '3mf', f'{T}/a.png', 128)
check('gesliced 3MF zonder build-items: ingebedde afbeelding gebruikt', r['source'] == 'embedded' and os.path.exists(f'{T}/a.png'), r)
with zipfile.ZipFile(f'{T}/b.3mf', 'w') as z: z.writestr('3D/3dmodel.model', M)
try: render.make_thumb(f'{T}/b.3mf', '3mf', f'{T}/b.png', 128); ok = False
except render.NoPreview: ok = True
check('zonder afbeelding: NoPreview in plaats van fout', ok)
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
