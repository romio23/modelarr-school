"""Test: tijdelijke slicer-links (/dl/...) en 'openen met standaardprogramma'. De slicer zelf wordt niet gestart.
Gebruik: python tests/test_links.py"""
import io, os, shutil, sys, tempfile, time, zipfile
import trimesh
from werkzeug.security import generate_password_hash
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-links')
shutil.rmtree(ROOT, ignore_errors=True); M = f'{ROOT}/models'; os.makedirs(M); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
BOX = trimesh.exchange.stl.export_stl(trimesh.creation.box((40, 20, 10))); CYL = trimesh.exchange.stl.export_stl(trimesh.creation.cylinder(8, 30))
open(f'{M}/my model (v2).stl', 'wb').write(BOX)
with zipfile.ZipFile(f'{M}/pack.zip', 'w') as z: z.writestr('sub/inner.stl', CYL)
for f in os.listdir(M): os.utime(f'{M}/{f}', (time.time() - 600,) * 2)
A.init(); A.put('min_age', '0'); c = A.app.test_client(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (M,))
A.scan(); L = {m['name']: m for m in c.get('/api/library').get_json()['models']}
loose, member = L['my model (v2)'], L['inner']
check('model en zip-onderdeel staan in de bibliotheek', loose and member and member['container'] == 'pack.zip')
lib = c.get('/api/library').get_json()
check('bibliotheek meldt de gekozen slicer (standaard Bambu Studio)', lib['slicer'] == {'name': 'Bambu Studio', 'scheme': 'bambustudio://open?file='}, lib['slicer'])
r = c.post(f"/api/models/{loose['id']}/link").get_json(); path = r['path']
check('link: /dl/<id>.<verloop>.<handtekening>/<bestandsnaam>, spaties en haakjes gecodeerd', path.startswith(f"/dl/{loose['id']}.") and path.endswith('/my%20model%20%28v2%29.stl') and r['expires'] == 600 and r['scheme'].startswith('bambustudio://'), path)
g = c.get(path); check('link levert het bestand', g.status_code == 200 and g.data == BOX)
adm, anon = A.app.test_client(), A.app.test_client(); adm.post('/api/users', json={'username': 'u', 'password': 'wachtwoord1'})  # eerste account: beheerder, meteen ingelogd
check('met inlog: bibliotheek vraagt om wachtwoord (401), de ondertekende link niet', anon.get('/api/library').status_code == 401 and anon.get(path).status_code == 200 and anon.post(f"/api/models/{loose['id']}/link", headers={'X-Requested-With': 'modelbib'}).status_code == 401)
adm.post('/api/users/clear', json={'confirm': True}, headers={'X-Requested-With': 'modelbib'})
tok = path.split('/')[2]; mid, exp, sig = tok.split('.')
check('geknoeide handtekening: 403', c.get(f'/dl/{mid}.{exp}.{"0" * 32}/x.stl').status_code == 403)
check('link van model A werkt niet voor model B (id aangepast): 403', c.get(f"/dl/{member['id']}.{exp}.{sig}/x.stl").status_code == 403)
check('verlengde verlooptijd met oude handtekening: 403', c.get(f'/dl/{mid}.{int(exp) + 9999}.{sig}/x.stl').status_code == 403)
old = A.make_token(loose['id'], ttl=-5); check('verlopen link: 403 met duidelijke tekst', c.get(f'/dl/{old}/x.stl').status_code == 403 and 'verlopen' in c.get(f'/dl/{old}/x.stl').get_data(as_text=True))
check('onzin als link: 403, geen crash', all(c.get(f'/dl/{t}/x.stl').status_code == 403 for t in ('abc', '1.2', '..', '1.x.y')))
z = c.get(c.post(f"/api/models/{member['id']}/link").get_json()['path']); check('zip-onderdeel: alleen dat bestand uitgepakt geleverd', z.status_code == 200 and z.data == CYL)
os.rename(f'{M}/my model (v2).stl', f'{M}/weg.stl'); check('bestand verdwenen na het maken van de link: 404', c.get(path).status_code == 404); os.rename(f'{M}/weg.stl', f'{M}/my model (v2).stl')
check('slicer wijzigen: onbekende geweigerd, OrcaSlicer wordt gebruikt', c.post('/api/settings', json={'slicer': 'nonsens'}).status_code == 400 and c.post('/api/settings', json={'slicer': 'orcaslicer'}).status_code == 200 and c.post(f"/api/models/{loose['id']}/link").get_json()['scheme'] == 'orcaslicer://open?file=')
c.post('/api/settings', json={'slicer': 'bambustudio'})
# ---- openen met standaardprogramma
opened = []; A.open_file = opened.append; A.OPEN_OK = True
check('niet-lokale gebruiker (10.0.0.5): geweigerd (403), niets geopend', c.post(f"/api/models/{loose['id']}/open", environ_overrides={'REMOTE_ADDR': '10.0.0.5'}).status_code == 403 and not opened)
check('bibliotheek: local=false voor niet-lokale gebruiker, true voor lokale', c.get('/api/library', environ_overrides={'REMOTE_ADDR': '10.0.0.5'}).get_json()['local'] is False and c.get('/api/library', environ_overrides={'REMOTE_ADDR': '127.0.0.1'}).get_json()['local'] is True)
check('lokale gebruiker: bestand wordt geopend', c.post(f"/api/models/{loose['id']}/open", environ_overrides={'REMOTE_ADDR': '127.0.0.1'}).status_code == 200 and opened == [loose['path']], opened)
check('lokale gebruiker, zip-onderdeel: uitgepakte kopie wordt geopend', c.post(f"/api/models/{member['id']}/open", environ_overrides={'REMOTE_ADDR': '127.0.0.1'}).status_code == 200 and open(opened[-1], 'rb').read() == CYL and opened[-1].endswith('inner.stl'), opened[-1])
A.OPEN_OK = False; check('geen opener beschikbaar op dit systeem: 403 en local=false', c.post(f"/api/models/{loose['id']}/open", environ_overrides={'REMOTE_ADDR': '127.0.0.1'}).status_code == 403 and c.get('/api/library').get_json()['local'] is False)
A.OPEN_OK = True; os.remove(loose['path']); check('bestand weg: 404', c.post(f"/api/models/{loose['id']}/open", environ_overrides={'REMOTE_ADDR': '127.0.0.1'}).status_code == 404)
check('ondertekende links zitten niet in het zoeken/de API-lijst (geen geheimen in /api/settings)', 'link_secret' not in c.get('/api/settings').get_json() and A.CFG['link_secret'] not in c.get('/api/settings').get_data(as_text=True))
sys.exit(1 if bad else 0)
