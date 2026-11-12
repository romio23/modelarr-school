const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
let routeGen = 0;  // telt de paginawisselingen: een antwoord dat na het wisselen binnenkomt, mag de nieuwe pagina niet meer overschrijven
async function api(u, m = 'GET', b) {
  const gen = routeGen;
  const r = await fetch(u, {method: m, headers: {'Content-Type': 'application/json', 'X-Requested-With': 'modelbib', ...(inAuto ? {'X-Auto': '1'} : {})}, body: b === undefined ? undefined : JSON.stringify(b)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { if (r.status === 401 && j.login) showLogin(); throw new Error((j.error || r.statusText) + (r.status === 403 && j.path ? ' (' + j.path + ')' : '')); }
  if (gen !== routeGen && m === 'GET' && u !== '/api/rev' && u !== '/api/me') throw Object.assign(new Error('Verouderd antwoord'), {stale: true});
  return j;
}
let tt;
function toast(msg, kind) {
  const t = $('#toast'); t.textContent = (kind ? '' : '✓ ') + msg; t.className = 'show ' + (kind || '');
  clearTimeout(tt); tt = setTimeout(() => t.className = '', 2600);
}
const run = f => async (...a) => { try { return await f(...a); } catch (e) { if (!e.stale) toast(e.message, 'err'); } };
const fsize = b => b == null ? '–' : b >= 2 ** 30 ? (b / 2 ** 30).toFixed(1) + ' GB' : b >= 2 ** 20 ? (b / 2 ** 20).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
const fdate = t => t ? new Date(t * 1000).toLocaleString(I18N.LOC, {dateStyle: 'short', timeStyle: 'medium'}) : '–';
const label = m => m.display || m.name;
const dimTxt = m => {
  const r = x => Math.round(x * 10) / 10;
  if (multiPlate(m) && m.pdims && m.pdims.length > 1) return `${m.pdims.length} platen, grootste ${[0, 1, 2].map(i => r(Math.max(...m.pdims.map(x => x.dims[i])))).join(' × ')} mm`;
  return m.dims ? m.dims.map(r).join(' × ') + ' mm' : '–';
};
const ICON_EXT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';
const linkify = s => esc(s).replace(/(https?:\/\/[^\s<)]+)/g, u => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);
const tbl = (head, rows) => `<table><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr>${rows.join('')}</table>`;
let ME = {auth: false, user: null, role: 'admin', can_download: true, can_upload: true}, inAuto = false, onRev = null, stopFn = null, lastRev = null, openId = null, reloadLib = null, vw = null;
const adm = () => ME.role === 'admin';
const staff = () => ME.role === 'staff';
const MSLOGO = '<svg width="16" height="16" viewBox="0 0 21 21" aria-hidden="true" style="vertical-align:-3px"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>';
const msButton = `<a class="btn" id="lms" href="/api/ms/login" style="text-align:center;text-decoration:none;background:#fff;color:#1f1f1f!important;border:1px solid #8c8c8c;display:flex;align-items:center;justify-content:center;gap:10px;font-weight:600">${MSLOGO.replace('width="16" height="16"', 'width="21" height="21"')}<span>Inloggen met Microsoft</span></a>`;
const loginKind = u => u.ms ? MSLOGO + ' Microsoft' : '<span class="dim">Lokaal</span>';
const ROLE_NL = {admin: 'beheerder', staff: 'medewerker', student: 'leerling'};

// ------------------------------------------------------------ navigatie
const NAV = [['library', 'Bibliotheek'], ['requests', 'Printaanvragen'], ['reports', 'Meldingen'], ['pupils', 'Leerlingen'], ['access', 'Mappen'],
  ['activity', 'Activiteit', [['queue', 'Wachtrij'], ['history', 'Geschiedenis']]], ['wanted', 'Gewenst'], ['duplicates', 'Duplicaten'],
  ['settings', 'Instellingen', [['media', 'Mediabeheer'], ['printers', 'Printers'], ['schools', 'Scholen'], ['users', 'Gebruikers'], ['microsoft', 'Microsoft'], ['categories', 'Categorieën'], ['auto', 'Automatisch indelen'], ['general', 'Algemeen']]],
  ['system', 'Systeem', [['status', 'Status'], ['tasks', 'Taken'], ['logs', 'Logs']]]];
const langBlock = () => `<div class="lang">${['nl', 'en'].map(l => `<button data-lang="${l}" class="${I18N.lang === l ? 'p' : ''}" title="${l === 'nl' ? 'Nederlands' : 'English'}">${l.toUpperCase()}</button>`).join('')}</div>`;
function buildNav() {
  const nav = adm() ? NAV : NAV.filter(n => n[0] === 'library' || n[0] === 'requests' || (staff() && ['reports', 'pupils', 'access'].includes(n[0])));  // leerlingen: bibliotheek en eigen aanvragen; medewerkers ook meldingen en leerlingen
  $('#nav').innerHTML = '<div class="logo"><img src="/static/logo.svg" alt="" width="28" height="28"><span class="wm">Model<span>arr</span> School</span></div>' + nav.map(([id, t, ch]) => ch
    ? `<div class="grp">${t}${id === 'activity' ? '<span class="badge" id="qb"></span>' : ''}</div>` + ch.map(([c, n]) => `<a class="sub" href="#/${id}/${c}" data-r="${id}/${c}">${n}</a>`).join('')
    : `<a href="#/${id}" data-r="${id}">${t}${id === 'wanted' ? '<span class="badge" id="wb"></span>' : ''}${id === 'duplicates' ? '<span class="badge" id="db"></span>' : ''}${id === 'requests' ? '<span class="badge" id="rqb"></span>' : ''}${id === 'reports' ? '<span class="badge" id="rpb"></span>' : ''}</a>`).join('')
    + (ME.user ? `<div class="usr">👤 <b>${esc(ME.display || ME.user)}</b> <span class="dim">${ROLE_NL[ME.role] || ''}${ME.school ? ' · ' + esc(ME.school.name) : ''}</span><br><button id="logout">Uitloggen</button></div>` : '') + langBlock() + (ME.version ? `<div class="dim" style="font-size:11px;padding:6px 10px">${esc(ME.version)}</div>` : '');
}
$('#nav').onclick = run(async e => { if (e.target.dataset.lang) I18N.setLang(e.target.dataset.lang); if (e.target.id === 'logout') { await api('/api/logout', 'POST'); location.reload(); } });
const V = {};
function hideCtx() { const m = $('#ctx'); m.style.display = 'none'; m.innerHTML = ''; }
document.addEventListener('click', e => { if (!(e.target.closest && e.target.closest('#ctx'))) hideCtx(); });
let libKey = null;  // toetsen van de bibliotheek (Ctrl+A, Escape)
document.addEventListener('keydown', e => { const was = $('#ctx').style.display === 'block'; if (e.key === 'Escape') hideCtx(); if (libKey && !was) libKey(e); });
let ctxAt = 0;  // scrollen/vergroten sluit het menu, maar niet de eerste halve seconde (het opnieuw tekenen na het selecteren kan een scroll-gebeurtenis geven)
const hideCtxLater = () => { if (Date.now() - ctxAt > 500) hideCtx(); };
window.addEventListener('scroll', hideCtxLater, true); window.addEventListener('resize', hideCtxLater);
// Selecteren door te slepen: een kader over de modellen trekken
let drag = null, dragAt = 0, dragTimer = null;
function dragApply(x, y) {
  const v = $('#view'), vr = v.getBoundingClientRect ? v.getBoundingClientRect() : {left: 0, top: 0};
  const sx = drag.sx - (v.scrollLeft || 0) + vr.left, sy = drag.sy - (v.scrollTop || 0) + vr.top;  // beginpunt blijft aan de inhoud vast zitten, ook als er gescrold wordt
  const q = {l: Math.min(sx, x), t: Math.min(sy, y), r: Math.max(sx, x), b: Math.max(sy, y)}, band = $('#band');
  band.style.display = 'block'; band.style.left = q.l + 'px'; band.style.top = q.t + 'px'; band.style.width = (q.r - q.l) + 'px'; band.style.height = (q.b - q.t) + 'px';
  const sel = new Set(drag.add ? drag.base : []);
  document.querySelectorAll('#items [data-id]').forEach(el => {
    const r = el.getBoundingClientRect(), id = +el.dataset.id;
    if (r.right >= q.l && r.left <= q.r && r.bottom >= q.t && r.top <= q.b) sel.add(id);
    const on = sel.has(id), cb = el.querySelector('.sel');
    el.classList.toggle('s', on); if (cb) cb.checked = on;  // alleen de vinkjes bijwerken: niet de hele lijst opnieuw tekenen
  });
  L.sel = sel;
}
function dragMove(e) {
  if (!drag) return;
  drag.mx = e.clientX; drag.my = e.clientY;
  if (!drag.on) {
    if (Math.hypot(e.clientX - drag.cx, e.clientY - drag.cy) < 6) return;
    drag.on = true; $('#items').classList.add('drag'); dragTimer = setInterval(dragScroll, 30);
  }
  dragApply(e.clientX, e.clientY);
}
function dragScroll() {  // bij de boven- of onderrand automatisch doorscrollen
  if (!drag || !drag.on) return;
  const v = $('#view'), vr = v.getBoundingClientRect(); let d = 0;
  if (drag.my < vr.top + 40) d = -18; else if (drag.my > vr.bottom - 40) d = 18;
  if (d) { v.scrollTop += d; dragApply(drag.mx, drag.my); }
}
function dragEnd() {
  if (!drag) return;
  clearInterval(dragTimer); const was = drag.on; drag = null; $('#band').style.display = 'none'; $('#items').classList.remove('drag');
  if (was) { dragAt = Date.now(); drawBulk(); }  // de klik die op loslaten volgt negeren en de selectiebalk bijwerken
}
window.addEventListener('mousemove', dragMove); window.addEventListener('mouseup', dragEnd);
async function route() {
  routeGen++; closeModal(); hideCtx(); libKey = null; drag = null; onRev = null; if (stopFn) { stopFn(); stopFn = null; }
  let r = location.hash.replace(/^#\//, '') || 'library';
  r = {activity: 'activity/queue', settings: 'settings/media', system: 'system/status'}[r] || r;
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('on', a.dataset.r === r));
  $('#tools').innerHTML = ''; $('#view').onclick = null; $('#view').oncontextmenu = null; $('#view').ontouchstart = $('#view').ontouchmove = $('#view').ontouchend = $('#view').ontouchcancel = null; $('#view').onkeydown = null; $('#view').onchange = null; $('#view').innerHTML = '';
  await run(V[r] || V.library)();
}
addEventListener('hashchange', route);
function scanBar(s) {  // voortgang van een lopende scan: bij grote bibliotheken lijkt er anders niets te gebeuren
  const e = $('#scanbar'); if (!e) return;
  if (!s) { e.className = ''; e.textContent = ''; return; }
  const n = v => Number(v).toLocaleString(I18N.LOC);
  e.className = 'on';
  e.innerHTML = s.phase === 'bijwerken' && s.total
    ? `Modellen toevoegen… ${n(s.added)} van ${n(s.total)}<span class="bar"><i style="width:${Math.min(100, Math.round(100 * s.added / s.total))}%"></i></span>`
    : `Bibliotheek scannen… ${n(s.files)} bestanden gevonden in ${n(s.dirs)} mappen`;
}
// Pop-up voor medewerkers en beheerders: er staan printaanvragen of meldingen open. Verschijnt bij het inloggen en zodra er nieuwe bijkomen.
function staffPopup(r) {
  if (!(adm() || staff())) return;
  const rq = r.requests_open || 0, rp = r.reports_open || 0, at = (location.hash || '').replace('#/', '');
  let seen = {rq: -1, rp: -1};  // -1: nog niet getoond in deze sessie
  try { seen = JSON.parse(sessionStorage.getItem('popseen')) || seen; } catch (_) { /* privévenster */ }
  if (at.startsWith('requests')) seen.rq = rq; if (at.startsWith('reports')) seen.rp = rp;  // je kijkt er al naar
  if (rq < seen.rq) seen.rq = rq; if (rp < seen.rp) seen.rp = rp;  // minder geworden: later nieuwe laten melden
  const fresh = (rq > Math.max(seen.rq, 0) || (seen.rq < 0 && rq > 0)) || (rp > Math.max(seen.rp, 0) || (seen.rp < 0 && rp > 0));
  let el = $('#spop');
  if (fresh) {
    seen.rq = rq; seen.rp = rp;
    if (!el) { el = document.createElement('div'); el.id = 'spop'; document.body.appendChild(el); el.onclick = e => { const b = e.target.closest('[data-go]'); if (b && b.dataset.go) location.hash = '#/' + b.dataset.go; if (b) el.remove(); }; }
    el.innerHTML = '<b>Er wacht werk op je</b>' + (rq ? `<div>${rq} openstaande ${rq === 1 ? 'printaanvraag' : 'printaanvragen'}</div>` : '') + (rp ? `<div>${rp} openstaande ${rp === 1 ? 'melding' : 'meldingen'}</div>` : '')
      + `<div class="row">${rq ? '<button class="p" data-go="requests">Printaanvragen bekijken</button>' : ''}${rp ? `<button ${rq ? '' : 'class="p"'} data-go="reports">Meldingen bekijken</button>` : ''}<button data-go="">Niet nu</button></div>`;
  } else if (el && !rq && !rp) el.remove();
  try { sessionStorage.setItem('popseen', JSON.stringify(seen)); } catch (_) { /* privévenster */ }
}
async function poll() {
  if (ME.auth && !ME.user) return;  // niet ingelogd: de inlogpagina niet steeds opnieuw laten tekenen
  try {
    const r = await api('/api/rev');
    const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
    set('#qb', r.pending || ''); set('#rqb', r.requests_open || ''); set('#rpb', r.reports_open || ''); set('#wb', r.failed || ''); set('#db', r.dups || ''); staffPopup(r); scanBar(r.scan); $('#banner').style.display = (r.auth || !adm()) ? 'none' : 'block';
    if (lastRev !== null && r.rev !== lastRev && onRev) { inAuto = true; try { await onRev(); } finally { inAuto = false; } }
    lastRev = r.rev;
  } catch (e) { /* server tijdelijk weg */ }
}
setInterval(poll, 3000);

// ------------------------------------------------------------ bibliotheek
const L = {school: '', owner: '', view: localStorage.getItem('view') || 'posters', q: '', cat: 'all', ext: 'all', flt: 'all', sort: 'name', sel: new Set(), page: 0, size: (() => { try { const n = parseInt(localStorage.getItem('psize'), 10); return n >= 0 ? n : 100; } catch (e) { return 100; } })(), sig: '', printers: [], logs: {}, spools: null, d: {models: [], categories: [], big_mb: 50, recent_days: 7}};
const lc = s => String(s ?? '').toLowerCase();
// past het model op het bed? Afmetingen van het hele model; 90° draaien in het vlak mag. null = afmetingen onbekend.
const fitsDims = (d, p) => ((d[0] <= p.bed_x + .01 && d[1] <= p.bed_y + .01) || (d[0] <= p.bed_y + .01 && d[1] <= p.bed_x + .01)) && d[2] <= p.bed_z + .01;
const multiPlate = m => ((m.info || {}).plates || []).length > 1;
// Meerdere platen: elke plaat wordt apart geprint, dus elke plaat moet passen. null = (nog) onbekend.
const fits = (m, p) => multiPlate(m) ? (m.pdims && m.pdims.length ? m.pdims.every(x => fitsDims(x.dims, p)) : null) : m.dims ? fitsDims(m.dims, p) : null;
const fitsOn = (m, id) => { const p = (L.printers || []).find(x => x.id === id); return !!p && fits(m, p) === true; };
const thumb = (m, cls = '') => m.status === 'ok' ? `<img draggable="false" class="${cls}" loading="lazy" src="/api/thumb/${m.id}.png?v=${m.thumb_at}">`
  : `<span class="ph ${m.status} ${cls}" title="${esc(m.error || '')}">${m.status === 'pending' || m.status === 'processing' ? '⏳' : m.status === 'failed' ? '⚠' : esc(m.ext)}</span>`;
const chipsOf = m => m.cats.map(id => `<span class="chip">${esc((L.d.categories.find(c => c.id === id) || {}).name)}</span>`).join('');
const nf = n => Number(n).toLocaleString(I18N.LOC);
function pagerHTML(total, pages) {
  if (!total) return '';
  const from = L.size ? L.page * L.size + 1 : 1, to = L.size ? Math.min(total, (L.page + 1) * L.size) : total;
  const b = (p, txt, dis, title) => `<button class="sm" data-pg="${p}" ${dis ? 'disabled' : ''} ${title ? `title="${title}"` : ''}>${txt}</button>`;
  return `<span class="dim">${nf(from)}–${nf(to)} van ${nf(total)}</span>`
    + (pages > 1 ? `${b(0, '«', L.page === 0, 'Eerste pagina')}${b(L.page - 1, '‹', L.page === 0, 'Vorige pagina')}<span>Pagina <input class="pgi" type="number" min="1" max="${pages}" value="${L.page + 1}"> van ${nf(pages)}</span>${b(L.page + 1, '›', L.page >= pages - 1, 'Volgende pagina')}${b(pages - 1, '»', L.page >= pages - 1, 'Laatste pagina')}` : '')
    + `<label class="dim">Per pagina <select class="pgs">${[25, 50, 100, 200, 500, 0].map(n => `<option value="${n}" ${n === L.size ? 'selected' : ''}>${n || 'Alles'}</option>`).join('')}</select></label>`;
}
async function goPage(p) { L.page = p; await loadLib(); $('#view').scrollTop = 0; }
// De server filtert, sorteert en pagineert; de browser krijgt alleen de zichtbare pagina (L.d.models) en de id's van alles wat past (L.d.ids).
const libURL = () => '/api/library?' + new URLSearchParams({page: L.page, size: L.size, q: L.q, cat: L.cat, ext: L.ext, flt: L.flt, sort: L.sort, ...(L.school ? {school: L.school} : {}), ...(L.owner ? {owner: L.owner} : {}), ...(openId ? {with: openId} : {})});
let libSeq = 0, loadLib = async () => {};
function drawBulk() {
  const total = L.d.total ?? L.d.models.length;
  $('#bulk').innerHTML = !L.sel.size ? (adm() && total ? `<button id="bsa" title="Selecteert alle modellen die nu in de lijst staan (met het huidige filter). Tip: Shift+klik op een vinkje selecteert alles ertussen.">☑ Alles selecteren (${total})</button>` : '') : `<b>${L.sel.size} geselecteerd</b><button id="bsa">☑ Alles selecteren (${total})</button><span class="dim">Categorie:</span><select id="bc" title="Kies een categorie en gebruik de knoppen hiernaast voor alle geselecteerde modellen">${L.d.categories.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><button id="ba" title="Zet de geselecteerde modellen in de gekozen categorie. De bestanden zelf blijven ongemoeid.">＋ In categorie zetten</button><button id="br" title="Haalt de geselecteerde modellen uit de gekozen categorie. De bestanden zelf worden niet verwijderd.">－ Uit categorie halen</button><button id="bf1">★ Favoriet</button><button id="bf0">☆ Niet favoriet</button><button id="bpt">🖨 Te printen</button><button id="bpp">✓ Geprint</button><button id="bt" class="d" title="Verplaatst de geselecteerde bestanden naar de map .prullenbak in hun root folder. Ze worden niet definitief verwijderd.">🗑 Naar prullenbak</button><button id="bx">Wis selectie</button>`;
}
// Alleen de selectie bijwerken (vinkjes, markering en de balk), zonder de lijst opnieuw te tekenen: dat houdt dubbelklikken en scrollen heel en voorkomt flikkeren.
function markSel() {
  document.querySelectorAll('#items [data-id]').forEach(el => { const on = L.sel.has(+el.dataset.id), cb = el.querySelector('.sel'); el.classList.toggle('s', on); if (cb) cb.checked = on; });
  drawBulk();
}
function draw() {
  const a = L.d.models, total = L.d.total ?? a.length, pages = L.d.pages || 1;
  $('#cnt').textContent = `${total} van ${L.d.all ?? total}`;
  const pager = pagerHTML(total, pages); $('#pg1').innerHTML = pager; $('#pg2').innerHTML = total > Math.min(L.size || 1e9, 25) ? pager : '';
  drawBulk();
  $('#items').innerHTML = !total ? '<p class="empty">Geen modellen gevonden. Voeg een root folder toe onder Instellingen → Mediabeheer.</p>'
    : L.view === 'posters' ? `<div class="grid">${a.map(m => `<div class="card ${L.sel.has(m.id) ? 's' : ''}" data-id="${m.id}">${adm() ? `<input type="checkbox" class="sel" ${L.sel.has(m.id) ? 'checked' : ''}>` : ''}<div class="badges">${m.container ? `<span title="In zip: ${esc(m.container)}">ZIP</span>` : ''}${adm() && m.favorite ? '<span class="favb" title="Favoriet">★</span>' : ''}${!adm() ? '' : m.printed === 'printed' ? '<span class="prb" title="Geprint">✓</span>' : m.printed === 'toprint' ? '<span title="Te printen">🖨</span>' : ''}${adm() && m.dup ? `<span class="dupb" title="${m.dup === 'exact' ? 'Identiek aan een ander bestand' : 'Zelfde mesh als een ander bestand'}">⧉</span>` : ''}</div><div class="th">${thumb(m)}</div><div class="nm" title="${esc(m.path)}">${esc(label(m))}</div><div class="chips">${chipsOf(m)}</div></div>`).join('')}</div>`
    : tbl([adm() ? '<input type="checkbox" id="all">' : '', '', 'Naam', 'Categorieën', 'Formaat', 'Afmetingen', 'Grootte', 'Toegevoegd', 'Ontwerper', 'Map'],
      a.map(m => `<tr data-id="${m.id}"><td>${adm() ? `<input type="checkbox" class="sel" ${L.sel.has(m.id) ? 'checked' : ''}>` : ''}</td><td>${thumb(m, 'mini')}</td><td>${m.favorite ? '★ ' : ''}${esc(label(m))}</td><td><div class="chips" style="padding:0;min-height:0">${chipsOf(m)}</div></td><td>${esc(m.ext)}</td><td>${dimTxt(m)}</td><td>${fsize(m.size)}</td><td>${fdate(m.added)}</td><td>${esc((m.info || {}).designer || '')}</td><td class="dim">${esc(m.folder)}</td></tr>`));
}
V.library = async () => {
  $('#title').textContent = 'Bibliotheek';
  $('#tools').innerHTML = `<input id="q" placeholder="Zoeken… (bijv. rack ext:3mf cat:server map:lab)" title="Zoekt in naam, weergavenaam, categorie, extensie, map en 3MF-info. Prefixen: naam: ext: cat: map: ontwerper: kleuren: notitie: bron:. Gebruik &quot;aanhalingstekens&quot; voor zinnen." value="${esc(L.q)}" style="width:310px"><select id="fc"></select><select id="fe"></select><select id="ff"></select><select id="fs"><option value="name">Sorteer: naam</option><option value="added">Sorteer: toegevoegd</option><option value="size">Sorteer: grootte</option></select>${adm() || staff() ? '<select id="fsc" style="display:none" title="Toon alleen modellen van deze school"></select><select id="fo" style="display:none" title="Toon alleen de bestanden van deze leerling"></select>' : ''}<span id="cnt" class="dim"></span><button id="vws"></button>${adm() ? '<button id="upd" class="p">↻ Bijwerken</button>' : ''}${ME.can_upload ? '<button id="upl" class="up" title="Modellen uploaden naar een map en categorie kiezen">⬆ Uploaden</button>' : ''}`;
  $('#view').innerHTML = '<div id="bulk"></div><div class="pager" id="pg1"></div><div id="items"></div><div class="pager" id="pg2"></div>';
  const sync = () => $('#vws').textContent = L.view === 'posters' ? '☰ Tabel' : '▦ Posters';
  sync(); $('#fs').value = L.sort;
  let qt; $('#q').oninput = e => { L.q = e.target.value.toLowerCase(); clearTimeout(qt); qt = setTimeout(() => { L.page = 0; load(); }, (L.d.all || 0) > 3000 ? 250 : 0); };  // niet bij elke toets de server vragen bij een grote bibliotheek
  $('#fc').onchange = e => { L.cat = e.target.value; L.page = 0; load(); };
  $('#fe').onchange = e => { L.ext = e.target.value; L.page = 0; load(); };
  $('#ff').onchange = e => { L.flt = e.target.value; if (L.flt === 'recent') L.sort = 'added'; if (L.flt === 'big') L.sort = 'size'; $('#fs').value = L.sort; L.page = 0; load(); };
  $('#fs').onchange = e => { L.sort = e.target.value; L.page = 0; load(); };
  const loadOwners = run(async () => {  // beheerder kiest eerst een school, daarna een leerling; een medewerker kiest direct uit de eigen school
    if (!$('#fo')) return;
    if (adm()) {
      if (!L.schools) L.schools = (await api('/api/schools')).schools;
      $('#fsc').innerHTML = '<option value="">Alle scholen</option>' + L.schools.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join(''); $('#fsc').value = String(L.school || ''); $('#fsc').style.display = '';
    }
    const sid = adm() ? L.school : (ME.school && ME.school.id);
    if (!sid) { L.owner = ''; $('#fo').style.display = 'none'; return; }
    const us = (await api('/api/school/users' + (adm() ? '?school_id=' + sid : ''))).users;
    $('#fo').innerHTML = '<option value="">Alle leerlingen</option>' + us.map(x => `<option value="${x.id}">${esc(x.display_name || x.username)}${x.klas ? ' (' + esc(x.klas) + ')' : ''}</option>`).join('');
    $('#fo').value = String(L.owner || ''); if ($('#fo').value !== String(L.owner || '')) { L.owner = ''; $('#fo').value = ''; }
    $('#fo').style.display = '';
  });
  if ($('#fsc')) $('#fsc').onchange = e => { L.school = e.target.value; L.owner = ''; L.page = 0; loadOwners().then(() => load()); };
  if ($('#fo')) $('#fo').onchange = e => { L.owner = e.target.value; L.page = 0; load(); };
  $('#vws').onclick = () => { L.view = L.view === 'posters' ? 'table' : 'posters'; localStorage.setItem('view', L.view); sync(); draw(); };
  if ($('#upl')) $('#upl').onclick = run(async () => openUpload(L.d.categories));
  if ($('#upd')) $('#upd').onclick = run(async () => { await api('/api/tasks/scan/run', 'POST'); toast('Scan gestart', 'info'); });
  const load = run(async () => {
    const my = ++libSeq, d = await api(libURL()), pr = await api('/api/printers');
    if (my !== libSeq) return;  // een nieuwere vraag (snel typen) is onderweg: dit antwoord is verouderd
    L.d = d; L.printers = pr; L.page = d.page ?? L.page;
    const keep = L.cat;
    $('#fc').innerHTML = '<option value="all">Alle categorieën</option><option value="none">Zonder categorie</option>' + L.d.categories.map(c => `<option value="${c.id}">${esc(c.name)} (${c.count})</option>`).join('');
    $('#fc').value = keep; if ($('#fc').value !== keep) { L.cat = 'all'; $('#fc').value = 'all'; }
    const exts = L.d.exts || [...new Set(L.d.models.map(m => m.ext))].sort();
    $('#fe').innerHTML = '<option value="all">Alle formaten</option>' + exts.map(e => `<option value="${e}">${e.toUpperCase()}</option>`).join('');
    $('#fe').value = L.ext; if ($('#fe').value !== L.ext) { L.ext = 'all'; $('#fe').value = 'all'; }
    $('#ff').innerHTML = `<option value="all">Alle modellen</option><option value="nopreview">Zonder preview</option><option value="recent">Recent toegevoegd (${L.d.recent_days} dgn)</option><option value="big">Groot (&gt; ${L.d.big_mb} MB)</option><option value="multicolor">Meerkleurig (2+ kleuren)</option>${adm() ? '' : '<option value="mine">Mijn modellen</option>'}${adm() ? '<option value="dup">Dubbele bestanden</option><option value="fav">★ Favorieten</option><option value="toprint">Te printen</option><option value="printed">Geprint</option><option value="failedprint">Eerder mislukt</option>' : ''}` + L.printers.map(p => `<option value="fit:${p.id}">Past op ${esc(p.name)}</option>`).join('');
    $('#ff').value = L.flt; if ($('#ff').value !== L.flt) { L.flt = 'all'; $('#ff').value = 'all'; }
    if (L.d.ids && L.d.total === L.d.all) L.sel = new Set([...L.sel].filter(id => L.d.ids.includes(id)));  // verwijderde modellen uit de selectie halen
    draw();
  });
  $('#view').onchange = run(async e => {
    if (e.target.classList.contains('pgs')) { L.size = +e.target.value; try { localStorage.setItem('psize', String(L.size)); } catch (x) { /* privévenster */ } await goPage(0); }
    else if (e.target.classList.contains('pgi')) { const p = parseInt(e.target.value, 10); if (p >= 1) await goPage(p - 1); }
  });
  // Acties op de selectie (vanuit de balk en het rechtsklikmenu). Na een actie wordt de selectie gewist; wat niet lukte blijft geselecteerd.
  const bulkFlag = async body => {
    const n = L.sel.size; await api('/api/models/bulk', 'POST', {model_ids: [...L.sel], ...body}); L.sel.clear(); await load(); toast(`Bijgewerkt: ${n} modellen`);
  };
  const bulkCat = async (add, c) => {
    const n = L.sel.size; await api('/api/assign', 'POST', {model_ids: [...L.sel], category_id: c, action: add ? 'add' : 'remove'}); L.sel.clear(); await load();
    toast(add ? `Categorie toegevoegd aan ${n} modellen` : `Categorie verwijderd van ${n} modellen`);
  };
  const bulkTrash = async () => {
    const ids = [...L.sel];
    if (!confirm(`${ids.length} bestanden naar de map .prullenbak in hun root folder verplaatsen?\n\nDe bestanden worden niet definitief verwijderd. Modellen in een zip en in een map waar schrijven uit staat worden overgeslagen.`)) return;
    let done = 0; const failed = [];
    for (let i = 0; i < ids.length; i += 500) { const r = await api('/api/models/trash', 'POST', {ids: ids.slice(i, i + 500), any: true}); done += r.done; failed.push(...r.failed); }
    L.sel = new Set(failed.map(f => f.id));  // wat niet lukte blijft geselecteerd
    await load();
    toast(failed.length ? `${done} verplaatst, ${failed.length} niet: ${failed[0].error}` : `${done} naar .prullenbak verplaatst`, failed.length ? 'err' : undefined);
  };
  // Rechtsklikmenu op een model (of op de selectie); op een aanraakscherm: lang indrukken
  let lpAt = 0, lpTimer = null, lpXY = null;
  const showCtx = (id, x, y) => {
    if (!L.sel.has(id)) { L.sel.clear(); L.sel.add(id); markSel(); }  // klik op iets buiten de selectie: alleen dat model
    const cats = L.d.categories, n = L.sel.size, menu = $('#ctx');
    const sub = act => `<div class="sub">${cats.map(c => `<div class="it" data-cm="${act}:${c.id}">${esc(c.name)}</div>`).join('')}</div>`;
    const has = (label, act) => cats.length ? `<div class="it has"><span>${label}</span><span class="ar">▸</span>${sub(act)}</div>` : `<div class="it off"><span>${label}</span><span class="ar dim">Nog geen categorieën</span></div>`;
    menu.innerHTML = `<div class="hd">${n} geselecteerd</div>${has('In categorie zetten', 'cadd')}${has('Uit categorie halen', 'crem')}<div class="sep"></div>`
      + `<div class="it" data-cm="fav1">★ Favoriet</div><div class="it" data-cm="fav0">☆ Niet favoriet</div><div class="sep"></div><div class="it d" data-cm="trash">🗑 Naar prullenbak</div>`;
    const w = window.innerWidth || 1200, h = window.innerHeight || 800;
    menu.className = x > w - 440 ? 'left' : '';
    menu.style.display = 'block'; ctxAt = Date.now();
    const mw = menu.offsetWidth || 230, mh = menu.offsetHeight || 260;  // binnen het scherm houden
    menu.style.left = Math.max(4, Math.min(x || 0, w - mw - 6)) + 'px'; menu.style.top = Math.max(4, Math.min(y || 0, h - mh - 6)) + 'px';
  };
  const rowOf = e => adm() && e.target && e.target.closest ? e.target.closest('[data-id]') : null;
  $('#view').oncontextmenu = e => {
    const row = rowOf(e); if (!row) return;
    e.preventDefault();
    if (Date.now() - lpAt > 800) showCtx(+row.dataset.id, e.clientX, e.clientY);  // bij lang indrukken staat het menu er al
  };
  const lpStop = () => { clearTimeout(lpTimer); lpTimer = null; };
  $('#view').ontouchstart = e => {
    lpStop(); const row = rowOf(e), tt = e.touches && e.touches[0]; if (!row || !tt || e.touches.length > 1) return;
    lpXY = [tt.clientX, tt.clientY];
    lpTimer = setTimeout(() => { lpTimer = null; lpAt = Date.now(); showCtx(+row.dataset.id, lpXY[0], lpXY[1]); }, 500);
  };
  $('#view').ontouchmove = e => { const tt = e.touches && e.touches[0]; if (lpTimer && tt && lpXY && Math.hypot(tt.clientX - lpXY[0], tt.clientY - lpXY[1]) > 10) lpStop(); };  // vegen/scrollen is geen lang indrukken
  $('#view').ontouchend = e => { lpStop(); if (Date.now() - lpAt < 700 && e.cancelable !== false && e.preventDefault) e.preventDefault(); };  // geen klik (model openen) na lang indrukken
  $('#view').ontouchcancel = lpStop;
  $('#ctx').onclick = run(async e => {
    const a = e.target.dataset && e.target.dataset.cm;
    if (!a) { const hs = e.target.closest && e.target.closest('.has'); if (hs) hs.classList.toggle('open'); return; }  // aanraakscherm: tik opent het submenu
    hideCtx();
    const [act, cid] = a.split(':');
    if (act === 'cadd' || act === 'crem') return bulkCat(act === 'cadd', +cid);
    if (act === 'fav1' || act === 'fav0') return bulkFlag({favorite: act === 'fav1'});
    if (act === 'trash') return bulkTrash();
  });
  $('#view').onmousedown = e => {
    if (!adm() || e.button !== 0 || !e.target.closest) return;
    if (e.target.closest('button,input,select,a,textarea,.pager,#bulk') || !e.target.closest('#items')) return;
    const v = $('#view'), vr = v.getBoundingClientRect();
    drag = {cx: e.clientX, cy: e.clientY, sx: e.clientX - vr.left + v.scrollLeft, sy: e.clientY - vr.top + v.scrollTop, add: e.shiftKey || e.ctrlKey || e.metaKey, base: new Set(L.sel), on: false};
    e.preventDefault();  // geen tekstselectie of sleepactie van de browser
  };
  $('#view').ondblclick = e => { const row = e.target.closest && e.target.closest('[data-id]'); if (row && !e.target.closest('input,button')) openModal(+row.dataset.id); };  // met een actieve selectie opent een klik het model niet: dubbelklik wel
  libKey = e => {
    if (openId || !adm()) return;
    const tg = e.target, tag = (tg && tg.tagName) || '';
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || (tg && tg.isContentEditable)) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) { e.preventDefault(); (L.d.ids || L.d.models.map(m => m.id)).forEach(id => L.sel.add(id)); markSel(); }  // alles wat in het filter past
    else if (e.key === 'Escape' && L.sel.size) { L.sel.clear(); markSel(); }
  };
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (Date.now() - lpAt < 700 || Date.now() - dragAt < 300) return;  // de klik die op lang indrukken of slepen volgt
    if (t.dataset.pg !== undefined && !t.disabled) return goPage(+t.dataset.pg);
    if (t.id === 'bx') { L.sel.clear(); return markSel(); }
    if (t.id === 'bt') return bulkTrash();
    if (t.id === 'bsa') { (L.d.ids || L.d.models.map(m => m.id)).forEach(id => L.sel.add(id)); return markSel(); }
    if (['bf1', 'bf0', 'bpp', 'bpt'].includes(t.id)) return bulkFlag({bf1: {favorite: true}, bf0: {favorite: false}, bpp: {printed: 'printed'}, bpt: {printed: 'toprint'}}[t.id]);
    if (t.id === 'all') { t.checked ? (L.d.ids || L.d.models.map(m => m.id)).forEach(id => L.sel.add(id)) : L.sel.clear(); return markSel(); }
    if (t.id === 'ba' || t.id === 'br') {
      const c = +$('#bc').value; if (!c) return toast('Kies eerst een categorie', 'info');
      return bulkCat(t.id === 'ba', c);
    }
    const row = t.closest('[data-id]');
    if (!row) { if (adm() && L.sel.size && t.closest('#items')) { L.sel.clear(); markSel(); } return; }  // klik naast de modellen: selectie wissen
    const id = +row.dataset.id;
    if (t.classList.contains('sel') || (adm() && (L.sel.size || e.ctrlKey || e.metaKey || e.shiftKey))) {  // met een actieve selectie (of Ctrl/Shift) selecteert een klik op het kaartje
      const list = L.d.ids || L.d.models.map(m => m.id), i = list.indexOf(id), k = list.indexOf(L.lastSel);
      if (e.shiftKey && i >= 0 && k >= 0) { const on = !L.sel.has(id); list.slice(Math.min(i, k), Math.max(i, k) + 1).forEach(x => on ? L.sel.add(x) : L.sel.delete(x)); }  // Shift+klik: alles ertussen
      else L.sel.has(id) ? L.sel.delete(id) : L.sel.add(id);
      L.lastSel = id; markSel();
    } else openModal(id);
  });
  onRev = load; reloadLib = load; loadLib = load; loadOwners(); await load();
};

