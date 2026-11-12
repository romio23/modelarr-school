"""Kleuren in 3MF: gebruikte filamenten uit slice_info, anders de toegewezen filamenten; zoeken (kleuren:3), filter Meerkleurig, eenmalige herlezing.
Gebruik: python tests/test_colors.py"""
import json, os, shutil, sys, tempfile, time, zipfile
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-colors'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A, render
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
MODEL = '<?xml version="1.0"?><model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><metadata name="Title">T</metadata><resources/><build/></model>'
def mk(name, files):
    p = f'{ROOT}/m/{name}.3mf'
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('3D/3dmodel.model', MODEL)
        for k, v in files.items(): z.writestr(k, v)
    return p
sl = lambda *fs: '<config><plate>' + ''.join(f'<filament id="{i}" type="PLA" color="{c}" used_m="{m}" used_g="{g}"/>' for i, c, m, g in fs) + '</plate></config>'
ms = lambda *ex: '<config>' + ''.join(f'<object id="{i}"><metadata key="extruder" value="{e}"/></object>' for i, e in enumerate(ex, 1)) + '</config>'
ps = json.dumps({'filament_colour': ['#FF0000', '#00ff00', '#0000FF', '#FFFFFF'], 'filament_type': ['PLA'] * 4})
p1 = mk('gesliced', {'Metadata/slice_info.config': sl((1, '#FF0000', 1, 3.2), (2, '#00FF00', 0, 0), (3, '#0000FF', 2, 5.0)), 'Metadata/project_settings.config': ps})
i1 = render.info_3mf(p1)
check('gesliced: alleen filamenten met verbruik tellen (2 van de 3)', i1.get('colors') == ['#FF0000', '#0000FF'] and i1.get('color_count') == 2, i1)
p2 = mk('ongesliced', {'Metadata/project_settings.config': ps, 'Metadata/model_settings.config': ms(1, 3, 3)})
i2 = render.info_3mf(p2)
check('niet gesliced: filamenten waaraan objecten zijn toegewezen (1 en 3)', i2.get('colors') == ['#FF0000', '#0000FF'] and i2.get('color_count') == 2, i2)
p3 = mk('standaard', {'Metadata/project_settings.config': ps})
i3 = render.info_3mf(p3)
check('geen toewijzing: alleen filament 1', i3.get('colors') == ['#FF0000'] and i3['color_count'] == 1, i3)
p4 = mk('kaal', {})
check('kale 3MF zonder kleurinfo: geen kleuren, geen fout', 'colors' not in render.info_3mf(p4))
p5 = mk('kapot', {'Metadata/slice_info.config': '<config><oops', 'Metadata/project_settings.config': ps})
check('kapotte slice_info valt netjes terug op de projectinstellingen', render.info_3mf(p5).get('color_count') == 1)
p6 = mk('onzin', {'Metadata/slice_info.config': sl((1, 'rood', 1, 1)), 'Metadata/project_settings.config': json.dumps({'filament_colour': ['xx']})})
check('ongeldige kleurcodes worden genegeerd', 'colors' not in render.info_3mf(p6))
# zoeken en filter
M = lambda n, info: dict(id=n, name='abcd'[n-1]*3, display='', ext='3mf', folder='', cats=[], notes='', source_url='', info=info, status='ok', added=0, favorite=False, printed='', prints_failed=0, size=1, dup='', dims=None, pdims=None)
ms_ = [M(1, i1), M(2, i3), M(3, {}), M(4, {'color_count': 3, 'colors': ['#000000'] * 3})]
f = lambda q='', flt='all': [m['id'] for m in A.lib_filter(ms_, [], q, 'all', 'all', flt, 'name', 7, 50, {})]
check('filter Meerkleurig: alleen 2+ kleuren', f(flt='multicolor') == [1, 4], f(flt='multicolor'))
check('zoeken kleuren:3 en kleuren:2', f('kleuren:3') == [4] and f('kleuren:2') == [1], (f('kleuren:3'), f('kleuren:2')))
check('gewone zoekopdracht matcht niet op het aantal kleuren', f('9') == [])
# eenmalige herlezing
A.init()
with A.db() as d:
    d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
A.put('min_age', '0')
for _ in range(50):
    if A.scan() is not False: break
    time.sleep(.2)
with A.db() as d:
    d.execute("UPDATE models SET info='{}'"); d.execute("DELETE FROM settings WHERE key='info_colors_done'")
A.init()
with A.db() as d:
    n = d.execute("SELECT COUNT(*) FROM models WHERE info IS NULL AND ext='3mf'").fetchone()[0]; tot = d.execute("SELECT COUNT(*) FROM models WHERE ext='3mf'").fetchone()[0]
    d.execute("UPDATE models SET info='{}'")
A.init()
with A.db() as d: n2 = d.execute("SELECT COUNT(*) FROM models WHERE info IS NULL").fetchone()[0]
check('eerste start na de update: alle 3MF-info wordt opnieuw gelezen, daarna niet nog eens', tot > 0 and n == tot and n2 == 0, (n, tot, n2))
print('\nAlles goed.' if not bad else '\nFOUT: %s' % bad); sys.exit(1 if bad else 0)
