const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
const P={id:1,name:'P1S',bed_x:256,bed_y:256,bed_z:256}, S={id:2,name:'A1 mini',bed_x:180,bed_y:180,bed_z:180}, W={id:3,name:'Breed',bed_x:350,bed_y:150,bed_z:200};
const mk=(id,dims)=>({id,name:'m'+id,ext:'stl',folder:'',size:1,added:1,status:'ok',cats:[],info:null,dims});
t('past precies op het bed (randgeval)', fits(mk(1,[256,256,256]),P)===true);
t('te hoog', fits(mk(1,[100,100,257]),P)===false);
t('te breed in beide richtingen', fits(mk(1,[257,100,10]),P)===false);
t('90° gedraaid passend (300x100 op 100x350)', fits(mk(1,[300,100,10]),{...W,bed_x:100,bed_y:350})===true && fits(mk(1,[300,100,10]),W)===true);
t('past niet gedraaid én niet rechtop', fits(mk(1,[300,160,10]),W)===false);
t('onbekende afmetingen = null', fits(mk(1,null),P)===null);
t('afrondingsruis (256.004) toegestaan', fits(mk(1,[256.004,10,10]),P)===true);
L.printers=[P,S]; L.d={categories:[],big_mb:50,recent_days:7,models:[mk(1,[200,200,100]),mk(2,[100,100,50]),mk(3,[300,10,10]),mk(4,null)]};
const h=fitHTML(L.d.models[0]); t('detail: ✓ P1S en ✗ A1 mini', h.includes('✓ P1S')&&h.includes('✗ A1 mini'));
t('detail: zonder afmetingen niets', fitHTML(L.d.models[3])==='');
L.printers=[]; t('detail: zonder printers een link naar instellingen', fitHTML(L.d.models[0]).includes('#/settings/printers'));

