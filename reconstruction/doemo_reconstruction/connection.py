"""Read-only checks of the private worker; never start a Pod or run an inference."""
import time

import httpx

ENGINES = ('paddleocr', 'qwen', 'rtmdet')


def inspect_worker(remote):
    health = remote('GET', '/health', timeout=8)
    models = remote('GET', '/models', timeout=8)
    if not isinstance(health, dict) or not isinstance(models, list):
        raise ValueError('Invalid worker contract')
    if any(type(health.get(k)) is not bool for k in ('ready', 'draining')):
        raise ValueError('Invalid readiness')
    if any(type(health.get(k)) is not int or health[k] < 0 for k in ('active', 'unsaved')):
        raise ValueError('Invalid admission state')
    if any(not isinstance(health.get(k), str) or not health[k].strip()
           for k in ('pod_id', 'worker_instance_id')):
        raise ValueError('Missing worker identity')
    versions, summary = {}, []
    for name in ENGINES:
        found = [m for m in models if isinstance(m, dict) and m.get('id') == name]
        if len(found) != 1:
            raise ValueError('Missing or duplicate engine')
        model = found[0]
        version = model.get('version')
        if (not isinstance(version, str) or not 0 < len(version) <= 200
                or any(ord(c) < 32 for c in version)
                or any(marker in version.lower() for marker in ('replace', 'to-verify', 'placeholder'))):
            raise ValueError('Unverified model version')
        verified = all(model.get(k) is True for k in
                       ('configured', 'environment_present', 'functional_inference_verified'))
        # Older workers omit per-engine startup details; their existing checks still apply.
        startup_state = 'passed' if verified else 'pending'
        error_code = None
        if 'startup' in health:
            startup = health['startup']
            if not isinstance(startup, dict) or not isinstance(startup.get(name), dict):
                raise ValueError('Invalid startup status')
            startup_state, error_code = startup[name].get('state'), startup[name].get('error_code')
            if startup_state not in ('pending', 'running', 'passed', 'failed') or error_code not in (
                    None, 'gpu_unavailable', 'timeout', 'invalid_output', 'inference_failed'):
                raise ValueError('Invalid startup status')
            if (startup_state == 'failed') != (error_code is not None):
                raise ValueError('Inconsistent startup status')
            verified = verified and startup_state == 'passed'
        summary.append({'id': name, 'version': version, 'startup_inference_verified': verified,
                        'startup_state': startup_state, 'error_code': error_code})
        if verified:
            versions[name] = version
    if health.get('warmup_error') or health['unsaved'] or any(m['startup_state']=='failed' for m in summary):
        state = 'not_ready'
    elif health['draining'] or health['active']:
        state = 'busy'
    elif not health['ready'] or len(versions) != len(ENGINES):
        state = 'starting'
    else:
        state = 'ready'
    return state, health, versions, summary


def connection_status(configured, remote):
    """Sanitized status: do not expose endpoints, credentials, paths or exception text."""
    result = {'configured': configured, 'checked_at': time.time(), 'state': 'not_configured',
              'can_analyze': False, 'engines': [], 'segmentation_qualified': False}
    if not configured:
        return result
    try:
        state, _, _, engines = inspect_worker(remote)
        result.update(state=state, engines=engines, can_analyze=state == 'ready')
    except httpx.HTTPStatusError as error:
        result['state'] = 'authentication_failed' if error.response.status_code in (401, 403) else 'unavailable'
    except httpx.TransportError:
        result['state'] = 'unavailable'
    except OSError:
        result['state'] = 'key_unavailable'
    except (ValueError, TypeError, KeyError):
        result['state'] = 'invalid_configuration_or_contract'
    return result
