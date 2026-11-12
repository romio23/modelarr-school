"""Scholen: eigenaar uit het pad, zichtbaarheid (eigen map + gedeeld, opt-out, verborgen, andere school), bibliotheek en bestandsrechten.
Gebruik: python tests/test_school_visibility.py"""
import os, shutil, sys, tempfile, time
import trimesh
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-vis'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
from werkzeug.security import generate_password_hash
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
def mk(rel):
    p = f'{ROOT}/m/{rel}'; os.makedirs(os.path.dirname(p), exist_ok=True); trimesh.creation.box((5, 5, 5)).export(p); os.utime(p, (time.time() - 600,) * 2)
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?,1)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    for n, sl in (('School A', 'school-a'), ('School B', 'school-b')): d.execute('INSERT INTO schools(name, slug, root_id, created) VALUES(?,?,?,?)', (n, sl, rid, time.time()))
    sa, sb = [r[0] for r in d.execute('SELECT id FROM schools ORDER BY id')]
    def user(name, role, sid, home, disp):
        d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, school_id, home, display_name, klas, created) VALUES(?,?,?,1,1,?,?,?,?,?)',
                  (name, generate_password_hash('wachtwoord1'), role, sid, home, disp, '1A' if role == 'student' else '', time.time()))
        return d.execute('SELECT id FROM users WHERE username=?', (name,)).fetchone()[0]
    uid = dict(adm=user('adm', 'admin', None, None, 'Beheer'), jan=user('jan', 'student', sa, 'school-a/leerlingen/jan', 'Jan Jansen'), piet=user('piet', 'student', sa, 'school-a/leerlingen/piet', 'Piet Peters'),
               kees=user('kees', 'student', sb, 'school-b/leerlingen/kees', 'Kees Klein'), mees=user('mees', 'staff', sa, 'school-a/medewerkers/mees', 'Mees Meester'), nel=user('nel', 'staff', sb, 'school-b/medewerkers/nel', 'Nel Nijhuis'))
for r in ('school-a/leerlingen/jan/jan1.stl', 'school-a/leerlingen/jan/privé.stl', 'school-a/leerlingen/piet/piet1.stl', 'school-b/leerlingen/kees/kees1.stl', 'school-a/bibliotheek/schoolA-lib.stl', 'los.stl', 'algemeen/oud/x.stl', 'algemeen/ok/y.stl'): mk(r)
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
with A.db() as d:
    own = {r['name']: (r['owner_id'], r['school_id']) for r in d.execute('SELECT name, owner_id, school_id FROM models')}
check('eigenaar en school worden uit het pad afgeleid', own['jan1'] == (uid['jan'], sa) and own['piet1'] == (uid['piet'], sa) and own['kees1'] == (uid['kees'], sb), own)
check('  bestand in de schoolmap zonder leerling heeft een school maar geen eigenaar; los bestand heeft geen school', own['schoolA-lib'] == (None, sa) and own['los'] == (None, None))
with A.db() as d:
    d.execute("UPDATE models SET shared=0 WHERE name='privé'")
A.AUTH_ON[0] = True
H = {'X-Requested-With': 'modelbib'}
def login(n):
    c = A.app.test_client(); r = c.post('/api/login', json=dict(username=n, password='wachtwoord1'), headers=H); assert r.status_code == 200, r.data; return c
cl = {n: login(n) for n in uid}
names = lambda n: sorted(m['name'] for m in cl[n].get('/api/library').get_json()['models'])
check('beheerder ziet alles', names('adm') == sorted(['jan1', 'privé', 'piet1', 'kees1', 'schoolA-lib', 'los', 'x', 'y']), names('adm'))
check('leerling ziet eigen modellen, gedeelde modellen van anderen (ook andere school) en de schoolbibliotheek, ook de algemene bibliotheek, maar niet het privé-model van een ander', names('piet') == ['jan1', 'kees1', 'los', 'piet1', 'schoolA-lib', 'x', 'y'], names('piet'))
check('leerling ziet zijn eigen privé-model wel', names('jan') == ['jan1', 'kees1', 'los', 'piet1', 'privé', 'schoolA-lib', 'x', 'y'], names('jan'))
check('medewerker ziet alles van de eigen school, inclusief privé; van een andere school alleen het gedeelde', names('mees') == ['jan1', 'kees1', 'los', 'piet1', 'privé', 'schoolA-lib', 'x', 'y'] and names('nel') == ['jan1', 'kees1', 'los', 'piet1', 'schoolA-lib', 'x', 'y'], (names('mees'), names('nel')))
mid = {m['name']: m['id'] for m in cl['adm'].get('/api/library').get_json()['models']}
check('niet-zichtbaar model: bestand, thumbnail en 3D-weergave geven 404', all(cl['piet'].get(f'/api/{x}/{mid["privé"]}{y}').status_code == 404 for x, y in (('file', ''), ('thumb', '.png'), ('mesh', '.stl'))))
check('zichtbaar model downloaden werkt', cl['piet'].get(f'/api/file/{mid["jan1"]}').status_code == 200)
check('leerling en medewerker laden de bibliotheek zonder fout', all(c.get(u).status_code == 200 for c in (cl['piet'], cl['mees']) for u in ('/api/library', '/api/rev', '/api/printers', '/api/me', '/api/requests', '/api/requests/options', '/api/library?page=0&size=100&sort=name&cat=all&ext=all&flt=all')))
check('leerling mag niets van het beheer', all(cl['piet'].get(u).status_code == 403 for u in ('/api/users', '/api/settings', '/api/roots', '/api/duplicates', '/api/logs')))
lib = cl['piet'].get('/api/library').get_json()
m1 = [m for m in lib['models'] if m['name'] == 'jan1'][0]
check('andermans model, eigen school: alleen voornaam; geen paden of ids', m1['owner'] == 'Jan' and m1['mine'] is False and m1['manage'] is False and m1['path'] == 'jan1.stl' and not m1['owner_id'], str({k: m1[k] for k in ('owner', 'path', 'owner_id')}))
mk_ = [m for m in cl['kees'].get('/api/library').get_json()['models'] if m['name'] == 'jan1'][0]
mn = [m for m in cl['nel'].get('/api/library').get_json()['models'] if m['name'] == 'jan1'][0]
check('andere school (leerling én medewerker): alleen de schoolnaam', mk_['owner'] == 'School A' and mn['owner'] == 'School A', (mk_['owner'], mn['owner']))
mm = [m for m in cl['mees'].get('/api/library').get_json()['models'] if m['name'] == 'jan1'][0]
check('medewerker van dezelfde school ziet de volledige naam en klas', mm['owner'] == 'Jan Jansen (1A)' and mm['manage'] is True, mm['owner'])
check('algemene bibliotheek: los bestand heeft map en geen eigenaar-naam', [m for m in cl['piet'].get('/api/library').get_json()['models'] if m['name'] == 'x'][0]['folder'] == 'algemeen/oud')
with A.db() as d: rid = d.execute('SELECT id FROM roots').fetchone()[0]
check('medewerker verbergt een map: leerlingen zien die modellen niet meer, medewerker en beheerder wel',
      cl['mees'].post('/api/folder-access/hide', json=dict(root=rid, path='algemeen/oud', hidden=True), headers=H).status_code == 200
      and 'x' not in names('piet') and 'y' in names('piet') and 'x' in names('mees') and 'x' in names('adm') and 'x' not in names('kees'))
