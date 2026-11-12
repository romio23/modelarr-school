"""Meshes laden (STL/3MF/OBJ/PLY/GLB/GLTF) en thumbnails renderen met numpy + Pillow.
Geen GPU/OpenGL nodig, dus geschikt voor Docker/LXC zonder display."""
import base64
import html
import io
import json
import math
import os
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw

SUPPORTED = {'stl', '3mf', 'obj', 'ply', 'glb', 'gltf'}
EMBED_ONLY = {'fcstd', 'gcode', 'gco'}  # geen mesh-lader, wel een ingebedde afbeelding
CAN_THUMB = SUPPORTED | EMBED_ONLY


class NoPreview(Exception):
    pass

YUP = {'obj', 'glb', 'gltf'}  # Y-up formaten; intern werken we overal Z-up (zoals STL/3MF/slicers)


# Een thumbnail is maar 384 px: meer dan ~250k driehoeken tekenen kost minuten (Pillow, per driehoek) en voegt niets zichtbaars toe.
MAX_TRIS = max(20_000, int(os.environ.get('THUMB_MAX_TRIS', '250000') or 250000))

def _local(e):
    return e.tag.rsplit('}', 1)[-1]


def _all(el, name):
    return [x for x in el.iter() if _local(x) == name]


def _matrix(s):
    m, v = np.eye(4), (np.array(s.split(), float) if s else np.array([]))
    if v.size == 12:  # 3MF: rij-vector notatie
        m[:3, :3], m[:3, 3] = v[:9].reshape(3, 3).T, v[9:]
    return m


def _apply(V, m):
    return V @ m[:3, :3].T + m[:3, 3]


def _join(parts):
    parts = [p for p in parts if len(p[0]) and len(p[1])]
    if not parts:
        raise ValueError('geen geometrie gevonden')
    off = np.cumsum([0] + [len(V) for V, _ in parts[:-1]])
    return np.vstack([V for V, _ in parts]), np.vstack([F + o for (_, F), o in zip(parts, off)])


def _plates(z):
    """Platen uit Metadata/model_settings.config (Bambu Studio / OrcaSlicer): [{'id', 'name', 'items': {(object_id, instance_id)}}]."""
    n = next((x for x in z.namelist() if x.lstrip('/') == 'Metadata/model_settings.config'), None)
    if not n:
        return []
    try:
        root = ET.fromstring(z.read(n))
    except ET.ParseError:
        return []
    out = []
    for pl in root.iter('plate'):
        md = {m.get('key'): m.get('value') for m in pl if _local(m) == 'metadata'}
        items = set()
        for mi in pl:
            if _local(mi) == 'model_instance':
                d = {m.get('key'): m.get('value') for m in mi if _local(m) == 'metadata'}
                if d.get('object_id') is not None:
                    items.add((d['object_id'], int(d.get('instance_id') or 0)))
        out.append(dict(id=int(md.get('plater_id') or len(out) + 1), name=md.get('plater_name') or '', items=items))
    return out


