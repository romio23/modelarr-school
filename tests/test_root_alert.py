"""Test: een root folder die offline is, onverwacht leeg (share niet gekoppeld) of deels onleesbaar geeft een melding
in de webinterface en de modellen blijven in de bibliotheek staan. Gebruik: python tests/test_root_alert.py"""
import os, shutil, sys, tempfile, time
import trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-rootalert')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(ROOT); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
c = A.app.test_client(); STL = trimesh.exchange.stl.export_stl(trimesh.creation.box((10, 10, 10)))
M = f'{ROOT}/mount'
def tree():
    for p in ('a.stl', 'sub/b.stl', 'sub/c.stl', 'other/d.stl'):
        os.makedirs(os.path.dirname(f'{M}/{p}'), exist_ok=True); open(f'{M}/{p}', 'wb').write(STL); os.utime(f'{M}/{p}', (time.time() - 600,) * 2)
def rescan():
    for _ in range(60):
        if A.scan() is not False: return
        time.sleep(.2)
def names():
    with A.db() as d: return sorted(r['name'] for r in d.execute('SELECT name FROM models'))
alerts = lambda: c.get('/api/rev').get_json()['roots_alert']
status = lambda: c.get('/api/roots').get_json()[0]
hist = lambda: [h['message'] for h in c.get('/api/history').get_json()]

tree()
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (M,))
rescan()
check('uitgangspunt: 4 modellen, geen melding', names() == ['a', 'b', 'c', 'd'] and alerts() == [], (names(), alerts()))

# 1. share niet gekoppeld: het mountpunt bestaat nog, maar is leeg (zoals na een herstart met de NAS nog uit)
shutil.move(M, M + '.weg'); os.makedirs(M); A.NEXT['soon'] = 0
rescan(); a = alerts()
check('lege root: niets verwijderd', names() == ['a', 'b', 'c', 'd'], names())
check('lege root: melding "empty" met het aantal bekende modellen', len(a) == 1 and a[0]['kind'] == 'empty' and a[0]['known'] == 4 and a[0]['path'] == M, a)
check('lege root: status in Instellingen toont de melding', status()['alert'] == 'empty' and status()['ok'] is True, status())
check('lege root: binnen een minuut opnieuw scannen', 0 < A.NEXT['soon'] - time.time() <= A.ALERT_RETRY + 1, A.NEXT['soon'] - time.time())
check('lege root: één regel in de geschiedenis', sum('lijkt leeg' in m for m in hist()) == 1, hist()[:3])
rescan()
check('nogmaals scannen: geen tweede geschiedenisregel en "since" blijft gelijk', sum('lijkt leeg' in m for m in hist()) == 1 and alerts()[0]['since'] == a[0]['since'])

# 2. mountpunt helemaal weg (share-map bestaat niet)
os.rmdir(M); rescan(); a = alerts()
check('offline root: niets verwijderd', names() == ['a', 'b', 'c', 'd'], names())
check('offline root: melding "offline"', len(a) == 1 and a[0]['kind'] == 'offline' and a[0]['known'] == 4, a)
check('offline root: status "niet bereikbaar"', status()['ok'] is False and status()['alert'] == 'offline', status())

# 3. share weer terug: melding weg, bibliotheek ongewijzigd
shutil.move(M + '.weg', M); rescan()
check('share terug: melding verdwenen', alerts() == [] and status()['alert'] is None, alerts())
check('share terug: alle modellen nog aanwezig', names() == ['a', 'b', 'c', 'd'], names())
check('share terug: "weer bereikbaar" in de geschiedenis', any(m.endswith('is weer bereikbaar') for m in hist()), hist()[:3])

# 4. een submap is tijdelijk niet te lezen (share hapert halverwege): de modellen daarin blijven staan
real = A.os.walk
def flaky(top, *a, onerror=None, **k):
    for d, dirs, files in real(top, *a, onerror=onerror, **k):
        if 'sub' in dirs:
            dirs.remove('sub'); onerror(OSError(5, 'Input/output error', os.path.join(d, 'sub')))
        yield d, dirs, files
A.os.walk = flaky; A.NEXT['soon'] = 0  # de planner draait niet in de test: oude herhaalscan van stap 1/2 wissen
try:
    os.remove(f'{M}/other/d.stl')  # echt verwijderd bestand in een leesbare map
    rescan(); a = alerts()
finally:
    A.os.walk = real
check('onleesbare submap: b en c blijven staan, d (echt weg) wordt wel verwijderd', names() == ['a', 'b', 'c'], names())
check('onleesbare submap: melding "partial" met het aantal mappen', len(a) == 1 and a[0]['kind'] == 'partial' and a[0]['dirs'] == 1, a)
check('onleesbare submap: geen snelle herhaalscan (een volledige scan elke minuut is te zwaar)', A.NEXT['soon'] == 0, A.NEXT['soon'])
rescan()
check('submap weer leesbaar: melding weg, b en c nog aanwezig', alerts() == [] and names() == ['a', 'b', 'c'], (alerts(), names()))

# 5. root folder verwijderd terwijl er een melding was: melding verdwijnt mee
A.ROOT_ALERT[9999] = dict(kind='offline', path='/weg', known=1, dirs=0, since=time.time())
check('melding van een verwijderde root folder wordt opgeruimd', all(x['id'] != 9999 for x in alerts()))
print('\nALLES GOED' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