// ------------------------------------------------------------ detailvenster met 3D-viewer
const cur = () => L.d.models.find(x => x.id === openId) || (L.d.open && L.d.open.id === openId ? L.d.open : undefined);
const INFO = {title: 'Titel', designer: 'Ontwerper', application: 'Programma', created: 'Aangemaakt', license: 'Licentie', copyright: 'Copyright', printer: 'Printer', layer_height: 'Laaghoogte', nozzle: 'Nozzle', filament: 'Filament', print_time: 'Printtijd', filament_g: 'Filamentverbruik', color_count: 'Kleuren', plates: 'Platen'};
const copyrightTxt = v => { try { const j = JSON.parse(v); const a = (Array.isArray(j) ? j : [j]).map(x => [x.author, x.title].filter(Boolean).join(' – ')).filter(Boolean); if (a.length) return a.join('; '); } catch (_) {} return v.length > 120 ? v.slice(0, 117) + '…' : v; };
const infoVal = (k, v) => k === 'copyright' ? copyrightTxt(String(v)) : k === 'plates' ? v.length + ' (' + v.map(x => x.name || x.id).join(', ') + ')' : k === 'layer_height' || k === 'nozzle' ? v + ' mm' : k === 'filament_g' ? v + ' g' : k === 'print_time' ? `${Math.floor(v / 3600)}u ${Math.round(v % 3600 / 60)}m` : v;
const swatches = i => (i.colors || []).map(c => `<span title="${esc(c)}" style="display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid #fff4;background:${/^#[0-9A-F]{6}$/.test(c) ? c : '#888'};margin-right:3px;vertical-align:-2px"></span>`).join('') + ' ' + i.color_count;
function infoHTML(m) {
  const i = m.info || {}, rows = Object.keys(INFO).filter(k => i[k]).map(k => `<tr><td class="dim">${INFO[k]}</td><td>${k === 'color_count' ? swatches(i) : esc(infoVal(k, i[k]))}</td></tr>`);
  if (!rows.length && !i.description) return '';
  return `<b>3MF-informatie</b><table class="kv">${rows.join('')}</table>${i.description ? `<div class="info desc">${linkify(i.description)}</div>` : ''}${adm() && i.title && i.title !== m.display ? '<button id="vtitle">Titel overnemen als weergavenaam</button>' : ''}`;
}
function fitHTML(m) {
  if (!m.dims && !multiPlate(m)) return '';
  const ps = L.printers || [];
  if (!ps.length) return adm() ? '<div class="info">Past op: <a href="#/settings/printers">voeg je printers toe</a></div>' : '';
  const mp = multiPlate(m);
  const one = p => {
    const f = fits(m, p);
    if (f === null) return `<span class="dim">? ${esc(p.name)}</span>`;
    if (f) return `<span class="ok">✓ ${esc(p.name)}</span>`;
    const bad = mp && m.pdims.find(x => !fitsDims(x.dims, p));
    return `<span class="err">✗ ${esc(p.name)}${bad ? ` (plaat ${bad.id} te groot)` : ''}</span>`;
  };
  return '<div class="info">Past op' + (mp ? ' (per plaat)' : '') + ': ' + ps.map(one).join(' · ') + (mp && !(m.pdims && m.pdims.length) ? ' <span class="dim">— platen worden nog berekend</span>' : '') + '</div>';
}
const logLines = m => {
  const lg = L.logs[m.id];
  if (lg === undefined) return 'Laden…';
  return lg.length ? lg.slice(0, 5).map(x => `<div>${x.result === 'ok' ? '<span class="ok">✓</span>' : '<span class="err">✗</span>'} ${fdate(x.ts)}${x.printer ? ' · ' + esc(x.printer) : ''}${x.plate ? ' · plaat ' + x.plate : ''}${x.grams ? ' · ' + x.grams + ' g' : ''}${x.spool ? ' van ' + esc(x.spool) : ''}${x.notes ? '<br><span class="dim">' + esc(x.notes) + '</span>' : ''} <span class="x" data-delprint="${x.id}" title="Verwijder deze regel (verbruik dat al in Spoolman is afgetrokken blijft staan)">×</span></div>`).join('') + (lg.length > 5 ? `<div class="dim">… en ${lg.length - 5} eerdere</div>` : '') : '<span class="dim">Nog niets gelogd.</span>';
};
const logCount = m => { const lg = L.logs[m.id] || []; return `${lg.filter(x => x.result === 'ok').length} gelukt, ${lg.filter(x => x.result === 'failed').length} mislukt`; };
function logHTML(m) {
  const pl = (m.info || {}).plates || [];
  return `<b>Printlogboek</b> <span class="dim" id="vlogcnt">(${logCount(m)})</span>
<div class="info" id="vlogs">${logLines(m)}</div>
<button id="vlogbtn">+ Print loggen</button>
<div id="vlogform" style="display:none"><div class="f"><small>Resultaat</small><select id="lr"><option value="ok">Gelukt</option><option value="failed">Mislukt</option></select></div>
<div class="f"><small>Printer</small><select id="lp"><option value="">Onbekend</option>${(L.printers || []).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></div>
${pl.length > 1 ? `<div class="f"><small>Plaat</small><select id="lpl"><option value="">Alle platen</option>${pl.map(p => `<option value="${p.id}">${esc(p.name || 'Plaat ' + p.id)}</option>`).join('')}</select></div>` : ''}
<div class="f"><small>Filamentverbruik (gram)</small><input id="lg" type="number" min="0" step="0.1" value="${(m.info || {}).filament_g || ''}"></div>
${L.d.spoolman ? '<div class="f"><small>Spoolman: verbruik aftrekken van spoel</small><select id="ls"><option value="">Niet aftrekken</option></select></div>' : ''}
<div class="f"><small>Notitie</small><input id="ln" placeholder="bijv. 0.2 mm, 15% infill"></div>
<button class="p" id="lsave">Opslaan in logboek</button></div>`;
}
function bbHTML(m) {
  if (!L.d.bambuddy || !['3mf', 'gcode', 'stl'].includes(m.ext)) return '';
  return `<button id="vbbbtn" title="Het model naar Bambuddy sturen">↗ Naar Bambuddy…</button>
<div id="vbbform" style="display:none"><div class="f"><small>Printer (voor de wachtrij)</small><select id="bbp"><option value="">Laden…</option></select></div><div id="bbcol" class="dim" style="margin:0 0 8px"></div>
<div class="row"><button id="bblib" title="Alleen in de bibliotheek van Bambuddy zetten">In bibliotheek zetten</button><button class="p" id="bbq" title="In de wachtrij van Bambuddy zetten; starten doe je daar zelf" ${m.ext === 'stl' ? 'disabled' : ''}>In wachtrij zetten</button></div>
<small class="dim">Er wordt niets gestart. Starten doe je zelf in Bambuddy.${m.ext === 'stl' ? ' De wachtrij van Bambuddy neemt alleen geslicede bestanden (.gcode of .gcode.3mf) aan.' : ''}</small></div>`;
}
async function openBbForm() {
  const f = $('#vbbform'); f.style.display = f.style.display === 'none' ? '' : 'none';
  if (f.style.display === 'none') return;
  try {
    const r = await api('/api/bambuddy/status');
    if (!r.ok) { $('#bbp').innerHTML = '<option value="">Niet beschikbaar</option>'; return toast(r.error || 'Bambuddy is niet ingesteld', 'err'); }
    $('#bbp').innerHTML = '<option value="">Kies een printer…</option>' + r.printers.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  } catch (e) { toast(e.message, 'err'); }
}
async function showBbColors(pid) {  // de kleuren die nu echt in de gekozen printer zitten (AMS en externe spoel)
  const box = $('#bbcol'); if (!box) return;
  if (!pid) { box.innerHTML = ''; return; }
  box.textContent = 'Laden…';
  try {
    const r = await api('/api/bambuddy/colors?printer=' + encodeURIComponent(pid)), sl = ((r.printers || [])[0] || {}).slots || [];
    box.innerHTML = !r.ok ? esc(r.error || '') : !sl.length ? 'Geen spoelen gevonden in deze printer.' : 'Nu geladen: ' + sl.map(x => `<span title="${esc(x.slot)}" style="white-space:nowrap;margin-right:10px"><span style="display:inline-block;width:12px;height:12px;border-radius:3px;border:1px solid #fff4;background:${/^#[0-9A-F]{6}$/.test(x.hex) ? x.hex : '#888'};vertical-align:-1px"></span> ${esc(x.name)} ${esc(x.material)}</span>`).join('');
  } catch (e) { box.textContent = ''; }
}
async function sendToBambuddy(action) {
  const pid = $('#bbp').value;
  if (action === 'queue' && !pid) return toast('Kies eerst een printer', 'info');
  const m = cur();
  if (!confirm(action === 'queue' ? `"${label(m)}" naar Bambuddy sturen en in de wachtrij van de gekozen printer zetten?\nEr wordt niets gestart.` : `"${label(m)}" naar de bibliotheek van Bambuddy sturen?`)) return;
  const r = await api(`/api/models/${m.id}/bambuddy`, 'POST', {action, printer_id: pid ? +pid : null});
  toast(action === 'queue' ? `In de wachtrij van Bambuddy gezet (#${r.queue_item_id}${r.queue_status ? ', status: ' + r.queue_status : ''})` : r.duplicate ? 'Verstuurd (Bambuddy had dit bestand al)' : 'In de bibliotheek van Bambuddy gezet');
}
async function loadLogs(id) {
  L.logs[id] = await api(`/api/models/${id}/prints`);
  if (openId === id && $('#vlogs')) { $('#vlogs').innerHTML = logLines(cur()); $('#vlogcnt').textContent = `(${logCount(cur())})`; }
}
async function openLogForm() {
  const f = $('#vlogform'); f.style.display = f.style.display === 'none' ? '' : 'none';
  if (f.style.display === 'none' || !L.d.spoolman || !$('#ls') || $('#ls').options.length > 1) return;
  try {
    L.spools = await api('/api/spoolman/spools');
    const types = (((cur().info || {}).filament) || '').toLowerCase().split(/[,;]\s*/).filter(Boolean);
    const fit = s => types.includes(s.material.toLowerCase()) ? 0 : 1;
    $('#ls').innerHTML = '<option value="">Niet aftrekken</option>' + [...L.spools].sort((a, b) => fit(a) - fit(b)).map(s => `<option value="${s.id}">${esc(s.label)}${s.material ? ' (' + esc(s.material) + ')' : ''}${s.remaining != null ? ' — ' + Math.round(s.remaining) + ' g over' : ''}</option>`).join('');
  } catch (e) { toast(e.message, 'err'); }
}
function sideHTMLViewer(m) {  // alleen-lezen weergave voor gasten
  const cats = m.cats.map(id => `<span class="chip">${esc((L.d.categories.find(c => c.id === id) || {}).name)}</span>`).join('') || '<i class="dim">Geen categorie</i>';
  const src = /^https?:\/\//i.test(m.source_url) ? `<a class="btn sm" target="_blank" rel="noopener noreferrer" href="${esc(m.source_url)}">${ICON_EXT} Bron openen</a>` : '';
  return `<h3 style="margin:0">${esc(label(m))}</h3>
<div class="info">${dimTxt(m)}${m.tris ? ' · ' + m.tris.toLocaleString(I18N.LOC) + ' driehoeken' : ''} · ${fsize(m.size)}${m.container ? `<br>In zip: <b>${esc(m.container)}</b>` : ''}<br><span class="dim">${esc(m.path)}</span>${m.owner ? `<br>Door: <b>${esc(m.owner)}</b>${m.mine ? ' (jij)' : ''}` : ''}${m.hidden ? '<br><span class="warn">Verborgen voor andere leerlingen</span>' : ''}</div>
${m.manage ? `<label><input type="checkbox" id="vshare" ${m.shared ? 'checked' : ''}> Delen met andere leerlingen en scholen</label>` : ''}
${src}${fitHTML(m)}${infoHTML(m)}
<b>Categorieën</b><div class="chips" style="padding:0">${cats}</div>
<div class="row" style="margin-top:auto">${ME.can_download ? `<a class="btn" href="/api/file/${m.id}" download>⬇ Download</a><button id="vslic" title="De slicer haalt het bestand zelf op via een tijdelijke link">▶ Openen in ${esc(L.d.slicer.name)}</button>` : '<span class="dim">Downloaden is voor jouw account niet ingeschakeld.</span>'}<button id="vx">Sluiten</button></div>
<div class="row">${ME.school ? '<button id="vreq" class="p" title="Vraag een medewerker om dit model te printen">🖨 Print aanvragen</button>' : ''}${m.mine ? '' : '<button id="vrep" title="Meld dit model bij een medewerker">⚑ Melden</button>'}${staff() && m.manage ? `<button id="vhide">${m.hidden ? 'Weer tonen' : 'Verbergen'}</button>` : ''}${m.manage ? '<button id="vdel" class="d">🗑 Verwijderen</button>' : ''}</div>`;
}
function sideHTML(m) {
  const avail = L.d.categories.filter(c => !m.cats.includes(c.id));
  return `<div class="row"><button id="vfav">${m.favorite ? '★ Favoriet' : '☆ Favoriet'}</button></div>
<div class="f"><small>Weergavenaam (database)</small><input id="vd" value="${esc(m.display)}" placeholder="${esc(m.name)}"></div>
<div class="f"><small>Bestandsnaam (op schijf)</small><div class="row"><input id="vf" value="${esc(m.name)}" ${m.can_rename ? '' : 'disabled title="' + (m.container ? 'Dit model zit in een zip: alleen de weergavenaam kan worden gewijzigd' : 'Hernoemen staat uit voor deze root folder (Instellingen → Mediabeheer)') + '"'}><span class="dim">.${esc(m.ext)}</span></div></div>
<div class="f"><small>Bron (link)</small><div class="row"><input id="vsrc" value="${esc(m.source_url)}" placeholder="https://www.printables.com/model/…"><a id="vsrcl" class="btn" target="_blank" rel="noopener noreferrer" ${/^https?:\/\//i.test(m.source_url) ? `href="${esc(m.source_url)}"` : 'hidden'} title="Bron openen" aria-label="Bron openen">${ICON_EXT}</a></div></div>
<div class="f"><small>Printstatus</small><select id="vprn"><option value="" ${m.printed === '' ? 'selected' : ''}>Onbekend</option><option value="toprint" ${m.printed === 'toprint' ? 'selected' : ''}>Te printen</option><option value="printed" ${m.printed === 'printed' ? 'selected' : ''}>Geprint</option></select></div>
<div class="f"><small>Notities</small><textarea id="vnotes" rows="4" style="width:100%">${esc(m.notes)}</textarea></div>
<button class="p" id="vs">Opslaan</button>
<div class="info">${dimTxt(m)}${m.tris ? ' · ' + m.tris.toLocaleString(I18N.LOC) + ' driehoeken' : ''} · ${fsize(m.size)}<br>Toegevoegd: ${fdate(m.added)}<br>${m.container ? `In zip: <b>${esc(m.container)}</b><br>` : ''}<span class="dim">${esc(m.path)}</span></div>
${fitHTML(m)}${infoHTML(m)}
<b>Categorieën van dit model</b>
<div class="chips" style="padding:0">${m.cats.map(id => `<span class="chip">${esc((L.d.categories.find(c => c.id === id) || {}).name)}<span class="x" data-rm="${id}" title="Verwijder van dit model">×</span></span>`).join('') || '<i class="dim">Nog geen categorie</i>'}</div>
<div class="f"><small>Categorie toevoegen</small><div class="row"><select id="vsel"><option value="">Kies een categorie…</option>${avail.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}<option value="__new">+ Nieuwe categorie…</option></select><button id="vadd">Toevoegen</button></div>
<input id="vnew" placeholder="Naam nieuwe categorie (Enter)" style="display:none;margin-top:6px"></div>
${logHTML(m)}
${bbHTML(m)}
<div class="row" style="margin-top:auto"><button id="vslic" title="De slicer haalt het bestand zelf op via een tijdelijke link">▶ Openen in ${esc(L.d.slicer.name)}</button>${L.d.local ? '<button id="vopen" title="Met het standaardprogramma van je computer">Openen met standaardprogramma</button>' : ''}</div>
<div class="row"><button id="vsnap" title="Draai het model en gebruik de huidige weergave als thumbnail">📷 Weergave als thumbnail</button></div>
<div class="row"><button id="vre" title="Terug naar de automatische thumbnail">Thumbnail opnieuw</button><a class="btn" href="/api/file/${m.id}" download>⬇ Download</a><button id="vx">Sluiten</button></div>`;
}
function openModal(id) {
  openId = id;
  $('#modal').innerHTML = '<div class="back"><div class="box"><div id="vwrap"><div id="ptabs"></div><div id="viewer">Laden…</div></div><div class="side" id="side"></div></div></div>';
  $('#modal').style.display = 'block'; $('#side').innerHTML = adm() ? sideHTML(cur()) : sideHTMLViewer(cur());
  $('#ptabs').innerHTML = plateTabs(cur(), 0);
  startViewer($('#viewer'), cur());
  if (adm()) loadLogs(id).catch(() => {});
}
function plateTabs(m, active) {  // tabbladen voor 3MF's met meerdere platen (Bambu Studio / OrcaSlicer)
  const pl = (m.info || {}).plates;
  if (!pl || pl.length < 2) return '';
  return [{id: 0, name: 'Alles'}, ...pl.map(p => ({id: p.id, name: p.name || 'Plaat ' + p.id}))].map(p => `<button data-plate="${p.id}" class="${p.id === active ? 'p' : ''}">${esc(p.name)}</button>`).join('');
}
function closeModal() {
  openId = null; if (vw) { vw.stop = true; vw.r && vw.r.dispose(); vw = null; }
  $('#modal').style.display = 'none'; $('#modal').innerHTML = '';
}
async function startViewer(box, m, plate = 0) {
  const v = vw = {stop: false};
  try {
    if (!adm() && !ME.can_download) throw new Error('je account mag geen 3D-weergave of downloads gebruiken');
    const THREE = await import('three');
    const {OrbitControls} = await import('three/addons/OrbitControls.js');
    const {STLLoader} = await import('three/addons/STLLoader.js');
    const mr = await fetch(`/api/mesh/${m.id}.stl${plate ? '?plate=' + plate : ''}`);
    if (!mr.ok) throw new Error((await mr.text().catch(() => '')) || `fout ${mr.status}`);
    const g = new STLLoader().parse(await mr.arrayBuffer());
    if (v.stop) return;
    g.center(); g.computeBoundingBox();
    const s = g.boundingBox.getSize(new THREE.Vector3());
    const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({color: 0xb0b8c4, roughness: .6, metalness: .1}));
    mesh.rotation.x = -Math.PI / 2; mesh.scale.setScalar(1 / Math.max(s.x, s.y, s.z));
    const sc = new THREE.Scene(); sc.add(new THREE.HemisphereLight(0xffffff, 0x444455, 1.6));
    const d = new THREE.DirectionalLight(0xffffff, 2.2); d.position.set(2, 3, 2); sc.add(d, mesh);
    box.textContent = '';
    const r = v.r = new THREE.WebGLRenderer({antialias: true});
    r.setPixelRatio(devicePixelRatio); r.setSize(box.clientWidth, box.clientHeight); r.setClearColor(0x2a2f3a); box.appendChild(r.domElement);
    const cam = new THREE.PerspectiveCamera(35, box.clientWidth / box.clientHeight, .05, 50);
    cam.position.set(1.4, 1, 1.6).multiplyScalar(1.4); cam.lookAt(0, 0, 0);
    const oc = new OrbitControls(cam, r.domElement); oc.enableDamping = true;
    v.snap = () => {  // vierkant uitsnede van de huidige weergave
      r.render(sc, cam);
      const c = r.domElement, s = Math.min(c.width, c.height), o = document.createElement('canvas');
      o.width = o.height = 512; o.getContext('2d').drawImage(c, (c.width - s) / 2, (c.height - s) / 2, s, s, 0, 0, 512, 512);
      return o.toDataURL('image/png');
    };
    (function loop() { if (v.stop) return; oc.update(); r.render(sc, cam); requestAnimationFrame(loop); })();
  } catch (e) { if (!v.stop) box.innerHTML = (m.status === 'ok' ? `<div style="text-align:center"><img src="/api/thumb/${m.id}.png?v=${m.thumb_at}" style="max-width:90%;max-height:60vh">` : '<div style="text-align:center">') + `<p class="dim">Geen 3D-weergave voor dit bestand (${esc(e.message)})</p></div>`; }
}
const modalDone = async msg => { await reloadLib(); if (openId) $('#side').innerHTML = sideHTML(cur()); toast(msg); };
$('#modal').onclick = run(async e => {
  const t = e.target;
  if (t.classList.contains('back') || t.id === 'vx') return closeModal();
  if (t.dataset.rm) { await api('/api/assign', 'POST', {model_ids: [openId], category_id: +t.dataset.rm, action: 'remove'}); return modalDone('Categorie verwijderd van dit model'); }
  if (t.id === 'vre') { await api(`/api/models/${openId}/regen`, 'POST'); return modalDone('Thumbnail wordt opnieuw gemaakt'); }
  if (t.dataset.plate !== undefined) {
    const pl = +t.dataset.plate;
    if (vw) { vw.stop = true; vw.r && vw.r.dispose(); }
    $('#viewer').textContent = 'Laden…'; $('#ptabs').innerHTML = plateTabs(cur(), pl); startViewer($('#viewer'), cur(), pl); return;
  }
  if (t.id === 'vslic') {
    const r = await api(`/api/models/${openId}/link`, 'POST');
    location.href = r.scheme + encodeURIComponent(location.origin + r.path);
    return toast(`Link naar ${r.slicer} verstuurd. Opent het niet? Controleer of ${r.slicer} is geïnstalleerd, of download het bestand en open het zelf.`, 'info');
  }
  if (t.id === 'vshare') { await api(`/api/models/${openId}/share`, 'POST', {shared: t.checked}); await reloadLib(); return toast(t.checked ? 'Dit model is nu gedeeld' : 'Dit model is nu privé'); }
  if (t.id === 'vreq') return openRequest(cur());
  if (t.id === 'vrep') { const reason = prompt('Waarom meld je dit model?'); if (!reason || !reason.trim()) return; await api(`/api/models/${openId}/report`, 'POST', {reason}); return toast('Bedankt, een medewerker kijkt ernaar'); }
  if (t.id === 'vhide') { await api(`/api/models/${openId}/hide`, 'POST', {hidden: !cur().hidden}); await reloadLib(); $('#side').innerHTML = sideHTMLViewer(cur()); return toast('Opgeslagen'); }
  if (t.id === 'vdel') { if (!confirm('Dit model verwijderen? Het gaat naar de prullenbak van de beheerder.')) return; await api(`/api/models/${openId}/delete`, 'POST'); closeModal(); await reloadLib(); return toast('Model verwijderd'); }
  if (t.id === 'vopen') { await api(`/api/models/${openId}/open`, 'POST'); return toast('Geopend met het standaardprogramma'); }
  if (t.id === 'vlogbtn') return openLogForm();
  if (t.id === 'vbbbtn') return openBbForm();
  if (t.id === 'bblib') return sendToBambuddy('library');
  if (t.id === 'bbq') return sendToBambuddy('queue');
  if (t.dataset.delprint) {
    if (!confirm('Deze logregel verwijderen? Verbruik dat al in Spoolman is afgetrokken blijft daar staan.')) return;
    await api('/api/prints/' + t.dataset.delprint, 'DELETE'); await loadLogs(openId); await reloadLib(); return toast('Logregel verwijderd');
  }
  if (t.id === 'lsave') {
    const m = cur(), body = {result: $('#lr').value, printer_id: $('#lp').value || null, plate: $('#lpl') ? $('#lpl').value || null : null, grams: $('#lg').value || null, notes: $('#ln').value.trim()};
    if ($('#ls') && $('#ls').value) { body.spool_id = +$('#ls').value; body.deduct = true; body.spool = $('#ls').selectedOptions[0].textContent.replace(/ \(.*$/, ''); if (!body.grams) return toast('Vul het filamentverbruik in om het in Spoolman af te trekken', 'info'); }
    const r = await api(`/api/models/${openId}/prints`, 'POST', body);
    await loadLogs(openId); await reloadLib(); if (body.result === 'ok' && $('#vprn')) $('#vprn').value = 'printed';
    $('#vlogform').style.display = 'none'; $('#ln').value = '';
    return toast(r.deducted ? `Print gelogd en ${body.grams} g afgetrokken in Spoolman` : 'Print gelogd');
  }
  if (t.id === 'vadd') return addCat();
  if (t.id === 'vtitle') { $('#vd').value = cur().info.title; return toast('Titel ingevuld, klik op Namen opslaan', 'info'); }
  if (t.id === 'vs') {
    const m = cur(), body = {}, val = id => $(id).value.trim();
    if (val('#vd') !== m.display) body.display = val('#vd');
    if (!$('#vf').disabled && val('#vf') !== m.name) body.filename = val('#vf');
    if (val('#vsrc') !== m.source_url) body.source_url = val('#vsrc');
    if ($('#vprn').value !== m.printed) body.printed = $('#vprn').value;
    if (val('#vnotes') !== m.notes) body.notes = val('#vnotes');
    if (!Object.keys(body).length) return toast('Geen wijzigingen om op te slaan', 'info');
    await api('/api/models/' + openId, 'POST', body);
    return modalDone(body.filename !== undefined ? 'Opgeslagen en bestand hernoemd op schijf' : 'Opgeslagen');
  }
  if (t.id === 'vfav') { await api('/api/models/' + openId, 'POST', {favorite: !cur().favorite}); return modalDone(cur().favorite ? 'Favoriet weggehaald' : 'Toegevoegd aan favorieten'); }
  if (t.id === 'vsnap') {
    if (!vw || !vw.snap) return toast('De 3D-weergave is nog niet geladen', 'info');
    await api(`/api/models/${openId}/thumb`, 'POST', {data: vw.snap()});
    return modalDone('Thumbnail vervangen door deze weergave');
  }
});
$('#modal').oninput = e => {  // bronlink meteen klikbaar zodra er een geldige link staat
  if (e.target.id !== 'vsrc') return;
  const v = e.target.value.trim(), a = $('#vsrcl');
  if (/^https?:\/\//i.test(v)) { a.href = v; a.hidden = false; } else { a.removeAttribute('href'); a.hidden = true; }
};
$('#modal').onchange = e => { if (e.target.id === 'bbp') showBbColors(e.target.value); if (e.target.id === 'vsel') { const n = e.target.value === '__new'; $('#vnew').style.display = n ? '' : 'none'; if (n) $('#vnew').focus(); } };
$('#modal').onkeydown = run(async e => { if (e.key === 'Enter' && e.target.id === 'vnew') await addCat(); if (e.key === 'Enter' && (e.target.id === 'vd' || e.target.id === 'vf')) $('#vs').click(); if (e.key === 'Escape') closeModal(); });
async function addCat() {
  const v = $('#vsel').value; let id;
  if (v === '__new') { const name = $('#vnew').value.trim(); if (!name) return toast('Vul een naam in voor de nieuwe categorie', 'info'); id = (await api('/api/categories', 'POST', {name})).id; }
  else if (v) id = +v; else return toast('Kies eerst een categorie', 'info');
  await api('/api/assign', 'POST', {model_ids: [openId], category_id: id, action: 'add'});
  await modalDone(v === '__new' ? 'Nieuwe categorie aangemaakt en toegevoegd' : 'Categorie toegevoegd');
}

// ------------------------------------------------------------ activiteit & gewenst
V['activity/queue'] = async () => {
  $('#title').textContent = 'Activiteit — Wachtrij';
  const load = run(async () => {
    const q = await api('/api/queue');
    $('#tools').innerHTML = `<button id="pz">${q.paused ? '▶ Hervatten' : '⏸ Pauzeren'}</button>`;
    $('#pz').onclick = run(async () => { await api('/api/queue/pause', 'POST', {paused: !q.paused}); toast(q.paused ? 'Wachtrij hervat' : 'Wachtrij gepauzeerd', 'info'); load(); });
    $('#view').innerHTML = `${q.paused ? '<p class="warn">⏸ De wachtrij staat gepauzeerd: thumbnails en vergelijkingen wachten.</p>' : ''}<p>${q.current ? `⚙ Bezig met: <b>${esc(q.current.name)}</b> (${q.current.secs}s)` : 'Niets bezig.'} &nbsp; Wachtend: <b>${q.pending}</b> · Mislukt: <b>${q.failed}</b></p>`
      + (q.items.length ? tbl(['Model', 'Formaat', 'Toegevoegd'], q.items.map(m => `<tr><td>${esc(m.name)}</td><td>${esc(m.ext)}</td><td>${fdate(m.added)}</td></tr>`)) : '')
      + (q.pending > q.items.length + (q.current ? 1 : 0) ? '<p class="dim">… en meer</p>' : '');
  });
  onRev = load; await load();
};
V['activity/history'] = async () => {
  $('#title').textContent = 'Activiteit — Geschiedenis';
  const load = run(async () => {
    const h = await api('/api/history');
    $('#view').innerHTML = h.length ? tbl(['Tijd', 'Gebeurtenis', 'Details'], h.map(x => `<tr><td class="dim">${fdate(x.ts)}</td><td class="${x.event === 'Mislukt' || x.event === 'Verwijderd' ? 'err' : x.event === 'Toegevoegd' ? 'ok' : ''}">${esc(x.event)}</td><td>${esc(x.message)}</td></tr>`)) : '<p class="empty">Nog geen activiteit.</p>';
  });
  onRev = load; await load();
};
V.wanted = async () => {
  $('#title').textContent = 'Gewenst — modellen zonder thumbnail';
  const load = run(async () => {
    const wd = await api('/api/wanted'), w = wd.items;
    $('#tools').innerHTML = w.some(m => m.status === 'failed') ? '<button id="rall" class="p">Alles opnieuw proberen</button>' : '';
    if ($('#rall')) $('#rall').onclick = run(async () => { await api('/api/wanted/retry', 'POST', {}); toast('Opnieuw in de wachtrij gezet'); });
    $('#view').innerHTML = w.length ? tbl(['Model', 'Reden', 'Pad', ''], w.map(m => `<tr><td>${esc(m.name)}.${esc(m.ext)}</td><td class="${m.status === 'failed' ? 'err' : 'dim'}">${esc(m.error)}</td><td class="dim">${esc(m.path)}</td><td>${m.status === 'failed' ? `<button data-retry="${m.id}">Opnieuw</button>` : ''}</td></tr>`)) : '<p class="empty">✓ Geen mislukte thumbnails.</p>';
    if (wd.unsupported) $('#view').innerHTML += `<p class="dim">${wd.unsupported} bestand(en) staan alleen in de bibliotheek, zonder preview (formaat zonder preview-ondersteuning of geen ingebedde afbeelding). Zie het filter "Zonder preview" in de bibliotheek.</p>`;
  });
  $('#view').onclick = run(async e => { if (e.target.dataset.retry) { await api('/api/wanted/retry', 'POST', {ids: [e.target.dataset.retry]}); toast('Opnieuw in de wachtrij gezet'); } });
  onRev = load; await load();
};

V.duplicates = async () => {
  $('#title').textContent = 'Duplicaten';
  const ids = g => g.map(m => m.id).join(',');
  const pick = new Set(); let cur = {exact: [], mesh: []};
  const dbar = () => (cur.exact.length || cur.mesh.length) ? `<div id="dbar"><button data-act="allcopies" title="Kiest in elke groep identieke bestanden alles behalve het oudste bestand">☑ Alle kopieën kiezen (oudste blijft)</button>${pick.size ? ` <button class="d" data-act="trashsel">${pick.size} naar prullenbak</button> <button data-act="clearsel">Wis selectie</button>` : ''}</div>` : '';
  const grp = (g, kind, ign) => `<h3>${kind === 'exact' ? 'Identieke bestanden' : kind === 'ignored' ? 'Genegeerde groep' : 'Zelfde mesh'} · ${g.length} stuks${kind === 'exact' ? ` · ${fsize(g[0].size)} per bestand` : ''} <button class="sm" data-ign="${ids(g)}" data-on="${ign ? 0 : 1}">${ign ? 'Niet meer negeren' : 'Negeren'}</button></h3>`
    + tbl(['', '', 'Naam', 'Pad', 'Grootte', 'Toegevoegd', ''], g.map((m, j) => `<tr><td>${ign || !m.can_write ? '' : `<input type="checkbox" class="dsel" data-id="${m.id}" ${pick.has(m.id) ? 'checked' : ''}>`}</td><td>${thumb(m, 'mini')}</td><td>${esc(m.name)}.${esc(m.ext)}${j === 0 ? ' <span class="dim">(oudste)</span>' : ''}</td><td class="dim">${esc(m.path)}</td><td>${fsize(m.size)}</td><td>${fdate(m.added)}</td><td><button class="d" data-trash="${m.id}" data-p="${esc(m.path)}" ${m.can_write ? '' : 'disabled title="Verplaatsen staat uit voor deze root folder (Instellingen → Mediabeheer)"'}>Naar prullenbak</button></td></tr>`));
  const load = run(async () => {
    const d = await api('/api/duplicates'); cur = d;
    const present = new Set([...d.exact, ...d.mesh].flat().map(m => m.id)); [...pick].forEach(i => present.has(i) || pick.delete(i));
    $('#view').innerHTML = dbar() + `<p class="dim">${d.exact.length ? `<b>${d.exact.length}</b> groep(en) identieke bestanden, samen <b>${fsize(d.wasted)}</b> extra opslag. ` : ''}${d.waiting ? `Nog ${d.waiting} bestand(en) worden vergeleken… ` : ''}Bestanden gaan naar de map <code>.prullenbak</code> in je root folder; er wordt niets definitief gewist. Met Negeren haal je een groep uit de lijst zonder iets te verplaatsen.</p>`
      + (d.exact.length || d.mesh.length ? d.exact.map(g => grp(g, 'exact')).join('')
        + (d.mesh.length ? '<h3 style="margin-top:28px">Mogelijk dezelfde mesh</h3><p class="dim">Zelfde aantal driehoeken en afmetingen, maar niet byte-voor-byte gelijk (bijv. STL en 3MF van hetzelfde model). Controleer zelf of het echt dubbelen zijn.</p>' + d.mesh.map(g => grp(g, 'mesh')).join('') : '')
        : '<p class="empty">✓ Geen dubbele bestanden gevonden.</p>')
      + (d.ignored.length ? `<details style="margin-top:28px"><summary>Genegeerd · ${d.ignored.length} groep(en)</summary><p class="dim">Deze groepen staan niet meer in de lijst en niet in de teller. Komt er een kopie bij, dan verschijnt de groep weer.</p>${d.ignored.map(g => grp(g, 'ignored', true)).join('')}</details>` : '');
  });
  $('#view').onclick = run(async e => {
    if (e.target.dataset.ign) { await api('/api/duplicates/ignore', 'POST', {ids: e.target.dataset.ign.split(',').map(Number), ignore: e.target.dataset.on === '1'}); toast(e.target.dataset.on === '1' ? 'Groep genegeerd' : 'Groep staat weer in de lijst'); await load(); return; }
    const act = e.target.dataset.act;
    if (act === 'allcopies') { cur.exact.forEach(g => g.slice(1).forEach(m => m.can_write && pick.add(m.id))); return load(); }
    if (act === 'clearsel') { pick.clear(); return load(); }
    if (act === 'trashsel') {
      if (!confirm(`${pick.size} bestanden naar de map .prullenbak in hun root folder verplaatsen?\n\nVan elke groep blijft altijd minstens één kopie staan.`)) return;
      const r = await api('/api/models/trash', 'POST', {ids: [...pick]}); pick.clear();
      toast(r.failed.length ? `${r.done} verplaatst, ${r.failed.length} niet: ${r.failed[0].error}` : `${r.done} naar .prullenbak verplaatst`, r.failed.length ? 'err' : undefined); return load();
    }
    if (e.target.classList.contains('dsel')) { const i = +e.target.dataset.id; e.target.checked ? pick.add(i) : pick.delete(i); const b = $('#dbar'); if (b) b.outerHTML = dbar(); return; }
    const id = e.target.dataset.trash; if (!id) return;
    if (!confirm('Dit bestand naar de map .prullenbak in je root folder verplaatsen?\n\n' + e.target.dataset.p)) return;
    await api(`/api/models/${id}/trash`, 'POST'); toast('Verplaatst naar .prullenbak'); await load();
  });
  onRev = load; await load();
};

// ------------------------------------------------------------ instellingen
function pickFolder(hidden) {  // hidden: ook mappen met een punt tonen (voor de back-upmap)
  return new Promise(res => {
    const m = $('#modal'), prev = m.onclick;
    m.innerHTML = '<div class="back"><div class="pick"><b>Kies een map</b><div class="row"><input id="fp" placeholder="Typ of plak een pad, bijv. D:&#92;3D of &#92;&#92;nas&#92;modellen"><button id="fgo">Ga</button></div><div id="func" class="dim"></div><ul id="fl"></ul><div class="row"><button class="p" id="fok">Kies deze map</button><button id="fcx">Annuleren</button></div></div></div>';
    m.style.display = 'block';
    let path = '';
    const go = run(async p => {
      const d = await api('/api/fs?' + (hidden ? 'hidden=1&' : '') + (p ? 'path=' + encodeURIComponent(p) : '')); path = d.path; $('#fp').value = d.path;
      $('#fl').innerHTML = (d.parent !== null && d.path ? `<li data-p="${esc(d.parent)}">⬑ ..</li>` : '') + (d.dirs.map(x => `<li data-p="${esc(x.path)}">📁 ${esc(x.name)}${x.unc ? ` <span class="dim">→ ${esc(x.unc)}</span>` : ''}</li>`).join('') || '<li class="dim">(geen submappen)</li>');
      $('#func').innerHTML = d.unc ? `Netwerkpad: <code>${esc(d.unc)}</code> <button id="funcb" data-u="${esc(d.unc)}">Dit netwerkpad kiezen</button>`
        : !d.path ? 'Voor een netwerkshare zonder stationsletter: typ hierboven het pad (server én share, bijv. &#92;&#92;nas&#92;modellen) en kies Ga.' : '';
    });
    const done = v => { m.style.display = 'none'; m.innerHTML = ''; m.onclick = prev; res(v); };
    m.onclick = e => {
      const li = e.target.closest('li[data-p]'); if (li) go(li.dataset.p);
      if (e.target.id === 'fgo') go($('#fp').value);
      if (e.target.id === 'funcb') done(e.target.dataset.u);
      if (e.target.id === 'fok') { if (!path) return toast('Open eerst een map of typ een pad', 'info'); done(path); }
      if (e.target.id === 'fcx' || e.target.classList.contains('back')) done(null);
    };
    $('#fp').onkeydown = e => { if (e.key === 'Enter') go(e.target.value); };
    go('');
  });
}
V['settings/media'] = async () => {
  $('#title').textContent = 'Instellingen — Mediabeheer';
  const load = run(async () => {
    const [roots, s] = await Promise.all([api('/api/roots'), api('/api/settings')]);
    $('#view').innerHTML = `<h3>Root folders</h3><p class="dim">Mappen met 3D-modellen. Elke root wordt gescand en live in de gaten gehouden; nieuwe bestanden komen automatisch in de bibliotheek met een thumbnail. Standaard wordt er alleen geïndexeerd: hernoemen en verplaatsen (ook naar de prullenbak) zet je per root folder aan.</p>`
      + (roots.length ? tbl(['Pad', 'Status', 'Vrije ruimte', 'Modellen', 'Wachter', 'Bestanden wijzigen', ''], roots.map(r => `<tr><td>${esc(r.path)}</td><td class="${r.ok ? 'ok' : 'err'}">${r.ok ? (r.writable ? '✓ bereikbaar' : '✓ alleen-lezen') : '✗ niet bereikbaar'}</td><td>${fsize(r.free)}</td><td>${r.count}</td><td><label><input type="checkbox" data-w="${r.id}" ${r.watch ? 'checked' : ''}> ${r.live ? 'live' : r.watch ? 'alleen scannen' : 'uit'}</label></td><td><label><input type="checkbox" data-aw="${r.id}" ${r.allow_write ? 'checked' : ''}> Toestaan</label><br><small class="${r.allow_write ? 'warn' : 'dim'}">${r.allow_write ? 'Bestanden mogen hernoemd en naar de prullenbak verplaatst worden' : 'Alleen lezen: Modelarr verandert niets aan je bestanden'}</small></td><td><button data-mv="${r.id}" data-p="${esc(r.path)}">Pad wijzigen</button> <button class="d" data-del="${r.id}">Verwijderen</button></td></tr>`)) : '<p class="empty">Nog geen root folders.</p>')
      + `<div class="row" style="max-width:720px"><button class="p" id="addroot">+ Map kiezen…</button><input id="newroot" placeholder="of typ/plak een pad, bijv. D:&#92;3D of &#92;&#92;nas&#92;modellen"><button id="addtyped">Toevoegen</button></div>
<h3>Scannen &amp; thumbnails</h3><div class="form">
<label>Scaninterval (minuten)</label><input type="number" id="s1" min="1" value="${s.scan_interval}"><small>Extra vangnet naast de live wachter, nodig voor NFS/SMB-shares.</small>
<label>Minimale bestandsleeftijd (sec)</label><input type="number" id="s2" min="0" value="${s.min_age}"><small>Bestanden die nog gekopieerd worden worden pas daarna opgenomen.</small>
<label>Bestandsextensies</label><input id="s3" value="${esc(s.extensions)}"><small>Komma-gescheiden. 3D-preview: stl, 3mf, obj, ply, glb, gltf. Afbeelding uit het bestand: fcstd, gcode, gco. De rest wordt alleen geïndexeerd. Modellen in zip-bestanden worden apart doorzocht (zie hieronder).</small>
<label>Thumbnail-grootte (px)</label><input type="number" id="s4" min="128" max="1024" value="${s.thumb_size}"><small>Bij wijzigen worden alle thumbnails automatisch opnieuw gemaakt.</small>
<label>Thumbnails van 3MF / G-code</label><select id="s7"><option value="embedded" ${s.thumb_source === 'embedded' ? 'selected' : ''}>Ingebouwde afbeelding gebruiken (indien aanwezig)</option><option value="render" ${s.thumb_source === 'render' ? 'selected' : ''}>Altijd zelf renderen</option></select><small>Bij wijzigen worden alle thumbnails opnieuw gemaakt (eigen opnames uit de viewer blijven staan).</small>
<label>Pauze tussen thumbnails (sec)</label><input type="number" id="s8" min="0" value="${s.thumb_delay}"><small>Verlaagt de belasting op een NAS. Pauzeren kan ook onder Activiteit → Wachtrij.</small>
<label>Recent toegevoegd (dagen)</label><input type="number" id="s5" min="1" value="${s.recent_days}"><small>Voor het filter "Recent toegevoegd" in de bibliotheek.</small>
<label>Grote bestanden vanaf (MB)</label><input type="number" id="s6" min="1" value="${s.big_mb}"><small>Voor het filter "Groot" in de bibliotheek.</small>
<label>Opslagruimte per leerling (MB)</label><input type="number" id="s6q" min="0" value="${s.student_quota_mb}"><small>Maximale grootte van de eigen map van een leerling. 0 = onbeperkt. Medewerkers hebben geen limiet.</small>
<label>Zip-bestanden</label><label><input type="checkbox" id="s11" data-was="${s.zip_support ? 1 : 0}" ${s.zip_support ? 'checked' : ''}> modellen in zips doorzoeken</label><small>Zonder uitpakken, tot de bestandsgrootte-limiet. Zet je dit uit, dan verdwijnen die modellen (met categorieën en notities) uit de bibliotheek.</small>
<label>Back-upmap</label><div><input id="s12" style="width:100%;box-sizing:border-box" value="${esc(s.backup_dir)}" placeholder="${esc(s.backup_dir_now)}"><div class="row" style="margin:6px 0 0"><button id="bkpick">Kiezen…</button><button id="bknow">Nu back-uppen</button></div></div><small>Hier komt elke dag een back-up, altijd in deze map. Leeg laten betekent de standaardmap (zie hierboven). Kies bij voorkeur een map buiten je config-volume, op een andere schijf of de NAS. Staat de map binnen een root folder, laat de mapnaam dan met een punt beginnen (bijv. .back-ups): zulke mappen worden niet gescand. Is de map er later niet meer (bijvoorbeeld een share die niet gekoppeld is), dan mislukt de back-up met een melding en schrijft de app nooit naar een andere map.</small>
<span></span><small>${s.backup_error ? `<span class="err">Laatste back-up mislukt: ${esc(s.backup_error)}</span>` : s.backup_last ? `Laatste back-up: ${fdate(s.backup_last)}` : 'Nog geen back-up gemaakt sinds het opstarten.'}</small>
<label>Back-ups bewaren (aantal)</label><input type="number" id="s9" min="1" max="60" value="${s.backup_keep}"><small>Dagelijks één back-up van de database. De oudste worden opgeruimd.</small>
<label>Thumbnails in de back-up</label><label><input type="checkbox" id="s10" ${s.backup_thumbs ? 'checked' : ''}> meenemen (kost extra schijfruimte)</label><small>Dan blijven ook eigen opnames uit de viewer bewaard. Zonder worden ontbrekende thumbnails na een herstel automatisch opnieuw gemaakt.</small>
<span></span><button class="p" id="savemm">Opslaan</button></div>`;
  });
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'addroot') { const p = await pickFolder(); if (p) { await api('/api/roots', 'POST', {path: p}); toast('Root folder toegevoegd, scan gestart'); await load(); } }
    if (t.id === 'addtyped') {
      const p = $('#newroot').value.trim(); if (!p) return toast('Typ eerst een pad', 'info');
      await api('/api/roots', 'POST', {path: p}); toast('Root folder toegevoegd, scan gestart'); await load();
    }
    if (t.dataset.mv) {
      const p = prompt('Nieuw pad voor deze root folder, zoals de app het ziet (bijv. /models of D:\\3D). Modellen, categorieën, notities en thumbnails blijven behouden.', t.dataset.p);
      if (!p || !p.trim() || p.trim() === t.dataset.p) return;
      const a = await api('/api/roots/' + t.dataset.mv + '/move', 'POST', {path: p});
      const msg = `Pad wijzigen naar:\n${a.new_path}\n\nGevonden op de nieuwe plek: ${a.found} van ${a.total} modellen.` + (a.missing ? `\n${a.missing} niet gevonden: die blijven in de bibliotheek staan.` : '')
        + (a.conflicts ? `\n\nOp de nieuwe plek staan al ${a.conflicts} van dezelfde bestanden als apart model${a.conflicts_with_data ? ` (${a.conflicts_with_data} met eigen gegevens)` : ''}. Die dubbele ingangen worden vervangen door de bestaande modellen, met al hun gegevens.` : '')
        + (a.needs_force ? '\n\nLet op: minder dan de helft van de bestanden is gevonden. Controleer of dit het juiste pad is.' : '') + '\n\nDoorgaan?';
      if (!confirm(msg)) return;
      await api('/api/roots/' + t.dataset.mv + '/move', 'POST', {path: p, apply: true, force: true});
      toast('Pad gewijzigd, scan gestart'); await load();
    }
    if (t.dataset.del && confirm('Root folder uit de bibliotheek verwijderen? Bestanden op schijf blijven onaangeroerd.')) { await api('/api/roots/' + t.dataset.del, 'DELETE'); toast('Root folder verwijderd'); await load(); }
    if (t.dataset.w) { await api('/api/roots/' + t.dataset.w, 'PUT', {watch: t.checked}); toast('Opgeslagen'); await load(); }
    if (t.dataset.aw) { await api('/api/roots/' + t.dataset.aw, 'PUT', {allow_write: t.checked}); toast(t.checked ? 'Hernoemen en verplaatsen toegestaan' : 'Alleen indexeren'); await load(); }
    if (t.id === 'bkpick') { const p = await pickFolder(true); if (p) $('#s12').value = p; }
    if (t.id === 'bknow') { await api('/api/settings', 'POST', {backup_dir: $('#s12').value.trim()}); await api('/api/tasks/backup/run', 'POST'); toast('Back-up gestart', 'info'); setTimeout(load, 1500); }
    if (t.id === 'savemm') {
      if (!$('#s11').checked && $('#s11').dataset.was === '1' && !confirm('Zip-bestanden niet meer doorzoeken? De modellen uit zips verdwijnen dan uit de bibliotheek, met hun categorieën en notities.')) return;
      await api('/api/settings', 'POST', {zip_support: $('#s11').checked, scan_interval: $('#s1').value, min_age: $('#s2').value, extensions: $('#s3').value, thumb_size: $('#s4').value, recent_days: $('#s5').value, big_mb: $('#s6').value, student_quota_mb: $('#s6q').value, thumb_source: $('#s7').value, thumb_delay: $('#s8').value, backup_keep: $('#s9').value, backup_thumbs: $('#s10').checked, backup_dir: $('#s12').value.trim()}); toast('Instellingen opgeslagen'); setTimeout(load, 1500); }
  });
  $('#view').onkeydown = e => { if (e.key === 'Enter' && e.target.id === 'newroot') $('#addtyped').click(); };
  await load();
};
V['settings/categories'] = async () => {
  $('#title').textContent = 'Instellingen — Categorieën';
  const load = run(async () => {
    const d = await api('/api/library?page=0&size=1');
    $('#view').innerHTML = '<p class="dim">Veel modellen tegelijk indelen? Maak categorieën aan uit je mappen of stel regels in: <a href="#/settings/auto">Automatisch indelen →</a></p>' + (d.categories.length ? tbl(['Naam', 'Modellen', ''], d.categories.map(c => `<tr><td>${esc(c.name)}</td><td>${c.count}</td><td><button data-ren="${c.id}" data-n="${esc(c.name)}">Hernoemen</button> <button class="d" data-del="${c.id}">Verwijderen</button></td></tr>`)) : '<p class="empty">Nog geen categorieën.</p>')
      + '<div class="row" style="max-width:420px"><input id="nc" placeholder="Nieuwe categorie"><button class="p" id="ac">Toevoegen</button></div>';
  });
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'ac' && $('#nc').value.trim()) { await api('/api/categories', 'POST', {name: $('#nc').value}); toast('Categorie aangemaakt'); await load(); }
    if (t.dataset.ren) { const n = prompt('Nieuwe naam:', t.dataset.n); if (n && n.trim()) { await api('/api/categories/' + t.dataset.ren, 'PUT', {name: n}); toast('Categorie hernoemd'); await load(); } }
    if (t.dataset.del && confirm('Categorie verwijderen? Modellen blijven bestaan.')) { await api('/api/categories/' + t.dataset.del, 'DELETE'); toast('Categorie verwijderd'); await load(); }
  });
  await load();
};
V['settings/auto'] = async () => {
  $('#title').textContent = 'Instellingen — Automatisch indelen';
  const FIELDS = {path: 'pad bevat', name: 'naam bevat', ext: 'extensie is', folder: 'map is'};
  let F = {folders: [], loose: 0, total: 0}, R = [], C = [], filter = '';
  const pick = new Map();  // mapnaam -> {on, cat}
  const folderRows = () => F.folders.filter(f => !filter || f.name.toLowerCase().includes(filter)).map(f => {
    const p = pick.get(f.name);
    return `<tr><td><input type="checkbox" data-fo="${esc(f.name)}" ${p.on ? 'checked' : ''}></td><td>${esc(f.name)}</td><td>${nf(f.count)}</td><td><input class="fcat" data-fc="${esc(f.name)}" value="${esc(p.cat)}" style="width:260px"></td><td class="${f.done >= f.count ? 'ok' : 'dim'}">${f.done >= f.count ? '✓ alles ingedeeld' : f.done ? `${nf(f.done)} van ${nf(f.count)} ingedeeld` : f.category_id ? 'categorie bestaat al' : 'nog niet ingedeeld'}</td></tr>`;
  });
  const drawFolders = () => {
    const n = [...pick.values()].filter(p => p.on).length;
    $('#fl').innerHTML = F.folders.length ? tbl(['', 'Map', 'Modellen', 'Categorie', 'Status'], folderRows()) : '<p class="empty">Geen mappen gevonden. Modellen die direct in een root folder staan, tellen niet mee.</p>';
    $('#fa').textContent = `Toepassen (${n} ${n === 1 ? 'map' : 'mappen'})`; $('#fa').disabled = !n;
  };
  const drawRules = () => {
    $('#rl').innerHTML = (R.length ? tbl(['Regel', 'Categorie', 'Past op', 'Nog niet ingedeeld', ''], R.map(r => `<tr><td>${FIELDS[r.field]} <b>${esc(r.value)}</b></td><td>${esc(r.category)}</td><td>${nf(r.matches)}</td><td class="${r.todo ? 'warn' : 'ok'}">${nf(r.todo)}</td><td><button data-rd="${r.id}" class="d">Verwijderen</button></td></tr>`))
      + `<div class="row"><button id="rapply" class="p" ${R.some(r => r.todo) ? '' : 'disabled'}>Alle regels nu toepassen op bestaande modellen</button></div>` : '<p class="dim">Nog geen regels.</p>');
  };
  const load = run(async () => {
    [F, R] = [await api('/api/folders'), await api('/api/rules')];
    C = (await api('/api/library?page=0&size=1')).categories;
    for (const f of F.folders) if (!pick.has(f.name)) pick.set(f.name, {on: false, cat: f.name});
    $('#nc').innerHTML = C.length ? C.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('') : '<option value="">(eerst een categorie aanmaken)</option>';
    $('#fs').textContent = `${nf(F.folders.length)} mappen op het hoogste niveau, ${nf(F.total - F.loose)} van ${nf(F.total)} modellen. ${F.loose ? `${nf(F.loose)} modellen staan direct in een root folder en hebben geen map.` : ''}`;
    drawFolders(); drawRules();
  });
  $('#view').innerHTML = `<h3>Categorieën uit mappen</h3><p class="dim">Elke map op het hoogste niveau van je root folders kan een categorie worden. Alle modellen in die map (ook in submappen) komen erin. Er wordt niets weggehaald en bestaande categorieën blijven staan. Pas de naam aan om een andere categorie te gebruiken, bijvoorbeeld een die al bestaat.</p>
    <p id="fs" class="dim"></p><div class="row"><input id="ff" placeholder="Mappen filteren…" style="width:240px"><button id="fall">Alles kiezen</button><button id="fnone">Niets kiezen</button><button id="ftodo">Alleen nog niet ingedeelde</button><button id="fa" class="p" disabled>Toepassen</button></div><div id="fl"></div>
    <h3 style="margin-top:34px">Regels</h3><p class="dim">Nieuwe bestanden krijgen de categorie automatisch bij de volgende scan. Bij "pad bevat" telt het pad vanaf de root folder, met / tussen de mappen (bijvoorbeeld "10 inch rack/"). Een regel haalt nooit een categorie weg.</p>
    <div class="row"><select id="nf">${Object.entries(FIELDS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select><input id="nv" placeholder="tekst, bijv. rack" style="width:220px"><span class="dim">→ categorie</span><select id="nc"></select><button id="nadd" class="p">Regel toevoegen</button></div><div id="rl"></div>`;
  $('#view').oninput = e => {
    const t = e.target;
    if (t.id === 'ff') { filter = t.value.toLowerCase().trim(); drawFolders(); $('#ff').focus && $('#ff').focus(); }
    if (t.dataset.fc !== undefined) { const p = pick.get(t.dataset.fc); if (p) p.cat = t.value; }
  };
  $('#view').onchange = e => { const t = e.target; if (t.dataset.fo !== undefined) { const p = pick.get(t.dataset.fo); if (p) p.on = t.checked; drawFolders(); } };
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'fall') { F.folders.filter(f => !filter || f.name.toLowerCase().includes(filter)).forEach(f => pick.get(f.name).on = true); return drawFolders(); }
    if (t.id === 'fnone') { pick.forEach(p => p.on = false); return drawFolders(); }
    if (t.id === 'ftodo') { F.folders.forEach(f => pick.get(f.name).on = f.done < f.count); return drawFolders(); }
    if (t.id === 'fa') {
      const items = F.folders.filter(f => pick.get(f.name).on).map(f => ({folder: f.name, category: pick.get(f.name).cat.trim()}));
      if (items.some(i => !i.category)) return toast('Vul bij elke gekozen map een categorienaam in', 'err');
      const n = F.folders.filter(f => pick.get(f.name).on).reduce((a, f) => a + f.count, 0);
      if (!confirm(`${items.length} mappen omzetten in categorieën? Er worden tot ${nf(n)} modellen ingedeeld. Dit haalt niets weg.`)) return;
      const r = await api('/api/folders/categorize', 'POST', {items}); pick.forEach(p => p.on = false);
      toast(`${nf(r.assigned)} indelingen gezet, ${r.created} nieuwe categorieën`); return load();
    }
    if (t.id === 'nadd') {
      const v = $('#nv').value.trim(); if (!v) return toast('Vul een tekst in voor de regel', 'err');
      if (!$('#nc').value) return toast('Maak eerst een categorie aan', 'err');
      const r = await api('/api/rules', 'POST', {field: $('#nf').value, value: v, category_id: +$('#nc').value}); $('#nv').value = '';
      toast(r.existing ? 'Deze regel bestaat al' : 'Regel toegevoegd', r.existing ? 'info' : undefined); return load();
    }
    if (t.dataset.rd) { await api('/api/rules/' + t.dataset.rd, 'DELETE'); toast('Regel verwijderd'); return load(); }
    if (t.id === 'rapply') { const r = await api('/api/rules/apply', 'POST', {}); toast(`${nf(r.assigned)} indelingen gezet`); return load(); }
  });
  await load();
};
V['settings/printers'] = async () => {
  $('#title').textContent = 'Instellingen — Printers';
  const load = run(async () => {
    const [ps, presets] = await Promise.all([api('/api/printers'), api('/api/printers/presets')]); L.presets = presets;
    $('#view').innerHTML = '<p class="dim">Met de bedgrootte van je printers laat de bibliotheek zien welke modellen passen (een model mag 90° gedraaid worden). Controleer de maten van de voorinstellingen altijd met je eigen printer.</p>'
      + (ps.length ? tbl(['Naam', 'Bed X × Y × Z (mm)', ''], ps.map(p => `<tr><td>${esc(p.name)}</td><td>${p.bed_x} × ${p.bed_y} × ${p.bed_z}</td><td><button data-edit="${p.id}" data-n="${esc(p.name)}" data-s="${p.bed_x}x${p.bed_y}x${p.bed_z}">Wijzigen</button> <button class="d" data-del="${p.id}">Verwijderen</button></td></tr>`)) : '<p class="empty">Nog geen printers.</p>')
      + `<h3>Printer toevoegen</h3><div class="row" style="max-width:820px;flex-wrap:wrap"><select id="pp"><option value="">Voorinstelling…</option>${presets.map((x, i) => `<option value="${i}">${esc(x.name)}</option>`).join('')}</select><input id="pn" placeholder="Naam"><input id="px" type="number" placeholder="X" style="max-width:90px"><input id="py" type="number" placeholder="Y" style="max-width:90px"><input id="pz" type="number" placeholder="Z" style="max-width:90px"><button class="p" id="pa">Toevoegen</button></div>`;
  });
  $('#view').onchange = e => { if (e.target.id === 'pp' && e.target.value !== '') { const x = L.presets[+e.target.value]; $('#pn').value = x.name; $('#px').value = x.bed_x; $('#py').value = x.bed_y; $('#pz').value = x.bed_z; } };
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'pa') { await api('/api/printers', 'POST', {name: $('#pn').value, bed_x: $('#px').value, bed_y: $('#py').value, bed_z: $('#pz').value}); toast('Printer toegevoegd'); await load(); }
    if (t.dataset.del && confirm('Printer verwijderen?')) { await api('/api/printers/' + t.dataset.del, 'DELETE'); toast('Printer verwijderd'); await load(); }
    if (t.dataset.edit) {
      const n = prompt('Naam:', t.dataset.n); if (!n) return;
      const s = prompt('Bedgrootte X x Y x Z in mm:', t.dataset.s); if (!s) return;
      const [x, y, z] = s.split(/[x×,; ]+/).map(Number);
      await api('/api/printers/' + t.dataset.edit, 'PUT', {name: n, bed_x: x, bed_y: y, bed_z: z}); toast('Printer gewijzigd'); await load();
    }
  });
  await load();
};
V['settings/users'] = async () => {
  $('#title').textContent = 'Instellingen — Gebruikers';
  const load = run(async () => {
    const [us, scs] = await Promise.all([api('/api/users'), api('/api/schools')]); const SC = scs.schools, scOpt = cur => '<option value="">–</option>' + SC.map(x => `<option value="${x.id}" ${x.id === cur ? 'selected' : ''}>${esc(x.name)}</option>`).join('');
    $('#view').innerHTML = (us.length ? '<p class="dim">Beheerders mogen alles. Een medewerker beheert de leerlingen en printaanvragen van de eigen school en ziet alle modellen van die school. Een leerling ziet de eigen modellen en wat gedeeld is, en uploadt alleen in de eigen map. Voor leerlingen en medewerkers kies je een school; hun eigen map wordt automatisch aangemaakt. Leerlingen voeg je gemakkelijker toe via Leerlingen (ook met CSV-import).</p>'
        : '<p class="warn">Er zijn nog geen accounts: iedereen met toegang tot dit adres kan alles. Maak hieronder je eigen beheerdersaccount aan; daarna moet iedereen inloggen.</p>')
      + (us.length ? tbl(['Gebruiker', 'Inlog', 'E-mail', 'Rol', 'School', 'Downloaden', 'Uploaden', 'Actief', 'Laatste login', ''], us.map(u => `<tr><td>${esc(u.username)}${u.me ? ' <span class="dim">(jij)</span>' : ''}</td><td>${loginKind(u)}</td><td class="dim">${esc(u.email) || '–'}</td>
        <td><select data-role="${u.id}"><option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Beheerder</option><option value="staff" ${u.role === 'staff' ? 'selected' : ''}>Medewerker</option><option value="student" ${u.role === 'student' ? 'selected' : ''}>Leerling</option></select></td><td>${u.role === 'admin' ? '<span class="dim">–</span>' : `<select data-sc="${u.id}">${scOpt(u.school_id)}</select>`}</td>
        <td><input type="checkbox" data-dl="${u.id}" ${u.can_download ? 'checked' : ''}></td><td>${u.role === 'admin' ? '<span class="dim">altijd</span>' : `<input type="checkbox" data-up="${u.id}" ${u.can_upload ? 'checked' : ''}>`}</td><td><input type="checkbox" data-act="${u.id}" ${u.active ? 'checked' : ''}></td><td class="dim">${fdate(u.last_login)}</td>
        <td><button data-em="${u.id}" data-n="${esc(u.username)}" data-v="${esc(u.email)}">E-mail</button> <button data-pw="${u.id}" data-n="${esc(u.username)}">Wachtwoord</button> <button class="d" data-del="${u.id}" data-n="${esc(u.username)}">Verwijderen</button></td></tr>`)) : '')
      + `<h3>${us.length ? 'Gebruiker toevoegen' : 'Eerste beheerder aanmaken'}</h3><div class="ugrid"><div class="f"><small>Gebruikersnaam</small><input id="nu" autocomplete="off"></div><div class="f"><small>E-mailadres (optioneel)</small><input id="ne" type="email" autocomplete="off"></div><div class="f"><small>Wachtwoord (minstens 8 tekens)</small><input id="np" type="password" autocomplete="new-password"></div>${us.length ? '<div class="f sm"><small>Rol</small><select id="nr"><option value="student">Leerling</option><option value="staff">Medewerker</option><option value="admin">Beheerder</option></select></div><div class="f sm"><small>School</small><select id="nsc">' + scOpt(SC.length === 1 ? SC[0].id : null) + '</select></div><div class="f fit"><small>Rechten</small><div class="chk"><label><input type="checkbox" id="nd" checked> mag downloaden</label><label><input type="checkbox" id="nu2" checked> mag uploaden</label></div></div>' : ''}<div class="f go"><small>&nbsp;</small><button class="p" id="na">${us.length ? 'Toevoegen' : 'Account aanmaken'}</button></div></div>`
      + (us.length ? '<h3>Inloggen uitzetten</h3><p class="dim">Verwijdert alle accounts; daarna heeft iedereen met toegang tot dit adres weer alle rechten.</p><button class="d" id="nclear">Alle accounts verwijderen</button>' : '')
      + '<p class="dim" style="margin-top:24px">Zet de app niet rechtstreeks op internet: gebruik daarvoor HTTPS, bijvoorbeeld via de reverse proxy van je NAS. Wachtwoorden worden versleuteld opgeslagen; na 5 foute pogingen is inloggen 10 minuten geblokkeerd.</p>';
  });
  $('#view').onchange = run(async e => {
    if (e.target.id === 'nr') { $('#nsc').disabled = e.target.value === 'admin'; return; }
    const t = e.target, body = t.dataset.role ? {role: t.value} : t.dataset.sc ? {school_id: +t.value || null} : t.dataset.dl ? {can_download: t.checked} : t.dataset.up ? {can_upload: t.checked} : t.dataset.act ? {active: t.checked} : null;
    if (!body) return;
    try { await api('/api/users/' + (t.dataset.role || t.dataset.sc || t.dataset.dl || t.dataset.up || t.dataset.act), 'PUT', body); toast('Opgeslagen'); } catch (err) { toast(err.message, 'err'); }
    await load();
  });
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'na') {
      const first = !$('#nr');
      await api('/api/users', 'POST', {username: $('#nu').value, email: $('#ne').value, password: $('#np').value, role: first ? 'admin' : $('#nr').value, school_id: first ? undefined : (+$('#nsc').value || undefined), can_download: first ? true : $('#nd').checked, can_upload: first ? false : $('#nu2').checked});
      toast('Account aangemaakt');
      if (first) { ME = await api('/api/me'); buildNav(); route(); return; }
      await load();
    }
    if (t.dataset.em) { const v = prompt(`E-mailadres van ${t.dataset.n} (leeg laten om te wissen):`, t.dataset.v); if (v === null) return; await api('/api/users/' + t.dataset.em, 'PUT', {email: v}); toast('E-mailadres opgeslagen'); await load(); }
    if (t.dataset.pw) { const p = prompt(`Nieuw wachtwoord voor ${t.dataset.n} (minstens 8 tekens):`); if (!p) return; await api('/api/users/' + t.dataset.pw, 'PUT', {password: p}); toast('Wachtwoord gewijzigd'); }
    if (t.dataset.del && confirm(`Account "${t.dataset.n}" verwijderen?`)) { await api('/api/users/' + t.dataset.del, 'DELETE'); toast('Account verwijderd'); await load(); }
    if (t.id === 'nclear' && confirm('Alle accounts verwijderen en inloggen uitzetten?')) { await api('/api/users/clear', 'POST', {confirm: true}); toast('Inloggen staat uit'); ME = await api('/api/me'); buildNav(); route(); }
  });
  await load();
};
// ------------------------------------------------------------ uploaden
function openUpload(cats) {
  const old = document.querySelector('#upmodal'); if (old && old.remove) old.remove();
  const el = document.createElement('div'); el.id = 'upmodal';
  el.style.cssText = 'position:fixed;inset:0;background:#000b;z-index:10;display:flex;align-items:center;justify-content:center';
  document.body.appendChild(el);
  const S = {roots: [], root: 0, path: [], q: '', dirs: [], files: [], busy: false, exts: [], max: 0, scoped: false, quota: 0, used: 0, share: true};
  const close = () => { if (!S.busy || confirm('De upload loopt nog. Toch sluiten?')) el.remove(); };
  const crumbs = () => [S.roots.find(r => r.id === S.root).name, ...S.path].map((x, i, all) => i === all.length - 1 ? `<b>📁 ${esc(x)}</b>` : `<a href="#" data-crumb="${i}" style="color:#7fb2ff">📁 ${esc(x)}</a>`).join(' <span class="dim">›</span> ');
  const listHTML = () => {
    const q = S.q.trim().toLowerCase(), ds = S.dirs.filter(d => !q || d.toLowerCase().includes(q));
    const row = (attr, txt) => `<div ${attr} style="padding:7px 12px;cursor:pointer;border-bottom:1px solid #2a2f3d">${txt}</div>`;
    return (S.path.length ? row('data-up="1"', '📁 <span class="dim">.. (een map omhoog)</span>') : '') + ds.map(d => row(`data-dir="${esc(d)}"`, '📁 ' + esc(d))).join('')
      + (ds.length || (S.have || []).length ? '' : `<div class="dim" style="padding:12px">${S.dirs.length ? 'Geen mappen die passen bij je zoekopdracht' : 'Geen submappen'}</div>`)
      + (S.have || []).filter(f => !q || f.toLowerCase().includes(q)).map(f => `<div class="dim" style="padding:5px 12px;border-bottom:1px solid #2a2f3d">📄 ${esc(f)}</div>`).join('');
  };
  const draw = () => {
    el.innerHTML = `<div style="background:#232733;border-radius:12px;width:min(640px,95vw);max-height:92vh;overflow:auto;padding:22px">
<h3 style="margin-top:0">Modellen uploaden</h3>
${S.roots.length ? `${S.scoped ? `<p class="dim">Je uploadt in je eigen map.${S.quota ? ` Opslagruimte: ${S.used} van ${S.quota} MB gebruikt.` : ''}</p>` : '<label>Root folder</label>'}<select style="${S.scoped ? 'display:none' : ''}" id="ur" ${S.busy ? 'disabled' : ''}>${S.roots.map(r => `<option value="${r.id}" ${r.id === S.root ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>
<label>Map</label><div id="ucr" style="margin-bottom:6px">${crumbs()}</div>
<input id="uq" placeholder="Zoek in deze map…" autocomplete="off" ${S.busy ? 'disabled' : ''} value="${esc(S.q)}">
<div id="udl" style="margin-top:6px;border:1px solid #3a4052;border-radius:8px;height:210px;overflow:auto;background:#1c1f29">${listHTML()}</div>
<div class="row" style="margin-top:8px"><input id="unew" placeholder="Of een nieuwe map in deze map (optioneel)" ${S.busy ? 'disabled' : ''}></div>
<label>Categorie(ën) (optioneel)</label><div class="chips" style="padding:0">${cats.map(c => `<label style="margin-right:12px;white-space:nowrap"><input type="checkbox" data-cat="${c.id}" ${S.busy ? 'disabled' : ''}> ${esc(c.name)}</label>`).join('') || '<span class="dim">Nog geen categorieën</span>'}</div>
${S.scoped ? `<label><input type="checkbox" id="ushare" ${S.share ? 'checked' : ''} ${S.busy ? 'disabled' : ''}> Delen met andere leerlingen en scholen</label>` : ''}
<label>Bestanden</label><input type="file" id="uf" multiple accept="${S.exts.map(e => '.' + e).join(',')}" ${S.busy ? 'disabled' : ''}>
<small>Toegestaan: ${esc(S.exts.join(', '))}. Maximaal ${S.max} MB per bestand. Een bestand met dezelfde naam wordt nooit overschreven; er komt dan (2) achter.</small>
<div id="ulist" style="margin-top:10px">${S.files.map((f, i) => `<div class="dim">${esc(f.name)} <span id="us${i}">${f.state || ''}</span></div>`).join('')}</div>`
      : '<p class="warn">Er is geen beschrijfbare root folder om naartoe te uploaden.</p>'}
<div class="row" style="margin-top:14px;justify-content:flex-end"><button id="ucl">${S.busy ? 'Sluiten' : 'Klaar'}</button>${S.roots.length ? `<button class="p" id="ugo" ${S.busy ? 'disabled' : ''}>⬆ Uploaden</button>` : ''}</div></div>`;
  };
  const loadDirs = async () => { try { const j = await api(`/api/upload/dirs?root=${S.root}&path=${encodeURIComponent(S.path.join('/'))}`); S.dirs = j.dirs; S.have = j.files || []; } catch (e) { S.dirs = []; S.have = []; toast(e.message, 'err'); } };
  const sendOne = (f, folder, catIds) => new Promise(res => {
    const x = new XMLHttpRequest(), fd = new FormData();
    fd.append('root', S.root); fd.append('folder', folder); fd.append('categories', catIds.join(',')); if (S.scoped) fd.append('shared', S.share ? '1' : '0'); fd.append('file', f);
    x.open('POST', '/api/upload'); x.setRequestHeader('X-Requested-With', 'modelbib');
    x.upload.onprogress = e => { const o = el.querySelector('#us' + S.files.indexOf(f)); if (o && e.lengthComputable) o.textContent = Math.round(e.loaded / e.total * 100) + '%'; };
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (_) {} if (x.status === 401) showLogin(); res(x.status < 300 ? {ok: true, renamed: j.renamed, name: j.name} : {error: j.error || 'Mislukt (' + x.status + ')'}); };
    x.onerror = () => res({error: 'Verbinding verbroken'});
    x.send(fd);
  });
  el.onclick = run(async e => {
    const t = e.target;
    if (t === el || t.id === 'ucl') return close();
    if (S.busy) return;
    if (t.closest && t.closest('[data-crumb]')) e.preventDefault();
    const row = t.closest ? t.closest('[data-dir],[data-up],[data-crumb]') : t, d = row && row.dataset || {};
    if (d.dir) { S.path.push(d.dir); S.q = ''; await loadDirs(); draw(); }
    else if (d.up) { S.path.pop(); S.q = ''; await loadDirs(); draw(); }
    else if (d.crumb !== undefined) { S.path = S.path.slice(0, +d.crumb); S.q = ''; await loadDirs(); draw(); }
    if (t.id === 'ugo') {
      const files = [...$('#uf').files]; if ($('#ushare')) S.share = $('#ushare').checked;
      if (!files.length) return toast('Kies eerst een of meer bestanden', 'err');
      const catIds = [...el.querySelectorAll('[data-cat]')].filter(c => c.checked).map(c => c.dataset.cat);
      const nw = $('#unew').value.trim(), folder = [...S.path, ...(nw ? [nw] : [])].join('/');
      S.files = files.map(f => Object.assign(f, {state: ''})); S.busy = true; draw();
      let ok = 0, bad = 0;
      for (const f of files) {
        const o = () => el.querySelector('#us' + S.files.indexOf(f));
        if (o()) o().textContent = '…';
        const r = await sendOne(f, folder, catIds);
        if (r.ok) { ok++; if (o()) o().innerHTML = '✓' + (r.renamed ? ' <span class="dim">(opgeslagen als ' + esc(r.name) + ')</span>' : ''); }
        else { bad++; if (o()) o().innerHTML = '<span class="warn">✗ ' + esc(r.error) + '</span>'; }
      }
      S.busy = false; el.querySelector('#ugo').disabled = false; el.querySelector('#ucl').textContent = 'Sluiten';
      toast(`${ok} geüpload${bad ? `, ${bad} mislukt` : ''}. Ze verschijnen in de bibliotheek zodra de scan ze oppakt.`, bad ? 'err' : undefined);
      if (!bad) close();  // alles gelukt: venster automatisch sluiten; bij fouten open laten zodat je ze kunt lezen
    }
  });
  el.onchange = run(async e => { if (e.target.id === 'ur' && !S.busy) { S.root = +e.target.value; S.path = []; await loadDirs(); draw(); } });
  el.oninput = e => { if (e.target.id === 'uq') { S.q = e.target.value; el.querySelector('#udl').innerHTML = listHTML(); } };
  el.onkeydown = e => { if (e.key === 'Escape') close(); };
  run(async () => {
    const r = await api('/api/upload/targets');
    S.scoped = !!r.scoped; S.quota = r.quota_mb || 0; S.used = r.used_mb || 0; S.share = r.share_default !== false; S.roots = r.roots; S.exts = r.exts; S.max = r.max_mb; S.root = r.roots.length ? r.roots[0].id : 0;
    if (S.root) await loadDirs();
    draw();
  })();
}
const bbInfo = sy => !sy || !sy.last ? '' : sy.error ? 'Laatste synchronisatie mislukt: ' + sy.error : `Laatste synchronisatie: ${fdate(sy.last)}. ${sy.result.added} nieuw, ${sy.result.known} al bekend, ${sy.result.unmatched} zonder bijpassend model${sy.result.examples.length ? ' (' + sy.result.examples.join(', ') + ')' : ''}.`;
V['settings/general'] = async () => {
  $('#title').textContent = 'Instellingen — Algemeen';
  const s = await api('/api/settings');
  $('#view').innerHTML = `<h3>Server</h3><div class="form"><label>Adres</label><span>${esc(s.host)}:${s.port} <span class="dim">(via omgevingsvariabelen HOST / PORT)</span></span><label>Versie</label><span>${esc(s.version)}</span></div>
<h3>Gebruikers en toegang</h3><p class="dim">Accounts, inloggen en gasten die modellen mogen bekijken en downloaden beheer je onder <a href="#/settings/users">Instellingen → Gebruikers</a>.</p>
<h3>Slicer</h3><div class="form"><label>"Openen in slicer" via link</label><select id="slc">${[['bambustudio', 'Bambu Studio'], ['orcaslicer', 'OrcaSlicer'], ['prusaslicer', 'PrusaSlicer']].map(([v, n]) => `<option value="${v}" ${s.slicer === v ? 'selected' : ''}>${n}</option>`).join('')}</select><small>De slicer haalt het bestand zelf op via een tijdelijke link (10 minuten), dus het adres van deze app moet vanaf je computer bereikbaar zijn. Lukt dat niet, download het bestand of gebruik "Openen met standaardprogramma" (alleen als de app op deze computer draait).</small><span></span><button class="p" id="slsave">Opslaan</button></div>
<h3>Spoolman</h3><div class="form"><label>Adres van Spoolman</label><input id="smu" value="${esc(s.spoolman_url)}" placeholder="http://spoolman:7912"><small>Optioneel. Dan kun je bij een print het verbruik van een spoel laten aftrekken. De app moet Spoolman kunnen bereiken (in Docker: de containernaam of het NAS-adres).</small><span></span><div class="row"><button class="p" id="smsave">Opslaan</button><button id="smtest">Verbinding testen</button></div></div>
<h3>Bambuddy</h3><div class="form"><label>Adres van Bambuddy</label><input id="bbu" value="${esc(s.bambuddy_url)}" placeholder="http://192.168.1.20:8000"><label>API-sleutel van Bambuddy</label><input id="bbk" type="password" autocomplete="off" value="" placeholder="${s.bambuddy_key_set ? '•••••••• (opgeslagen, leeg laten om te behouden)' : 'Plak hier de sleutel uit Bambuddy'}"><small>Optioneel. Maak in Bambuddy onder Instellingen → API Keys een sleutel. Daarmee kun je een model naar Bambuddy sturen (bibliotheek of wachtrij) en wordt de printgeschiedenis van Bambuddy elke 30 minuten overgenomen in het printlogboek. De sleutel wordt in de database van deze app opgeslagen en nooit teruggestuurd naar de browser.</small><span></span><div class="row"><button class="p" id="bbsave">Opslaan</button><button id="bbtest">Verbinding testen</button><button id="bbsync">Nu synchroniseren</button><button id="bbclear">Sleutel wissen</button></div><span></span><small id="bbinfo" class="dim"></small></div>
<h3>API-sleutel</h3><div class="form"><label>Sleutel</label><input id="ak" readonly value="${esc(s.api_key)}"><small>Meesturen als header X-Api-Key om zonder wachtwoord bij de API te komen.</small><span></span><button id="rk">Nieuwe sleutel genereren</button></div>`;
  if (s.bambuddy_url && s.bambuddy_key_set) api('/api/bambuddy/status').then(r => { if ($('#bbinfo')) $('#bbinfo').textContent = bbInfo(r.sync); }).catch(() => {});
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'slsave') { await api('/api/settings', 'POST', {slicer: $('#slc').value}); toast('Slicer opgeslagen'); }
    if (t.id === 'smsave') { await api('/api/settings', 'POST', {spoolman_url: $('#smu').value}); toast($('#smu').value.trim() ? 'Spoolman-adres opgeslagen' : 'Spoolman uitgeschakeld'); }
    if (t.id === 'bbsave') { const b = {bambuddy_url: $('#bbu').value}; if ($('#bbk').value.trim()) b.bambuddy_key = $('#bbk').value.trim(); await api('/api/settings', 'POST', b); toast('Bambuddy opgeslagen'); return V['settings/general'](); }
    if (t.id === 'bbclear' && confirm('De opgeslagen Bambuddy-sleutel wissen? De koppeling staat dan uit.')) { await api('/api/settings', 'POST', {bambuddy_key_clear: true}); toast('Sleutel gewist'); return V['settings/general'](); }
    if (t.id === 'bbtest') { const r = await api('/api/bambuddy/status'); if (!r.configured) toast('Vul eerst adres en sleutel in en klik op Opslaan', 'info'); else if (r.ok) toast(`Verbonden met Bambuddy: ${r.printers.length} ${r.printers.length === 1 ? 'printer' : 'printers'}`); else toast(r.error, 'err'); }
    if (t.id === 'bbsync') { const r = await api('/api/bambuddy/sync', 'POST'); const x = r.result; toast(`${x.added} nieuwe prints overgenomen` + (x.unmatched ? `, ${x.unmatched} zonder bijpassend model` : ''), 'info'); $('#bbinfo').textContent = bbInfo(r); }
    if (t.id === 'smtest') { const r = await api('/api/spoolman/status'); if (!r.configured) toast('Vul eerst het adres in en klik op Opslaan', 'info'); else if (r.ok) toast('Verbonden met Spoolman ' + (r.version || '')); else toast(r.error, 'err'); }
    if (t.id === 'rk' && confirm('Nieuwe API-sleutel genereren? De oude werkt dan niet meer.')) { await api('/api/settings', 'POST', {regen_key: true}); toast('Nieuwe API-sleutel'); V['settings/general'](); }
  });
};

// ------------------------------------------------------------ systeem
V['system/status'] = async () => {
  $('#title').textContent = 'Systeem — Status';
  const load = run(async () => {
    const s = await api('/api/status'), up = Math.floor(s.uptime);
    $('#view').innerHTML = '<h3>Gezondheid</h3>' + (s.health.length ? s.health.map(h => `<div class="health ${h.level}">${esc(h.msg)}</div>`).join('') : '<div class="health good">✓ Geen problemen gevonden.</div>')
      + `<h3>Over</h3><div class="form"><label>Versie</label><span>${esc(s.version)}</span><label>Python</label><span>${esc(s.python)}</span><label>Platform</label><span>${esc(s.platform)}</span><label>Actief sinds</label><span>${Math.floor(up / 3600)}u ${Math.floor(up % 3600 / 60)}m</span><label>Config-map</label><span>${esc(s.config)}</span><label>Database</label><span>${fsize(s.db_size)}</span><label>Modellen / categorieën</label><span>${s.models} / ${s.categories}</span></div>`
      + '<h3>Opslag</h3>' + (s.roots.length ? tbl(['Root folder', 'Modellen', 'Vrij', 'Totaal'], s.roots.map(r => `<tr><td>${esc(r.path)}</td><td>${r.count}</td><td>${fsize(r.free)}</td><td>${fsize(r.total)}</td></tr>`)) : '<p class="dim">Geen root folders.</p>');
  });
  onRev = load; await load();
};
V['system/tasks'] = async () => {
  $('#title').textContent = 'Systeem — Taken';
  const load = run(async () => {
    const t = await api('/api/tasks');
    $('#view').innerHTML = tbl(['Taak', 'Interval', 'Laatst uitgevoerd', 'Duur', 'Volgende', ''], t.map(x => `<tr><td><b>${esc(x.name)}</b><br><span class="dim">${esc(x.desc)}</span>${x.dir ? `<br><span class="dim">Map: </span><code>${esc(x.dir)}</code>` : ''}${x.error ? `<br><span class="err">Laatste poging mislukt: ${esc(x.error)}</span>` : ''}</td><td>${esc(x.interval)}</td><td>${fdate(x.last)}</td><td>${x.dur != null ? x.dur.toFixed(1) + 's' : '–'}</td><td>${x.running ? '<span class="warn">bezig…</span>' : fdate(x.next)}</td><td><button data-run="${x.key}">▶ Nu uitvoeren</button></td></tr>`));
  });
  $('#view').onclick = run(async e => { if (e.target.dataset.run) { await api(`/api/tasks/${e.target.dataset.run}/run`, 'POST'); toast('Taak gestart', 'info'); setTimeout(load, 800); } });
  onRev = load; await load();
};
V['system/logs'] = async () => {
  $('#title').textContent = 'Systeem — Logs';
  $('#tools').innerHTML = '<select id="ll"><option value="INFO">Info</option><option value="WARNING">Waarschuwingen</option><option value="ERROR">Fouten</option><option value="DEBUG">Alles</option></select><button id="lc">Leegmaken</button>';
  const load = run(async () => {
    const l = await api('/api/logs?level=' + $('#ll').value);
    $('#view').innerHTML = l.length ? tbl(['Tijd', 'Niveau', 'Bericht'], l.map(x => `<tr><td class="dim" style="white-space:nowrap">${fdate(x.t)}</td><td class="${x.level === 'ERROR' ? 'err' : x.level === 'WARNING' ? 'warn' : ''}">${x.level}</td><td><pre>${esc(x.msg)}</pre></td></tr>`)) : '<p class="empty">Geen logregels.</p>';
  });
  $('#ll').onchange = load; $('#lc').onclick = run(async () => { await api('/api/logs', 'DELETE'); load(); });
  stopFn = (id => () => clearInterval(id))(setInterval(load, 3000)); await load();
};

// ------------------------------------------------------------ scholen: printaanvragen, meldingen, leerlingen, scholen
const REQ_ST = {open: 'Open', busy: 'Bezig', done: 'Klaar', rejected: 'Afgewezen', cancelled: 'Ingetrokken'};
const sw = (name, hex) => `<span title="${esc(name)}" style="display:inline-block;width:14px;height:14px;border-radius:50%;background:${esc(hex)};border:1px solid #666;vertical-align:-2px;margin-right:3px"></span>`;
function overlay(html, id = 'ovl') {
  const old = document.getElementById(id); if (old && old.remove) old.remove();
  const el = document.createElement('div'); el.id = id;
  el.style.cssText = 'position:fixed;inset:0;background:#000b;z-index:10;display:flex;align-items:center;justify-content:center';
  el.innerHTML = `<div style="background:#232733;border-radius:12px;width:min(680px,95vw);max-height:92vh;overflow:auto;padding:22px">${html}</div>`;
  document.body.appendChild(el); return el;
}
function openRequest(m) {
  run(async () => {
    const o = await api('/api/requests/options');
    const el = overlay(`<h3 style="margin-top:0">Print aanvragen</h3><p><b>${esc(label(m))}</b></p>
<label>Kleur(en), maximaal ${o.max_colors} (optioneel)</label><div id="rcol" style="display:flex;flex-wrap:wrap;gap:6px 14px;margin:6px 0">${o.colors.map(c => `<label style="white-space:nowrap"><input type="checkbox" data-c="${esc(c.name)}"> ${sw(c.name, c.hex)}${esc(c.name)}</label>`).join('')}</div>
<label>Aantal</label><input type="number" id="rn" min="1" max="${o.max_copies}" value="1" style="width:90px">
<label>Opmerking voor de medewerker</label><textarea id="rnote" rows="3" maxlength="300" style="width:100%"></textarea>
<div class="row" style="margin-top:14px;justify-content:flex-end"><button id="rcl">Annuleren</button><button class="p" id="rgo">Aanvragen</button></div>`);
    el.onclick = run(async e => {
      const t = e.target;
      if (t === el || t.id === 'rcl') return el.remove();
      if (t.dataset && t.dataset.c !== undefined && el.querySelectorAll('[data-c]').length && [...el.querySelectorAll('[data-c]')].filter(c => c.checked).length > o.max_colors) { t.checked = false; return toast(`Kies maximaal ${o.max_colors} kleuren`, 'err'); }
      if (t.id === 'rgo') {
        const colors = [...el.querySelectorAll('[data-c]')].filter(c => c.checked).map(c => c.dataset.c);
        await api('/api/requests', 'POST', {model_id: m.id, colors, copies: +$('#rn').value || 1, note: $('#rnote').value});
        el.remove(); toast('Aanvraag verstuurd. Je ziet de status onder Printaanvragen.');
      }
    });
  })();
}
function sendFile(url, file) {
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest(), fd = new FormData(); fd.append('file', file);
    x.open('POST', url); x.setRequestHeader('X-Requested-With', 'modelbib');
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (_) {} x.status < 300 ? res(j) : rej(new Error(j.error || 'Mislukt (' + x.status + ')')); };
    x.onerror = () => rej(new Error('Verbinding verbroken')); x.send(fd);
  });
}
V.requests = async () => {
  $('#title').textContent = 'Printaanvragen';
  const hex = {}; ((await api('/api/requests/options')).colors || []).forEach(c => hex[c.name] = c.hex);
  const stf = adm() || staff();
  $('#tools').innerHTML = '<select id="rf"><option value="active">Lopende aanvragen</option><option value="all">Alle aanvragen</option></select>';
  const load = run(async () => {
    const rs = (await api('/api/requests' + ($('#rf').value === 'active' ? '?status=active' : ''))).requests;
    const cols = r => r.colors.length ? r.colors.map(c => sw(c, hex[c] || '#888') + esc(c)).join(' ') : '<span class="dim">geen voorkeur</span>';
    if (!rs.length) { $('#view').innerHTML = '<p class="dim">Geen aanvragen. Open een model in de bibliotheek en kies "Print aanvragen".</p>'; return; }
    $('#view').innerHTML = stf
      ? tbl(['Leerling', 'Model', 'Kleuren', 'Aantal', 'Opmerking', 'Gesliced bestand', 'Status', 'Opmerking aan leerling', ''], rs.map(r => `<tr data-r="${r.id}"><td>${esc(r.requester)}<br><span class="dim">${fdate(r.created)}</span></td><td>${r.model_id ? `<a href="/api/file/${r.model_id}" download title="Model downloaden">⬇ ${esc(r.model)}</a>` : esc(r.model)}</td><td>${cols(r)}</td><td>${r.copies}</td><td>${esc(r.note)}</td>
<td>${r.has_file ? `<a href="/api/requests/${r.id}/file">⬇ ${esc(r.sliced_name)}</a><br>` : ''}<input type="file" data-f="${r.id}" accept=".3mf,.gcode,.bgcode"></td>
<td><select data-st="${r.id}">${['open', 'busy', 'done', 'rejected'].map(s => `<option value="${s}" ${r.status === s ? 'selected' : ''}>${REQ_ST[s]}</option>`).join('')}${r.status === 'cancelled' ? '<option selected value="cancelled" disabled>Ingetrokken</option>' : ''}</select></td>
<td><input data-n="${r.id}" value="${esc(r.staff_note)}" maxlength="300"></td><td><button data-save="${r.id}">Opslaan</button></td></tr>`))
      : tbl(['Datum', 'Model', 'Kleuren', 'Aantal', 'Status', 'Bericht van de medewerker', ''], rs.map(r => `<tr><td class="dim">${fdate(r.created)}</td><td>${esc(r.model)}</td><td>${cols(r)}</td><td>${r.copies}</td><td><b>${REQ_ST[r.status] || r.status}</b></td><td>${esc(r.staff_note)}</td><td>${r.status === 'open' ? `<button data-cx="${r.id}">Intrekken</button>` : ''}</td></tr>`));
  });
  $('#rf').onchange = load; onRev = load;
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.dataset.cx) { await api(`/api/requests/${t.dataset.cx}/cancel`, 'POST'); toast('Aanvraag ingetrokken'); return load(); }
    if (t.dataset.save) {
      const id = t.dataset.save, f = $(`[data-f="${id}"]`).files[0];
      if (f) await sendFile(`/api/requests/${id}/file`, f);
      let st = $(`[data-st="${id}"]`).value;
      await api('/api/requests/' + id, 'POST', {status: f && st === 'open' ? 'busy' : st, staff_note: $(`[data-n="${id}"]`).value});
      toast('Opgeslagen'); load();
    }
  });
  await load();
};
V.access = async () => {
  $('#title').textContent = 'Mappen: zichtbaar voor leerlingen';
  const S = {root: 0, path: []};
  const load = run(async () => {
    if (!S.root) { const r = (await api('/api/folder-access')).roots; if (!r.length) { $('#view').innerHTML = '<p class="dim">Er is nog geen root folder.</p>'; return; } S.roots = r; S.root = r[0].id; }
    const d = await api(`/api/folder-access?root=${S.root}&path=${encodeURIComponent(S.path.join('/'))}`);
    const crumbs = [S.roots.find(r => r.id === S.root).name, ...S.path].map((x, i, a) => i === a.length - 1 ? `<b>📁 ${esc(x)}</b>` : `<a href="#" data-crumb="${i}">📁 ${esc(x)}</a>`).join(' <span class="dim">›</span> ');
    $('#view').innerHTML = `<p class="dim">Modellen die niet in een schoolmap staan, zijn voor alle leerlingen zichtbaar. Haal het vinkje weg bij een map om hem (en alles daarin) voor leerlingen te verbergen. Medewerkers en beheerders zien alles.</p>
${S.roots.length > 1 ? `<select id="aroot">${S.roots.map(r => `<option value="${r.id}" ${r.id === S.root ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>` : ''}
<div style="margin:8px 0">${crumbs}</div>${d.inherited ? '<p class="warn">Deze map is verborgen via een bovenliggende map.</p>' : ''}
${d.dirs.length ? tbl(['Map', 'Zichtbaar voor leerlingen'], d.dirs.map(x => `<tr><td><a href="#" data-dir="${esc(x.name)}">📁 ${esc(x.name)}</a></td><td><input type="checkbox" data-vis="${esc(x.name)}" ${x.hidden || x.inherited ? '' : 'checked'} ${x.inherited ? 'disabled' : ''}></td></tr>`)) : '<p class="dim">Geen submappen.</p>'}`;
  });
  $('#view').onclick = run(async e => {
    const t = e.target, a = t.closest ? t.closest('[data-crumb],[data-dir]') : null; if (!a) return;
    e.preventDefault();
    if (a.dataset.dir) S.path.push(a.dataset.dir); else S.path = S.path.slice(0, +a.dataset.crumb);
    await load();
  });
  $('#view').onchange = run(async e => {
    const t = e.target;
    if (t.id === 'aroot') { S.root = +t.value; S.path = []; return load(); }
    if (t.dataset.vis) { await api('/api/folder-access/hide', 'POST', {root: S.root, path: [...S.path, t.dataset.vis].join('/'), hidden: !t.checked}); toast('Opgeslagen'); await load(); }
  });
  await load();
};
V.reports = async () => {
  $('#title').textContent = 'Meldingen';
  const load = run(async () => {
    const rs = (await api('/api/reports')).reports;
    $('#view').innerHTML = rs.length ? tbl(['Tijd', 'Model', 'School', 'Reden', 'Gemeld door', ''], rs.map(r => `<tr><td class="dim">${fdate(r.ts)}</td><td>${esc(r.model)}${r.hidden ? ' <span class="warn">(verborgen)</span>' : ''}</td><td>${esc(r.school)}</td><td>${esc(r.reason)}</td><td>${esc(r.reporter)}</td>
<td style="white-space:nowrap"><button data-a="dismiss" data-id="${r.id}">Negeren</button> <button data-a="hide" data-id="${r.id}">Verbergen</button> <button class="d" data-a="delete" data-id="${r.id}">Verwijderen</button></td></tr>`)) : '<p class="dim">Geen openstaande meldingen.</p>';
  });
  onRev = load;
  $('#view').onclick = run(async e => {
    const t = e.target; if (!t.dataset.a) return;
    if (t.dataset.a === 'delete' && !confirm('Dit model verwijderen? Het gaat naar de prullenbak.')) return;
    await api('/api/reports/' + t.dataset.id, 'POST', {action: t.dataset.a}); toast('Afgehandeld'); load();
  });
  await load();
};
function showCreds(rows, title) {
  const ok = rows.filter(r => !r.error), bad = rows.filter(r => r.error);
  const el = overlay(`<h3 style="margin-top:0">${esc(title)}</h3><p class="warn">Bewaar deze wachtwoorden nu: ze worden maar één keer getoond.</p>
${tbl(['Naam', 'Klas', 'Gebruikersnaam', 'Wachtwoord'], ok.map(r => `<tr><td>${esc(r.name || '')}</td><td>${esc(r.klas || '')}</td><td><code>${esc(r.username)}</code></td><td><code>${esc(r.password)}</code></td></tr>`))}
${bad.length ? `<p class="warn">Niet gelukt:</p>` + bad.map(r => `<div class="dim">Regel ${r.line || ''} ${esc(r.name || '')}: ${esc(r.error)}</div>`).join('') : ''}
<div class="row" style="margin-top:14px;justify-content:flex-end"><button id="cdl">⬇ CSV downloaden</button><button id="cpr">🖨 Afdrukken</button><button class="p" id="ccl">Sluiten</button></div>`, 'credsm');
  el.onclick = e => {
    const t = e.target;
    if (t.id === 'ccl') el.remove();
    if (t.id === 'cpr') window.print();
    if (t.id === 'cdl') {
      const csv = 'naam;klas;gebruikersnaam;wachtwoord\n' + ok.map(r => [r.name, r.klas, r.username, r.password].map(x => String(x || '').replace(/;/g, ',')).join(';')).join('\n');
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv'})); a.download = 'accounts.csv'; a.click();
    }
  };
}
V.pupils = async () => {
  $('#title').textContent = 'Leerlingen';
  let sid = ''; const q = () => adm() && sid ? '?school_id=' + sid : '';
  let scHTML = ''; if (adm()) { const sc = (await api('/api/schools')).schools; sid = sc.length ? sc[0].id : ''; scHTML = `<select id="psc">${sc.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('')}</select>`; }
  $('#tools').innerHTML = scHTML + '<button id="pnew" class="p">+ Leerling</button><button id="pimp">⬆ CSV importeren</button>';
  if ($('#psc')) $('#psc').onchange = e => { sid = e.target.value; load(); };
  const load = run(async () => {
    const us = (await api('/api/school/users' + q())).users;
    $('#view').innerHTML = `<p class="dim">${us.length} leerlingen. Importeer een CSV met de kolommen <code>naam</code>, <code>klas</code> en eventueel <code>gebruikersnaam</code>, <code>wachtwoord</code> en <code>email</code>. Ontbrekende gebruikersnamen en wachtwoorden worden aangemaakt.</p>`
      + (us.length ? tbl(['<input type="checkbox" id="psel" title="Alles selecteren">', 'Naam', 'Gebruikersnaam', 'Inlog', 'Klas', 'Uploaden', 'Actief', 'Laatst ingelogd', ''], us.map(u => `<tr><td><input type="checkbox" data-sel="${u.id}"></td><td>${esc(u.display_name)}</td><td><code>${esc(u.username)}</code></td><td>${loginKind(u)}</td><td><input data-k="${u.id}" value="${esc(u.klas)}" size="5"></td><td><input type="checkbox" data-up="${u.id}" ${u.can_upload ? 'checked' : ''}></td><td><input type="checkbox" data-act="${u.id}" ${u.active ? 'checked' : ''}></td><td class="dim">${fdate(u.last_login)}</td><td>${u.ms ? '' : `<button data-pw="${u.id}">Nieuw wachtwoord</button> `}<button data-del="${u.id}" title="Leerling verwijderen">🗑</button></td></tr>`)) : '');
    $('#tools').querySelector('#pdi')?.remove();
    if (us.some(u => !u.active)) $('#tools').insertAdjacentHTML('beforeend', '<button id="pdi">🗑 Verwijder alle gedeactiveerde leerlingen</button>');
    $('#pdi') && ($('#pdi').onclick = () => removePupils({inactive: true}));
    updSel();
  });
  const form = (url, extra) => ({school_id: sid || undefined, ...extra});
  const sels = () => [...document.querySelectorAll('[data-sel]:checked')].map(x => +x.dataset.sel);
  function updSel() {
    $('#tools').querySelector('#pdel')?.remove(); const n = sels().length;
    if (n) { $('#tools').insertAdjacentHTML('beforeend', `<button id="pdel">🗑 Verwijder geselecteerde (${n})</button>`); $('#pdel').onclick = () => removePupils({ids: sels()}); }
  }
  function removePupils(body) {
    return run(async () => {
      const pv = await api('/api/school/users/remove', 'POST', {...body, preview: true, school_id: sid || undefined});
      if (!pv.count) { toast('Geen leerlingen gevonden'); return; }
      const el = overlay(`<h3 style="margin-top:0">Leerlingen verwijderen?</h3>
<p>${pv.count} ${pv.count === 1 ? 'leerling' : 'leerlingen'} met ${pv.models} ${pv.models === 1 ? 'bestand' : 'bestanden'} wordt definitief verwijderd. Het account kan niet worden teruggezet.</p>
<label style="display:block;margin:10px 0"><input type="checkbox" id="rfd"> Ook alle bestanden van deze leerling(en) verwijderen <span class="dim">(ze gaan naar de map .prullenbak en niet meer in de bibliotheek)</span></label>
<p class="dim" id="rfk">De bestanden blijven bewaard; alleen medewerkers zien ze nog.</p>
${pv.ms ? `<p class="warn">${pv.ms} ${pv.ms === 1 ? 'leerling logt' : 'leerlingen loggen'} in met Microsoft. Haal ze ook uit de groep in Microsoft Entra, anders wordt het account bij de volgende inlog opnieuw aangemaakt.</p>` : ''}
<div class="row" style="margin-top:14px;justify-content:flex-end"><button id="rno">Annuleren</button><button class="p" id="rok">Verwijderen</button></div>`, 'credsm');
      el.onchange = e => { if (e.target.id === 'rfd') $('#rfk').style.display = e.target.checked ? 'none' : ''; };
      el.onclick = run(async e => {
        if (e.target.id === 'rno') el.remove();
        if (e.target.id === 'rok') {
          const r = await api('/api/school/users/remove', 'POST', {...body, files: el.querySelector('#rfd').checked ? 'delete' : 'keep', school_id: sid || undefined});
          el.remove(); toast(r.failed ? `${r.removed} verwijderd, ${r.failed} niet (map kon niet worden verplaatst)` : `${r.removed} ${r.removed === 1 ? 'leerling' : 'leerlingen'} verwijderd`); load();
        }
      });
    })();
  }
  $('#view').onchange = run(async e => {
    const t = e.target, id = t.dataset.k || t.dataset.up || t.dataset.act; if (!id) return;
    await api('/api/school/users/' + id, 'PUT', t.dataset.k ? {klas: t.value, school_id: sid || undefined} : t.dataset.up ? {can_upload: t.checked, school_id: sid || undefined} : {active: t.checked, school_id: sid || undefined}); toast('Opgeslagen');
  });
  $('#view').addEventListener('change', e => { if (e.target.id === 'psel') document.querySelectorAll('[data-sel]').forEach(x => x.checked = e.target.checked); if (e.target.id === 'psel' || e.target.dataset.sel) updSel(); });
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.dataset.del) { removePupils({ids: [+t.dataset.del]}); return; }
    if (t.dataset.pw && confirm('Een nieuw wachtwoord instellen? De leerling wordt uitgelogd.')) { const r = await api('/api/school/users/' + t.dataset.pw, 'PUT', {password: true, school_id: sid || undefined}); const u = $(`[data-pw="${t.dataset.pw}"]`).closest('tr'); showCreds([{name: u.cells[0].textContent, klas: u.querySelector('[data-k]').value, username: u.cells[1].textContent, password: r.password}], 'Nieuw wachtwoord'); }
  });
  $('#pnew').onclick = run(async () => {
    const name = prompt('Naam van de leerling'); if (!name) return;
    const klas = prompt('Klas (optioneel)') || '';
    const un = name.trim().toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const r = await api('/api/school/users', 'POST', {username: prompt('Gebruikersnaam', un) || un, display_name: name, klas, school_id: sid || undefined});
    showCreds([{name, klas, username: r.username, password: r.password}], 'Leerling aangemaakt'); load();
  });
  $('#pimp').onclick = () => {
    const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.csv,.txt';
    inp.onchange = run(async () => {
      const f = inp.files[0]; if (!f) return;
      const send = prev => new Promise((res, rej) => { const x = new XMLHttpRequest(), fd = new FormData(); fd.append('file', f); if (prev) fd.append('preview', '1'); if (sid) fd.append('school_id', sid);
        x.open('POST', '/api/school/users/import'); x.setRequestHeader('X-Requested-With', 'modelbib'); x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (_) {} x.status < 300 ? res(j) : rej(new Error(j.error || 'Mislukt')); }; x.send(fd); });
      const pv = await send(true);
      if (!confirm(`${pv.ok} leerlingen worden aangemaakt, ${pv.updated || 0} bestaande leerlingen worden bijgewerkt (klas en naam).${pv.failed ? ` ${pv.failed} regels hebben een fout.` : ''} Doorgaan?`)) return;
      const r = await send(false), made = r.rows.filter(x => !x.updated);
      if (made.some(x => !x.error)) showCreds(made, `${r.ok} leerlingen aangemaakt${r.updated ? `, ${r.updated} bijgewerkt` : ''}`); else if (made.length) showCreds(made, 'Niet gelukt'); else toast(`${r.updated} leerlingen bijgewerkt`);
      load();
    });
    inp.click();
  };
  onRev = load; await load();
};
V['settings/microsoft'] = async () => {
  $('#title').textContent = 'Instellingen — Microsoft';
  const s = await api('/api/settings'), ck = (id, v) => `<input type="checkbox" id="${id}" ${v ? 'checked' : ''}>`;
  $('#view').innerHTML = `<h3>Inloggen met Microsoft (Entra ID)</h3>
<p class="dim">Maak in Microsoft Entra een app-registratie (één tenant, type Web) met de omleidings-URL hieronder. Geef de app het recht User.Read (delegated). Zet bij Token configuration een groepsclaim aan (Security groups). Vul de groep-ID's van elke school in bij Instellingen › Scholen. Een gebruiker krijgt de rol en school van zijn groep: eerst de beheerdersgroep, dan medewerkers, dan leerlingen.</p>
<div class="form"><label>Publiek adres van Modelarr</label><input id="mpu" value="${esc(s.public_url)}" placeholder="https://modelarr.school.nl"><small>Alleen het basisadres, dus zonder iets erachter (geen /api/ms/callback). Voor testen op deze computer: http://localhost:8765. Open Modelarr ook via dit adres als je met Microsoft inlogt.</small>
<span id="mpw" class="warn" style="display:none;grid-column:1/-1"></span>
<label>Omleidings-URL (Redirect URI)</label><span style="display:flex;gap:8px;align-items:center"><input readonly id="msr" value="${esc(s.ms_redirect)}" onclick="this.select()" style="flex:1"><button id="mcopy" type="button">Kopiëren</button></span><small>Dit is het adres dat je in Entra invult onder Authentication › Add a platform › Web. Het past zich aan wanneer je het publieke adres wijzigt.</small>
<label>Tenant-ID</label><input id="mt" value="${esc(s.ms_tenant)}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"><label>Client-ID (Application ID)</label><input id="mc" value="${esc(s.ms_client_id)}">
<label>Clientgeheim</label><input id="ms" type="password" autocomplete="new-password" placeholder="${s.ms_secret_set ? '•••••••• (opgeslagen; laat leeg om te behouden)' : ''}"><label>Groep-ID beheerders</label><input id="mag" value="${esc(s.ms_admin_group)}">
<label>Inloggen met Microsoft</label><label>${ck('men', s.ms_enabled)} Inloggen met Microsoft aanzetten</label><label>Alleen Microsoft</label><label>${ck('mon', s.ms_only)} Wachtwoordformulier verbergen <span class="dim">(lokale beheerders loggen daarna in via de link onder aan de pagina)</span></label>
<label>Klas</label><label>${ck('mkl', s.ms_klas)} Klas van leerlingen overnemen uit het veld Afdeling (Department) in Microsoft</label>
<span></span><span><button class="p" id="mssave">Opslaan</button> ${s.ms_secret_set ? '<button id="msclr">Geheim wissen</button>' : ''}</span></div>
`;
  const redir = () => { const u = $('#mpu').value.trim().replace(/^(https?:\/\/[^/]+).*$/i, '$1') || location.origin; $('#msr').value = u + '/api/ms/callback'; const w = $('#mpw'), pu = $('#mpu').value.trim().replace(/^(https?:\/\/[^/]+).*$/i, '$1'); w.style.display = pu && pu.toLowerCase() !== location.origin.toLowerCase() ? '' : 'none'; w.textContent = 'Let op: je gebruikt Modelarr nu via ' + location.origin + ', niet via het publieke adres. Open Modelarr via het publieke adres voordat je met Microsoft inlogt.'; };
  $('#mpu').oninput = redir; redir();
  $('#view').onclick = run(async e => {
    const t = e.target;
    if (t.id === 'mcopy') { $('#msr').select(); try { await navigator.clipboard.writeText($('#msr').value); toast('Gekopieerd'); } catch (_) { document.execCommand('copy'); toast('Gekopieerd'); } }
    if (t.id === 'mssave') { const b = {public_url: $('#mpu').value, ms_tenant: $('#mt').value, ms_client_id: $('#mc').value, ms_admin_group: $('#mag').value, ms_enabled: $('#men').checked, ms_only: $('#mon').checked, ms_klas: $('#mkl').checked}; if ($('#ms').value) b.ms_client_secret = $('#ms').value; await api('/api/settings', 'POST', b); toast('Opgeslagen'); return V['settings/microsoft'](); }
    if (t.id === 'msclr' && confirm('Het opgeslagen clientgeheim wissen? Inloggen met Microsoft stopt dan.')) { await api('/api/settings', 'POST', {ms_secret_clear: true}); toast('Geheim gewist'); return V['settings/microsoft'](); }
  });
};
V['settings/schools'] = async () => {
  $('#title').textContent = 'Instellingen — Scholen';
  const load = run(async () => {
    const [d, roots] = await Promise.all([api('/api/schools'), api('/api/roots')]);
    const ro = roots.roots || roots, opt = (cur) => `<option value="">–</option>` + ro.map(r => `<option value="${r.id}" ${r.id === cur ? 'selected' : ''}>${esc(r.path)}</option>`).join('');
    $('#view').innerHTML = `<p class="dim">Elke school heeft een eigen map in een root folder (<code>&lt;map&gt;/leerlingen/…</code> en <code>&lt;map&gt;/medewerkers/…</code>). Laat de limiet leeg om de algemene limiet te gebruiken (${d.default_quota_mb || 'onbeperkt'} MB, instelbaar onder Algemeen).</p>`
      + tbl(['School', 'Mapnaam', 'Root folder', 'Groep-ID leerlingen', 'Groep-ID medewerkers', 'Limiet leerling (MB)', 'Actief', 'Leerlingen', 'Medewerkers', 'Modellen', ''], d.schools.map(s => `<tr data-s="${s.id}"><td><input data-f="name" value="${esc(s.name)}"></td><td><input data-f="slug" value="${esc(s.slug)}" size="14" ${s.models ? 'disabled' : ''}></td><td><select data-f="root_id">${opt(s.root_id)}</select></td><td><input data-f="group_id" value="${esc(s.group_id || '')}" size="20"></td><td><input data-f="staff_group_id" value="${esc(s.staff_group_id || '')}" size="20"></td><td><input data-f="quota_mb" type="number" min="0" value="${s.quota_mb ?? ''}" style="width:90px"></td><td><input type="checkbox" data-f="active" ${s.active ? 'checked' : ''}></td><td>${s.students}</td><td>${s.staff}</td><td>${s.models}</td><td><button data-sv="${s.id}">Opslaan</button></td></tr>`).concat([`<tr data-s="new"><td><input data-f="name" placeholder="Nieuwe school"></td><td><input data-f="slug" placeholder="(automatisch)" size="14"></td><td><select data-f="root_id">${opt(ro.length === 1 ? ro[0].id : null)}</select></td><td><input data-f="group_id" size="20"></td><td><input data-f="staff_group_id" size="20"></td><td><input data-f="quota_mb" type="number" min="0" style="width:90px"></td><td><input type="checkbox" data-f="active" checked></td><td></td><td></td><td></td><td><button class="p" data-sv="new">Toevoegen</button></td></tr>`]));
  });
  $('#view').onclick = run(async e => {
    const id = e.target.dataset.sv; if (!id) return;
    const tr = e.target.closest('tr'), b = {}; tr.querySelectorAll('[data-f]').forEach(i => b[i.dataset.f] = i.type === 'checkbox' ? i.checked : i.value);
    if (id === 'new') await api('/api/schools', 'POST', b); else await api('/api/schools/' + id, 'PUT', b);
    toast('Opgeslagen'); load();
  });
  await load();
};