def load_3mf(path, plate=None, per_plate=False):
    """Eigen 3MF-parser: ondersteunt slicer-bestanden (Bambu/Prusa/Cura) met meerdere .model-bestanden,
    components en transformaties."""
    z = zipfile.ZipFile(path)
    docs = {'/' + n.lstrip('/'): ET.fromstring(z.read(n)) for n in z.namelist() if n.lower().endswith('.model')}
    objs = {p: {o.get('id'): o for o in _all(d, 'object')} for p, d in docs.items()}

    def build(p, oid, depth=0):
        el = objs.get(p, {}).get(oid)
        if el is None or depth > 8:
            return []
        parts = []
        for me in [x for x in el if _local(x) == 'mesh']:
            V = np.array([[float(v.get('x')), float(v.get('y')), float(v.get('z'))] for v in _all(me, 'vertex')])
            F = np.array([[int(t.get('v1')), int(t.get('v2')), int(t.get('v3'))] for t in _all(me, 'triangle')])
            if len(V) and len(F):
                parts.append((V, F))
        for c in _all(el, 'component'):
            cp = next((v for k, v in c.attrib.items() if k.rsplit('}', 1)[-1] == 'path'), None) or p
            m = _matrix(c.get('transform'))
            parts += [(_apply(V, m), F) for V, F in build('/' + cp.lstrip('/'), c.get('objectid'), depth + 1)]
        return parts

    root = next((p for p, d in docs.items() if _all(d, 'item')), None)
    if root is None:
        raise ValueError('3MF bevat geen build-items')
    items = _all(docs[root], 'item')
    if per_plate:  # afmetingen per plaat (Bambu Studio / OrcaSlicer), voor de 'past op printer'-controle
        pls = _plates(z)
        if len(pls) < 2:
            return []
        seen, owner = {}, {}
        for it in items:
            oid = it.get('objectid')
            k = seen.get(oid, 0)
            seen[oid] = k + 1
            for p in pls:
                if (oid, k) in p['items']:
                    owner[id(it)] = p['id']
        lo, hi = {}, {}
        for it in items:
            pid = owner.get(id(it))
            if pid is None:
                continue
            m = _matrix(it.get('transform'))
            for V, F in build(root, it.get('objectid')):
                W = _apply(V, m)
                lo[pid] = np.minimum(lo.get(pid, W.min(0)), W.min(0))
                hi[pid] = np.maximum(hi.get(pid, W.max(0)), W.max(0))
        return [dict(id=p['id'], dims=[float(x) for x in hi[p['id']] - lo[p['id']]]) for p in pls if p['id'] in lo]
    if plate:  # alleen de objecten van één plaat
        pl = next((p for p in _plates(z) if p['id'] == plate), None)
        if pl is None:
            raise ValueError(f'plaat {plate} bestaat niet in dit bestand')
        seen, keep = {}, []
        for it in items:
            oid = it.get('objectid')
            k = seen.get(oid, 0)
            seen[oid] = k + 1
            if (oid, k) in pl['items']:
                keep.append(it)
        items = keep or [it for it in items if it.get('objectid') in {o for o, _ in pl['items']}]
    parts = []
    for it in items:
        m = _matrix(it.get('transform'))
        parts += [(_apply(V, m), F) for V, F in build(root, it.get('objectid'))]
    return _join(parts)


def plate_dims(path):
    """[{'id', 'dims'}] per plaat voor een 3MF met meerdere platen; [] als er geen platen zijn."""
    return load_3mf(path, per_plate=True)


def _load_ascii_stl_cr(path, trimesh):
    """ASCII-STL met alleen CR als regeleinde (oud Mac-formaat): trimesh leest dat niet.
    Zet de regeleinden om naar LF en probeer opnieuw (alleen voor tekstbestanden)."""
    import io
    with open(path, 'rb') as f:
        raw = f.read()
    if not raw.lstrip()[:5].lower() == b'solid' or b'\r' not in raw:
        raise ValueError('geen geldig STL-bestand')
    raw = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    return trimesh.load(io.BytesIO(raw), file_type='stl', force='mesh', process=False)


def load_mesh(path, ext, plate=None):
    """Geeft (vertices, faces) terug, altijd Z-up."""
    ext = ext.lower().lstrip('.')
    if ext == '3mf':
        V, F = load_3mf(path, plate)
    elif ext in SUPPORTED:
        import trimesh
        try:
            m = trimesh.load(path, force='mesh', process=False)
        except Exception:
            if ext != 'stl':
                raise
            m = _load_ascii_stl_cr(path, trimesh)
        V, F = np.asarray(m.vertices, float), np.asarray(m.faces, int)
        if ext in YUP:
            V = np.column_stack([V[:, 0], -V[:, 2], V[:, 1]])
    else:
        raise ValueError(f'.{ext} wordt niet ondersteund voor previews')
    if len(F) == 0 or len(V) == 0:
        raise ValueError('mesh is leeg')
    return np.nan_to_num(V), F.astype(np.int64)


def stl_bytes(V, F):
    """Binaire STL, voor de 3D-viewer in de browser (zo hoeft de browser maar één formaat te kennen)."""
    t = V[F].astype('<f4')
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True).clip(1e-12)
    a = np.zeros(len(F), dtype=[('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')])
    a['n'], a['v'] = n, t
    return b'\0' * 80 + struct.pack('<I', len(F)) + a.tobytes()


