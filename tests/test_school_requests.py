"""Scholen: beheer van scholen (limiet per school), meldingen en printaanvragen. Gebruik: python tests/test_school_requests.py"""
import io, os, shutil, sys, tempfile, time
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-req'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
import trimesh
from werkzeug.security import generate_password_hash
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
H = {'X-Requested-With': 'modelbib'}
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?,1)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, created) VALUES(?,?,?,1,1,?)', ('adm', generate_password_hash('wachtwoord1'), 'admin', time.time()))
A.refresh_auth()
def login(n):
    c = A.app.test_client(); r = c.post('/api/login', json=dict(username=n, password='wachtwoord1'), headers=H); assert r.status_code == 200, r.data; return c
adm = login('adm')
r = adm.post('/api/schools', json=dict(name='School A', root_id=rid, quota_mb=1), headers=H); check('school aanmaken', r.status_code == 200, r.data)
r = adm.post('/api/schools', json=dict(name='School B', root_id=rid), headers=H)
check('  mappen leerlingen/medewerkers worden aangemaakt', os.path.isdir(f'{ROOT}/m/school-a/leerlingen') and os.path.isdir(f'{ROOT}/m/school-b/medewerkers'))
check('  dubbele naam wordt geweigerd', adm.post('/api/schools', json=dict(name='school a'), headers=H).status_code == 409)
sa, sb = [s['id'] for s in adm.get('/api/schools').get_json()['schools']]
with A.db() as d:
    def user(name, role, sid, home):
        d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, school_id, home, display_name, klas, created) VALUES(?,?,?,1,1,?,?,?,?,?)',
                  (name, generate_password_hash('wachtwoord1'), role, sid, home, name.title(), '1A' if role == 'student' else '', time.time()))
    user('jan', 'student', sa, 'school-a/leerlingen/jan'); user('piet', 'student', sa, 'school-a/leerlingen/piet'); user('kees', 'student', sb, 'school-b/leerlingen/kees')
    user('mees', 'staff', sa, 'school-a/medewerkers/mees'); user('nel', 'staff', sb, 'school-b/medewerkers/nel')
A.refresh_auth()
jan, piet, kees, mees, nel = (login(n) for n in ('jan', 'piet', 'kees', 'mees', 'nel'))
def stl(kb=1):
    b = io.BytesIO(); trimesh.creation.box((5, 5, 5)).export(b, file_type='stl'); return b.getvalue() + b'\0' * kb * 1024
def up(c, name, kb=1):
    return c.post('/api/upload', data=dict(root=str(rid), folder='', file=(io.BytesIO(stl(kb)), name)), content_type='multipart/form-data', headers=H)
check('limiet per school: school A heeft 1 MB, school B de algemene 500 MB', up(jan, 'groot.stl', 1500).status_code == 413 and up(kees, 'groot.stl', 1500).status_code == 200)
check('  upload binnen de limiet', up(jan, 'auto.stl').status_code == 200 and up(piet, 'p.stl').status_code == 200)
check('leerling mag scholen niet beheren', jan.post('/api/schools', json=dict(name='X'), headers=H).status_code == 403 and jan.get('/api/schools').status_code == 403)
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
mid = {m['name']: m['id'] for m in adm.get('/api/library').get_json()['models']}
# meldingen
check('melden zonder reden mislukt', kees.post(f'/api/models/{mid["auto"]}/report', json=dict(reason=''), headers=H).status_code == 400)
check('leerling meldt een gedeeld model van een andere school', kees.post(f'/api/models/{mid["auto"]}/report', json=dict(reason='Niet geschikt'), headers=H).status_code == 200)
kees.post(f'/api/models/{mid["auto"]}/report', json=dict(reason='nog eens'), headers=H)
check('  meldingen zijn alleen zichtbaar voor medewerkers van de school van het model', mees.get('/api/reports').get_json()['reports'][0]['school'] == 'School A' and len(mees.get('/api/reports').get_json()['reports']) == 1 and nel.get('/api/reports').get_json()['reports'] == [])
check('  dubbele melding door dezelfde leerling wordt samengevoegd', len(adm.get('/api/reports').get_json()['reports']) == 1)
check('  leerlingen zien de meldingen niet', jan.get('/api/reports').status_code == 403)
rp = mees.get('/api/reports').get_json()['reports'][0]
check('  melder staat er voor de medewerker met naam bij', rp['reporter'] == 'Kees (1A)', rp)
check('  medewerker van een andere school kan niet afhandelen', nel.post(f'/api/reports/{rp["id"]}', json=dict(action='hide'), headers=H).status_code == 404)
check('  verbergen: model verdwijnt voor andere scholen, eigenaar houdt het', mees.post(f'/api/reports/{rp["id"]}', json=dict(action='hide'), headers=H).status_code == 200
      and 'auto' not in [m['name'] for m in kees.get('/api/library').get_json()['models']] and 'auto' in [m['name'] for m in jan.get('/api/library').get_json()['models']])
