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


def _get_headers():
    token = _get_auth_token()
    if not token:
        return None
    return {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json',
    }


def payout_to_phone(to_phone: str, amount_fcfa: int, description: str = '', external_reference: str = None):
    """
    Effectue un retrait (withdraw) vers un numéro mobile via Campay.
    - to_phone : numéro avec indicatif pays (ex: '2376XXXXXXXX')
    - amount_fcfa : entier
    - external_reference : uuid4 string unique (si None, en génère une)

    Retourne (success: bool, response_data: dict or None, error_message: str or None)
    response_data contient notamment :
      - 'processing_number'  : ID interne Campay à stocker pour le webhook
      - 'external_reference' : votre UUID renvoyé par Campay
      - 'status'             : statut initial (PENDING, SUCCESSFUL, FAILED)
    """
    headers = _get_headers()
    if not headers:
        return False, None, 'Missing Campay auth token/configuration'

    if external_reference is None:
        external_reference = str(uuid.uuid4())

    payload = {
        'amount': str(int(amount_fcfa)),
        'to': to_phone,
        'description': description or 'Payout prestataire',
        'external_reference': external_reference,
    }

    try:
        resp = requests.post(f"{settings.CAMPAY_API_URL}/withdraw/", json=payload, headers=headers, timeout=15)
        try:
            data = resp.json()
        except ValueError:
            data = {'http_status': resp.status_code, 'text': resp.text}

        if resp.status_code in (200, 201):
            logger.info('[Campay] Payout initié. processing_number=%s external_ref=%s status=%s',
                        data.get('processing_number'), external_reference, data.get('status'))
            return True, data, None
        else:
            err = data.get('message') or data.get('detail') or f'HTTP {resp.status_code}'
            logger.warning('[Campay] Payout rejeté: %s — réponse: %s', err, data)
            return False, data, err
    except requests.RequestException as e:
        logger.exception('Erreur réseau vers Campay')
        return False, None, str(e)


def get_transaction_status(processing_number: str):
    """
    Interroge Campay pour connaître le statut actuel d'une transaction.
    - processing_number : ID interne Campay (retourné par /withdraw/)

    Retourne (success: bool, data: dict or None, error: str or None)
    data contient 'status' (SUCCESSFUL / FAILED / PENDING) et d'autres champs.
    """
    headers = _get_headers()
    if not headers:
        return False, None, 'Missing Campay auth token/configuration'

    try:
        resp = requests.get(
            f"{settings.CAMPAY_API_URL}/transaction/{processing_number}/",
            headers=headers,
            timeout=10
        )
        try:
            data = resp.json()
        except ValueError:
            data = {'http_status': resp.status_code, 'text': resp.text}

        if resp.status_code == 200:
            return True, data, None
        else:
            err = data.get('message') or data.get('detail') or f'HTTP {resp.status_code}'
            return False, data, err
    except requests.RequestException as e:
        logger.exception('Erreur réseau vers Campay (get_transaction_status)')
        return False, None, str(e)