def render(V, F, size=384, ss=2, bg=(42, 47, 58), base=(176, 184, 196), max_tris=None):
    max_tris = max_tris or MAX_TRIS
    lo, hi = V.min(0), V.max(0)
    V = (V - (lo + hi) / 2) / max((hi - lo).max(), 1e-9)
    V = np.column_stack([V[:, 0], V[:, 2], -V[:, 1]])  # Z-up -> Y-up
    eye = np.array([1.4, 1.0, 1.6]) * 1.4
    fwd = -eye / np.linalg.norm(eye)
    right = np.cross(fwd, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    rel = V - eye
    x, y, z = rel @ right, rel @ up, rel @ fwd
    N, f = size * ss, 1 / math.tan(math.radians(35) / 2)
    P = np.column_stack([(x * f / z * .5 + .5) * N, (.5 - y * f / z * .5) * N])
    lo2, hi2 = P.min(0), P.max(0)  # object vult ~86% van het beeld
    P = (P - (lo2 + hi2) / 2) * (.86 * N / max((hi2 - lo2).max(), 1e-9)) + N / 2
    T = V[F]
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True).clip(1e-12)
    nrm[(nrm @ fwd) > 0] *= -1  # tweezijdig: normaal naar de camera
    light = np.array([2., 3., 2.])
    light /= np.linalg.norm(light)
    k = (.30 + .30 * (.5 + .5 * nrm[:, 1]) + .55 * np.clip(nrm @ light, 0, 1)).clip(0, 1)
    col = (np.array(base) * k[:, None]).astype(np.uint8)
    order = np.argsort(-z[F].mean(1))  # painter's algorithm: ver -> dichtbij
    if len(order) > max_tris:
        order = order[np.linspace(0, len(order) - 1, max_tris).astype(np.int64)]
    img = Image.new('RGB', (N, N), bg)
    d = ImageDraw.Draw(img)
    for i in range(0, len(order), 100_000):
        o = order[i:i + 100_000]
        for p, c in zip(P[F[o]].reshape(-1, 6).tolist(), col[o].tolist()):
            d.polygon(p, fill=tuple(c))
    return img.resize((size, size), Image.LANCZOS)


def fit_square(img, size, bg=(42, 47, 58)):
    """Afbeelding (ook niet-vierkant of met transparantie) passend in een vierkante thumbnail."""
    img = img.convert('RGBA')
    k = size / max(img.width, img.height)
    img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    out = Image.new('RGB', (size, size), bg)
    out.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return out


def save_png(img, out, tag=None):
    """PNG opslaan, met (indien gegeven) een tekstkenmerk 'modelbib' dat aangeeft bij welk model/bestand de thumbnail hoort."""
    info = None
    if tag:
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo()
        info.add_text('modelbib', tag)
    img.save(out, 'PNG', optimize=True, pnginfo=info)


def _zip_thumb(path):
    z = zipfile.ZipFile(path)
    low = {n.lower().lstrip('/'): n for n in z.namelist()}
    order = []
    if '_rels/.rels' in low:  # 3MF/OPC: relatie van het type 'thumbnail'
        try:
            for rel in ET.fromstring(z.read(low['_rels/.rels'])):
                if rel.get('Type', '').lower().endswith('thumbnail') and rel.get('Target'):
                    order.append(rel.get('Target').lstrip('/').lower())
        except ET.ParseError:
            pass
    order += ['metadata/plate_1.png', 'metadata/thumbnail.png', 'thumbnails/thumbnail.png']
    order += sorted(k for k in low if 'thumbnail' in k and k.endswith(('.png', '.jpg', '.jpeg')) and 'small' not in k)
    for k in order:
        n = low.get(k)
        if n and z.getinfo(n).file_size < 20 * 2 ** 20:
            try:
                im = Image.open(io.BytesIO(z.read(n)))
                im.load()
                return im
            except Exception:
                continue
    return None


_GC = re.compile(rb';\s*thumbnail(?:_JPG|_QOI)? begin (\d+)x(\d+) \d+\r?\n(.*?);\s*thumbnail(?:_JPG|_QOI)? end', re.S)


def _gcode_thumb(path):
    with open(path, 'rb') as f:
        head = f.read(3 * 2 ** 20)  # slicers zetten de afbeelding(en) in de kop
    best = None
    for m in _GC.finditer(head):
        try:
            im = Image.open(io.BytesIO(base64.b64decode(re.sub(rb'(?m)^;|\s', b'', m.group(3)))))
            im.load()
        except Exception:
            continue
        if best is None or im.width * im.height > best.width * best.height:
            best = im
    return best


