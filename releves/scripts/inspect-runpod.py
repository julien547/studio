"""OVH ONLY: read current Pod metadata without displaying any provider secrets.
Load RUNPOD_API_KEY and DOEMO_RUNPOD_POD_ID via the existing private EnvironmentFile.
No start, stop, PATCH, restart or deletion. No environment values are returned.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error


def main():
 ident=os.environ.get('DOEMO_RUNPOD_POD_ID','');key=os.environ.get('RUNPOD_API_KEY','')
 if not key or not re.fullmatch('[A-Za-z0-9_-]{1,80}',ident):
  print('Charger la configuration privée existante sur OVH.',file=sys.stderr);return 1
 request=urllib.request.Request('https://api.runpod.io/v2/pods/'+ident,headers={'Authorization':'Bearer '+key})
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):return None
 try:
  with urllib.request.build_opener(NoRedirect).open(request,timeout=10) as response:
   raw=response.read(4*1024**2+1)
   if len(raw)>4*1024**2:raise ValueError()
   data=json.loads(raw)
  if data.get('id')!=ident or data.get('name')!=os.environ.get('DOEMO_RUNPOD_POD_NAME','DOEMO-STUDIO-IA'):raise ValueError()
  ssh=data.get('ssh') or {}
  # The provider's entire `env` field is deliberately excluded.
  print(json.dumps({'id':ident,'name':data['name'],'status':data.get('status'),
    'ssh':{k:{'command':v.get('command')} for k,v in ssh.items() if k in ('direct','proxy') and isinstance(v,dict)},
    'gateway':'https://'+ident+'-'+os.environ.get('DOEMO_RUNPOD_GATEWAY_PORT','8000')+'.proxy.runpod.net'},indent=2))
 except urllib.error.HTTPError as error:
  print('API RunPod HTTP '+str(error.code)+' ; réponse brute masquée.',file=sys.stderr);return 1
 except Exception:
  print('Lecture impossible ou Pod différent de la configuration autorisée.',file=sys.stderr);return 1
 return 0

if __name__=='__main__':sys.exit(main())
