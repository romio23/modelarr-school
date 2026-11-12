// Bibliotheek: alles selecteren + Shift-klik bereik. Duplicaten: kopieën kiezen en in één keer naar de prullenbak.
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const M=n=>({id:n,name:'m'+n,ext:'stl',cats:[],status:'ok',thumb_at:1,added:n,size:100,path:'/m/m'+n+'.stl',dims:[1,1,1],info:null,can_rename:true,favorite:false,printed:'',notes:'',dup:'',source_url:'',display:'',folder:'',pdims:null,prints_ok:0,prints_failed:0,last_print:null,error:null,container:'',member:'',tris:12,hash:''});
let html=''; const v=$('#view'); Object.defineProperty(v,'innerHTML',{configurable:true,set(x){html=x},get(){return html}});
ME={auth:false,user:null,role:'admin',can_download:true};
apiImpl=async u=>u.startsWith('/api/library')?SRV([1,2,3,4,5].map(M),u,{categories:[{id:1,name:'Rack',count:0}]}):u==='/api/printers'?[]:{};
L.sel.clear(); L.q=''; L.cat='all'; L.ext='all'; L.flt='all'; L.sort='name'; L.lastSel=undefined;
await V.library();
t('zonder selectie staat er een knop "Alles selecteren (5)"', /id="bsa"[^>]*>☑ Alles selecteren \(5\)</.test($('#bulk').innerHTML));
await $('#view').onclick({target:{id:'bsa',classList:{contains:()=>false},dataset:{},closest:()=>null}});
t('klik op Alles selecteren selecteert alle 5 modellen en toont de balk met categorie-keuze', L.sel.size===5&&$('#bulk').innerHTML.includes('id="ba"'));
L.sel.clear(); draw();
const click=(id,shift)=>$('#view').onclick({shiftKey:!!shift,target:{id:'',classList:{contains:c=>c==='sel'},dataset:{},closest:()=>({dataset:{id:String(id)}})}});
await click(1); await click(4,true);
t('Shift+klik selecteert alles tussen het eerste en laatste vinkje', [1,2,3,4].every(i=>L.sel.has(i))&&!L.sel.has(5));
// duplicaten
const D=(id,w=true)=>({id,name:'d'+id,ext:'stl',path:'/m/d'+id+'.stl',size:684,added:id,status:'ok',thumb_at:1,can_write:w});
let calls=[]; apiImpl=async(u,m,b)=>{ if(u==='/api/duplicates') return {exact:[[D(1),D(2),D(3)],[D(4),D(5,false)]],mesh:[],ignored:[],wasted:1,waiting:0}; if(u==='/api/models/trash'){calls.push(b);return {done:b.ids.length,failed:[]};} return {}; };
Object.defineProperty(v,'innerHTML',{configurable:true,set(x){html=x},get(){return html}});
await V.duplicates();
t('duplicaten: vinkjes alleen bij bestanden die verplaatst mogen worden', (html.match(/class="dsel"/g)||[]).length===4);
await $('#view').onclick({target:{dataset:{act:'allcopies'},classList:{contains:()=>false}}});
t('"Alle kopieën kiezen" kiest alles behalve het oudste per groep (en niet wat niet mag)', html.includes('3 naar prullenbak')===false&&html.includes('2 naar prullenbak')&&/data-id="2" checked/.test(html)&&/data-id="3" checked/.test(html)&&!/data-id="1" checked/.test(html));
await $('#view').onclick({target:{dataset:{act:'trashsel'},classList:{contains:()=>false}}});
t('"naar prullenbak" stuurt alle gekozen id\'s in één verzoek', calls.length===1&&JSON.stringify(calls[0].ids.sort())==='[2,3]');
// bibliotheek: geselecteerde modellen naar de prullenbak
apiImpl=async u=>u.startsWith('/api/library')?SRV([1,2,3,4,5].map(M),u,{categories:[]}):u==='/api/printers'?[]:{};
Object.defineProperty(v,'innerHTML',{configurable:true,set(x){html=x},get(){return html}});
L.sel.clear(); await V.library(); L.sel=new Set([2,3]); draw();
t('met selectie: knop "Naar prullenbak" naast de categorieknoppen met duidelijke namen', $('#bulk').innerHTML.includes('id="bt"')&&$('#bulk').innerHTML.includes('In categorie zetten')&&$('#bulk').innerHTML.includes('Uit categorie halen'));
let sent=[]; apiImpl=async(u,m,b)=>{ if(u==='/api/models/trash'){ sent.push(b); return {done:1,failed:[{id:3,error:'Model niet gevonden'}]}; } return u.startsWith('/api/library')?SRV([1,2,3,4,5].map(M),u):u==='/api/printers'?[]:{}; };
confirmMsgs.length=0; await $('#view').onclick({target:{id:'bt',classList:{contains:()=>false},dataset:{}}});
t('vraagt eerst bevestiging met het aantal en zegt dat niets definitief wordt verwijderd', confirmMsgs.length===1&&confirmMsgs[0].startsWith('2 bestanden')&&confirmMsgs[0].includes('niet definitief'));
t('stuurt de gekozen id\'s met any:true', sent.length===1&&JSON.stringify(sent[0].ids)==='[2,3]'&&sent[0].any===true);
t('wat niet lukte blijft geselecteerd', L.sel.size===1&&L.sel.has(3));
confirmAnswer=false; sent.length=0; await $('#view').onclick({target:{id:'bt',classList:{contains:()=>false},dataset:{}}});
t('bevestiging geweigerd: er gebeurt niets', sent.length===0&&L.sel.size===1);
