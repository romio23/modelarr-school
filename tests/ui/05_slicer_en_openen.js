const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const m={id:1,name:'a',ext:'3mf',folder:'',size:1,added:1,status:'ok',cats:[],info:null,dims:null,path:'/p',container:'',member:'',can_rename:true,printed:'',notes:'',source_url:'',favorite:false};
L.printers=[]; L.logs={};
L.d={categories:[],models:[m],spoolman:false,local:false,slicer:{name:'Bambu Studio',scheme:'bambustudio://open?file='}};
let h=sideHTML(m); t('knop "Openen in Bambu Studio" altijd aanwezig', h.includes('id="vslic"')&&h.includes('Openen in Bambu Studio'));
t('"Openen met standaardprogramma" niet als de app niet lokaal draait', !h.includes('id="vopen"'));
L.d.local=true; h=sideHTML(m); t('... wel als de gebruiker op dezelfde computer zit', h.includes('id="vopen"'));
L.d.slicer={name:'<OrcaSlicer>',scheme:'x'}; t('slicernaam wordt ge-escaped', sideHTML(m).includes('Openen in &lt;OrcaSlicer&gt;'));