async function boot() {
  try { ME = await api('/api/me'); } catch (e) { /* server tijdelijk weg: toon de app zonder account */ }
  if (ME.auth && !ME.user) return showLogin();
  buildNav(); route(); poll();
}
let loginUp = false;
function showLogin(msg) {
  ME = {...ME, user: null};  // sessie weg: stop met pollen
  if (loginUp) { if (msg && $('#le')) $('#le').textContent = msg; return; }  // al zichtbaar: invoer niet wissen
  loginUp = true;
  const pw = !ME.ms_only || /[?&]lokaal\b/.test(location.search);  // alleen Microsoft: het wachtwoordformulier blijft verborgen (noodingang: ?lokaal=1 voor lokale beheerders)
  $('#nav').innerHTML = ''; $('#top').style.display = 'none'; $('#banner').style.display = 'none'; closeModal();
  $('#view').innerHTML = `<div class="login"><img src="/static/logo.svg" alt="" width="72" height="72" style="align-self:center"><h2 style="text-align:center;margin:0">Model<span style="color:#8fb0ff">arr</span> School</h2><p class="dim">Log in om verder te gaan.</p>${ME.ms ? msButton : ''}${pw ? `${ME.ms ? '<p class="dim" style="text-align:center;margin:4px 0">of met een lokaal account</p>' : ''}<input id="lu" placeholder="Gebruikersnaam of e-mailadres" autocomplete="username"><input id="lp" type="password" placeholder="Wachtwoord" autocomplete="current-password"><button class="p" id="lb">Inloggen</button>` : ''}<div class="err" id="le">${esc(msg || '')}</div>${!pw ? '<a href="/?lokaal=1" class="dim" style="text-align:center;font-size:12px">Lokale beheerder? Inloggen met wachtwoord</a>' : ''}${langBlock()}</div>`;
  const go = async () => { try { await api('/api/login', 'POST', {username: $('#lu').value, password: $('#lp').value}); location.reload(); } catch (e) { $('#le').textContent = e.message; } };
  $('#view').onclick = e => { if (e.target.dataset.lang) I18N.setLang(e.target.dataset.lang); }; if ($('#lb')) { $('#lb').onclick = go; $('#view').onkeydown = e => { if (e.key === 'Enter') go(); }; $('#lu').focus(); }
}
boot();
