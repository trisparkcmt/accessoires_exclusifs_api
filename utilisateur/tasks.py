import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail

logger = logging.getLogger('utilisateur')


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,  # 1 minute initiale
    autoretry_for=(Exception,),
    retry_backoff=True,      # Backoff exponentiel (1 min, 2 min, 4 min, etc.)
    retry_backoff_max=600,   # Plafond à 10 minutes
    retry_jitter=True,       # Évite les pics simultanés
)
def send_email_async(self, subject, message, recipient_list, from_email=None, html_message=None):
    """
    Envoie un email en arrière-plan via Celery avec réessais automatiques en cas d'erreur SMTP.
    """
    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL

    if isinstance(recipient_list, str):
        recipient_list = [recipient_list]

    try:
        logger.info(f"[CELERY EMAIL] Envoi asynchrone: '{subject}' vers {recipient_list}")
        if html_message:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=from_email,
                to=recipient_list,
            )
            msg.attach_alternative(html_message, "text/html")
            msg.send(fail_silently=False)
        else:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=False,
            )
        logger.info(f"[CELERY EMAIL] Envoyé avec succès: '{subject}' vers {recipient_list}")
        return True
    except Exception as exc:
        logger.warning(
            f"[CELERY EMAIL] Erreur envoi '{subject}' vers {recipient_list} (tentative {self.request.retries + 1}/{self.max_retries}): {exc}"
        )
        raise exc
