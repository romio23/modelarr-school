"""Modelarr - beheer je 3D-modellen zoals Sonarr/Radarr je films beheert.
Config: omgevingsvariabelen (CONFIG_DIR, MODELS_DIR, HOST, PORT, AUTH_USER, AUTH_PASS, MAX_FILE_MB)
en de Instellingen-pagina's in de app."""
import base64, unicodedata, contextlib, io, json, logging.handlers, ntpath, os, posixpath, re, sys, time, hmac, hashlib, platform, secrets, sqlite3, threading, logging, shutil, collections, socket, subprocess, tempfile, urllib.error, urllib.parse, urllib.request, zipfile
from xml.etree import ElementTree
from datetime import timedelta
from flask import Flask, request, jsonify, send_file, send_from_directory, abort, Response, g, session, has_request_context
from werkzeug.security import generate_password_hash, check_password_hash
import render
import integrations as INT
from PIL import Image

VERSION = 'school-0.6.0'
BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.environ.get('CONFIG_DIR', os.path.join(BASE, 'config')))
BACKUP_ENV = os.environ.get('BACKUP_DIR', '').strip()  # standaard back-upmap (de instelling in de app gaat voor)
THUMBS, DB = os.path.join(CONFIG, 'thumbs'), os.path.join(CONFIG, 'library.db')
HOST, PORT = os.environ.get('HOST', '0.0.0.0'), int(os.environ.get('PORT', 8765))
MAX_MB = int(os.environ.get('MAX_FILE_MB', 400))
FOLLOW_LINKS = os.environ.get('FOLLOW_SYMLINKS', '1' if os.name == 'nt' else '0') == '1'  # Windows/netwerkshares: mappen kunnen als link worden gemeld; op Linux standaard uit
START, REV = time.time(), 0
os.makedirs(THUMBS, exist_ok=True)
app = Flask(__name__, static_folder=os.path.join(BASE, 'static'), static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 25 * 2 ** 20
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(days=30))

# ---------------------------------------------------------------- logging (ringbuffer voor Systeem > Logs)
LOGS = collections.deque(maxlen=2000)


class Ring(logging.Handler):
    def emit(self, r):
        LOGS.append(dict(t=r.created, level=r.levelname, msg=self.format(r)))


log = logging.getLogger('modelbib')
log.setLevel(logging.INFO)
_r, _fmt = Ring(), logging.Formatter('%(asctime)s %(levelname)s %(message)s')
log.addHandler(_r)
_fh = logging.handlers.RotatingFileHandler(os.path.join(CONFIG, 'modelarr.log'), maxBytes=1_000_000, backupCount=3, encoding='utf-8')
_fh.setFormatter(_fmt)
log.addHandler(_fh)
if sys.stderr is not None:  # ontbreekt bij pythonw.exe (Windows zonder console)
    _s = logging.StreamHandler()
    _s.setFormatter(_fmt)
    log.addHandler(_s)

# ---------------------------------------------------------------- database & instellingen
OLD_EXTS = 'stl,3mf,obj,ply,glb,gltf'
DEFAULT_EXTS = ('stl,3mf,obj,ply,glb,gltf,'  # met 3D-preview
                'fcstd,gcode,gco,'  # preview uit een ingebedde afbeelding
                'step,stp,iges,igs,f3d,scad,blend,fbx,dae,3ds,off,amf,x3d,dxf,dwg,skp,sldprt,sldasm,ipt,iam,catpart,bgcode')  # alleen indexeren
DEFAULTS = dict(scan_interval='5', min_age='10', extensions=DEFAULT_EXTS, thumb_size='384',
                auth_user='', auth_hash='', api_key='', big_mb='50', recent_days='7', thumb_source='embedded', thumb_delay='0', thumb_paused='0', backup_keep='7', backup_thumbs='0', backup_dir='', bambuddy_url='', bambuddy_key='', folder_rules_migrated='0', zip_support='1', spoolman_url='', slicer='bambustudio', link_secret='', session_secret='', student_quota_mb='500', default_share='1',
                ms_enabled='0', ms_tenant='', ms_client_id='', ms_client_secret='', ms_admin_group='', ms_only='0', public_url='', ms_klas='1')
CFG, OKAUTH = dict(DEFAULTS), set()
AUTH_ON, FAILS = [False], {}  # AUTH_ON: zijn er accounts (dan is inloggen verplicht)? FAILS: mislukte inlogpogingen per adres
DUMMY_HASH = generate_password_hash('dummy-voor-gelijke-rekentijd')


DBW = 0  # telt het aantal schrijfacties in de database (om de bibliotheeklijst te cachen)


@contextlib.contextmanager
def db():
    """Eigen verbinding per gebruik (ook in achtergrond-threads): commit bij succes, rollback bij fout, altijd sluiten."""
    global DBW
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    n0 = c.total_changes
    try:
        with c:
            yield c
    finally:
        if c.total_changes != n0:
            DBW += 1  # er is iets gewijzigd: de bibliotheeklijst in het geheugen is niet meer actueel
        c.close()


def init():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS roots(id INTEGER PRIMARY KEY, path TEXT UNIQUE, watch INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS models(id INTEGER PRIMARY KEY, root_id INTEGER REFERENCES roots(id) ON DELETE CASCADE,
            path TEXT UNIQUE, name TEXT, display_name TEXT, ext TEXT, size INTEGER, mtime REAL, added_at REAL,
            thumb_status TEXT DEFAULT 'pending', thumb_error TEXT, thumb_at REAL, dx REAL, dy REAL, dz REAL, tris INTEGER);
        CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS model_categories(
            model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE, PRIMARY KEY(model_id, category_id));
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, ts REAL, event TEXT, model_id INTEGER, message TEXT);
        CREATE TABLE IF NOT EXISTS dup_ignored(key TEXT PRIMARY KEY, ts REAL);
        CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, field TEXT, value TEXT, category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE, created REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);''')
        c.executescript('CREATE INDEX IF NOT EXISTS idx_models_root ON models(root_id); CREATE INDEX IF NOT EXISTS idx_models_status ON models(thumb_status);')
        if 'info' not in [r[1] for r in c.execute('PRAGMA table_info(models)')]:
            c.execute('ALTER TABLE models ADD COLUMN info TEXT')  # 3MF-metadata als JSON
        if 'hash' not in [r[1] for r in c.execute('PRAGMA table_info(models)')]:
            c.execute('ALTER TABLE models ADD COLUMN hash TEXT')  # inhoud-hash voor de dubbelen-check
        c.executescript('CREATE INDEX IF NOT EXISTS idx_models_size ON models(size); CREATE INDEX IF NOT EXISTS idx_models_hash ON models(hash);')
        c.executescript('CREATE TABLE IF NOT EXISTS printers(id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, bed_x REAL, bed_y REAL, bed_z REAL);'
                        'CREATE TABLE IF NOT EXISTS prints(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES models(id) ON DELETE CASCADE, ts REAL, result TEXT, printer_id INTEGER,'
                        ' printer TEXT, plate INTEGER, grams REAL, spool_id INTEGER, spool TEXT, notes TEXT);'
                        'CREATE INDEX IF NOT EXISTS idx_prints_model ON prints(model_id);'
                        'CREATE TABLE IF NOT EXISTS bb_imported(bb_id INTEGER PRIMARY KEY);'
                        "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE, pw_hash TEXT, role TEXT DEFAULT 'viewer',"
                        ' can_download INTEGER DEFAULT 1, active INTEGER DEFAULT 1, ver INTEGER DEFAULT 0, created REAL, last_login REAL);')
        have = [r[1] for r in c.execute('PRAGMA table_info(models)')]
        for col, typ in (('notes', 'TEXT'), ('favorite', 'INTEGER DEFAULT 0'), ('source_url', 'TEXT'), ('printed', "TEXT DEFAULT ''"), ('thumb_custom', 'INTEGER DEFAULT 0'), ('container', 'TEXT'), ('member', 'TEXT'), ('pdims', 'TEXT')):
            if col not in have:
                c.execute(f'ALTER TABLE models ADD COLUMN {col} {typ}')
        if 'allow_write' not in [r[1] for r in c.execute('PRAGMA table_info(roots)')]:
            c.execute('ALTER TABLE roots ADD COLUMN allow_write INTEGER DEFAULT 0')  # hernoemen/verplaatsen toestaan
        if 'email' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
            c.execute('ALTER TABLE users ADD COLUMN email TEXT')
        if 'ms_oid' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
            c.execute('ALTER TABLE users ADD COLUMN ms_oid TEXT')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS schools(id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, slug TEXT UNIQUE COLLATE NOCASE,
            root_id INTEGER REFERENCES roots(id) ON DELETE SET NULL, group_id TEXT, active INTEGER DEFAULT 1, created REAL);
        CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES models(id) ON DELETE CASCADE, reporter_id INTEGER,
            reason TEXT, ts REAL, status TEXT DEFAULT 'open', handled_by INTEGER, handled_ts REAL, action TEXT);
        CREATE TABLE IF NOT EXISTS print_requests(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES models(id) ON DELETE SET NULL, model_name TEXT,
            requester_id INTEGER, school_id INTEGER, colors TEXT, copies INTEGER DEFAULT 1, note TEXT, status TEXT DEFAULT 'open', staff_note TEXT,
            handler_id INTEGER, sliced_name TEXT, created REAL, updated REAL);
        CREATE INDEX IF NOT EXISTS idx_reports_model ON reports(model_id);''')
        for col, typ in (('school_id', 'INTEGER'), ('klas', 'TEXT'), ('display_name', 'TEXT'), ('home', 'TEXT'), ('share_default', 'INTEGER DEFAULT 1')):
            if col not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
        for col, typ in (('owner_id', 'INTEGER'), ('school_id', 'INTEGER'), ('shared', 'INTEGER DEFAULT 1'), ('hidden', 'INTEGER DEFAULT 0')):
            if col not in {r[1] for r in c.execute('PRAGMA table_info(models)')}:
                c.execute(f'ALTER TABLE models ADD COLUMN {col} {typ}')
        if 'quota_mb' not in {r[1] for r in c.execute('PRAGMA table_info(schools)')}:
            c.execute('ALTER TABLE schools ADD COLUMN quota_mb INTEGER')  # leeg = algemene instelling
        if 'share_default' not in {r[1] for r in c.execute('PRAGMA table_info(schools)')}:
            c.execute('ALTER TABLE schools ADD COLUMN share_default INTEGER')  # uploads van leerlingen standaard delen: 1/0, leeg = algemene instelling
        if 'share_own' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
            c.execute('ALTER TABLE users ADD COLUMN share_own INTEGER')  # eigen standaard van een leerling (via /api/me/prefs); leeg = die van de school
        if 'staff_group_id' not in {r[1] for r in c.execute('PRAGMA table_info(schools)')}:
            c.execute('ALTER TABLE schools ADD COLUMN staff_group_id TEXT')  # Microsoft-groep van de medewerkers (group_id = leerlingen)
        c.execute("UPDATE users SET role='student' WHERE role='viewer'")  # de schoolversie kent beheerder, medewerker en leerling
        c.executescript('CREATE INDEX IF NOT EXISTS idx_models_school ON models(school_id, owner_id);')
        if 'can_upload' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
            c.execute('ALTER TABLE users ADD COLUMN can_upload INTEGER DEFAULT 0')  # gast met toestemming om modellen te uploaden
        c.execute('CREATE TABLE IF NOT EXISTS hidden_folders(root_id INTEGER, rel TEXT, PRIMARY KEY(root_id, rel))')  # mappen buiten de scholen die leerlingen niet zien
        c.execute('CREATE TABLE IF NOT EXISTS upload_share(path TEXT PRIMARY KEY, shared INTEGER, ts REAL)')  # deelkeuze bij het uploaden, toe te passen zodra de scan het model ziet
        c.execute('CREATE TABLE IF NOT EXISTS upload_cats(path TEXT, category_id INTEGER, ts REAL, PRIMARY KEY(path, category_id))')  # gekozen categorieën, toe te passen zodra de scan het model ziet
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oid ON users(ms_oid) WHERE ms_oid IS NOT NULL')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email COLLATE NOCASE) WHERE email IS NOT NULL')
        # 3MF-info met onleesbare HTML-entiteiten (oudere versie) opnieuw laten lezen
        if not c.execute("SELECT 1 FROM settings WHERE key='info_colors_done'").fetchone():  # eenmalig: kleuren uit 3MF-bestanden lezen (de worker leest de info opnieuw)
            c.execute("UPDATE models SET info=NULL WHERE ext='3mf'")
            c.execute("INSERT OR REPLACE INTO settings VALUES('info_colors_done','1')")
        c.execute("UPDATE models SET info=NULL WHERE ext='3mf' AND (info LIKE '%&lt;%' OR info LIKE '%&gt;%' OR info LIKE '%&amp;%' OR info LIKE '%&#%' OR info LIKE '%&quot;%')")
        # Een model dat tijdens een crash/OOM werd verwerkt mag niet eindeloos opnieuw de app laten crashen:
        c.execute("UPDATE models SET thumb_status='pending', thumb_error=NULL WHERE thumb_status='failed' AND thumb_error LIKE '%build-items%'")  # eerder mislukt: gesliced 3MF, nu via de ingebedde afbeelding
        c.execute("UPDATE models SET thumb_status='failed', thumb_error='Verwerking onderbroken (crash of te weinig geheugen?)' WHERE thumb_status='processing'")
        CFG.update({r['key']: r['value'] for r in c.execute('SELECT * FROM settings')})
        if CFG['extensions'] == OLD_EXTS:  # ongewijzigde oude standaard -> nieuwe, ruimere lijst
            CFG['extensions'] = DEFAULT_EXTS
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('extensions', DEFAULT_EXTS))
    migrate_legacy_auth()
    if not CFG['session_secret']:
        put('session_secret', secrets.token_hex(32))
    app.secret_key = CFG['session_secret']
    refresh_auth()


def put(k, v):
    CFG[k] = str(v)
    with db() as c:
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (k, str(v)))


def bump():
    global REV
    REV += 1


def hist(event, msg, mid=None):
    with db() as c:
        c.execute('INSERT INTO history(ts,event,model_id,message) VALUES(?,?,?,?)', (time.time(), event, mid, msg))
        c.execute('DELETE FROM history WHERE id < (SELECT MAX(id) FROM history) - 2000')
    bump()


# ---------------------------------------------------------------- hulpfuncties
LAST_USER = [0.0]
MTIME_TOL = 2.0  # seconden: Windows/SMB en Linux ronden de wijzigingstijd van hetzelfde bestand soms verschillend af
YIELD = os.environ.get('YIELD_TO_USERS', '1') != '0'  # 0 = nooit even wachten voor gebruikers (handig bij testen)


def thumb_tag(row):
    """Kenmerk dat in elke thumbnail wordt opgeslagen: model-id + grootte + wijzigingsdatum van het modelbestand."""
    return f"{row['id']}:{row['size']}:{row['mtime']}"


def tag_matches(tag, row):
    """Hoort dit thumbnail-kenmerk bij het model? De wijzigingstijd mag een paar seconden afwijken (ander platform, andere afronding)."""
    try:
        i, s, m = str(tag).split(':')
        return int(i) == row['id'] and int(s) == row['size'] and abs(float(m) - row['mtime']) <= MTIME_TOL
    except ValueError:
        return False
NETFS = ('nfs', 'nfs4', 'cifs', 'smb3', 'smbfs', 'afs', 'ncpfs', '9p', 'fuse.sshfs', 'fuse.rclone', 'fuse.s3fs', 'fuse.gcsfuse')


ZIP_MAX_ENTRIES = 5000
ARCHIVE_EXTS = ('.zip', '.rar', '.7z')


def zip_members(path, allowed):
    """Modellen in een zip, zonder uitpakken: [(naam in zip, stam, extensie, grootte)]; None als het zip onleesbaar is."""
    try:
        with zipfile.ZipFile(path) as z:
            out = []
            for i in z.infolist()[:ZIP_MAX_ENTRIES]:
                base = posixpath.basename(i.filename)
                if i.is_dir() or i.flag_bits & 1 or i.filename.startswith('__MACOSX/') or not base or base.startswith('.'):
                    continue  # map, versleuteld, macOS-rommel of verborgen bestand
                stem, e = os.path.splitext(base)
                if e.lower() not in allowed or e.lower() in ARCHIVE_EXTS or i.file_size > MAX_MB * 2 ** 20:
                    continue
                out.append((i.filename, stem, e[1:].lower(), i.file_size))
            return out
    except (zipfile.BadZipFile, OSError, NotImplementedError, RuntimeError):
        return None


