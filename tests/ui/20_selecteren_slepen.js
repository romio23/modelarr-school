// Makkelijker selecteren: klik op het kaartje bij een actieve selectie, dubbelklik opent, sleep-kader, Ctrl+A en Escape.
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const M=n=>({id:n,name:'m'+n,ext:'stl',cats:[],status:'ok',thumb_at:1,added:n,size:100,path:'/m/m'+n+'.stl',dims:[1,1,1],info:null,can_rename:true,favorite:false,printed:'',notes:'',dup:'',source_url:'',display:'',folder:'',pdims:null,prints_ok:0,prints_failed:0,last_print:null,error:null,container:'',member:''});
ME={auth:false,user:null,role:'admin',can_download:true};
apiImpl=async u=>u.startsWith('/api/library')?SRV(Array.from({length:12},(_,i)=>M(i+1)),u,{categories:[]}):u==='/api/printers'?[]:{};
L.sel.clear(); L.q=''; L.cat='all'; L.ext='all'; L.flt='all'; L.sort='name'; L.size=100; L.page=0; L.lastSel=undefined;
await V.library();
const view=$('#view'); view.getBoundingClientRect=()=>({left:0,top:0,right:1000,bottom:800}); view.scrollLeft=0; view.scrollTop=0;
const ck=(id,o={})=>({target:{id:'',classList:{contains:()=>false},dataset:{},closest:s=>s==='[data-id]'?{dataset:{id:String(id)}}:s==='#items'?{}:null,...(o.target||{})},ctrlKey:!!o.ctrl,shiftKey:!!o.shift,metaKey:false});
openId=null; await view.onclick(ck(3));
t('geen selectie: een klik op het kaartje opent het model (zoals altijd)', openId===3); openId=null; $('#modal').innerHTML='';
await view.onclick(ck(2,{ctrl:true}));
t('Ctrl+klik start een selectie zonder het model te openen', L.sel.has(2)&&L.sel.size===1&&openId===null);
await view.onclick(ck(5));
t('met een actieve selectie voegt een gewone klik op het kaartje toe (niet openen)', L.sel.has(5)&&L.sel.size===2&&openId===null);
await view.onclick(ck(5)); t('en een tweede klik haalt het weer weg', !L.sel.has(5)&&L.sel.size===1);
L.sel=new Set([4]); L.lastSel=4; await view.onclick(ck(8,{shift:true})); t('Shift+klik bereik 4 t/m 8', [4,5,6,7,8].every(i=>L.sel.has(i))&&L.sel.size===5);
let o=null; view.ondblclick({target:{closest:s=>s==='[data-id]'?{dataset:{id:'7'}}:null}}); t('dubbelklik opent het model, ook met een selectie', openId===7); openId=null; $('#modal').innerHTML='';
await view.onclick({target:{id:'',classList:{contains:()=>false},dataset:{},closest:s=>s==='#items'?{}:null}});
t('klik naast de modellen wist de selectie', L.sel.size===0);
// sleep-kader: 4 kaartjes in een raster van 2x2 (100x100 met 10 tussenruimte)
const mkCard=(id,l,tp)=>{ const c={dataset:{id:String(id)},cls:new Set(),cb:{checked:false},getBoundingClientRect:()=>({left:l,top:tp,right:l+100,bottom:tp+100}),classList:{toggle:(n,on)=>on?c.cls.add(n):c.cls.delete(n)},querySelector:()=>c.cb}; return c; };
const cards=[mkCard(1,0,0),mkCard(2,110,0),mkCard(3,0,110),mkCard(4,110,110)];
document.querySelectorAll=s=>s==='#items [data-id]'?cards:[];
const down=(x,y,o={})=>{ let pd=false; view.onmousedown({button:0,clientX:x,clientY:y,shiftKey:!!o.shift,ctrlKey:!!o.ctrl,metaKey:false,preventDefault(){pd=true},target:{closest:s=>s==='#items'?{}:null}}); return pd; };
t('muisknop op een kaartje start een mogelijke sleepactie (en voorkomt tekstselectie)', down(50,50)===true&&drag&&!drag.on);
dragMove({clientX:52,clientY:52}); t('een klein verschuiven (minder dan 6 px) is nog gewoon een klik', !drag.on&&L.sel.size===0);
dragMove({clientX:150,clientY:60});
t('slepen over twee kaartjes naast elkaar selecteert die twee, het kader is zichtbaar', drag.on&&[...L.sel].sort().join()==='1,2'&&$('#band').style.display==='block'&&$('#band').style.width==='100px');
t('vinkjes en markering volgen het kader direct', cards[0].cb.checked&&cards[1].cb.checked&&!cards[2].cb.checked&&cards[0].cls.has('s'));
dragMove({clientX:150,clientY:160}); t('kader groter maken: alle vier', L.sel.size===4);
dragMove({clientX:50,clientY:60}); t('kader weer kleiner maken: kaartje 2 valt af', [...L.sel].sort().join()==='1'&&!cards[1].cb.checked);
dragEnd(); t('loslaten: kader weg en de klik die erop volgt wordt genegeerd', $('#band').style.display==='none'&&drag===null);
openId=null; await view.onclick(ck(1)); t('geen model geopend door de klik na het slepen', openId===null&&L.sel.has(1));
// toevoegen met Shift of Ctrl, vervangen zonder
L.sel=new Set([4]); dragAt=0; down(0,0,{ctrl:true}); dragMove({clientX:60,clientY:60}); dragEnd(); t('slepen met Ctrl voegt toe aan de selectie', [...L.sel].sort().join()==='1,4');
dragAt=0; down(0,0); dragMove({clientX:60,clientY:60}); dragEnd(); t('slepen zonder toets vervangt de selectie', [...L.sel].join()==='1');
// scrollen tijdens het slepen houdt het beginpunt aan de inhoud vast
L.sel.clear(); dragAt=0; down(5,5); dragMove({clientX:100,clientY:790}); view.scrollTop=0; drag.my=790;
dragScroll(); t('bij de onderrand scrolt de lijst automatisch door', view.scrollTop===18);
dragEnd();
// gast en knoppen
ME={auth:true,user:'gast',role:'viewer',can_download:true}; drag=null; down(5,5); t('gast: geen sleepactie', drag===null); ME={auth:false,user:null,role:'admin',can_download:true};
drag=null; let pd2=false; view.onmousedown({button:0,clientX:5,clientY:5,preventDefault(){pd2=true},target:{closest:s=>s.startsWith('button')?{}:s==='#items'?{}:null}});
t('mousedown op een knop of invoerveld start geen sleepactie', drag===null&&pd2===false);
drag=null; view.onmousedown({button:2,clientX:5,clientY:5,preventDefault(){},target:{closest:()=>null}}); t('rechtermuisknop start geen sleepactie', drag===null);
// toetsen
const key=(k,o={})=>{ let p=false; libKey({key:k,ctrlKey:!!o.ctrl,metaKey:false,target:o.target||{tagName:'BODY'},preventDefault(){p=true}}); return p; };
L.sel.clear(); L.d.ids=[1,2,3,4,5,6,7,8,9,10,11,12];
t('Ctrl+A selecteert alles wat in het filter past (alle pagina\'s)', key('a',{ctrl:true})===true&&L.sel.size===12);
t('Escape wist de selectie', (key('Escape'),L.sel.size===0));
L.sel=new Set([1]); key('a',{ctrl:true,target:{tagName:'INPUT'}}); t('Ctrl+A in het zoekveld blijft gewone tekstselectie', L.sel.size===1);
openId=5; key('Escape'); t('met een openstaand model doet Escape niets met de selectie', L.sel.size===1); openId=null;
ME={auth:true,user:'gast',role:'viewer',can_download:true}; key('Escape'); t('gast: toetsen doen niets', L.sel.size===1); ME={auth:false,user:null,role:'admin',can_download:true};
