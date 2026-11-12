// Hulpscript voor de Python-tests: leest een JSON-lijst met Nederlandse teksten op stdin en geeft de Engelse vertalingen als JSON.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const st = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'static');
const sb = {localStorage: {getItem: () => 'en', setItem() {}}, navigator: {language: 'en'}, location: {reload() {}}, document: {readyState: 'complete', body: null}};
sb.window = sb; vm.createContext(sb);
for (const f of ['i18n-en.js', 'i18n.js']) vm.runInContext(fs.readFileSync(path.join(st, f), 'utf8'), sb);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(input.map(s => sb.I18N.translate(s, 'en'))));
