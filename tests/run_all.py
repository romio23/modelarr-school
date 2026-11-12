"""Draait alle tests (Python en node) en toont een overzicht. Gebruik: python tests/run_all.py [reguliere expressie voor de naam]"""
import glob, os, re, subprocess, sys, tempfile, time
here = os.path.dirname(os.path.abspath(__file__)); only = sys.argv[1] if len(sys.argv) > 1 else ''
jobs = [(os.path.basename(f), [sys.executable, f]) for f in sorted(glob.glob(os.path.join(here, 'test_*.py')) + [os.path.join(here, 'integration_test.py')])]
jobs += [('ui_test.mjs', ['node', os.path.join(here, 'ui_test.mjs')]), ('i18n_test.mjs', ['node', os.path.join(here, 'i18n_test.mjs')])]
bad = []
for name, cmd in jobs:
    if only and not re.search(only, name): continue
    t0 = time.time()
    try: r = subprocess.run(cmd, cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=400, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    except subprocess.TimeoutExpired: print(f'FOUT {name}: te traag (400 s)'); bad.append(name); continue
    out = r.stdout + r.stderr; ok = len(re.findall(r'^OK', out, re.M)) + sum(int(m) for m in re.findall(r'^(\d+) controles goed', out, re.M))
    fails = re.findall(r'^FOUT.*$', out, re.M) + re.findall(r'Traceback', out)
    good = r.returncode == 0 and not fails
    print(f"{'OK  ' if good else 'FOUT'} {name:32s} {ok:4d} goed  {time.time() - t0:5.1f}s"); 
    if not good: bad.append(name); print('\n'.join('     ' + x for x in (fails[:5] or out.strip().splitlines()[-5:])))
print('\nAlles goed.' if not bad else f'\nFout in: {", ".join(bad)}'); sys.exit(1 if bad else 0)
