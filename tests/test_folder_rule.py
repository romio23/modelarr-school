"""Een map die is ingedeeld ("Categorieën uit mappen") onthoudt dat: nieuwe bestanden in die map krijgen dezelfde categorie.
Ook voor mappen die al eerder waren ingedeeld (eenmalige migratie). Gebruik: python tests/test_folder_rule.py"""
import os, shutil, sys, tempfile, time
import trimesh
ROOT = os.path.join(tempfile.gettempdir(), 'modelarr-folderrule'); shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(f'{ROOT}/m/Rek/sub'); os.makedirs(f'{ROOT}/m/Kabels'); os.makedirs(f'{ROOT}/m/Rekenmachine'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A
A.init(); A.put('min_age', '0'); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
def mk(rel):
    p = f'{ROOT}/m/{rel}'; trimesh.creation.box((5, 5, 5)).export(p); os.utime(p, (time.time() - 600,) * 2)
for r in ('Rek/een.stl', 'Rek/sub/twee.stl', 'Kabels/kabel.stl', 'Rekenmachine/calc.stl', 'los.stl'): mk(r)
with A.db() as d: d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',))
def scan():
    for _ in range(50):
        if A.scan() is not False: break
        time.sleep(.2)
def cats_of(name):
    with A.db() as d: return sorted(r[0] for r in d.execute('SELECT c.name FROM model_categories mc JOIN categories c ON c.id=mc.category_id JOIN models m ON m.id=mc.model_id WHERE m.name=?', (name,)))
scan()
c = A.app.test_client(); H = {'X-Requested-With': 'modelbib'}
r = c.post('/api/folders/categorize', json={'items': [{'folder': 'Rek', 'category': '10 inch rek'}, {'folder': 'Kabels', 'category': 'Kabels'}]}, headers=H)
check('map indelen werkt zoals vroeger voor bestaande modellen (ook submappen)', r.status_code == 200 and cats_of('een') == ['10 inch rek'] and cats_of('twee') == ['10 inch rek'] and cats_of('calc') == [])
rules = c.get('/api/rules').get_json()
check('er is een regel "map is" per ingedeelde map', sorted((x['field'], x['value'], x['category']) for x in rules) == [('folder', 'Kabels', 'Kabels'), ('folder', 'Rek', '10 inch rek')], rules)
check('  de regel past op de modellen in die map en laat niets te doen over', {x['value']: (x['matches'], x['todo']) for x in rules} == {'Rek': (2, 0), 'Kabels': (1, 0)})
mk('Rek/nieuw.stl'); mk('Rek/sub/diep.stl'); mk('Kabels/nieuw2.stl'); mk('Rekenmachine/calc2.stl'); mk('los2.stl'); scan()
check('nieuw bestand in een ingedeelde map krijgt dezelfde categorie (ook in een submap)', cats_of('nieuw') == ['10 inch rek'] and cats_of('diep') == ['10 inch rek'] and cats_of('nieuw2') == ['Kabels'])
check('een map met een gelijkende naam (Rekenmachine) en losse bestanden krijgen niets', cats_of('calc2') == [] and cats_of('los2') == [])
r = c.post('/api/folders/categorize', json={'items': [{'folder': 'Rek', 'category': '10 inch rek'}]}, headers=H)
check('nogmaals indelen maakt geen dubbele regel', len([x for x in c.get('/api/rules').get_json() if x['value'] == 'Rek']) == 1)
c.delete(f"/api/rules/{[x for x in c.get('/api/rules').get_json() if x['value'] == 'Kabels'][0]['id']}", headers=H); mk('Kabels/nieuw3.stl'); scan()
check('regel verwijderen: nieuwe bestanden krijgen de categorie niet meer', cats_of('nieuw3') == [])

# eerder ingedeeld, nog zonder regel (oude versie): eenmalige migratie
with A.db() as d:
    d.execute('DELETE FROM rules'); d.execute("DELETE FROM settings WHERE key='folder_rules_migrated'")
    d.execute("INSERT INTO categories(name) VALUES('Rekenmachine')")
    d.execute("INSERT INTO categories(name) VALUES('Los')")
A.CFG['folder_rules_migrated'] = '0'
n = A.migrate_folder_rules()
rules = c.get('/api/rules').get_json()
check('migratie: map met een categorie van dezelfde naam waar de meeste modellen al in zitten krijgt een regel (met de echte schrijfwijze)', n == 1 and [(x['value'], x['category']) for x in rules] == [('Kabels', 'Kabels')], rules)
check('  map met een andere categorienaam (Rek / "10 inch rek") en lege categorieën krijgen geen regel; indelen via de pagina maakt die wel', 'Rek' not in [x['value'] for x in rules] and 'Rekenmachine' not in [x['value'] for x in rules])
check('  tweede keer doet niets', A.migrate_folder_rules() == 0)
print('ALLES GOED' if not bad else 'FOUT: ' + ', '.join(bad)); sys.exit(1 if bad else 0)
