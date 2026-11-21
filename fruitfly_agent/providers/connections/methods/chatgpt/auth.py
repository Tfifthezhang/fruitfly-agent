"""Official public-client registration and validated ChatGPT plan consent."""
from __future__ import annotations
import time
from typing import Any
from urllib.parse import urlencode
import httpx
import jwt
from ....auth.oauth import OAuthAttempt
from ....auth.session import binding_identity
from fruitfly_agent.core.errors import FatalError

ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
TOKEN = ISSUER + '/api/accounts/oauth/token'
SCOPE = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'

def token_request(data: dict[str, str]) -> dict[str, Any]:
    try:
        response = httpx.post(TOKEN, data=data, timeout=10, follow_redirects=False)
        if response.status_code != 200:
            code = response.json().get('error', '')
            if isinstance(code, dict):
                code = code.get('code', '')
            kind = 'authentication_required' if code in {'invalid_grant', 'invalid_refresh_token',
                'token_expired', 'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused'} else 'authentication_unavailable'
            raise FatalError('ChatGPT authorization could not be renewed; reconnect or retry later', details={'kind': kind})
        value = response.json()
        for key in ('access_token', 'refresh_token', 'id_token', 'scope'):
            if not isinstance(value.get(key), str) or not value[key]:
                raise ValueError('Invalid token response')
        if value.get('token_type', '').lower() != 'bearer' or type(value.get('expires_in')) not in (int, float) or not 0 < value['expires_in'] <= 86400:
            raise ValueError('Invalid token lifetime')
        return value
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise FatalError('ChatGPT authorization service unavailable', details={'kind': 'authentication_unavailable'}) from None

def claims(id_token: str, client_id: str, nonce: str | None = None) -> dict[str, Any]:
    try:
        discovery = httpx.get(ISSUER + '/.well-known/openid-configuration', timeout=10).json()
        jwks_uri = discovery['jwks_uri']
        if not jwks_uri.startswith(ISSUER + '/'):
            raise ValueError('Untrusted identity key endpoint')
        keys = jwt.PyJWKSet.from_dict(httpx.get(jwks_uri, timeout=10).json())
        header = jwt.get_unverified_header(id_token)
        key = next(k for k in keys.keys if k.key_id == header.get('kid'))
        result = jwt.decode(id_token, key.key, algorithms=['RS256'], audience=client_id, issuer=ISSUER,
            options={'require': ['exp', 'iat', 'sub', 'aud', 'iss']})
        if nonce is not None and result.get('nonce') != nonce:
            raise ValueError('Identity nonce mismatch')
        if not isinstance(result['sub'], str) or not result['sub']:
            raise ValueError('Invalid identity subject')
        return result
    except (httpx.HTTPError, ValueError, KeyError, StopIteration, jwt.PyJWTError):
        raise ValueError('ChatGPT identity validation failed') from None

def authorization_url(attempt: OAuthAttempt, host_id: str, saved: dict[str, Any] | None = None) -> str:
    query = dict(client_id=attempt.client_id or 'dynamic_agent_client', ext_agent_host_id=host_id,
        response_type='code', redirect_uri=attempt.redirect_uri, resource=RESOURCE, scope=SCOPE,
        state=attempt.state, nonce=attempt.nonce, code_challenge=attempt.challenge, code_challenge_method='S256')
    if not attempt.client_id:
        query['agent_name_hint'] = 'FruitFlyAgent'
    return ISSUER + '/api/accounts/authorize?' + urlencode(query)

def complete(attempt: OAuthAttempt, record: dict[str, Any]) -> dict[str, Any]:
    if attempt.error or attempt.result is None:
        raise ValueError(attempt.error or 'Authorization is not complete')
    value = token_request(dict(grant_type='authorization_code', client_id=attempt.result['client_id'],
        code=attempt.result['code'], code_verifier=attempt.verifier, redirect_uri=attempt.redirect_uri, resource=RESOURCE))
    identity = claims(value['id_token'], attempt.result['client_id'], attempt.nonce)
    if record.get('subject') and record['subject'] != identity['sub']:
        raise ValueError('Authorized account differs from the selected registration')
    result = {**record, 'subject': identity['sub'], 'client_id': attempt.result['client_id'],
        'label': record.get('label') or identity.get('email', 'ChatGPT account')}
    return apply_tokens(result, value)

def apply_tokens(record: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    scopes = value['scope'].split()
    result = {**record, **{k: value[k] for k in ('access_token', 'refresh_token', 'id_token')},
        'scopes': scopes, 'expires_at': time.time() + value['expires_in'],
        'status': 'connected' if 'chatgpt.tokens.use.direct' in scopes else 'plan_disabled'}
    result['binding'] = binding_identity(result)
    return result

def refresh(record: dict[str, Any]) -> dict[str, Any]:
    value = token_request(dict(grant_type='refresh_token', client_id=record['client_id'],
        refresh_token=record['refresh_token'], resource=RESOURCE))
    identity = claims(value['id_token'], record['client_id'])
    if identity['sub'] != record['subject']:
        raise FatalError('ChatGPT identity changed during renewal', details={'kind': 'authentication_required'})
    result = apply_tokens(record, value)
    if result['status'] != 'connected':
        raise FatalError('ChatGPT plan permission is missing', details={'kind': 'authentication_required'})
    return result

def revoke(record: dict[str, Any]) -> bool:
    try:
        discovery = httpx.get(ISSUER + '/.well-known/openid-configuration', timeout=10).json()
        endpoint = discovery['revocation_endpoint']
        if not endpoint.startswith(ISSUER + '/'):
            return False
        return httpx.post(endpoint, data={'token': record['refresh_token'], 'token_type_hint': 'refresh_token',
            'client_id': record['client_id']}, timeout=10).status_code == 200
    except (httpx.HTTPError, ValueError, KeyError):
        return False


def begin_login(host_id: str, record: dict[str, Any]) -> tuple[OAuthAttempt, str]:
    attempt = OAuthAttempt(client_id=record.get('client_id', ''))
    return attempt, authorization_url(attempt, host_id, record)
