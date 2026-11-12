"""Test: categorieën uit mappen op het hoogste niveau en regels (pad/naam/extensie) die bij een scan en op bestaande modellen worden toegepast.
Gebruik: python tests/test_auto_categorize.py"""
import os, shutil, sys, tempfile, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-autocat')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(ROOT); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
M = f'{ROOT}/m'
def mk(rel, dims):
    p = f'{M}/{rel}'; os.makedirs(os.path.dirname(p), exist_ok=True); trimesh.creation.box(dims).export(p); os.utime(p, (time.time() - 600,) * 2)
mk('10 inch rack/patchpaneel.stl', (1, 2, 3)); mk('10 inch rack/sub/hoek.stl', (2, 3, 4)); mk('Gereedschap/haak.stl', (3, 4, 5)); mk('Gereedschap/Rack_houder.3mf'.replace('.3mf', '.stl'), (4, 5, 6))
mk('los.stl', (5, 6, 7)); mk('.prullenbak/oud.stl', (6, 7, 8))
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (M,))
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
c = A.app.test_client(); H = {'X-Requested-With': 'modelbib'}
names = lambda: {m['name']: [x for x in m['cats']] for m in c.get('/api/library').get_json()['models']}
cats = lambda: {x['name']: x['id'] for x in c.get('/api/library').get_json()['categories']}
f = c.get('/api/folders').get_json()
check('mappen op het hoogste niveau met aantallen (submappen tellen mee, losse bestanden niet, .prullenbak niet)',
      {x['name']: x['count'] for x in f['folders']} == {'10 inch rack': 2, 'Gereedschap': 2} and f['loose'] == 1 and f['folders'][0]['count'] == 2, f)
r = c.post('/api/folders/categorize', json={'items': [{'folder': '10 inch rack', 'category': '10 inch rack'}, {'folder': 'Gereedschap', 'category': 'Tools'}, {'folder': 'bestaat niet', 'category': 'X'}]}, headers=H).get_json()
check('categorieën aangemaakt (eigen naam mag) en alle modellen uit de map ingedeeld', r == {'created': 2, 'assigned': 4} and set(cats()) == {'10 inch rack', 'Tools'}, r)
n = names(); ct = cats()
check('hoek.stl in een submap hoort bij de hoofdmap-categorie; losse bestanden hebben niets', n['hoek'] == [ct['10 inch rack']] and n['los'] == [] and n['haak'] == [ct['Tools']], n)
f = c.get('/api/folders').get_json()
check('opnieuw: bestaande categorie wordt herkend en al ingedeelde modellen tellen mee', {x['name']: (x['done'], x['category_id']) for x in f['folders']}['10 inch rack'] == (2, ct['10 inch rack']))
r = c.post('/api/folders/categorize', json={'items': [{'folder': '10 inch rack', 'category': '10 inch rack'}]}, headers=H).get_json()
check('nogmaals toepassen: niets nieuw en niets dubbel', r == {'created': 0, 'assigned': 0}, r)
check('foute invoer geeft een melding', c.post('/api/folders/categorize', json={'items': []}, headers=H).status_code == 400 and c.post('/api/folders/categorize', json={'items': [{'folder': 'Gereedschap', 'category': ' '}]}, headers=H).status_code == 400)
# regels
tid = ct['Tools']
rid = c.post('/api/rules', json={'field': 'name', 'value': 'RACK', 'category_id': ct['10 inch rack']}, headers=H).get_json()['id']
rl = [x for x in c.get('/api/rules').get_json() if x['field'] == 'name']  # de mapregels (uit "Categorieën uit mappen") staan er ook in
check('regel: naam bevat "rack" (hoofdletterongevoelig) vindt Rack_houder; 1 nog te doen', rl[0]['matches'] == 1 and rl[0]['todo'] == 1 and rl[0]['category'] == '10 inch rack', rl)
check('dezelfde regel nog eens: bestaande wordt teruggegeven', c.post('/api/rules', json={'field': 'name', 'value': 'rack', 'category_id': ct['10 inch rack']}, headers=H).get_json().get('existing') is True)
check('ongeldige regels worden geweigerd', all(c.post('/api/rules', json=b, headers=H).status_code == 400 for b in ({'field': 'x', 'value': 'a', 'category_id': tid}, {'field': 'path', 'value': ' ', 'category_id': tid}, {'field': 'path', 'value': 'a', 'category_id': 9999})))
r = c.post('/api/rules/apply', json={}, headers=H).get_json()
check('regel toepassen op bestaande modellen: Rack_houder krijgt de categorie erbij, de oude blijft', r['assigned'] == 1 and set(names()['Rack_houder']) == {tid, ct['10 inch rack']}, r)
check('opnieuw toepassen: 0 nieuwe', c.post('/api/rules/apply', json={}, headers=H).get_json()['assigned'] == 0)
c.post('/api/rules', json={'field': 'path', 'value': 'sub/', 'category_id': tid}, headers=H); c.post('/api/rules', json={'field': 'ext', 'value': '.STL', 'category_id': tid}, headers=H)
rl = {(x['field'], x['value']): x for x in c.get('/api/rules').get_json()}
check('regel op pad (submap) en op extensie (met punt en hoofdletters)', rl[('path', 'sub/')]['matches'] == 1 and rl[('ext', '.STL')]['matches'] == 5, [(k, v['matches']) for k, v in rl.items()])
# nieuwe bestanden krijgen de categorie bij de scan
mk('Nieuw/rack_extra.stl', (7, 8, 9)); mk('Nieuw/andere.stl', (8, 9, 10))
A.scan(); n = names()
check('nieuw bestand: regel "naam bevat rack" en regel "ext stl" werken meteen bij de scan', set(n['rack_extra']) == {ct['10 inch rack'], tid} and n['andere'] == [tid], n)
check('verwijderde regel werkt niet meer', c.delete(f'/api/rules/{rid}', headers=H).status_code == 200 and all(x['id'] != rid for x in c.get('/api/rules').get_json()))
c.delete(f"/api/categories/{tid}", headers=H)
check('categorie verwijderd: de regels die daarbij hoorden verdwijnen mee', all(x['category_id'] != tid for x in c.get('/api/rules').get_json()) and c.get('/api/rules').status_code == 200)
# veel nieuwe modellen tegelijk (meer dan SQLite-variabelen in één query)
cid = c.post('/api/categories', json={'name': 'Massa'}, headers=H).get_json()['id']; c.post('/api/rules', json={'field': 'path', 'value': 'bulk/', 'category_id': cid}, headers=H)
with A.db() as d:
    rid0 = d.execute('SELECT id FROM roots').fetchone()[0]
    for i in range(1300): d.execute("INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,thumb_status) VALUES(?,?,?,'stl',1,1,1,'ok')", (rid0, f'{M}/bulk/n{i}.stl', f'n{i}'))
    ids = [r[0] for r in d.execute("SELECT id FROM models WHERE path LIKE ?", (f'%/bulk/%',))]
check('1300 modellen tegelijk (in blokken verwerkt)', A.apply_rules(ids) == 1300 and sum(1 for m in c.get('/api/library').get_json()['models'] if cid in m['cats']) == 1300)
sys.exit(1 if bad else 0)
