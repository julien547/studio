#!/usr/bin/env python3
"""Check the active OVH service's RunPod connection without sending a plan."""
import argparse
import json
import sys

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', default='/run/doemo-redessin/api.sock')
    args = parser.parse_args()
    try:
        transport = httpx.HTTPTransport(uds=args.socket)
        with httpx.Client(transport=transport, base_url='http://localhost', timeout=25) as client:
            response = client.get('/runpod/status', headers={'X-Doemo-User': 'deployment-check'})
            response.raise_for_status()
            status = response.json()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        # Startup inference only. The operator must still run the page test in Studio.
        return 0 if status.get('state') == 'ready' and status.get('can_analyze') is True else 1
    except (httpx.HTTPError, ValueError):
        print('Contrôle impossible : vérifier le service OVH et les droits du socket.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
