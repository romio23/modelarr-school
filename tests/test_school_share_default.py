"""Scholen: instelling of uploads van leerlingen standaard gedeeld worden (algemeen en per school). Gebruik: python tests/test_school_share_default.py"""
import io, os, shutil, sys, tempfile, time
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-share'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
import trimesh
from werkzeug.security import generate_password_hash
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?,1)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    d.execute('INSERT INTO schools(name, slug, root_id, created) VALUES(?,?,?,?)', ('School A', 'school-a', rid, time.time()))
    d.execute('INSERT INTO schools(name, slug, root_id, created) VALUES(?,?,?,?)', ('School B', 'school-b', rid, time.time()))
    def user(name, role, school, home):
        d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, school_id, home, display_name, created) VALUES(?,?,?,1,1,?,?,?,?)',
                  (name, generate_password_hash('wachtwoord1'), role, school, home, name.title(), time.time()))
    user('adm', 'admin', None, None); user('jan', 'student', 1, 'school-a/leerlingen/jan'); user('bob', 'student', 2, 'school-b/leerlingen/bob'); user('mees', 'staff', 1, 'school-a/medewerkers/mees')
for p in ('school-a/leerlingen/jan', 'school-b/leerlingen/bob', 'school-a/medewerkers/mees'):
    os.makedirs(f'{ROOT}/m/{p}', exist_ok=True)
A.refresh_auth(); H = {'X-Requested-With': 'modelbib'}
def login(n):
    c = A.app.test_client(); assert c.post('/api/login', json=dict(username=n, password='wachtwoord1'), headers=H).status_code == 200; return c
adm, jan, bob, mees = login('adm'), login('jan'), login('bob'), login('mees')
def stl():
    b = io.BytesIO(); trimesh.creation.box((5, 5, 5)).export(b, file_type='stl'); return b.getvalue()
def up(c, name):  # zonder keuze in het formulier: de standaard geldt
    return c.post('/api/upload', data=dict(root=str(rid), folder='', file=(io.BytesIO(stl()), name)), content_type='multipart/form-data', headers=H)
def drop(path):  # bestand rechtstreeks in de map gezet (bijv. via de share), zonder upload
    open(f'{ROOT}/m/{path}', 'wb').write(stl()); os.utime(f'{ROOT}/m/{path}', (time.time() - 600,) * 2)
def scan():
    for _ in range(50):
        if A.scan() is not False: break
        time.sleep(.2)
    A.assign_owners()
def shared(name):
    with A.db() as d: r = d.execute('SELECT shared FROM models WHERE name=?', (name,)).fetchone(); return None if r is None else bool(r['shared'])
default = lambda c: c.get('/api/upload/targets').get_json()['share_default']

check('standaard (nieuwe installatie): uploads van leerlingen worden gedeeld', A.CFG['default_share'] == '1' and default(jan) is True)
check('instelling staat in Instellingen → Algemeen', adm.get('/api/settings').get_json()['default_share'] is True)

# 1. algemene instelling uit
r = adm.post('/api/settings', json=dict(default_share=False), headers=H)
check('beheerder zet "standaard delen" uit', r.status_code == 200 and adm.get('/api/settings').get_json()['default_share'] is False, r.data)
check('  leerlingen krijgen standaard "niet delen" bij uploaden', default(jan) is False and default(bob) is False)
check('  medewerkers houden hun eigen standaard (aan)', default(mees) is True)
up(jan, 'jan1.stl'); drop('school-b/leerlingen/bob/bob1.stl'); up(mees, 'mees1.stl'); scan()
check('  upload van een leerling zonder keuze is niet gedeeld', shared('jan1') is False, shared('jan1'))
check('  bestand dat via de share in de map van een leerling komt is ook niet gedeeld', shared('bob1') is False, shared('bob1'))
check('  upload van een medewerker blijft gedeeld', shared('mees1') is True, shared('mees1'))
check('  andere leerling ziet het model niet', 'jan1' not in [m['name'] for m in bob.get('/api/library').get_json()['models']])

# 2. per school: School A zet het weer aan, School B volgt de algemene instelling (uit)
s = adm.get('/api/schools').get_json()
check('scholenlijst toont de keuze (leeg = algemeen) en de algemene waarde', all(x['share_default'] is None for x in s['schools']) and s['default_share'] is False, s)
r = adm.put('/api/schools/1', json=dict(share_default='1'), headers=H)
check('school A: "standaard aan" opslaan', r.status_code == 200 and adm.get('/api/schools').get_json()['schools'][0]['share_default'] == 1, r.data)
check('  leerling van school A deelt nu standaard, school B niet', default(jan) is True and default(bob) is False)
up(jan, 'jan2.stl'); drop('school-b/leerlingen/bob/bob2.stl'); scan()
check('  nieuwe modellen volgen de keuze van hun school', shared('jan2') is True and shared('bob2') is False, (shared('jan2'), shared('bob2')))
check('  bestaande modellen veranderen niet', shared('jan1') is False)
adm.put('/api/schools/2', json=dict(share_default='0'), headers=H); A.put('default_share', '1')
check('school B "standaard uit" gaat voor de algemene instelling (aan)', default(bob) is False)
adm.put('/api/schools/2', json=dict(share_default=''), headers=H)
check('school B terug op "Algemeen": volgt weer de algemene instelling', default(bob) is True and adm.get('/api/schools').get_json()['schools'][1]['share_default'] is None)
A.put('default_share', '0')

# 3. keuze bij het uploaden en per model blijft werken
r = jan.post('/api/upload', data=dict(root=str(rid), folder='', shared='0', file=(io.BytesIO(stl()), 'jan3.stl')), content_type='multipart/form-data', headers=H); scan()
check('keuze bij het uploaden gaat voor de standaard', shared('jan3') is False)
with A.db() as d: mid = d.execute("SELECT id FROM models WHERE name='jan1'").fetchone()[0]
check('per model delen aanzetten werkt nog', jan.post(f'/api/models/{mid}/share', json=dict(shared=True), headers=H).status_code == 200 and shared('jan1') is True)

# 4. een eigen standaard van de leerling (via /api/me/prefs) gaat voor die van de school
jan.post('/api/me/prefs', json=dict(share_default=False), headers=H)
check('eigen standaard van een leerling gaat voor die van de school', default(jan) is False)
check('alleen een beheerder mag de algemene instelling wijzigen', mees.post('/api/settings', json=dict(default_share=True), headers=H).status_code in (401, 403) and A.CFG['default_share'] == '0')
print('\nALLES GOED' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