@contextlib.contextmanager
def materialize(row):
    """Echt bestandspad voor een model. Zit het in een zip, dan wordt alleen dat onderdeel tijdelijk uitgepakt (en daarna opgeruimd)."""
    if not row['container']:
        yield row['path']
        return
    d = os.path.join(CONFIG, 'tmp')
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix='.' + row['ext'], dir=d)
    os.close(fd)
    try:
        with zipfile.ZipFile(row['container']) as z, z.open(row['member']) as src, open(tmp, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        yield tmp
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def member_hash(container, member):
    h = hashlib.blake2b(digest_size=16)
    with zipfile.ZipFile(container) as z, z.open(member) as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


SLICERS = {'bambustudio': ('Bambu Studio', 'bambustudio://open?file='), 'orcaslicer': ('OrcaSlicer', 'orcaslicer://open?file='),
           'prusaslicer': ('PrusaSlicer', 'prusaslicer://open?file=')}
LINK_TTL = 600
OPEN_OK = os.name == 'nt' or sys.platform == 'darwin' or bool(shutil.which('xdg-open'))


def _sign(mid, exp):
    if not CFG['link_secret']:
        put('link_secret', secrets.token_hex(32))
    return hmac.new(CFG['link_secret'].encode(), f'{mid}.{exp}'.encode(), hashlib.sha256).hexdigest()[:32]


def make_token(mid, ttl=LINK_TTL):
    exp = int(time.time()) + ttl
    return f'{mid}.{exp}.{_sign(mid, exp)}'


def check_token(tok):
    """Model-id als de link geldig en niet verlopen is, anders None."""
    try:
        mid, exp, sig = tok.split('.')
        if hmac.compare_digest(sig, _sign(int(mid), int(exp))) and int(exp) >= time.time():
            return int(mid)
    except (ValueError, TypeError):
        pass
    return None


def is_local():
    """Zit de gebruiker op dezelfde computer als de app, en kan die daar bestanden openen?"""
    u = g.get('user')
    return (OPEN_OK and request.remote_addr in ('127.0.0.1', '::1') and not (u and u['role'] != 'admin')
            and not any(request.headers.get(h) for h in ('X-Forwarded-For', 'Forwarded', 'X-Real-IP')))  # via een reverse proxy lijkt iedereen lokaal


def open_file(path):
    if os.name == 'nt':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def clean_path(s):
    """Pad uit een invoerveld opschonen: spaties en aanhalingstekens weg (Windows 'Kopiëren als pad' zet er aanhalingstekens omheen)."""
    return (s or '').strip().strip('"').strip("'").strip()


def unc_server_only(p):
    """True bij '\\\\server' zonder share: zo'n pad is niet te bladeren."""
    q = p.replace('/', '\\').rstrip('\\')
    return q.startswith('\\\\') and q.count('\\') == 2


def windows_drives(get_mask=None):
    """Beschikbare stationsletters. GetLogicalDrives raakt het netwerk niet aan (geen wachten op niet-bereikbare schijven)."""
    try:
        if get_mask is None:
            import ctypes
            get_mask = ctypes.windll.kernel32.GetLogicalDrives
        mask = get_mask()
        return [f'{chr(65 + i)}:\\' for i in range(26) if mask >> i & 1]
    except Exception:
        return [f'{d}:\\' for d in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if os.path.isdir(f'{d}:\\')]


def unc_of(path, api=None):
    """UNC-pad van een pad op een gekoppelde netwerkschijf (Z:\\map -> \\\\nas\\share\\map); None als het geen netwerkschijf is."""
    drive = ntpath.splitdrive(path)[0]
    if len(drive) != 2 or drive[1] != ':':
        return None
    try:
        import ctypes
        if api is None:
            if os.name != 'nt':
                return None
            api = ctypes.windll.mpr.WNetGetConnectionW
        buf, n = ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
        if api(drive, buf, ctypes.byref(n)) != 0 or not buf.value:
            return None
        return buf.value.rstrip('\\') + path[2:]
    except Exception:
        return None


def yield_to_users(cap=3.0):
    """Even wachten als iemand de app gebruikt, zodat de interface vlot blijft (max. `cap` seconden)."""
    if not YIELD:
        return
    t0 = time.time()
    while time.time() - LAST_USER[0] < 2 and time.time() - t0 < cap:
        time.sleep(.3)


def fs_type(path, mounts=None):
    """Bestandssysteemtype van de mount waar `path` op staat (Linux, via /proc/mounts); '' als onbekend."""
    try:
        txt = mounts if mounts is not None else open('/proc/mounts').read()
    except OSError:
        return ''
    p, best = os.path.realpath(path), ('', '')
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mp = parts[1].replace('\\040', ' ')
        if (p == mp or p.startswith(mp.rstrip('/') + '/')) and len(mp) >= len(best[0]):
            best = (mp, parts[2])
    return best[1]


def config_on_network():
    """Type netwerkshare als de config-map (database) daarop staat, anders ''."""
    if os.name == 'nt':
        try:
            import ctypes
            full = os.path.abspath(CONFIG)
            if full.startswith('\\\\'):
                return 'smb'
            return 'netwerkschijf' if ctypes.windll.kernel32.GetDriveTypeW(os.path.splitdrive(full)[0] + '\\') == 4 else ''
        except Exception:
            return ''
    t = fs_type(CONFIG)
    return t if t in NETFS or t.startswith(('nfs', 'cifs', 'smb')) else ''


# ---------------------------------------------------------------- scannen
scan_lock = threading.Lock()
SCANP = dict(phase='', dirs=0, files=0, added=0, total=0)  # voortgang van de lopende scan (voor de balk in de webinterface)
ROOT_ALERT = {}  # root_id -> dict(kind, path, known, since, dirs): root folder offline, onverwacht leeg of deels onleesbaar (melding in de webinterface)
ALERT_RETRY = 60  # seconden: zolang er een melding is, sneller opnieuw scannen zodat de bibliotheek terugkomt zodra de share weer gekoppeld is
T = dict(scan=dict(last=None, dur=None, running=False), rebuild=dict(last=None), backup=dict(last=None, dur=None), thumbcheck=dict(last=None))
NEXT, dirty, CUR, OBS = dict(scan=0, soon=0, backup=time.time() + 3600, bambuddy=time.time() + 90), {}, {}, {}
STABLE = {}  # pad -> (grootte, sinds wanneer onveranderd): netwerk-kopieën behouden vaak een oude mtime


def exts():
    return {'.' + e.strip().lower().lstrip('.') for e in CFG['extensions'].split(',') if e.strip()}


def walk_top(p, pm=os.path):
    """Een kale drive of share (C: of \\\\server\\share) krijgt een slash erachter: nieuwere Python-versies plakken er anders de mapnaam direct achter (\\\\server\\sharemap)."""
    return p + pm.sep if p and pm.splitdrive(p)[0] == p else p


def _set_alert(r, kind, known, dirs=0):
    """Onthoud dat een root folder niet in orde is. Een nieuwe of andere melding komt ook in het logboek."""
    old = ROOT_ALERT.get(r['id'])
    if not old or old['kind'] != kind:
        hist('Root folder', {'offline': f"{r['path']} is niet bereikbaar; de bibliotheek blijft staan tot de map terug is",
                             'empty': f"{r['path']} lijkt leeg terwijl er {known} modellen bekend zijn (share niet gekoppeld?); niets verwijderd",
                             'partial': f"{dirs} map(pen) in {r['path']} niet te lezen; modellen daarin blijven staan"}[kind])
    ROOT_ALERT[r['id']] = dict(kind=kind, path=r['path'], known=known, dirs=dirs, since=old['since'] if old and old['kind'] == kind else time.time())
    if kind != 'partial':  # offline of leeg: snel opnieuw kijken (goedkoop). Bij onleesbare submappen niet: een volledige scan van een grote share elke minuut is te zwaar
        NEXT['soon'] = min(NEXT['soon'] or 1e18, time.time() + ALERT_RETRY)
    bump()


def _clear_alert(r):
    if ROOT_ALERT.pop(r['id'], None):
        hist('Root folder', f"{r['path']} is weer bereikbaar")
        log.info('Root folder %s is weer bereikbaar', r['path'])
        bump()


def root_alerts():
    with db() as c:
        ids = {x[0] for x in c.execute('SELECT id FROM roots')}
    for k in [k for k in ROOT_ALERT if k not in ids]:  # root folder intussen verwijderd
        ROOT_ALERT.pop(k, None)
    return [dict(id=k, **v) for k, v in sorted(ROOT_ALERT.items())]


def _scan_root(r, allowed, min_age):
    root, young, now = r['path'], 0, time.time()
    SCANP['phase'] = 'zoeken'
    if not os.path.isdir(root):
        log.warning('Root folder niet bereikbaar, overgeslagen: %s', root)
        with db() as c:
            known = c.execute('SELECT COUNT(*) FROM models WHERE root_id=?', (r['id'],)).fetchone()[0]
        _set_alert(r, 'offline', known)
        return 0
    zip_on = CFG['zip_support'] == '1'

    def unstable(p, size, mt):
        """Nog in beweging? Jong volgens mtime, of de grootte is de laatste min_age seconden veranderd."""
        if now - mt < min_age:
            return True
        s = STABLE.get(p)
        if s is None or s[0] != size:
            STABLE[p] = (size, now)
            return min_age > 0
        if now - s[1] < min_age:
            return True
        del STABLE[p]
        return False

    found, zips, errs, links, seen, ndirs, top_sub = {}, [], [], [], set(), 0, 0
    for d, dirs, files in os.walk(walk_top(root), followlinks=FOLLOW_LINKS, onerror=errs.append):
        ndirs += 1
        SCANP['dirs'] += 1
        if ndirs == 1:
            top_sub = len([x for x in dirs if not x.startswith(('.', '@', '#', '$'))])
        if FOLLOW_LINKS:  # symlinks volgen zonder in een kringetje te belanden
            rp = os.path.realpath(d)
            if rp in seen:
                dirs[:] = []
                continue
            seen.add(rp)
        else:
            links += [os.path.join(d, x) for x in dirs if os.path.islink(os.path.join(d, x))]
        dirs[:] = [x for x in dirs if not x.startswith(('.', '@', '#', '$')) and x != 'System Volume Information']  # o.a. Synology @eaDir/#recycle, Windows $RECYCLE.BIN
        for f in files:
            stem, e = os.path.splitext(f)
            is_zip = zip_on and e.lower() == '.zip'
            if f.startswith('.') or (e.lower() not in allowed and not is_zip):
                continue
            p = os.path.join(d, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if is_zip:
                zips.append((p, st.st_size, st.st_mtime))
            if e.lower() in allowed:
                found[p] = (stem, e[1:].lower(), st.st_size, st.st_mtime)
                SCANP['files'] += 1
    if ndirs == 1 and top_sub:
        log.warning('Root folder %s: alleen de hoofdmap is doorzocht, de %d submappen niet (symbolische links of een leesfout?).', root, top_sub)
    for e_ in errs[:10]:
        log.warning('Map niet te lezen, overgeslagen: %s (%s)', e_.filename, e_.strerror or e_)
    if len(errs) > 10:
        log.warning('Nog %d mappen niet te lezen in %s', len(errs) - 10, root)
    for l_ in links[:10]:
        log.warning('Map is een symbolische link en wordt niet gevolgd: %s (zet FOLLOW_SYMLINKS=1 om links te volgen)', l_)
    if len(links) > 10:
        log.warning('Nog %d symbolische links overgeslagen in %s', len(links) - 10, root)
    zset = {z[0] for z in zips}
    for k in [k for k in STABLE if k.startswith(root) and k not in found and k not in zset]:
        del STABLE[k]
    ev, meta = [], {}
    with db() as c:
        ex = {x['path']: x for x in c.execute('SELECT * FROM models WHERE root_id=?', (r['id'],))}
        taken = {x[0] for x in c.execute('SELECT path FROM models WHERE root_id<>?', (r['id'],))}  # path is uniek voor de hele database: bestanden van een andere root (overlappende roots) niet nogmaals toevoegen
        skipped = 0
        def sig(size, mt, e, member):  # zelfde bestand onder nieuwe naam/map herkennen
            return (size, mt, e) + ((posixpath.basename(member),) if member else ())

        orphan = {sig(x['size'], x['mtime'], x['ext'], x['member']) for x in ex.values() if x['container'] and x['container'] not in zset}
        for zp, zsize, zmt in zips:  # modellen in zips (zonder uitpakken)
            old = {k: x for k, x in ex.items() if x['container'] == zp}
            keep = bool(old) and all(abs(x['mtime'] - zmt) <= MTIME_TOL for x in old.values())  # zip ongewijzigd sinds de vorige scan
            if not keep:
                mem = zip_members(zp, allowed)
                moved = mem is not None and any(sig(ms, zmt, me, nm) in orphan for nm, _, me, ms in mem)  # verplaatst/hernoemd zip: niet wachten
                if not moved and unstable(zp, zsize, zmt):  # wordt nog gekopieerd: bestaande modellen laten staan
                    young += 1
                    keep = True
                elif mem is None:
                    log.warning('Zip niet te lezen, overgeslagen: %s', zp)
                    keep = True
                else:
                    for name, mstem, mext, msize in mem:
                        vp = f'{zp}!/{name}'
                        found[vp], meta[vp] = (mstem, mext, msize, zmt), (zp, name)
            if keep:
                for k, x in old.items():
                    found[k], meta[k] = (x['name'], x['ext'], x['size'], x['mtime']), (zp, x['member'])
        if ex and not found:
            log.warning('Root folder %s lijkt leeg terwijl %d modellen bekend zijn; niets verwijderd (mount offline?)', root, len(ex))
            _set_alert(r, 'empty', len(ex))
            return 0

        gone = {p: x for p, x in ex.items() if p not in found}
        bad_dirs = [e_.filename for e_ in errs if getattr(e_, 'filename', None)]
        if bad_dirs:  # een map kon niet gelezen worden (share haperde, rechten): de modellen daarin niet als verwijderd zien
            def under(p, d):
                d = os.path.normcase(os.path.normpath(d)); p = os.path.normcase(p)
                return p == d or p.startswith(d.rstrip('\\/') + os.sep)
            kept = [p for p, x in gone.items() if any(under(x['container'] or p, d) for d in bad_dirs)]
            for p in kept:
                gone.pop(p)
            if kept:
                log.warning('Root folder %s: %d model(len) in onleesbare mappen niet verwijderd', root, len(kept))
        bysig = {sig(x['size'], x['mtime'], x['ext'], x['member']): x for x in gone.values()}
        SCANP.update(phase='bijwerken', total=len(found), added=0)
        last_bump, batch = time.time(), 0
        for p, (stem, e, size, mt) in found.items():
            if batch >= 500:  # tussentijds vastleggen: modellen verschijnen al tijdens een grote scan, en een fout later in de scan draait niet alles terug
                c.commit()
                batch = 0
                if time.time() - last_bump > 2:
                    bump()
                    last_bump = time.time()
            st0 = 'pending' if e in render.CAN_THUMB else 'unsupported'
            cont, mem = meta.get(p, (None, None))
            row = ex.get(p)
            if row:
                if row['size'] != size or abs(row['mtime'] - mt) > MTIME_TOL:
                    if not cont and unstable(p, size, mt):  # nog in beweging (kopie bezig)
                        young += 1
                        continue
                    c.execute('UPDATE models SET size=?, mtime=?, thumb_status=?, thumb_error=NULL, info=NULL, hash=NULL, pdims=NULL, thumb_custom=0 WHERE id=?', (size, mt, st0, row['id']))
                    ev.append(('Gewijzigd', f'{stem}.{e} is gewijzigd, thumbnail wordt vernieuwd', row['id']))
                continue
            if p in taken:
                skipped += 1
                continue
            mv = bysig.pop(sig(size, mt, e, mem), None)  # eerder al volledig gezien
            if not mv and not cont and unstable(p, size, mt):
                young += 1
                continue
            if mv:
                c.execute('UPDATE models SET path=?, name=?, container=?, member=? WHERE id=?', (p, stem, cont, mem, mv['id']))
                gone.pop(mv['path'], None)
                ev.append(('Verplaatst', f"{posixpath.basename(mv['path'].replace(chr(92), '/'))} → {stem}.{e}", mv['id']))
            else:
                cur = c.execute('INSERT INTO models(root_id,path,name,ext,size,mtime,added_at,thumb_status,container,member) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (r['id'], p, stem, e, size, mt, now, st0, cont, mem))
                batch += 1
                SCANP['added'] += 1
                ev.append(('Toegevoegd', f'{stem}.{e}' + (f' (in {os.path.basename(cont)})' if cont else ''), cur.lastrowid))
        for p, x in gone.items():
            c.execute('DELETE FROM models WHERE id=?', (x['id'],))
            ev.append(('Verwijderd', f"{posixpath.basename(p.replace(chr(92), '/'))} niet meer gevonden", None))
            try:
                os.remove(os.path.join(THUMBS, f"{x['id']}.png"))
            except OSError:
                pass
    if errs:
        _set_alert(r, 'partial', len(ex), len(errs))
    else:
        _clear_alert(r)
    if skipped:
        log.warning('Root folder %s: %d bestand(en) overgeslagen omdat ze al bij een andere root folder staan (overlappende root folders?)', root, skipped)
    for e_ in ev:
        hist(*e_)
    new_ids = [e_[2] for e_ in ev if e_[0] == 'Toegevoegd' and e_[2]]
    if new_ids:
        try:
            apply_upload_cats(new_ids)
        except Exception as ex:
            log.warning('Categorieën van uploads toepassen mislukt: %s', ex)
        try:
            n = apply_rules(new_ids)
            if n:
                log.info('Regels: %d categorie-koppeling(en) gezet voor nieuwe modellen', n)
        except Exception as ex:  # indelen is een extra: een fout mag de scan nooit stoppen
            log.warning('Regels toepassen mislukt: %s', ex)
    if ev:
        log.info('Scan %s: %d wijziging(en)', root, len(ev))
    return young


def scan(root_id=None):
    if not scan_lock.acquire(blocking=False):
        return False
    T['scan']['running'], t0 = True, time.time()
    SCANP.update(phase='zoeken', dirs=0, files=0, added=0, total=0)
    bump()
    try:
        allowed, min_age = exts(), max(0, int(CFG['min_age']))
        with db() as c:
            roots = [dict(r) for r in c.execute('SELECT * FROM roots' + (' WHERE id=?' if root_id else ''), (root_id,) if root_id else ())]
        young = sum(_scan_root(r, allowed, min_age) for r in roots)
        try:
            n = assign_owners()
            if n:
                log.info('Eigenaar/school bijgewerkt voor %d model(len)', n)
        except Exception as e:  # een fout hier mag de scan nooit stoppen
            log.warning('Eigenaren bepalen mislukt: %s', e)
        if root_id is None:
            check_thumbs(False)
        if young:
            NEXT['soon'] = time.time() + min_age + 1
    except Exception as e:
        log.exception('Scan mislukt: %s', e)
    finally:
        T['scan'].update(running=False, last=time.time(), dur=time.time() - t0)
        SCANP.update(phase='')
        scan_lock.release()
        bump()
    return True


# ---------------------------------------------------------------- thumbnail-worker
def why(e):
    if isinstance(e, MemoryError):
        return 'Te weinig geheugen om dit model te verwerken'
    if isinstance(e, zipfile.BadZipFile):
        return 'Geen geldig 3MF-bestand (beschadigd of nog niet volledig gekopieerd?)'
    if isinstance(e, ElementTree.ParseError):
        return 'Bestand bevat ongeldige XML (beschadigd?)'
    return str(e) or e.__class__.__name__


def check_thumbs(deep=False):
    """Thumbnails die in de database 'ok' zijn maar ontbreken of niet bij het model horen (bijv. na het terugzetten van een
    back-up) opnieuw laten maken. deep=True leest ook het kenmerk in elke PNG; thumbnails van vóór dit kenmerk (zonder) blijven geldig."""
    with db() as c:
        rows = c.execute("SELECT id, size, mtime FROM models WHERE thumb_status='ok'").fetchall()
    bad = []
    for r in rows:
        p = os.path.join(THUMBS, f"{r['id']}.png")
        if not os.path.exists(p):
            bad.append((r['id'], 'ontbrak'))
        elif deep:
            try:
                with Image.open(p) as im:
                    tag = im.info.get('modelbib')
            except Exception:
                bad.append((r['id'], 'was onleesbaar'))
                continue
            if tag is not None and not tag_matches(tag, r):
                bad.append((r['id'], 'hoorde bij een ander model of bestand'))
    if bad:
        with db() as c:
            c.executemany("UPDATE models SET thumb_status='pending', thumb_error=NULL, thumb_custom=0 WHERE id=? AND thumb_status='ok'", [(i,) for i, _ in bad])
        why_ = ', '.join(f'{n}× {w}' for w, n in collections.Counter(w for _, w in bad).items())
        log.warning('Thumbnails hersteld: %s; ze worden opnieuw gemaakt', why_)
        hist('Hersteld', f'{len(bad)} thumbnail(s) opnieuw in de wachtrij ({why_})')
    T['thumbcheck']['last'] = time.time()
    return len(bad)


def rebuild_thumbs():
    with db() as c:
        c.executemany("UPDATE models SET thumb_status='pending' WHERE ext=? AND thumb_custom=0", [(e,) for e in render.CAN_THUMB])
    T['rebuild']['last'] = time.time()
    bump()


def backup_dir():
    """Waar de back-ups komen: de instelling in de app, anders BACKUP_DIR, anders <config>/backups."""
    return CFG['backup_dir'].strip() or (os.path.abspath(BACKUP_ENV) if BACKUP_ENV else '') or os.path.join(CONFIG, 'backups')


def check_backup_dir(p, create=False):
    """'' als de map bruikbaar is, anders een foutmelding. Een ontbrekende map wordt alleen aangemaakt met create=True (als je
    de map zelf opgeeft in de app). Bij een geplande back-up niet: is een share of schijf niet gekoppeld, dan mag er niet
    stilletjes een lege map op de verkeerde schijf ontstaan waar de back-ups dan terechtkomen."""
    if not os.path.isabs(p):
        return 'Geef een volledig pad op, zoals /backups of D:\\Back-ups'
    try:
        if not os.path.isdir(p):
            if not create:
                return f'Back-upmap bestaat niet (is de share of schijf gekoppeld?): {p}'
            os.makedirs(p, exist_ok=True)
        t = os.path.join(p, '.modelarr-schrijftest')
        with open(t, 'w') as f:
            f.write('ok')
        os.remove(t)
    except OSError as e:
        return f'Back-upmap is niet beschrijfbaar: {e.strerror or e}'
    return ''


BACKUP_LOCK = threading.Lock()


def backup():
    if not BACKUP_LOCK.acquire(blocking=False):  # er loopt er al een (bijv. net gestart door het opslaan van de map)
        return
    try:
        _backup()
    finally:
        BACKUP_LOCK.release()


def _backup():
    """Maakt een back-up in de ingestelde map. Altijd daar: valt de map weg (bijv. een NAS die uit staat), dan mislukt de
    back-up met een melding en volgt na een uur een nieuwe poging; er wordt niet stilletjes naar een andere map geschreven.
    De database wordt eerst lokaal gekopieerd en daarna als .part naar de doelmap, zodat SQLite nooit op een netwerkshare
    schrijft en een halve kopie (verbinding weg) nooit voor een echte back-up kan doorgaan."""
    t0, d = time.time(), backup_dir()
    stamp = time.strftime('%Y%m%d-%H%M%S')
    dest, zdest = os.path.join(d, f'library-{stamp}.db'), os.path.join(d, f'library-{stamp}-thumbs.zip')
    tmp = os.path.join(CONFIG, f'.backup-{stamp}.tmp')
    try:
        err = check_backup_dir(d, create=(d == os.path.join(CONFIG, 'backups')))  # alleen de standaardmap maakt zichzelf aan
        if err:
            raise OSError(err)
        src, dst = sqlite3.connect(DB), sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        shutil.copyfile(tmp, dest + '.part')
        os.replace(dest + '.part', dest)
        if CFG['backup_thumbs'] == '1':  # PNG's zijn al gecomprimeerd: alleen opslaan, niet nogmaals comprimeren
            with zipfile.ZipFile(zdest + '.part', 'w', zipfile.ZIP_STORED) as z:
                for f in sorted(os.listdir(THUMBS)):
                    if f.endswith('.png'):
                        z.write(os.path.join(THUMBS, f), f)
            os.replace(zdest + '.part', zdest)
        keep = max(1, int(CFG['backup_keep']))
        for suffix in ('.db', '-thumbs.zip'):
            for old in sorted(f for f in os.listdir(d) if f.startswith('library-') and f.endswith(suffix))[:-keep]:
                os.remove(os.path.join(d, old))
    except Exception as e:
        for p in (dest + '.part', zdest + '.part'):
            with contextlib.suppress(OSError):
                os.remove(p)
        T['backup'].update(error=str(e), failed=time.time())
        NEXT['backup'] = time.time() + 3600
        log.error('Back-up naar %s mislukt: %s (nieuwe poging over een uur)', d, e)
        return False
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)
    T['backup'].update(last=time.time(), dur=time.time() - t0, error=None, dir=d)
    log.info('Back-up gemaakt: %s%s', dest, ' (met thumbnails)' if CFG['backup_thumbs'] == '1' else '')
    return True


def file_hash(path):
    h = hashlib.blake2b(digest_size=16)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def hash_model(r):
    """Inhoud hashen (alleen bij bestanden met dezelfde grootte als een ander model) en een identieke kopie melden.
    '' = onleesbaar: wordt niet eindeloos opnieuw geprobeerd."""
    try:
        h = member_hash(r['container'], r['member']) if r['container'] else file_hash(r['path'])
    except (OSError, zipfile.BadZipFile, KeyError) as e:
        log.warning('Hashen mislukt voor %s: %s', r['path'], getattr(e, 'strerror', None) or e)
        h = ''
    with db() as c:
        c.execute('UPDATE models SET hash=? WHERE id=? AND size=?', (h, r['id'], r['size']))
        twin = c.execute('SELECT name, ext FROM models WHERE hash=? AND id<>?', (h, r['id'])).fetchone() if h else None
    if twin:
        hist('Dubbel', f"{r['name']}.{r['ext']} is identiek aan {twin['name']}.{twin['ext']}", r['id'])
    else:
        bump()


# ---------------------------------------------------------------- zware modelverwerking in een apart proces
ISOLATE = os.environ.get('THUMB_ISOLATE', '1') != '0'
THUMB_MEM_MB = int(os.environ.get('THUMB_MEM_MB', '4096') or 0)
THUMB_TIMEOUT = int(os.environ.get('THUMB_TIMEOUT', '600') or 0)  # seconden per model; 0 = geen limiet
ISO_RECYCLE_JOBS, ISO_RECYCLE_MB = 25, 800  # hulpproces vervangen na zoveel modellen of als het zoveel geheugen vasthoudt


class Isolated:
    """Eén hulpproces (renderproc.py) dat opdrachten uit render.py uitvoert. Loopt het vast, gebruikt het te veel geheugen
    of duurt het te lang, dan wordt alleen dat proces gestopt: de webserver blijft gewoon werken."""

    def __init__(self):
        self.p, self.n, self.lock = None, 0, threading.Lock()

    def _stop(self):
        p, self.p, self.n = self.p, None, 0
        if p:
            try:
                p.kill()
                p.wait(5)
            except Exception:
                pass

    def _rss_mb(self):
        try:
            with open(f'/proc/{self.p.pid}/statm') as f:
                return int(f.read().split()[1]) * (os.sysconf('SC_PAGE_SIZE') // 1024) / 1024
        except Exception:
            return 0

    def _read(self, n):
        buf = b''
        while len(buf) < n:
            c = self.p.stdout.read(n - len(buf))
            if not c:
                raise EOFError
            buf += c
        return buf

    def call(self, fn, *args, **kw):
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self._stop()
                env = dict(os.environ, THUMB_MEM_MB=str(THUMB_MEM_MB), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
                self.p = subprocess.Popen([sys.executable, os.path.join(BASE, 'renderproc.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          cwd=BASE, env=env, bufsize=0)
            import pickle, struct
            data = pickle.dumps((fn, args, kw), protocol=4)
            timed_out = []
            timer = threading.Timer(THUMB_TIMEOUT, lambda: (timed_out.append(1), self.p.kill())) if THUMB_TIMEOUT else None
            if timer:
                timer.start()
            try:
                self.p.stdin.write(struct.pack('>Q', len(data)) + data)
                kind, val = pickle.loads(self._read(struct.unpack('>Q', self._read(8))[0]))
            except (EOFError, OSError):
                code = self.p.poll() if self.p.poll() is not None else self.p.wait(5)
                self._stop()
                if timed_out:
                    raise RuntimeError(f'Verwerken duurde langer dan {THUMB_TIMEOUT} s (THUMB_TIMEOUT)')
                raise RuntimeError(f'Verwerking afgebroken (code {code}); waarschijnlijk te weinig geheugen')
            finally:
                if timer:
                    timer.cancel()
            self.n += 1
            if self.n >= ISO_RECYCLE_JOBS or self._rss_mb() > ISO_RECYCLE_MB:
                self._stop()
            if kind == 'exc':
                raise val
            return val


_ISO_LOCAL, ISO_VIEW = threading.local(), Isolated()


def heavy(fn, *args, view=False, **kw):
    """render.<fn>(*args) uitvoeren: in een apart, geheugenbegrensd proces (standaard) of in dit proces (THUMB_ISOLATE=0)."""
    if not ISOLATE:
        return ('mesh_stl' == fn and render.stl_bytes(*render.load_mesh(*args, **kw))) or getattr(render, fn)(*args, **kw)
    if view:
        return ISO_VIEW.call(fn, *args, **kw)
    if not hasattr(_ISO_LOCAL, 'iso'):
        _ISO_LOCAL.iso = Isolated()
    return _ISO_LOCAL.iso.call(fn, *args, **kw)


def thumb_for(r, out):
    with materialize(r) as src:
        return heavy('make_thumb', src, r['ext'], out, int(CFG['thumb_size']), prefer_embedded=CFG['thumb_source'] == 'embedded', tag=thumb_tag(r))


def plate_dims_model(r):
    """Afmetingen per plaat van een 3MF met meerdere platen bepalen (voor de 'past op printer'-controle). '[]' = geprobeerd, niets gevonden."""
    try:
        with materialize(r) as src:
            pd = heavy('plate_dims', src)
    except Exception as e:
        log.warning('Plaatafmetingen bepalen mislukt voor %s: %s', r['path'], why(e))
        pd = []
    with db() as c:
        c.execute('UPDATE models SET pdims=? WHERE id=? AND size=?', (json.dumps(pd), r['id'], r['size']))
    bump()


def read_info(r):
    """3MF-metadata lezen en opslaan. '{}' = geprobeerd, niets gevonden (voorkomt eindeloos opnieuw proberen)."""
    try:
        with materialize(r) as src:
            info = heavy('info_3mf', src)
    except Exception as e:
        log.warning('3MF-info lezen mislukt voor %s: %s', r['path'], why(e))
        info = {}
    with db() as c:
        c.execute('UPDATE models SET info=? WHERE id=?', (json.dumps(info, ensure_ascii=False), r['id']))
    bump()


def worker(first=True):
    try:  # lage prioriteit: de webinterface blijft vlot, ook op een NAS
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except (AttributeError, OSError):
        pass
    if first:
        try:
            check_thumbs(True)  # o.a. na het terugzetten van een back-up
        except Exception as e:
            log.error('Thumbnails controleren mislukt: %s', e)
    while True:
        try:
            if CFG['thumb_paused'] == '1':
                time.sleep(1)
                continue
            with db() as c:
                r = c.execute("SELECT * FROM models WHERE thumb_status='pending' ORDER BY id LIMIT 1").fetchone()
                todo = None if r else c.execute("SELECT * FROM models WHERE ext='3mf' AND info IS NULL LIMIT 1").fetchone()
                dup = None if (r or todo) else c.execute("SELECT * FROM models WHERE hash IS NULL AND size IN (SELECT size FROM models GROUP BY size HAVING COUNT(*) > 1) LIMIT 1").fetchone()
            if not r:  # niets te renderen: 3MF-info aanvullen, bestanden met gelijke grootte vergelijken, plaatafmetingen bepalen
                if todo:
                    read_info(todo)
                elif dup:
                    yield_to_users()
                    hash_model(dup)
                else:
                    with db() as c:
                        pdq = c.execute("SELECT * FROM models WHERE ext='3mf' AND pdims IS NULL AND info LIKE '%\"plates\"%' LIMIT 1").fetchone()
                    if pdq:
                        yield_to_users()
                        plate_dims_model(pdq)
                    else:
                        time.sleep(2)
                continue
            if r['ext'] == '3mf' and r['info'] is None:
                read_info(r)
            yield_to_users()
            with db() as c:  # atomair claimen: met meerdere workers pakt er maar één dit model
                if c.execute("UPDATE models SET thumb_status='processing' WHERE id=? AND thumb_status='pending'", (r['id'],)).rowcount != 1:
                    continue
            t_start = time.time()
            CUR.update(id=r['id'], name=r['name'], started=t_start)
            bump()
            try:
                if r['size'] > MAX_MB * 2 ** 20:
                    raise ValueError(f'Bestand groter dan {MAX_MB} MB (MAX_FILE_MB)')
                info = thumb_for(r, os.path.join(THUMBS, f"{r['id']}.png"))
                with db() as c:
                    c.execute("UPDATE models SET thumb_status='ok', thumb_error=NULL, thumb_at=?, dx=?, dy=?, dz=?, tris=? WHERE id=? AND thumb_status='processing'",
                              (time.time(), *info['dims'], info['tris'], r['id']))
                log.info('Thumbnail gemaakt: %s (%d driehoeken, %.1fs)', r['name'], info['tris'], time.time() - t_start)
            except render.NoPreview as e:
                with db() as c:
                    c.execute("UPDATE models SET thumb_status='unsupported', thumb_error=? WHERE id=? AND thumb_status='processing'", (str(e)[:300], r['id']))
            except Exception as e:
                with db() as c:
                    c.execute("UPDATE models SET thumb_status='failed', thumb_error=? WHERE id=? AND thumb_status='processing'", (why(e)[:300], r['id']))
                log.warning('Thumbnail mislukt voor %s: %s', r['path'], why(e))
                hist('Mislukt', f"Thumbnail voor {r['name']}.{r['ext']}: {why(e)[:150]}", r['id'])
            if CUR.get('id') == r['id']:
                CUR.clear()
            bump()
            time.sleep(max(0.0, float(CFG['thumb_delay'])))
        except Exception as e:
            log.error('Worker-fout: %s', e)
            time.sleep(5)


# ---------------------------------------------------------------- planner + bestandswachter
def scheduler():
    while True:
        time.sleep(1)
        now = time.time()
        try:
            if now >= NEXT['scan']:
                NEXT['scan'] = now + max(1, int(CFG['scan_interval'])) * 60
                scan()
            if NEXT['soon'] and now >= NEXT['soon']:
                NEXT['soon'] = 0
                scan()
            if now >= NEXT.get('bambuddy', 0):
                NEXT['bambuddy'] = now + 1800
                if CFG['bambuddy_url'] and CFG['bambuddy_key']:
                    try:
                        bambuddy_sync()
                    except ValueError as e:
                        log.warning('Bambuddy synchroniseren mislukt: %s', e)
            if now >= NEXT['backup']:
                NEXT['backup'] = now + 86400
                backup()
            for rid, t in list(dirty.items()):
                if now - t >= 3:  # debounce: wacht tot het rustig is
                    dirty.pop(rid, None)
                    if not scan(rid):
                        dirty[rid] = now
        except Exception as e:
            log.error('Planner-fout: %s', e)


def sync_watchers():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        return
    with db() as c:
        want = {r['id']: r['path'] for r in c.execute('SELECT * FROM roots WHERE watch=1') if os.path.isdir(r['path'])}
    for rid in list(OBS):
        if want.get(rid) != OBS[rid][1]:
            try:
                OBS.pop(rid)[0].stop()
            except Exception:  # nog niet (helemaal) gestart: niets om te stoppen
                pass

    def handler(rid):
        class H(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.event_type not in ('opened', 'closed_no_write') and '@eaDir' not in str(event.src_path):
                    dirty[rid] = time.time()
        return H()

    for rid, path in want.items():
        if rid in OBS:
            continue
        net = fs_type(path) if os.name != 'nt' else ''
        if net in NETFS or net.startswith(('nfs', 'cifs', 'smb')):
            # Op NFS/SMB komen wijzigingen van andere computers niet binnen, en het opzetten van de wachter loopt eerst de hele
            # mappenboom over het netwerk af (minuten bij tienduizenden bestanden). Daarom alleen periodiek scannen.
            log.info('Bestandswachter overgeslagen voor %s: netwerkshare (%s). Er wordt elke %s min gescand.', path, net, CFG['scan_interval'])
            continue
        try:
            o = Observer()
            o.schedule(handler(rid), path, recursive=True)
            o.daemon = True
            OBS[rid] = (o, path)
            threading.Thread(target=_start_observer, args=(o, rid, path), daemon=True).start()  # niet wachten: het opzetten kan lang duren
        except Exception as e:
            OBS.pop(rid, None)
            log.warning('Bestandswachter niet actief voor %s (%s); terugval op periodiek scannen', path, e)


def _start_observer(o, rid, path):
    """Start de wachter op de achtergrond: watchdog loopt hierbij de hele mappenboom af, en de webserver mag daar niet op wachten."""
    t0 = time.time()
    try:
        o.start()
        if OBS.get(rid, (None,))[0] is not o:  # intussen weer uitgezet: meteen stoppen
            o.stop()
            return
        log.info('Bestandswachter actief: %s (%.1fs)', path, time.time() - t0)
    except Exception as e:
        if OBS.get(rid, (None,))[0] is o:
            OBS.pop(rid, None)
        log.warning('Bestandswachter niet actief voor %s (%s); terugval op periodiek scannen', path, e)


# ---------------------------------------------------------------- authenticatie (optioneel)
@app.before_request
def mark_user():
    p = request.path
    if p.startswith('/api/') and p != '/api/rev' and not p.startswith('/api/thumb/') and not request.headers.get('X-Auto'):  # X-Auto = automatisch herladen door de pagina zelf
        LAST_USER[0] = time.time()


# ---------------------------------------------------------------- gebruikers en toegang
OPEN_PATHS = ('/', '/ping', '/api/login', '/api/me', '/api/ms/login', '/api/ms/callback')  # nodig om de inlogpagina te kunnen tonen
USERNAME_RE = re.compile(r'^[\w.@-]{1,40}$')


def refresh_auth():
    """Inloggen is verplicht zodra er minstens één account is."""
    with db() as c:
        AUTH_ON[0] = c.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0
    OKAUTH.clear()


def migrate_legacy_auth():
    """De oude enkele inlog (instellingen auth_user/auth_hash) omzetten naar een beheerdersaccount."""
    name = CFG['auth_user']
    if name and CFG['auth_hash']:
        with db() as c:
            if not c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                c.execute("INSERT INTO users(username, pw_hash, role, created) VALUES(?,?, 'admin', ?)", (name, CFG['auth_hash'], time.time()))
                log.info('Bestaande inlog omgezet naar beheerdersaccount "%s"', name)
        put('auth_user', '')
        put('auth_hash', '')


def bootstrap_env_admin():
    """AUTH_USER/AUTH_PASS: maakt bij de eerste start een beheerdersaccount aan als er nog geen accounts zijn."""
    u, p = os.environ.get('AUTH_USER', '').strip(), os.environ.get('AUTH_PASS', '')
    if u and p and not AUTH_ON[0]:
        with db() as c:
            c.execute("INSERT INTO users(username, pw_hash, role, created) VALUES(?,?, 'admin', ?)", (u, generate_password_hash(p), time.time()))
        refresh_auth()
        log.info('Beheerdersaccount "%s" aangemaakt via AUTH_USER/AUTH_PASS', u)


EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$')


def parse_email(v):
    """(adres of None, foutmelding of None): een leeg veld betekent: geen e-mailadres."""
    e = str(v or '').strip()
    if not e:
        return None, None
    if len(e) > 254 or not EMAIL_RE.match(e):
        return None, 'Ongeldig e-mailadres'
    return e, None


def find_login(c, name):
    """Actieve gebruiker op gebruikersnaam of e-mailadres (hoofdletterongevoelig); een gebruikersnaam gaat voor."""
    return c.execute('SELECT * FROM users WHERE active=1 AND (username=? OR email=? COLLATE NOCASE) ORDER BY (username=?) DESC LIMIT 1', (name, name, name)).fetchone()


def current_user():
    """(gebruiker, via): via API-sleutel, sessiecookie of Basic-authenticatie. (None, None) zonder geldige inlog."""
    key = request.headers.get('X-Api-Key')
    if key and CFG['api_key'] and hmac.compare_digest(key.encode(), CFG['api_key'].encode()):
        return dict(id=0, username='api', role='admin', can_download=1, can_upload=1), 'key'
    if session.get('uid'):
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE id=? AND active=1', (session['uid'],)).fetchone()
        if r and r['ver'] == session.get('ver'):
            return dict(r), 'session'
    a = request.authorization
    if a and a.username and a.password is not None:
        with db() as c:
            r = find_login(c, a.username)
        if r:
            d = hashlib.sha256(f"{r['id']}:{r['ver']}:{a.password}".encode()).hexdigest()
            if d in OKAUTH or check_password_hash(r['pw_hash'], a.password):
                OKAUTH.add(d)
                return dict(r), 'basic'
    return None, None


# ---------------------------------------------------------------- scholen: rollen, mappen en zichtbaarheid
ROLES = ('admin', 'staff', 'student')
SUBDIR = {'student': 'leerlingen', 'staff': 'medewerkers'}


def slugify(t, default='x'):
    t = unicodedata.normalize('NFKD', str(t or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:40] or default


def _hid_match(hid, root_id, folder):
    f = (folder or '').replace('\\', '/').strip('/')
    return any(r == root_id and (f == rel or f.startswith(rel + '/')) for r, rel in hid)


def folder_hidden_db(m):
    """Staat de map van dit model (of een bovenliggende map) op 'verborgen voor leerlingen'? (voor een model uit de database)"""
    with db() as c:
        hid = [(r['root_id'], r['rel']) for r in c.execute('SELECT * FROM hidden_folders')]
        if not hid:
            return False
        root = c.execute('SELECT path FROM roots WHERE id=?', (m['root_id'],)).fetchone()
    if not root:
        return False
    try:
        folder = os.path.relpath(os.path.dirname(m['path']), root['path'])
    except ValueError:
        return False
    return _hid_match(hid, m['root_id'], '' if folder == '.' else folder)


def can_see(u, m):
    """Mag deze gebruiker dit model zien? Beheerder: alles. Medewerker: alles van de eigen school. Anderen: eigen modellen en wat gedeeld is
    (standaard alles; een leerling kan het per model uitzetten) en niet door een medewerker verborgen. Modellen buiten elke school: alleen beheerder."""
    if not u:
        return False
    if u['role'] == 'admin':
        return True
    sid = m['school_id']
    if sid is None:  # algemene bibliotheek (buiten de schoolmappen): zichtbaar voor iedereen, tenzij een medewerker of beheerder de map heeft verborgen
        if u['role'] == 'staff':
            return True
        return not (m['fhidden'] if isinstance(m, dict) and 'fhidden' in m else folder_hidden_db(m))
    if u['role'] == 'staff' and u.get('school_id') == sid:
        return True
    if m['owner_id'] is not None and m['owner_id'] == u['id']:
        return True
    return bool(m['shared']) and not m['hidden']


def can_manage(u, m):
    """Mag deze gebruiker dit model beheren (delen aan/uit, verwijderen)? Eigenaar, medewerker van dezelfde school of beheerder."""
    if u['role'] == 'admin':
        return True
    if m['owner_id'] is not None and m['owner_id'] == u['id']:
        return True
    return u['role'] == 'staff' and m['school_id'] is not None and u.get('school_id') == m['school_id']


def share_default_for(u, schools=None):
    """Worden nieuwe uploads van deze gebruiker standaard gedeeld? Leerling: de eigen keuze als die is gezet, anders die van de school,
    anders de algemene instelling (Instellingen → Algemeen). Medewerker en beheerder: hun eigen standaard (standaard aan)."""
    if u.get('role') != 'student':
        return bool(u.get('share_default', 1) if u.get('share_default') is not None else 1)
    if u.get('share_own') is not None:
        return bool(u['share_own'])
    sid = u.get('school_id')
    if sid:
        if schools is not None:
            v = schools.get(sid)
        else:
            with db() as c:
                r = c.execute('SELECT share_default FROM schools WHERE id=?', (sid,)).fetchone()
            v = r['share_default'] if r else None
        if v is not None:
            return bool(v)
    return CFG['default_share'] == '1'


def assign_owners():
    """Eigenaar en school van elk model afleiden uit het pad: <school>/leerlingen/<leerling>/... of <school>/medewerkers/<medewerker>/...
    Wordt na elke scan uitgevoerd. Een nieuw model krijgt de standaard-deelkeuze van zijn eigenaar. Geeft het aantal gewijzigde modellen."""
    with db() as c:
        by_root = {}
        for sc in c.execute('SELECT id, slug, root_id FROM schools WHERE root_id IS NOT NULL'):
            by_root.setdefault(sc['root_id'], {})[sc['slug'].lower()] = sc['id']
        if not by_root:
            return 0
        homes = {}
        sch_share = {r['id']: r['share_default'] for r in c.execute('SELECT id, share_default FROM schools')}
        for u in c.execute("SELECT id, home, role, school_id, share_default, share_own FROM users WHERE home IS NOT NULL AND home<>''"):
            pr = u['home'].replace('\\', '/').split('/')
            if len(pr) == 3:
                homes[(pr[0].lower(), pr[1], pr[2].lower())] = u
        roots = {r['id']: r['path'] for r in c.execute('SELECT id, path FROM roots')}
        n = 0
        for rid, slugs in by_root.items():
            rp = roots.get(rid)
            if not rp:
                continue
            for m in c.execute('SELECT id, path, owner_id, school_id FROM models WHERE root_id=?', (rid,)).fetchall():
                try:
                    parts = os.path.relpath(m['path'], rp).replace(os.sep, '/').split('/')
                except ValueError:
                    continue
                sid = slugs.get(parts[0].lower()) if len(parts) > 1 else None
                own = homes.get((parts[0].lower(), parts[1], parts[2].lower())) if sid and len(parts) >= 4 else None
                oid = own['id'] if own else None
                if (oid, sid) != (m['owner_id'], m['school_id']):
                    if own and m['owner_id'] is None:
                        up = c.execute('SELECT shared FROM upload_share WHERE path=?', (m['path'],)).fetchone()
                        sh = up['shared'] if up else (1 if share_default_for(dict(own), sch_share) else 0)
                        c.execute('UPDATE models SET owner_id=?, school_id=?, shared=? WHERE id=?', (oid, sid, sh, m['id']))
                        c.execute('DELETE FROM upload_share WHERE path=?', (m['path'],))
                    else:
                        c.execute('UPDATE models SET owner_id=?, school_id=? WHERE id=?', (oid, sid, m['id']))
                    n += 1
    return n


# wat een medewerker of leerling mag (methode, pad, extra eis). Beheerders mogen alles.
_COMMON = [('GET', r'/api/(library|rev|me/prefs|printers)', None), ('GET', r'/api/thumb/\d+\.png', None), ('GET', r'/api/(mesh/\d+\.stl|file/\d+)', 'download'),
           ('POST', r'/api/models/\d+/link', 'download'), ('POST', r'/api/logout', None), ('POST', r'/api/me/prefs', None),
           ('GET', r'/api/upload/(targets|dirs)', 'upload'), ('POST', r'/api/upload', 'upload'),
           ('POST', r'/api/models/\d+/(share|delete|report)', None), ('GET', r'/api/requests/options', None),
           ('GET', r'/api/requests', None), ('POST', r'/api/requests', None), ('POST', r'/api/requests/\d+/cancel', None)]
_STAFF = [('GET', r'/api/folder-access', None), ('POST', r'/api/folder-access/hide', None), ('GET', r'/api/reports', None), ('POST', r'/api/reports/\d+', None), ('POST', r'/api/models/\d+/hide', None),
          ('POST', r'/api/requests/\d+', None), ('POST', r'/api/requests/\d+/file', None), ('GET', r'/api/requests/\d+/file', None),
          ('GET', r'/api/school/users', None), ('POST', r'/api/school/users', None), ('POST', r'/api/school/users/import', None), ('POST', r'/api/school/users/remove', None),
          ('PUT', r'/api/school/users/\d+', None), ('DELETE', r'/api/school/users/\d+', None), ('GET', r'/api/school/info', None)]


def role_ok(user):
    p, m = request.path, request.method
    for rm, rx, need in _COMMON + (_STAFF if user['role'] == 'staff' else []):
        if rm == m and re.fullmatch(rx, p):
            if need == 'download':
                return bool(user['can_download'])
            if need == 'upload':
                return bool(user.get('can_upload'))
            return True
    return False


@app.before_request
def guard():
    p = request.path
    g.user = g.via = None
    if p in OPEN_PATHS or p.startswith('/dl/') or p.startswith('/static/'):  # /dl/: de ondertekende link is zelf de toegang
        return
    if not AUTH_ON[0]:  # nog geen accounts: iedereen is beheerder (de app waarschuwt hiervoor)
        g.user, g.via = dict(id=0, username='', role='admin', can_download=1, can_upload=1), 'open'
        return
    user, via = current_user()
    if user is None:
        return jsonify(error='Inloggen vereist', login=True), 401
    g.user, g.via = user, via
    if user['role'] != 'admin' and not role_ok(user):
        log.warning('Geweigerd: %s %s voor %s (%s)', request.method, request.path, user['username'], user['role'])
        return jsonify(error='Je account heeft hier geen toestemming voor', path=request.path), 403
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH') and via == 'session' and request.headers.get('X-Requested-With') != 'modelbib':
        return jsonify(error='Ongeldig verzoek'), 403  # bescherming tegen verzoeken vanaf andere websites


def me_payload(u):
    if not AUTH_ON[0]:
        return dict(auth=False, user=None, role='admin', can_download=True, can_upload=True)
    if not u:
        return dict(auth=True, user=None, role=None, can_download=False, can_upload=False, ms=ms_ready(), ms_only=ms_ready() and CFG['ms_only'] == '1')
    sc = None
    if u.get('school_id'):
        with db() as c:
            r = c.execute('SELECT id, name FROM schools WHERE id=?', (u['school_id'],)).fetchone()
        sc = dict(r) if r else None
    return dict(auth=True, version=VERSION, user=u['username'], role=u['role'], id=u['id'], can_download=bool(u['can_download']), can_upload=u['role'] == 'admin' or bool(u.get('can_upload')),
                display=u.get('display_name') or u['username'], klas=u.get('klas') or '', school=sc, share_default=share_default_for(u))


@app.get('/api/me')
def me():
    return jsonify(me_payload(current_user()[0] if AUTH_ON[0] else None))


@app.post('/api/login')
def login():
    ip = request.remote_addr or '?'
    now = time.time()
    FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < 600]
    if len(FAILS[ip]) >= 5:
        return jsonify(error='Te veel mislukte pogingen. Probeer het over 10 minuten opnieuw.'), 429
    j = request.json or {}
    with db() as c:
        r = find_login(c, str(j.get('username') or '').strip())
    ok = check_password_hash(r['pw_hash'] if r else DUMMY_HASH, str(j.get('password') or '')) and r is not None  # altijd rekenen: geen verschil in tijd
    if ok and ms_ready() and CFG['ms_only'] == '1' and (r['role'] != 'admin' or r['ms_oid']):
        return jsonify(error='Inloggen kan alleen met Microsoft'), 403  # alleen lokale beheerders houden een noodingang
    if not ok:
        FAILS[ip].append(now)
        log.warning('Mislukte inlogpoging voor "%s" vanaf %s', str(j.get('username') or '')[:40], ip)
        return jsonify(error='Onjuiste gebruikersnaam of wachtwoord'), 401
    FAILS.pop(ip, None)
    session.clear()
    session.permanent = True
    session['uid'], session['ver'] = r['id'], r['ver']
    with db() as c:
        c.execute('UPDATE users SET last_login=? WHERE id=?', (now, r['id']))
    log.info('Ingelogd: %s', r['username'])
    return jsonify(me_payload(dict(r)))


@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


# ---------------------------------------------------------------- inloggen met Microsoft (Entra ID)
def ms_ready():
    return CFG['ms_enabled'] == '1' and INT.valid_tenant(CFG['ms_tenant']) and bool(CFG['ms_client_id'] and CFG['ms_client_secret'])


def ms_redirect():
    base = (CFG['public_url'] or request.host_url).rstrip('/')
    return base + '/api/ms/callback'


def _ms_page(msg, code=400):
    html = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Inloggen mislukt</title>'
            '<body style="font:16px system-ui;background:#16181f;color:#e6e8ef;display:grid;place-items:center;min-height:100vh;margin:0"><div style="max-width:440px;padding:24px">'
            '<h2>Inloggen met Microsoft mislukt</h2><p>%s</p><p><a style="color:#8fb0ff" href="/">Terug naar de inlogpagina</a></p></div>' % (msg.replace('&', '&amp;').replace('<', '&lt;')))
    return Response(html, code, mimetype='text/html')


@app.get('/api/ms/login')
def ms_login():
    if not ms_ready():
        return _ms_page('Inloggen met Microsoft staat niet aan.', 404)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    ver, chal = INT.pkce()
    session['ms'] = dict(state=state, nonce=nonce, ver=ver, ts=time.time())
    return Response(status=302, headers={'Location': INT.auth_url(CFG['ms_tenant'], CFG['ms_client_id'], ms_redirect(), state, nonce, chal)})


def ms_provision(c, claims, role, school_id, klas=None):
    """Account bij een Microsoft-gebruiker zoeken of aanmaken; rol en school volgen de groepen. (rij, fout)"""
    oid = str(claims.get('oid') or claims.get('sub')).lower()
    upn = str(claims.get('preferred_username') or claims.get('email') or claims.get('upn') or oid).strip().lower()
    mail = str(claims.get('email') or (upn if '@' in upn else '') or '').strip().lower() or None
    name = str(claims.get('name') or upn).strip()[:80]
    u = c.execute('SELECT * FROM users WHERE ms_oid=?', (oid,)).fetchone()
    if not u:  # bestaand lokaal account met dezelfde inlognaam of hetzelfde e-mailadres koppelen
        u = c.execute('SELECT * FROM users WHERE ms_oid IS NULL AND (username=? OR (email IS NOT NULL AND email=?)) COLLATE NOCASE', (upn, mail)).fetchone()
    if u and not u['active']:
        return None, 'Dit account is uitgeschakeld. Neem contact op met de beheerder.'
    if u:
        keep_admin = u['role'] == 'admin' and u['ms_oid'] is None  # een lokale beheerder verliest zijn rechten niet door een koppeling
        role, school_id = ('admin', None) if keep_admin else (role, school_id)
        home = u['home'] if (u['home'] and u['school_id'] == school_id and u['role'] == role) else (make_home(c, school_id, role, upn.split('@')[0]) if school_id else None)
        if klas and role == 'student':  # klas volgt het veld Afdeling in Microsoft
            c.execute('UPDATE users SET klas=? WHERE id=?', (klas[:20], u['id']))
        c.execute('UPDATE users SET ms_oid=?, role=?, school_id=?, home=?, display_name=?, email=COALESCE(email, ?) WHERE id=?', (oid, role, school_id, home, name, mail if mail and not c.execute('SELECT 1 FROM users WHERE email=? COLLATE NOCASE AND id<>?', (mail, u['id'])).fetchone() else None, u['id']))
        return c.execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone(), None
    if c.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE', (upn,)).fetchone():
        return None, 'Er bestaat al een account met deze naam'
    if mail and c.execute('SELECT 1 FROM users WHERE email=? COLLATE NOCASE', (mail,)).fetchone():
        mail = None
    home = make_home(c, school_id, role, upn.split('@')[0]) if school_id else None
    uid = c.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, created, email, school_id, display_name, home, ms_oid, klas) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (upn, generate_password_hash(secrets.token_urlsafe(32)), role, 1, 1, time.time(), mail, school_id, name, home, oid, (klas or '')[:20] if role == 'student' else '')).lastrowid
    return c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone(), None


@app.get('/api/ms/callback')
def ms_callback():
    if not ms_ready():
        return _ms_page('Inloggen met Microsoft staat niet aan.', 404)
    st = session.pop('ms', None)
    a = request.args
    if a.get('error'):
        return _ms_page(a.get('error_description') or a.get('error'))
    if not st or time.time() - st['ts'] > 900 or not a.get('state') or not secrets.compare_digest(a['state'], st['state']) or not a.get('code'):
        return _ms_page('De inlogpoging is verlopen of ongeldig. Probeer het opnieuw.')
    try:
        tok = INT.exchange(CFG['ms_tenant'], CFG['ms_client_id'], CFG['ms_client_secret'], ms_redirect(), a['code'], st['ver'])
        claims = INT.check_claims(INT.jwt_claims(tok['id_token']), CFG['ms_tenant'], CFG['ms_client_id'], st['nonce'])
        groups = INT.groups_for(claims, tok.get('access_token'))
    except INT.AuthError as e:
        log.warning('Microsoft-inlog mislukt: %s', e)
        return _ms_page(str(e))
    with db() as c:
        schools = [dict(r) for r in c.execute('SELECT id, group_id, staff_group_id FROM schools WHERE active=1')]
    res = INT.resolve_role(groups, CFG['ms_admin_group'], schools)
    who = str(claims.get('preferred_username') or claims.get('email') or claims.get('oid'))
    if not res:
        log.warning('Microsoft-inlog geweigerd (geen bekende groep): %s', who)
        return _ms_page('Je account is niet gekoppeld aan een school. Vraag de beheerder om je in de juiste groep te zetten.', 403)
    klas = INT.department(tok.get('access_token')) if CFG['ms_klas'] == '1' and res[0] == 'student' else None
    with db() as c:
        u, err = ms_provision(c, claims, *res, klas=klas)
        if u:
            c.execute('UPDATE users SET last_login=? WHERE id=?', (time.time(), u['id']))
    if err:
        return _ms_page(err, 403)
    session.clear()
    session.permanent = True
    session['uid'], session['ver'] = u['id'], u['ver']
    OKAUTH.clear()
    AUTH_ON[0] = True
    log.info('Ingelogd via Microsoft: %s (%s)', u['username'], u['role'])
    return Response(status=302, headers={'Location': '/'})


def make_home(c, school_id, role, username):
    """Thuismap voor een gebruiker: <school>/leerlingen|medewerkers/<naam>, uniek, en aangemaakt op de schijf (als de school een opslagmap heeft)."""
    sc = c.execute('SELECT s.slug, r.path FROM schools s LEFT JOIN roots r ON r.id=s.root_id WHERE s.id=?', (school_id,)).fetchone()
    if not sc:
        return None
    base, n = slugify(username, 'gebruiker'), 1
    sub = SUBDIR.get(role, 'medewerkers')
    while True:
        h = f"{sc['slug']}/{sub}/{base}" + (f'-{n}' if n > 1 else '')
        if not c.execute('SELECT 1 FROM users WHERE lower(home)=lower(?)', (h,)).fetchone():
            break
        n += 1
    if sc['path']:
        try:
            os.makedirs(os.path.join(sc['path'], *h.split('/')), exist_ok=True)
        except OSError as e:
            log.warning('Thuismap aanmaken mislukt: %s', e)
    return h


def _pw():
    al = 'abcdefghjkmnpqrstuvwxyz23456789'
    return ''.join(secrets.choice(al) for _ in range(10))


def _school_user_rows(school_id):
    with db() as c:
        return [dict(id=r['id'], username=r['username'], display_name=r['display_name'] or '', klas=r['klas'] or '', email=r['email'] or '', active=bool(r['active']), can_upload=bool(r['can_upload']),
                     last_login=r['last_login'], ms=bool(r['ms_oid']), used_mb=0) for r in c.execute("SELECT * FROM users WHERE school_id=? AND role='student' ORDER BY klas, COALESCE(NULLIF(display_name,''), username) COLLATE NOCASE", (school_id,))]


def _need_school():
    """School waarvoor de aanvraag geldt: de eigen school van een medewerker; een beheerder geeft school_id mee."""
    u = g.user
    if u['role'] != 'admin':
        return u.get('school_id')
    sid = request.values.get('school_id', type=int)
    if sid is None and request.is_json:
        try:
            sid = int((request.get_json(silent=True) or {}).get('school_id'))
        except (TypeError, ValueError):
            sid = None
    return sid


def add_student(c, school_id, name, pw, display, klas, email):
    """(fout, uid) leerling aanmaken in een school."""
    if not USERNAME_RE.match(name):
        return f'Ongeldige gebruikersnaam: {name}', None
    if len(pw) < 8:
        return 'Wachtwoord te kort (minstens 8 tekens)', None
    email, err = parse_email(email)
    if err:
        return err, None
    if c.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone():
        return f'Gebruikersnaam bestaat al: {name}', None
    if email and c.execute('SELECT 1 FROM users WHERE email=? COLLATE NOCASE', (email,)).fetchone():
        return f'E-mailadres bestaat al: {email}', None
    home = make_home(c, school_id, 'student', name)
    uid = c.execute('INSERT INTO users(username, pw_hash, role, can_download, can_upload, created, email, school_id, display_name, klas, home) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (name, generate_password_hash(pw), 'student', 1, 1, time.time(), email, school_id, display[:80], klas[:20], home)).lastrowid
    return None, uid


@app.get('/api/school/info')
def school_info():
    sid = _need_school()
    with db() as c:
        sc = c.execute('SELECT * FROM schools WHERE id=?', (sid,)).fetchone()
    if not sc:
        return jsonify(error='School niet gevonden'), 404
    return jsonify(id=sc['id'], name=sc['name'], quota_mb=quota_mb(sc), students=len(_school_user_rows(sid)))


@app.get('/api/school/users')
def school_users_get():
    sid = _need_school()
    return jsonify(users=_school_user_rows(sid))


@app.post('/api/school/users')
def school_users_add():
    j = request.json or {}
    sid = _need_school()
    name = str(j.get('username') or '').strip()
    display = str(j.get('display_name') or '').strip() or name
    pw = str(j.get('password') or '') or _pw()
    with db() as c:
        if not c.execute('SELECT 1 FROM schools WHERE id=? AND active=1', (sid,)).fetchone():
            return jsonify(error='School niet gevonden'), 404
        err, uid = add_student(c, sid, name, pw, display, str(j.get('klas') or '').strip(), j.get('email'))
    if err:
        return jsonify(error=err), 400
    return jsonify(ok=True, id=uid, username=name, password=pw)


def _csv_rows(text):
    import csv
    text = text.lstrip('\ufeff')
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=';,\t')
    except csv.Error:
        dialect = csv.excel
    rd = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in rd if any(x.strip() for x in r)]
    if not rows:
        return []
    alias = {'naam': 'display_name', 'name': 'display_name', 'leerling': 'display_name', 'weergavenaam': 'display_name', 'gebruikersnaam': 'username', 'username': 'username', 'login': 'username',
             'inlognaam': 'username', 'wachtwoord': 'password', 'password': 'password', 'klas': 'klas', 'class': 'klas', 'groep': 'klas', 'email': 'email', 'e-mail': 'email', 'mail': 'email', 'emailadres': 'email'}
    head = [alias.get(x.strip().lower().replace(' ', ''), '') for x in rows[0]]
    if not ({'display_name', 'username', 'email'} & set(head)):
        return None
    return [{k: (r[i].strip() if i < len(r) else '') for i, k in enumerate(head) if k} for r in rows[1:]]


def _import_match(c, sid, r):
    """Bestaande leerling in deze school bij een CSV-regel: op gebruikersnaam, anders op e-mailadres. Op naam alleen wordt niet gekoppeld: twee leerlingen kunnen dezelfde naam hebben."""
    q = "SELECT * FROM users WHERE role='student' AND school_id=? AND "
    if r.get('username'):
        return c.execute(q + 'username=? COLLATE NOCASE', (sid, r['username'])).fetchone()
    if r.get('email'):
        x = c.execute(q + 'email=? COLLATE NOCASE', (sid, r['email'])).fetchone()
        if x:
            return x
    return None


@app.post('/api/school/users/import')
def school_users_import():
    """CSV (kolommen: naam, gebruikersnaam, wachtwoord, klas, email). Alleen naam is genoeg: de rest wordt aangemaakt. Met preview=1 gebeurt er niets, je ziet alleen wat er zou komen."""
    sid = _need_school()
    prev = request.values.get('preview') in ('1', 'true')
    f = request.files.get('file')
    raw = f.read(2 * 2 ** 20) if f else (request.data or b'')
    if not raw:
        return jsonify(error='Geen bestand ontvangen'), 400
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')
    rows = _csv_rows(text)
    if rows is None:
        return jsonify(error='Zet in de eerste regel de kolomnamen: naam, gebruikersnaam, wachtwoord, klas, email'), 400
    if len(rows) > 2000:
        return jsonify(error='Maximaal 2000 regels per import'), 400
    out, ok = [], 0
    with db() as c:
        if not c.execute('SELECT 1 FROM schools WHERE id=? AND active=1', (sid,)).fetchone():
            return jsonify(error='School niet gevonden'), 404
        seen, upd = set(), 0
        for i, r in enumerate(rows, 2):
            display = r.get('display_name', '')
            ex = _import_match(c, sid, r)  # bestaande leerling van deze school: bijwerken (klas, naam) in plaats van een fout
            if ex:
                if ex['id'] in seen:
                    out.append(dict(line=i, name=display, error='Deze leerling staat al eerder in het bestand'))
                    continue
                seen.add(ex['id'])
                klas = r.get('klas', '')
                if not prev and (klas or (display and r.get('username'))):
                    c.execute('UPDATE users SET klas=COALESCE(NULLIF(?, \'\'), klas), display_name=COALESCE(NULLIF(?, \'\'), display_name) WHERE id=?',
                              (klas[:20], display[:80] if r.get('username') else '', ex['id']))
                upd += 1
                out.append(dict(line=i, name=display or ex['display_name'] or ex['username'], username=ex['username'], klas=klas or ex['klas'] or '', updated=True))
                continue
            name = r.get('username') or slugify(display, '')
            if not name:
                out.append(dict(line=i, name=display, error='Naam of gebruikersnaam ontbreekt'))
                continue
            if not r.get('username'):  # automatisch gemaakte gebruikersnaam uniek maken
                base, n = name, 1
                while c.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone() or name in seen:
                    n += 1
                    name = f'{base}{n}'
            seen.add(name)
            pw = r.get('password') or _pw()
            if prev:
                bad = None if USERNAME_RE.match(name) and not c.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone() else 'Gebruikersnaam ongeldig of bestaat al'
                uid = None
            else:
                bad, uid = add_student(c, sid, name, pw, display or name, r.get('klas', ''), r.get('email') or None)
            if bad:
                out.append(dict(line=i, name=display or name, username=name, error=bad))
            else:
                ok += 1
                out.append(dict(line=i, name=display or name, username=name, password=pw, klas=r.get('klas', '')))
    if (ok or upd) and not prev:
        hist('Gebruikers', f"{g.user['username']} importeerde {ok} leerlingen, {upd} bijgewerkt")
        OKAUTH.clear()
    return jsonify(ok=ok, updated=upd, failed=len([x for x in out if x.get('error')]), preview=prev, rows=out)


def _own_student(uid):
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not u or u['role'] != 'student' or not _staff_of(g.user, u['school_id']):
        abort(404)
    return u


@app.put('/api/school/users/<int:uid>')
def school_users_put(uid):
    """Medewerker: wachtwoord opnieuw instellen, naam/klas wijzigen, account (de)activeren, uploaden aan/uit."""
    u, j = _own_student(uid), request.json or {}
    pw = j.get('password')
    if pw == True:
        pw = _pw()
    out = {}
    with db() as c:
        ver, pw_hash = u['ver'], u['pw_hash']
        if pw:
            if not 8 <= len(str(pw)) <= 200:
                return jsonify(error='Het wachtwoord moet minstens 8 tekens hebben'), 400
            pw_hash, ver = generate_password_hash(str(pw)), ver + 1
            out['password'] = str(pw)
        active = 1 if j.get('active', bool(u['active'])) else 0
        if u['active'] and not active:
            ver += 1
        c.execute('UPDATE users SET display_name=?, klas=?, active=?, can_upload=?, pw_hash=?, ver=? WHERE id=?',
                  (str(j.get('display_name', u['display_name']) or '').strip()[:80], str(j.get('klas', u['klas']) or '').strip()[:20], active,
                   1 if j.get('can_upload', bool(u['can_upload'])) else 0, pw_hash, ver, uid))
    OKAUTH.clear()
    return jsonify(ok=True, **out)


@app.post('/api/school/users/remove')
def school_users_remove():
    """Leerlingen definitief verwijderen: {ids: [...]} of {inactive: true} (alle gedeactiveerde leerlingen van de school), files = 'keep' (standaard) of 'delete'.
    Bewaren: de map en modellen blijven, zonder eigenaar en niet meer gedeeld (alleen medewerkers zien ze). Verwijderen: de map gaat naar <root>/.prullenbak.
    Met preview=true gebeurt er niets en komt het aantal terug. Printaanvragen en meldingen blijven in de lijst staan."""
    j, sid = request.json or {}, _need_school()
    files = 'delete' if j.get('files') == 'delete' else 'keep'
    with db() as c:
        if j.get('inactive'):
            us = c.execute("SELECT * FROM users WHERE school_id=? AND role='student' AND active=0", (sid,)).fetchall()
        else:
            ids = [int(x) for x in (j.get('ids') or []) if str(x).lstrip('-').isdigit()]
            us = c.execute(f"SELECT * FROM users WHERE school_id=? AND role='student' AND id IN ({','.join('?' * len(ids)) or 'NULL'})", [sid] + ids).fetchall()
        us = [dict(u) for u in us]
        if j.get('preview'):
            return jsonify(ok=True, count=len(us), ms=sum(1 for u in us if u['ms_oid']), models=sum(c.execute('SELECT COUNT(*) FROM models WHERE owner_id=?', (u['id'],)).fetchone()[0] for u in us))
        sc = c.execute('SELECT s.slug, r.path FROM schools s LEFT JOIN roots r ON r.id=s.root_id WHERE s.id=?', (sid,)).fetchone()
    moved = failed = 0
    for u in us:
        if files == 'delete':
            with db() as c:
                mids = [r['id'] for r in c.execute('SELECT id FROM models WHERE owner_id=?', (u['id'],))]
            home = u['home'] or ''
            if sc and sc['path'] and home:
                src = os.path.join(sc['path'], *home.split('/'))
                if os.path.isdir(src) and os.path.realpath(src).startswith(os.path.realpath(sc['path']) + os.sep):
                    dest = os.path.join(walk_top(sc['path']), '.prullenbak', time.strftime('%Y%m%d-%H%M%S_') + home.replace('/', '_'))
                    base, n = dest, 1
                    while os.path.exists(dest):
                        n += 1
                        dest = f'{base}__{n}'
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.move(src, dest)
                        moved += 1
                    except OSError:
                        failed += 1
                        continue  # map niet verplaatst: leerling en bestanden laten staan
            with db() as c:
                c.execute(f"DELETE FROM models WHERE id IN ({','.join('?' * len(mids)) or 'NULL'})", mids)
            for i in mids:
                try:
                    os.remove(os.path.join(THUMBS, f'{i}.png'))
                except OSError:
                    pass
        else:
            with db() as c:
                c.execute('UPDATE models SET owner_id=NULL, shared=0 WHERE owner_id=?', (u['id'],))
        with db() as c:
            c.execute("UPDATE print_requests SET status='cancelled', updated=? WHERE requester_id=? AND status IN ('open','busy')", (time.time(), u['id']))
            c.execute('DELETE FROM users WHERE id=?', (u['id'],))
    OKAUTH.clear()
    hist('Leerlingen', f"{len(us) - failed} leerling(en) verwijderd, bestanden naar de prullenbak" if files == 'delete' else f"{len(us) - failed} leerling(en) verwijderd, bestanden bewaard")
    return jsonify(ok=True, removed=len(us) - failed, failed=failed)


@app.delete('/api/school/users/<int:uid>')
def school_users_del(uid):
    """Leerling deactiveren (de modellen en de map blijven bestaan). Definitief verwijderen: POST /api/school/users/remove."""
    _own_student(uid)
    with db() as c:
        c.execute('UPDATE users SET active=0, ver=ver+1 WHERE id=?', (uid,))
    OKAUTH.clear()
    return jsonify(ok=True)


@app.get('/api/users')
def users_get():
    with db() as c:
        rows = [dict(id=r['id'], username=r['username'], ms=bool(r['ms_oid']), email=r['email'] or '', role=r['role'], can_download=bool(r['can_download']), can_upload=bool(r['can_upload']), active=bool(r['active']),
                     created=r['created'], last_login=r['last_login'], me=bool(g.user and r['id'] == g.user['id']),
                     school_id=r['school_id'], display_name=r['display_name'] or '', klas=r['klas'] or '', home=r['home'] or '')
                for r in c.execute('SELECT * FROM users ORDER BY username COLLATE NOCASE')]
    return jsonify(rows)


@app.post('/api/users')
def users_add():
    j = request.json or {}
    name, pw = str(j.get('username') or '').strip(), str(j.get('password') or '')
    if not USERNAME_RE.match(name):
        return jsonify(error='Gebruikersnaam: 1 tot 40 tekens (letters, cijfers, . _ - @), geen spaties'), 400
    if not 8 <= len(pw) <= 200:
        return jsonify(error='Het wachtwoord moet minstens 8 tekens hebben'), 400
    email, err = parse_email(j.get('email'))
    if err:
        return jsonify(error=err), 400
    first = not AUTH_ON[0]  # het eerste account is altijd beheerder
    role = 'admin' if first else (j['role'] if j.get('role') in ROLES else 'student')
    try:
        with db() as c:
            if c.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone():
                return jsonify(error='Er bestaat al een gebruiker met die naam'), 409
            if email and c.execute('SELECT 1 FROM users WHERE email=? COLLATE NOCASE', (email,)).fetchone():
                return jsonify(error='Dit e-mailadres is al in gebruik'), 409
            sid = j.get('school_id') or None
            if role != 'admin' and not sid:
                return jsonify(error='Kies een school voor deze gebruiker'), 400
            if sid and not c.execute('SELECT 1 FROM schools WHERE id=?', (sid,)).fetchone():
                return jsonify(error='School niet gevonden'), 400
            if role == 'admin':
                sid = None
            home = make_home(c, sid, role, name) if sid else None
            uid = c.execute('INSERT INTO users(username, pw_hash, role, can_download, created, email, can_upload, school_id, display_name, klas, home) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (name, generate_password_hash(pw), role, 1 if j.get('can_download', True) else 0, time.time(), email, 1 if j.get('can_upload', role != 'admin') else 0,
                             sid, str(j.get('display_name') or '').strip()[:80], str(j.get('klas') or '').strip()[:20], home)).lastrowid
    except sqlite3.IntegrityError:
        return jsonify(error='Er bestaat al een gebruiker met die naam of dat e-mailadres'), 409
    refresh_auth()
    if first:  # de maker van het eerste account blijft ingelogd
        session.clear()
        session.permanent = True
        session['uid'], session['ver'] = uid, 0
    log.info('Account aangemaakt: %s (%s)', name, role)
    return jsonify(id=uid, auto_login=first)


@app.put('/api/users/<int:uid>')
def users_put(uid):
    j = request.json or {}
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not u:
            abort(404)
        role = j.get('role', u['role'])
        active = 1 if j.get('active', bool(u['active'])) else 0
        dl = 1 if j.get('can_download', bool(u['can_download'])) else 0
        up = 1 if j.get('can_upload', bool(u['can_upload'])) else 0
        email = u['email']
        if 'email' in j:
            email, err = parse_email(j['email'])
            if err:
                return jsonify(error=err), 400
            if email and c.execute('SELECT 1 FROM users WHERE email=? COLLATE NOCASE AND id<>?', (email, uid)).fetchone():
                return jsonify(error='Dit e-mailadres is al in gebruik'), 409
        if role not in ROLES:
            return jsonify(error='Onbekende rol'), 400
        others = c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)).fetchone()[0]
        if others == 0 and not (role == 'admin' and active):
            return jsonify(error='Er moet minstens één actieve beheerder blijven'), 400
        ver, pw_hash = u['ver'], u['pw_hash']
        if j.get('password'):
            if not 8 <= len(str(j['password'])) <= 200:
                return jsonify(error='Het wachtwoord moet minstens 8 tekens hebben'), 400
            pw_hash, ver = generate_password_hash(str(j['password'])), ver + 1
        if u['active'] and not active:
            ver += 1  # lopende sessies ongeldig maken
        sid = j.get('school_id', u['school_id']) or None
        if role == 'admin':
            sid = None
        elif not sid:
            return jsonify(error='Kies een school voor deze gebruiker'), 400
        home = u['home']
        if sid and (sid != u['school_id'] or role != u['role'] or not home):
            if u['school_id'] and (sid != u['school_id'] or role != u['role']):
                home = None  # andere school of rol: nieuwe thuismap (de oude map en modellen blijven op de schijf staan)
            home = home or make_home(c, sid, role, u['username'])
        elif not sid:
            home = None
        dn = str(j['display_name']).strip()[:80] if 'display_name' in j else u['display_name']
        kl = str(j['klas']).strip()[:20] if 'klas' in j else u['klas']
        c.execute('UPDATE users SET role=?, active=?, can_download=?, can_upload=?, pw_hash=?, ver=?, email=?, school_id=?, home=?, display_name=?, klas=? WHERE id=?', (role, active, dl, up, pw_hash, ver, email, sid, home, dn, kl, uid))
    OKAUTH.clear()
    if g.via == 'session' and g.user['id'] == uid and active:
        session['ver'] = ver  # de eigen sessie blijft geldig na het wijzigen van je eigen wachtwoord
    return jsonify(ok=True)


@app.delete('/api/users/<int:uid>')
def users_del(uid):
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not u:
            abort(404)
        others = c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)).fetchone()[0]
        if u['role'] == 'admin' and u['active'] and others == 0:
            return jsonify(error='Je kunt de laatste beheerder niet verwijderen. Gebruik "Alle accounts verwijderen" om het inloggen uit te zetten.'), 400
        c.execute('DELETE FROM users WHERE id=?', (uid,))
    refresh_auth()
    return jsonify(ok=True)


