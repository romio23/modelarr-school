"""Test: padinvoer (aanhalingstekens, UNC), Windows-stationslijst en UNC-vertaling van gekoppelde schijven (met nagebootste Windows-API's).
Gebruik: python tests/test_paths.py"""
import os, shutil, sys, tempfile
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-paths')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/models')
os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); c = A.app.test_client(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
check('clean_path: aanhalingstekens en spaties weg', [A.clean_path(x) for x in ('  "\\\\nas\\share\\dir" ', "'D:\\3D'", '', None)] == ['\\\\nas\\share\\dir', 'D:\\3D', '', ''])
check('alleen-server UNC-pad herkend', [A.unc_server_only(x) for x in ('\\\\nas', '\\\\nas\\', '//nas', '\\\\nas\\share', '\\\\nas\\share\\sub', 'C:\\x', '/mnt/x')] == [True, True, True, False, False, False, False])
check('stationslijst uit bitmasker (A, C, D)', A.windows_drives(get_mask=lambda: 0b1101) == ['A:\\', 'C:\\', 'D:\\'])
check('stationslijst: terugval zonder crash als de API ontbreekt', isinstance(A.windows_drives(get_mask=lambda: 1 / 0), list))
def fake(drive, buf, n):
    if drive == 'Z:': buf.value = '\\\\nas\\modellen\\'; return 0
    return 2250  # ERROR_NOT_CONNECTED
r = {p: A.unc_of(p, fake) for p in ('Z:\\sub\\dir', 'Z:\\', 'C:\\x', '\\\\nas\\share\\x', '/tmp', 'z:\\kleine\\letter')}
check('gekoppelde schijf -> UNC-pad', r == {'Z:\\sub\\dir': '\\\\nas\\modellen\\sub\\dir', 'Z:\\': '\\\\nas\\modellen\\', 'C:\\x': None, '\\\\nas\\share\\x': None, '/tmp': None, 'z:\\kleine\\letter': None}, r)
check('unc_of zonder Windows-API geeft None (geen crash)', A.unc_of('Z:\\x') is None)
s = c.get('/api/fs?path=' + '"/tmp"'); j = s.get_json()
check('mapkiezer: pad met aanhalingstekens werkt, antwoord bevat unc-veld', s.status_code == 200 and j['path'] == '/tmp' and j['unc'] is None, j.get('path'))
import tempfile as _tf
_d = _tf.mkdtemp()
for _n in ('zichtbaar', '.back-ups', '@eaDir', '#recycle'): os.makedirs(os.path.join(_d, _n))
_names = lambda q: sorted(x['name'] for x in c.get('/api/fs?path=' + _d + q).get_json()['dirs'])
check('mapkiezer: mappen met een punt of @ # $ blijven standaard verborgen', _names('') == ['zichtbaar'], _names(''))
check('mapkiezer met hidden=1 (back-upmap): ook mappen met een punt, maar nog steeds geen @eaDir of #recycle', _names('&hidden=1') == ['.back-ups', 'zichtbaar'], _names('&hidden=1'))
check('mapkiezer: onbekende map geeft een foutmelding (400)', c.get('/api/fs?path=/bestaat/niet').status_code == 400)
s = c.post('/api/roots', json={}); check('leeg pad toevoegen: 400 (voegde eerst de werkmap toe)', s.status_code == 400 and c.get('/api/roots').get_json() == [], s.get_json())
check('alleen spaties: 400', c.post('/api/roots', json={'path': '   '}).status_code == 400)
check('onbekend pad: 400', c.post('/api/roots', json={'path': '/bestaat/niet'}).status_code == 400)
s = c.post('/api/roots', json={'path': f'  "{ROOT}/models"  '}); roots = c.get('/api/roots').get_json()
check('pad met aanhalingstekens en spaties wordt opgeslagen zonder', s.status_code == 200 and [r['path'] for r in roots] == [f'{ROOT}/models'], [r['path'] for r in roots])
import ntpath
check('kale share krijgt een slash (Python 3.15 plakte anders de mapnaam er direct achter)', A.walk_top('\\\\192.168.1.10\\3d', ntpath) == '\\\\192.168.1.10\\3d\\', A.walk_top('\\\\192.168.1.10\\3d', ntpath))
check('kale schijfletter C: krijgt een slash', A.walk_top('C:', ntpath) == 'C:\\')
check('paden die al een map of slash hebben blijven gelijk', all(A.walk_top(x, ntpath) == x for x in ('\\\\h\\3d\\Auto', 'C:\\', 'D:\\Modellen', '\\\\h\\3d\\')))
check('Linux-paden blijven gelijk', A.walk_top('/models') == '/models' and A.walk_top('/') == '/')
sys.exit(1 if bad else 0)
