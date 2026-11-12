"""Scholen: inloggen, blokkeren na foute pogingen, laatste beheerder, dubbele namen/e-mail. Gebruik: python tests/test_school_auth.py"""
import os, shutil, sys, tempfile, time
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-auth'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
A.init(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
H = {'X-Requested-With': 'modelbib'}
mk = lambda: A.app.test_client()
check('zonder accounts is iedereen beheerder', mk().get('/api/me').get_json()['role'] == 'admin')
c = mk(); r = c.post('/api/users', json=dict(username='Beheer', password='geheim-123'), headers=H); check('eerste account wordt beheerder en blijft ingelogd', r.get_json().get('auto_login') and c.get('/api/me').get_json()['role'] == 'admin')
check('daarna is inloggen verplicht', mk().get('/api/library').status_code == 401)
with A.db() as d:
    d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
c.post('/api/schools', json=dict(name='School A', root_id=1), headers=H); sa = c.get('/api/schools').get_json()['schools'][0]['id']
check('medewerker/leerling zonder school wordt geweigerd', c.post('/api/users', json=dict(username='x', password='wachtwoord1', role='student'), headers=H).status_code == 400)
check('dubbele naam (hoofdletterongevoelig): 409', c.post('/api/users', json=dict(username='Mees', password='wachtwoord1', role='staff', school_id=sa), headers=H).status_code == 200 and c.post('/api/users', json=dict(username='mees', password='wachtwoord1', role='staff', school_id=sa), headers=H).status_code == 409)
check('dubbel e-mailadres: 409', c.post('/api/users', json=dict(username='n1', password='wachtwoord1', role='staff', school_id=sa, email='a@b.nl'), headers=H).status_code == 200 and c.post('/api/users', json=dict(username='n2', password='wachtwoord1', role='staff', school_id=sa, email='A@B.nl'), headers=H).status_code == 409)
check('te kort wachtwoord: 400', c.post('/api/users', json=dict(username='n3', password='kort', role='staff', school_id=sa), headers=H).status_code == 400)
check('de laatste beheerder: niet verwijderen, niet degraderen, niet deactiveren', c.delete('/api/users/1', headers=H).status_code == 400 and c.put('/api/users/1', json={'role': 'staff', 'school_id': sa}, headers=H).status_code == 400 and c.put('/api/users/1', json={'active': False}, headers=H).status_code == 400)
check('verkeerd wachtwoord: 401, na 5 pogingen geblokkeerd', all(mk().post('/api/login', json=dict(username='mees', password='fout'), headers=H).status_code == 401 for _ in range(5)) and mk().post('/api/login', json=dict(username='mees', password='wachtwoord1'), headers=H).status_code == 429)
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
