import logging
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('orders')


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def generer_facture_async(self, commande_id):
    """
    Génère la facture PDF et l'envoie par email au client en arrière-plan.
    """
    from orders.models import Commande
    from orders.services import generer_facture

    try:
        logger.info(f"[CELERY FACTURE] Début génération facture pour commande #{commande_id}")
        commande = Commande.objects.get(id=commande_id)
        facture = generer_facture(commande)
        logger.info(f"[CELERY FACTURE] Facture {facture.numero_facture} générée avec succès pour commande #{commande_id}")
        return facture.numero_facture
    except Commande.DoesNotExist:
        logger.warning(f"[CELERY FACTURE] Commande #{commande_id} introuvable.")
        return None
    except Exception as exc:
        logger.error(f"[CELERY FACTURE] Erreur génération facture pour commande #{commande_id}: {exc}")
        raise exc


@shared_task
def relancer_paniers_abandonnes_task():
    """
    Tâche périodique (Celery Beat) pour relancer les clients ayant abandonné leur panier
    depuis plus de 2 heures et moins de 24 heures.
    """
    from orders.models import Panier
    from utilisateur.tasks import send_email_async

    maintenant = timezone.now()
    seuil_min = maintenant - timedelta(hours=2)
    seuil_max = maintenant - timedelta(hours=24)

    paniers_abandonnes = Panier.objects.filter(
        statut='actif',
        total__gt=0,
        client__isnull=False,
        client__user__email__isnull=False,
        date_modification__range=(seuil_max, seuil_min),
    ).select_related('client__user')

    count = 0
    frontend_url = getattr(settings, 'FRONTEND_URL', 'https://dev.accessoiresexclusifs.com').rstrip('/')

    for panier in paniers_abandonnes:
        user = panier.client.user
        email = user.email
        if not email:
            continue

        prenom = user.first_name or "Cher client"
        sujet = "Votre panier vous attend chez Accessoires Exclusifs ! ✨"
        message = f"""Bonjour {prenom},

Vous avez laissé des articles dans votre panier d'un montant de {panier.total:,.0f} FCFA.
Ne passez pas à côté de vos coups de cœur !

Pour finaliser votre commande en toute simplicité :
{frontend_url}/panier

À très vite sur Accessoires Exclusifs !
"""
        html_message = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; max-width: 600px; margin: auto; padding: 25px; border: 1px solid #eaeaea; border-radius: 10px; background-color: #ffffff;">
            <h2 style="color: #bfa15f; margin-top: 0;">Votre sélection vous attend ✨</h2>
            <p>Bonjour <strong>{prenom}</strong>,</p>
            <p>Vous avez sélectionné des articles d'exception dans votre panier pour un montant total de <strong>{panier.total:,.0f} FCFA</strong>.</p>
            <p>Les articles sont actuellement réservés, mais les stocks sont limités.</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{frontend_url}/panier" style="background-color: #1a1a1a; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Finaliser ma commande →</a>
            </div>
            <p style="font-size: 12px; color: #888888; border-top: 1px solid #eeeeee; padding-top: 15px;">
                Si vous avez déjà finalisé vos achats entre-temps, veuillez ignorer cet email.<br>
                L'équipe Accessoires Exclusifs
            </p>
        </div>
        """
        try:
            send_email_async.delay(
                subject=sujet,
                message=message,
                recipient_list=[email],
                html_message=html_message,
            )
            count += 1
        except Exception as e:
            logger.warning(f"[CELERY RELANCE PANIERS] Impossible d'enfiler la relance pour {email}: {e}")

    logger.info(f"[CELERY RELANCE PANIERS] {count} relances envoyées.")
    return count
