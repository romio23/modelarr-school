#!/usr/bin/env python3
"""Maakt de GitHub-wiki (map `wiki/`) uit README.md (Nederlands) en README-EN.md (Engels). De README's blijven de bron:
pas die aan en draai dit script opnieuw. Gebruik:  python tools/make_wiki.py [uitvoermap]   (standaard: ./wiki)
Een GitHub-wiki is een aparte git-repository (<repo>.wiki.git) met gewone Markdown-bestanden: kopieer de inhoud van de uitvoermap erheen."""
import os, re, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'wiki')

def parse(path):
    """-> (intro, [ {title, body, subs:[{title, body}] } ]); kopjes tellen niet binnen codeblokken."""
    lines = open(path, encoding='utf-8').read().split('\n')
    intro, secs, fence = [], [], False
    for ln in lines:
        if ln.lstrip().startswith('```'):
            fence = not fence
        if not fence and ln.startswith('## '):
            secs.append(dict(title=ln[3:].strip(), body=[], subs=[])); continue
        if not fence and ln.startswith('### ') and secs:
            secs[-1]['subs'].append(dict(title=ln[4:].strip(), body=[])); continue
        (secs[-1]['subs'][-1]['body'] if secs and secs[-1]['subs'] else secs[-1]['body'] if secs else intro).append(ln)
    clean = lambda b: '\n'.join(b).strip('\n')
    for s in secs:
        s['body'] = clean(s['body'])
        for u in s['subs']:
            u['body'] = clean(u['body'])
    return clean(intro), secs

# (slug EN, titel EN, slug NL, titel NL, onderdelen). ('s', n) = hele sectie n; ('i', n) = alleen het stuk vóór de ###-kopjes; ('u', n, m) = subsectie m
PAGES = [
    ('Installation', 'Installation', 'Installatie', 'Installatie', [('i', 2)]),
    ('Installation-Windows', 'Installation: Windows', 'Installatie-Windows', 'Installatie: Windows', [('s', 1)]),
    ('Installation-Synology', 'Installation: Docker on a Synology', 'Installatie-Synology', 'Installatie: Docker op een Synology', [('u', 2, 0)]),
    ('Installation-Docker', 'Installation: Docker on Linux or PC', 'Installatie-Docker', 'Installatie: Docker op Linux of pc', [('u', 2, 1)]),
    ('Installation-Proxmox-LXC', 'Installation: Proxmox LXC', 'Installatie-Proxmox-LXC', 'Installatie: Proxmox LXC', [('u', 2, 2)]),
    ('Configuration', 'Configuration', 'Configuratie', 'Configuratie', [('s', 3)]),
    ('Updating', 'Updating', 'Bijwerken', 'Bijwerken', [('s', 27)]),
    ('Moving-and-Migrating', 'Moving and migrating', 'Verhuizen-en-migreren', 'Verhuizen en migreren', [('s', 20)]),
    ('Scanning-and-Search', 'Scanning and search', 'Scannen-en-zoeken', 'Scannen en zoeken', [('s', 5), ('s', 6)]),
    ('Organizing', 'Organizing the library', 'Indelen', 'De bibliotheek indelen', [('s', 8)]),
    ('Duplicates-and-Trash', 'Duplicates and trash', 'Duplicaten-en-prullenbak', 'Duplicaten en prullenbak', [('s', 7)]),
    ('Notes-and-Favorites', 'Notes, favorites and print status', 'Notities-en-favorieten', 'Notities, favorieten en printstatus', [('s', 10)]),
    ('Thumbnails-and-File-Types', 'Thumbnails and file types', 'Thumbnails-en-bestandstypen', 'Thumbnails en bestandstypen', [('s', 11), ('s', 12), ('s', 13), ('s', 19), ('s', 26)]),
    ('Printers-and-Slicers', 'Printers, plates and slicers', 'Printers-en-slicers', 'Printers, platen en slicers', [('s', 14), ('s', 16), ('s', 15), ('s', 18)]),
    ('Print-Log-and-Spoolman', 'Print log and Spoolman', 'Printlogboek-en-Spoolman', 'Printlogboek en Spoolman', [('s', 17)]),
    ('Bambuddy', 'Bambuddy integration', 'Bambuddy', 'Bambuddy-koppeling', [('s', 4)]),
    ('Users-and-Security', 'Users and security', 'Gebruikers-en-beveiliging', 'Gebruikers en beveiliging', [('s', 21), ('s', 9)]),
    ('API', 'API and integrations', 'API', 'API en koppelingen', [('s', 22)]),
    ('Backups', 'Backups', 'Back-ups', 'Back-ups', [('s', 23)]),
    ('Language', 'Language', 'Taal', 'Taal', [('s', 24)]),
    ('Development', 'Development and tests', 'Ontwikkeling-en-tests', 'Ontwikkeling en tests', [('s', 25)]),
]
L = {'en': dict(path='README-EN.md', home='Home', homet='Home', prefix='', other='Nederlands', flag='🇳🇱', back='Back to Home', lic=28),
     'nl': dict(path='README.md', home='NL-Home', homet='Home (Nederlands)', prefix='NL-', other='English', flag='🇬🇧', back='Terug naar Home', lic=28)}
