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


@receiver(pre_save, sender='orders.Commande')
def capturer_ancien_statut_commande(sender, instance, **kwargs):
    """Capture l'ancien statut et le livreur d'une commande avant modification."""
    if instance.pk:
        try:
            from orders.models import Commande
            ancien = Commande.objects.get(pk=instance.pk)
            instance._ancien_statut = ancien.statut
            instance._ancien_statut_livraison = ancien.statut_livraison
            instance._ancien_statut_paiement = ancien.statut_paiement
            instance._ancien_livreur_id = ancien.livreur_id
        except Exception:
            instance._ancien_statut = None
            instance._ancien_statut_livraison = None
            instance._ancien_statut_paiement = None
            instance._ancien_livreur_id = None
    else:
        instance._ancien_statut = None
        instance._ancien_statut_livraison = None
        instance._ancien_statut_paiement = None
        instance._ancien_livreur_id = None


@receiver(post_save, sender='orders.Commande')
def notifier_changement_commande(sender, instance, created, **kwargs):
    """
    Gestion stricte des notifications selon les règles métier demandées :
    - Client : notifié UNIQUEMENT quand la commande est 'livrée' ou 'remboursée'.
    - Serveuses & Admins : notifiés lors d'une NOUVELLE commande passée.
    - Prestataire : notifié lorsque son code promo génère une commission (payée/livrée) ou est remboursé.
    - Livreur : notifié lors d'une affectation, retrait d'affectation ou annulation de sa commande.
    """
    cmd_ref = getattr(instance, 'numero_commande', '') or f"#{instance.pk}"

    # 1. NOUVELLE COMMANDE CRÉÉE
    if created:
        # Notifier les Admins & Serveuses (exclut l'acheteur s'il est aussi serveuse/admin)
        client_email = instance.client.email if instance.client else 'Client'
        Notification.objects.create(
            is_global_admin=True,
            type='nouvelle_commande_admin',
            title=f"Nouvelle Commande {cmd_ref}",
            message=f"Commande **{cmd_ref}** de **{instance.total_ttc} FCFA** reçue de **{client_email}**.",
            url=f"/api/v1/orders/commandes/{instance.pk}/",
            metadata={
                'commande_id': str(instance.pk),
                'numero_commande': str(cmd_ref),
                'statut': instance.statut,
                'total_ttc': str(instance.total_ttc),
                'exclude_user_id': str(instance.client.user.pk) if (instance.client and instance.client.user) else '',
            }
        )

    # 2. MODIFICATION D'UNE COMMANDE EXISTANTE
    else:
        ancien_statut = getattr(instance, '_ancien_statut', None)
        nouveau_statut = instance.statut
        ancien_livreur_id = getattr(instance, '_ancien_livreur_id', None)
        nouveau_livreur_id = instance.livreur_id

        # --- A. NOTIFICATIONS CLIENT (Règle : UNIQUEMENT pour 'livrée' et 'remboursée') ---
        if ancien_statut and ancien_statut != nouveau_statut and instance.client and instance.client.user:
            user_client = instance.client.user
            if nouveau_statut == 'livrée' and ancien_statut != 'livrée':
                Notification.objects.create(
                    recipient=user_client,
                    type='commande_livree',
                    title=f"Commande {cmd_ref} livrée ! 📦",
                    message=f"Votre commande **{cmd_ref}** a été livrée avec succès. Merci de votre confiance !",
                    url=f"/api/v1/orders/commandes/{instance.pk}/",
                    metadata={'commande_id': str(instance.pk), 'numero_commande': str(cmd_ref), 'statut': 'livrée'}
                )
            elif nouveau_statut == 'remboursée' and ancien_statut != 'remboursée':
                Notification.objects.create(
                    recipient=user_client,
                    type='commande_remboursee',
                    title=f"Commande {cmd_ref} remboursée 💳",
                    message=f"Votre commande **{cmd_ref}** a été remboursée.",
                    url=f"/api/v1/orders/commandes/{instance.pk}/",
                    metadata={'commande_id': str(instance.pk), 'numero_commande': str(cmd_ref), 'statut': 'remboursée'}
                )

        # --- B. NOTIFICATIONS PRESTATAIRE (quand son code promo génère une commission ou est remboursé) ---
        if instance.prestataire and instance.prestataire.client and instance.prestataire.client.user:
            user_prestataire = instance.prestataire.client.user
            if nouveau_statut in ['validé', 'livrée'] and ancien_statut not in ['validé', 'livrée']:
                code_promo_val = instance.code_promo_utilise or (instance.prestataire.code_promo if instance.prestataire else '') or ''
                Notification.objects.create(
                    recipient=user_prestataire,
                    type='commission_gagne',
                    title="Commission validée ! 💰",
                    message=(
                        f"La commande **{cmd_ref}** utilisant votre code promo **{code_promo_val}** a été validée/livrée ! "
                        f"Vous avez gagné **{instance.commission_montant} FCFA** de commission."
                    ),
                    url="/api/v1/utilisateur/prestataire/dashboard/",
                    metadata={
                        'commande_id': str(instance.pk),
                        'numero_commande': str(cmd_ref),
                        'commission_montant': str(instance.commission_montant),
                        'code_promo': str(code_promo_val),
                    }
                )
            elif nouveau_statut == 'remboursée' and ancien_statut != 'remboursée':
                Notification.objects.create(
                    recipient=user_prestataire,
                    type='commission_annulee',
                    title="Commande avec votre code remboursée ⚠️",
                    message=f"La commande **{cmd_ref}** liée à votre code promo a été remboursée.",
                    url="/api/v1/utilisateur/prestataire/dashboard/",
                    metadata={'commande_id': str(instance.pk), 'numero_commande': str(cmd_ref)}
                )

        # --- C. NOTIFICATIONS LIVREUR ---
        # 1. Attribué à un nouveau livreur
        if nouveau_livreur_id and nouveau_livreur_id != ancien_livreur_id:
            try:
                from utilisateur.models import Livreur
                nouveau_livreur = Livreur.objects.get(pk=nouveau_livreur_id)
                if nouveau_livreur.client and nouveau_livreur.client.user:
                    Notification.objects.create(
                        recipient=nouveau_livreur.client.user,
                        type='livraison_assignee',
                        title=f"Nouvelle livraison attribuée ! 🚚",
                        message=f"La commande **{cmd_ref}** vous a été attribuée pour livraison.",
                        url=f"/api/v1/auth/livreur/commandes/",
                        metadata={'commande_id': str(instance.pk), 'numero_commande': str(cmd_ref), 'adresse': str(instance.adresse_livraison or '')}
                    )
            except Exception:
                pass

        # 2. Retiré/désattribué à l'ancien livreur
        if ancien_livreur_id and ancien_livreur_id != nouveau_livreur_id:
            try:
                from utilisateur.models import Livreur
                ancien_livreur = Livreur.objects.get(pk=ancien_livreur_id)
                if ancien_livreur.client and ancien_livreur.client.user:
                    Notification.objects.create(
                        recipient=ancien_livreur.client.user,
                        type='livraison_retiree',
                        title=f"Livraison réassignée ℹ️",
                        message=f"La livraison de la commande **{cmd_ref}** ne vous est plus attribuée.",
                        url=f"/api/v1/auth/livreur/commandes/",
                        metadata={'commande_id': str(instance.pk), 'numero_commande': str(cmd_ref)}
                    )
            except Exception:
                pass

        # 3. Commande attribuée qui est annulée
        if nouveau_statut == 'annulée' and ancien_statut != 'annulée' and nouveau_livreur_id:
            try:
                from utilisateur.models import Livreur
                livreur_actuel = Livreur.objects.get(pk=nouveau_livreur_id)
                if livreur_actuel.client and livreur_actuel.client.user:
                    Notification.objects.create(
                        recipient=livreur_actuel.client.user,
                        type='livraison_annulee',
                        title=f"Livraison annulée 🛑",
                        message=f"La commande **{cmd_ref}** qui vous était attribuée a été annulée.",
                        url=f"/api/v1/auth/livreur/commandes/",
                        metadata={'commande_id': str(instance.pk), 'numero_commande': str(cmd_ref)}
                    )
            except Exception:
                pass


