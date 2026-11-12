const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const base={id:1,name:'multi',ext:'3mf',folder:'',size:2e6,added:1,status:'ok',thumb_at:5,cats:[],dims:[646,20,30],tris:12,path:'/m/multi.3mf',container:'',member:'',
  info:{plates:[{id:1,name:''},{id:2,name:'Deksels'},{id:3,name:''}]},favorite:false,printed:'',notes:'',source_url:'',can_rename:true,dup:''};
const tabsHtml=plateTabs(base,0);
t('plaat-tabbladen: Alles + 3 platen, naam of nummer', ['Alles','Plaat 1','Deksels','Plaat 3'].every(x=>tabsHtml.includes('>'+x+'<')) && (tabsHtml.match(/<button/g)||[]).length===4);
t('actief tabblad gemarkeerd', /data-plate="2" class="p"/.test(plateTabs(base,2)) && /data-plate="0" class=""/.test(plateTabs(base,2)));
t('geen tabbladen bij één plaat of geen info', plateTabs({...base,info:{plates:[{id:1,name:''}]}},0)==='' && plateTabs({...base,info:null},0)==='');
t('info toont aantal platen met namen', sideHTML(base).includes('Platen')&&sideHTML(base).includes('3 (1, Deksels, 3)'));
const z={...base,id:2,name:'cyl',ext:'stl',container:'pack.zip',member:'sub/cyl.stl',path:'/m/pack.zip!/sub/cyl.stl',can_rename:false,info:null};
const h=sideHTML(z); t('zip-model: toont "In zip", bestandsnaam uitgeschakeld met uitleg', h.includes('In zip: <b>pack.zip</b>')&&/id="vf"[^>]*disabled title="Dit model zit in een zip/.test(h));
L.d={categories:[],slicer:{name:'Bambu Studio'},local:false,big_mb:50,recent_days:7,models:[base,z]}; L.printers=[]; L.view='posters'; L.sel=new Set(); $('#bulk'); $('#items'); $('#cnt'); draw();
t('kaartje met ZIP-label alleen voor het zip-model', (out['#items'].innerHTML.match(/>ZIP</g)||[]).length===1);

