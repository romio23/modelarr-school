"""Test: de server filtert, sorteert en pagineert de bibliotheek (/api/library?page=..). Gebruik: python tests/test_library_paging.py"""
import json, os, shutil, sys, tempfile, time
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-libpaging')
shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(f'{ROOT}/m'); os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'; sys.path.insert(0, APP)
import app as A
A.init(); bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
now = time.time(); DAY = 86400
with A.db() as d:
    d.execute('INSERT INTO roots(path) VALUES(?)', (f'{ROOT}/m',)); rid = d.execute('SELECT id FROM roots').fetchone()[0]
    d.execute("INSERT INTO categories(name) VALUES('10 inch server'),('Gereedschap')")
    def add(name, ext, folder='', size=1e6, added=now - 30 * DAY, status='ok', cats=(), info=None, display=None, dims=(10, 10, 10), notes=None, fav=0):
        cur = d.execute('INSERT INTO models(root_id,path,name,display_name,ext,size,mtime,added_at,thumb_status,info,dx,dy,dz) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (rid, f'{ROOT}/m/{folder}/{name}.{ext}', name, display, ext, size, 1, added, status, json.dumps(info) if info else None, *(dims or (None,) * 3)))
        for c in cats: d.execute('INSERT INTO model_categories VALUES(?,?)', (cur.lastrowid, c))
        if notes or fav: d.execute('UPDATE models SET notes=?, favorite=? WHERE id=?', (notes, fav, cur.lastrowid))
        return cur.lastrowid
    add('pi_rack', '3mf', '10 inch rack/Lab Rax', display='Raspberry Pi Rack', cats=(1,), info=dict(designer='Jan', title='Pi Rack', printer='Bambu Lab X1C'), notes='ABS goed', fav=1)
    add('blok', 'stl', 'Gereedschap', size=80 * 2 ** 20, added=now - DAY, cats=(2,), dims=(300, 10, 10))
    add('kapot', 'stl', status='failed', added=now - 2 * DAY, dims=None)
    add('deksel', 'obj', status='unsupported')
c = A.app.test_client()
def q(**p):
    p.setdefault('page', 0); p.setdefault('size', 100)
    r = c.get('/api/library', query_string=p).get_json(); return r
ids = lambda **p: ','.join(sorted(m['name'] for m in q(**p)['models']))
check('zonder paginaparameters: de hele lijst, zoals voorheen', len(c.get('/api/library').get_json()['models']) == 4 and 'total' not in c.get('/api/library').get_json())
for n, p, want in [('bestandsnaam', dict(q='pi_rack'), 'pi_rack'), ('weergavenaam', dict(q='raspberry'), 'pi_rack'), ('categorie als vrije tekst', dict(q='gereedschap'), 'blok'),
                   ('extensie vrij', dict(q='3mf'), 'pi_rack'), ('map', dict(q='lab rax'), 'pi_rack'), ('meerdere woorden = AND', dict(q='rack bambu'), 'pi_rack'),
                   ('AND zonder match', dict(q='rack blok'), ''), ('ext:', dict(q='ext:stl'), 'blok,kapot'), ('cat:', dict(q='cat:server'), 'pi_rack'),
                   ('cat:"zin"', dict(q='cat:"10 inch"'), 'pi_rack'), ('map:', dict(q='map:gereedschap'), 'blok'), ('ontwerper:', dict(q='ontwerper:jan'), 'pi_rack'),
                   ('3MF-info', dict(q='bambu'), 'pi_rack'), ('naam: telt categorie niet mee', dict(q='naam:server'), ''), ('onbekende prefix = tekst', dict(q='foo:bar'), ''),
                   ('hoofdletters', dict(q='PI_RACK'), 'pi_rack'), ('notitie:', dict(q='notitie:abs'), 'pi_rack'), ('bron:', dict(q='bron:x.nl'), ''),
                   ('filter zonder preview', dict(flt='nopreview'), 'deksel,kapot'), ('filter recent', dict(flt='recent'), 'blok,kapot'), ('filter groot', dict(flt='big'), 'blok'),
                   ('filter favoriet', dict(flt='fav'), 'pi_rack'), ('filter + zoek + ext', dict(q='blok', flt='big', ext='stl'), 'blok'), ('categoriefilter: zonder', dict(cat='none'), 'deksel,kapot'),
                   ('categoriefilter: id', dict(cat='2'), 'blok'), ('formaat', dict(ext='obj'), 'deksel')]:
    check(n, ids(**p) == want, f'{ids(**p)!r} != {want!r}' if ids(**p) != want else '')
with A.db() as d:
    d.execute("INSERT INTO printers(name,bed_x,bed_y,bed_z) VALUES('P1S',256,256,256),('Mini',180,180,180)")
    pid = [r[0] for r in d.execute('SELECT id FROM printers ORDER BY id')]
check('past op printer: alleen modellen met bekende afmetingen die passen', ids(flt=f'fit:{pid[0]}') == 'deksel,pi_rack' and ids(flt=f'fit:{pid[1]}') == 'deksel,pi_rack', ids(flt=f'fit:{pid[0]}'))
check('past op een verwijderde printer: niets', ids(flt='fit:999') == '')
with A.db() as d: d.execute("UPDATE models SET dx=300,dy=10,dz=10 WHERE name='deksel'")
check('te lang voor het bed (300 > 256)', 'deksel' not in ids(flt=f'fit:{pid[0]}'))
r = q(sort='added'); check('sorteren op toegevoegd: nieuwste eerst', [m['name'] for m in r['models']][:2] == ['blok', 'kapot'])
r = q(sort='size'); check('sorteren op grootte: grootste eerst', r['models'][0]['name'] == 'blok')
r = q(); nm = [m['display'] or m['name'] for m in r['models']]; check('sorteren op naam (weergavenaam telt mee, hoofdletters en accenten tellen niet)', nm == sorted(nm, key=str.casefold), nm[:5])
check('antwoord bevat totaal, aantal, id\'s en formaten', r['total'] == 4 and r['all'] == 4 and len(r['ids']) == 4 and r['exts'] == ['3mf', 'obj', 'stl'] and r['pages'] == 1)
# veel modellen: pagina's
with A.db() as d:
    for i in range(1230): d.execute("INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,thumb_status) VALUES(?,?,?,'stl',1,1,?,'ok')", (rid, f'{ROOT}/m/x/n{i:04d}.stl', f'n{i:04d}', i))
r = q(size=100); check('1234 modellen: 13 pagina\'s, eerste pagina 100 modellen, alle id\'s voor selecteren', r['total'] == 1234 and r['pages'] == 13 and len(r['models']) == 100 and len(r['ids']) == 1234)
r = q(size=100, page=12); check('laatste pagina heeft 34 modellen', len(r['models']) == 34 and r['page'] == 12)
r = q(size=100, page=99); check('pagina buiten bereik wordt de laatste', r['page'] == 12 and len(r['models']) == 34)
r = q(size=0); check('"Alles" (size=0) geeft alle modellen', len(r['models']) == 1234 and r['pages'] == 1)
r = q(size=25, page=2, ext='stl'); check('pagina + filter samen', r['page'] == 2 and len(r['models']) == 25 and r['total'] == 1232 and r['all'] == 1234)
r = q(size='abc', page='x'); check('onzinwaarden vallen terug op standaard', r['page'] == 0 and r['size'] == 100)
oid = q(q='pi_rack')['models'][0]['id']
r = q(q='blok', **{'with': oid}); check('"with": openstaand model komt mee, ook buiten het filter', r['open'] and r['open']['id'] == oid and len(r['models']) == 1)
# de onthouden lijst volgt elke wijziging meteen
b = q(q='blok')['models'][0]['id']; H0 = {'X-Requested-With': 'modelbib'}
q(); c.post(f'/api/models/{b}', json={'favorite': True}, headers=H0)
check('favoriet zetten is direct zichtbaar in filter en lijst (geen verouderde cache)', ids(flt='fav') == 'blok,pi_rack' and q(q='blok')['models'][0]['favorite'] is True)
c.post(f'/api/models/{b}', json={'display': 'Zware blok'}, headers=H0)
check('hernoemen is direct zichtbaar', ids(q='zware') == 'blok')
with A.db() as d: d.execute('DELETE FROM models WHERE id=?', (b,))
check('verwijderd model verdwijnt direct uit de lijst en de teller', q()['all'] == 1233 and 'blok' not in ids(q='blok'))
sys.exit(1 if bad else 0)
