from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum, Q
from allauth.account.signals import email_confirmed
from allauth.socialaccount.signals import social_account_added

from .models import Prestataire, Notification

User = get_user_model()

import logging as _sig_logger
logger_fidelite = _sig_logger.getLogger(__name__)

SEUIL_POINTS = 25000  # 1 point tous les 25 000 FCFA dépensés


def _recalculer_points_client(client):
    """
    Recalcule les points de fidélité d'un client à partir du total de ses commandes payées.
    Règle : 1 point par tranche de SEUIL_POINTS FCFA.
    Sauvegarde uniquement si la valeur a changé (évite les écritures inutiles).
    """
    from django.db.models import Sum, Q
    total = client.commandes.filter(
        statut_paiement='payé'
    ).aggregate(
        total=Sum('total_ttc')
    )['total'] or 0

    nouveaux_points = int(total // SEUIL_POINTS)

    if client.points_fidelite != nouveaux_points:
        client.points_fidelite = nouveaux_points
        client.save(update_fields=['points_fidelite'])
        logger_fidelite.info(
            "[Fidélité] Client #%d — dépenses totales=%.0f FCFA → %d points",
            client.pk, total, nouveaux_points
        )


@receiver(post_save, sender='orders.Commande')
def maj_points_fidelite_sur_paiement(sender, instance, **kwargs):
    """
    Recalcule les points de fidélité du client à chaque mise à jour de commande.
    Ne s'exécute que si la commande est payée et que le client existe.
    """
    if instance.statut_paiement == 'payé' and instance.client:
        try:
            _recalculer_points_client(instance.client)
        except Exception as e:
            logger_fidelite.exception(
                "[Fidélité] Erreur recalcul points pour client #%s : %s",
                getattr(instance.client, 'pk', '?'), e
            )



@receiver(pre_save, sender=Prestataire)
def capturer_ancien_statut_prestataire(sender, instance, **kwargs):
    """Capture l'ancien statut avant sauvegarde pour détecter l'acceptation ou le refus."""
    if instance.pk:
        try:
            ancien = Prestataire.objects.get(pk=instance.pk)
            instance._ancien_statut = ancien.statut
        except Prestataire.DoesNotExist:
            instance._ancien_statut = None
    else:
        instance._ancien_statut = None


@receiver(post_save, sender=Prestataire)
def notify_prestataire_statut_change(sender, instance, created, **kwargs):
    """
    Notifie le prestataire (In-App + Push FCM) lorsque sa candidature est acceptée ou refusée.
    """
    if created:
        return  # La création initiale (demande) est notifiée aux admins par notify_admin_on_prestataire_request

    ancien_statut = getattr(instance, '_ancien_statut', None)
    nouveau_statut = instance.statut

    if ancien_statut and ancien_statut != nouveau_statut:
        user = instance.client.user
        
        # 1. CAS ACCEPTÉ / VALIDÉ (ex: en_attente -> actif ou valide)
        if nouveau_statut in ['actif', 'valide']:
            Notification.objects.create(
                recipient=user,
                type='prestataire_statut_valide',
                title="Candidature Prestataire Validée ! 🎉",
                message=(
                    f"Félicitations {user.first_name or user.username} ! "
                    f"Votre demande pour devenir partenaire a été acceptée.\n"
                    f"Code promo : {instance.code_promo or 'N/A'}\n"
                    f"Taux commission : {instance.taux_commission}%\n"
                    f"Réduction client : {instance.reduction_client_pourcentage}%"
                ),
                url='/api/v1/utilisateur/prestataire/dashboard/',
                metadata={
                    'prestataire_id': instance.pk,
                    'statut': nouveau_statut,
                    'code_promo': instance.code_promo or '',
                    'taux_commission': str(instance.taux_commission),
                    'reduction_client': str(instance.reduction_client_pourcentage),
                }
            )

        # 2. CAS REFUSÉ / REJETÉ (ex: en_attente -> inactif / suspendu / refuse)
        elif nouveau_statut in ['refuse', 'rejete', 'inactif', 'suspendu'] and ancien_statut == 'en_attente':
            Notification.objects.create(
                recipient=user,
                type='prestataire_statut_refuse',
                title="Mise à jour candidature Prestataire",
                message=(
                    f"Bonjour {user.first_name or user.username}, "
                    f"nous avons examiné votre demande de partenariat. "
                    f"Malheureusement, nous ne pouvons pas y donner une suite favorable pour le moment."
                ),
                url='/api/v1/utilisateur/me/',
                metadata={
                    'prestataire_id': instance.pk,
                    'statut': nouveau_statut,
                }
            )


@receiver(post_save, sender=Prestataire)
def notify_admin_on_prestataire_request(sender, instance, created, **kwargs):
    """Signal envoyé à l'administrateur quand un prestataire fait une demande."""
    if created and instance.statut == 'en_attente':
        admin_users = User.objects.filter(is_staff=True, is_active=True)
        subject = f"Nouvelle demande de prestataire : {instance.client.email}"
        message = (
            f"Une nouvelle demande de prestataire a été reçue.\n\n"
            f"Client: {instance.client.email}\n"
            f"Nom: {instance.client.user.get_full_name()}\n"
            f"Statut: {instance.statut}\n"
            f"Date: {instance.date_creation}\n\n"
            "Veuillez consulter l'admin ou le tableau de bord dédié pour traiter cette demande."
        )

        # Créer une notification globale visible par tous les admins
        Notification.objects.create(
            recipient=None,
            type='prestataire_request',
            title='Nouvelle demande de prestataire',
            message=message,
            url=f'/api/v1/utilisateur/prestataire-requests/{instance.pk}/',
            is_global_admin=True,
            metadata={
                'prestataire_id': instance.pk,
                'client_email': instance.client.email,
                'statut': instance.statut,
            }
        )

        # Envoi d'email HTML enrichi en complément
        admin_emails = list(admin_users.values_list('email', flat=True))
        if admin_emails:
            try:
                client_user = instance.client.user
                context = {
                    'client_email': instance.client.email,
                    'client_nom': client_user.get_full_name() or client_user.username,
                    'client_telephone': getattr(client_user, 'telephone', '') or '',
                    'date_creation': instance.date_creation,
                    'admin_url': f"{settings.FRONTEND_URL.rstrip('/')}/admin/prestataires",
                }
                html_content = render_to_string('emails/prestataire_request_admin.html', context)
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=admin_emails,
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send(fail_silently=True)
            except Exception as exc:
                _sig_logger.error(f"[PRESTATAIRE] Erreur envoi email HTML admin : {exc}")
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    admin_emails,
                    fail_silently=True,
                )

