"""Scholen: uploaden naar eigen map, quotum, delen aan/uit, eigen verwijderen. Gebruik: python tests/test_school_upload.py"""
import io, os, shutil, sys, tempfile, time
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-up'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
import trimesh
from werkzeug.security import generate_password_hash
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?,1)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    d.execute('INSERT INTO schools(name, slug, root_id, created) VALUES(?,?,?,?)', ('School A', 'school-a', rid, time.time())); sa = 1
    def user(name, role, home, up=1):
        d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, school_id, home, display_name, created) VALUES(?,?,?,1,?,?,?,?,?)',
                  (name, generate_password_hash('wachtwoord1'), role, up, sa if role != 'admin' else None, home, name.title(), time.time()))
    user('adm', 'admin', None); user('jan', 'student', 'school-a/leerlingen/jan'); user('piet', 'student', 'school-a/leerlingen/piet'); user('mees', 'staff', 'school-a/medewerkers/mees')
A.refresh_auth(); H = {'X-Requested-With': 'modelbib'}
def login(n):
    c = A.app.test_client(); assert c.post('/api/login', json=dict(username=n, password='wachtwoord1'), headers=H).status_code == 200; return c
jan, piet, mees = login('jan'), login('piet'), login('mees')
def stl(kb=1):
    b = io.BytesIO(); trimesh.creation.box((5, 5, 5)).export(b, file_type='stl'); return b.getvalue() + b'\0' * kb * 1024
def up(c, name, folder='', shared=None, data=None):
    f = dict(root=str(rid), folder=folder, file=(io.BytesIO(data or stl()), name))
    if shared is not None: f['shared'] = shared
    return c.post('/api/upload', data=f, content_type='multipart/form-data', headers=H)
def scan():
    for _ in range(50):
        if A.scan() is not False: break
        time.sleep(.2)
r = up(jan, 'auto.stl'); check('leerling kan uploaden', r.status_code == 200, r.data)
check('  bestand staat in de eigen map', os.path.exists(f'{ROOT}/m/school-a/leerlingen/jan/auto.stl'))
r = up(jan, 'boot.stl', folder='../piet'); check('  pad naar andermans map wordt geweigerd', r.status_code == 400 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/piet/boot.stl'), r.data)
r = up(jan, 'sub.stl', folder='projecten/auto'); check('  submap in eigen map mag', r.status_code == 200 and os.path.exists(f'{ROOT}/m/school-a/leerlingen/jan/projecten/auto/sub.stl'))
r = up(jan, 'geheim.stl', shared='0'); up(piet, 'p.stl'); up(mees, 'les.stl', folder='lessen')
scan()
names = lambda c: sorted(m['name'] for m in c.get('/api/library').get_json()['models'])
check('upload met "niet delen" is voor anderen onzichtbaar, voor jezelf zichtbaar', 'geheim' not in names(piet) and 'geheim' in names(jan) and 'geheim' in names(mees), (names(piet), names(jan)))
check('gedeelde uploads zijn voor iedereen zichtbaar', {'auto', 'sub', 'p', 'les'} <= set(names(piet)) | {'p'}, names(piet))
t = jan.get('/api/upload/targets').get_json()
check('doelen: één, scoped, met quotum en gebruik', len(t['roots']) == 1 and t['scoped'] and t['quota_mb'] == 500 and 'path' not in str(t), t)
check('mappenlijst begint in de eigen map', jan.get(f'/api/upload/dirs?root={rid}').get_json()['dirs'] == ['projecten'], jan.get(f'/api/upload/dirs?root={rid}').data)
tm = mees.get('/api/upload/targets').get_json(); check('medewerker: zijn school als doel, zonder quotum', tm['roots'][0]['name'] == 'School A' and tm['quota_mb'] == 0)
check('medewerker uploadde in de schoolmap', os.path.exists(f'{ROOT}/m/school-a/lessen/les.stl'))
A.put('student_quota_mb', '1')
r = up(jan, 'groot.stl', data=stl(1500)); check('quotum: te veel data wordt geweigerd', r.status_code == 413 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/jan/groot.stl') and not [f for f in os.listdir(f'{ROOT}/m/school-a/leerlingen/jan') if f.endswith('.part')], r.data)
A.put('student_quota_mb', '500')
mid = {m['name']: m['id'] for m in A.app.test_client().get('/api/library').get_json().get('models', [])} or {m['name']: m['id'] for m in login('adm').get('/api/library').get_json()['models']}
check('delen aan/uit door eigenaar', jan.post(f'/api/models/{mid["auto"]}/share', json=dict(shared=False), headers=H).status_code == 200 and 'auto' not in names(piet))
check('andermans (nu privé) model delen aanpassen: 404', piet.post(f'/api/models/{mid["auto"]}/share', json=dict(shared=True), headers=H).status_code == 404)
check('leerling kan model van een ander niet verwijderen', piet.post(f'/api/models/{mid["sub"]}/delete', headers=H).status_code == 403)
check('medewerker kan een leerlingmodel verwijderen', mees.post(f'/api/models/{mid["sub"]}/delete', headers=H).status_code == 200 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/jan/projecten/auto/sub.stl'))
r = jan.post(f'/api/models/{mid["geheim"]}/delete', headers=H); check('eigen model verwijderen: naar de prullenbak', r.status_code == 200 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/jan/geheim.stl') and os.path.isdir(f'{ROOT}/m/.prullenbak'), r.data)
check('voorkeur: standaard delen uit, nieuwe upload is privé', jan.post('/api/me/prefs', json=dict(share_default=False), headers=H).status_code == 200 and up(jan, 'nieuw.stl').status_code == 200)
scan(); check('  ... en dus onzichtbaar voor anderen', 'nieuw' not in names(piet) and 'nieuw' in names(jan))
with A.db() as d: d.execute("UPDATE users SET can_upload=0 WHERE username='piet'")
A.OKAUTH.clear(); pc = login('piet')
check('leerling zonder uploadrecht: 403', up(pc, 'x.stl').status_code == 403)
r = jan.get(f'/api/upload/dirs?root={rid}&path=').get_json()
check('uploadvenster toont eerder geüploade bestanden', 'auto.stl' in r.get('files', []) and 'projecten' in r['dirs'], r)
# school zonder gekoppelde root, maar er is precies één root: wordt vanzelf gekoppeld
with A.db() as d:
    d.execute('INSERT INTO schools(name, slug, root_id, created) VALUES(?,?,NULL,?)', ('School B', 'school-b', time.time())); sb = d.execute("SELECT id FROM schools WHERE slug='school-b'").fetchone()[0]
    d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, school_id, home, display_name, created) VALUES(?,?,?,1,1,?,?,?,?)', ('kees', generate_password_hash('wachtwoord1'), 'student', sb, 'school-b/leerlingen/kees', 'Kees', time.time()))
A.OKAUTH.clear(); kc = login('kees'); r = up(kc, 'kees.stl')
check('school zonder root krijgt bij één root die root automatisch', r.status_code == 200 and os.path.exists(f'{ROOT}/m/school-b/leerlingen/kees/kees.stl'), r.data)
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
