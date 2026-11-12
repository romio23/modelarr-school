"""Test: printers (CRUD, validatie, voorinstellingen). Gebruik: python tests/test_printers.py"""
import os, shutil, sys, tempfile
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-printers')
shutil.rmtree(ROOT, ignore_errors=True); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); c = A.app.test_client(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
p = c.get('/api/printers/presets').get_json()
check('voorinstellingen: eensluidende maten, geen H2D', len(p) == 7 and {x['name']: (x['bed_x'], x['bed_y'], x['bed_z']) for x in p}['Bambu Lab A1 mini'] == (180, 180, 180) and not any('H2D' in x['name'] for x in p), [x['name'] for x in p])
s = c.post('/api/printers', json={'name': 'P1S', 'bed_x': 256, 'bed_y': 256, 'bed_z': 256}); check('printer toevoegen', s.status_code == 200, s.get_json())
check('dubbele naam (hoofdletterongevoelig): 409', c.post('/api/printers', json={'name': 'p1s', 'bed_x': 1, 'bed_y': 1, 'bed_z': 1}).status_code == 409)
check('ontbrekende maat: 400', c.post('/api/printers', json={'name': 'X', 'bed_x': 100}).status_code == 400)
check('geen naam: 400', c.post('/api/printers', json={'name': ' ', 'bed_x': 1, 'bed_y': 1, 'bed_z': 1}).status_code == 400)
check('onzinnige maat (0, negatief, tekst, te groot): 400', all(c.post('/api/printers', json={'name': 'Y', 'bed_x': v, 'bed_y': 10, 'bed_z': 10}).status_code == 400 for v in (0, -5, 'abc', 99999)))
pid = c.get('/api/printers').get_json()[0]['id']
check('printer wijzigen', c.put(f'/api/printers/{pid}', json={'name': 'P1S (werkplaats)', 'bed_x': 250, 'bed_y': 250, 'bed_z': 250}).status_code == 200 and c.get('/api/printers').get_json()[0]['bed_x'] == 250)
c.post('/api/printers', json={'name': 'A1 mini', 'bed_x': 180, 'bed_y': 180, 'bed_z': 180})
check('hernoemen naar bestaande naam: 409', c.put(f'/api/printers/{pid}', json={'name': 'a1 MINI', 'bed_x': 1, 'bed_y': 1, 'bed_z': 1}).status_code == 409)
check('lijst gesorteerd op naam', [x['name'] for x in c.get('/api/printers').get_json()] == ['A1 mini', 'P1S (werkplaats)'])
c.delete(f'/api/printers/{pid}'); check('printer verwijderen', [x['name'] for x in c.get('/api/printers').get_json()] == ['A1 mini'])
sys.exit(1 if bad else 0)
