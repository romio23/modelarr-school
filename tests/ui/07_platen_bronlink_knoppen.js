const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const H2D={id:1,name:'H2D',bed_x:350,bed_y:320,bed_z:325}, MINI={id:2,name:'A1 mini',bed_x:180,bed_y:180,bed_z:180};
const mk=(o)=>({id:1,name:'multi',ext:'3mf',folder:'',size:1,added:1,status:'ok',cats:[],path:'/p',container:'',member:'',can_rename:true,printed:'',notes:'',source_url:'',favorite:false,dup:'',...o});
const info3=[{id:1,name:''},{id:2,name:''},{id:3,name:''}];
const kws=mk({dims:[1359.9,1427.8,3],info:{plates:info3},pdims:[{id:1,dims:[250,200,3]},{id:2,dims:[300,300,3]},{id:3,dims:[260,240,3]}]});
t('SCREENSHOT: hele indeling 1360x1428 mm, maar elke plaat past op de H2D', fits(kws,H2D)===true);
t('... en past niet op de A1 mini', fits(kws,MINI)===false);
t('een te grote plaat laat het model niet passen', fits(mk({dims:[10,10,3],info:{plates:info3},pdims:[{id:1,dims:[250,200,3]},{id:2,dims:[400,300,3]}]}),H2D)===false);
t('platen nog niet berekend: onbekend (null), niet ten onrechte "past niet"', fits(mk({dims:[1360,1428,3],info:{plates:info3},pdims:null}),H2D)===null);
t('één plaat of geen platen: gewone controle op het hele model', fits(mk({dims:[300,300,10],info:null}),H2D)===true && fits(mk({dims:[400,10,10],info:{plates:[{id:1}]}}),H2D)===false);
L.printers=[H2D,MINI]; L.d={categories:[],models:[kws],slicer:{name:'Bambu Studio'},local:false};
let h=fitHTML(kws); t('detail: ✓ H2D, ✗ A1 mini met de te grote plaat genoemd, "per plaat"', h.includes('✓ H2D')&&/✗ A1 mini \(plaat \d te groot\)/.test(h)&&h.includes('per plaat'));
t('detail: "platen worden nog berekend" zolang pdims ontbreekt', fitHTML(mk({dims:[1,1,1],info:{plates:info3},pdims:null})).includes('nog berekend')&&fitHTML(mk({dims:[1,1,1],info:{plates:info3},pdims:null})).includes('? H2D'));
t('afmetingen: aantal platen en grootste plaat i.p.v. de hele indeling', dimTxt(kws)==='3 platen, grootste 300 × 300 × 3 mm' && dimTxt(mk({dims:[83.84,42,7],info:null}))==='83.8 × 42 × 7 mm');
const inf={title:'T',description:'Zie https://makerworld.com/a?x=1&y=2 (en https://b.nl/c) <script>x</script>'};
const side1=sideHTML(mk({dims:[1,1,1],info:inf,source_url:''}));
t('beschrijving: links klikbaar, rest ge-escaped (geen script), haakjes niet in de link', /<a href="https:\/\/makerworld.com\/a\?x=1&amp;y=2"[^>]*>/.test(side1)&&side1.includes('href="https://b.nl/c"')&&side1.includes('&lt;script&gt;')&&!side1.includes('<script>'));
t('bronlink: verborgen zonder url', /id="vsrcl"[^>]*hidden/.test(side1) && !/id="vsrcl"[^>]*href=/.test(side1));
const side2=sideHTML(mk({dims:[1,1,1],info:null,source_url:'https://www.printables.com/model/1?a=1&b=2'}));
t('bronlink: klikbaar, nieuw tabblad, noopener, met url', /id="vsrcl" class="btn" target="_blank" rel="noopener noreferrer" href="https:\/\/www.printables.com\/model\/1\?a=1&amp;b=2"/.test(side2) && !/id="vsrcl"[^>]*hidden/.test(side2));
t('Download is een echte knop (class btn), geen kale link', side2.includes('<a class="btn" href="/api/file/1" download>⬇ Download</a>'));

t('bronlink-knop: klein, alleen het "open extern"-icoon (svg) met toegankelijke naam, geen pijltekst', /id="vsrcl"[^>]*title="Bron openen" aria-label="Bron openen"><svg[^>]*aria-hidden="true"><path d="M15 3h6v6"\/>/.test(side2) && !side2.includes('Openen ↗'));

