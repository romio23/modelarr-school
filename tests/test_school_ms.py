"""Microsoft-login (groepen -> school/rol, klas uit Department) met nagebootste Microsoft-servers. Gebruik: python tests/test_school_ms.py"""
import base64, io, json, os, shutil, sys, tempfile, time, urllib.parse
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-school-ms'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A, integrations as INT
from werkzeug.security import generate_password_hash
A.init(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
TEN, CID = '11111111-2222-3333-4444-555555555555', 'client-abc'
G_ADM, G_STAFF, G_PUP, G_B = 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000004'
with A.db() as d:
    d.execute('INSERT INTO roots(path, allow_write) VALUES(?,1)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    d.execute('INSERT INTO schools(name, slug, root_id, group_id, staff_group_id, created) VALUES(?,?,?,?,?,?)', ('Werkman', 'werkman', rid, G_PUP, G_STAFF, time.time()))
    d.execute('INSERT INTO schools(name, slug, root_id, group_id, created) VALUES(?,?,?,?,?)', ('Tweede', 'tweede', rid, G_B, time.time()))
    d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, created, email) VALUES(?,?,?,1,1,?,?)', ('adm', generate_password_hash('wachtwoord1'), 'admin', time.time(), 'adm@school.nl'))
    d.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, school_id, created, email) VALUES(?,?,?,1,1,1,?,?)', ('oud', generate_password_hash('x'), 'student', time.time(), 'oud@school.nl'))
A.refresh_auth(); H = {'X-Requested-With': 'modelbib'}
for k, v in dict(ms_enabled='1', ms_tenant=TEN, ms_client_id=CID, ms_client_secret='geheim', ms_admin_group=G_ADM).items(): A.put(k, v)

# ---- nagebootste Microsoft
CALLS = []; NEXT = {}
def jwt(c): return 'x.' + base64.urlsafe_b64encode(json.dumps(c).encode()).decode().rstrip('=') + '.y'
def fake_http(method, url, data=None, headers=None, body=None, timeout=20):
    CALLS.append((method, url, data, body, headers))
    if url.endswith('/oauth2/v2.0/token') and data and data.get('grant_type') == 'authorization_code':
        c = dict(aud=CID, iss=f'https://login.microsoftonline.com/{TEN}/v2.0', tid=TEN, exp=time.time() + 600, oid='oid-1', preferred_username='jan.jansen@school.nl', name='Jan Jansen', groups=[G_PUP])
        c.update(NEXT.get('claims', {})); c['nonce'] = NEXT.get('nonce', NONCE[0])
        return 200, dict(id_token=jwt(c), access_token='AT', refresh_token='RT-' + c['oid'])
    if url.endswith('/oauth2/v2.0/token') and data and data.get('grant_type') == 'refresh_token':
        if data['refresh_token'] == 'RT-dood': return 400, dict(error='invalid_grant')
        return 200, dict(access_token='UT-' + data['refresh_token'], refresh_token=data['refresh_token'] + '+')
    if url.endswith('/oauth2/v2.0/token'): return 200, dict(access_token='GT', expires_in=3600)
    if url.endswith('/me/getMemberObjects'): return 200, dict(value=[G_STAFF.upper()])
    if url.startswith(INT.GRAPH + '/me?'): return 200, dict(department=NEXT.get('dept', '1B'))
    if '/sendMail' in url: return 202, {}
    return 404, {}
INT.http = fake_http; NONCE = [None]
def login(claims=None, nonce=None, code='c'):
    NEXT.clear(); NEXT['claims'] = claims or {}
    c = A.app.test_client(); r = c.get('/api/ms/login'); assert r.status_code == 302, r.status_code
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers['Location']).query)
    NONCE[0] = q['nonce'][0]
    if nonce: NEXT['nonce'] = nonce
    r = c.get('/api/ms/callback?' + urllib.parse.urlencode(dict(state=q['state'][0], code=code)))
    return c, r, q

