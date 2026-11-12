// Regressie: de inlogpagina werd elke paar seconden opnieuw getekend (poll -> 401 -> showLogin), waardoor invoer verdween.
const t=(n,ok)=>console.log(ok?'OK  ':'FOUT',n);
loginUp=false; let draws=0, v=$('#view'); let html='';
Object.defineProperty(v,'innerHTML',{configurable:true,set(x){draws++;html=x},get(){return html}});
const unauth=async u=>{ if (u==='/api/me') return {auth:true,user:null,role:null,can_download:false}; const e=new Error('Inloggen vereist'); e.status=401; e.login=true; throw e; };
apiImpl=unauth; route=()=>{}; await boot();
t('opstarten zonder inlog: inlogpagina getekend', draws===1&&html.includes('id="lu"'));
apiCalls.length=0; await poll(); await poll(); await poll();
t('niet ingelogd: de pagina vraagt de status niet op en tekent niets opnieuw', draws===1&&!apiCalls.some(c=>c[0]==='/api/rev'));
$('#lu').value='kees'; await api('/api/library').catch(()=>{}); await api('/api/library').catch(()=>{});
t('ook een 401 op een ander verzoek tekent de inlogpagina niet opnieuw (invoer blijft)', draws===1&&$('#lu').value==='kees');
// sessie verloopt tijdens het gebruik: één keer de inlogpagina, daarna niet steeds opnieuw
loginUp=false; draws=0; ME={auth:true,user:'beheer',role:'admin',can_download:true}; apiImpl=unauth;
await poll(); await poll(); await poll();
t('sessie verlopen: één keer de inlogpagina, daarna stopt het pollen', draws===1&&ME.user===null);
// na inloggen werkt alles weer
apiImpl=async u=>u==='/api/login'?{}:{}; await $('#lb').onclick(); await new Promise(r=>setTimeout(r,5));
t('inloggen herlaadt de pagina', location.reloaded===true);
