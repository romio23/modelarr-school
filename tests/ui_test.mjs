// Interfacetest: voert de ECHTE static/app.js uit (zoals de browser) met een nagebootste pagina en server, en draait daarna
// de controles uit tests/ui/*.js. Gebruik: node tests/ui_test.mjs
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, '..', 'static', 'app.js'), 'utf8').replace(/\nboot\(\);\s*$/, '\n');  // boot() starten de tests zelf
if (/\nboot\(\);\s*$/.test(src)) throw new Error('boot() staat nog aan het eind');
const mkEl = () => ({innerHTML: '', textContent: '', value: '', checked: false, hidden: false, style: {}, dataset: {}, className: '', onclick: null, onkeydown: null, onchange: null, oninput: null,
  classList: {add() {}, remove() {}, toggle() {}, contains: () => false}, focus() {}, click() { if (this.onclick) this.onclick({target: this}); }, setAttribute() {}, removeAttribute() {},
  querySelector: () => null, querySelectorAll: () => [], appendChild() {}, addEventListener() {}, getBoundingClientRect: () => ({width: 800, height: 600}), closest: () => null});
const out = {};
const store = new Map();
const sb = {
  console: {log: (...a) => console.log(...a)}, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {}, Math, JSON, Date, URL, URLSearchParams, Promise, Set, Map, Object, Array, String, Number, RegExp, Error, Intl,
  out, els: out, apiCalls: [], apiImpl: async () => ({}), confirmMsgs: [], confirmAnswer: true, promptAnswer: null,
  document: {querySelector: s => out[s] || (out[s] = mkEl()), querySelectorAll: () => [], addEventListener() {}, createElement: () => mkEl(), body: mkEl(), documentElement: mkEl()},
  localStorage: {getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k)},
  location: {hash: '', reloaded: false, reload() { this.reloaded = true; }}, navigator: {language: 'nl-NL'}, addEventListener() {}, innerWidth: 1280,
};
// Nabootsing van de paginering van /api/library (het echte filteren en sorteren wordt getest in tests/test_library_paging.py)
sb.SRV = (all, u, extra = {}) => {
  const p = new URLSearchParams(String(u).split('?')[1] || ''), ext = p.get('ext') || 'all', a = all.filter(m => ext === 'all' || m.ext === ext);
  const size = +(p.get('size') ?? 100), pages = size ? Math.max(1, Math.ceil(a.length / size)) : 1, page = Math.min(Math.max(0, +p.get('page') || 0), pages - 1);
  return {models: size ? a.slice(page * size, (page + 1) * size) : a, total: a.length, all: all.length, page, pages, size, ids: a.map(m => m.id), exts: [...new Set(all.map(m => m.ext))].sort(),
    categories: [], big_mb: 50, recent_days: 7, local: true, slicer: {name: 'Bambu Studio'}, ...extra};
};
sb.window = sb;
sb.confirm = m => { sb.confirmMsgs.push(m); return sb.confirmAnswer; };
sb.prompt = () => sb.promptAnswer;
sb.alert = () => {};
sb.fetch = async (url, o = {}) => {
  const body = o.body ? JSON.parse(o.body) : undefined, method = o.method || 'GET';
  sb.apiCalls.push([url, method, body]);
  try { const j = await sb.apiImpl(url, method, body); return {ok: true, status: 200, statusText: 'OK', json: async () => j ?? {}}; }
  catch (e) { return {ok: false, status: e.status || 400, statusText: 'Bad Request', json: async () => ({error: e.message, login: e.login})}; }
};
const ctx = vm.createContext(sb);
for (const f of ['i18n-en.js', 'i18n.js']) vm.runInContext(fs.readFileSync(path.join(here, '..', 'static', f), 'utf8'), ctx, {filename: f});
vm.runInContext(src, ctx, {filename: 'static/app.js'});
vm.runInContext('var __origRoute = route, __origPoll = poll;', ctx);  // om na onderdelen die ze vervangen de echte functies terug te zetten
let ok = 0, bad = 0;
sb.console.log = (...a) => { const s = a.join(' '); if (process.env.DEBUG) console.log(s); if (s.startsWith('OK')) ok++; else if (s.startsWith('FOUT')) { bad++; console.log(s); } };
const dir = path.join(here, 'ui');
const only = process.argv[2] && new RegExp(process.argv[2]);  // optioneel: alleen onderdelen waarvan de bestandsnaam hierbij past, bijv. node tests/ui_test.mjs zip
const RESET = `L.q = ''; L.cat = 'all'; L.ext = 'all'; L.flt = 'all'; L.sort = 'name'; L.sel = new Set(); L.view = 'posters'; L.printers = []; L.logs = {};
  L.d = {categories: [], models: [], slicer: {name: 'Bambu Studio'}, local: false, big_mb: 50, recent_days: 7}; ME = {auth: false, user: null, role: 'admin', can_download: true};
  apiCalls.length = 0; apiImpl = async () => ({}); confirmMsgs.length = 0; confirmAnswer = true; promptAnswer = null; openId = null; loginUp = false; route = __origRoute; poll = __origPoll;`;
for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.js') && (!only || only.test(x))).sort()) {
  vm.runInContext(RESET, ctx);  // elk onderdeel begint met een schone status
  try { await vm.runInContext(`(async () => {\n${fs.readFileSync(path.join(dir, f), 'utf8')}\n})()`, ctx, {filename: f}); }
  catch (e) { bad++; console.log(`FOUT ${f}: uitzondering: ${e.message}\n${(e.stack || '').split('\n').slice(0, 4).join('\n')}`); }
}
console.log(`${ok} controles goed, ${bad} fout`);
process.exit(bad ? 1 : 0);