check('  ook bestand/thumbnail van een verborgen map geven 404', cl['piet'].get(f'/api/file/{mid["x"]}').status_code == 404 and cl['piet'].get(f'/api/thumb/{mid["x"]}.png').status_code == 404)
fl = cl['mees'].get(f'/api/folder-access?root={rid}').get_json()['dirs']; sub = cl['mees'].get(f'/api/folder-access?root={rid}&path=algemeen').get_json()['dirs']
check('  mappenlijst: schoolmappen ontbreken; verborgen map is gemarkeerd', {d['name'] for d in fl} == {'algemeen'} and [(d['name'], d['hidden']) for d in sub] == [('ok', False), ('oud', True)], (fl, sub))
with A.db() as d: d.execute('DELETE FROM hidden_folders'); d.execute('INSERT INTO hidden_folders VALUES(?,?)', (rid, 'algemeen'))
check('  een bovenliggende verborgen map verbergt ook de submappen', 'y' not in names('piet') and 'x' not in names('piet'))
check('  leerling mag mappen niet beheren', cl['piet'].post('/api/folder-access/hide', json=dict(root=rid, path='algemeen', hidden=False), headers=H).status_code == 403 and cl['piet'].get('/api/folder-access').status_code == 403)
check('  weer tonen', cl['adm'].post('/api/folder-access/hide', json=dict(root=rid, path='algemeen', hidden=False), headers=H).status_code == 200 and {'x', 'y'} <= set(names('piet')))
check('  pad buiten de root of verborgen map wordt geweigerd', cl['mees'].post('/api/folder-access/hide', json=dict(root=rid, path='../x', hidden=True), headers=H).status_code == 400)
check('categorieën tellen alleen wat je mag zien', all(c['count'] == 0 for c in lib['categories']))
with A.db() as d: d.execute("UPDATE models SET hidden=1 WHERE name='jan1'")
check('verborgen model: andere leerlingen zien het niet, de eigenaar en de medewerker wel', 'jan1' not in names('piet') and 'jan1' in names('jan') and 'jan1' in names('mees') and 'jan1' not in names('nel'))
pg = cl['piet'].get('/api/library?page=0&size=100&sort=name').get_json()
check('leerling: alle aanroepen van de bibliotheekpagina werken (library met paginering, printers, rev, me)', pg['total'] > 0 and all(cl['piet'].get(u).status_code == 200 for u in ('/api/printers', '/api/rev', '/api/me', '/api/me/prefs')))
check('leerling krijgt geen beheertellers via /api/rev', cl['piet'].get('/api/rev').get_json()['pending'] == 0)
fl = lambda n, q: sorted(m['name'] for m in cl[n].get('/api/library?' + q).get_json()['models'])
check('filter op leerling: medewerker ziet alle bestanden van die leerling (ook privé)', fl('mees', f"owner={uid['jan']}") == ['jan1', 'privé'], fl('mees', f"owner={uid['jan']}"))
check('filter op school (beheerder) en school + leerling', fl('adm', f'school={sb}') == ['kees1'] and fl('adm', f"school={sa}&owner={uid['piet']}") == ['piet1'], fl('adm', f'school={sb}'))
check('medewerker kan niet op school filteren (parameter genegeerd)', len(fl('mees', f'school={sb}')) == len(names('mees')))
check('leerling kan niet filteren op een andere leerling', fl('piet', f"owner={uid['jan']}") == names('piet'))
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
