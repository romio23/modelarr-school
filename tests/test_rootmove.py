"""Test: root folder een nieuw pad geven (Windows <-> Docker), wijzigingstijd-tolerantie en thumbnail-kenmerk. Gebruik: python tests/test_rootmove.py"""
import io, json, os, shutil, sys, tempfile, time, zipfile
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-move')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(ROOT); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
c = A.app.test_client(); STL = lambda d: trimesh.exchange.stl.export_stl(trimesh.creation.box(d))
def tree(base, names=('a', 'b', 'z')):
    os.makedirs(f'{base}/sub', exist_ok=True)
    if 'a' in names: open(f'{base}/a.stl', 'wb').write(STL((10, 10, 10)))
    if 'b' in names: open(f'{base}/sub/b.stl', 'wb').write(STL((20, 10, 5)))
    if 'z' in names:
        with zipfile.ZipFile(f'{base}/z.zip', 'w') as z: z.writestr('m.stl', STL((5, 5, 30)))
    for d, _, fs in os.walk(base):
        for f in fs: os.utime(os.path.join(d, f), (time.time() - 600,) * 2)
def rescan():
    for _ in range(60):
        if A.scan() is not False: return
        time.sleep(.2)
def add_root(p):
    with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (p,)); return d.execute('SELECT id FROM roots WHERE path=?', (p,)).fetchone()['id']
def rows(rid): 
    with A.db() as d: return {r['name']: dict(r) for r in d.execute('SELECT * FROM models WHERE root_id=?', (rid,))}
def events(): return [h['event'] for h in c.get('/api/history').get_json()]  # nieuwste eerst
def new_events(before): return events()[:len(events()) - len(before)]
mv = lambda rid, path, **k: c.post(f'/api/roots/{rid}/move', json={'path': path, **k})
# ---- 1. echte verhuizing: zelfde bestanden op een nieuwe plek, wijzigingstijd net anders
old, new = f'{ROOT}/old', f'{ROOT}/new'; tree(old); rid = add_root(old); rescan(); m = rows(rid)
check('uitgangspunt: 3 modellen (los, in submap, in zip)', set(m) == {'a', 'b', 'm'} and m['m']['container'] is not None, list(m))
ids = {k: v['id'] for k, v in m.items()}
c.post('/api/categories', json={'name': 'Rack'}); cat = c.get('/api/library').get_json()['categories'][0]['id']
c.post(f"/api/models/{ids['a']}", json={'notes': 'mijn notitie', 'favorite': True}); c.post('/api/assign', json={'model_ids': [ids['b']], 'action': 'add', 'category_id': cat})
os.makedirs(A.THUMBS, exist_ok=True)
for i in ids.values(): open(os.path.join(A.THUMBS, f'{i}.png'), 'wb').write(b'png')
with A.db() as d: d.execute('UPDATE models SET thumb_custom=1, thumb_status="ok" WHERE id=?', (ids['a'],))
shutil.copytree(old, new)
for d_, _, fs in os.walk(new):
    for f in fs: p = os.path.join(d_, f); os.utime(p, (time.time() - 600, os.stat(p).st_mtime + 0.4))  # ander platform: net andere afronding
before = events(); plan = mv(rid, new).get_json()
check('overzicht vooraf: 3 van 3 gevonden, geen dubbelen, niets gewijzigd', plan['total'] == 3 and plan['found'] == 3 and plan['conflicts'] == 0 and not plan['merge'] and not plan['needs_force'] and rows(rid)['a']['path'].startswith(old), plan)
r = mv(rid, new, apply=True); rescan(); time.sleep(.3); rescan(); m2 = rows(rid)
check('verhuisd: zelfde ids, paden onder de nieuwe map, zip-onderdeel en zip bijgewerkt', r.status_code == 200 and {k: v['id'] for k, v in m2.items()} == ids and m2['b']['path'] == os.path.join(new, 'sub', 'b.stl') and m2['m']['container'] == os.path.join(new, 'z.zip') and m2['m']['path'] == os.path.join(new, 'z.zip') + '!/m.stl', {k: v['path'] for k, v in m2.items()})
with A.db() as d: nroots = [x['path'] for x in d.execute('SELECT path FROM roots')]; cats = d.execute('SELECT category_id FROM model_categories WHERE model_id=?', (ids['b'],)).fetchall()
check('gegevens blijven: notitie, favoriet, categorie, eigen thumbnail', m2['a']['notes'] == 'mijn notitie' and m2['a']['favorite'] == 1 and len(cats) == 1 and m2['a']['thumb_custom'] == 1 and os.path.exists(os.path.join(A.THUMBS, f"{ids['a']}.png")))
check('root-pad is aangepast (één root)', nroots == [new], nroots)
check('daarna geen "gewijzigd/toegevoegd/verwijderd" door de scan (tolerantie voor wijzigingstijd)', new_events(before) == ['Root verplaatst'], new_events(before))
os.utime(f'{new}/a.stl', (time.time() - 600, os.stat(f'{new}/a.stl').st_mtime + 5)); rescan()
check('een echte wijziging (5 seconden) wordt wel gezien', 'Gewijzigd' in new_events(before))
# ---- 2. Windows-database (UNC-paden met \) naar een Linux-pad
win = '\\\\nas\\3d\\rack'; lin = f'{ROOT}/lin/rack'; tree(lin); wr = add_root(win)
with A.db() as d:
    for p, name, ext, cont, mem in ((win + '\\a.stl', 'a', 'stl', None, None), (win + '\\sub\\b.stl', 'b', 'stl', None, None), (win + '\\z.zip!/m.stl', 'm', 'stl', win + '\\z.zip', 'm.stl')):
        d.execute('INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,container,member) VALUES(?,?,?,?,1,1,1,?,?)', (wr, p, name, ext, cont, mem))
