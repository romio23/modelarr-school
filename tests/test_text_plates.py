"""Test: leesbare 3MF-beschrijvingen (dubbel gecodeerde HTML) en afmetingen per plaat. Gebruik: python tests/test_text_plates.py"""
import io, json, os, shutil, sqlite3, sys, tempfile, zipfile
import numpy as np, trimesh
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, APP)
ROOT = os.path.join(tempfile.gettempdir(), 'modelbib-text'); shutil.rmtree(ROOT, ignore_errors=True); os.makedirs(ROOT)
os.environ['CONFIG_DIR'] = f'{ROOT}/cfg'
import render, app as A
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
# tekst zoals in de screenshot: de 3MF bevat &amp;lt;, de XML-parser geeft &lt;
raw = ('&lt;h3&gt;&lt;a target=&#34;_blank&#34; rel=&#34;noopener noreferrer ugc&#34; href=&#34;https://makerworld.com/es/collections/29161919-10-rack&#34;&gt;'
       'Follow the collection for new rack modules and updates&lt;/a&gt;&lt;/h3&gt;&lt;p&gt;Create your own &lt;strong&gt;parametric side panels for 10 inch racks&lt;/strong&gt; with the KWS RACK Panel Generator.&lt;/p&gt;')
t = render.clean_text(raw, 800)
check('screenshot-tekst: leesbaar, link bewaard als "tekst (url)", geen tags of entiteiten', '<' not in t and '&lt;' not in t and '&#34;' not in t
      and 'Follow the collection for new rack modules and updates (https://makerworld.com/es/collections/29161919-10-rack)' in t
      and 'Create your own parametric side panels for 10 inch racks with the KWS RACK Panel Generator.' in t, repr(t))
check('alinea\'s blijven gescheiden', '\n' in t)
check('<script> wordt platte tekst zonder tags', '<' not in render.clean_text('x<script>alert(1)</script>y') and 'alert(1)' in render.clean_text('x<script>alert(1)</script>y'))
check('gewone tekst met & blijft ongewijzigd', render.clean_text('Tom & Jerry') == 'Tom & Jerry')
check('dubbel gecodeerd ampersand wordt één &', render.clean_text('A &amp;amp; B') == 'A & B')
check('lengtelimiet', len(render.clean_text('x' * 5000, 200)) == 200 and render.clean_text(None) == '')
NS = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
def objxml(i, box):
    v = ''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in box.vertices); tr = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in box.faces)
    return f'<object id="{i}"><mesh><vertices>{v}</vertices><triangles>{tr}</triangles></mesh></object>'
def multi3mf(path, plates=True):
    A_, B_, C_ = trimesh.creation.box((40, 20, 10)), trimesh.creation.box((10, 10, 10)), trimesh.creation.box((20, 10, 30)); tr = lambda x: f'1 0 0 0 1 0 0 0 1 {x} 0 0'
    model = (f'<?xml version="1.0"?><model unit="millimeter" {NS}><metadata name="Title">Rack &amp;amp; Co</metadata><metadata name="Description">{raw.replace("&", "&amp;")}</metadata>'
             f'<resources>{objxml(1, A_)}{objxml(2, B_)}{objxml(3, C_)}</resources><build><item objectid="1" transform="{tr(0)}"/><item objectid="2" transform="{tr(303)}"/><item objectid="3" transform="{tr(333)}"/><item objectid="1" transform="{tr(606)}"/></build></model>')
    inst = lambda o, i: f'<model_instance><metadata key="object_id" value="{o}"/><metadata key="instance_id" value="{i}"/></model_instance>'
    cfg = ('<config>' + f'<plate><metadata key="plater_id" value="1"/>{inst(1, 0)}</plate><plate><metadata key="plater_id" value="2"/>{inst(2, 0)}{inst(3, 0)}</plate><plate><metadata key="plater_id" value="3"/>{inst(1, 1)}</plate></config>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('3D/3dmodel.model', model)
        if plates: z.writestr('Metadata/model_settings.config', cfg)
mp = f'{ROOT}/multi.3mf'; multi3mf(mp)
info = render.info_3mf(mp)
check('3MF-info: dubbel gecodeerde titel en beschrijving worden schone tekst', info['title'] == 'Rack & Co' and '<' not in info['description'] and 'Follow the collection' in info['description'] and 'https://makerworld.com' in info['description'], (info['title'], info['description'][:60]))
pd = render.plate_dims(mp)
check('afmetingen per plaat: A / B+C samen / tweede A', [p['id'] for p in pd] == [1, 2, 3] and np.allclose(pd[0]['dims'], [40, 20, 10]) and np.allclose(pd[1]['dims'], [45, 10, 30]) and np.allclose(pd[2]['dims'], [40, 20, 10]), pd)
whole = render.load_mesh(mp, '3mf')[0]; check('...terwijl het hele model 646 mm breed is (daarom was de oude controle fout)', abs(np.ptp(whole, 0)[0] - 646) < 1)
multi3mf(f'{ROOT}/single.3mf', plates=False); check('3MF zonder platen: geen afmetingen per plaat', render.plate_dims(f'{ROOT}/single.3mf') == [])
# migratie: oude, onleesbare info wordt opnieuw gelezen
A.init()
with A.db() as c:
    c.execute("INSERT INTO roots(path) VALUES('/x')")
    c.execute("INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,info) VALUES(1,'/x/a.3mf','a','3mf',1,1,1,?)", (json.dumps({'description': '&lt;h3&gt;oud'}),))
    c.execute("INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,info) VALUES(1,'/x/b.3mf','b','3mf',1,1,1,?)", (json.dumps({'description': 'Tom & Jerry <3'}),))
A.init()
with A.db() as c: r = {x['name']: x['info'] for x in c.execute('SELECT name, info FROM models')}
check('migratie: info met entiteiten wordt opnieuw gelezen, schone info blijft', r['a'] is None and r['b'] is not None, r)
sys.exit(1 if bad else 0)
