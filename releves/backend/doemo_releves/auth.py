"""Optional standalone authentication; existing PHP session integration stays available."""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit
from pathlib import Path
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from .api import create_app
from .models import Model
from pydantic import Field


def password_hash(password, salt=None):
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Le mot de passe doit contenir entre 12 et 1024 caractères")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def password_matches(password, stored):
    try:
        return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)
    except (ValueError, TypeError):
        return False


class Credentials(Model):
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


def standalone(root=None, origin=None, dist=None):
    api = create_app(root)
    store = api.state.store
    origin = origin or os.environ.get('DOEMO_PUBLIC_ORIGIN', 'http://127.0.0.1:8082')
    parts = urlsplit(origin)
    local = parts.hostname in ('127.0.0.1', 'localhost', '::1')
    if parts.scheme != 'https' and not (local and parts.scheme == 'http'):
        raise ValueError('HTTPS obligatoire hors localhost')
    if parts.path or parts.query or parts.fragment or parts.username:
        raise ValueError('Origine sans chemin attendue')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    cookie = 'doemo_studio_session'

    @app.middleware('http')
    async def gate(request: Request, call_next):
        if request.headers.get('host') != parts.netloc:
            return JSONResponse({'detail':'Hôte refusé'}, status_code=400)
        if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') != origin:
            return JSONResponse({'detail':'Origine refusée'}, status_code=403)
        token = request.cookies.get(cookie, '')
        user = None
        if token:
            with store.connect() as c:
                user = c.execute('SELECT u.login,u.role FROM sessions s JOIN users u ON u.login=s.login WHERE s.token_hash=? AND s.expires>? AND u.active=1',
                                 (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        request.state.user = dict(user) if user else None
        if request.url.path.startswith('/api/'):
            if not user:
                return JSONResponse({'detail':'Connexion requise'}, status_code=401)
            headers = [(k,v) for k,v in request.scope['headers'] if k.lower() not in (b'x-doemo-user',b'x-doemo-role')]
            headers += [(b'x-doemo-user', user['login'].encode()), (b'x-doemo-role',user['role'].encode())]
            request.scope['headers'] = headers
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/session')
    def session(request: Request):
        if not request.state.user:
            raise HTTPException(401, 'Connexion requise')
        return request.state.user

    @app.post('/session')
    def login(data: Credentials, request: Request):
        # Persistent throttling per account (does not trust forwarded IP headers).
        key = hashlib.sha256(data.login.encode()).hexdigest()
        now = time.time()
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            limit = c.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
            if limit and limit['reset_at'] > now and limit['failures'] >= 8:
                raise HTTPException(429,'Trop de tentatives. Réessayer dans quinze minutes.')
            user = c.execute('SELECT * FROM users WHERE login=? AND active=1',(data.login,)).fetchone()
            # Same password KDF cost for nonexistent accounts.
            fallback = '00'*16 + ':' + '00'*64
            valid = password_matches(data.password, user['password_hash'] if user else fallback)
            if not user or not valid:
                count = limit['failures']+1 if limit and limit['reset_at']>now else 1
                reset = limit['reset_at'] if limit and limit['reset_at']>now else now+900
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(key,count,reset))
                return JSONResponse({'detail':'Identifiants incorrects'},status_code=401)
            c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
            c.execute('DELETE FROM sessions WHERE expires<?',(now,))
            token = secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),data.login,now+43200))
            c.execute('INSERT INTO events(actor,action,data) VALUES(?,?,?)',(data.login,'login','{}'))
        response = JSONResponse({'login':user['login'],'role':user['role']})
        response.set_cookie(cookie,token,secure=parts.scheme=='https',httponly=True,samesite='strict',max_age=43200,path='/')
        return response

    @app.post('/session/logout')
    def logout(request: Request):
        with store.connect() as c:
            c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(request.cookies.get(cookie,'').encode()).hexdigest(),))
            if request.state.user:
                c.execute('INSERT INTO events(actor,action,data) VALUES(?,?,?)',(request.state.user['login'],'logout','{}'))
        response = JSONResponse({'ok':True});response.delete_cookie(cookie,path='/')
        return response

    app.mount('/api',api)
    build = Path(dist or os.environ.get('DOEMO_RELEVES_DIST', Path(__file__).resolve().parents[2]/'dist'))

    @app.get('/')
    def home():
        return RedirectResponse('/releves/')

    @app.get('/releves/')
    def index():
        if not (build/'index.html').is_file():
            return HTMLResponse('Construire le frontend : npm --prefix releves/web run build',status_code=503)
        html = (build/'index.html').read_text().replace('</head>','<script>window.DOEMO_STANDALONE=true;</script></head>')
        return HTMLResponse(html)

    if (build/'assets').is_dir():
        app.mount('/releves/assets',StaticFiles(directory=build/'assets'),name='assets')
    return app


def main():
    import argparse
    import getpass
    from .store import Store
    parser=argparse.ArgumentParser(description='Créer un compte local DOEMO Studio')
    parser.add_argument('login');parser.add_argument('--role',choices=['admin','administration','dessinateur'],default='dessinateur')
    args=parser.parse_args()
    if not args.login.isascii() or not 1<=len(args.login)<=100:
        parser.error('Identifiant ASCII de 1 à 100 caractères requis')
    first=getpass.getpass('Mot de passe (12 caractères minimum) : ')
    if first != getpass.getpass('Confirmer : '):
        parser.error('Mots de passe différents')
    store=Store(os.environ.get('DOEMO_RELEVES_DATA','/var/lib/doemo-studio/releves'))
    with store.connect() as c:
        if c.execute('SELECT 1 FROM users WHERE login=?',(args.login,)).fetchone():
            parser.error('Ce compte existe déjà')
        c.execute('INSERT INTO users(login,password_hash,role) VALUES(?,?,?)',(args.login,password_hash(first),args.role))
    print('Compte créé.')

if __name__=='__main__':
    main()
