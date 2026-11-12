"""Test: de bestandswachter houdt het opstarten niet op (hij start op de achtergrond) en wordt op een netwerkshare overgeslagen.
Gebruik: python tests/test_watcher_startup.py"""
import os, shutil, sys, tempfile, threading, time
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-watcher')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/models')
os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
import watchdog.observers as WO
A.init(); c = A.app.test_client(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/models',))
rid = c.get('/api/roots').get_json()[0]['id']

# 1. een trage wachter (zoals een netwerkmap met tienduizenden bestanden) houdt sync_watchers niet op
class Slow:
    started = threading.Event(); stopped = False; daemon = False
    def schedule(self, *a, **k): pass
    def start(self): time.sleep(1.5); Slow.started.set()
    def stop(self): Slow.stopped = True
real = WO.Observer; WO.Observer = Slow
try:
    t0 = time.time(); A.sync_watchers(); dt = time.time() - t0
    check('sync_watchers wacht niet op het opzetten van de wachter (<0,5 s bij een wachter die 1,5 s nodig heeft)', dt < .5, f'{dt:.2f}s')
    check('de wachter staat meteen als actief bij de map', c.get('/api/roots').get_json()[0]['live'] is True)
    check('de wachter start daarna op de achtergrond', Slow.started.wait(4))
    # uitzetten terwijl de wachter nog start: geen fout
    A.OBS.clear(); Slow.started.clear(); A.sync_watchers()
    with A.db() as d: d.execute('UPDATE roots SET watch=0')
    try: A.sync_watchers(); ok = True
    except Exception as e: ok = False; print(e)
    check('uitzetten terwijl hij nog start geeft geen fout en haalt hem uit de lijst', ok and rid not in A.OBS)
    time.sleep(1.8)
    with A.db() as d: d.execute('UPDATE roots SET watch=1')
    # 2. netwerkshare: geen wachter, wel een melding en de plaats in de lijst is 'alleen scannen'
    A.OBS.clear(); Slow.started.clear()
    real_fs = A.fs_type
    for t in ('cifs', 'nfs4', 'smb3'):
        A.fs_type = lambda p, m=None, t=t: t; A.sync_watchers()
        check(f'netwerkshare ({t}): geen wachter, dus geen trage start', rid not in A.OBS and not Slow.started.is_set())
    check('root toont "niet live" (alleen scannen)', c.get('/api/roots').get_json()[0]['live'] is False)
    A.fs_type = lambda p, m=None: 'ext4'; A.sync_watchers()
    check('lokale schijf (ext4): wel een wachter', rid in A.OBS)
    A.fs_type = real_fs
finally:
    WO.Observer = real
# 3. met de echte wachter op een lokale map: een nieuw bestand wordt opgemerkt
A.OBS.clear(); A.dirty.clear(); A.sync_watchers()
time.sleep(1.0); open(f'{ROOT}/models/nieuw.stl', 'w').write('x')
t0 = time.time()
while time.time() - t0 < 6 and rid not in A.dirty: time.sleep(.2)
check('echte wachter op een lokale map meldt nog steeds een nieuw bestand', rid in A.dirty, A.dirty)
for o, _ in list(A.OBS.values()):
    try: o.stop()
    except Exception: pass
print('\nALLES GOED' if not bad else f'\nFOUT: {bad}'); sys.exit(1 if bad else 0)
