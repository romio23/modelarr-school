"""Test: naam en logo (Modelarr) overal aanwezig en bereikbaar zonder inloggen. Gebruik: python tests/test_branding.py"""
import io, os, re, shutil, sys, tempfile, xml.dom.minidom
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-brand')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(ROOT); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
from PIL import Image
import app as A
A.init(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
rd = lambda p: open(os.path.join(APP, p), encoding='utf-8', newline='').read()
c = A.app.test_client(); c.post('/api/users', json={'username': 'beheer', 'password': 'geheim-123'}); anon = A.app.test_client()
h = anon.get('/').get_data(as_text=True)
check('titel Modelarr, favicon en iOS-icoon in de pagina (ook zonder inloggen)', '<title>Modelarr School</title>' in h and 'rel="icon"' in h and '/static/logo.svg' in h and 'apple-touch-icon' in h)
r = anon.get('/static/logo.svg'); xml.dom.minidom.parseString(r.data)
check('logo.svg bereikbaar zonder inloggen, geldige SVG', r.status_code == 200 and 'svg' in r.content_type)
im = Image.open(io.BytesIO(anon.get('/static/icon-180.png').data)); check('icon-180.png is een 180x180 PNG', im.size == (180, 180) and im.format == 'PNG')
js = rd('static/app.js'); check('navigatie en inlogpagina tonen logo en naam', js.count('/static/logo.svg') == 2 and js.count('Model<span') == 2 and '3D Modelbibliotheek' not in js)
css = rd('static/style.css'); check('logo: "Model" en "arr" staan in één item (geen spatie door de flex-opmaak)', '<span class="wm">Model<span>arr</span> School</span>' in js and '.logo .wm span{color' in css)
check('geen oude naam meer in pagina, docs en scripts (behalve het opruimen van de oude Windows-taak)', all('3D Modelbibliotheek' not in rd(f) for f in ('static/index.html', 'README.md', 'app.py', 'install-lxc.sh', 'start-windows.bat')) and rd('README.md').startswith('# Modelarr'))
check('Windows-autostart: nieuwe taak "Modelarr"; oude taak wordt opgeruimd bij aan én uit', 'Create /TN "Modelarr"' in rd('autostart-aan.bat') and 'Delete /TN "3D Modelbibliotheek"' in rd('autostart-aan.bat') and 'Delete /TN "Modelarr"' in rd('autostart-uit.bat') and 'Delete /TN "3D Modelbibliotheek"' in rd('autostart-uit.bat'))
check('batchbestanden houden CRLF-regeleinden', all('\r\n' in rd(f) and re.search(r'(?<!\r)\n', rd(f)) is None for f in ('autostart-aan.bat', 'autostart-uit.bat', 'start-windows.bat')))
check('technische naam is modelarr (compose, installatiescript, logbestand, update-script); geen modelbibliotheek meer in de actieve code', 'container_name: modelarr' in rd('docker-compose.yml') and 'modelarr.service' in rd('install-lxc.sh') and "'modelarr.log'" in rd('app.py') and 'modelbibliotheek' not in rd('app.py') and 'modelbibliotheek' not in rd('docker-compose.yml'))
check('het installatiescript neemt een bestaande installatie onder de oude naam over (database blijft behouden)', 'mv /var/lib/modelbibliotheek /var/lib/modelarr' in rd('install-lxc.sh'))

sys.exit(1 if bad else 0)
