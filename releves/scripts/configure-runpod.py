"""Run on OVH only. Create private systemd EnvironmentFiles; never contact RunPod."""
import argparse
import getpass
import json
import os
import re
import secrets
import sys
from pathlib import Path


def write_configuration(directory, pod_id, provider_key, gateway_token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',pod_id):
        raise ValueError('Identifiant Pod invalide')
    if not provider_key or any(ord(c)<32 for c in provider_key):
        raise ValueError('Clé vide ou contenant un caractère de contrôle')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,}',gateway_token):
        raise ValueError('Jeton gateway invalide')
    directory=Path(directory)
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    paths=[directory/'runpod-ovh.env',directory/'runpod-gateway.env']
    if any(p.exists() or p.is_symlink() for p in paths):
        raise ValueError('Configuration déjà présente : aucun fichier écrasé')
    backend={
        'RUNPOD_API_KEY':provider_key,
        'DOEMO_RUNPOD_TOKEN':gateway_token,
        'DOEMO_RUNPOD_POD_ID':pod_id,
        'DOEMO_RUNPOD_POD_NAME':'DOEMO-STUDIO-IA',
        'DOEMO_RUNPOD_GATEWAY_PORT':'8000',
        'DOEMO_RUNPOD_MANAGED':'0',
        'DOEMO_RUNPOD_AUTOSTART':'1',
        'DOEMO_RUNPOD_AUTOSTOP':'1',
    }
    for path,values in zip(paths,[backend,{'DOEMO_RUNPOD_TOKEN':gateway_token}]):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as out:
            out.write('# Fichier privé pour systemd EnvironmentFile ; ne pas publier.\n')
            for key,value in values.items():
                out.write(key+'='+json.dumps(value,ensure_ascii=False)+'\n')
    return paths


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--pod-id',default='41m7oy6qjaj2ji')
    args=parser.parse_args()
    if not sys.stdin.isatty():
        parser.error('Utiliser un terminal interactif sur OVH pour masquer la clé.')
    key=getpass.getpass('Clé API RunPod (saisie masquée, stockage sur OVH uniquement) : ').strip()
    try:
        paths=write_configuration(args.output_dir,args.pod_id,key,secrets.token_urlsafe(48))
    except (ValueError,OSError) as exc:
        print('Configuration interrompue : '+type(exc).__name__+'. Vérifier le dossier et les fichiers existants.',file=sys.stderr)
        return 1
    print('Configuration privée créée pour le Pod '+args.pod_id+'.')
    print('OVH uniquement : '+str(paths[0]))
    print('Jeton gateway séparé, sans clé API RunPod : '+str(paths[1]))
    print('Gestion désactivée (MANAGED=0) tant que le bootstrap du Pod n’est pas préparé.')
    print('Aucun appel RunPod, aucun démarrage et aucun déploiement effectué.')
    return 0


if __name__=='__main__':sys.exit(main())
