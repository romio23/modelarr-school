const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
ME={auth:true,user:'romio',role:'admin',can_download:true};
apiImpl=async u=>u==='/api/schools'?{schools:[{id:1,name:'Kamerlingh Onnes'},{id:2,name:'Werkman VMBO'}]}:u==='/api/users'?[{id:1,username:'romio',email:'',role:'admin',can_download:true,can_upload:false,active:true,me:true,school_id:null},{id:2,username:'mees',email:'',role:'staff',can_download:true,can_upload:true,active:true,me:false,school_id:2}]:{};
await V['settings/users'](); const h=els['#view'].innerHTML; const i=h.indexOf('id="nsc"'), seg=h.slice(i,i+300);
t('gebruiker toevoegen: schoolkeuze bevat de scholen', seg.includes('Werkman VMBO')&&seg.includes('Kamerlingh')&&!seg.includes('${'));
t('gebruikerslijst: school van een medewerker is geselecteerd', /data-sc="2">[^]*?<option value="2" selected>Werkman/.test(h));
