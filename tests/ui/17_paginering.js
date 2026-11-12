// Bibliotheek met veel modellen: pagina's, aantal per pagina, terug naar pagina 1 bij een ander filter, selectie over alle pagina's.
const t=(n,ok,extra='')=>console.log(ok?'OK  ':'FOUT',n,extra);
const en=s=>I18N.translate(s,'en');
const mk=n=>({id:n,name:'model'+String(n).padStart(4,'0'),ext:n%2?'stl':'3mf',cats:[],status:'ok',thumb_at:1,added:n,size:100,path:'/m/'+n+'.stl',dims:[1,1,1],info:null,can_rename:true,favorite:false,printed:'',notes:'',dup:'',source_url:'',display:'',folder:'',pdims:null,prints_ok:0,prints_failed:0,last_print:null,error:null,container:'',member:'',tris:12,hash:''});
ME={auth:false,user:null,role:'admin',can_download:true};
let html={}; for (const id of ['#pg1','#pg2','#items','#bulk']) { const e=$(id); Object.defineProperty(e,'innerHTML',{configurable:true,set(x){html[id]=x},get(){return html[id]||''}}); }
const lib={models:Array.from({length:1234},(_,i)=>mk(i+1)),categories:[],big_mb:50,recent_days:7,local:true};
apiImpl=async u=>u.startsWith('/api/library')?JSON.parse(JSON.stringify(SRV(lib.models,u))):u==='/api/printers'?[]:{};
L.q='';L.cat='all';L.ext='all';L.flt='all';L.sort='name';L.sel.clear();L.view='posters';L.size=100;L.page=0;L.sig='';
await V.library();  // zet ook de klik- en wijzigingsafhandeling van de bibliotheek weer neer
const cards=()=>(html['#items'].match(/class="card/g)||[]).length;
t('standaard 100 modellen op pagina 1', cards()===100&&html['#pg1'].includes('1–100 van 1.234')||html['#pg1'].includes('1–100 van 1,234'), html['#pg1'].slice(0,80));
t('13 pagina\'s bij 1234 modellen (100 per pagina)', /van 13</.test(html['#pg1'])||/ van 13/.test(html['#pg1']));
await $('#view').onchange({target:{classList:{contains:c=>c==='pgi'},value:'13'}});
t('laatste pagina toont de laatste 34 modellen', cards()===34&&L.page===12);
t('de pager staat ook onder de lijst', html['#pg2']===html['#pg1']&&html['#pg2'].length>0);
await $('#view').onchange({target:{classList:{contains:c=>c==='pgs'},value:'25'}});
t('25 per pagina: terug naar pagina 1 met 25 kaartjes', cards()===25&&L.page===0&&L.size===25);
await $('#view').onclick({target:{dataset:{pg:'3'},disabled:false,id:'',classList:{contains:()=>false}}});
t('klik op een paginaknop gaat naar die pagina', L.page===3&&/76–100 van|76–100 of/.test(html['#pg1'].replace(/ /g,' ')));
L.ext='3mf'; await goPage(5); L.page=0; await goPage(0);
t('ander filter: terug naar pagina 1 en het aantal klopt (617 modellen)', L.page===0&&/van 617|of 617/.test(html['#pg1']));
L.ext='all'; L.size=0; await goPage(0);
t('"Alles" toont alle modellen zonder paginaknoppen', cards()===1234&&!html['#pg1'].includes('data-pg'));
L.size=25; await goPage(0);
await $('#view').onclick({target:{id:'bsa',classList:{contains:()=>false},dataset:{}}});
t('Alles selecteren kiest alle 1234 modellen, ook die niet op deze pagina staan', L.sel.size===1234);
t('Engels: pager volledig vertaald', ['Pagina','Per pagina','Alles','Eerste pagina','Volgende pagina'].every(s=>en(s)!==s)&&en('1–25 van 1.234')==='1–25 of 1.234'&&en('van 13')==='of 13');
L.sel.clear(); L.size=100;
