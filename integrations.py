"""Microsoft (Entra ID) inloggen. Geen Flask hierin: alles is los te testen.
Netwerkverkeer gaat via http(); tests vervangen die functie."""
import base64, hashlib, json, re, secrets, time, urllib.error, urllib.parse, urllib.request

LOGIN = 'https://login.microsoftonline.com/'
GRAPH = 'https://graph.microsoft.com/v1.0'
GUID = re.compile(r'^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')


class AuthError(Exception):
    pass


def http(method, url, data=None, headers=None, body=None, timeout=20):
    """(status, JSON of tekst). data = formulier, body = JSON."""
    h = dict(headers or {})
    raw = None
    if data is not None:
        raw = urllib.parse.urlencode(data).encode()
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        raw = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            st, txt = r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        st, txt = e.code, e.read().decode('utf-8', 'replace')
    except (urllib.error.URLError, OSError) as e:
        raise AuthError(f'Geen verbinding met Microsoft: {getattr(e, "reason", e)}')
    try:
        return st, json.loads(txt) if txt else {}
    except ValueError:
        return st, txt


def _err(j):
    if isinstance(j, dict):
        e = j.get('error')
        if isinstance(e, dict):
            return e.get('message') or e.get('code') or ''
        return j.get('error_description') or e or ''
    return str(j)[:200]


def valid_tenant(t):
    t = (t or '').strip()
    return bool(GUID.match(t) or re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', t))


# ------------------------------------------------------------------ inloggen (OpenID Connect, authorization code + PKCE)
def pkce():
    v = secrets.token_urlsafe(48)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode()


SCOPE = 'openid profile email User.Read'


def auth_url(tenant, client_id, redirect, state, nonce, challenge, scope=SCOPE):
    q = dict(client_id=client_id, response_type='code', redirect_uri=redirect, response_mode='query', scope=scope,
             state=state, nonce=nonce, code_challenge=challenge, code_challenge_method='S256', prompt='select_account')
    return f'{LOGIN}{tenant}/oauth2/v2.0/authorize?' + urllib.parse.urlencode(q)


def exchange(tenant, client_id, secret, redirect, code, verifier, scope=SCOPE):
    st, j = http('POST', f'{LOGIN}{tenant}/oauth2/v2.0/token', data=dict(client_id=client_id, client_secret=secret, grant_type='authorization_code',
                                                                          code=code, redirect_uri=redirect, code_verifier=verifier, scope=scope))
    if st != 200 or not isinstance(j, dict) or not j.get('id_token'):
        raise AuthError('Microsoft weigerde de inlog: ' + (_err(j) or f'status {st}'))
    return j


def jwt_claims(tok):
    try:
        p = tok.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4)))
    except Exception:
        raise AuthError('Ongeldig token van Microsoft')


def check_claims(c, tenant, client_id, nonce, now=None):
    """De id_token komt rechtstreeks van het token-endpoint over TLS (OIDC Core 3.1.3.7): de handtekening hoeft dan niet extra gecontroleerd te worden, de inhoud wel."""
    now = now or time.time()
    if c.get('aud') != client_id:
        raise AuthError('Token is niet voor deze applicatie bestemd')
    if not secrets.compare_digest(str(c.get('nonce') or ''), str(nonce or '')):
        raise AuthError('Ongeldige inlogpoging (nonce)')
    if float(c.get('exp') or 0) < now - 60:
        raise AuthError('Token is verlopen')
    iss = str(c.get('iss') or '')
    if not (iss.startswith(LOGIN) and iss.endswith('/v2.0')):
        raise AuthError('Onbekende uitgever van het token')
    if GUID.match(tenant) and str(c.get('tid') or '').lower() != tenant.lower():
        raise AuthError('Dit account hoort niet bij de ingestelde Microsoft-omgeving')
    if not c.get('oid') and not c.get('sub'):
        raise AuthError('Token bevat geen gebruiker')
    return c


def groups_for(claims, access_token=None):
    """Groep-ID's van de gebruiker: uit het token, of (bij meer dan 200 groepen) bij Microsoft Graph opgevraagd."""
    g = claims.get('groups')
    if isinstance(g, list) and not claims.get('hasgroups') and '_claim_names' not in claims:
        return [x.lower() for x in g]
    if access_token:
        st, j = http('POST', f'{GRAPH}/me/getMemberObjects', body=dict(securityEnabledOnly=False), headers={'Authorization': 'Bearer ' + access_token})
        if st == 200 and isinstance(j, dict):
            return [x.lower() for x in j.get('value', [])]
        raise AuthError('Groepen ophalen bij Microsoft mislukt: ' + (_err(j) or f'status {st}'))
    return [x.lower() for x in g] if isinstance(g, list) else []


def resolve_role(groups, admin_group, schools):
    """(rol, school_id) uit groepslidmaatschap, of None. schools: lijst met dicts (id, group_id = leerlingen, staff_group_id = medewerkers). Beheerder gaat voor medewerker, medewerker voor leerling."""
    gs = {x.lower() for x in groups}
    if admin_group and admin_group.strip().lower() in gs:
        return 'admin', None
    for s in schools:
        if s.get('staff_group_id') and s['staff_group_id'].strip().lower() in gs:
            return 'staff', s['id']
    for s in schools:
        if s.get('group_id') and s['group_id'].strip().lower() in gs:
            return 'student', s['id']
    return None


def department(access_token):
    """Het veld Afdeling (Department) van de gebruiker bij Microsoft Graph; None als het leeg is of niet op te halen is (dat blokkeert het inloggen nooit)."""
    if not access_token:
        return None
    try:
        st, j = http('GET', f'{GRAPH}/me?$select=department', headers={'Authorization': 'Bearer ' + access_token}, timeout=10)
    except AuthError:
        return None
    d = j.get('department') if st == 200 and isinstance(j, dict) else None
    return str(d).strip() or None if d else None
