const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
ME={auth:true,user:'romio',role:'admin',can_download:true};
const S={ms_redirect:'https://m.school.nl/api/ms/callback',public_url:'',ms_tenant:'',ms_client_id:'',ms_secret_set:true,ms_admin_group:'',ms_enabled:false,ms_only:false,ms_klas:true};
apiImpl=async u=>u==='/api/settings'?S:{};
await V['settings/microsoft'](); const h=els['#view'].innerHTML;
t('Microsoft-pagina toont omleidings-URL en bewaarde geheimen zonder waarde', h.includes('https://m.school.nl/api/ms/callback')&&h.includes('opgeslagen')&&!h.includes('${'));
t('schoolpagina heeft kolommen voor leerlingen- en medewerkersgroep', await (async()=>{apiImpl=async u=>u==='/api/schools'?{schools:[{id:1,name:'W',slug:'w',group_id:'g1',staff_group_id:'g2',active:1,models:0,students:0,staff:0}],default_quota_mb:0}:{roots:[]};await V['settings/schools']();const x=els['#view'].innerHTML;return x.includes('Groep-ID leerlingen')&&x.includes('Groep-ID medewerkers')&&x.includes('data-f="staff_group_id" value="g2"')})());
