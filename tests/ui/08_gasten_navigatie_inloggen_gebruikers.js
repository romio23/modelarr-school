var routed = 0, polled = 0; route = () => { routed++; }; poll = () => { polled++; };
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const H=(x)=>JSON.stringify(x);
const m={id:1,name:'doos',display:'',ext:'stl',folder:'rack',size:5,added:1,status:'ok',thumb_at:1,cats:[1],dims:[40,20,10],tris:12,path:'rack/doos.stl',container:'',member:'',info:{title:'Titel',description:'tekst'},source_url:'https://printables.com/model/1',favorite:false,printed:'',notes:'',can_rename:false,dup:''};
L.d={categories:[{id:1,name:'Rack <b>'}],models:[m,{...m,id:2,name:'z',container:'pack.zip',member:'z.stl',path:'pack.zip/z.stl'}],big_mb:50,recent_days:7,slicer:{name:'Bambu Studio'},local:false}; L.printers=[];
// ---- gast
ME={auth:true,user:'gast',role:'student',can_download:true};
let h=sideHTMLViewer(m);
t('gast: alleen lezen (geen invoervelden, opslaan-, favoriet- of logboekknoppen)', !/<input|<textarea|id="vs"|id="vfav"|id="vlogbtn"|id="lsave"|id="vsnap"|id="vre"|id="vadd"/.test(h));
t('gast: naam, afmetingen, relatief pad, categorie (ge-escaped zonder verwijderknop), bronlink', h.includes('doos')&&h.includes('40 × 20 × 10 mm')&&h.includes('rack/doos.stl')&&h.includes('Rack &lt;b&gt;')&&!h.includes('data-rm')&&/href="https:\/\/printables.com\/model\/1"[^>]*>/.test(h)||/<a class="btn"[^>]*href="https:\/\/printables.com\/model\/1"/.test(h));
t('gast mét download-recht: Download-knop en slicer-knop', h.includes('class="btn" href="/api/file/1" download')&&h.includes('id="vslic"')&&h.includes('Sluiten'));
ME.can_download=false; h=sideHTMLViewer(m); t('gast zónder download-recht: geen Download/slicer, wel uitleg', !h.includes('/api/file/')&&!h.includes('id="vslic"')&&h.includes('niet ingeschakeld'));
t('gast: geen "Titel overnemen"-knop in de 3MF-info', !infoHTML(m).includes('vtitle') && (ME.role='admin', infoHTML(m).includes('vtitle')));
ME={auth:true,user:'gast',role:'student',can_download:true}; L.printers=[]; t('gast: geen "voeg je printers toe"-link', fitHTML(m)==='' );
L.view='posters'; L.sel=new Set(); $('#bulk'); $('#items'); $('#cnt'); L.cat='all'; L.q=''; L.flt='all'; L.ext='all'; draw();
const cards=els['#items'].innerHTML; t('gast: kaartjes zonder selectievakje; ZIP-label blijft', !cards.includes('class="sel"') && (cards.match(/>ZIP</g)||[]).length===1);
L.d.models[0]={...m,favorite:true,printed:'printed',dup:'exact'}; draw(); t('gast: geen favoriet-, geprint- of dubbel-label (privé voor de beheerder)', !/favb|prb|dupb/.test(els['#items'].innerHTML));
L.view='table'; draw(); t('gast: tabel zonder selectievakjes', !els['#items'].innerHTML.includes('class="sel"')&&!els['#items'].innerHTML.includes('id="all"'));
ME={auth:true,user:'beheer',role:'admin',can_download:true}; L.view='posters'; draw(); t('beheerder: wel selectievakjes en labels', els['#items'].innerHTML.includes('class="sel"')&&/favb/.test(els['#items'].innerHTML)&&/dupb/.test(els['#items'].innerHTML));
// ---- navigatie per rol
ME={auth:true,user:'gast',role:'student',can_download:true}; buildNav(); let nv=els['#nav'].innerHTML;
t('navigatie gast: alleen Bibliotheek, naam, "gast" en Uitloggen', nv.includes('Bibliotheek')&&!nv.includes('Instellingen')&&!nv.includes('Systeem')&&!nv.includes('Gewenst')&&nv.includes('leerling')&&nv.includes('Printaanvragen')&&nv.includes('id="logout"'));
ME={auth:true,user:'beheer',role:'admin',can_download:true}; buildNav(); nv=els['#nav'].innerHTML;
t('navigatie beheerder: alles incl. Gebruikers en Uitloggen', nv.includes('Instellingen')&&nv.includes('#/settings/users')&&nv.includes('Systeem')&&nv.includes('beheerder')&&nv.includes('id="logout"'));
ME={auth:false,user:null,role:'admin',can_download:true}; buildNav(); t('zonder accounts: geen gebruikersblok', !els['#nav'].innerHTML.includes('logout')&&els['#nav'].innerHTML.includes('Instellingen'));
// ---- inlogpagina en opstarten
await (async()=>{
  els['#nav'].innerHTML='x'; apiImpl=async()=>({auth:true,user:null,role:null,can_download:false}); await boot();
  t('opstarten zonder inlog (accounts bestaan): inlogpagina (naam of e-mailadres), geen app', els['#view'].innerHTML.includes('Gebruikersnaam of e-mailadres')&&els['#view'].innerHTML.includes('id="lu"')&&els['#view'].innerHTML.includes('id="lp"')&&els['#nav'].innerHTML===''&&routed===0&&els['#top'].style.display==='none');
  apiImpl=async()=>{throw new Error('Onjuiste gebruikersnaam of wachtwoord')}; $('#lu').value='x'; $('#lp').value='y'; await els['#lb'].onclick(); await new Promise(r=>setTimeout(r,5));
  t('foute inlog: melding op de pagina, geen herlaad', els['#le'].textContent==='Onjuiste gebruikersnaam of wachtwoord'&&!location.reloaded);
  apiImpl=async()=>({}); await els['#lb'].onclick(); await new Promise(r=>setTimeout(r,5)); t('goede inlog: pagina wordt herladen', location.reloaded===true&&apiCalls.at(-1)[0]==='/api/login'&&apiCalls.at(-1)[2].username==='x');
  showLogin('<b>x</b>'); t('inlogmelding wordt als gewone tekst getoond (geen HTML)', els['#le'].textContent==='<b>x</b>');
  routed=0; polled=0; apiImpl=async()=>({auth:true,user:'beheer',role:'admin',can_download:true}); await boot();
  t('opstarten met inlog: navigatie, route en poll starten', ME.user==='beheer'&&routed===1&&polled===1&&els['#nav'].innerHTML.includes('Instellingen'));
  routed=0; apiImpl=async()=>({auth:false,user:null,role:'admin',can_download:true}); await boot(); t('opstarten zonder accounts: gewoon de app', routed===1);
  // ---- gebruikersbeheer
  apiImpl=async u=>u==='/api/users'?[]:u==='/api/schools'?{schools:[]}:{}; await V['settings/users'](); let uh=els['#view'].innerHTML;
  t('beheer zonder accounts: waarschuwing en "eerste beheerder", geen rol-keuze', uh.includes('Er zijn nog geen accounts')&&uh.includes('Eerste beheerder aanmaken')&&!uh.includes('id="nr"')&&!uh.includes('nclear'));
  apiImpl=async u=>u==='/api/schools'?{schools:[{id:1,name:'School A'}]}:u==='/api/users'?[{id:1,username:'beheer<x>',email:'b@x.nl',role:'admin',can_download:true,active:true,last_login:5,me:true},{id:2,username:'gast',email:'',role:'student',can_download:false,active:true,last_login:null,me:false}]:{}; await V['settings/users'](); uh=els['#view'].innerHTML;
  t('beheer met accounts: e-mailkolom, "E-mail"-knop en adresveld bij toevoegen', uh.includes('E-mail')&&uh.includes('b@x.nl')&&uh.includes('data-em="2"')&&uh.includes('id="ne"')&&uh.includes('E-mailadres (optioneel)'));
  t('beheer met accounts: tabel, rol, download, actief, "(jij)", ge-escaped naam, alles-verwijderen', uh.includes('beheer&lt;x&gt;')&&uh.includes('(jij)')&&uh.includes('data-role="2"')&&/data-dl="2"\s*>/.test(uh)&&uh.includes('id="nclear"')&&uh.includes('Leerling')&&uh.includes('id="nr"')&&uh.includes('HTTPS'));
  apiCalls=[]; await els['#view'].onchange({target:{dataset:{dl:'2'},checked:true}}); t('download-recht aanzetten: PUT met can_download', apiCalls[0][0]==='/api/users/2'&&apiCalls[0][1]==='PUT'&&apiCalls[0][2].can_download===true);
  apiCalls=[]; await els['#view'].onchange({target:{dataset:{role:'2'},value:'admin'}}); t('rol wijzigen: PUT met role', apiCalls[0][2].role==='admin');
  $('#nu').value='kees'; $('#ne').value='kees@x.nl'; $('#np').value='wachtwoord1'; $('#nr').value='student'; $('#nd').checked=false; apiCalls=[]; await els['#view'].onclick({target:{id:'na',dataset:{}}});
  t('gast toevoegen: POST met rol en download-keuze', apiCalls[0][0]==='/api/users'&&apiCalls[0][2].role==='student'&&apiCalls[0][2].can_download===false&&apiCalls[0][2].username==='kees'&&apiCalls[0][2].email==='kees@x.nl');
})();