# ============================================================
# SIGNAL CODE PROMO ADMIN EXCLUSIF
# ============================================================
from django.db.models.signals import m2m_changed
from orders.models import CodePromoAdmin

@receiver(m2m_changed, sender=CodePromoAdmin.clients_autorises.through)
def notifier_clients_code_promo_exclusif(sender, instance, action, pk_set, **kwargs):
    """
    Notifie le ou les clients sélectionnés lorsqu'un Code Promo Admin exclusif leur est attribué.
    """
    if action == 'post_add' and pk_set:
        from utilisateur.models import Client
        clients = Client.objects.filter(pk__in=pk_set).select_related('user')
        
        # Formater proprement le pourcentage de réduction (ex: 10% au lieu de 10.00%)
        pourcentage_val = instance.reduction_pourcentage
        if pourcentage_val is not None:
            if pourcentage_val % 1 == 0:
                pourcentage_str = f"{int(pourcentage_val)}%"
            else:
                pourcentage_str = f"{pourcentage_val}%"
        else:
            pourcentage_str = "une"

        for client in clients:
            if client.user and client.user.is_active:
                Notification.objects.create(
                    recipient=client.user,
                    type='code_promo_exclusif',
                    title="🎁 Code Promo Exclusif !",
                    message=(
                        f"Vous avez reçu un code promo exclusif **{instance.code}** "
                        f"offrant **{pourcentage_str}** de réduction !"
                    ),
                    url="/api/v1/orders/promos/",
                    metadata={
                        'code_promo': str(instance.code),
                        'reduction_pourcentage': str(instance.reduction_pourcentage),
                    }
                )




