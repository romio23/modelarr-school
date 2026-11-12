// Regressie: een trage lading (grote bibliotheek) die binnenkomt nadat je naar een andere pagina bent gegaan,
// schreef in elementen die er niet meer waren ("Cannot set properties of null (setting 'innerHTML')").
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
let release; const slow=new Promise(r=>release=r);
apiImpl=async u=>{ if(u==='/api/library'){await slow; return {models:[],categories:[]};} return {}; };
const toastBefore=$('#toast').textContent;
const p=run(async()=>{ await api('/api/library'); return 'verwerkt'; })();
routeGen++;  // gebruiker gaat naar een andere pagina
release();
t('antwoord na een paginawissel wordt genegeerd, geen foutmelding', (await p)===undefined&&$('#toast').textContent===toastBefore);
apiImpl=async()=>({rev:1});
t('een antwoord op de huidige pagina werkt gewoon', (await api('/api/library')).rev===1);
let rel2; const slow2=new Promise(r=>rel2=r); apiImpl=async u=>{await slow2; return {rev:5};};
const q=api('/api/rev'); routeGen++; rel2();
t('de statuspoll (/api/rev) wordt nooit als verouderd afgewezen', (await q).rev===5);