@app.post('/api/users/clear')
def users_clear():
    """Alle accounts verwijderen = inloggen uitzetten (iedereen heeft dan weer toegang)."""
    if not (request.json or {}).get('confirm'):
        return jsonify(error='Bevestiging ontbreekt'), 400
    with db() as c:
        c.execute('DELETE FROM users')
    refresh_auth()
    session.clear()
    return jsonify(ok=True)


# ---------------------------------------------------------------- API
def one(mid):
    with db() as c:
        r = c.execute('SELECT * FROM models WHERE id=?', (mid,)).fetchone()
    if not r:
        abort(404)
    if has_request_context() and g.get('user') and g.user['role'] != 'admin' and not can_see(g.user, r):
        abort(404)  # een model dat je niet mag zien bestaat voor jou niet
    return r


@app.get('/ping')
def ping():
    return 'ok'


@app.get('/')
def index():
    # stijl- en scriptbestanden krijgen hun wijzigingstijd mee, zodat de browser na een update niet met oude bestanden blijft werken
    try:
        html = open(os.path.join(app.static_folder, 'index.html'), encoding='utf-8').read()
        for f in ('style.css', 'app.js', 'i18n.js', 'i18n-en.js'):
            fp = os.path.join(app.static_folder, f)
            if os.path.exists(fp):
                html = html.replace(f'/static/{f}"', f'/static/{f}?v={int(os.path.getmtime(fp))}"')
        r = Response(html, mimetype='text/html')
        r.headers['Cache-Control'] = 'no-cache'
        return r
    except OSError:
        return send_from_directory(app.static_folder, 'index.html')


