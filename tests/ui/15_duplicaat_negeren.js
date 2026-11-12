// Duplicaten: een groep negeren en weer terugzetten via de knoppen op de pagina.
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const mk=(id,name)=>({id,name,ext:'stl',path:'/m/'+name+'.stl',size:684,added:1,status:'ok',thumb_at:1,can_write:true});
let state={exact:[[mk(1,'a'),mk(2,'b')]],mesh:[],ignored:[],wasted:684,waiting:0};
apiImpl=async(u,m,b)=>{ if(u==='/api/duplicates') return JSON.parse(JSON.stringify(state)); if(u==='/api/duplicates/ignore'){ api.last=b; if(b.ignore){state={...state,exact:[],ignored:[state.exact[0]||state.ignored[0]]}} else {state={...state,exact:[state.ignored[0]],ignored:[]}} return {ok:true}; } return {}; };
let html=''; const v=$('#view'); Object.defineProperty(v,'innerHTML',{configurable:true,set(x){html=x},get(){return html}});
await V.duplicates();
t('de groep heeft een Negeren-knop met de model-id\'s', /data-ign="1,2" data-on="1">Negeren</.test(html));
await v.onclick({target:{dataset:{ign:'1,2',on:'1'}}});
t('klik op Negeren stuurt de id\'s en ignore=true naar de server', JSON.stringify(api.last)===JSON.stringify({ids:[1,2],ignore:true}));
t('daarna staat de groep onder "Genegeerd" met een knop om terug te zetten', html.includes('Genegeerd · 1 groep(en)')&&/data-on="0">Niet meer negeren</.test(html)&&html.includes('Geen dubbele bestanden gevonden'));
await v.onclick({target:{dataset:{ign:'1,2',on:'0'}}});
t('"Niet meer negeren" zet de groep weer in de lijst', JSON.stringify(api.last)===JSON.stringify({ids:[1,2],ignore:false})&&/data-ign="1,2" data-on="1"/.test(html)&&!html.includes('Genegeerd ·'));
