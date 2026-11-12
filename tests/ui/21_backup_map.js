const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const base={scan_interval:5,min_age:5,extensions:'stl,3mf',thumb_size:384,thumb_source:'embedded',thumb_delay:0,recent_days:7,big_mb:50,zip_support:true,backup_keep:7,backup_thumbs:false,backup_dir:'',backup_dir_now:'/config/backups',backup_last:null,backup_error:null};
let settings={...base};
apiImpl=async(u,m,b)=>u==='/api/roots'?[]:u==='/api/settings'?settings:{};
await V['settings/media']();
let h=out['#view'].innerHTML, click=d=>out['#view'].onclick({target:{id:d.id||'',dataset:d.dataset||{}}});
t('Back-upmap: invoerveld met de standaardmap als voorbeeld, plus knoppen Kiezen en Nu back-uppen', h.includes('id="s12"')&&h.includes('placeholder="/config/backups"')&&h.includes('id="bkpick"')&&h.includes('id="bknow"'));
t('uitleg: altijd deze map, buiten het config-volume, punt-map binnen een root', h.includes('altijd in deze map')&&h.includes('buiten je config-volume')&&h.includes('met een punt beginnen'));
t('nog geen back-up: dat staat er', h.includes('Nog geen back-up gemaakt'));
settings={...base,backup_dir:'/mnt/nas/bk',backup_dir_now:'/mnt/nas/bk',backup_last:1760000000};
await V['settings/media'](); h=out['#view'].innerHTML;
t('ingestelde map staat in het veld en de laatste back-up wordt getoond', h.includes('value="/mnt/nas/bk"')&&h.includes('Laatste back-up:'));
settings={...settings,backup_error:"Back-upmap is niet beschrijfbaar: File exists"};
await V['settings/media'](); h=out['#view'].innerHTML;
t('mislukte back-up: rode melding met de reden', h.includes('class="err">Laatste back-up mislukt: Back-upmap is niet beschrijfbaar'));
const q=s=>document.querySelector(s); q('#s11').checked=true; q('#s12').value='  /mnt/nas/nieuw  '; apiCalls.length=0;
await click({id:'savemm'});
const sv=apiCalls.find(c=>c[0]==='/api/settings'&&c[1]==='POST');
t('opslaan stuurt de back-upmap mee, zonder spaties', sv&&sv[2].backup_dir==='/mnt/nas/nieuw');
q('#s12').value=''; apiCalls.length=0; await click({id:'savemm'});
t('leeg veld stuurt een lege map: terug naar de standaard', apiCalls.find(c=>c[0]==='/api/settings')[2].backup_dir==='');
apiCalls.length=0; await click({id:'bknow'});
t('"Nu back-uppen" start de back-uptaak', apiCalls.some(c=>c[0]==='/api/tasks/backup/run'&&c[1]==='POST'));
q('#s12').value=' /mnt/3d-modellen/.backup '; apiCalls.length=0; await click({id:'bknow'});
const i1=apiCalls.findIndex(c=>c[0]==='/api/settings'&&c[1]==='POST'), i2=apiCalls.findIndex(c=>c[0]==='/api/tasks/backup/run');
t('"Nu back-uppen" slaat eerst de ingevulde map op (anders gaat de back-up naar de oude map)', i1>=0&&i2>i1&&apiCalls[i1][2].backup_dir==='/mnt/3d-modellen/.backup');
// taakpagina
apiImpl=async u=>u==='/api/tasks'?[{key:'backup',name:'Database back-up',interval:'24 uur',running:false,last:1760000000,next:1760086400,dur:.1,desc:'x',dir:'/mnt/nas/bk',error:'Back-upmap is niet beschrijfbaar: Permission denied'},{key:'scan',name:'Bibliotheek scannen',interval:'5 min',running:false,last:null,next:null,dur:null,desc:'y'}]:{};
await V['system/tasks'](); h=out['#view'].innerHTML;
t('taken: de back-uptaak toont de map en de laatste fout; andere taken niet', h.includes('<code>/mnt/nas/bk</code>')&&h.includes('Laatste poging mislukt: Back-upmap is niet beschrijfbaar: Permission denied')&&h.split('Map: ').length===2);

// mapkiezer voor de back-upmap toont ook mappen met een punt (bijv. .back-ups); die voor root folders niet
apiImpl=async(u2)=>u2==='/api/roots'?[]:u2==='/api/settings'?settings:{}; await V['settings/media'](); apiCalls.length=0; click({id:'bkpick'}); await new Promise(r=>setTimeout(r,30));
t('Kiezen bij de back-upmap vraagt de mappen op met hidden=1 (zodat .back-ups te kiezen is)', apiCalls.some(c=>String(c[0]).startsWith('/api/fs?hidden=1')));
apiCalls.length=0; await V['settings/media'](); click({id:'addroot'}); await new Promise(r=>setTimeout(r,30));
t('Map kiezen bij root folders blijft verborgen mappen overslaan', apiCalls.some(c=>String(c[0]).startsWith('/api/fs'))&&!apiCalls.some(c=>String(c[0]).includes('hidden=1')));
