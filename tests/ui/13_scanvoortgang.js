// De scanbalk toont voortgang tijdens een lange scan en verdwijnt daarna.
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
ME={auth:false,user:null,role:null,can_download:true}; lastRev=null; onRev=null;
const bar=$('#scanbar');
apiImpl=async u=>u==='/api/rev'?{rev:1,pending:0,failed:0,dups:0,auth:false,scan:{phase:'zoeken',dirs:210,files:12340,added:0,total:0}}:{};
await poll();
t('tijdens het zoeken: aantal bestanden en mappen zichtbaar', bar.className==='on'&&/12.340|12,340/.test(bar.innerHTML)&&/210/.test(bar.innerHTML)&&bar.innerHTML.includes('bestanden gevonden'));
apiImpl=async u=>u==='/api/rev'?{rev:2,pending:0,failed:0,dups:0,auth:false,scan:{phase:'bijwerken',dirs:300,files:35479,added:5000,total:35479}}:{};
await poll();
t('tijdens het toevoegen: x van y met een voortgangsbalk', /5.000|5,000/.test(bar.innerHTML)&&bar.innerHTML.includes('35')&&/width:14%/.test(bar.innerHTML));
apiImpl=async u=>u==='/api/rev'?{rev:3,pending:0,failed:0,dups:0,auth:false,scan:null}:{};
await poll();
t('scan klaar: de balk verdwijnt', bar.className===''&&bar.textContent==='');