# ============================================================
# SIGNATION RETRAITS PRESTATAIRE (PayoutTransaction)
# ============================================================
from .models import PayoutTransaction

@receiver(pre_save, sender=PayoutTransaction)
def capturer_ancien_statut_payout(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = PayoutTransaction.objects.get(pk=instance.pk)
            instance._ancien_statut = ancien.statut
        except PayoutTransaction.DoesNotExist:
            instance._ancien_statut = None
    else:
        instance._ancien_statut = None


@receiver(post_save, sender=PayoutTransaction)
def notifier_statut_payout_prestataire(sender, instance, created, **kwargs):
    """Notifie le Prestataire des demandes et de l'état final de son virement Campay."""
    if not instance.prestataire or not instance.prestataire.client or not instance.prestataire.client.user:
        return

    user_prestataire = instance.prestataire.client.user

    if created:
        Notification.objects.create(
            recipient=user_prestataire,
            type='payout_demande',
            title="Demande de retrait enregistrée 💸",
            message=f"Votre demande de retrait de **{instance.montant} FCFA** est en cours de traitement.",
            url="/api/v1/utilisateur/prestataire/payouts/",
            metadata={'payout_id': str(instance.pk), 'montant': str(instance.montant)}
        )
    else:
        ancien = getattr(instance, '_ancien_statut', None)
        if ancien and ancien != instance.statut:
            if instance.statut == 'succes':
                Notification.objects.create(
                    recipient=user_prestataire,
                    type='payout_succes',
                    title="Retrait effectué avec succès ! 💰",
                    message=f"Votre virement de **{instance.montant} FCFA** vers **{instance.telephone_destination}** a été validé.",
                    url="/api/v1/utilisateur/prestataire/payouts/",
                    metadata={'payout_id': str(instance.pk), 'montant': str(instance.montant)}
                )
            elif instance.statut == 'echec':
                Notification.objects.create(
                    recipient=user_prestataire,
                    type='payout_echec',
                    title="Échec du virement ⚠️",
                    message=f"Votre demande de retrait de **{instance.montant} FCFA** n'a pas pu aboutir. Votre solde a été crédité.",
                    url="/api/v1/utilisateur/prestataire/payouts/",
                    metadata={'payout_id': str(instance.pk), 'montant': str(instance.montant)}
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
            prenom = user.first_name or user.username
            Notification.objects.create(
                recipient=user,
                type='prestataire_statut_valide',
                title="Candidature Prestataire Validée ! 🎉",
                message=(
                    f"Félicitations **{prenom}** ! "
                    f"Votre demande pour devenir partenaire a été acceptée.\n"
                    f"Code promo : **{instance.code_promo or 'N/A'}**\n"
                    f"Taux commission : **{instance.taux_commission}%**\n"
                    f"Réduction client : **{instance.reduction_client_pourcentage}%**"
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
            prenom = user.first_name or user.username
            Notification.objects.create(
                recipient=user,
                type='prestataire_statut_refuse',
                title="Mise à jour candidature Prestataire",
                message=(
                    f"Bonjour **{prenom}**, "
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
        client_nom = instance.client.user.get_full_name()
        client_email = instance.client.email
        subject = f"Nouvelle demande de prestataire : {client_email}"
        message = (
            f"Une nouvelle demande de prestataire a été reçue.\n\n"
            f"Client: **{client_email}**\n"
            f"Nom: **{client_nom}**\n"
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
                'client_email': client_email,
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
        exclude_id = str(instance.metadata.get('exclude_user_id', '')) if instance.metadata else ''
        seen = set()
        all_users = []
        for user in admin_users + staff_users + serveuse_users:
            if str(user.pk) == exclude_id:
                continue
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

