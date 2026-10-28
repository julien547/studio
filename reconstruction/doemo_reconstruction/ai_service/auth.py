"""Short lived Ed25519 service tokens. Private signing key stays on OVH."""
import base64
import json
import time
from cryptography.hazmat.primitives.serialization import load_pem_private_key,load_pem_public_key


def b64(data):return base64.urlsafe_b64encode(data).decode().rstrip('=')
def unb64(data):return base64.urlsafe_b64decode(data+'='*(-len(data)%4))


def issue(private_pem, audience, scope, now=None, ttl=120):
    if not 1<=ttl<=300:raise ValueError('Invalid token lifetime')
    now=int(time.time() if now is None else now)
    payload=b64(json.dumps({'aud':audience,'scope':scope,'iat':now,'exp':now+ttl},separators=(',',':')).encode())
    key=load_pem_private_key(private_pem,password=None)
    return payload+'.'+b64(key.sign(payload.encode()))


def verify(public_pem, token, audience, scope, now=None):
    try:
        if not isinstance(token,str) or len(token)>4096:raise ValueError()
        payload,signature=token.split('.')
        load_pem_public_key(public_pem).verify(unb64(signature),payload.encode())
        claims=json.loads(unb64(payload));now=time.time() if now is None else now
        if claims['aud']!=audience or claims['scope']!=scope:raise ValueError()
        if type(claims['iat']) is not int or type(claims['exp']) is not int:raise ValueError()
        if not 0<claims['exp']-claims['iat']<=300 or claims['iat']>now+5 or claims['exp']<=now:raise ValueError()
        return claims
    except Exception as error:
        raise ValueError('Jeton absent, expiré ou invalide') from error