def embedded_thumb(path, ext):
    """Ingebedde preview: 3MF/FCStd (afbeelding in het zip-bestand) of G-code (base64 in commentaar). None als er geen is."""
    if ext in ('3mf', 'fcstd'):
        return _zip_thumb(path)
    if ext in ('gcode', 'gco'):
        return _gcode_thumb(path)
    return None


def make_thumb(path, ext, out, size=384, prefer_embedded=True, tag=None):
    """Thumbnail maken. Meshformaten: afmetingen en driehoeken bepalen en (tenzij prefer_embedded en aanwezig) zelf renderen.
    Formaten zonder mesh-lader (FCStd, G-code): alleen een ingebedde afbeelding, anders NoPreview."""
    ext = ext.lower().lstrip('.')
    dims, tris, V, F = (None, None, None), None, None, None
    nomesh = None
    if ext in SUPPORTED:
        try:
            V, F = load_mesh(path, ext)
            dims, tris = tuple(float(v) for v in V.max(0) - V.min(0)), int(len(F))
        except Exception as e:
            if ext != '3mf':
                raise
            nomesh = e  # bv. een gesliced .gcode.3mf zonder build-items: de ingebedde afbeelding is dan nog bruikbaar
    elif ext not in EMBED_ONLY:
        raise NoPreview(f'.{ext} wordt niet ondersteund voor previews (alleen geïndexeerd)')
    img = None
    if prefer_embedded or ext not in SUPPORTED or nomesh:
        try:
            img = embedded_thumb(path, ext)
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError):
            img = None
    if img is not None:
        save_png(fit_square(img, size), out, tag)
        src = 'embedded'
    elif V is not None:
        save_png(render(V, F, size), out, tag)
        src = 'render'
    elif nomesh:
        raise NoPreview(f'Geen 3D-weergave en geen ingebedde afbeelding ({nomesh})')
    else:
        raise NoPreview('Geen ingebedde afbeelding in dit bestand')
    return dict(dims=dims, tris=tris, source=src)