def send_accessoire_welcome_email(user):
    """Envoie le mail de bienvenue Accessoires Exclusifs."""
    subject = "Bienvenue chez Accessoires Exclusifs !"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [user.email]

    context = {
        'user': user,
        'frontend_url': settings.FRONTEND_URL,
    }

    # Rendu des templates
    text_content = render_to_string('account/email/welcome_message.txt', context)
    html_content = render_to_string('account/email/welcome_message.html', context)

    # Création et envoi de l'email
    msg = EmailMultiAlternatives(subject, text_content, from_email, to)
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


@receiver(email_confirmed)
def send_welcome_email(sender, request, email_address, **kwargs):
    """Signal envoyé par allauth quand un utilisateur confirme son adresse email."""
    user = email_address.user
    if not user.is_active:
        user.is_active = True
        user.save()
    send_accessoire_welcome_email(user)


@receiver(social_account_added)
def send_google_welcome_email(sender, request, sociallogin, **kwargs):
    """Envoie le mail de bienvenue quand un compte Google est créé ou lié."""
    if sociallogin.account.provider == 'google':
        send_accessoire_welcome_email(sociallogin.user)


# ============================================================
# SIGNAL FCM — Push automatique sur chaque nouvelle Notification
# ============================================================

import logging as _logging
_fcm_logger = _logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def envoyer_push_fcm_sur_notification(sender, instance, created, **kwargs):
    """
    Déclenche un push FCM à chaque nouvelle Notification créée en base de données.
    Ne s'exécute PAS lors des mises à jour (ex: marquage comme lu).
    """
    if not created:
        return  # Push uniquement pour les nouvelles notifications

    from utilisateur.fcm_service import send_fcm_notification

    # Métadonnées transmises au frontend (toutes les valeurs doivent être des strings)
    extra_data = {
        'notification_id': str(instance.pk),
        'type': str(instance.type or 'general'),
        'url': str(instance.url or ''),
    }
    if instance.metadata:
        for k, v in instance.metadata.items():
            extra_data[str(k)] = str(v)

    if instance.is_global_admin:
        # Push vers tous les admins (is_superuser ou is_staff) et serveuses actives
        admin_users = list(User.objects.filter(is_superuser=True, is_active=True))
        staff_users = list(User.objects.filter(is_staff=True, is_active=True))

        try:
            from utilisateur.models import Serveuse  # noqa
            serveuse_users = list(
                User.objects.filter(client__serveuse__actif=True, is_active=True)
            )
        except Exception:
            serveuse_users = []

        # Dédupliquer les utilisateurs cibles
        seen = set()
        all_users = []
        for user in admin_users + staff_users + serveuse_users:
            if user.pk not in seen:
                seen.add(user.pk)
                all_users.append(user)

        if all_users:
            send_fcm_notification(
                users=all_users,
                title=instance.title,
                message=instance.message,
                data=extra_data,
            )
            _fcm_logger.info(
                "[Signal FCM] Notif globale admin #%d → %d utilisateurs.",
                instance.pk, len(all_users),
            )

    elif instance.recipient:
        # Push vers un utilisateur spécifique
        send_fcm_notification(
            users=[instance.recipient],
            title=instance.title,
            message=instance.message,
            data=extra_data,
        )
        _fcm_logger.info(
            "[Signal FCM] Notif #%d → %s.",
            instance.pk, instance.recipient.email,
        )


# ============================================================
# AUTOMATISATION SITE — Empêche les erreurs 500 dans l'Admin
# ============================================================
from django.db.models.signals import post_migrate

@receiver(post_migrate)
def meubler_site_par_defaut(sender, **kwargs):
    """
    S'assure que le Site correspondant à SITE_ID existe bien en base de données.
    Évite les erreurs 500 dans l'administration Django et allauth si le site n'existe pas.
    """
    if getattr(sender, 'name', '') == 'django.contrib.sites':
        try:
            from django.contrib.sites.models import Site
            site_id = getattr(settings, 'SITE_ID', 1)
            site, created = Site.objects.get_or_create(
                id=site_id,
                defaults={
                    'domain': 'accessoiresexclusifs.com',
                    'name': 'Accessoires Exclusifs',
                }
            )
            if created:
                print(f"[SITE AUTO] Site #{site_id} créé automatiquement : {site.domain}")
        except Exception as e:
            print(f"[SITE AUTO] Erreur création site par défaut : {e}")

