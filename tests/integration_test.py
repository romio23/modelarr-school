"""Integratietest: start de app tegen testmodellen en controleert scannen, verplaatsen, beveiliging, back-up, crash-herstel. Gebruik: python tests/integration_test.py"""
import subprocess, os, sys, time, json, shutil, sqlite3, threading, urllib.request, urllib.error, http.client, base64, trimesh
from PIL import Image
import tempfile
ROOT=os.path.join(tempfile.gettempdir(),'modelbib-test'); APP=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); PORT=8798
shutil.rmtree(ROOT,ignore_errors=True)
for d in ('models/sub','models/sub2','cfg'): os.makedirs(f'{ROOT}/{d}')
M=f'{ROOT}/models'; OLD=time.time()-600
trimesh.creation.box((40,20,10)).export(f'{M}/box.stl'); trimesh.creation.cylinder(8,30).export(f'{M}/sub/cyl.stl')
open(f'{M}/sub2/secret.txt','w').write('GEHEIM')
for p in (f'{M}/box.stl',f'{M}/sub/cyl.stl'): os.utime(p,(OLD,OLD))
def start():
    env=dict(os.environ,CONFIG_DIR=f'{ROOT}/cfg',MODELS_DIR=M,PORT=str(PORT),ALLOW_ORGANIZE='1', YIELD_TO_USERS='0')
    p=subprocess.Popen([sys.executable,'app.py'],cwd=APP,env=env,stdout=open(f'{ROOT}/log.txt','a'),stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen(f'http://127.0.0.1:{PORT}/ping'); return p
        except Exception: time.sleep(.2)
    raise SystemExit('start mislukt')
def req(u,m='GET',b=None,h=None):
    r=urllib.request.Request(f'http://127.0.0.1:{PORT}'+u,method=m,data=json.dumps(b).encode() if b is not None else None,headers={'Content-Type':'application/json',**(h or {})})
    try:
        with urllib.request.urlopen(r) as x: return x.status,x.read(),x.headers
    except urllib.error.HTTPError as e: return e.code,e.read(),e.headers
J=lambda u,*a,**k: json.loads(req(u,*a,**k)[1])
names=lambda: {m['name']:m for m in J('/api/library')['models']}
def wait(cond,t=30):
    t0=time.time()
    while time.time()-t0<t:
        if cond(): return round(time.time()-t0,1)
        time.sleep(.5)
    return None
srv=start(); ok=lambda x: 'OK ' if x else 'FOUT'
try:
    req('/api/settings','POST',{'min_age':3})
    t=wait(lambda: len(names())==2 and all(m['status']=='ok' for m in names().values()),40)
    print(ok(t),'eerste import (twee oude bestanden, grootte-stabiliteit):',t,'s')
    rid=names()['cyl']['id']
    # --- pad-traversal
    c=http.client.HTTPConnection('127.0.0.1',PORT); res=[]
    for path in (f'/api/file/{rid}/../../sub2/secret.txt',f'/api/file/{rid}/..%2F..%2Fsub2%2Fsecret.txt',f'/api/file/{rid}/secret.txt'):
        c.request('GET',path); r=c.getresponse(); b=r.read(); res.append((r.status,b'GEHEIM' in b))
    s,b,h=req(f'/api/file/{rid}')
    print(ok(all(st==404 and not leak for st,leak in res) and s==200 and len(b)>100),'traversal geblokkeerd',res,'| download model:',s,h.get('Content-Disposition'))
    # --- API-sleutel
    key=J('/api/settings')['api_key']; print(ok(req('/api/users','POST',{'username':'beheer','password':'geheim-123'})[0]==200),'eerste account aangemaakt: inloggen verplicht')
    bas={'Authorization':'Basic '+base64.b64encode(b'beheer:geheim-123').decode()}
    c=http.client.HTTPConnection('127.0.0.1',PORT); c.putrequest('GET','/api/library'); c.putheader('X-Api-Key','é'.encode('latin-1')); c.endheaders(); weird=c.getresponse().status
    print(ok(req(f'/api/library?apikey={key}')[0]==401 and req('/api/library',h={'X-Api-Key':key})[0]==200 and weird==401),'apikey: URL=',req(f'/api/library?apikey={key}')[0],'header=',req('/api/library',h={'X-Api-Key':key})[0],'niet-ASCII header=',weird,'| rev.auth=',J('/api/rev',h=bas)['auth'])
    req('/api/users/clear','POST',{'confirm':True},h=bas); print(ok(J('/api/rev')['auth'] is False),'auth weer uit, banner-vlag:',J('/api/rev')['auth'])
    # --- kopie met oude mtime die nog groeit (SMB/NFS)
    full=open(f'{M}/box.stl','rb').read(); g=f'{M}/sub/growing.stl'
    open(g,'wb').write(full[:90]); os.utime(g,(OLD,OLD)); req('/api/tasks/scan/run','POST'); time.sleep(1)
    a='growing' in names()
    open(g,'ab').write(full[90:140]); os.utime(g,(OLD,OLD)); req('/api/tasks/scan/run','POST'); time.sleep(1)
    b='growing' in names()
    t=wait(lambda: 'growing' in names(),15)
    print(ok(not a and not b and t is not None),f'groeiend bestand met oude mtime: na scan1={a}, na scan2 (grootte veranderd)={b}, uiteindelijk opgenomen na {t}s')
    # --- verplaatst
    cid=J('/api/categories','POST',{'name':'T'})['id']; bid=names()['box']['id']; req('/api/assign','POST',{'model_ids':[bid],'category_id':cid,'action':'add'})
    shutil.move(f'{M}/box.stl',f'{M}/sub/doos.stl'); req('/api/tasks/scan/run','POST'); time.sleep(4)
    d=names().get('doos'); print(ok(d and d['id']==bid and d['cats']==[cid]),'verplaatst: id en categorie behouden')
    # --- gelijktijdig schrijven tijdens scans en thumbnails
    errs=[]
    def hammer(n):
        for i in range(40):
            s=req('/api/categories','POST',{'name':f'c{n}_{i}'})[0]; errs.append(s)
            mid=list(names().values())[0]['id']; errs.append(req('/api/assign','POST',{'model_ids':[mid],'category_id':cid,'action':'add' if i%2 else 'remove'})[0])
            if i%10==0: req('/api/tasks/scan/run','POST'); req('/api/tasks/rebuild/run','POST')
    ths=[threading.Thread(target=hammer,args=(n,)) for n in range(4)]; [t.start() for t in ths]; [t.join() for t in ths]
    print(ok(set(errs)=={200}),f'gelijktijdig schrijven: {len(errs)} requests, statuscodes {sorted(set(errs))}; "locked" in log: {"locked" in open(ROOT+"/log.txt").read()}')
    # --- back-up
    req('/api/tasks/backup/run','POST'); time.sleep(1.5); bk=os.listdir(f'{ROOT}/cfg/backups')
    n=sqlite3.connect(f'{ROOT}/cfg/backups/{bk[0]}').execute('select count(*) from models').fetchone()[0]
    print(ok(bk and n==len(names())),'back-up:',bk,'bevat',n,'modellen | tasks:',[t['key'] for t in J('/api/tasks')])
    # --- thumbnailgrootte wijzigen => automatisch opnieuw
    req('/api/settings','POST',{'thumb_size':200})
    t=wait(lambda: all(m['status']=='ok' for n,m in names().items() if n!='growing'),30); mid=names()['cyl']['id']
    print(ok(t and Image.open(f'{ROOT}/cfg/thumbs/{mid}.png').size==(200,200)),'thumb_size 200: alles automatisch opnieuw, formaat',Image.open(f'{ROOT}/cfg/thumbs/{mid}.png').size)
finally:
    srv.terminate(); srv.wait()
# --- crash-loop bescherming
con=sqlite3.connect(f'{ROOT}/cfg/library.db'); mid=names_id=con.execute("select id from models where name='cyl'").fetchone()[0]
con.execute("update models set thumb_status='processing' where id=?",(mid,)); con.commit(); con.close()
srv=start()
try:
    m=[x for x in J('/api/library')['models'] if x['id']==mid][0]
    print(ok(m['status']=='failed' and 'onderbroken' in (m['error'] or '')),'na crash tijdens renderen:',m['status'],'-',m['error'])
    req('/api/wanted/retry','POST',{'ids':[mid]}); t=wait(lambda: [x for x in J('/api/library')['models'] if x['id']==mid][0]['status']=='ok',15)
    print(ok(t is not None),'opnieuw proberen via Gewenst werkt')
finally:
    srv.terminate(); srv.wait()
print('--- fouten in log:',[l for l in open(ROOT+'/log.txt') if 'ERROR' in l or 'Traceback' in l][:3])
