"""Scholen: de melding over een offline/lege root folder toont paden alleen aan de beheerder. Gebruik: python tests/test_school_root_alert.py"""
import os, shutil, sys, tempfile, time
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-alert'); shutil.rmtree(ROOT, ignore_errors=True)
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
    c = A.app.test_client(); c.post('/api/login', json=dict(username=n, password=pw), headers=H); return c
adm = login('adm')
adm.post('/api/schools', json=dict(name='School A', root_id=rid), headers=H)
sa = adm.get('/api/schools').get_json()['schools'][0]['id']
adm.post('/api/users', json=dict(username='mees', password='wachtwoord1', role='staff', school_id=sa), headers=H)
mees = login('mees')
pw = mees.post('/api/school/users', json=dict(username='jan', display_name='Jan Jansen', klas='1A'), headers=H).get_json()['password']
jan = login('jan', pw)

check('zonder melding: lege lijst voor iedereen', all(c.get('/api/rev').get_json()['roots_alert'] == [] for c in (adm, mees, jan)))
A.ROOT_ALERT[rid] = dict(kind='empty', path=f'{ROOT}/m', known=12, dirs=0, since=time.time())
a, m, j = (c.get('/api/rev').get_json()['roots_alert'] for c in (adm, mees, jan))
check('beheerder ziet pad en aantal modellen', len(a) == 1 and a[0]['path'] == f'{ROOT}/m' and a[0]['known'] == 12, a)
check('medewerker ziet alleen dat er iets mis is, zonder pad', m == [dict(id=rid, kind='empty')], m)
check('leerling ziet alleen dat er iets mis is, zonder pad', j == [dict(id=rid, kind='empty')], j)
A.ROOT_ALERT.clear()
print('\nALLES GOED' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