@app.get('/api/rev')
def rev():
    with db() as c:
        p = c.execute("SELECT COUNT(*) FROM models WHERE thumb_status='pending'").fetchone()[0]
        f = c.execute("SELECT COUNT(*) FROM models WHERE thumb_status='failed'").fetchone()[0]
        ign = ignored_keys(c)
        d = len(split_ignored(find_duplicates(c.execute('SELECT * FROM models WHERE hash IS NOT NULL').fetchall())[0], ign)[0]) if ign else c.execute("SELECT COUNT(*) FROM (SELECT hash FROM models WHERE hash IS NOT NULL AND hash<>'' GROUP BY hash HAVING COUNT(*) > 1)").fetchone()[0]
    u, ro, rp = g.get('user'), 0, 0
    if u and u['role'] != 'admin':  # leerlingen en medewerkers zien geen beheertellers
        p = f = d = 0
    if u and u.get('id'):
        with db() as c:
            if u['role'] == 'student':
                ro = c.execute("SELECT COUNT(*) FROM print_requests WHERE requester_id=? AND status='done' AND updated>?", (u['id'], time.time() - 7 * 86400)).fetchone()[0]
            else:
                w, a = ('', []) if u['role'] == 'admin' else (' AND school_id=?', [u.get('school_id')])
                ro = c.execute("SELECT COUNT(*) FROM print_requests WHERE status='open'" + w, a).fetchone()[0]
                rp = c.execute("SELECT COUNT(*) FROM reports r JOIN models m ON m.id=r.model_id WHERE r.status='open'" + w.replace('school_id', 'm.school_id'), a).fetchone()[0]
    ra = root_alerts()
    if u and u['role'] != 'admin':  # leerlingen en medewerkers zien alleen dat er iets mis is, niet de paden op de server
        ra = [dict(id=a['id'], kind=a['kind']) for a in ra]
    return jsonify(rev=REV, pending=p, failed=f, dups=d, requests_open=ro, reports_open=rp, auth=AUTH_ON[0], scan=dict(SCANP) if T['scan']['running'] and SCANP['phase'] else None, roots_alert=ra)


def find_duplicates(rows):
    """(exact, mesh): lijsten van groepen. exact = identieke inhoud (hash). mesh = zelfde aantal driehoeken en
    afmetingen maar niet bewezen identiek (bijv. dezelfde mesh als STL en als 3MF, of opnieuw geëxporteerd)."""
    by_hash, by_mesh = {}, {}
    for r in rows:
        if r['hash']:
            by_hash.setdefault(r['hash'], []).append(r)
        if r['tris'] and r['dx'] is not None:
            by_mesh.setdefault((r['tris'], round(r['dx'], 1), round(r['dy'], 1), round(r['dz'], 1)), []).append(r)
    exact = [g for g in by_hash.values() if len(g) > 1]
    mesh = [g for g in by_mesh.values() if len(g) > 1 and len({x['hash'] or 'id%d' % x['id'] for x in g}) > 1]
    return exact, mesh


def gkey(g):
    """Sleutel van een dubbelen-groep: de gesorteerde model-id's. Komt er een kopie bij (of verdwijnt er een), dan is het een andere groep en verschijnt hij weer."""
    return ','.join(str(i) for i in sorted(int(x['id']) for x in g))


def split_ignored(groups, ign):
    return [g for g in groups if gkey(g) not in ign], [g for g in groups if gkey(g) in ign]


def ignored_keys(c):
    return {r[0] for r in c.execute('SELECT key FROM dup_ignored')}


def dup_map(rows, ign=None):
    exact, mesh = find_duplicates(rows)
    if ign:
        exact, mesh = split_ignored(exact, ign)[0], split_ignored(mesh, ign)[0]
    out = {x['id']: 'mesh' for g in mesh for x in g}
    out.update({x['id']: 'exact' for g in exact for x in g})
    return out


