import requests
import uuid
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_auth_token():
    """Retourne un token d'auth pour Campay.
    Priorité : CAMPAY_API_TOKEN (permanent). Sinon, utilise CAMPAY_USERNAME/CAMPAY_PASSWORD
    pour récupérer un token temporaire via /token/.
    """
    if getattr(settings, 'CAMPAY_API_TOKEN', None):
        return settings.CAMPAY_API_TOKEN

    username = getattr(settings, 'CAMPAY_USERNAME', '')
    password = getattr(settings, 'CAMPAY_PASSWORD', '')
    if not username or not password:
        return None

    try:
        resp = requests.post(f"{settings.CAMPAY_API_URL}/token/", json={
            'username': username,
            'password': password,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get('token')
    except Exception as e:
        logger.exception('Erreur lors de la récupération du token Campay')
        return None


def payout_to_phone(to_phone: str, amount_fcfa: int, description: str = '', external_reference: str = None):
    """
    Effectue un retrait (withdraw) vers un numéro mobile via Campay.
    - to_phone : numéro avec indicatif pays (ex: '2376XXXXXXXX')
    - amount_fcfa : entier
    - external_reference : uuid4 string unique (si None, en génère une)

    Retourne (success: bool, response_data: dict or None, error_message: str or None)
    """
    token = _get_auth_token()
    if not token:
        return False, None, 'Missing Campay auth token/configuration'

    if external_reference is None:
        external_reference = str(uuid.uuid4())

    payload = {
        'amount': str(int(amount_fcfa)),
        'to': to_phone,
        'description': description or 'Payout prestataire',
        'external_reference': external_reference,
    }

    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(f"{settings.CAMPAY_API_URL}/withdraw/", json=payload, headers=headers, timeout=15)
        try:
            data = resp.json()
        except ValueError:
            data = {'http_status': resp.status_code, 'text': resp.text}

        if resp.status_code in (200, 201):
            return True, data, None
        else:
            err = data.get('message') or data.get('detail') or f'HTTP {resp.status_code}'
            return False, data, err
    except requests.RequestException as e:
        logger.exception('Erreur réseau vers Campay')
        return False, None, str(e)