def clean_text(s, limit=200):
    """Tekst uit 3MF-metadata leesbaar maken: HTML-entiteiten (soms dubbel gecodeerd) omzetten, links als 'tekst (url)' bewaren
    en de overige HTML-tags weghalen. Het resultaat is gewone tekst."""
    s = s or ''
    for _ in range(2):
        t = html.unescape(s)
        if t == s:
            break
        s = t
    s = re.sub(r'(?is)<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', lambda m: f'{m.group(2)} ({m.group(1)})' if m.group(2).strip() != m.group(1) else m.group(1), s)
    s = re.sub(r'(?i)<br\s*/?>|</(?:p|h[1-6]|li|div|tr)>', '\n', s)
    s = re.sub(r'(?s)<[^>]*>', '', s)
    s = html.unescape(s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n\s*\n+', '\n\n', s).strip()
    return s[:limit]


_CORE = {'Title': 'title', 'Designer': 'designer', 'Description': 'description', 'Copyright': 'copyright',
         'LicenseTerms': 'license', 'License': 'license', 'CreationDate': 'created', 'Application': 'application'}


def _hex(c):
    m = re.fullmatch(r'#?([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?', str(c or '').strip())
    return '#' + m.group(1).upper() if m else None


def _colors_3mf(z, files, cfg, ET):
    """Kleuren die echt gebruikt worden: bij een gesliced Bambu/Orca-project uit slice_info.config (filamenten met verbruik), anders de filamenten
    waaraan objecten in het project zijn toegewezen (model_settings.config) met de kleuren uit de projectinstellingen. Leeg als er niets te vinden is."""
    if 'Metadata/slice_info.config' in files:
        try:
            seen = {}
            for f in ET.fromstring(z.read(files['Metadata/slice_info.config'])).iter('filament'):
                c = _hex(f.get('color'))
                try:
                    used = float(f.get('used_g') or f.get('used_m') or 1) > 0
                except ValueError:
                    used = True
                if c and used:
                    seen.setdefault(f.get('id') or str(len(seen)), c)
            if seen:
                return list(dict.fromkeys(seen.values()))
        except (ET.ParseError, KeyError, ValueError, TypeError):
            pass  # kapotte slice_info: terugvallen op de projectinstellingen
    try:
        pal = cfg.get('filament_colour') or cfg.get('extruder_colour')
        pal = pal if isinstance(pal, list) else re.split(r'[;,]', str(pal or ''))
        pal = [_hex(x) for x in pal]
        if not any(pal):
            return []
        used = set()
        for name in ('Metadata/model_settings.config', 'Metadata/Slic3r_PE_model.config'):
            if name in files:
                for m in ET.fromstring(z.read(files[name])).iter('metadata'):
                    if m.get('key') == 'extruder' and str(m.get('value') or '').isdigit() and int(m.get('value')) > 0:
                        used.add(int(m.get('value')))
        used = used or {1}
        out = [pal[i - 1] for i in sorted(used) if i <= len(pal) and pal[i - 1]]
        return list(dict.fromkeys(out))
    except (ET.ParseError, KeyError, ValueError, TypeError):
        return []


def info_3mf(path):
    """Metadata uit een 3MF: titel, ontwerper, programma, licentie, plus slicer-instellingen
    (Bambu Studio / PrusaSlicer) en slice-resultaat (printtijd, filamentgewicht) als die erin zitten.
    Leest alleen de kop van het model-bestand, dus ook snel bij grote bestanden."""
    z = zipfile.ZipFile(path)
    files = {n.lstrip('/'): n for n in z.namelist()}
    out = {}
    root = next((n for k, n in files.items() if k.lower().endswith('3dmodel.model')), None)
    if root:
        with z.open(root) as f:
            for ev, el in ET.iterparse(f, events=('start', 'end')):
                t = _local(el)
                if ev == 'start' and t in ('resources', 'build'):
                    break  # metadata staat altijd vóór de geometrie
                if ev == 'end' and t == 'metadata' and _CORE.get(el.get('name')) and (el.text or '').strip():
                    txt = clean_text(el.text, 800 if el.get('name') == 'Description' else 200)
                    if txt:
                        out.setdefault(_CORE[el.get('name')], txt)
    cfg = {}
    if 'Metadata/project_settings.config' in files:  # Bambu Studio / OrcaSlicer (JSON)
        try:
            cfg = json.loads(z.read(files['Metadata/project_settings.config']))
        except ValueError:
            cfg = {}
    elif 'Metadata/Slic3r_PE.config' in files:  # PrusaSlicer ("; sleutel = waarde")
        txt = z.read(files['Metadata/Slic3r_PE.config']).decode('utf-8', 'ignore')
        cfg = dict(re.findall(r'^;\s*(\w+)\s*=\s*(.*)$', txt, re.M))

    def scalar(k):
        v = cfg.get(k)
        v = v[0] if isinstance(v, list) and v else v
        return '' if v in (None, '') else str(v).strip()

    def vals(k):
        v = cfg.get(k)
        v = v if isinstance(v, list) else (re.split(r'[;,]', str(v)) if v not in (None, '') else [])
        return [str(x).strip() for x in v if str(x).strip()]

    for dst, v in (('printer', scalar('printer_model') or scalar('printer_settings_id')), ('layer_height', scalar('layer_height')),
                   ('nozzle', (vals('nozzle_diameter') or [''])[0]), ('filament', ', '.join(dict.fromkeys(vals('filament_type'))))):
        if v:
            out[dst] = v
    if 'Metadata/slice_info.config' in files:  # Bambu: resultaat van het slicen
        try:
            tm = g = 0.0
            for m in ET.fromstring(z.read(files['Metadata/slice_info.config'])).iter('metadata'):
                if m.get('key') == 'prediction':
                    tm += float(m.get('value'))
                elif m.get('key') == 'weight':
                    g += float(m.get('value'))
            if tm:
                out['print_time'] = int(tm)
            if g:
                out['filament_g'] = round(g, 1)
        except (ET.ParseError, ValueError, TypeError):
            pass
    cols = _colors_3mf(z, files, cfg, ET)
    if cols:
        out['colors'], out['color_count'] = cols, len(cols)
    pls = _plates(z)
    if len(pls) > 1:
        out['plates'] = [{'id': p['id'], 'name': p['name']} for p in pls]
    if 'description' in out:
        out['description'] = out['description'][:800]
    return out