data = {k: parse(os.path.join(ROOT, v['path'])) for k, v in L.items()}
a, b = data['en'][1], data['nl'][1]
assert len(a) == len(b) and [len(x['subs']) for x in a] == [len(x['subs']) for x in b], 'README.md en README-EN.md hebben niet dezelfde opbouw'
used = {n for p in PAGES for part in p[4] for n in ([part[1]] if part[0] != 'u' else [])} | {2, 28}
assert used == set(range(1, len(a) + 1)), f'secties zonder pagina: {sorted(set(range(1, len(a) + 1)) - used)}'

def page_of(n):  # sectienummer -> pagina
    return next(p for p in PAGES if any(part[0] != 'u' and part[1] == n for part in p[4]))
def xref(lang, text):
    """zie "Back-ups" -> zie [Back-ups](pagina): koppen van de README worden links naar de bijbehorende wikipagina."""
    for n, sec in enumerate(data[lang][1], 1):
        if n in (2,) or n == 28:
            continue
        pg = page_of(n)
        text = re.sub(r'\b(zie|see|Zie|See) "' + re.escape(sec['title']) + '"', lambda m: f'{m.group(1)} [{sec["title"]}]({slug(lang, pg)})', text)
    return text
def slug(lang, p): return p[0] if lang == 'en' else L['nl']['prefix'] + p[2]
def title(lang, p): return p[1] if lang == 'en' else p[3]
def link(lang, p): return f'[{title(lang, p)}]({slug(lang, p)})'

shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
def write(name, text): open(os.path.join(OUT, name + '.md'), 'w', encoding='utf-8', newline='\n').write(text.rstrip('\n') + '\n')

for lang in ('en', 'nl'):
    secs = data[lang][1]; o = 'nl' if lang == 'en' else 'en'
    for p in PAGES:
        parts = []
        for part in p[4]:
            s = secs[part[1] - 1]  # sectie 1 = eerste ##-kopje; 0 is de inleiding
            if part[0] == 's':
                body = s['body'] + ''.join(f"\n\n### {u['title']}\n\n{u['body']}" for u in s['subs'])
                parts.append((s['title'], body))
            elif part[0] == 'i':
                parts.append((s['title'], s['body']))
            else:
                parts.append((s['subs'][part[2]]['title'], s['subs'][part[2]]['body']))
        body = parts[0][1] if len(parts) == 1 else '\n\n'.join(f'## {t}\n\n{b_}' for t, b_ in parts)
        if p[0] == 'Installation':  # verwijs naar de aparte pagina's
            sub = [q for q in PAGES if q[0].startswith('Installation-')]
            body = body.replace('Windows is covered above. For the other platforms there are step-by-step guides:', 'Step-by-step guides (for Windows see [Installation: Windows](Installation-Windows)):') \
                       .replace('Windows staat hierboven. Voor de andere plekken zijn er stap-voor-stap handleidingen:', 'Stap-voor-stap handleidingen (voor Windows zie [Installatie: Windows](NL-Installatie-Windows)):')
            body += '\n\n## ' + ('Guides' if lang == 'en' else 'Handleidingen') + '\n\n' + '\n'.join(f'- {link(lang, q)}' for q in sub)
        head = f"{L[lang]['flag']} {L[lang]['other']}: [{title(o, p)}]({slug(o, p)}) · [{L[lang]['back']}]({L[lang]['home']})\n\n"
        write(slug(lang, p), f'# {title(lang, p)}\n\n' + head + xref(lang, body))

    # home
    intro = data[lang][0]
    intro = re.sub(r'^> .*README.*\n+', '', intro, flags=re.M).strip()
    intro = intro.replace('# Modelarr (server-versie)', '# Modelarr').replace('# Modelarr (server version)', '# Modelarr')
    toc = '\n'.join(f'- {link(lang, p)}' for p in PAGES)
    sw = f"{L[lang]['flag']} **{L[lang]['other']}:** [{L['nl' if lang == 'en' else 'en']['homet']}]({L['nl' if lang == 'en' else 'en']['home']})"
    lic = secs[L[lang]['lic'] - 1]['body']
    write(L[lang]['home'], intro + f"\n\n{sw}\n\n## " + ('Pages' if lang == 'en' else "Pagina's") + f"\n\n{toc}\n\n## " + ('License' if lang == 'en' else 'Licentie') + f"\n\n{lic.replace('(LICENSE)', '(../blob/main/LICENSE)')}")

# zijbalk en voet (gelden voor de hele wiki)
side = ['**Modelarr**', '', '[Home](Home) · [Home (NL)](NL-Home)', '', '<details open><summary><b>English</b></summary>', '']
side += [f'- {link("en", p)}' for p in PAGES] + ['', '</details>', '', '<details><summary><b>Nederlands</b></summary>', '']
side += [f'- {link("nl", p)}' for p in PAGES] + ['', '</details>']
write('_Sidebar', '\n'.join(side))
write('_Footer', 'Modelarr is MIT-licensed · documentation is generated from README.md / README-EN.md (`tools/make_wiki.py`).')
print(f'{len(os.listdir(OUT))} bestanden in {OUT}')
