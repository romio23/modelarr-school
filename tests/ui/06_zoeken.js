// Zoeken en filteren gebeurt op de server (zie tests/test_library_paging.py). Hier: de bibliotheek vraagt de juiste pagina aan en negeert verouderde antwoorden.
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const mk=n=>({id:n,name:'m'+n,ext:'stl',cats:[],status:'ok',thumb_at:1,added:n,size:1,path:'/m'+n,dims:[1,1,1],info:null,can_rename:true,favorite:false,printed:'',notes:'',dup:'',source_url:'',display:'',folder:''});
const all=[1,2,3,4,5].map(mk); let reqs=[], slow=null;
ME={auth:false,user:null,role:'admin',can_download:true};
apiImpl=async u=>{ if(u.startsWith('/api/library')){ reqs.push(u); const r=SRV(all,u); if(slow&&u.includes('q=oud')){ await slow; r.models=[mk(99)]; r.total=1; } return r; } return u==='/api/printers'?[]:{}; };
Object.assign(L,{q:'',cat:'all',ext:'all',flt:'all',sort:'name',size:100,page:0,sel:new Set()});
await V.library();
t('de eerste aanvraag bevat pagina, aantal per pagina, zoekterm, filters en sortering', reqs.length===1&&/^\/api\/library\?page=0&size=100&q=&cat=all&ext=all&flt=all&sort=name$/.test(reqs[0]));
$('#q').oninput({target:{value:'Rack ext:3mf'}}); await new Promise(r=>setTimeout(r,20));
t('zoeken stuurt de zoekterm (kleine letters) naar de server', reqs.at(-1).includes('q=rack+ext%3A3mf'));
L.page=3; $('#fc').onchange({target:{value:'2'}}); await new Promise(r=>setTimeout(r,20));
t('ander filter: terug naar pagina 1 en filter meegestuurd', reqs.at(-1).includes('page=0')&&reqs.at(-1).includes('cat=2'));
$('#fs').onchange({target:{value:'added'}}); await new Promise(r=>setTimeout(r,20));
t('sortering wordt meegestuurd', reqs.at(-1).includes('sort=added'));
// een traag antwoord op een oude zoekopdracht mag een nieuwere niet overschrijven
let open; slow=new Promise(r=>open=r); L.q='oud'; const first=$('#fs').onchange({target:{value:'name'}});
L.q=''; const second=await $('#fs').onchange({target:{value:'name'}}); open(); await first; await new Promise(r=>setTimeout(r,20));
t('verouderd antwoord op een eerdere zoekopdracht wordt genegeerd', L.d.models.length===5&&L.d.models[0].id!==99);