check('  afgehandeld: staat niet meer in de open lijst', mees.get('/api/reports').get_json()['reports'] == [])
check('  weer tonen via hide=false', mees.post(f'/api/models/{mid["auto"]}/hide', json=dict(hidden=False), headers=H).status_code == 200 and 'auto' in [m['name'] for m in kees.get('/api/library').get_json()['models']])
kees.post(f'/api/models/{mid["p"]}/report', json=dict(reason='Dit is storend'), headers=H); r2 = mees.get('/api/reports').get_json()['reports'][0]
check('  verwijderen via melding: bestand naar de prullenbak', mees.post(f'/api/reports/{r2["id"]}', json=dict(action='delete'), headers=H).status_code == 200 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/piet/p.stl'))
# printaanvragen
op = kees.get('/api/requests/options').get_json(); check('kleurenpalet beschikbaar', len(op['colors']) > 5 and op['colors'][0]['hex'].startswith('#'))
r = kees.post('/api/requests', json=dict(model_id=mid['auto'], colors=['Rood', 'Wit'], copies=2, note='voor mijn project'), headers=H); check('aanvraag indienen', r.status_code == 200, r.data)
check('  onbekende kleur wordt genegeerd, te veel kleuren geweigerd', kees.post('/api/requests', json=dict(model_id=mid['auto'], colors=['Paars-bestaat-niet'], copies=1), headers=H).status_code == 200
      and kees.post('/api/requests', json=dict(model_id=mid['auto'], colors=['Wit', 'Zwart', 'Grijs', 'Rood', 'Geel'], copies=1), headers=H).status_code == 400)
check('  aanvraag voor een model dat je niet mag zien: 404', kees.post('/api/requests', json=dict(model_id=99999), headers=H).status_code == 404)
mine = kees.get('/api/requests').get_json()['requests']; check('leerling ziet alleen eigen aanvragen, zonder aanvragersnaam', len(mine) == 2 and mine[0]['requester'] == '' and jan.get('/api/requests').get_json()['requests'] == [])
sch = nel.get('/api/requests').get_json()['requests']; check('aanvraag gaat naar de medewerker van de school van de AANVRAGER', len(sch) == 2 and sch[0]['requester'] == 'Kees (1A)' and mees.get('/api/requests').get_json()['requests'] == [], sch)
q = [x for x in sch if x['colors'] == ['Rood', 'Wit']][0]; qid = q['id']
check('  medewerker van de andere school kan niet bewerken', mees.post(f'/api/requests/{qid}', json=dict(status='busy'), headers=H).status_code == 404)
check('  leerling kan status niet zetten', kees.post(f'/api/requests/{qid}', json=dict(status='done'), headers=H).status_code == 403)
r = nel.post(f'/api/requests/{qid}/file', data=dict(file=(io.BytesIO(b'PK sliced'), 'auto.gcode.3mf')), content_type='multipart/form-data', headers=H)
check('medewerker voegt het gesliced bestand toe; aanvraag wordt "bezig"', r.status_code == 200 and [x for x in nel.get('/api/requests').get_json()['requests'] if x['id'] == qid][0]['status'] == 'busy', r.data)
check('  fout bestandstype wordt geweigerd', nel.post(f'/api/requests/{qid}/file', data=dict(file=(io.BytesIO(b'x'), 'a.stl')), content_type='multipart/form-data', headers=H).status_code == 400)
check('  gesliced bestand is te downloaden door de medewerker, niet door de leerling', nel.get(f'/api/requests/{qid}/file').data == b'PK sliced' and kees.get(f'/api/requests/{qid}/file').status_code == 403)
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
check('  het gesliced bestand verschijnt niet in de bibliotheek', not any('auto.gcode' in m['name'] for m in adm.get('/api/library').get_json()['models']))
check('medewerker zet de aanvraag op klaar met opmerking', nel.post(f'/api/requests/{qid}', json=dict(status='done', staff_note='Ligt bij de balie'), headers=H).status_code == 200)
st = [x for x in kees.get('/api/requests').get_json()['requests'] if x['id'] == qid][0]; check('  leerling ziet status en opmerking', st['status'] == 'done' and st['staff_note'] == 'Ligt bij de balie' and st['has_file'], st)
other = [x for x in kees.get('/api/requests').get_json()['requests'] if x['id'] != qid][0]['id']
check('leerling kan open aanvraag intrekken; een afgeronde niet', kees.post(f'/api/requests/{other}/cancel', headers=H).status_code == 200 and kees.post(f'/api/requests/{qid}/cancel', headers=H).status_code == 409)
check('andermans aanvraag intrekken: 404', jan.post(f'/api/requests/{qid}/cancel', headers=H).status_code == 404)
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
