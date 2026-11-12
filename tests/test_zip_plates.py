"""Test: modellen in zips (zonder uitpakken) en meerdere platen in een 3MF. Gebruik: python tests/test_zip_plates.py"""
import io, json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile
import numpy as np, trimesh
from PIL import Image
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, APP)
ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-zip'); PORT = 8793
shutil.rmtree(ROOT, ignore_errors=True); M = f'{ROOT}/models'; os.makedirs(M); os.makedirs(f'{ROOT}/cfg')
OLD = time.time() - 600
def stl(box): return trimesh.exchange.stl.export_stl(box)
def png(color):
    b = io.BytesIO(); Image.new('RGB', (128, 128), color).save(b, 'PNG'); return b.getvalue()
NS = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
def objxml(i, box):
    v = ''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in box.vertices); t = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in box.faces)
    return f'<object id="{i}"><mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>'
def multi3mf(path, extra=None):
    A, B, C = trimesh.creation.box((40, 20, 10)), trimesh.creation.box((10, 10, 10)), trimesh.creation.box((20, 10, 30))
    tr = lambda x: f'1 0 0 0 1 0 0 0 1 {x} 0 0'
    model = (f'<?xml version="1.0"?><model unit="millimeter" {NS}><resources>{objxml(1, A)}{objxml(2, B)}{objxml(3, C)}</resources><build>'
             f'<item objectid="1" transform="{tr(0)}"/><item objectid="2" transform="{tr(303)}"/><item objectid="3" transform="{tr(333)}"/><item objectid="1" transform="{tr(606)}"/></build></model>')
    inst = lambda o, i: f'<model_instance><metadata key="object_id" value="{o}"/><metadata key="instance_id" value="{i}"/></model_instance>'
    cfg = ('<config><object id="1"/>'
           f'<plate><metadata key="plater_id" value="1"/><metadata key="plater_name" value=""/>{inst(1, 0)}</plate>'
           f'<plate><metadata key="plater_id" value="2"/><metadata key="plater_name" value="Deksels"/>{inst(2, 0)}{inst(3, 0)}</plate>'
           f'<plate><metadata key="plater_id" value="3"/><metadata key="plater_name" value=""/>{inst(1, 1)}</plate></config>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('3D/3dmodel.model', model); z.writestr('Metadata/model_settings.config', cfg); z.writestr('Metadata/plate_1.png', png((200, 30, 30)))
box = trimesh.creation.box((40, 20, 10)); BOX = stl(box)
def inner3mf():
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('3D/3dmodel.model', f'<?xml version="1.0"?><model unit="millimeter" {NS}><resources>{objxml(1, trimesh.creation.box((15, 15, 15)))}</resources><build><item objectid="1"/></build></model>')
        z.writestr('Metadata/plate_1.png', png((220, 20, 20)))
    return b.getvalue()
def make_pack(path, extra=()):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('box.stl', BOX); z.writestr('sub/cyl.stl', stl(trimesh.creation.cylinder(8, 30))); z.writestr('readme.txt', 'x')
        z.writestr('__MACOSX/._box.stl', 'junk'); z.writestr('.hidden.stl', BOX); z.writestr('proj.3mf', inner3mf()); z.writestr('big.stl', stl(trimesh.creation.icosphere(subdivisions=6)))
        for n, d in extra: z.writestr(n, d)
    os.utime(path, (OLD, OLD))
make_pack(f'{M}/pack.zip'); multi3mf(f'{M}/multi.3mf'); open(f'{M}/box.stl', 'wb').write(BOX); open(f'{M}/big.stl', 'wb').write(stl(trimesh.creation.icosphere(subdivisions=6))); open(f'{M}/kapot.zip', 'wb').write(b'PK\x03\x04 dit is geen zip')
for f in ('multi.3mf', 'box.stl', 'big.stl', 'kapot.zip'): os.utime(f'{M}/{f}', (OLD, OLD))
def start():
    env = dict(os.environ, CONFIG_DIR=f'{ROOT}/cfg', MODELS_DIR=M, PORT=str(PORT), YIELD_TO_USERS='0', ALLOW_ORGANIZE='1', MAX_FILE_MB='1')
    p = subprocess.Popen([sys.executable, 'app.py'], cwd=APP, env=env, stdout=open(f'{ROOT}/out.txt', 'a'), stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen(f'http://127.0.0.1:{PORT}/ping'); return p
        except Exception: time.sleep(.2)
    raise SystemExit('start mislukt')
def parse(d):
    try: return json.loads(d or b'{}')
    except ValueError: return d
def req(u, m='GET', b=None, raw=False):
    r = urllib.request.Request(f'http://127.0.0.1:{PORT}' + u, method=m, data=json.dumps(b).encode() if b is not None else None, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r) as x: d = x.read(); return x.status, (d if raw else parse(d)), x.headers
    except urllib.error.HTTPError as e: d = e.read(); return e.code, (d if raw else parse(d)), e.headers
def wait(c, t=45):
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            if c(): return True
        except Exception: pass
        time.sleep(.5)
    return False
lib = lambda: {(m['container'] + '!' if m['container'] else '') + m['name']: m for m in req('/api/library')[1]['models']}
ext = lambda b: np.round(trimesh.load(io.BytesIO(b), file_type='stl').bounds, 1)
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
# ---- losse functies (zonder server)
import render
mp = f'{M}/multi.3mf'
info = render.info_3mf(mp)
check('info: 3 platen met naam', [(p['id'], p['name']) for p in info.get('plates', [])] == [(1, ''), (2, 'Deksels'), (3, '')], info.get('plates'))
b = lambda pl: render.load_mesh(mp, '3mf', plate=pl)[0]
check('plaat 1 = alleen object A (40x20x10)', np.allclose(np.ptp(b(1), 0), [40, 20, 10]))
check('plaat 2 = objecten B en C samen (45x10x30)', np.allclose(np.ptp(b(2), 0), [45, 10, 30]), np.ptp(b(2), 0))
check('plaat 3 = tweede exemplaar van A (x rond 606)', abs(b(3)[:, 0].mean() - 606) < 1 and np.allclose(np.ptp(b(3), 0), [40, 20, 10]))
check('zonder plaat = alles (platen op x = 0, 303, 333, 606: 646 breed)', abs(np.ptp(render.load_mesh(mp, '3mf')[0], 0)[0] - 646) < 1, np.ptp(render.load_mesh(mp, '3mf')[0], 0))
try: b(9); check('onbekende plaat geeft een fout', False)
except ValueError: check('onbekende plaat geeft een fout', True)
srv = start()
try:
    check('eerste import', wait(lambda: len(lib()) >= 6 and all(m['status'] in ('ok', 'failed') for m in lib().values()), 60), sorted(lib()))
    L = lib()
    check('onderdelen van de zip zichtbaar; readme/__MACOSX/verborgen/te groot niet', {k for k in L if k.startswith('pack.zip!')} == {'pack.zip!box', 'pack.zip!cyl', 'pack.zip!proj'}, sorted(L))
    check('kapotte zip: geen crash, geen modellen', not any(k.startswith('kapot.zip!') for k in L) and req('/ping')[0] == 200)
    check('losse te grote stl krijgt een fout, geen preview', L['big']['status'] == 'failed' and '1 MB' in (L['big']['error'] or ''), L['big']['error'])
    zb, zc, zp_ = L['pack.zip!box'], L['pack.zip!cyl'], L['pack.zip!proj']
    check('onderdeel in zip: thumbnail + afmetingen zonder uitpakken', zb['status'] == 'ok' and [round(x) for x in zb['dims']] == [40, 20, 10], zb['dims'])
    th = Image.open(f"{ROOT}/cfg/thumbs/{zp_['id']}.png").convert('RGB'); px = th.getpixel((th.width // 2, th.height // 2))
    check('3MF in een zip: ingebedde afbeelding gebruikt (rood)', zp_['status'] == 'ok' and px[0] > 180 and px[1] < 80, px)
    wait(lambda: lib()['pack.zip!box']['dup'] == 'exact' and lib()['box']['dup'] == 'exact', 30)  # het hashen gebeurt op de achtergrond, na de thumbnails
    L = lib(); zb = L['pack.zip!box']
    check('zip-onderdeel en losse kopie zijn identiek (dubbel)', zb['dup'] == 'exact' and L['box']['dup'] == 'exact', (zb['dup'], L['box']['dup']))
    s, data, _ = req(f"/api/mesh/{zb['id']}.stl", raw=True); check('viewer-mesh van zip-onderdeel', s == 200 and np.allclose(np.ptp(ext(data), 0), [40, 20, 10]))
    s, data, h = req(f"/api/file/{zc['id']}", raw=True); check('download van zip-onderdeel (alleen dat bestand)', s == 200 and 'cyl.stl' in h.get('Content-Disposition', '') and len(data) == len(stl(trimesh.creation.cylinder(8, 30))))
    check('hernoemen van zip-onderdeel geweigerd (400)', req(f"/api/models/{zc['id']}", 'POST', {'filename': 'x'})[0] == 400)
    check('weergavenaam van zip-onderdeel wijzigen mag', req(f"/api/models/{zc['id']}", 'POST', {'display': 'Cilinder'})[0] == 200 and lib()['pack.zip!cyl']['display'] == 'Cilinder')
    check('zip-onderdeel naar prullenbak geweigerd', req(f"/api/models/{zb['id']}/trash", 'POST')[0] == 409 and os.path.exists(f'{M}/pack.zip'))
    cat = req('/api/categories', 'POST', {'name': 'Uit zip'})[1]['id']; req('/api/assign', 'POST', {'model_ids': [zc['id']], 'category_id': cat, 'action': 'add'})
    # ---- platen in de server
    mm = lib()['multi']; check('platen in de bibliotheek-info', len(mm['info']['plates']) == 3)
    check('afmetingen per plaat op de achtergrond berekend', wait(lambda: len(lib()['multi']['pdims'] or []) == 3, 40) and np.allclose(lib()['multi']['pdims'][1]['dims'], [45, 10, 30]), lib()['multi']['pdims'])
    ex = lambda q: np.ptp(ext(req(f"/api/mesh/{mm['id']}.stl{q}", raw=True)[1]), 0)
    check('/api/mesh?plate=1 en ?plate=2', np.allclose(ex('?plate=1'), [40, 20, 10]) and np.allclose(ex('?plate=2'), [45, 10, 30]))
    check('onbekende plaat: 415', req(f"/api/mesh/{mm['id']}.stl?plate=9", raw=True)[0] == 415)
    # ---- zip gewijzigd: ids en categorieën blijven, nieuw onderdeel verschijnt
    ids = {k: v['id'] for k, v in lib().items() if k.startswith('pack.zip!')}
    make_pack(f'{M}/pack.zip', extra=[('extra.stl', stl(trimesh.creation.cone(5, 10)))]); os.utime(f'{M}/pack.zip', (OLD + 100, OLD + 100)); req('/api/tasks/scan/run', 'POST')
    check('gewijzigde zip: nieuw onderdeel erbij', wait(lambda: 'pack.zip!extra' in lib(), 40))
    L2 = lib(); check('gewijzigde zip: bestaande onderdelen houden id en categorie', all(L2[k]['id'] == i for k, i in ids.items()) and L2['pack.zip!cyl']['cats'] == [cat])
    # ---- zip verplaatst/hernoemd: niets verliezen
    os.rename(f'{M}/pack.zip', f'{M}/nieuwe_naam.zip'); req('/api/tasks/scan/run', 'POST'); time.sleep(3)
    L3 = lib(); check('hernoemde zip: onderdelen behouden id, categorie en weergavenaam', all(L3.get('nieuwe_naam.zip!' + k.split('!')[1], {}).get('id') == i for k, i in ids.items()) and L3['nieuwe_naam.zip!cyl']['cats'] == [cat] and L3['nieuwe_naam.zip!cyl']['display'] == 'Cilinder', sorted(L3))
    # ---- instelling uit: zip-modellen verdwijnen; weer aan: ze komen terug
    req('/api/settings', 'POST', {'zip_support': False}); check('zip-ondersteuning uit: onderdelen weg', wait(lambda: not any('.zip!' in k for k in lib()), 20) and 'box' in lib())
    req('/api/settings', 'POST', {'zip_support': True}); check('zip-ondersteuning weer aan: onderdelen terug', wait(lambda: 'nieuwe_naam.zip!box' in lib(), 40))
    # ---- zip verwijderd
    os.remove(f'{M}/nieuwe_naam.zip'); req('/api/tasks/scan/run', 'POST'); check('zip verwijderd: onderdelen weg, losse bestanden blijven', wait(lambda: not any('.zip!' in k for k in lib()), 20) and 'box' in lib() and 'multi' in lib())
finally:
    srv.terminate(); srv.wait()
left = [f for f in os.listdir(f'{ROOT}/cfg/tmp')] if os.path.isdir(f'{ROOT}/cfg/tmp') else []
check('geen tijdelijke bestanden blijven achter', left == [], left)
print('--- fouten in uitvoer:', [l for l in open(f'{ROOT}/out.txt') if 'Traceback' in l][:2])
sys.exit(1 if bad else 0)
