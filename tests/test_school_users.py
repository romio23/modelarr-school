"""Scholen: gebruikersbeheer door beheerder en medewerker, CSV-import, thuismappen. Gebruik: python tests/test_school_users.py"""
import io, os, shutil, sys, tempfile, time
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-usr'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
from werkzeug.security import generate_password_hash
A.init(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
H = {'X-Requested-With': 'modelbib'}
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?,1)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, created) VALUES(?,?,?,1,1,?)', ('adm', generate_password_hash('wachtwoord1'), 'admin', time.time()))
A.refresh_auth()
def login(n, pw='wachtwoord1'):
    c = A.app.test_client(); r = c.post('/api/login', json=dict(username=n, password=pw), headers=H); return c, r.status_code
adm = login('adm')[0]
adm.post('/api/schools', json=dict(name='School A', root_id=rid), headers=H); adm.post('/api/schools', json=dict(name='School B', root_id=rid), headers=H)
sa, sb = [s['id'] for s in adm.get('/api/schools').get_json()['schools']]
r = adm.post('/api/users', json=dict(username='mees', password='wachtwoord1', role='staff', school_id=sa, display_name='Mees Meester'), headers=H)
check('beheerder maakt medewerker in een school; thuismap wordt aangemaakt', r.status_code == 200 and os.path.isdir(f'{ROOT}/m/school-a/medewerkers/mees'), r.data)
check('  zonder school mislukt voor niet-beheerders', adm.post('/api/users', json=dict(username='x1', password='wachtwoord1', role='staff'), headers=H).status_code == 400)
adm.post('/api/users', json=dict(username='nel', password='wachtwoord1', role='staff', school_id=sb), headers=H)
mees, nel = login('mees')[0], login('nel')[0]
r = mees.post('/api/school/users', json=dict(username='jan', display_name='Jan Jansen', klas='1A'), headers=H).get_json()
check('medewerker maakt een leerling met gegenereerd wachtwoord', r.get('ok') and len(r['password']) >= 8 and os.path.isdir(f'{ROOT}/m/school-a/leerlingen/jan'), r)
c, st = login('jan', r['password']); check('  de leerling kan inloggen', st == 200)
me = c.get('/api/me').get_json(); check('  /api/me: school, klas en weergavenaam', me['school']['name'] == 'School A' and me['klas'] == '1A' and me['display'] == 'Jan Jansen', me)
check('  dubbele gebruikersnaam wordt geweigerd', mees.post('/api/school/users', json=dict(username='jan'), headers=H).status_code == 400)
csv = 'Naam;Klas;E-mail\nPiet Peters;1A;\nKlaas de Vries;1B;klaas@leerlingen.test\nJan Jansen;2C;\n;;\nLeeg Naam;;\n'
pv = mees.post('/api/school/users/import', data=dict(file=(io.BytesIO(csv.encode()), 'l.csv'), preview='1'), content_type='multipart/form-data', headers=H).get_json()
check('CSV-voorbeeld: niets aangemaakt, wel overzicht', pv['preview'] and pv['ok'] == 4 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/piet-peters'), pv)
im = mees.post('/api/school/users/import', data=dict(file=(io.BytesIO(csv.encode()), 'l.csv')), content_type='multipart/form-data', headers=H).get_json()
check('CSV-import: puntkomma herkend, namen -> gebruikersnamen, wachtwoorden gegenereerd', im['ok'] == 4 and {x['username'] for x in im['rows']} == {'piet-peters', 'klaas-de-vries', 'jan-jansen', 'leeg-naam'} and all(len(x['password']) >= 8 for x in im['rows']), im)
check('  thuismappen aangemaakt', all(os.path.isdir(f'{ROOT}/m/school-a/leerlingen/{n}') for n in ('piet-peters', 'klaas-de-vries')))
check('  gebruikersnaam "jan-jansen" botst niet met "jan"', len(mees.get('/api/school/users').get_json()['users']) == 5)
check('  CSV met komma en eigen wachtwoord', mees.post('/api/school/users/import', data='naam,wachtwoord,klas\nAnna,geheim1234,3A\n', content_type='text/csv', headers=H).get_json()['ok'] == 1 and login('anna', 'geheim1234')[1] == 200)
check('  zonder kopregel: duidelijke fout', mees.post('/api/school/users/import', data='Jan\nPiet\n', content_type='text/csv', headers=H).status_code == 400)
check('medewerker ziet alleen de leerlingen van de eigen school', nel.get('/api/school/users').get_json()['users'] == [])
r0 = mees.get('/api/school/users').get_json()['users']; n0 = len(r0)
up = mees.post('/api/school/users/import', data='gebruikersnaam;naam;klas\npiet-peters;;2B\nklaas-de-vries;Klaas de Vries jr;3A\nnieuw-kind;Nieuw Kind;1A\n', content_type='text/csv', headers=H).get_json()
us = {u['username']: u for u in mees.get('/api/school/users').get_json()['users']}
check('CSV opnieuw: bestaande leerling krijgt andere klas (naam blijft als die leeg is), nieuwe wordt aangemaakt', up['ok'] == 1 and up['updated'] == 2 and us['piet-peters']['klas'] == '2B' and us['piet-peters']['display_name'] == 'Piet Peters' and us['klaas-de-vries']['display_name'] == 'Klaas de Vries jr' and len(us) == n0 + 1, up)
pw_before = [x for x in up['rows'] if x.get('updated')]
check('  bijgewerkte leerlingen krijgen geen nieuw wachtwoord en het oude blijft werken', all('password' not in x for x in pw_before) and login('piet-peters', [x for x in im['rows'] if x['username'] == 'piet-peters'][0]['password'])[1] == 200)
mm = mees.post('/api/school/users/import', data='email;klas\nklaas@leerlingen.test;4C\n', content_type='text/csv', headers=H).get_json()
check('  koppelen op e-mailadres', mm['updated'] == 1 and {u['username']: u for u in mees.get('/api/school/users').get_json()['users']}['klaas-de-vries']['klas'] == '4C', mm)
pv2 = mees.post('/api/school/users/import', data=dict(file=(io.BytesIO(b'gebruikersnaam;klas\npiet-peters;5A\n'), 'l.csv'), preview='1'), content_type='multipart/form-data', headers=H).get_json()
check('  voorbeeld wijzigt niets', pv2['updated'] == 1 and {u['username']: u for u in mees.get('/api/school/users').get_json()['users']}['piet-peters']['klas'] == '2B')
ko = nel.post('/api/school/users/import', data='gebruikersnaam;klas\npiet-peters;9Z\n', content_type='text/csv', headers=H).get_json()
check('  leerling van een andere school wordt niet bijgewerkt (gebruikersnaam bezet)', ko['updated'] == 0 and ko['failed'] == 1 and {u['username']: u for u in mees.get('/api/school/users').get_json()['users']}['piet-peters']['klas'] == '2B', ko)
uid = [u for u in mees.get('/api/school/users').get_json()['users'] if u['username'] == 'jan'][0]['id']
check('  medewerker van een andere school kan niet bewerken', nel.put(f'/api/school/users/{uid}', json=dict(password=True), headers=H).status_code == 404)
r = mees.put(f'/api/school/users/{uid}', json=dict(password=True), headers=H).get_json(); check('wachtwoord opnieuw instellen: nieuwe wachtwoord, oude sessie ongeldig', r['ok'] and login('jan', r['password'])[1] == 200 and c.get('/api/library').status_code == 401)
check('deactiveren: inloggen kan niet meer', mees.delete(f'/api/school/users/{uid}', headers=H).status_code == 200 and login('jan', r['password'])[1] != 200)
jan2 = login('piet-peters', [x for x in im['rows'] if x['username'] == 'piet-peters'][0]['password'])[0]
check('leerling heeft geen toegang tot gebruikersbeheer', jan2.get('/api/school/users').status_code == 403 and jan2.get('/api/users').status_code == 403)
check('beheerder kan met school_id ook een school beheren', len(adm.get('/api/school/users?school_id=%d' % sa).get_json()['users']) == 7)
# ---- verwijderen
def mk(user, fn):
    uid = A_uid(user); d = f'{ROOT}/m/school-a/leerlingen/{user}'; os.makedirs(d, exist_ok=True); open(f'{d}/{fn}', 'wb').write(b'x')
    with A.db() as c:
        c.execute('INSERT INTO models(root_id, path, name, ext, owner_id, school_id, shared) VALUES(?,?,?,?,?,?,1)', (rid, f'{d}/{fn}', fn[:-4], 'stl', uid, sa))
        return c.execute('SELECT last_insert_id()' if False else 'SELECT MAX(id) FROM models').fetchone()[0]
def A_uid(user):
    with A.db() as c: return c.execute('SELECT id FROM users WHERE username=?', (user,)).fetchone()[0]
m_jan, m_piet = mk('jan', 'j.stl'), mk('piet-peters', 'p.stl')
with A.db() as c: c.execute("INSERT INTO print_requests(model_id, model_name, requester_id, school_id, status, created, updated) VALUES(?,?,?,?,'open',?,?)", (m_piet, 'p', A_uid('piet-peters'), sa, time.time(), time.time()))
pv = mees.post('/api/school/users/remove', json=dict(inactive=True, preview=True), headers=H).get_json()
check('verwijderen: voorbeeld telt alleen gedeactiveerde leerlingen, wijzigt niets', pv['count'] == 1 and pv['models'] == 1 and A_uid('jan'), pv)
check('  leerling heeft hier geen toegang toe', jan2.post('/api/school/users/remove', json=dict(inactive=True), headers=H).status_code == 403)
check('  medewerker van een andere school raakt niets', nel.post('/api/school/users/remove', json=dict(ids=[A_uid('piet-peters')]), headers=H).get_json().get('removed') == 0)
r = mees.post('/api/school/users/remove', json=dict(inactive=True), headers=H).get_json()
with A.db() as c: mj = c.execute('SELECT owner_id, shared FROM models WHERE id=?', (m_jan,)).fetchone(); gone = c.execute('SELECT COUNT(*) FROM users WHERE username=?', ('jan',)).fetchone()[0]
check('  standaard bewaren: account weg, bestand en map blijven, zonder eigenaar en niet gedeeld', r['removed'] == 1 and gone == 0 and mj['owner_id'] is None and mj['shared'] == 0 and os.path.isfile(f'{ROOT}/m/school-a/leerlingen/jan/j.stl'), r)
check('  actieve leerlingen blijven staan', A_uid('piet-peters'))
r = mees.post('/api/school/users/remove', json=dict(ids=[A_uid('piet-peters')], files='delete'), headers=H).get_json()
with A.db() as c: mp = c.execute('SELECT COUNT(*) FROM models WHERE id=?', (m_piet,)).fetchone()[0]; pr = c.execute('SELECT status FROM print_requests WHERE model_name=?', ('p',)).fetchone()[0]
trash = [x for x in os.listdir(f'{ROOT}/m/.prullenbak')] if os.path.isdir(f'{ROOT}/m/.prullenbak') else []
check('  bestanden verwijderen: map naar .prullenbak, modelrijen weg, open printaanvraag geannuleerd', r['removed'] == 1 and mp == 0 and not os.path.exists(f'{ROOT}/m/school-a/leerlingen/piet-peters') and len(trash) == 1 and trash[0].endswith('school-a_leerlingen_piet-peters') and pr == 'cancelled', (r, trash, pr))
check('  printaanvraag blijft zichtbaar voor medewerker met "Verwijderde leerling"', any(x['requester'] == 'Verwijderde leerling' for x in mees.get('/api/requests').get_json()['requests']))
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
