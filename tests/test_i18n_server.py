"""Test: elke tekst die de server aan de gebruiker toont (foutmeldingen, gezondheid, geschiedenis, taken) heeft een Engelse vertaling.
Gebruik: python tests/test_i18n_server.py   (vereist node)"""
import ast, json, os, re, subprocess, sys
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = []
def check(n, ok, extra=''): print('OK  ' if ok else 'FOUT', n, extra); (None if ok else bad.append(n))
def parts(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, str): return [n.value]
    if isinstance(n, ast.JoinedStr): return [''.join(v.value if isinstance(v, ast.Constant) else '{}' for v in n.values)]
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add): return parts(n.left) + parts(n.right)
    if isinstance(n, ast.IfExp): return parts(n.body) + parts(n.orelse)
    return []
def candidates(path):
    tree = ast.parse(open(os.path.join(APP, path), encoding='utf-8').read()); out = {}
    def add(node):
        for p in parts(node):
            p = p.strip()
            if re.search(r'[A-Za-zÀ-ÿ]{3}', p) and (' ' in p or p[0].isupper()) and not p.startswith('/'): out[p] = path
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            nm = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ''
            for k in n.keywords:
                if k.arg in ('error', 'msg') or (nm == 'dict' and k.arg in ('name', 'desc')): add(k.value)
            if nm == 'hist': [add(a) for a in n.args[:2]]
        if isinstance(n, ast.Tuple) and len(n.elts) == 2 and isinstance(n.elts[1], ast.Constant) and isinstance(n.elts[1].value, int) and n.elts[1].value >= 400: add(n.elts[0])  # (melding, statuscode)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'append' and n.args and isinstance(n.args[0], ast.Tuple):  # scan-gebeurtenissen (soort, tekst, id)
            for e in n.args[0].elts[:2]: add(e)
    return out
cands = {}
for f in ('app.py', 'render.py'): cands.update(candidates(f))
base = json.load(open(os.path.join(APP, 'tests', 'i18n_baseline.json'), encoding='utf-8')); same = set(base['same_ok'])
items = [c for c in cands if c not in same]
tr = subprocess.run(['node', os.path.join(APP, 'tests', 'i18n_translate.mjs')], input=json.dumps([c.replace('{}', '7') for c in items]), capture_output=True, text=True)
res = json.loads(tr.stdout) if tr.returncode == 0 else []
miss = [c for c, r in zip(items, res) if r == c.replace('{}', '7') and not re.match(r'^[A-Z_]+$', c)]
check(f'{len(cands)} serverteksten gevonden', len(cands) >= 60, len(cands))
check('elke servertekst heeft een Engelse vertaling', tr.returncode == 0 and not miss, '\n   ontbreekt (voeg toe aan de woordenlijst): ' + json.dumps(miss, ensure_ascii=False, indent=1))
sys.exit(1 if bad else 0)
