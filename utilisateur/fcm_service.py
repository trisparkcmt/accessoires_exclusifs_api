# utilisateur/fcm_service.py
"""
Service Firebase Cloud Messaging.

Ce module fournit une fonction centrale `send_fcm_notification` qui :
  1. Récupère tous les tokens FCM actifs pour les utilisateurs cibles.
  2. Envoie la notification push via le SDK firebase-admin.
  3. Désactive automatiquement les tokens invalides (expirés ou désinscrits).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def send_fcm_notification(
    users,
    title: str,
    message: str,
    data: Optional[dict] = None,
):
    """
    Envoie une notification push FCM à une liste d'utilisateurs.

    Args:
        users: Un seul User, ou un queryset / une liste de User.
        title: Titre de la notification.
        message: Corps textuel de la notification.
        data: Dictionnaire de métadonnées supplémentaires (ex: {"type": "commande", "id": "5"}).
              Les valeurs DOIVENT être des chaînes de caractères.
    """
    try:
        import firebase_admin.messaging as fcm_messaging
    except ImportError:
        logger.error("[FCM] Le module firebase_admin n'est pas installé.")
        return

    from utilisateur.models import FCMDevice

    # Accepte un seul utilisateur ou une collection
    if not hasattr(users, '__iter__'):
        users = [users]

    # Forcer les valeurs de data en string (exigé par FCM)
    str_data = {k: str(v) for k, v in (data or {}).items()}
    str_data['title'] = title
    str_data['message'] = message

    # Récupérer tous les tokens actifs pour les utilisateurs cibles
    user_ids = [u.pk for u in users]
    devices = FCMDevice.objects.filter(user_id__in=user_ids, active=True)
    tokens = list(devices.values_list('registration_token', flat=True))

    if not tokens:
        logger.debug("[FCM] Aucun token actif trouvé pour les utilisateurs : %s", user_ids)
        return

    # Découper en lots de 500 (limite FCM par batch)
    def chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    invalid_tokens = []

    for batch in chunks(tokens, 500):
        multicast_message = fcm_messaging.MulticastMessage(
            tokens=batch,
            notification=fcm_messaging.Notification(
                title=title,
                body=message,
            ),
            data=str_data,
            android=fcm_messaging.AndroidConfig(
                priority='high',
                notification=fcm_messaging.AndroidNotification(
                    sound='default',
                    click_action='FLUTTER_NOTIFICATION_CLICK',
                ),
            ),
            apns=fcm_messaging.APNSConfig(
                payload=fcm_messaging.APNSPayload(
                    aps=fcm_messaging.Aps(sound='default'),
                ),
            ),
            webpush=fcm_messaging.WebpushConfig(
                headers={'Urgency': 'high'},
                notification=fcm_messaging.WebpushNotification(
                    title=title,
                    body=message,
                    icon='/icons/icon-192x192.png',
                ),
                fcm_options=fcm_messaging.WebpushFCMOptions(
                    link=str_data.get('url', '/'),
                ),
            ),
        )

        try:
            response = fcm_messaging.send_each_for_multicast(multicast_message)
            logger.info(
                "[FCM] Batch envoyé — Succès: %d, Échecs: %d",
                response.success_count,
                response.failure_count,
            )

            # Collecter les tokens invalides pour les désactiver
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    error_code = resp.exception.code if resp.exception else 'unknown'
                    if error_code in (
                        'registration-token-not-registered',
                        'invalid-registration-token',
                        'messaging/registration-token-not-registered',
                    ):
                        invalid_tokens.append(batch[idx])
                        logger.warning("[FCM] Token invalide détecté : %s", batch[idx][:30])

        except Exception as e:
            logger.exception("[FCM] Erreur lors de l'envoi du batch FCM : %s", e)

    # Désactiver tous les tokens invalides en une seule requête
    if invalid_tokens:
        deactivated = FCMDevice.objects.filter(
            registration_token__in=invalid_tokens
        ).update(active=False)
        logger.info("[FCM] %d token(s) invalide(s) désactivé(s).", deactivated)