def _info(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return None


_LIBC = dict(v=-1)
_LIB_LOCK = threading.Lock()


def _lib_base():
    """De volledige modellenlijst (zonder gastmaskering). Wordt onthouden tot er iets in de database verandert, zodat het bladeren door pagina's snel blijft."""
    with _LIB_LOCK:
        if _LIBC['v'] == DBW:
            return _LIBC['models'], _LIBC['categories']
        v = DBW
        with db() as c:
            roots = {r['id']: r['path'] for r in c.execute('SELECT * FROM roots')}
            rw = {r['id']: bool(r['allow_write']) for r in c.execute('SELECT * FROM roots')}
            pc = {r['model_id']: r for r in c.execute("SELECT model_id, SUM(result='ok') ok, SUM(result='failed') failed, MAX(ts) last FROM prints GROUP BY model_id")}
            cats = {}
            for r in c.execute('SELECT * FROM model_categories'):
                cats.setdefault(r['model_id'], []).append(r['category_id'])
            rows = c.execute('SELECT * FROM models').fetchall()
            us = {r['id']: r for r in c.execute('SELECT id, username, display_name, klas FROM users')}
            sch = {r['id']: r['name'] for r in c.execute('SELECT id, name FROM schools')}
            hid = [(r['root_id'], r['rel']) for r in c.execute('SELECT * FROM hidden_folders')]
            dups = dup_map(rows, ignored_keys(c))
            models = []
            for r in rows:
                try:
                    folder = os.path.relpath(os.path.dirname(r['path']), roots[r['root_id']])
                except (KeyError, ValueError):
                    folder = ''
                models.append(dict(id=r['id'], name=r['name'], display=r['display_name'] or '', ext=r['ext'], path=r['path'],
                                   folder='' if folder == '.' else folder, size=r['size'], added=r['added_at'],
                                   status=r['thumb_status'], error=r['thumb_error'], thumb_at=r['thumb_at'] or 0,
                                   dims=[r['dx'], r['dy'], r['dz']] if r['dx'] is not None else None, tris=r['tris'], info=_info(r['info']), dup=dups.get(r['id'], ''), favorite=bool(r['favorite']), printed=r['printed'] or '', notes=r['notes'] or '',
                                   source_url=r['source_url'] or '', thumb_custom=bool(r['thumb_custom']), can_rename=rw.get(r['root_id'], False) and not r['container'],
                                   container=os.path.basename(r['container']) if r['container'] else '', member=r['member'] or '',
                                   prints_ok=(pc[r['id']]['ok'] if r['id'] in pc else 0), prints_failed=(pc[r['id']]['failed'] if r['id'] in pc else 0),
                                   last_print=(pc[r['id']]['last'] if r['id'] in pc else None), pdims=_info(r['pdims']),
                                   cats=cats.get(r['id'], []), fhidden=_hid_match(hid, r['root_id'], '' if folder == '.' else folder), owner_id=r['owner_id'], school_id=r['school_id'], shared=bool(r['shared']), hidden=bool(r['hidden']),
                                   school=sch.get(r['school_id'], ''), owner_full=(us[r['owner_id']]['display_name'] or us[r['owner_id']]['username']) if r['owner_id'] in us else '',
                                   owner_klas=(us[r['owner_id']]['klas'] or '') if r['owner_id'] in us else ''))
            categories = [dict(r) for r in c.execute(
                'SELECT c.id, c.name, COUNT(mc.model_id) AS count FROM categories c '
                'LEFT JOIN model_categories mc ON mc.category_id=c.id GROUP BY c.id ORDER BY c.name COLLATE NOCASE')]
        _LIBC.update(v=v, models=models, categories=categories)
    return models, categories


@app.get('/api/library')
def library():
    models, categories = _lib_base()
    u = g.get('user')
    if u and u['role'] in ('admin', 'staff'):  # filter op school (beheerder) en op leerling: alle bestanden van één leerling
        sc, ow = request.args.get('school', type=int), request.args.get('owner', type=int)
        if sc and u['role'] == 'admin':
            models = [m for m in models if m['school_id'] == sc]
        if ow:
            models = [m for m in models if m['owner_id'] == ow]
    viewer = bool(u) and u['role'] != 'admin'
    if viewer:  # leerlingen en medewerkers zien alleen wat bij hen hoort en geen privé-gegevens: notities, logboek, bestandspaden op de schijf (op een kopie: de onthouden lijst blijft ongemoeid)
        models = [m for m in models if can_see(u, m)]
        cnt = collections.Counter(c for m in models for c in m['cats'])
        categories = [dict(c, count=cnt.get(c['id'], 0)) for c in categories]
        staff_view = u['role'] == 'staff'

        def owner_label(m):  # medewerkers van dezelfde school zien de volledige naam; leerlingen de voornaam (eigen school) of alleen de schoolnaam (andere school)
            if not m['owner_id']:
                return m['school'] or ''
            if staff_view and m['school_id'] == u.get('school_id'):
                return m['owner_full'] + (f" ({m['owner_klas']})" if m['owner_klas'] else '')
            if m['school_id'] == u.get('school_id'):  # eigen school: alleen de voornaam
                return m['owner_full'].split(' ')[0] if m['owner_full'] else ''
            return m['school'] or ''  # andere school: alleen de schoolnaam, geen naam
        models = [dict(m, path=f"{m['name']}.{m['ext']}",
                       notes='', error=None, can_rename=False, prints_ok=0, prints_failed=0, last_print=None, favorite=False, printed='', dup='',
                       owner=owner_label(m), mine=m['owner_id'] == u['id'], manage=can_manage(u, m), owner_id=None, owner_full='', owner_klas='', folder=m['folder'] if m['school_id'] is None else '') for m in models]
    else:
        models = [dict(m, owner=m['owner_full'] + (f" ({m['owner_klas']})" if m['owner_klas'] else '') if m['owner_id'] else m['school'], mine=False, manage=True) for m in models]
    out = dict(categories=categories, big_mb=int(CFG['big_mb']), recent_days=int(CFG['recent_days']), spoolman=bool(CFG['spoolman_url']) and not viewer, bambuddy=bool(CFG['bambuddy_url'] and CFG['bambuddy_key']) and not viewer,
               local=is_local(), slicer=dict(zip(('name', 'scheme'), SLICERS.get(CFG['slicer'], SLICERS['bambustudio']))))
    if 'page' not in request.args:  # zonder paginaparameters: de hele lijst (API-gebruikers, tests)
        return jsonify(models=models, **out)
    # Met paginaparameters filtert, sorteert en pagineert de server; de browser krijgt alleen de zichtbare pagina.
    with db() as c:
        beds = {r['id']: r for r in c.execute('SELECT * FROM printers')}
    a = request.args
    sel = lib_filter(models, categories, a.get('q', ''), a.get('cat', 'all'), a.get('ext', 'all'), a.get('flt', 'all'), a.get('sort', 'name'), out['recent_days'], out['big_mb'], beds)
    size = max(0, min(int(a.get('size', 100) or 0), 100000)) if str(a.get('size', '100')).lstrip('-').isdigit() else 100
    pages = max(1, -(-len(sel) // size)) if size else 1
    page = max(0, min(int(a.get('page', 0)) if str(a.get('page', '0')).isdigit() else 0, pages - 1))
    shown = sel[page * size:(page + 1) * size] if size else sel
    want = int(a['with']) if str(a.get('with', '')).isdigit() else None  # model dat in het venster openstaat, ook als het niet (meer) in het filter past
    return jsonify(models=shown, total=len(sel), all=len(models), page=page, pages=pages, size=size, ids=[m['id'] for m in sel],
                   exts=sorted({m['ext'] for m in models}), open=next((m for m in models if m['id'] == want), None) if want else None, **out)


_LIB_ALIAS = dict(kleuren='kleuren', colors='kleuren', colours='kleuren', ext='ext', cat='cat', categorie='cat', map='map', folder='map', naam='naam', name='naam', ontwerper='ontwerper', designer='ontwerper',
                  notitie='notitie', notities='notitie', note='notitie', bron='bron', source='bron')


def _parse_q(q):
    """'rack ext:3mf cat:"10 inch"' -> [(veld, tekst)]; onbekende prefix telt als gewone tekst (zelfde regels als de zoekbalk)."""
    out = []
    for t in re.finditer(r'(?:(\w+):)?(?:"([^"]*)"|(\S+))', (q or '').lower(), re.A):
        v = t.group(2) if t.group(2) is not None else t.group(3)
        k = _LIB_ALIAS.get(t.group(1))
        out.append((k, v) if k else ('all', (t.group(1) + ':' if t.group(1) else '') + v))
    return out


def _fits_dims(d, p):
    return ((d[0] <= p['bed_x'] + .01 and d[1] <= p['bed_y'] + .01) or (d[0] <= p['bed_y'] + .01 and d[1] <= p['bed_x'] + .01)) and d[2] <= p['bed_z'] + .01


def _fits(m, p):  # True/False, of None als de afmetingen (nog) onbekend zijn; meerdere platen: elke plaat moet passen
    if len((m['info'] or {}).get('plates') or []) > 1:
        pd = m.get('pdims')
        return all(_fits_dims(x['dims'], p) for x in pd) if pd else None
    return _fits_dims(m['dims'], p) if m['dims'] and None not in m['dims'] else None


def _hay(m, catnames):
    i = m['info'] or {}
    s = lambda x: str(x if x is not None else '').lower()
    lab = m['display'] or m['name']
    f = dict(naam=s(f"{lab} {m['name']}.{m['ext']}"), ext=s(m['ext']), map=s(m['folder']), ontwerper=s(f"{i.get('designer') or ''} {i.get('title') or ''}"),
             cat=' '.join(catnames.get(c, '') for c in m['cats']).lower(), notitie=s(m['notes']), bron=s(m['source_url']))
    f['kleuren'] = str(i.get('color_count') or '')
    f['all'] = ' '.join(v for k, v in f.items() if k != 'kleuren') + ' ' + s(' '.join(str(i.get(k) or '') for k in ('application', 'printer', 'filament', 'description')))
    return f


def _sortkey(m):
    t = unicodedata.normalize('NFKD', (m['display'] or m['name'])).casefold()
    return ''.join(ch for ch in t if not unicodedata.combining(ch))


def lib_filter(models, categories, q, cat, ext, flt, sort, recent_days, big_mb, beds):
    """Dezelfde filters als de bibliotheekweergave: zoeken (met prefixen), categorie, formaat, 'Alle modellen'-lijst en sortering."""
    toks = _parse_q(q)
    names = {c['id']: c['name'] for c in categories}
    now = time.time()
    fit = beds.get(int(flt[4:])) if flt.startswith('fit:') and flt[4:].isdigit() else None
    tests = {'nopreview': lambda m: m['status'] != 'ok', 'recent': lambda m: m['added'] > now - recent_days * 86400, 'dup': lambda m: bool(m['dup']),
             'fav': lambda m: m['favorite'], 'toprint': lambda m: m['printed'] == 'toprint', 'printed': lambda m: m['printed'] == 'printed',
             'failedprint': lambda m: m['prints_failed'] > 0, 'multicolor': lambda m: (m['info'] or {}).get('color_count', 0) >= 2, 'mine': lambda m: bool(m.get('mine')), 'big': lambda m: m['size'] > big_mb * 2 ** 20}
    ft = None if flt == 'all' else (lambda m: fit is not None and _fits(m, fit) is True) if flt.startswith('fit:') else tests.get(flt, tests['big'])
    cid = int(cat) if cat.lstrip('-').isdigit() else None
    out = []
    for m in models:
        if cat == 'none':
            if m['cats']:
                continue
        elif cid is not None and cid not in m['cats']:
            continue
        if ext != 'all' and m['ext'] != ext:
            continue
        if ft and not ft(m):
            continue
        if toks:
            h = _hay(m, names)
            if not all(v in h[k] for k, v in toks):
                continue
        out.append(m)
    if sort == 'added':
        out.sort(key=lambda m: -m['added'])
    elif sort == 'size':
        out.sort(key=lambda m: -m['size'])
    else:
        out.sort(key=_sortkey)
    return out


@app.get('/api/file/<int:mid>')
def model_file(mid):
    """Download het originele bestand. Alleen het model zelf: nooit een pad uit de URL."""
    r = one(mid)
    if g.get('user') and g.user['role'] != 'admin':
        hist('Download', f"{g.user['username']} downloadde {r['name']}.{r['ext']}", mid)
    return send_model(r, True)


def send_model(r, attachment):
    """Het modelbestand zelf versturen (bij een onderdeel van een zip: alleen dat onderdeel, uitgepakt in het geheugen)."""
    if r['container']:
        try:
            if r['size'] > MAX_MB * 2 ** 20:
                abort(413)
            with zipfile.ZipFile(r['container']) as z:
                data = z.read(r['member'])
        except (OSError, zipfile.BadZipFile, KeyError):
            abort(404)
        return send_file(io.BytesIO(data), as_attachment=attachment, download_name=posixpath.basename(r['member']))
    if not os.path.isfile(r['path']):
        abort(404)
    return send_file(r['path'], as_attachment=attachment, conditional=True)


@app.post('/api/models/<int:mid>/link')
def model_link(mid):
    """Tijdelijke, ondertekende downloadlink (10 min) zodat een slicer het bestand zelf kan ophalen, zonder wachtwoord in de link."""
    r = one(mid)
    if g.get('user') and g.user['role'] != 'admin':
        hist('Download', f"{g.user['username']} opende {r['name']}.{r['ext']} in de slicer", mid)
    name = urllib.parse.quote(posixpath.basename(r['member']) if r['container'] else os.path.basename(r['path']))
    nm, scheme = SLICERS.get(CFG['slicer'], SLICERS['bambustudio'])
    return jsonify(path=f'/dl/{make_token(mid)}/{name}', slicer=nm, scheme=scheme, expires=LINK_TTL)


@app.get('/dl/<token>/<path:name>')
def model_dl(token, name):
    mid = check_token(token)
    if mid is None:
        return Response('Deze link is ongeldig of verlopen. Maak in de bibliotheek een nieuwe aan.', 403)
    return send_model(one(mid), False)


@app.post('/api/models/<int:mid>/open')
def model_open(mid):
    """Openen met het standaardprogramma van het besturingssysteem; alleen als de gebruiker op dezelfde computer zit als de app."""
    if not is_local():
        return jsonify(error='Openen met het standaardprogramma kan alleen als de app op dezelfde computer draait als je browser.'), 403
    r = one(mid)
    p = r['path']
    if r['container']:  # onderdeel van een zip: een gewone kopie klaarzetten
        d = os.path.join(CONFIG, 'open')
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{mid}_{posixpath.basename(r['member'])}")
        try:
            with zipfile.ZipFile(r['container']) as z, z.open(r['member']) as src, open(p, 'wb') as dst:
                shutil.copyfileobj(src, dst)
        except (OSError, zipfile.BadZipFile, KeyError) as e:
            return jsonify(error=f'Uitpakken mislukt: {e}'), 400
    if not os.path.isfile(p):
        return jsonify(error='Bestand niet gevonden'), 404
    try:
        open_file(p)
    except OSError as e:
        return jsonify(error=f'Openen mislukt: {e.strerror or e}'), 500
    return jsonify(ok=True)


@app.get('/api/mesh/<int:mid>.stl')
def mesh(mid):
    r = one(mid)
    try:
        with materialize(r) as src:
            data = heavy('mesh_stl', src, r['ext'], plate=request.args.get('plate', type=int), view=True)
    except Exception as e:
        return Response(f'Kan model niet laden: {why(e) if isinstance(e, MemoryError) else e}', 415)
    return Response(data, mimetype='model/stl')


@app.get('/api/thumb/<int:mid>.png')
def thumb_get(mid):
    one(mid)  # zelfde zichtbaarheidsregels als het model zelf
    p = os.path.join(THUMBS, f'{mid}.png')
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype='image/png', max_age=86400)


PRINTED = ('', 'toprint', 'printed')


@app.post('/api/models/<int:mid>')
def model_update(mid):
    j, r = request.json or {}, one(mid)
    if 'source_url' in j:
        u = (j['source_url'] or '').strip()
        if u and not u.lower().startswith(('http://', 'https://')):
            return jsonify(error='Bron moet een link zijn die met http:// of https:// begint'), 400
        j['source_url'] = u[:500]
    if 'printed' in j and j['printed'] not in PRINTED:
        return jsonify(error='Ongeldige printstatus'), 400
    with db() as c:
        if 'filename' in j:
            if r['container']:
                return jsonify(error='Dit model zit in een zip: alleen de weergavenaam kan worden gewijzigd.'), 400
            root = c.execute('SELECT allow_write FROM roots WHERE id=?', (r['root_id'],)).fetchone()
            if not root or not root['allow_write']:
                return jsonify(error='Hernoemen staat uit voor deze root folder. Zet het aan onder Instellingen → Mediabeheer.'), 403
            stem = (j['filename'] or '').strip()
            if not stem or stem.endswith('.') or any(ch in stem for ch in '<>:"/\\|?*'):
                return jsonify(error='Ongeldige bestandsnaam (leeg of bevat < > : " / \\ | ? *)'), 400
            old = r['path']
            new = os.path.join(os.path.dirname(old), stem + os.path.splitext(old)[1])
            if new != old:
                if os.path.exists(new) and not os.path.samefile(new, old):
                    return jsonify(error='Er bestaat al een bestand met die naam'), 409
                try:
                    os.rename(old, new)
                except OSError as e:
                    return jsonify(error=f'Hernoemen mislukt: {e.strerror or e}'), 400
                c.execute('UPDATE models SET path=?, name=? WHERE id=?', (new, stem, mid))
                log.info('Hernoemd: %s -> %s', old, new)
        if 'display' in j:
            c.execute('UPDATE models SET display_name=? WHERE id=?', ((j['display'] or '').strip() or None, mid))
        if 'notes' in j:
            c.execute('UPDATE models SET notes=? WHERE id=?', ((j['notes'] or '').strip()[:5000] or None, mid))
        if 'favorite' in j:
            c.execute('UPDATE models SET favorite=? WHERE id=?', (1 if j['favorite'] else 0, mid))
        if 'printed' in j:
            c.execute('UPDATE models SET printed=? WHERE id=?', (j['printed'], mid))
        if 'source_url' in j:
            c.execute('UPDATE models SET source_url=? WHERE id=?', (j['source_url'] or None, mid))
    bump()
    return jsonify(ok=True)


@app.post('/api/models/bulk')
def models_bulk():
    j = request.json or {}
    ids = [(int(i),) for i in j.get('model_ids', [])]
    if 'printed' in j and j['printed'] not in PRINTED:
        return jsonify(error='Ongeldige printstatus'), 400
    with db() as c:
        if 'favorite' in j:
            c.executemany('UPDATE models SET favorite=%d WHERE id=?' % (1 if j['favorite'] else 0), ids)
        if 'printed' in j:
            c.executemany('UPDATE models SET printed=? WHERE id=?', [(j['printed'], i[0]) for i in ids])
    bump()
    return jsonify(ok=True)


@app.post('/api/models/<int:mid>/thumb')
def model_thumb(mid):
    """Eigen thumbnail (bijv. een opname uit de 3D-viewer). Blijft behouden tot 'Thumbnail opnieuw' of een gewijzigd bestand."""
    r = one(mid)
    try:
        img = Image.open(io.BytesIO(base64.b64decode((request.json or {})['data'].split(',', 1)[1])))
        img.load()
    except Exception:
        return jsonify(error='Ongeldige afbeelding'), 400
    render.save_png(render.fit_square(img, int(CFG['thumb_size'])), os.path.join(THUMBS, f'{mid}.png'), thumb_tag(r))
    with db() as c:
        c.execute("UPDATE models SET thumb_status='ok', thumb_error=NULL, thumb_at=?, thumb_custom=1 WHERE id=?", (time.time(), mid))
    bump()
    return jsonify(ok=True)


@app.post('/api/models/<int:mid>/regen')
def model_regen(mid):
    r = one(mid)
    with db() as c:
        c.execute('UPDATE models SET thumb_status=?, thumb_custom=0, thumb_error=NULL WHERE id=?', ('pending' if r['ext'] in render.CAN_THUMB else 'unsupported', mid))
    bump()
    return jsonify(ok=True)


@app.get('/api/duplicates')
def duplicates():
    with db() as c:
        rows = c.execute('SELECT * FROM models').fetchall()
        rw = {r['id']: bool(r['allow_write']) for r in c.execute('SELECT * FROM roots')}
        waiting = c.execute("SELECT COUNT(*) FROM models WHERE hash IS NULL AND size IN (SELECT size FROM models GROUP BY size HAVING COUNT(*) > 1)").fetchone()[0]
    exact, mesh = find_duplicates(rows)
    with db() as c:
        ign = ignored_keys(c)
    (exact, ig_exact), (mesh, ig_mesh) = split_ignored(exact, ign), split_ignored(mesh, ign)
    item = lambda r: dict(id=r['id'], name=r['name'], ext=r['ext'], path=r['path'], size=r['size'], added=r['added_at'],
                          status=r['thumb_status'], thumb_at=r['thumb_at'] or 0, can_write=rw.get(r['root_id'], False) and not r['container'])
    grp = lambda g: [item(r) for r in sorted(g, key=lambda r: r['added_at'] or 0)]  # oudste eerst
    exact.sort(key=lambda g: -(len(g) - 1) * g[0]['size'])
    mesh.sort(key=lambda g: -g[0]['size'])
    return jsonify(exact=[grp(g) for g in exact], mesh=[grp(g) for g in mesh], ignored=[grp(g) for g in sorted(ig_exact + ig_mesh, key=lambda g: -g[0]['size'])],
                   wasted=sum((len(g) - 1) * g[0]['size'] for g in exact), waiting=waiting)


def _group_of(ids):
    """De dubbelen-groep die precies bij deze model-id's hoort, of None."""
    with db() as c:
        rows = c.execute('SELECT * FROM models').fetchall()
    want = sorted(int(i) for i in ids)
    return next((g for g in sum(find_duplicates(rows), []) if sorted(int(x['id']) for x in g) == want), None)


@app.post('/api/duplicates/ignore')
def dup_ignore():
    j = request.json or {}
    try:
        ids = [int(i) for i in j.get('ids') or []]
    except (TypeError, ValueError):
        return jsonify(error='Ongeldige groep'), 400
    g = _group_of(ids) if len(ids) > 1 else None
    if not g:
        return jsonify(error='Deze groep bestaat niet (meer); ververs de pagina.'), 409
    with db() as c:
        if j.get('ignore', True):
            c.execute('INSERT OR REPLACE INTO dup_ignored(key, ts) VALUES(?, ?)', (gkey(g), time.time()))
        else:
            c.execute('DELETE FROM dup_ignored WHERE key=?', (gkey(g),))
    bump()
    return jsonify(ok=True)


def _trash(mid, any_file=False):
    """Verplaatst een bestand naar <root>/.prullenbak (niet definitief wissen). Standaard alleen een dubbel bestand, en alleen als er
    nog minstens één ander bestand in dezelfde dubbelen-groep zit, zodat nooit de laatste kopie verdwijnt. Met any_file (vanuit de
    bibliotheek, na bevestiging door de gebruiker) mag elk bestand, maar nog steeds alleen in een root folder waar schrijven aan staat."""
    with db() as c:
        r = c.execute('SELECT * FROM models WHERE id=?', (mid,)).fetchone()
    if not r:
        return dict(error='Model niet gevonden'), 404
    if r['container']:
        return dict(error='Dit model zit in een zip en kan niet apart worden verplaatst.'), 409
    with db() as c:
        rows = [] if any_file else c.execute('SELECT * FROM models').fetchall()
        root = c.execute('SELECT path, allow_write FROM roots WHERE id=?', (r['root_id'],)).fetchone()
    twins = []
    if not any_file:
        exact, mesh = find_duplicates(rows)
        twins = [x for g in exact + mesh if mid in {y['id'] for y in g} for x in g if x['id'] != mid]
    if (not twins and not any_file) or not root:
        return dict(error='Dit is geen dubbel bestand (meer); er is niets verplaatst'), 409
    if not root['allow_write']:
        return dict(error='Verplaatsen staat uit voor deze root folder. Zet het aan onder Instellingen → Mediabeheer.'), 403
    d = os.path.join(walk_top(root['path']), '.prullenbak')
    dest = os.path.join(d, time.strftime('%Y%m%d-%H%M%S_') + os.path.basename(r['path']))
    n = 1
    while os.path.exists(dest):  # gelijke naam in dezelfde seconde (kopieën met dezelfde naam uit verschillende mappen): nooit overschrijven
        n += 1
        dest = os.path.join(d, time.strftime('%Y%m%d-%H%M%S_') + f'{n}_' + os.path.basename(r['path']))
    try:
        os.makedirs(d, exist_ok=True)
        shutil.move(r['path'], dest)
    except OSError as e:
        return dict(error=f'Verplaatsen mislukt: {e.strerror or e}'), 400
    with db() as c:
        c.execute('DELETE FROM models WHERE id=?', (mid,))
    try:
        os.remove(os.path.join(THUMBS, f'{mid}.png'))
    except OSError:
        pass
    hist('Prullenbak', f"{os.path.basename(r['path'])} verplaatst naar .prullenbak (dubbel van {twins[0]['name']}.{twins[0]['ext']})" if twins
         else f"{os.path.basename(r['path'])} naar .prullenbak verplaatst (via de bibliotheek)")
    return dict(ok=True, dest=dest), 200


@app.post('/api/models/<int:mid>/trash')
def model_trash(mid):
    out, code = _trash(mid)
    return jsonify(out), code


@app.post('/api/models/trash')
def models_trash():
    """Meerdere bestanden in één keer naar de prullenbak. Standaard (duplicatenweergave) wordt elk bestand apart gecontroleerd tegen
    de actuele groepen: van een groep blijft altijd minstens één kopie staan, ook als je ze allemaal selecteert. Met "any": true
    (bibliotheek) mag elk bestand, behalve in een zip of in een root folder waar schrijven uit staat."""
    j = request.json or {}
    try:
        ids = list(dict.fromkeys(int(i) for i in j.get('ids') or []))
    except (TypeError, ValueError):
        return jsonify(error='Ongeldige selectie'), 400
    done, failed = 0, []
    for i in ids[:2000]:
        out, code = _trash(i, any_file=bool(j.get('any')))
        if code == 200:
            done += 1
        else:
            failed.append(dict(id=i, error=out['error']))
    return jsonify(done=done, failed=failed)


@app.post('/api/categories')
def cat_add():
    name = ((request.json or {}).get('name') or '').strip()
    if not name:
        return jsonify(error='Naam ontbreekt'), 400
    with db() as c:
        c.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)', (name,))
        cid = c.execute('SELECT id FROM categories WHERE name=?', (name,)).fetchone()['id']
    bump()
    return jsonify(id=cid)


@app.put('/api/categories/<int:cid>')
def cat_rename(cid):
    name = ((request.json or {}).get('name') or '').strip()
    if not name:
        return jsonify(error='Naam ontbreekt'), 400
    try:
        with db() as c:
            c.execute('UPDATE categories SET name=? WHERE id=?', (name, cid))
    except sqlite3.IntegrityError:
        return jsonify(error='Er bestaat al een categorie met die naam'), 409
    bump()
    return jsonify(ok=True)


@app.delete('/api/categories/<int:cid>')
def cat_del(cid):
    with db() as c:
        c.execute('DELETE FROM categories WHERE id=?', (cid,))
    bump()
    return jsonify(ok=True)


@app.post('/api/assign')
def assign():
    j = request.json
    with db() as c:
        for mid in j['model_ids']:
            if j['action'] == 'add':
                c.execute('INSERT OR IGNORE INTO model_categories VALUES(?,?)', (mid, j['category_id']))
            else:
                c.execute('DELETE FROM model_categories WHERE model_id=? AND category_id=?', (mid, j['category_id']))
    bump()
    return jsonify(ok=True)


# ---------------------------------------------------------------- automatisch indelen: mappen en regels
RULE_FIELDS = ('path', 'name', 'ext', 'folder')  # folder: de map op het hoogste niveau is gelijk aan de tekst (ook submappen)


def _model_keys(c, ids=None):
    """id -> (pad, naam, extensie), allemaal in kleine letters. Het pad is relatief aan de root folder, met / als scheidingsteken."""
    roots = {r['id']: r['path'] for r in c.execute('SELECT id, path FROM roots')}
    q = 'SELECT id, root_id, path, name, ext, container, member FROM models'
    if ids is None:
        rows = c.execute(q).fetchall()
    else:
        ids, rows = list(ids), []
        for i in range(0, len(ids), 500):  # SQLite heeft een maximum aantal variabelen per query
            part = ids[i:i + 500]
            rows += c.execute(q + ' WHERE id IN (%s)' % ','.join('?' * len(part)), part).fetchall()
    out = {}
    for r in rows:
        try:
            rel = os.path.relpath(r['container'] or r['path'], roots[r['root_id']]).replace(os.sep, '/')
        except (KeyError, ValueError):
            rel = (r['container'] or r['path']).replace(os.sep, '/')
        top = rel.split('/')[0] if '/' in rel else ''  # hoogste map; bij een zip telt de map waarin de zip staat
        if r['container'] and r['member']:
            rel += '/' + r['member']
        out[r['id']] = (rel.lower(), (r['name'] or '').lower(), (r['ext'] or '').lower(), top.lower(), top)
    return out


def _rule_hits(rule, keys):
    v = (rule['value'] or '').strip().lower().lstrip('.') if rule['field'] == 'ext' else (rule['value'] or '').strip().lower()
    if not v:
        return []
    i = {'path': 0, 'name': 1, 'ext': 2, 'folder': 3}[rule['field']]
    return [mid for mid, k in keys.items() if (k[i] == v if rule['field'] in ('ext', 'folder') else v in k[i])]


def apply_rules(ids=None, rule_id=None):
    """Zet de categorie van elke regel bij de modellen die erbij passen (ids=None: alle modellen). Haalt nooit iets weg. Geeft het aantal nieuwe koppelingen."""
    with db() as c:
        rules = c.execute('SELECT * FROM rules' + (' WHERE id=?' if rule_id else ''), (rule_id,) if rule_id else ()).fetchall()
        if not rules:
            return 0
        keys = _model_keys(c, ids)
        n = 0
        for rl in rules:
            for mid in _rule_hits(rl, keys):
                n += c.execute('INSERT OR IGNORE INTO model_categories VALUES(?,?)', (mid, rl['category_id'])).rowcount
    if n:
        bump()
    return n


def migrate_folder_rules():
    """Eenmalig: mappen die met "Categorieën uit mappen" waren ingedeeld (categorie met de mapnaam, minstens de helft van de modellen erin)
    krijgen alsnog een regel, zodat nieuwe bestanden in die map dezelfde categorie krijgen. Er wordt niets aan bestaande modellen veranderd."""
    if CFG.get('folder_rules_migrated') == '1':
        return 0
    n = 0
    with db() as c:
        keys = _model_keys(c)
        cats = {r['name'].lower(): r['id'] for r in c.execute('SELECT id, name FROM categories')}
        have = {(r['model_id'], r['category_id']) for r in c.execute('SELECT * FROM model_categories')}
        by = {}
        for mid, k in keys.items():
            if k[3] and not k[3].startswith('.'):
                by.setdefault(k[4], []).append(mid)
        for f, ids in by.items():
            cid = cats.get(f.lower())
            if cid and sum((m, cid) in have for m in ids) * 2 >= len(ids) \
                    and not c.execute('SELECT 1 FROM rules WHERE field=? AND value=? COLLATE NOCASE AND category_id=?', ('folder', f, cid)).fetchone():
                c.execute('INSERT INTO rules(field,value,category_id,created) VALUES(?,?,?,?)', ('folder', f, cid, time.time()))
                n += 1
    put('folder_rules_migrated', '1')
    if n:
        log.info('%d map(pen) die al waren ingedeeld hebben nu een regel: nieuwe bestanden krijgen dezelfde categorie', n)
    return n


def _top_folder(m):
    return m['folder'].replace(os.sep, '/').split('/')[0] if m['folder'] else ''


@app.get('/api/folders')
def folders_list():
    """Mappen op het hoogste niveau van de root folders, met het aantal modellen en of er al een categorie met die naam is."""
    models, categories = _lib_base()
    by, loose = {}, 0
    cat_by_name = {c['name'].lower(): c['id'] for c in categories}
    for m in models:
        f = _top_folder(m)
        if not f:
            loose += 1
        elif not f.startswith('.'):
            e = by.setdefault(f, dict(name=f, count=0, done=0))
            e['count'] += 1
            cid = cat_by_name.get(f.lower())
            if cid and cid in m['cats']:
                e['done'] += 1
    items = sorted(by.values(), key=lambda x: (-x['count'], x['name'].lower()))
    for e in items:
        e['category_id'] = cat_by_name.get(e['name'].lower())
    return jsonify(folders=items, loose=loose, total=len(models))


@app.post('/api/folders/categorize')
def folders_categorize():
    """{items: [{folder, category}]}: maakt de categorie aan (als die nog niet bestaat) en zet alle modellen uit die map erin. Haalt nooit iets weg."""
    items = (request.json or {}).get('items')
    if not isinstance(items, list) or not items or len(items) > 5000:
        return jsonify(error='Kies minstens één map'), 400
    models, _ = _lib_base()
    ids_by = {}
    for m in models:
        ids_by.setdefault(_top_folder(m), []).append(m['id'])
    created = assigned = 0
    with db() as c:
        for it in items:
            f, name = str(it.get('folder') or ''), str(it.get('category') or '').strip()
            if not f or f not in ids_by:
                continue
            if not name or len(name) > 100:
                return jsonify(error=f'Ongeldige categorienaam voor map "{f}"'), 400
            row = c.execute('SELECT id FROM categories WHERE name=?', (name,)).fetchone()
            if row:
                cid = row['id']
            else:
                cid = c.execute('INSERT INTO categories(name) VALUES(?)', (name,)).lastrowid
                created += 1
            assigned += sum(c.execute('INSERT OR IGNORE INTO model_categories VALUES(?,?)', (mid, cid)).rowcount for mid in ids_by[f])
            if not c.execute('SELECT 1 FROM rules WHERE field=? AND value=? COLLATE NOCASE AND category_id=?', ('folder', f, cid)).fetchone():
                c.execute('INSERT INTO rules(field,value,category_id,created) VALUES(?,?,?,?)', ('folder', f, cid, time.time()))  # onthoud de map: nieuwe bestanden erin krijgen dezelfde categorie
    hist('Categorie', f'{assigned} modellen ingedeeld vanuit {len(items)} map(pen); {created} nieuwe categorie(ën)')
    return jsonify(created=created, assigned=assigned)


@app.get('/api/rules')
def rules_list():
    with db() as c:
        rows = c.execute('SELECT r.*, c.name AS category FROM rules r JOIN categories c ON c.id=r.category_id ORDER BY r.id').fetchall()
        keys = _model_keys(c) if rows else {}
        have = {(r['model_id'], r['category_id']) for r in c.execute('SELECT * FROM model_categories')} if rows else set()
    out = []
    for r in rows:
        hits = _rule_hits(r, keys)
        out.append(dict(id=r['id'], field=r['field'], value=r['value'], category_id=r['category_id'], category=r['category'], matches=len(hits),
                        todo=sum(1 for m in hits if (m, r['category_id']) not in have)))
    return jsonify(out)


@app.post('/api/rules')
def rules_add():
    j = request.json or {}
    field, value = j.get('field'), str(j.get('value') or '').strip()
    if field not in RULE_FIELDS:
        return jsonify(error='Ongeldig veld voor de regel'), 400
    if not value or len(value) > 200:
        return jsonify(error='Vul een tekst in voor de regel (maximaal 200 tekens)'), 400
    with db() as c:
        if not c.execute('SELECT 1 FROM categories WHERE id=?', (j.get('category_id'),)).fetchone():
            return jsonify(error='Kies een categorie'), 400
        ex = c.execute('SELECT id FROM rules WHERE field=? AND value=? COLLATE NOCASE AND category_id=?', (field, value, j['category_id'])).fetchone()
        if ex:
            return jsonify(id=ex['id'], existing=True)
        rid = c.execute('INSERT INTO rules(field,value,category_id,created) VALUES(?,?,?,?)', (field, value, j['category_id'], time.time())).lastrowid
    bump()
    return jsonify(id=rid)


@app.delete('/api/rules/<int:rid>')
def rules_delete(rid):
    with db() as c:
        c.execute('DELETE FROM rules WHERE id=?', (rid,))
    bump()
    return jsonify(ok=True)


@app.post('/api/rules/apply')
def rules_apply():
    rid = (request.json or {}).get('id')
    n = apply_rules(rule_id=int(rid) if rid else None)
    if n:
        hist('Categorie', f'Regels toegepast: {n} koppeling(en) gezet')
    return jsonify(assigned=n)


def roots_info():
    out = []
    with db() as c:
        counts = {r['root_id']: r['n'] for r in c.execute('SELECT root_id, COUNT(*) n FROM models GROUP BY root_id')}
        for r in c.execute('SELECT * FROM roots ORDER BY path'):
            ok, free, total = os.path.isdir(r['path']), None, None
            if ok:
                try:
                    u = shutil.disk_usage(r['path'])
                    free, total = u.free, u.total
                except OSError:
                    pass
            out.append(dict(id=r['id'], path=r['path'], watch=bool(r['watch']), allow_write=bool(r['allow_write']), ok=ok, free=free, total=total,
                            writable=ok and os.access(r['path'], os.W_OK), count=counts.get(r['id'], 0), live=r['id'] in OBS,
                            alert=(ROOT_ALERT.get(r['id']) or {}).get('kind')))
    return out


@app.get('/api/roots')
def roots_get():
    return jsonify(roots_info())


@app.post('/api/roots')
def roots_add():
    raw = clean_path((request.json or {}).get('path'))
    if not raw:
        return jsonify(error='Geen pad opgegeven'), 400
    if os.name == 'nt' and unc_server_only(raw):
        return jsonify(error='Geef een volledig netwerkpad op: server én share, bijvoorbeeld \\\\nas\\modellen'), 400
    p = os.path.normpath(raw)
    if not os.path.isdir(p):
        return jsonify(error='Map niet gevonden. Controleer het pad en of dit Windows-account toegang heeft (bij een netwerkpad: server én share, bijvoorbeeld \\\\nas\\modellen).'
                       if os.name == 'nt' else 'Map bestaat niet (is hij gemount in de container/LXC?)'), 400
    if os.name != 'nt' and p == '/':
        return jsonify(error='Dit is de hoofdmap van het systeem (/), geen modelmap. Kies de map met je modellen, bijvoorbeeld /models.'), 400
    with db() as c:
        known = [x['path'] for x in c.execute('SELECT path FROM roots')]
        for x in ([] if p in known else known):  # dezelfde root nogmaals toevoegen is geen overlap
            if _under(p, x) or _under(x, p):
                return jsonify(error=f"Deze map overlapt met een bestaande root folder: {x}"), 400
        c.execute('INSERT OR IGNORE INTO roots(path) VALUES(?)', (p,))
        rid = c.execute('SELECT id FROM roots WHERE path=?', (p,)).fetchone()['id']
    log.info('Root folder toegevoegd: %s', p)
    sync_watchers()
    threading.Thread(target=scan, args=(rid,), daemon=True).start()
    return jsonify(id=rid)


@app.put('/api/roots/<int:rid>')
def roots_put(rid):
    j = request.json or {}
    with db() as c:
        if 'watch' in j:
            c.execute('UPDATE roots SET watch=? WHERE id=?', (1 if j['watch'] else 0, rid))
        if 'allow_write' in j:
            c.execute('UPDATE roots SET allow_write=? WHERE id=?', (1 if j['allow_write'] else 0, rid))
    if 'watch' in j:
        sync_watchers()
    bump()
    return jsonify(ok=True)


@app.delete('/api/roots/<int:rid>')
def roots_del(rid):
    with db() as c:
        ids = [r['id'] for r in c.execute('SELECT id FROM models WHERE root_id=?', (rid,))]
        c.execute('DELETE FROM roots WHERE id=?', (rid,))
    for i in ids:
        try:
            os.remove(os.path.join(THUMBS, f'{i}.png'))
        except OSError:
            pass
    sync_watchers()
    hist('Root verwijderd', f'Root folder verwijderd uit de bibliotheek ({len(ids)} modellen); bestanden zijn niet aangeraakt')
    return jsonify(ok=True)


def _under(p, root):
    r = root.rstrip('\\/')
    return len(p) >= len(r) and p[:len(r)].lower() == r.lower() and (len(p) == len(r) or p[len(r)] in '\\/')


def _rebase(p, old, new):
    """Pad onder de oude root omzetten naar het nieuwe pad, ook van Windows (\\) naar Linux (/) en terug. None = niet onder de oude root."""
    if not _under(p, old):
        return None
    parts = [x for x in re.split(r'[\\/]+', p[len(old.rstrip('\\/')):]) if x]
    return os.path.join(new, *parts) if parts else new


def _has_data(c, ids):
    """Hoeveel van deze modellen hebben eigen gegevens (notitie, favoriet, categorie, printlogboek, eigen thumbnail...)?"""
    n = 0
    for i in range(0, len(ids), 500):
        ch = ids[i:i + 500]
        n += c.execute("SELECT COUNT(*) FROM models WHERE id IN (%s) AND (COALESCE(notes,'')<>'' OR favorite=1 OR COALESCE(printed,'')<>'' OR COALESCE(source_url,'')<>'' "
                       "OR COALESCE(display_name,'')<>'' OR thumb_custom=1 OR id IN (SELECT model_id FROM model_categories) OR id IN (SELECT model_id FROM prints))" % ','.join('?' * len(ch)), ch).fetchone()[0]
    return n


def plan_root_move(rid, raw):
    """Bepaalt wat er gebeurt als een root folder een nieuw pad krijgt. Geeft (plan, None) of (None, (melding, statuscode))."""
    raw = clean_path(raw)
    if not raw:
        return None, ('Geen pad opgegeven', 400)
    if os.name == 'nt' and unc_server_only(raw):
        return None, ('Geef een volledig netwerkpad op: server én share, bijvoorbeeld \\\\nas\\modellen', 400)
    new = os.path.normpath(raw)
    if not os.path.isdir(new):
        return None, ('Map niet gevonden. Controleer het pad en of dit Windows-account toegang heeft.' if os.name == 'nt' else 'Map bestaat niet (is hij gemount in de container/LXC?)', 400)
    with db() as c:
        r = c.execute('SELECT * FROM roots WHERE id=?', (rid,)).fetchone()
        if not r:
            return None, ('Root folder niet gevonden', 404)
        if new == r['path']:
            return None, ('Dit is al het pad van deze root folder', 400)
        roots = c.execute('SELECT * FROM roots WHERE id<>?', (rid,)).fetchall()
        rows = c.execute('SELECT id, path, container, member FROM models WHERE root_id=?', (rid,)).fetchall()
        others = {x['path']: (x['id'], x['root_id']) for x in c.execute('SELECT id, path, root_id FROM models WHERE root_id<>?', (rid,))}
    target = next((x for x in roots if x['path'] == new), None)
    for x in roots:
        if x is not target and (_under(x['path'], new) or _under(new, x['path'])):
            return None, (f"Het nieuwe pad overlapt met een andere root folder: {x['path']}", 400)
    key = (lambda s: s.lower()) if os.name == 'nt' else (lambda s: s)
    have = set()
    for d, dirs, files in os.walk(walk_top(new), followlinks=False):
        dirs[:] = [x for x in dirs if not x.startswith(('.', '@', '#', '$')) and x != 'System Volume Information']
        have.update(key(os.path.join(d, f)) for f in files)
    updates, found = [], 0
    for m in rows:
        if m['container']:
            nc = _rebase(m['container'], r['path'], new)
            np_ = f"{nc}!/{m['member']}" if nc else None
            present = bool(nc) and key(nc) in have
        else:
            nc, np_ = None, _rebase(m['path'], r['path'], new)
            present = bool(np_) and key(np_) in have
        if np_ is None:
            continue
        found += present
        updates.append((m['id'], np_, nc))
    clash = [others[p] for _, p, _ in updates if p in others]
    if any(x[1] != (target['id'] if target else None) for x in clash):
        return None, ('Het nieuwe pad overlapt met modellen uit een andere root folder', 400)
    cids = [x[0] for x in clash]
    with db() as c:
        with_data = _has_data(c, cids) if cids else 0
    return dict(old_path=r['path'], new_path=new, total=len(rows), found=found, missing=len(updates) - found, conflicts=len(cids), conflict_ids=cids,
                conflicts_with_data=with_data, merge=bool(target), target_id=target['id'] if target else None, updates=updates,
                needs_force=bool(rows) and found * 2 < len(rows)), None


@app.post('/api/roots/<int:rid>/move')
def roots_move(rid):
    """Root folder een nieuw pad geven (bijvoorbeeld van \\\\nas\\3d naar /models) terwijl modellen, categorieën, notities en thumbnails behouden blijven.
    Zonder 'apply' alleen een overzicht van wat er zou gebeuren."""
    j = request.json or {}
    plan, err = plan_root_move(rid, j.get('path'))
    if err:
        return jsonify(error=err[0]), err[1]
    out = {k: plan[k] for k in ('new_path', 'total', 'found', 'missing', 'conflicts', 'conflicts_with_data', 'merge', 'needs_force')}
    if not j.get('apply'):
        return jsonify(out)
    if plan['needs_force'] and not j.get('force'):
        return jsonify(error=f"Op het nieuwe pad zijn maar {plan['found']} van {plan['total']} bestanden gevonden", **out), 409
    with db() as c:
        if plan['conflict_ids']:  # dubbele ingangen van een eerdere scan op de nieuwe plek: de bestaande modellen met hun gegevens winnen
            c.executemany('DELETE FROM models WHERE id=?', [(i,) for i in plan['conflict_ids']])
        c.executemany('UPDATE models SET path=?, container=? WHERE id=?', [(p, nc, i) for i, p, nc in plan['updates']])
        final = rid
        if plan['merge']:
            final = plan['target_id']
            c.execute('UPDATE models SET root_id=? WHERE root_id=?', (final, rid))
            c.execute('DELETE FROM roots WHERE id=?', (rid,))
        else:
            c.execute('UPDATE roots SET path=? WHERE id=?', (plan['new_path'], rid))
    for i in plan['conflict_ids']:
        try:
            os.remove(os.path.join(THUMBS, f'{i}.png'))
        except OSError:
            pass
    log.info('Root folder verplaatst: %s -> %s (%d modellen)', plan['old_path'], plan['new_path'], len(plan['updates']))
    hist('Root verplaatst', f"{plan['old_path']} → {plan['new_path']} ({len(plan['updates'])} modellen)")
    sync_watchers()
    bump()
    threading.Thread(target=scan, args=(final,), daemon=True).start()
    return jsonify(out)


# ---------------------------------------------------------------- uploaden (beheerders en gasten met toestemming)
UPLOAD_BAD = set('\\/:*?"<>|\x00') | {chr(i) for i in range(32)}
UPLOAD_HIDDEN = ('.', '@', '#', '$')  # zulke mappen worden niet gescand


def apply_upload_cats(ids):
    """Categorieën die bij het uploaden zijn gekozen toepassen zodra de scan het nieuwe model heeft toegevoegd."""
    with db() as c:
        c.execute('DELETE FROM upload_cats WHERE ts<?', (time.time() - 7 * 86400,))
        if not c.execute('SELECT 1 FROM upload_cats LIMIT 1').fetchone():
            return
        for i in range(0, len(ids), 500):
            ch = ids[i:i + 500]
            for m in c.execute('SELECT id, path FROM models WHERE id IN (%s)' % ','.join('?' * len(ch)), ch).fetchall():
                for u in c.execute('SELECT category_id FROM upload_cats WHERE path=?', (m['path'],)).fetchall():
                    c.execute('INSERT OR IGNORE INTO model_categories SELECT ?, id FROM categories WHERE id=?', (m['id'], u['category_id']))
                c.execute('DELETE FROM upload_cats WHERE path=?', (m['path'],))
    bump()


def upload_name(s, what='Bestandsnaam'):
    """Veilige naam voor één bestand of map: geen paden, geen vreemde tekens, niet verborgen."""
    s = ''.join('_' if ch in UPLOAD_BAD else ch for ch in str(s or '')).strip().strip('.').strip()
    return s[:150]


def upload_root(rid):
    with db() as c:
        r = c.execute('SELECT * FROM roots WHERE id=?', (rid,)).fetchone()
    if not r or not os.path.isdir(r['path']):
        return None, ('Root folder niet gevonden of niet bereikbaar', 404)
    if not os.access(r['path'], os.W_OK):
        return None, ('Deze root folder is alleen-lezen (niet beschrijfbaar)', 400)
    return dict(r), None


def upload_dir(root, rel, create=False):
    """(absoluut pad, fout) voor een relatieve submap binnen de root folder. Nooit buiten de root, geen verborgen mappen."""
    parts = [x for x in re.split(r'[\\/]+', str(rel or '').strip()) if x]
    if len(parts) > 8:
        return None, 'Te veel mappen diep'
    clean = []
    for x in parts:
        if x in ('.', '..') or x.startswith(UPLOAD_HIDDEN) or x != upload_name(x) or x == 'System Volume Information':
            return None, f'Ongeldige mapnaam: {x}'
        clean.append(x)
    base = os.path.realpath(root['path'])
    d = os.path.join(root['path'], *clean)
    rp = os.path.realpath(d)
    if rp != base and not rp.startswith(base.rstrip(os.sep) + os.sep):
        return None, 'Map ligt buiten de root folder'
    if not os.path.isdir(d):
        if not create:
            return None, 'Map bestaat niet'
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            return None, e.strerror or 'Map aanmaken mislukt'
    return d, None


def upload_scope():
    """(root, basismap, fout) voor leerlingen en medewerkers: een leerling uploadt alleen in de eigen map, een medewerker binnen de eigen school.
    Beheerders: (None, '', None) = geen beperking."""
    u = g.get('user')
    if not u or u['role'] == 'admin':
        return None, '', None
    if not u.get('school_id'):
        return None, '', ('Je account is niet aan een school gekoppeld', 403)
    with db() as c:
        sc = c.execute('SELECT * FROM schools WHERE id=? AND active=1', (u['school_id'],)).fetchone()
    if sc and sc['root_id'] is None:
        with db() as c:  # school zonder root: bij precies één root folder die alsnog koppelen
            rr = c.execute('SELECT id FROM roots').fetchall()
            if len(rr) == 1:
                c.execute('UPDATE schools SET root_id=? WHERE id=?', (rr[0]['id'], sc['id']))
                sc = c.execute('SELECT * FROM schools WHERE id=?', (sc['id'],)).fetchone()
                _school_dirs(dict(sc))
    if not sc or sc['root_id'] is None:
        return None, '', ('Je school heeft nog geen opslagmap. Vraag de beheerder om bij Instellingen › Scholen een root folder te kiezen.', 404)
    root, err = upload_root(sc['root_id'])
    if err:
        return None, '', err
    if u['role'] == 'student':
        if not u.get('home'):
            with db() as c:  # thuismap kon niet gemaakt worden toen de school nog geen root had
                h = make_home(c, u['school_id'], 'student', u['username'])
                c.execute('UPDATE users SET home=? WHERE id=?', (h, u['id']))
            u['home'] = h
        if not u.get('home'):
            return None, '', ('Je account heeft nog geen eigen map', 403)
        base = u['home'].replace('\\', '/').strip('/')
    else:
        base = sc['slug']
    return dict(root, school=sc['name']), base, None


def sroot_row(u):
    with db() as c:
        return c.execute('SELECT * FROM schools WHERE id=?', (u.get('school_id'),)).fetchone()


def quota_mb(sc):
    """Opslagruimte per leerling in MB: de instelling van de school, anders de algemene instelling (0 = onbeperkt)."""
    if sc is not None and sc['quota_mb'] is not None:
        return int(sc['quota_mb'])
    return int(CFG['student_quota_mb'] or 0)


def dir_size(p):
    t = 0
    for dp, dn, fn in os.walk(p):
        for f in fn:
            try:
                t += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return t


@app.get('/api/upload/targets')
def upload_targets():
    """Root folders waar je naartoe kunt uploaden: alleen de mapnaam, nooit het pad op de schijf."""
    sroot, base, serr = upload_scope()
    if serr:
        return jsonify(error=serr[0]), serr[1]
    if sroot:
        used = dir_size(os.path.join(sroot['path'], base)) if g.user['role'] == 'student' and os.path.isdir(os.path.join(sroot['path'], base)) else 0
        return jsonify(roots=[dict(id=sroot['id'], name=(g.user.get('display_name') or g.user['username']) if g.user['role'] == 'student' else sroot['school'])],
                       exts=sorted(e[1:] for e in exts()) + (['zip'] if CFG['zip_support'] == '1' else []), max_mb=MAX_MB, scoped=True,
                       quota_mb=quota_mb(sroot_row(g.user)) if g.user['role'] == 'student' else 0, used_mb=round(used / 2 ** 20, 1),
                       share_default=share_default_for(g.user))
    out = []
    with db() as c:
        for r in c.execute('SELECT * FROM roots ORDER BY path'):
            if os.path.isdir(r['path']) and os.access(r['path'], os.W_OK):
                n = os.path.basename(r['path'].rstrip('/\\')) or r['path']
                out.append(dict(id=r['id'], name=n))
    return jsonify(roots=out, exts=sorted(e[1:] for e in exts()) + (['zip'] if CFG['zip_support'] == '1' else []), max_mb=MAX_MB)


@app.get('/api/upload/dirs')
def upload_dirs():
    root, err = upload_root(request.args.get('root', type=int))
    if err:
        return jsonify(error=err[0]), err[1]
    sroot, base, serr = upload_scope()
    if serr:
        return jsonify(error=serr[0]), serr[1]
    rel = request.args.get('path')
    if sroot:
        root = sroot
        rel = base + '/' + str(rel or '')
        os.makedirs(os.path.join(root['path'], base), exist_ok=True)
    d, e = upload_dir(root, rel)
    if e:
        return jsonify(error=e), 400
    try:
        dirs = sorted((x.name for x in os.scandir(d) if x.is_dir() and not x.name.startswith(UPLOAD_HIDDEN) and x.name != 'System Volume Information'), key=str.lower)
    except OSError as ex:
        return jsonify(error=ex.strerror or 'Map niet toegankelijk'), 400
    try:  # bestanden in deze map (alleen namen), zodat je ziet wat er al staat
        files = sorted((x.name for x in os.scandir(d) if x.is_file() and not x.name.startswith(UPLOAD_HIDDEN)), key=str.lower)[:500]
    except OSError:
        files = []
    return jsonify(dirs=dirs, files=files)


@app.post('/api/upload')
def upload_post():
    """Eén bestand uploaden naar een map in een root folder en meteen categorieën kiezen. Overschrijft nooit iets: bij dezelfde naam komt er (2) achter."""
    request.max_content_length = (MAX_MB + 2) * 2 ** 20
    root, err = upload_root(request.form.get('root', type=int))
    if err:
        return jsonify(error=err[0]), err[1]
    sroot, base, serr = upload_scope()
    if serr:
        return jsonify(error=serr[0]), serr[1]
    folder_in = request.form.get('folder')
    if sroot:  # leerling/medewerker: altijd binnen de eigen map of school, wat er ook is opgegeven
        root = sroot
        folder_in = base + '/' + str(folder_in or '')
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(error='Geen bestand ontvangen'), 400
    fname = upload_name(os.path.basename(str(f.filename).replace('\\', '/')))
    stem, ext = os.path.splitext(fname)
    ok = exts() | ({'.zip'} if CFG['zip_support'] == '1' else set())
    if not stem or ext.lower() not in ok:
        return jsonify(error=f'Bestandstype niet toegestaan ({ext or "geen extensie"}). Toegestaan: ' + ', '.join(sorted(x[1:] for x in ok))), 400
    cats = []
    for x in str(request.form.get('categories') or '').split(','):
        if x.strip().isdigit():
            cats.append(int(x))
    if cats:
        with db() as c:
            have = {r[0] for r in c.execute('SELECT id FROM categories')}
        if any(x not in have for x in cats):
            return jsonify(error='Categorie bestaat niet meer'), 400
    d, e = upload_dir(root, folder_in, create=True)
    if e:
        return jsonify(error=e), 400
    final, n = os.path.join(d, fname), 1
    while os.path.exists(final):
        n += 1
        final = os.path.join(d, f'{stem} ({n}){ext}')
    tmp = os.path.join(d, f'.upload-{secrets.token_hex(6)}.part')
    try:
        f.save(tmp)
        size = os.path.getsize(tmp)
        if size == 0:
            raise ValueError('Het bestand is leeg')
        if size > MAX_MB * 2 ** 20:
            raise ValueError(f'Bestand groter dan {MAX_MB} MB (MAX_FILE_MB)')
        if sroot and g.user['role'] == 'student':
            quota = quota_mb(sroot_row(g.user)) * 2 ** 20
            if quota and dir_size(os.path.join(root['path'], base)) > quota:  # het nieuwe (tijdelijke) bestand telt al mee
                raise ValueError(f'Je opslagruimte is vol (maximaal {quota // 2 ** 20} MB). Verwijder eerst een model.')
        if not os.path.exists(final):
            os.replace(tmp, final)
        else:  # tussendoor bezet geraakt
            final = os.path.join(d, f'{stem} ({n + 1}){ext}')
            os.replace(tmp, final)
    except ValueError as ex:
        _rm(tmp)
        return jsonify(error=str(ex)), 413
    except OSError as ex:
        _rm(tmp)
        return jsonify(error=ex.strerror or 'Opslaan mislukt'), 500
    if sroot:
        sh = request.form.get('shared')
        sh = (1 if sh in ('1', 'true', 'on') else 0) if sh is not None else (1 if share_default_for(g.user) else 0)
        with db() as c:
            c.execute('INSERT OR REPLACE INTO upload_share VALUES(?,?,?)', (os.path.join(root['path'], os.path.relpath(final, root['path'])), sh, time.time()))
    if cats:
        with db() as c:
            for x in cats:
                c.execute('INSERT OR REPLACE INTO upload_cats VALUES(?,?,?)', (os.path.join(root['path'], os.path.relpath(final, root['path'])), x, time.time()))
    who = g.user['username'] if g.get('user') and g.user.get('username') else 'iemand'
    rel = os.path.relpath(final, root['path']).replace(os.sep, '/')
    hist('Upload', f'{who} uploadde {os.path.basename(final)} naar {rel}')
    log.info('Upload: %s door %s (%d bytes)', rel, who, size)
    NEXT['soon'] = time.time() + max(0, int(CFG['min_age'])) + 1  # de scan neemt het bestand over zodra het "rustig" is
    return jsonify(ok=True, name=os.path.basename(final), renamed=os.path.basename(final) != fname)


@app.post('/api/models/<int:mid>/share')
def model_share(mid):
    r = one(mid)
    if not can_manage(g.user, r):
        return jsonify(error='Je mag dit model niet aanpassen'), 403
    sh = 1 if (request.json or {}).get('shared') else 0
    with db() as c:
        c.execute('UPDATE models SET shared=? WHERE id=?', (sh, mid))
    hist('Delen', f"{g.user['username']} zette delen {'aan' if sh else 'uit'} voor {r['name']}.{r['ext']}", mid)
    bump()
    return jsonify(ok=True, shared=bool(sh))


@app.post('/api/models/<int:mid>/delete')
def model_delete_own(mid):
    """Eigen model verwijderen (naar de prullenbak van de root folder). Eigenaar, medewerker van dezelfde school of beheerder."""
    r = one(mid)
    if not can_manage(g.user, r):
        return jsonify(error='Je mag dit model niet verwijderen'), 403
    out, code = _trash(mid, any_file=True)
    return jsonify(out), code


@app.get('/api/me/prefs')
def prefs_get():
    return jsonify(share_default=share_default_for(g.user))


@app.post('/api/me/prefs')
def prefs_set():
    if not g.user.get('id'):
        return jsonify(error='Geen account'), 400
    sd = 1 if (request.json or {}).get('share_default', True) else 0
    with db() as c:
        c.execute('UPDATE users SET share_default=?, share_own=? WHERE id=?', (sd, sd if g.user['role'] == 'student' else None, g.user['id']))
    OKAUTH.clear()
    return jsonify(ok=True, share_default=bool(sd))


# ---------------------------------------------------------------- scholen beheren, meldingen en printaanvragen
def _school_of(m):
    return m['school_id']


def _staff_of(u, school_id):
    return u['role'] == 'admin' or (u['role'] == 'staff' and school_id is not None and u.get('school_id') == school_id)


@app.get('/api/schools')
def schools_list():
    with db() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM schools ORDER BY name')]
        for r in rows:
            r['students'] = c.execute("SELECT COUNT(*) FROM users WHERE school_id=? AND role='student'", (r['id'],)).fetchone()[0]
            r['staff'] = c.execute("SELECT COUNT(*) FROM users WHERE school_id=? AND role='staff'", (r['id'],)).fetchone()[0]
            r['models'] = c.execute('SELECT COUNT(*) FROM models WHERE school_id=?', (r['id'],)).fetchone()[0]
    return jsonify(schools=rows, default_quota_mb=int(CFG['student_quota_mb'] or 0), default_share=CFG['default_share'] == '1')


def _school_fields(j, cur=None):
    name = str(j.get('name', cur['name'] if cur else '') or '').strip()
    if not name:
        return None, 'Geef de school een naam'
    slug = slugify(j.get('slug') or (cur['slug'] if cur else '') or name)
    root_id = j.get('root_id', cur['root_id'] if cur else None)
    if root_id in ('', 0):
        root_id = None
    if root_id is not None:
        with db() as c:
            if not c.execute('SELECT 1 FROM roots WHERE id=?', (int(root_id),)).fetchone():
                return None, 'Root folder bestaat niet'
        root_id = int(root_id)
    if root_id is None:
        with db() as c:
            rr = c.execute('SELECT id FROM roots').fetchall()
        if len(rr) == 1:
            root_id = rr[0]['id']  # maar één root folder: die is vanzelfsprekend
    q = j.get('quota_mb', cur['quota_mb'] if cur else None)
    try:
        q = None if q in (None, '') else max(0, min(1000000, int(q)))
    except (TypeError, ValueError):
        return None, 'Ongeldige opslaglimiet'
    sd = j.get('share_default', cur['share_default'] if cur else None)
    sd = None if sd in (None, '') else (1 if sd in (True, 1, '1', 'true', 'on', 'ja') else 0)
    return dict(share_default=sd, name=name, slug=slug, root_id=root_id, group_id=str(j.get('group_id', cur['group_id'] if cur else '') or '').strip(), staff_group_id=str(j.get('staff_group_id', cur['staff_group_id'] if cur else '') or '').strip(), quota_mb=q,
                active=1 if j.get('active', cur['active'] if cur else 1) else 0), None


def _school_dirs(f):
    with db() as c:
        r = c.execute('SELECT path FROM roots WHERE id=?', (f['root_id'],)).fetchone() if f['root_id'] else None
    if r:
        for sub in ('leerlingen', 'medewerkers'):
            try:
                os.makedirs(os.path.join(r['path'], f['slug'], sub), exist_ok=True)
            except OSError as e:
                log.warning('Schoolmap aanmaken mislukt: %s', e)


@app.post('/api/schools')
def schools_add():
    f, err = _school_fields(request.json or {})
    if err:
        return jsonify(error=err), 400
    try:
        with db() as c:
            sid = c.execute('INSERT INTO schools(name, slug, root_id, group_id, staff_group_id, active, created, quota_mb, share_default) VALUES(?,?,?,?,?,?,?,?,?)',
                            (f['name'], f['slug'], f['root_id'], f['group_id'], f['staff_group_id'], f['active'], time.time(), f['quota_mb'], f['share_default'])).lastrowid
    except sqlite3.IntegrityError:
        return jsonify(error='Er is al een school met deze naam of map'), 409
    _school_dirs(f)
    hist('Scholen', f"School {f['name']} toegevoegd")
    return jsonify(ok=True, id=sid)


@app.put('/api/schools/<int:sid>')
def schools_put(sid):
    with db() as c:
        cur = c.execute('SELECT * FROM schools WHERE id=?', (sid,)).fetchone()
    if not cur:
        return jsonify(error='School niet gevonden'), 404
    f, err = _school_fields(request.json or {}, cur)
    if err:
        return jsonify(error=err), 400
    if f['slug'] != cur['slug'] and sroot_models(sid):
        return jsonify(error='De mapnaam kan niet meer wijzigen: er staan al modellen van deze school'), 409
    try:
        with db() as c:
            c.execute('UPDATE schools SET name=?, slug=?, root_id=?, group_id=?, staff_group_id=?, active=?, quota_mb=?, share_default=? WHERE id=?', (f['name'], f['slug'], f['root_id'], f['group_id'], f['staff_group_id'], f['active'], f['quota_mb'], f['share_default'], sid))
    except sqlite3.IntegrityError:
        return jsonify(error='Er is al een school met deze naam of map'), 409
    _school_dirs(f)
    bump()
    return jsonify(ok=True)


def sroot_models(sid):
    with db() as c:
        return c.execute('SELECT COUNT(*) FROM models WHERE school_id=?', (sid,)).fetchone()[0]


# --- algemene bibliotheek: mappen buiten de scholen verbergen voor leerlingen
def _folder_root(rid):
    with db() as c:
        r = c.execute('SELECT * FROM roots WHERE id=?', (rid,)).fetchone()
    return dict(r) if r and os.path.isdir(r['path']) else None


def _rel_ok(root, rel):
    """(schone relatieve map, fout) binnen de root; geen verborgen mappen, geen ontsnappen."""
    parts = [x for x in re.split(r'[\\/]+', str(rel or '')) if x]
    if any(x in ('.', '..') or x.startswith('.') for x in parts):
        return None, 'Ongeldige map'
    d = os.path.join(root['path'], *parts)
    base = os.path.realpath(root['path'])
    rp = os.path.realpath(d)
    if rp != base and not rp.startswith(base.rstrip(os.sep) + os.sep):
        return None, 'Map ligt buiten de root folder'
    if not os.path.isdir(d):
        return None, 'Map bestaat niet'
    return '/'.join(parts), None


@app.get('/api/folder-access')
def folders_get():
    """Mappen van een root folder met hun zichtbaarheid voor leerlingen. Zonder root: de lijst met root folders. Schoolmappen staan er niet bij."""
    rid = request.args.get('root', type=int)
    if rid is None:
        with db() as c:
            return jsonify(roots=[dict(id=r['id'], name=os.path.basename(r['path'].rstrip('/\\')) or r['path']) for r in c.execute('SELECT * FROM roots ORDER BY path')])
    root = _folder_root(rid)
    if not root:
        return jsonify(error='Root folder niet gevonden'), 404
    rel, err = _rel_ok(root, request.args.get('path'))
    if err:
        return jsonify(error=err), 400
    with db() as c:
        hid = [r['rel'] for r in c.execute('SELECT rel FROM hidden_folders WHERE root_id=?', (rid,))]
        slugs = {r['slug'].lower() for r in c.execute('SELECT slug FROM schools WHERE root_id=?', (rid,))}
    inherited = any(rel == h or rel.startswith(h + '/') for h in hid) if rel else False
    out = []
    try:
        for e in sorted(os.scandir(os.path.join(root['path'], *rel.split('/')) if rel else root['path']), key=lambda x: x.name.lower()):
            if not e.is_dir() or e.name.startswith('.') or e.name == 'System Volume Information' or (not rel and e.name.lower() in slugs):
                continue
            r2 = (rel + '/' if rel else '') + e.name
            out.append(dict(name=e.name, hidden=r2 in hid, inherited=inherited))
    except OSError as ex:
        return jsonify(error=ex.strerror or 'Map niet toegankelijk'), 400
    return jsonify(dirs=out, path=rel, inherited=inherited)


@app.post('/api/folder-access/hide')
def folders_hide():
    j = request.json or {}
    root = _folder_root(j.get('root'))
    if not root:
        return jsonify(error='Root folder niet gevonden'), 404
    rel, err = _rel_ok(root, j.get('path'))
    if err or not rel:
        return jsonify(error=err or 'Kies een map'), 400
    with db() as c:
        if j.get('hidden'):
            c.execute('INSERT OR IGNORE INTO hidden_folders VALUES(?,?)', (root['id'], rel))
        else:
            c.execute('DELETE FROM hidden_folders WHERE root_id=? AND rel=?', (root['id'], rel))
    hist('Mappen', f"{g.user['username']} {'verborg' if j.get('hidden') else 'toonde'} de map {rel} {'voor' if j.get('hidden') else 'aan'} leerlingen")
    bump()
    return jsonify(ok=True)


# --- melden van gedeelde modellen
@app.post('/api/models/<int:mid>/report')
def model_report(mid):
    r = one(mid)
    reason = str((request.json or {}).get('reason') or '').strip()[:300]
    if not reason:
        return jsonify(error='Geef een reden op'), 400
    u = g.user
    with db() as c:
        if c.execute("SELECT 1 FROM reports WHERE model_id=? AND reporter_id=? AND status='open'", (mid, u['id'])).fetchone():
            return jsonify(ok=True, already=True)
        c.execute("INSERT INTO reports(model_id, reporter_id, reason, ts, status) VALUES(?,?,?,?,'open')", (mid, u['id'], reason, time.time()))
    hist('Melding', f"{u['username']} meldde {r['name']}.{r['ext']}: {reason}", mid)
    bump()
    return jsonify(ok=True)


@app.get('/api/reports')
def reports_list():
    u = g.user
    st = request.args.get('status', 'open')
    q = ('SELECT r.*, m.name AS mname, m.ext AS mext, m.school_id AS mschool, m.hidden AS mhidden, m.owner_id AS mowner, rp.username AS rname, rp.display_name AS rdisp, rp.klas AS rklas '
         'FROM reports r JOIN models m ON m.id=r.model_id LEFT JOIN users rp ON rp.id=r.reporter_id WHERE 1=1')
    args = []
    if st != 'all':
        q += ' AND r.status=?'; args.append('open')
    if u['role'] != 'admin':
        q += ' AND m.school_id=?'; args.append(u.get('school_id'))
    q += ' ORDER BY r.ts DESC LIMIT 300'
    with db() as c:
        rows = c.execute(q, args).fetchall()
        sch = {x['id']: x['name'] for x in c.execute('SELECT id, name FROM schools')}
    return jsonify(reports=[dict(id=r['id'], model_id=r['model_id'], model=f"{r['mname']}.{r['mext']}", reason=r['reason'], ts=r['ts'], status=r['status'], action=r['action'] or '',
                                 hidden=bool(r['mhidden']), reporter=(r['rdisp'] or r['rname'] or '') + (f" ({r['rklas']})" if r['rklas'] else ''), school=sch.get(r['mschool'], '')) for r in rows])


@app.post('/api/reports/<int:rid>')
def report_handle(rid):
    """Een melding afhandelen: negeren (dismiss), model verbergen (hide) of verwijderen (delete)."""
    act = (request.json or {}).get('action')
    if act not in ('dismiss', 'hide', 'delete'):
        return jsonify(error='Onbekende actie'), 400
    with db() as c:
        r = c.execute('SELECT r.*, m.school_id AS mschool FROM reports r JOIN models m ON m.id=r.model_id WHERE r.id=?', (rid,)).fetchone()
    if not r or not _staff_of(g.user, r['mschool']):
        return jsonify(error='Melding niet gevonden'), 404
    mid = r['model_id']
    if act == 'hide':
        with db() as c:
            c.execute('UPDATE models SET hidden=1 WHERE id=?', (mid,))
    with db() as c:
        c.execute("UPDATE reports SET status='done', handled_by=?, handled_ts=?, action=? WHERE model_id=? AND status='open'", (g.user['id'], time.time(), act, mid))
    if act == 'delete':
        out, code = _trash(mid, any_file=True)
        if code != 200:
            return jsonify(out), code
    hist('Melding', f"{g.user['username']} handelde melding af: {act}", None if act == 'delete' else mid)
    bump()
    return jsonify(ok=True)


@app.post('/api/models/<int:mid>/hide')
def model_hide(mid):
    r = one(mid)
    if not _staff_of(g.user, r['school_id']):
        return jsonify(error='Geen toegang'), 403
    h = 1 if (request.json or {}).get('hidden', True) else 0
    with db() as c:
        c.execute('UPDATE models SET hidden=? WHERE id=?', (h, mid))
    hist('Verborgen', f"{g.user['username']} {'verborg' if h else 'toonde weer'} {r['name']}.{r['ext']}", mid)
    bump()
    return jsonify(ok=True, hidden=bool(h))


# --- printaanvragen: leerling vraagt, medewerker slicet, print en meldt klaar
REQ_STATUS = ('open', 'busy', 'done', 'rejected', 'cancelled')
REQ_EXT = ('.3mf', '.gcode', '.bgcode')


def _req_dir(school_id, rid, create=False):
    with db() as c:
        sc = c.execute('SELECT s.slug, r.path FROM schools s JOIN roots r ON r.id=s.root_id WHERE s.id=?', (school_id,)).fetchone()
    if not sc:
        return None
    d = os.path.join(sc['path'], sc['slug'], '.aanvragen', str(int(rid)))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def _req_out(r, viewer, names):
    staff = _staff_of(viewer, r['school_id'])
    rq = names.get(r['requester_id'], {})
    return dict(id=r['id'], model_id=r['model_id'], model=r['model_name'], colors=[x for x in (r['colors'] or '').split(',') if x], copies=r['copies'], note=r['note'] or '',
                status=r['status'], staff_note=r['staff_note'] or '', has_file=bool(r['sliced_name']), sliced_name=r['sliced_name'] or '', created=r['created'], updated=r['updated'],
                mine=r['requester_id'] == viewer['id'], requester=(('Verwijderde leerling' if not rq else '') + (rq.get('display_name') or rq.get('username') or '') + (f" ({rq['klas']})" if rq.get('klas') else '')) if staff else '')


@app.get('/api/requests/options')
def requests_options():
    return jsonify(colors=[dict(name=n, hex='#' + h) for n, h in BB_COLORS], max_copies=20, max_colors=4)


@app.get('/api/requests')
def requests_list():
    u = g.user
    q, a = 'SELECT * FROM print_requests WHERE 1=1', []
    if u['role'] == 'student':
        q += ' AND requester_id=?'; a.append(u['id'])
    elif u['role'] == 'staff':
        q += ' AND school_id=?'; a.append(u.get('school_id'))
    st = request.args.get('status')
    if st == 'active':
        q += " AND status IN ('open','busy')"
    elif st in REQ_STATUS:
        q += ' AND status=?'; a.append(st)
    q += ' ORDER BY CASE status WHEN "open" THEN 0 WHEN "busy" THEN 1 ELSE 2 END, created DESC LIMIT 500'
    with db() as c:
        rows = c.execute(q, a).fetchall()
        names = {r['id']: dict(r) for r in c.execute('SELECT id, username, display_name, klas FROM users')}
    return jsonify(requests=[_req_out(r, u, names) for r in rows])


@app.post('/api/requests')
def requests_add():
    u, j = g.user, request.json or {}
    if not u.get('school_id'):
        return jsonify(error='Je account is niet aan een school gekoppeld'), 400
    try:
        mid = int(j.get('model_id'))
    except (TypeError, ValueError):
        return jsonify(error='Kies een model'), 400
    m = one(mid)
    valid = {n for n, _ in BB_COLORS}
    cols = []
    for x in (j.get('colors') or []):
        if x in valid and x not in cols:
            cols.append(x)
    if len(cols) > 4:
        return jsonify(error='Kies maximaal 4 kleuren'), 400
    try:
        copies = max(1, min(20, int(j.get('copies') or 1)))
    except (TypeError, ValueError):
        return jsonify(error='Ongeldig aantal'), 400
    note = str(j.get('note') or '').strip()[:300]
    with db() as c:
        if c.execute("SELECT COUNT(*) FROM print_requests WHERE requester_id=? AND status IN ('open','busy')", (u['id'],)).fetchone()[0] >= 10:
            return jsonify(error='Je hebt al 10 lopende aanvragen. Wacht tot er een klaar is.'), 429
        now = time.time()
        rid = c.execute('INSERT INTO print_requests(model_id, model_name, requester_id, school_id, colors, copies, note, status, created, updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (mid, f"{m['name']}.{m['ext']}", u['id'], u['school_id'], ','.join(cols), copies, note, 'open', now, now)).lastrowid
    hist('Printaanvraag', f"{u['username']} vroeg een print van {m['name']}.{m['ext']} aan ({copies}x)", mid)
    bump()
    return jsonify(ok=True, id=rid)


def _req_get(rid, staff=False):
    with db() as c:
        r = c.execute('SELECT * FROM print_requests WHERE id=?', (rid,)).fetchone()
    if not r:
        abort(404)
    u = g.user
    if staff:
        if not _staff_of(u, r['school_id']):
            abort(404)
    elif r['requester_id'] != u['id'] and not _staff_of(u, r['school_id']):
        abort(404)
    return r


@app.post('/api/requests/<int:rid>')
def request_update(rid):
    r, j = _req_get(rid, staff=True), request.json or {}
    st = j.get('status', r['status'])
    if st not in ('open', 'busy', 'done', 'rejected'):
        return jsonify(error='Onbekende status'), 400
    note = str(j.get('staff_note', r['staff_note']) or '').strip()[:300]
    with db() as c:
        c.execute('UPDATE print_requests SET status=?, staff_note=?, handler_id=?, updated=? WHERE id=?', (st, note, g.user['id'], time.time(), rid))
    hist('Printaanvraag', f"{g.user['username']} zette aanvraag {rid} ({r['model_name']}) op {st}", r['model_id'])
    bump()
    return jsonify(ok=True)


@app.post('/api/requests/<int:rid>/cancel')
def request_cancel(rid):
    r = _req_get(rid)
    if r['requester_id'] != g.user['id']:
        abort(404)
    if r['status'] != 'open':
        return jsonify(error='Deze aanvraag is al opgepakt en kan niet meer worden ingetrokken'), 409
    with db() as c:
        c.execute("UPDATE print_requests SET status='cancelled', updated=? WHERE id=?", (time.time(), rid))
    bump()
    return jsonify(ok=True)


@app.post('/api/requests/<int:rid>/file')
def request_file_put(rid):
    """De medewerker legt het gesliced bestand bij de aanvraag (3mf, gcode of bgcode). Het komt in een verborgen map van de school en wordt niet in de bibliotheek getoond."""
    request.max_content_length = (MAX_MB + 2) * 2 ** 20
    r = _req_get(rid, staff=True)
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(error='Geen bestand ontvangen'), 400
    name = upload_name(os.path.basename(str(f.filename).replace('\\', '/')))
    if not name or not name.lower().endswith(REQ_EXT):
        return jsonify(error='Alleen gesliced bestand: ' + ', '.join(e[1:] for e in REQ_EXT)), 400
    d = _req_dir(r['school_id'], rid, create=True)
    if not d:
        return jsonify(error='De school heeft geen opslagmap'), 400
    for old in os.listdir(d):
        _rm(os.path.join(d, old))
    dest = os.path.join(d, name)
    try:
        f.save(dest)
        if os.path.getsize(dest) == 0:
            _rm(dest)
            return jsonify(error='Het bestand is leeg'), 400
    except OSError as e:
        return jsonify(error=e.strerror or 'Opslaan mislukt'), 500
    with db() as c:
        c.execute("UPDATE print_requests SET sliced_name=?, status=CASE WHEN status='open' THEN 'busy' ELSE status END, handler_id=?, updated=? WHERE id=?", (name, g.user['id'], time.time(), rid))
    hist('Printaanvraag', f"{g.user['username']} voegde {name} toe aan aanvraag {rid}", r['model_id'])
    bump()
    return jsonify(ok=True, name=name)


@app.get('/api/requests/<int:rid>/file')
def request_file_get(rid):
    r = _req_get(rid, staff=True)
    d = _req_dir(r['school_id'], rid)
    if not r['sliced_name'] or not d or not os.path.isfile(os.path.join(d, r['sliced_name'])):
        abort(404)
    return send_file(os.path.join(d, r['sliced_name']), as_attachment=True, download_name=r['sliced_name'])


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


PRINTER_PRESETS = [  # maten uit meerdere bronnen; controleer altijd de maat van je eigen printer
    ('Bambu Lab A1 mini', 180, 180, 180), ('Bambu Lab A1', 256, 256, 256), ('Bambu Lab P1P', 256, 256, 256),
    ('Bambu Lab P1S', 256, 256, 256), ('Bambu Lab X1 Carbon', 256, 256, 256), ('Bambu Lab P2S', 256, 256, 256),
    ('Bambu Lab H2S', 340, 320, 340)]


def _printer_fields(j):
    name = (j.get('name') or '').strip()[:60]
    try:
        bed = [float(j[k]) for k in ('bed_x', 'bed_y', 'bed_z')]
    except (KeyError, TypeError, ValueError):
        return None, 'Vul de bedgrootte (X, Y en Z) in mm in'
    if not name:
        return None, 'Geef de printer een naam'
    if not all(0 < v <= 5000 for v in bed):
        return None, 'De bedgrootte moet tussen 0 en 5000 mm liggen'
    return (name, *bed), None


@app.get('/api/printers')
def printers_get():
    with db() as c:
        return jsonify([dict(r) for r in c.execute('SELECT * FROM printers ORDER BY name COLLATE NOCASE')])


@app.get('/api/printers/presets')
def printers_presets():
    return jsonify([dict(name=n, bed_x=x, bed_y=y, bed_z=z) for n, x, y, z in PRINTER_PRESETS])


@app.post('/api/printers')
def printers_add():
    f, err = _printer_fields(request.json or {})
    if err:
        return jsonify(error=err), 400
    try:
        with db() as c:
            pid = c.execute('INSERT INTO printers(name,bed_x,bed_y,bed_z) VALUES(?,?,?,?)', f).lastrowid
    except sqlite3.IntegrityError:
        return jsonify(error='Er bestaat al een printer met die naam'), 409
    bump()
    return jsonify(id=pid)


@app.put('/api/printers/<int:pid>')
def printers_put(pid):
    f, err = _printer_fields(request.json or {})
    if err:
        return jsonify(error=err), 400
    try:
        with db() as c:
            c.execute('UPDATE printers SET name=?, bed_x=?, bed_y=?, bed_z=? WHERE id=?', (*f, pid))
    except sqlite3.IntegrityError:
        return jsonify(error='Er bestaat al een printer met die naam'), 409
    bump()
    return jsonify(ok=True)


@app.delete('/api/printers/<int:pid>')
def printers_del(pid):
    with db() as c:
        c.execute('DELETE FROM printers WHERE id=?', (pid,))
    bump()
    return jsonify(ok=True)


# ---------------------------------------------------------------- Bambuddy (versturen + printgeschiedenis)
BB_EXTS = ('3mf', 'gcode', 'stl')
T['bambuddy'] = dict(last=None, result=None, error=None)


def bb_conn(timeout):
    import http.client
    base = CFG['bambuddy_url'].strip().rstrip('/')
    if not base or not CFG['bambuddy_key']:
        raise ValueError('Bambuddy is niet ingesteld (Instellingen → Algemeen)')
    u = urllib.parse.urlsplit(base)
    cls = http.client.HTTPSConnection if u.scheme == 'https' else http.client.HTTPConnection
    return cls(u.hostname, u.port, timeout=timeout), (u.path or '') + '/api/v1', base


def bb_reason(body):
    """De leesbare reden uit een foutantwoord van Bambuddy (FastAPI: {"detail": ...}), anders het begin van de tekst."""
    raw = body[:400].decode('utf-8', 'ignore')
    try:
        d = json.loads(body)
        d = d.get('detail', d) if isinstance(d, dict) else d
    except ValueError:
        return raw
    if isinstance(d, dict):
        errs = d.get('errors')
        if isinstance(errs, list) and errs:
            return '; '.join(f"{e.get('filename') or ''}: {e.get('error') or e}".strip(': ') if isinstance(e, dict) else str(e) for e in errs)[:300]
        return str(d.get('message') or raw)[:300]
    if isinstance(d, list):
        return '; '.join(str(x.get('msg', x)) if isinstance(x, dict) else str(x) for x in d)[:300]
    return str(d)[:300]


def bb_sliced(path, ext):
    """Is dit een geslicede print (.gcode, of een 3MF met G-code erin)? Bambuddy zet in de wachtrij alleen geslicede bestanden."""
    if ext in ('gcode', 'gco'):
        return True
    if ext == '3mf':
        try:
            with zipfile.ZipFile(path) as z:
                return any(n.lower().endswith('.gcode') for n in z.namelist())
        except (OSError, zipfile.BadZipFile):
            return False
    return False


def bb_fail(r, body, base):
    msg = bb_reason(body)
    if r.status in (401, 403):
        return ValueError(f'Bambuddy weigert de API-sleutel of de rechten daarvan ({r.status}). Controleer de sleutel onder Instellingen → API Keys in Bambuddy.')
    return ValueError(f'Bambuddy antwoordde met fout {r.status}: {msg}')


def bb_call(path, method='GET', params=None, body=None, timeout=15):
    conn, pre, base = bb_conn(timeout)
    q = ('?' + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ''
    try:
        conn.request(method, pre + path + q, body=json.dumps(body).encode() if body is not None else None,
                     headers={'X-API-Key': CFG['bambuddy_key'], 'Accept': 'application/json', **({'Content-Type': 'application/json'} if body is not None else {})})
        r = conn.getresponse()
        data = r.read()
    except (OSError, ValueError) as e:
        raise ValueError(f'Bambuddy is niet bereikbaar op {base}: {getattr(e, "strerror", None) or e}')
    finally:
        conn.close()
    if r.status >= 300:
        raise bb_fail(r, data, base)
    try:
        return json.loads(data or b'null')
    except ValueError:
        raise ValueError('Bambuddy gaf een onverwacht antwoord (geen JSON). Klopt het adres?')


def bb_upload(path, filename, timeout=600):
    """Bestand als multipart naar de bibliotheek van Bambuddy streamen (zonder het in het geheugen te laden)."""
    conn, pre, base = bb_conn(timeout)
    boundary = secrets.token_hex(16)
    safe = filename.replace('"', '_').replace('\r', '').replace('\n', '')
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode('utf-8')
    tail = f'\r\n--{boundary}--\r\n'.encode()
    try:
        conn.putrequest('POST', pre + '/library/files')
        conn.putheader('X-API-Key', CFG['bambuddy_key'])
        conn.putheader('Accept', 'application/json')
        conn.putheader('Content-Type', f'multipart/form-data; boundary={boundary}')
        conn.putheader('Content-Length', str(len(head) + os.path.getsize(path) + len(tail)))
        conn.endheaders()
        conn.send(head)
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                conn.send(chunk)
        conn.send(tail)
        r = conn.getresponse()
        data = r.read()
    except (OSError, ValueError) as e:
        raise ValueError(f'Versturen naar Bambuddy mislukt: {getattr(e, "strerror", None) or e}')
    finally:
        conn.close()
    if r.status >= 300:
        raise bb_fail(r, data, base)
    return json.loads(data or b'{}')


def bb_items(x, *keys):
    """Lijst uit een antwoord halen: direct een lijst, of onder een van de sleutels."""
    if isinstance(x, list):
        return x
    for k in keys:
        if isinstance(x, dict) and isinstance(x.get(k), list):
            return x[k]
    return []


@app.get('/api/bambuddy/status')
def bambuddy_status():
    if not (CFG['bambuddy_url'] and CFG['bambuddy_key']):
        return jsonify(configured=False)
    try:
        ps = [dict(id=p.get('id'), name=str(p.get('name') or p.get('serial_number') or f"Printer {p.get('id')}")) for p in bb_items(bb_call('/printers/', timeout=5), 'items', 'printers') if isinstance(p, dict) and p.get('id') is not None]
        return jsonify(configured=True, ok=True, printers=ps, sync=T['bambuddy'])
    except ValueError as e:
        return jsonify(configured=True, ok=False, error=str(e), sync=T['bambuddy'])


BB_COLORS = [('Wit', 'FFFFFF'), ('Zwart', '161616'), ('Grijs', '808080'), ('Lichtgrijs', 'C0C0C0'), ('Rood', 'D01F1F'), ('Oranje', 'F98C36'), ('Geel', 'F5D000'), ('Groen', '2EA043'),
             ('Lichtgroen', '8BD450'), ('Blauw', '1F4FD8'), ('Lichtblauw', '5CC8FF'), ('Turquoise', '00B5AD'), ('Paars', '7B3FBF'), ('Roze', 'FF69B4'), ('Bruin', '7B4A1E'),
             ('Beige', 'E6D3A3'), ('Goud', 'C9A227'), ('Zilver', 'B0B7BF')]


def bb_color_name(hx):
    """Dichtstbijzijnde kleurnaam (Nederlands) bij een kleurcode: 'F98C36' wordt 'Oranje'. Handig voor kinderen die geen hexcode lezen."""
    r, g_, b = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
    return min(BB_COLORS, key=lambda c: (2 * (r - int(c[1][0:2], 16)) ** 2 + 4 * (g_ - int(c[1][2:4], 16)) ** 2 + 3 * (b - int(c[1][4:6], 16)) ** 2))[0]


def bb_tray(t, where):
    """Een AMS-slot of externe spoel uit de printerstatus: alleen als er echt een spoel met een kleur in zit."""
    if not isinstance(t, dict) or t.get('exists') is False:
        return None
    c = re.sub(r'[^0-9A-Fa-f]', '', str(t.get('tray_color') or ''))
    if len(c) not in (6, 8) or (len(c) == 8 and c[6:].upper() == '00'):  # geen kleur, of volledig doorzichtig = leeg slot
        return None
    c = c[:6].upper()
    mat = str(t.get('tray_type') or '').strip()
    if not mat:
        return None
    rem = t.get('remain')
    return dict(hex='#' + c, name=bb_color_name(c), material=mat, brand=str(t.get('tray_sub_brands') or '').strip(), slot=where,
                remain=rem if isinstance(rem, (int, float)) and 0 <= rem <= 100 else None)  # -1 = onbekend (spoel zonder RFID)


def bb_slots(status):
    """Alle spoelen die nu in een printer zitten, uit GET /printers/{id}/status (AMS-eenheden en de externe spoel)."""
    out = []
    for u in (status.get('ams') or []) if isinstance(status, dict) else []:
        if not isinstance(u, dict):
            continue
        n = u.get('id')
        for t in u.get('tray') or []:
            x = bb_tray(t, f"AMS {n + 1 if isinstance(n, int) and n < 128 else 'HT'} slot {(t.get('id') + 1) if isinstance(t, dict) and isinstance(t.get('id'), int) else '?'}")
            if x:
                out.append(x)
    for k in ('vt_tray', 'external_spool'):
        v = status.get(k) if isinstance(status, dict) else None
        for t in (v if isinstance(v, list) else [v]):
            x = bb_tray(t, 'Externe spoel')
            if x:
                out.append(x)
    return out


@app.get('/api/bambuddy/colors')
def bambuddy_colors():
    """De kleuren die nu echt in de printers van Bambuddy zitten (AMS en externe spoel), per printer en samengevoegd. Leest alleen, start niets."""
    if not (CFG['bambuddy_url'] and CFG['bambuddy_key']):
        return jsonify(configured=False, printers=[], colors=[])
    want = request.args.get('printer', type=int)
    try:
        ps = [p for p in bb_items(bb_call('/printers/', timeout=5), 'items', 'printers') if isinstance(p, dict) and p.get('id') is not None and p.get('is_active', True)]
        out, merged = [], {}
        for p in ps:
            if want is not None and p['id'] != want:
                continue
            try:
                slots = bb_slots(bb_call(f"/printers/{p['id']}/status", timeout=8))
                err = None
            except ValueError as e:  # printer offline: de rest blijft werken
                slots, err = [], str(e)
            name = str(p.get('name') or p.get('serial_number') or f"Printer {p['id']}")
            out.append(dict(id=p['id'], name=name, model=p.get('model') or '', slots=slots, error=err))
            for x in slots:
                m = merged.setdefault((x['hex'], x['material']), dict(hex=x['hex'], name=x['name'], material=x['material'], brand=x['brand'], printers=[], remain=None))
                if name not in m['printers']:
                    m['printers'].append(name)
                if x['remain'] is not None:
                    m['remain'] = x['remain'] if m['remain'] is None else max(m['remain'], x['remain'])
        return jsonify(configured=True, ok=True, printers=out, colors=sorted(merged.values(), key=lambda c: (c['material'], c['name'])))
    except ValueError as e:
        return jsonify(configured=True, ok=False, error=str(e), printers=[], colors=[])


@app.post('/api/models/<int:mid>/bambuddy')
def bambuddy_send(mid):
    """Model naar Bambuddy sturen: in de bibliotheek zetten of ook in de wachtrij. Nooit meteen printen: starten doe je in Bambuddy."""
    r = one(mid)
    j = request.json or {}
    action = j.get('action')
    if action not in ('library', 'queue'):
        return jsonify(error='Onbekende actie'), 400
    if r['ext'] not in BB_EXTS:
        return jsonify(error=f'Bambuddy neemt alleen {", ".join("." + e for e in BB_EXTS)} aan'), 400
    if r['size'] > MAX_MB * 2 ** 20:
        return jsonify(error=f'Bestand groter dan {MAX_MB} MB (MAX_FILE_MB)'), 413
    try:
        pid = int(j['printer_id']) if action == 'queue' else None
    except (KeyError, TypeError, ValueError):
        return jsonify(error='Kies eerst een printer voor de wachtrij'), 400
    name = (posixpath.basename(r['member']) if r['container'] else f"{r['name']}.{r['ext']}")
    try:
        with materialize(r) as src:
            if action == 'queue' and not bb_sliced(src, r['ext']):  # vooraf: niets uploaden dat toch geweigerd wordt
                return jsonify(error='Bambuddy zet alleen geslicede bestanden (.gcode of .gcode.3mf) in de wachtrij. Dit bestand is niet gesliced: slice het eerst in je slicer en stuur dan dat bestand. In de bibliotheek zetten kan wel.'), 400
            up = bb_upload(src, name)
        fid = up.get('id')
        if fid is None:
            raise ValueError('Bambuddy gaf geen bestands-id terug')
        q = qstatus = None
        if action == 'queue':
            res = bb_call('/library/files/add-to-queue', 'POST', body=dict(file_ids=[fid], printer_id=pid), timeout=30)
            if res.get('errors'):
                raise ValueError('Bambuddy kon het niet in de wachtrij zetten: ' + str((res['errors'][0] or {}).get('error') or res['errors'][0]))
            added = res.get('added') or []
            if not added:  # niets aangemaakt en ook geen fout: nooit stilletjes "gelukt" melden
                raise ValueError('Bambuddy heeft niets in de wachtrij gezet. Antwoord van Bambuddy: ' + json.dumps(res, ensure_ascii=False)[:200])
            q = added[0].get('queue_item_id')
            try:  # controleren dat het item echt in de wachtrij staat en wat de status is
                item = bb_call(f'/queue/{q}', timeout=10)
                qstatus = str(item.get('status') or '') or None
            except ValueError as e:
                raise ValueError(f'Bambuddy meldt dat het in de wachtrij staat (#{q}), maar het item is daar niet terug te vinden: {e}')
    except ValueError as e:
        return jsonify(error=str(e)), 502
    except OSError as e:
        return jsonify(error=f'Bestand lezen mislukt: {e.strerror or e}'), 500
    hist('Bambuddy', f"{name} naar Bambuddy gestuurd ({'in de wachtrij' if action == 'queue' else 'in de bibliotheek'})", mid)
    return jsonify(ok=True, file_id=fid, queue_item_id=q, queue_status=qstatus, duplicate=up.get('duplicate_of') is not None)


def bb_norm(n):
    n = str(n or '').strip().lower()
    for ext in ('.gcode.3mf', '.3mf', '.gcode', '.stl'):
        if n.endswith(ext):
            n = n[:-len(ext)]
    return re.sub(r'\s+', ' ', n).strip()


def bb_ts(v):
    if not v:
        return None
    try:
        import datetime
        d = datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)).timestamp()  # Bambuddy rekent in UTC
    except ValueError:
        return None


BB_LOCK = threading.Lock()


def bambuddy_sync():
    """Printgeschiedenis uit Bambuddy overnemen in het printlogboek. Een regel wordt gekoppeld aan het model met dezelfde naam (alleen als dat
    eenduidig is); wat niet past blijft in Bambuddy staan en wordt bij de volgende keer opnieuw geprobeerd. Elke regel komt maar één keer
    binnen, ook als je hem hier later verwijdert."""
    if not (CFG['bambuddy_url'] and CFG['bambuddy_key']):
        raise ValueError('Bambuddy is niet ingesteld (Instellingen → Algemeen)')
    if not BB_LOCK.acquire(blocking=False):
        raise ValueError('Er loopt al een synchronisatie')
    try:
        items, off = [], 0
        while off < 5000:
            page = bb_call('/print-log/', params=dict(limit=100, offset=off), timeout=30)
            got = bb_items(page, 'items')
            items += got
            off += 100
            if len(got) < 100 or off >= int((page or {}).get('total') or 0):
                break
        with db() as c:
            seen = {r[0] for r in c.execute('SELECT bb_id FROM bb_imported')}
            idx = {}
            for m in c.execute('SELECT id, name, display_name, ext FROM models'):
                for n in {bb_norm(m['name']), bb_norm(m['display_name'])} - {''}:
                    idx.setdefault(n, []).append((m['id'], m['ext']))
        added, known, unmatched, other, statuses = 0, 0, [], 0, {}
        new = []
        for it in items:
            bid = it.get('id')
            if bid is None or bid in seen:
                known += 1
                continue
            st = str(it.get('status') or '').lower()
            statuses[st] = statuses.get(st, 0) + 1
            res = 'ok' if any(k in st for k in ('complet', 'success', 'finish')) else 'failed' if any(k in st for k in ('fail', 'error')) else None
            if res is None:  # bezig of afgebroken: pas meenemen als het een duidelijke uitkomst heeft
                other += 1
                continue
            cand = idx.get(bb_norm(it.get('print_name')), [])
            if len(cand) > 1:
                cand = [x for x in cand if x[1] == '3mf']
            if len(cand) != 1:
                unmatched.append(str(it.get('print_name') or '?'))
                continue
            note = 'Bambuddy' + (f": {it['failure_reason']}" if res == 'failed' and it.get('failure_reason') else '')
            new.append((bid, cand[0][0], bb_ts(it.get('completed_at')) or bb_ts(it.get('started_at')) or bb_ts(it.get('created_at')) or time.time(), res,
                        it.get('printer_name'), it.get('filament_used_grams'), note[:1000]))
        with db() as c:
            for bid, mid, ts, res, pr, grams, note in new:
                c.execute('INSERT OR IGNORE INTO bb_imported(bb_id) VALUES(?)', (bid,))
                c.execute('INSERT INTO prints(model_id,ts,result,printer,grams,notes) VALUES(?,?,?,?,?,?)', (mid, ts, res, pr, grams, note))
                if res == 'ok':
                    c.execute("UPDATE models SET printed='printed' WHERE id=?", (mid,))
                added += 1
        if added:
            hist('Bambuddy', f'{added} prints uit Bambuddy overgenomen in het printlogboek')
        T['bambuddy'] = dict(last=time.time(), error=None,
                             result=dict(added=added, known=known, unmatched=len(unmatched), other=other, examples=sorted(set(unmatched))[:8], statuses=statuses))
        bump()
        return T['bambuddy']
    except ValueError as e:
        T['bambuddy'] = dict(last=time.time(), error=str(e), result=None)
        raise
    finally:
        BB_LOCK.release()


@app.post('/api/bambuddy/sync')
def bambuddy_sync_now():
    try:
        return jsonify(bambuddy_sync())
    except ValueError as e:
        return jsonify(error=str(e)), 502


# ---------------------------------------------------------------- Spoolman + printlogboek
def spoolman_call(path, method='GET', body=None, timeout=5):
    base = CFG['spoolman_url'].rstrip('/')
    if not base:
        raise ValueError('Spoolman is niet ingesteld (Instellingen → Algemeen)')
    rq = urllib.request.Request(base + '/api/v1' + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as x:
            return json.loads(x.read() or b'null')
    except urllib.error.HTTPError as e:
        raise ValueError(f"Spoolman antwoordde met fout {e.code}: {e.read()[:200].decode('utf-8', 'ignore')}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ValueError(f"Spoolman is niet bereikbaar op {base}: {getattr(e, 'reason', e)}")


@app.get('/api/spoolman/status')
def spoolman_status():
    if not CFG['spoolman_url']:
        return jsonify(configured=False)
    try:
        return jsonify(configured=True, ok=True, version=spoolman_call('/info', timeout=3).get('version'))
    except ValueError as e:
        return jsonify(configured=True, ok=False, error=str(e))


@app.get('/api/spoolman/spools')
def spoolman_spools():
    try:
        spools = spoolman_call('/spool')
    except ValueError as e:
        return jsonify(error=str(e)), 502
    out = []
    for s in spools:
        if s.get('archived'):
            continue
        f = s.get('filament') or {}
        label = ' '.join(x for x in ((f.get('vendor') or {}).get('name'), f.get('name')) if x) or f"Spoel {s['id']}"
        out.append(dict(id=s['id'], label=label, material=f.get('material') or '', color=f.get('color_hex') or '', remaining=s.get('remaining_weight')))
    return jsonify(sorted(out, key=lambda x: x['label'].lower()))


@app.get('/api/models/<int:mid>/prints')
def prints_get(mid):
    one(mid)
    with db() as c:
        return jsonify([dict(r) for r in c.execute('SELECT * FROM prints WHERE model_id=? ORDER BY ts DESC, id DESC', (mid,))])


@app.post('/api/models/<int:mid>/prints')
def prints_add(mid):
    one(mid)
    j = request.json or {}
    if j.get('result') not in ('ok', 'failed'):
        return jsonify(error='Kies of de print gelukt of mislukt is'), 400
    try:
        grams = float(j['grams']) if j.get('grams') not in (None, '') else None
        ts = float(j['ts']) if j.get('ts') else time.time()
        plate = int(j['plate']) if j.get('plate') not in (None, '') else None
        pid = int(j['printer_id']) if j.get('printer_id') not in (None, '') else None
        spool_id = int(j['spool_id']) if j.get('spool_id') not in (None, '') else None
    except (TypeError, ValueError):
        return jsonify(error='Ongeldige waarde (gewicht, datum, plaat, printer of spoel)'), 400
    if grams is not None and not 0 <= grams <= 100000:
        return jsonify(error='Het filamentverbruik moet tussen 0 en 100000 gram liggen'), 400
    printer = None
    if pid is not None:
        with db() as c:
            pr = c.execute('SELECT name FROM printers WHERE id=?', (pid,)).fetchone()
        printer = pr['name'] if pr else None
    spool = None
    if j.get('deduct') and spool_id is not None and grams:  # verbruik aftrekken in Spoolman: eerst dat, pas daarna loggen
        try:
            spoolman_call(f'/spool/{spool_id}/use', 'PUT', {'use_weight': grams})
        except ValueError as e:
            return jsonify(error=f'Niets opgeslagen. {e}'), 502
        spool = (str(j.get('spool') or '') or f'spoel {spool_id}')[:100]
    else:
        spool_id = None
    with db() as c:
        new = c.execute('INSERT INTO prints(model_id,ts,result,printer_id,printer,plate,grams,spool_id,spool,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (mid, ts, j['result'], pid if printer else None, printer, plate, grams, spool_id, spool, (str(j.get('notes') or '').strip()[:1000]) or None)).lastrowid
        if j['result'] == 'ok':
            c.execute("UPDATE models SET printed='printed' WHERE id=?", (mid,))
    bump()
    return jsonify(id=new, deducted=spool is not None)


@app.delete('/api/prints/<int:pid>')
def prints_del(pid):
    with db() as c:
        c.execute('DELETE FROM prints WHERE id=?', (pid,))
    bump()
    return jsonify(ok=True)


@app.get('/api/fs')
def fs():
    p = clean_path(request.args.get('path')) or ('' if os.name == 'nt' else '/')
    if not p:  # Windows: lijst met stations, gekoppelde netwerkschijven met hun UNC-pad
        return jsonify(path='', parent=None, unc=None, dirs=[dict(name=d, path=d, unc=unc_of(d)) for d in windows_drives()])
    if os.name == 'nt' and unc_server_only(p):
        return jsonify(error='Geef een volledig netwerkpad op: server én share, bijvoorbeeld \\\\nas\\modellen'), 400
    p = os.path.abspath(p)
    try:
        skip = ('@', '#', '$') if request.args.get('hidden') == '1' else ('.', '@', '#', '$')  # hidden=1: ook mappen met een punt (bijv. .back-ups)
        dirs = sorted(e.name for e in os.scandir(p) if e.is_dir() and not e.name.startswith(skip))
    except OSError as e:
        return jsonify(error=e.strerror or 'Map niet toegankelijk'), 400
    par = os.path.dirname(p)
    return jsonify(path=p, parent=(('' if os.name == 'nt' else None) if par == p else par), unc=unc_of(p),
                   dirs=[dict(name=n, path=os.path.join(p, n)) for n in dirs])


def ms_settings():
    return dict(ms_enabled=CFG['ms_enabled'] == '1', ms_tenant=CFG['ms_tenant'], ms_client_id=CFG['ms_client_id'], ms_secret_set=bool(CFG['ms_client_secret']), ms_admin_group=CFG['ms_admin_group'],
                ms_only=CFG['ms_only'] == '1', ms_klas=CFG['ms_klas'] == '1', public_url=CFG['public_url'], ms_redirect=ms_redirect(), ms_ready=ms_ready())


@app.get('/api/settings')
def settings_get():
    return jsonify(scan_interval=int(CFG['scan_interval']), min_age=int(CFG['min_age']), extensions=CFG['extensions'],
                   thumb_size=int(CFG['thumb_size']), big_mb=int(CFG['big_mb']), student_quota_mb=int(CFG['student_quota_mb']), default_share=CFG['default_share'] == '1', recent_days=int(CFG['recent_days']), thumb_source=CFG['thumb_source'], thumb_delay=int(CFG['thumb_delay']), spoolman_url=CFG['spoolman_url'], slicer=CFG['slicer'], backup_keep=int(CFG['backup_keep']), backup_thumbs=CFG['backup_thumbs'] == '1', backup_dir=CFG['backup_dir'], backup_dir_now=backup_dir(), bambuddy_url=CFG['bambuddy_url'], bambuddy_key_set=bool(CFG['bambuddy_key']), backup_last=T['backup']['last'], backup_error=T['backup'].get('error'), zip_support=CFG['zip_support'] == '1', api_key=CFG['api_key'], **ms_settings(),
                   host=HOST, port=PORT, version=VERSION)


def ms_save(j):
    """Instellingen voor Microsoft-login bewaren; geeft een foutmelding of None."""
    for k in ('ms_enabled', 'ms_only', 'ms_klas'):
        if k in j:
            put(k, '1' if j[k] else '0')
    for k, n in (('ms_tenant', 120), ('ms_client_id', 80), ('ms_admin_group', 80)):
        if k in j:
            put(k, str(j[k] or '').strip()[:n])
    if 'ms_tenant' in j and CFG['ms_tenant'] and not INT.valid_tenant(CFG['ms_tenant']):
        return 'Vul bij Tenant-ID het ID (een GUID) of de domeinnaam van je Microsoft-omgeving in'
    if 'public_url' in j:
        u = str(j['public_url'] or '').strip()
        if u and not u.lower().startswith(('http://', 'https://')):
            return 'Het publieke adres moet met http:// of https:// beginnen'
        if u:
            pu = urllib.parse.urlsplit(u)
            u = f'{pu.scheme.lower()}://{pu.netloc}'  # alleen het basisadres: een pad (bijv. /api/ms/callback) vallen we weg
        put('public_url', u)
    for k, sk in (('ms_client_secret', 'ms_secret_clear'),):
        if j.get(sk):
            put(k, '')
        elif str(j.get(k) or '').strip():  # leeg laten = de opgeslagen waarde behouden
            put(k, str(j[k]).strip())
    if CFG['ms_enabled'] == '1' and not (INT.valid_tenant(CFG['ms_tenant']) and CFG['ms_client_id'] and CFG['ms_client_secret']):
        put('ms_enabled', '0')
        return 'Vul Tenant-ID, Client-ID en Clientgeheim in voordat je inloggen met Microsoft aanzet'
    return None


@app.post('/api/settings')
def settings_post():
    j, old = request.json or {}, (CFG['thumb_size'], CFG['thumb_source'])
    try:
        for k, lo, hi in (('scan_interval', 1, 1440), ('min_age', 0, 3600), ('thumb_size', 128, 1024), ('big_mb', 1, 100000), ('recent_days', 1, 3650), ('thumb_delay', 0, 600), ('backup_keep', 1, 60), ('student_quota_mb', 0, 1000000)):
            if k in j:
                put(k, min(hi, max(lo, int(j[k]))))
    except (TypeError, ValueError):
        return jsonify(error='Ongeldige waarde'), 400
    if 'slicer' in j:
        if j['slicer'] not in SLICERS:
            return jsonify(error='Onbekende slicer'), 400
        put('slicer', j['slicer'])
    if 'spoolman_url' in j:
        u = (j['spoolman_url'] or '').strip().rstrip('/')
        if u and not u.lower().startswith(('http://', 'https://')):
            return jsonify(error='Het adres van Spoolman moet met http:// of https:// beginnen'), 400
        put('spoolman_url', u)
    if 'bambuddy_url' in j:
        u = (j['bambuddy_url'] or '').strip().rstrip('/')
        if u and not u.lower().startswith(('http://', 'https://')):
            return jsonify(error='Het adres van Bambuddy moet met http:// of https:// beginnen'), 400
        put('bambuddy_url', u)
    if j.get('bambuddy_key_clear'):
        put('bambuddy_key', '')
    elif str(j.get('bambuddy_key') or '').strip():  # leeg laten = de opgeslagen sleutel behouden
        put('bambuddy_key', str(j['bambuddy_key']).strip())
    err = ms_save(j)
    if err:
        return jsonify(error=err), 400
    if 'backup_thumbs' in j:
        put('backup_thumbs', '1' if j['backup_thumbs'] else '0')
    if 'default_share' in j:
        put('default_share', '1' if j['default_share'] else '0')
    if 'backup_dir' in j:
        p = str(j['backup_dir'] or '').strip()
        if p != CFG['backup_dir']:
            err = check_backup_dir(p, create=True) if p else ''
            if err:
                return jsonify(error=err), 400
            put('backup_dir', p)
            threading.Thread(target=backup, daemon=True).start()  # meteen een back-up: zo zie je direct dat de map werkt
    if 'zip_support' in j and ('1' if j['zip_support'] else '0') != CFG['zip_support']:
        put('zip_support', '1' if j['zip_support'] else '0')
        threading.Thread(target=scan, daemon=True).start()
    if j.get('thumb_source') in ('embedded', 'render'):
        put('thumb_source', j['thumb_source'])
    if (CFG['thumb_size'], CFG['thumb_source']) != old:
        log.info('Thumbnail-instelling gewijzigd (grootte %s px, bron %s): alle thumbnails worden opnieuw gemaakt', CFG['thumb_size'], CFG['thumb_source'])
        rebuild_thumbs()
    if 'extensions' in j:
        put('extensions', ','.join(x.strip().lower().lstrip('.') for x in str(j['extensions']).split(',') if x.strip()))
    if j.get('regen_key'):
        put('api_key', secrets.token_hex(16))
    return jsonify(ok=True)


@app.get('/api/queue')
def queue():
    with db() as c:
        items = [dict(r) for r in c.execute("SELECT id, name, ext, added_at AS added FROM models WHERE thumb_status='pending' ORDER BY id LIMIT 100")]
        n = c.execute("SELECT COUNT(*) FROM models WHERE thumb_status='pending'").fetchone()[0]
        f = c.execute("SELECT COUNT(*) FROM models WHERE thumb_status='failed'").fetchone()[0]
    cur = dict(CUR)
    return jsonify(current=dict(name=cur['name'], secs=int(time.time() - cur['started'])) if cur else None,
                   pending=n, failed=f, paused=CFG['thumb_paused'] == '1', items=[i for i in items if i['id'] != cur.get('id')])


@app.post('/api/queue/pause')
def queue_pause():
    put('thumb_paused', '1' if (request.json or {}).get('paused') else '0')
    bump()
    return jsonify(ok=True)


@app.get('/api/history')
def history():
    with db() as c:
        return jsonify([dict(r) for r in c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 300')])


@app.get('/api/wanted')
def wanted():
    with db() as c:
        items = [dict(id=r['id'], name=r['name'], ext=r['ext'], path=r['path'], status=r['thumb_status'], error=r['thumb_error'] or 'Onbekende fout')
                 for r in c.execute("SELECT * FROM models WHERE thumb_status='failed' ORDER BY name")]
        n = c.execute("SELECT COUNT(*) FROM models WHERE thumb_status='unsupported'").fetchone()[0]
    return jsonify(items=items, unsupported=n)


@app.post('/api/wanted/retry')
def wanted_retry():
    ids = (request.json or {}).get('ids')
    with db() as c:
        if ids:
            c.executemany("UPDATE models SET thumb_status='pending', thumb_error=NULL WHERE thumb_status='failed' AND id=?", [(int(i),) for i in ids])
        else:
            c.execute("UPDATE models SET thumb_status='pending', thumb_error=NULL WHERE thumb_status='failed'")
    bump()
    return jsonify(ok=True)


@app.get('/api/tasks')
def tasks():
    iv = max(1, int(CFG['scan_interval']))
    return jsonify([
        dict(key='scan', name='Bibliotheek scannen', interval=f'{iv} min', running=T['scan']['running'], last=T['scan']['last'],
             next=NEXT['scan'] or None, dur=T['scan']['dur'],
             desc='Zoekt nieuwe, gewijzigde, verplaatste en verwijderde bestanden in alle root folders (naast de live bestandswachter).'),
        dict(key='rebuild', name='Alle thumbnails opnieuw maken', interval='handmatig', running=False, last=T['rebuild']['last'],
             next=None, dur=None, desc='Zet alle modellen terug in de thumbnail-wachtrij (gebeurt ook automatisch bij een andere thumbnail-grootte).'),
        dict(key='backup', name='Database back-up', interval=f"24 uur (bewaart {CFG['backup_keep']})", running=False, last=T['backup']['last'], next=NEXT['backup'],
             dur=T['backup']['dur'], dir=backup_dir(), error=T['backup'].get('error'),
             desc='Kopie van library.db (en optioneel de thumbnails) in de back-upmap. De map stel je in bij Instellingen → Mediabeheer. Terugzetten: stop de app en kopieer een back-up terug als library.db.'),
        dict(key='thumbcheck', name='Thumbnails controleren', interval='bij opstarten en na elke scan', running=False, last=T['thumbcheck']['last'], next=None, dur=None,
             desc='Controleert of elke thumbnail bestaat en bij het juiste model hoort (bijv. na het terugzetten van een back-up) en laat ontbrekende of verkeerde thumbnails opnieuw maken.')])


@app.post('/api/tasks/<key>/run')
def task_run(key):
    if key == 'scan':
        threading.Thread(target=scan, daemon=True).start()
    elif key == 'rebuild':
        rebuild_thumbs()
    elif key == 'backup':
        threading.Thread(target=backup, daemon=True).start()
    elif key == 'thumbcheck':
        threading.Thread(target=lambda: check_thumbs(True), daemon=True).start()
    else:
        abort(404)
    return jsonify(ok=True)


@app.get('/api/logs')
def logs():
    order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    lvl = order.index(request.args.get('level', 'INFO').upper()) if request.args.get('level', 'INFO').upper() in order else 1
    return jsonify([l for l in reversed(LOGS) if order.index(l['level']) >= lvl][:500])


@app.delete('/api/logs')
def logs_clear():
    LOGS.clear()
    return jsonify(ok=True)


@app.get('/api/status')
def status():
    roots, health = roots_info(), []
    with db() as c:
        counts = {k: c.execute(q).fetchone()[0] for k, q in dict(
            models='SELECT COUNT(*) FROM models', categories='SELECT COUNT(*) FROM categories',
            failed="SELECT COUNT(*) FROM models WHERE thumb_status='failed'",
            unsupported="SELECT COUNT(*) FROM models WHERE thumb_status='unsupported'").items()}
    if not roots:
        health.append(dict(level='warning', msg='Geen root folder ingesteld. Voeg er een toe onder Instellingen → Mediabeheer (of zet MODELS_DIR).'))
    if os.name != 'nt' and any(r['path'] == '/' for r in roots):
        health.append(dict(level='error', msg='Een root folder is de hoofdmap (/) van de container: daar worden ook systeembestanden gescand. Verwijder deze root en voeg je modelmap toe (bijvoorbeeld /models).'))
    for a in roots:
        for b in roots:
            if a['path'] != b['path'] and _under(a['path'], b['path']):
                health.append(dict(level='warning', msg=f"Root folders overlappen: {a['path']} ligt in {b['path']}. Bestanden worden maar één keer opgenomen; verwijder een van beide onder Instellingen → Mediabeheer."))
    for r in roots:
        if not r['ok']:
            health.append(dict(level='error', msg=f"Root folder niet bereikbaar: {r['path']} (mount offline of verkeerd pad?)"))
        elif not r['writable']:
            health.append(dict(level='info', msg=f"Root folder is alleen-lezen: {r['path']} (bestanden hernoemen is niet mogelijk)"))
        elif r['watch'] and not r['live']:
            health.append(dict(level='info', msg=f"Geen live bestandswachter voor {r['path']}; er wordt gescand elke {CFG['scan_interval']} min."))
    if CFG['spoolman_url']:
        try:
            spoolman_call('/info', timeout=2)
        except ValueError as e:
            health.append(dict(level='warning', msg=str(e)))
    net = config_on_network()
    if net:
        health.append(dict(level='warning', msg=f'De config-map met de database ({CONFIG}) staat op een netwerkshare ({net}). SQLite is daar onbetrouwbaar en kan beschadigd raken: gebruik lokale opslag.'))
    if not AUTH_ON[0]:
        health.append(dict(level='warning', msg='Er zijn geen accounts: iedereen op je netwerk kan bestanden zien en hernoemen. Maak een beheerdersaccount aan onder Instellingen → Gebruikers.'))
    if counts['failed']:
        health.append(dict(level='warning', msg=f"{counts['failed']} thumbnail(s) mislukt, zie Gewenst."))
    if counts['unsupported']:
        health.append(dict(level='info', msg=f"{counts['unsupported']} model(len) in een formaat zonder preview-ondersteuning."))
    return jsonify(version=VERSION, python=platform.python_version(), platform=platform.platform(), uptime=time.time() - START,
                   config=CONFIG, db_size=os.path.getsize(DB), roots=roots, health=health, **counts)


# ---------------------------------------------------------------- opstarten
def main():
    t_start = time.time()
    init()
    try:
        migrate_folder_rules()
    except Exception as e:  # een extra: mag het opstarten nooit stoppen
        log.warning('Mapregels aanmaken mislukt: %s', e)
    log.info('Database gereed (%.1fs)', time.time() - t_start)
    shutil.rmtree(os.path.join(CONFIG, 'tmp'), ignore_errors=True)
    shutil.rmtree(os.path.join(CONFIG, 'open'), ignore_errors=True)
    for d in filter(None, (x.strip() for x in os.environ.get('MODELS_DIR', '').split(','))):
        with db() as c:
            c.execute('INSERT OR IGNORE INTO roots(path) VALUES(?)', (os.path.normpath(d),))
            if os.environ.get('ALLOW_ORGANIZE') == '1':
                c.execute('UPDATE roots SET allow_write=1 WHERE path=?', (os.path.normpath(d),))
    bootstrap_env_admin()
    if not CFG['api_key']:
        put('api_key', secrets.token_hex(16))
    with socket.socket() as sk:
        if sk.connect_ex(('127.0.0.1', PORT)) == 0:
            sys.exit(f'Poort {PORT} is al in gebruik. Kies een andere met de omgevingsvariabele PORT.')
    log.info('Modelarr %s start op %s:%s (config: %s)', VERSION, HOST, PORT, CONFIG)
    net = config_on_network()
    if net:
        log.warning('De config-map staat op een netwerkshare (%s): SQLite is daar onbetrouwbaar. Gebruik lokale opslag voor %s', net, CONFIG)
    nw = max(1, min(8, int(os.environ.get('THUMB_WORKERS', '1') or 1)))  # meer workers = sneller op een NAS met meerdere cores (let op het geheugen)
    for i in range(nw):
        threading.Thread(target=worker, args=(i == 0,), daemon=True).start()
    threading.Thread(target=scheduler, daemon=True).start()
    if nw > 1:
        log.info('%d thumbnail-workers actief', nw)
    sync_watchers()
    log.info('Webserver start op poort %s (%.1fs na het opstarten)', PORT, time.time() - t_start)
    if os.environ.get('OPEN_BROWSER') == '1':  # handig op Windows
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    from waitress import serve
    serve(app, host=HOST, port=PORT, threads=8, ident='modelarr')


if __name__ == '__main__':
    main()
