// Test van de Engelse versie. Gebruik: node tests/i18n_test.mjs
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url)), st = path.join(here, '..', 'static');
function load(lang, nav = 'nl-NL') {
  const store = new Map(lang ? [['lang', lang]] : []);
  const sb = {localStorage: {getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v)}, navigator: {language: nav}, location: {reload() { sb.reloaded = true; }}, document: {readyState: 'complete', body: null}, reloaded: false};
  sb.window = sb; vm.createContext(sb);
  for (const f of ['i18n-en.js', 'i18n.js']) vm.runInContext(fs.readFileSync(path.join(st, f), 'utf8'), sb);
  return {I: sb.I18N, sb, store};
}
let ok = 0, bad = 0;
const t = (n, good, extra = '') => { if (good) ok++; else { bad++; console.log('FOUT', n, extra); } };
const {I: en} = load('en'), {I: nl} = load('nl');
const base = JSON.parse(fs.readFileSync(path.join(here, 'i18n_baseline.json'), 'utf8')), same = new Set(base.same_ok);
// 1. elke tekst die de app kan tonen heeft een Engelse vertaling (losse zinsdelen mogen binnen een tekst vertaald worden)
const trans = s => [s, '1 ' + s, s + ' 1'].some(x => en.translate(x, 'en') !== x);
const miss = base.js.filter(s => !same.has(s) && /[A-Za-zÀ-ÿ]{3}/.test(s) && !trans(s));
t('alle teksten van de pagina hebben een vertaling', miss.length === 0, '\n   ontbreekt: ' + JSON.stringify(miss));
const missPy = base.py.filter(s => !same.has(s) && !trans(s.replace(/\{\}/g, '7')));
t('alle serverteksten (meldingen, gezondheid, geschiedenis, taken) hebben een vertaling', missPy.length === 0, '\n   ontbreekt: ' + JSON.stringify(missPy));
// 2. samengestelde zinnen met ingevulde waarden
const S = [
  ['3 platen, grootste 300 × 300 × 3 mm', '3 plates, largest 300 × 300 × 3 mm'], ['Past op (per plaat): ', 'Fits on (per plate): '], ['✗ A1 mini (plaat 3 te groot)', '✗ A1 mini (plate 3 too large)'],
  ['12 van 40', '12 of 40'], ['3 geselecteerd', '3 selected'], ['Categorie toegevoegd aan 5 modellen', 'Category added to 5 models'], ['Bijgewerkt: 7 modellen', 'Updated: 7 models'], ['✓ Opgeslagen', '✓ Saved'],
  ['2 gelukt, 1 mislukt', '2 succeeded, 1 failed'], ['Toegevoegd: 17-10-2026, 17:31:22', 'Added: 17-10-2026, 17:31:22'], ['83.8 × 42 × 7 mm · 6.236 driehoeken · 703 KB', '83.8 × 42 × 7 mm · 6.236 triangles · 703 KB'],
  ['Account "kees" verwijderen?', 'Delete account "kees"?'], ['Gevonden op de nieuwe plek: 11 van 12 modellen.', 'Found at the new location: 11 of 12 models.'], ['Op het nieuwe pad zijn maar 1 van 3 bestanden gevonden', 'Only 1 of 3 files found at the new path'],
  ['Gast downloadde doos.stl', 'Gast downloaded doos.stl'], ['Recent toegevoegd (7 dgn)', 'Recently added (7 days)'], ['▶ Openen in Bambu Studio', '▶ Open in Bambu Studio'], ['Print gelogd en 12.5 g afgetrokken in Spoolman', 'Print logged and 12.5 g deducted in Spoolman'],
  ['  ★ Favoriet ', '  ★ Favorite '], ['Nog 3 bestand(en) worden vergeleken…', 'Still comparing 3 file(s)…'], ['plaat 5 bestaat niet in dit bestand', 'plate 5 does not exist in this file'], ['… en 4 eerdere', '… and 4 earlier'],
  ['Openen mislukt: geen toegang', 'Opening failed: geen toegang'], ['/tmp/a.stl verplaatst naar .prullenbak (dubbel van b.stl)', '/tmp/a.stl moved to .prullenbak (duplicate of b.stl)'], ['Root folder niet bereikbaar: /models (mount offline of verkeerd pad?)', 'Root folder not reachable: /models (mount offline or wrong path?)'],
];
for (const [nlText, want] of S) { const got = en.translate(nlText, 'en'); t('voorbeeld: ' + nlText, got === want, `\n   gekregen: ${JSON.stringify(got)}\n   verwacht: ${JSON.stringify(want)}`); }
// 3. gegevens van de gebruiker blijven ongemoeid
for (const u of ['Raspberry Pi Rack', 'Jan van Dijk', 'Lab-rax-edge-4U-3U', 'Rek voor 10 inch server', 'Cable+Comb+Horizontal', '\\\\192.168.1.10\\3d\\10 inch rack\\Lab Rax', 'KWS RACK Side Panel Generator 20+ Patterns', '12', '']) t('gebruikersgegevens ongewijzigd: ' + u, en.translate(u, 'en') === u);
t('Nederlands blijft Nederlands (geen vertaling)', S.every(([a]) => nl.translate(a, 'nl') === a) && nl.tr('Bibliotheek') === 'Bibliotheek' && en.tr('Bibliotheek') === 'Library');
// 4. taalkeuze: opgeslagen keuze, anders de browsertaal
t('taalkeuze: opgeslagen keuze gaat voor, anders browsertaal (nl -> Nederlands, anders Engels)', load('en', 'nl-NL').I.lang === 'en' && load('nl', 'en-US').I.lang === 'nl' && load(null, 'nl-BE').I.lang === 'nl' && load(null, 'en-GB').I.lang === 'en' && load(null, 'de-DE').I.lang === 'en');
t('datum/getalnotatie volgt de taal', load('en').I.LOC === 'en-GB' && load('nl').I.LOC === 'nl-NL');
const sw = load('nl'); sw.I.setLang('en'); t('taal wisselen: keuze opgeslagen en pagina herladen', sw.store.get('lang') === 'en' && sw.sb.reloaded === true);
// 5. de pagina zelf: tekst, tooltips en placeholders worden vervangen; invoervelden en gebruikersgegevens niet
const T = (v) => ({nodeType: 3, nodeValue: v, parentNode: null});
const E = (name, attrs = {}, kids = []) => { const e = {nodeType: 1, nodeName: name, childNodes: kids, getAttribute: k => attrs[k], setAttribute: (k, v) => { attrs[k] = v; }, attrs}; kids.forEach(k => { k.parentNode = e; }); return e; };
const area = E('TEXTAREA', {placeholder: 'Notities'}, [T('Mijn notitie: Opslaan')]), nm = T('Raspberry Pi Rack'), cnt = T('12 van 40');
const tree = E('DIV', {}, [E('H3', {}, [T('Printlogboek')]), E('INPUT', {placeholder: 'Zoeken… (bijv. rack ext:3mf cat:server map:lab)', title: 'Sluiten'}), E('BUTTON', {}, [T('★ Favoriet')]), E('SCRIPT', {}, [T('Opslaan')]), area, E('DIV', {}, [nm]), E('B', {}, [cnt])]);
en.walk(tree);
const flat = []; (function w(n) { if (n.nodeType === 3) flat.push(n.nodeValue); else n.childNodes.forEach(w); })(tree);
t('pagina: tekst vertaald', flat.includes('Print log') && flat.includes('★ Favorite') && flat.includes('12 of 40'));
t('pagina: placeholder en tooltip vertaald', tree.childNodes[1].attrs.placeholder.startsWith('Search… (e.g. rack ext:3mf cat:server folder:lab)') && tree.childNodes[1].attrs.title === 'Close');
t('pagina: modelnaam, notitieveld en script blijven ongemoeid', nm.nodeValue === 'Raspberry Pi Rack' && area.childNodes[0].nodeValue === 'Mijn notitie: Opslaan' && area.attrs.placeholder === 'Notities' && tree.childNodes[3].childNodes[0].nodeValue === 'Opslaan');
const once = JSON.stringify(flat); en.walk(tree); const flat2 = []; (function w(n) { if (n.nodeType === 3) flat2.push(n.nodeValue); else n.childNodes.forEach(w); })(tree);
t('pagina: nogmaals toepassen verandert niets (geen dubbele vertaling)', JSON.stringify(flat2) === once);
cnt.nodeValue = 'Alle modellen'; en.walk(cnt); t('pagina: later bijgewerkte tekst wordt opnieuw vertaald', cnt.nodeValue === 'All models');
const nlTree = E('DIV', {}, [T('Bibliotheek'), E('INPUT', {placeholder: 'Zoeken…'})]); nl.walk(nlTree); t('Nederlands: de pagina blijft ongewijzigd', nlTree.childNodes[0].nodeValue === 'Bibliotheek' && nlTree.childNodes[1].attrs.placeholder === 'Zoeken…');
// 6. nieuwe teksten in app.js zonder vertaling opsporen (alleen duidelijke zinnen: hoofdletter, tussen tags)
const dec = x => x.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#92;/g, '\\').replace(/&amp;/g, '&');
const code = fs.readFileSync(path.join(st, 'app.js'), 'utf8'), found = new Set();
for (const m of code.matchAll(/>([A-ZÀ-Ý][^<>{}$`'"\n\\]{3,100})</g)) found.add(dec(m[1].trim()));
for (const m of code.matchAll(/\b(?:title|placeholder|aria-label)="([A-ZÀ-Ý][^"{}$]{3,200})"/g)) found.add(dec(m[1].trim()));
const unknown = [...found].filter(s => !same.has(s) && /[a-zà-ÿ]{3}/.test(s) && !trans(s) && !/^(Python|Platform|Database|Modelarr)$/.test(s));
t('app.js: geen nieuwe zichtbare tekst zonder vertaling', unknown.length === 0, '\n   nog te vertalen (voeg toe aan de woordenlijst): ' + JSON.stringify(unknown));
console.log(`${ok} controles goed, ${bad} fout`);
process.exit(bad ? 1 : 0);