c, r, q = login()
check('login-URL: PKCE, scope, redirect', q['code_challenge_method'] == ['S256'] and 'openid' in q['scope'][0] and q['redirect_uri'][0].endswith('/api/ms/callback'), q)
me = c.get('/api/me').get_json()
check('leerlingengroep: ingelogd als leerling van de juiste school', r.status_code == 302 and me['role'] == 'student' and me['school']['name'] == 'Werkman' and me['display'] == 'Jan Jansen', me)
with A.db() as d: u = d.execute("SELECT * FROM users WHERE ms_oid='oid-1'").fetchone()
check('  klas overgenomen uit het veld Afdeling', u['klas'] == '1B', u['klas'])
check('  eigen map aangemaakt', u['home'] == 'werkman/leerlingen/jan-jansen' and os.path.isdir(f'{ROOT}/m/werkman/leerlingen/jan-jansen'), u['home'])
c, r, q = login(dict(oid='oid-1', groups=[G_PUP])); NEXT.clear()
with A.db() as d: k0 = d.execute("SELECT klas FROM users WHERE ms_oid='oid-1'").fetchone()[0]
check('  volgende login: klas blijft (of wordt) die uit Microsoft', k0 == '1B')
A.put('ms_klas', '0')
with A.db() as d: d.execute("UPDATE users SET klas='handmatig' WHERE ms_oid='oid-1'")
c, r, q = login(dict(oid='oid-1', groups=[G_PUP]))
with A.db() as d: k1 = d.execute("SELECT klas FROM users WHERE ms_oid='oid-1'").fetchone()[0]
check('  schakelaar uit: handmatige klas blijft staan', k1 == 'handmatig', k1)
A.put('ms_klas', '1')
c, r, q = login(dict(oid='oid-1', groups=[G_PUP, G_STAFF]))
check('medewerkersgroep gaat voor leerlingengroep; rol volgt de groep bij elke login', c.get('/api/me').get_json()['role'] == 'staff')
c, r, q = login(dict(oid='oid-2', preferred_username='piet@school.nl', name='Piet', groups=[G_B]))
check('andere school via andere groep', c.get('/api/me').get_json()['school']['name'] == 'Tweede')
c, r, q = login(dict(oid='oid-3', preferred_username='beheer@school.nl', name='Beheer', groups=[G_ADM, G_PUP]))
check('beheerdersgroep: beheerder zonder school', (lambda m: m['role'] == 'admin' and m['school'] is None)(c.get('/api/me').get_json()))
c, r, q = login(dict(oid='oid-4', preferred_username='x@school.nl', groups=['onbekend']))
check('geen bekende groep: geweigerd', r.status_code == 403 and c.get('/api/me').get_json()['user'] is None)
c, r, q = login(dict(oid='oid-5', preferred_username='oud@school.nl', groups=[G_PUP]))
with A.db() as d: n = d.execute("SELECT COUNT(*) FROM users WHERE username='oud'").fetchone()[0]; o = d.execute("SELECT ms_oid FROM users WHERE username='oud'").fetchone()[0]
check('bestaand lokaal account met hetzelfde adres wordt gekoppeld', n == 1 and o == 'oid-5' and c.get('/api/me').get_json()['user'] == 'oud')
for n, cl, nonce in (('verkeerde nonce', {}, 'anders'), ('verkeerde client (aud)', dict(aud='ander'), None), ('verlopen token', dict(exp=1), None),
                     ('andere tenant', dict(tid='99999999-2222-3333-4444-555555555555'), None), ('onbekende uitgever', dict(iss='https://evil.example/v2.0'), None)):
    c, r, q = login(dict(oid='oid-9', **cl), nonce=nonce); check('token geweigerd: ' + n, r.status_code == 400 and c.get('/api/me').get_json()['user'] is None, r.status_code)
c = A.app.test_client(); c.get('/api/ms/login'); r = c.get('/api/ms/callback?state=fout&code=c'); check('verkeerde state geweigerd', r.status_code == 400)
c = A.app.test_client(); r = c.get('/api/ms/callback?state=a&code=c'); check('callback zonder begonnen inlog geweigerd', r.status_code == 400)
CALLS.clear(); c, r, q = login(dict(oid='oid-6', preferred_username='veel@school.nl', groups=None, _claim_names=dict(groups='src1')))
gm = [x for x in CALLS if x[1].endswith('getMemberObjects')]
check('veel groepen (overage): groepen via Graph opgehaald (hoofdletterongevoelig)', gm and c.get('/api/me').get_json()['role'] == 'staff')
# ms_only
A.put('ms_only', '1')
lc = A.app.test_client()
check('alleen Microsoft: leerling kan niet met wachtwoord', lc.post('/api/login', json=dict(username='oud', password='x'), headers=H).status_code == 403)
check('  lokale beheerder houdt een noodingang', lc.post('/api/login', json=dict(username='adm', password='wachtwoord1'), headers=H).status_code == 200)
check('  /api/me meldt ms en ms_only voor de inlogpagina', (lambda m: m['ms'] and m['ms_only'])(A.app.test_client().get('/api/me').get_json()))
A.put('ms_only', '0')
A.put('ms_enabled', '0'); check('uitgeschakeld: /api/ms/login 404', A.app.test_client().get('/api/ms/login').status_code == 404); A.put('ms_enabled', '1')
# instellingen: geheim wordt nooit teruggegeven
ac = A.app.test_client(); ac.post('/api/login', json=dict(username='adm', password='wachtwoord1'), headers=H)
st = ac.get('/api/settings').get_json()
check('instellingen tonen het clientgeheim niet', 'geheim' not in json.dumps(st) and st['ms_secret_set'] and st['ms_redirect'].endswith('/api/ms/callback'))
r = ac.post('/api/settings', json=dict(ms_tenant='nietgeldig'), headers=H); check('ongeldige tenant geweigerd', r.status_code == 400)
check('niet-beheerder mag de instellingen niet lezen', A.app.test_client().get('/api/settings').status_code == 401)
r = ac.get('/api/settings').get_json(); check('instellingen bevatten geen e-mailopties meer', not [k for k in r if k.startswith(('mail_', 'smtp_'))])
A.put('ms_tenant', TEN)
r = ac.post('/api/settings', json=dict(public_url='http://localhost:8765/api/ms/callback/'), headers=H)
st = ac.get('/api/settings').get_json()
check('publiek adres: een pad erachter wordt weggehaald, omleidings-URL klopt', r.status_code == 200 and st['public_url'] == 'http://localhost:8765' and st['ms_redirect'] == 'http://localhost:8765/api/ms/callback', st['ms_redirect'])
ac.post('/api/settings', json=dict(public_url=''), headers=H)

print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
