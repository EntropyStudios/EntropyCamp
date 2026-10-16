"""Linear public OAuth client (PKCE, read only). No shared WorkGraph credentials."""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie

from task_sync import write_json_atomic

LOCK=threading.RLock()
PENDING={}
CALLBACK='http://127.0.0.1:8765/api/wbs/oauth/callback'


class AuthError(ValueError): pass


class LinearAuth:
    def __init__(self,directory):
        self.path=directory/'linear-oauth.json'

    def _read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def status(self):
        with LOCK:
            c=self._read()
            return {'registered':bool(c.get('clientId')),'authenticated':bool(c.get('accessToken')),
                    'clientId':c.get('clientId',''),'user':c.get('user'), 'redirectUri':CALLBACK}

    def configure(self,body):
        client=str(body.get('clientId') or '').strip()
        if not client or len(client)>200 or not all(ch.isalnum() or ch in '-_' for ch in client):
            raise AuthError('请输入Linear OAuth应用的Client ID')
        with LOCK:
            c=self._read()
            if c.get('clientId')!=client:
                write_json_atomic(self.path,{'clientId':client})
        return self.status()

    def start(self):
        with LOCK:
            c=self._read()
            if not c.get('clientId'): raise AuthError('首次登录需登记OAuth应用的Client ID')
            now=time.time()
            for k,v in list(PENDING.items()):
                if now-v['created']>600: PENDING.pop(k,None)
            state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);nonce=secrets.token_urlsafe(32)
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            PENDING[state]={'verifier':verifier,'nonce':nonce,'created':now,'clientId':c['clientId'],'path':str(self.path)}
        url='https://linear.app/oauth/authorize?'+urllib.parse.urlencode(dict(client_id=c['clientId'],redirect_uri=CALLBACK,
            response_type='code',scope='read',state=state,code_challenge=challenge,code_challenge_method='S256',actor='user'))
        return {'url':url},'entropy_linear_state='+nonce+'; HttpOnly; SameSite=Lax; Path=/api/wbs/oauth; Max-Age=600'

    def _token_request(self,body):
        req=urllib.request.Request('https://api.linear.app/oauth/token',data=urllib.parse.urlencode(body).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req,timeout=30) as response: value=json.load(response)
        except Exception: raise AuthError('Linear授权交换失败，请重新登录；原有数据保留') from None
        if not value.get('access_token') or not value.get('refresh_token'): raise AuthError('Linear未返回完整登录信息')
        scope=value.get('scope','read')
        scopes=set(scope.split() if isinstance(scope,str) else scope)
        if scopes!={'read'}: raise AuthError('授权范围不是仅read，未保存该授权，请重新选择只读应用')
        return value

    def callback(self,params,cookie):
        state=params.get('state',[''])[0]
        jar=SimpleCookie()
        try: jar.load(cookie or '')
        except Exception: raise AuthError('登录校验失败，请重新登录') from None
        with LOCK:
            pending=PENDING.get(state)
            nonce=jar.get('entropy_linear_state')
            if not pending or time.time()-pending['created']>600 or not nonce or not hmac.compare_digest(nonce.value,pending['nonce']) or pending['path']!=str(self.path):
                raise AuthError('登录校验失败或过期，请从本页面重新登录')
            PENDING.pop(state,None)
        if params.get('error'): raise AuthError('已取消Linear授权')
        code=params.get('code',[''])[0]
        if not code: raise AuthError('登录回调缺少授权码')
        token=self._token_request(dict(grant_type='authorization_code',client_id=pending['clientId'],redirect_uri=CALLBACK,code=code,code_verifier=pending['verifier']))
        req=urllib.request.Request('https://api.linear.app/graphql',data=json.dumps({'query':'query { viewer { id name } organization { id name } }'}).encode(),headers={'Authorization':'Bearer '+token['access_token'],'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as response: identity=json.load(response)
            user=identity['data']['viewer'];org=identity['data']['organization']
            if not user or not org: raise ValueError()
        except Exception: raise AuthError('无法确认Linear登录身份，未保存新授权') from None
        with LOCK:
            if self._read().get('clientId')!=pending['clientId']: raise AuthError('应用配置已改变，请重新登录')
            write_json_atomic(self.path,dict(clientId=pending['clientId'],accessToken=token['access_token'],refreshToken=token['refresh_token'],
                expiresAt=time.time()+int(token.get('expires_in',3600)),user={'name':user['name'],'workspace':org['name']}))
        return self.status()

    def bearer(self):
        with LOCK:
            c=self._read()
            if not c.get('accessToken'): return None
            if c.get('expiresAt',0)<time.time()+90:
                token=self._token_request(dict(grant_type='refresh_token',refresh_token=c['refreshToken'],client_id=c['clientId']))
                c.update(accessToken=token['access_token'],refreshToken=token['refresh_token'],expiresAt=time.time()+int(token.get('expires_in',3600)))
                write_json_atomic(self.path,c)
            return 'Bearer '+c['accessToken']

    def logout(self):
        with LOCK:
            c=self._read();write_json_atomic(self.path,{'clientId':c.get('clientId','')})
            for k,v in list(PENDING.items()):
                if v['path']==str(self.path):PENDING.pop(k,None)
        return self.status()
