const base={id:1,name:'plate',display:'',ext:'3mf',folder:'',size:2e6,added:1,status:'ok',thumb_at:5,cats:[1],dims:[40,20,10],tris:12,path:'/m/plate.3mf',
  info:{title:'Pi Rack',designer:'Jan',printer:'X1C',print_time:5547,filament_g:15.6,layer_height:'0.2'},dup:'exact',favorite:true,printed:'printed',notes:'ABS <b>',source_url:'https://x.nl/m?a=1&b=2',can_rename:false};
L.d={categories:[{id:1,name:'Rack'}],slicer:{name:'Bambu Studio'},local:false,big_mb:50,recent_days:7,models:[base,{...base,id:2,name:'b',notes:'',favorite:false,printed:'toprint',dup:'',source_url:'javascript:alert(1)',can_rename:true,status:'unsupported',info:null}]};
$('#bulk'); $('#items'); $('#cnt');
L.sel=new Set([1]); L.view='posters'; draw();
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
t('kaartje: favoriet-, geprint-, te-printen- en dubbel-label', out['#items'].innerHTML.includes('favb')&&out['#items'].innerHTML.includes('prb')&&out['#items'].innerHTML.includes('🖨')&&out['#items'].innerHTML.includes('dupb'));
t('groepsbalk met 4 nieuwe knoppen', ['bf1','bf0','bpt','bpp'].every(i=>out['#bulk'].innerHTML.includes('id="'+i+'"')));
t('teller', out['#cnt'].textContent==='2 van 2');
L.view='table'; draw(); t('tabelweergave met ster', out['#items'].innerHTML.includes('★ plate')&&out['#items'].innerHTML.includes('Jan'));
const h1=sideHTML(L.d.models[0]), h2=sideHTML(L.d.models[1]);
t('detail: bestandsnaam uitgeschakeld als hernoemen uit staat', /id="vf"[^>]*disabled/.test(h1) && !/id="vf"[^>]*disabled/.test(h2));
t('detail: notities veilig ge-escaped', h1.includes('ABS &lt;b&gt;') && !h1.includes('ABS <b>'));
t('detail: bronlink alleen voor http(s), met noopener', h1.includes('href="https://x.nl/m?a=1&amp;b=2"') && h1.includes('noopener') && !h2.includes('href="javascript'));
t('detail: printstatus en favoriet voorgeselecteerd', h1.includes('value="printed" selected')&&h2.includes('value="toprint" selected')&&h1.includes('★ Favoriet')&&h2.includes('☆ Favoriet'));
t('detail: 3MF-info incl. printtijd', h1.includes('1u 32m')&&h1.includes('Pi Rack')&&h1.includes('vtitle'));
t('detail: knop weergave als thumbnail', h1.includes('id="vsnap"'));
