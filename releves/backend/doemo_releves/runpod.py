"""Narrow official REST v2 client. Provider key never leaves the OVH backend.

Verified against runpod/docs 3b219f9929f6054846e784e01801206c3ae18ac6.
No resource creation, reset, restart, termination, PATCH or DELETE is implemented.
"""
import os
import re
import httpx

BASE='https://api.runpod.io/v2'


class ProviderError(Exception):
    def __init__(self, code, retry_after=60):
        self.code=code
        self.retry_after=max(15,min(1800,retry_after))
        super().__init__('RunPod indisponible' if code=='network' else f'RunPod HTTP {code}')


class RunPod:
    def __init__(self,key=None,client=None):
        self._key=key if key is not None else os.environ.get('RUNPOD_API_KEY','')
        self._client=client or httpx.Client(timeout=8,follow_redirects=False)

    def request(self,method,path,data=None):
        if not self._key:raise ProviderError('not_configured')
        try:
            r=self._client.request(method,BASE+path,headers={'Authorization':'Bearer '+self._key},json=data)
        except httpx.HTTPError as exc:raise ProviderError('network') from None
        if r.status_code!=200:
            try:retry=int(r.headers.get('Retry-After','60'))
            except ValueError:retry=60
            raise ProviderError(r.status_code,retry)
        try:body=r.json()
        except ValueError:raise ProviderError('invalid_response') from None
        if not isinstance(body,dict):raise ProviderError('invalid_response')
        # Never return or log provider `env`, registry credentials or raw errors.
        return body

    def get(self,pod_id):
        self.validate_id(pod_id)
        pod=self.request('GET','/pods/'+pod_id)
        if pod.get('id')!=pod_id or not isinstance(pod.get('status'),str):raise ProviderError('invalid_response')
        return {k:pod.get(k) for k in ('id','name','status','actions','ports','mounts','startedAt')}

    def action(self,pod_id,action):
        self.validate_id(pod_id)
        if action not in ('start','stop'):raise ValueError('Action RunPod interdite')
        pod=self.request('POST','/pods/'+pod_id+'/action',{'action':action})
        return {'id':pod.get('id'),'status':pod.get('status')}

    @staticmethod
    def validate_id(pod_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',pod_id or ''):raise ValueError('Identifiant Pod invalide')