check('de oude Windows-root staat als niet bereikbaar op deze machine', [x for x in c.get('/api/roots').get_json() if x['id'] == wr][0]['ok'] is False)
rescan(); check('scan van een niet-bereikbare root verwijdert niets', len(rows(wr)) == 3)
p = mv(wr, lin).get_json(); check('overzicht: \\\\nas\\3d\\rack -> Linux-map, 3 van 3 gevonden', p['found'] == 3 and p['total'] == 3, p)
mv(wr, lin, apply=True); w2 = rows(wr)
check('backslashes zijn omgezet naar de paden van dit platform', w2['b']['path'] == os.path.join(lin, 'sub', 'b.stl') and w2['m']['container'] == os.path.join(lin, 'z.zip') and w2['m']['path'] == os.path.join(lin, 'z.zip') + '!/m.stl' and '\\' not in w2['a']['path'], {k: v['path'] for k, v in w2.items()})
# ---- 3. samenvoegen met een map die al gescand is (bijv. via MODELS_DIR)
win2 = '\\\\nas\\3d\\merge'; tgt = f'{ROOT}/merge'; tree(tgt); tr_ = add_root(tgt); rescan(); fresh = rows(tr_)
mr = add_root(win2)
with A.db() as d:
    for p, name, cont, mem in ((win2 + '\\a.stl', 'a', None, None), (win2 + '\\sub\\b.stl', 'b', None, None), (win2 + '\\z.zip!/m.stl', 'm', win2 + '\\z.zip', 'm.stl')):
        d.execute('INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,container,member,notes) VALUES(?,?,?,?,1,1,1,?,?,?)', (mr, p, name, 'stl', cont, mem, 'oude notitie ' + name))
old_ids = {k: v['id'] for k, v in rows(mr).items()}; fresh_ids = {v['id'] for v in fresh.values()}
with A.db() as d: d.execute("UPDATE models SET notes='nieuwe notitie' WHERE id=?", (fresh['a']['id'],))
for i in fresh_ids: open(os.path.join(A.THUMBS, f'{i}.png'), 'wb').write(b'x')
p = mv(mr, tgt).get_json()
check('overzicht: samenvoegen, 3 dubbelen waarvan 1 met eigen gegevens', p['merge'] and p['conflicts'] == 3 and p['conflicts_with_data'] == 1 and p['found'] == 3, p)
mv(mr, tgt, apply=True); mm = rows(tr_)
with A.db() as d: nr = [x['path'] for x in d.execute('SELECT path FROM roots')]
check('samengevoegd: alleen de oude modellen (met hun gegevens) staan op de nieuwe paden', {k: v['id'] for k, v in mm.items()} == old_ids and mm['a']['notes'] == 'oude notitie a' and tgt in nr and win2 not in nr, {k: v['notes'] for k, v in mm.items()})
check('thumbnails van de vervangen dubbele ingangen zijn opgeruimd', not any(os.path.exists(os.path.join(A.THUMBS, f'{i}.png')) for i in fresh_ids))
# ---- 4. minder dan de helft gevonden, overlap, ongeldige invoer
win3 = '\\\\nas\\3d\\few'; few = f'{ROOT}/few'; tree(few, names=('a',)); fr = add_root(win3)
with A.db() as d:
    for n_, sub in (('a', ''), ('b', 'sub\\'), ('c', '')): d.execute('INSERT INTO models(root_id,path,name,ext,size,mtime,added_at) VALUES(?,?,?,?,1,1,1)', (fr, f'{win3}\\{sub}{n_}.stl', n_, 'stl'))
p = mv(fr, few).get_json(); check('minder dan de helft gevonden: waarschuwing', p['found'] == 1 and p['total'] == 3 and p['needs_force'] is True and p['missing'] == 2, p)
r = mv(fr, few, apply=True); check('...en zonder bevestiging (force) niet uitgevoerd (409)', r.status_code == 409 and rows(fr)['a']['path'].startswith(win3))
r = mv(fr, few, apply=True, force=True); check('...met bevestiging wel; ontbrekende modellen blijven staan', r.status_code == 200 and len(rows(fr)) == 3 and rows(fr)['a']['path'] == os.path.join(few, 'a.stl'))
outer = f'{ROOT}/outer'; os.makedirs(f'{outer}/inner'); orid = add_root(outer); lone = f'{ROOT}/lone'; os.makedirs(lone); lid = add_root(lone)
check('overlap met een andere root folder wordt geweigerd', mv(lid, f'{outer}/inner').status_code == 400 and mv(lid, f'{ROOT}').status_code == 400)
check('zelfde pad, bestaat niet, leeg: 400; onbekende root: 404', mv(lid, lone).status_code == 400 and mv(lid, f'{ROOT}/bestaatniet').status_code == 400 and mv(lid, '').status_code == 400 and mv(99999, lone).status_code == 404)
# ---- 5. thumbnail-kenmerk met tolerantie
row = {'id': 5, 'size': 100, 'mtime': 1000.0}
check('thumbnail-kenmerk: kleine afwijking in wijzigingstijd ok; ander model, andere grootte of rommel niet', A.tag_matches('5:100:1000.4', row) and A.tag_matches(A.thumb_tag(row), row) and not A.tag_matches('5:100:1005', row) and not A.tag_matches('6:100:1000.0', row) and not A.tag_matches('5:101:1000.0', row) and not A.tag_matches('rommel', row))
sys.exit(1 if bad else 0)
