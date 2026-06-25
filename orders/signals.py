from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from decimal import Decimal

from orders.models import Commande, CommandeLigneParfumPerso
from utilisateur.models import Notification

User = get_user_model()


@receiver(post_save, sender=Commande)
def notify_on_commande_paid(sender, instance, created=False, **kwargs):
    """
    Notifie le prestataire quand sa commande est payée (statut_paiement = 'payé')
    avec le montant de commission reçu.
    """
    # Vérifier si le statut_paiement vient de passer à 'payé'
    if instance.statut_paiement == 'payé' and instance.prestataire:
        prestataire_user = instance.prestataire.client.user
        
        # Vérifier si c'est une nouvelle notification (pas créée)
        # En vérifiant si c'est un changement et pas juste une création
        if not created:
            title = "Commande payée - Commission reçue"
            message = (
                f"Une commande a été payée et une commission vous a été attribuée.\n\n"
                f"Numéro commande: {instance.numero_commande}\n"
                f"Montant: {instance.total_ttc}€\n"
                f"Commission: {instance.commission_montant}€\n"
                f"Statut commission: {instance.commission_statut}"
            )
            
            Notification.objects.create(
                recipient=prestataire_user,
                type='prestataire_commission',
                title=title,
                message=message,
                url=f'/api/v1/commandes/{instance.numero}/',
                metadata={
                    'commande_id': instance.pk,
                    'numero_commande': instance.numero_commande,
                    'commission_montant': str(instance.commission_montant),
                    'total': str(instance.total_ttc),
                }
            )


@receiver(post_save, sender=Commande)
def notify_on_commande_with_parfum_perso(sender, instance, created=False, **kwargs):
    """
    Notifie le labo/admin quand une commande validée contient un parfum personnalisé.
    """
    if instance.statut == 'validé':
        # Vérifier s'il y a des parfums personnalisés dans cette commande
        has_parfum_perso = CommandeLigneParfumPerso.objects.filter(
            commande=instance
        ).exists()
        
        if has_parfum_perso:
            # Notifier les admins
            admin_users = User.objects.filter(is_staff=True, is_active=True)
            
            for admin in admin_users:
                title = "Nouvelle commande avec parfum personnalisé"
                message = (
                    f"Une commande validée contient un parfum personnalisé.\n\n"
                    f"Numéro commande: {instance.numero_commande}\n"
                    f"Client: {instance.client.user.email if instance.client else 'Invité'}\n"
                    f"Montant: {instance.total_ttc}€\n"
                    f"À traiter par le laboratoire."
                )
                
                Notification.objects.create(
                    recipient=admin,
                    type='commande_parfum_perso',
                    title=title,
                    message=message,
                    url=f'/api/v1/commandes/{instance.numero_commande}/',
                    metadata={
                        'commande_id': instance.pk,
                        'numero_commande': instance.numero_commande,
                        'client_email': instance.client.user.email if instance.client else None,
                    }
                )


@receiver(post_save, sender=Commande)
def notify_on_commande_assigned_to_livreur(sender, instance, created=False, **kwargs):
    """
    Notifie le livreur quand une commande lui est assignée 
    (livreur != null ET statut_livraison = 'assignée').
    """
    if instance.livreur and instance.statut_livraison == 'assignée':
        livreur_user = instance.livreur.user
        
        title = "Nouvelle commande assignée"
        message = (
            f"Une nouvelle commande vous a été assignée.\n\n"
            f"Numéro commande: {instance.numero_commande}\n"
            f"Client: {instance.livraison_nom_complet}\n"
            f"Adresse: {instance.livraison_quartier}, {instance.livraison_ville}\n"
            f"Téléphone: {instance.livraison_telephone}\n"
            f"Total: {instance.total_ttc}€"
        )
        
        Notification.objects.create(
            recipient=livreur_user,
            type='livreur_commande_assignee',
            title=title,
            message=message,
            url=f'/api/v1/commandes/{instance.numero_commande}/',
            metadata={
                'commande_id': instance.pk,
                'numero_commande': instance.numero_commande,
                'livreur_id': instance.livreur.pk,
                'montant': str(instance.total_ttc),
            }
        )


@receiver(post_save, sender=Commande)
def notify_on_commande_cancelled(sender, instance, created=False, **kwargs):
    """
    Notifie le livreur quand une commande assignée est annulée.
    """
    if instance.statut == 'annulée' and instance.livreur:
        livreur_user = instance.livreur.user
        
        title = "Commande annulée"
        message = (
            f"La commande qui vous était assignée a été annulée.\n\n"
            f"Numéro commande: {instance.numero_commande}\n"
            f"Client: {instance.livraison_nom_complet}\n"
            f"Raison: Annulation de commande"
        )
        
        Notification.objects.create(
            recipient=livreur_user,
            type='livreur_commande_annulee',
            title=title,
            message=message,
            url=f'/api/v1/commandes/{instance.numero_commande}/',
            metadata={
                'commande_id': instance.pk,
                'numero_commande': instance.numero_commande,
                'livreur_id': instance.livreur.pk,
            }
        )
