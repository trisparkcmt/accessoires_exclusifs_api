# catalogue/signals.py
from decimal import Decimal
from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from .models import (
    CategorieParfum, TypeAccessoire, TypeFlacon, Essence,
    Accessoire, Flacon, LotEssence, Ingredient, Parfum, ProduitFiniEssence,
)


# ============================================================
# NOTIFICATIONS PROMOTIONS — clients
# ============================================================
def _notifier_clients_promotion(title, message, url, metadata=None):
    """Envoie une notification in-app (+ FCM) à tous les clients actifs."""
    from utilisateur.models import Client, Notification

    if metadata is None:
        metadata = {}

    clients = Client.objects.select_related('user').filter(user__is_active=True)
    for client in clients:
        Notification.objects.create(
            recipient=client.user,
            type='promotion_catalogue',
            title=title,
            message=message,
            url=url,
            metadata=metadata,
        )


def _promotion_vient_de_devenir_active(etait_active, est_active):
    return est_active and not etait_active


# ============================================================
# HELPER — calcul du prix après réduction
# ============================================================
def appliquer_reduction(prix_unitaire, taux):
    """Calcule le prix après réduction, arrondi à 2 décimales."""
    reduction = Decimal(str(taux)) / Decimal('100')
    return (prix_unitaire * (1 - reduction)).quantize(Decimal('0.01'))


# ============================================================
# CAPTURE DE L'ANCIENNE VALEUR — via pre_save
# ============================================================
@receiver(pre_save, sender=CategorieParfum)
def capturer_ancien_aux_categorie(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = CategorieParfum.objects.get(pk=instance.pk)
            instance._ancien_taux_reduction = ancien.taux_reduction
            instance._promotion_etait_active = ancien.promotion_active()
        except CategorieParfum.DoesNotExist:
            instance._ancien_taux_reduction = Decimal('0')
            instance._promotion_etait_active = False
    else:
        instance._ancien_taux_reduction = Decimal('0')
        instance._promotion_etait_active = False


@receiver(pre_save, sender=TypeAccessoire)
def capturer_ancien_taux_accessoire(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = TypeAccessoire.objects.get(pk=instance.pk)
            instance._ancien_taux_reduction = ancien.taux_reduction
            instance._promotion_etait_active = ancien.promotion_active()
        except TypeAccessoire.DoesNotExist:
            instance._ancien_taux_reduction = Decimal('0')
            instance._promotion_etait_active = False
    else:
        instance._ancien_taux_reduction = Decimal('0')
        instance._promotion_etait_active = False


@receiver(pre_save, sender=TypeFlacon)
def capturer_ancien_taux_flacon(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = TypeFlacon.objects.get(pk=instance.pk)
            instance._ancien_taux_reduction = ancien.taux_reduction
        except TypeFlacon.DoesNotExist:
            instance._ancien_taux_reduction = Decimal('0')
    else:
        instance._ancien_taux_reduction = Decimal('0')


# ============================================================
# APPLICATION DES RÉDUCTIONS — via post_save (dynamique)
# ============================================================
@receiver(post_save, sender=CategorieParfum)
def mettre_a_jour_prix_parfums(sender, instance, **kwargs):
    """Les réductions de catégories sont maintenant calculées dynamiquement."""
    etait_active = getattr(instance, '_promotion_etait_active', False)
    est_active = instance.promotion_active()
    if _promotion_vient_de_devenir_active(etait_active, est_active):
        msg = instance.message_promotion or f"-{instance.taux_reduction}% sur tous les parfums de cette catégorie"
        _notifier_clients_promotion(
            title=f"Promotion : {instance.nom}",
            message=f"Bonne nouvelle ! {msg}.",
            url=f'/api/v1/shop/parfums/?categorie={instance.slug}',
            metadata={
                'cible': 'categorie_parfum',
                'categorie_id': instance.pk,
                'taux_reduction': str(instance.taux_reduction),
            },
        )


@receiver(post_save, sender=TypeAccessoire)
def mettre_a_jour_prix_accessoires(sender, instance, **kwargs):
    """Les réductions de types d'accessoires sont maintenant calculées dynamiquement."""
    etait_active = getattr(instance, '_promotion_etait_active', False)
    est_active = instance.promotion_active()
    if _promotion_vient_de_devenir_active(etait_active, est_active):
        msg = instance.message_promotion or f"-{instance.taux_reduction}% sur tous les accessoires de ce type"
        _notifier_clients_promotion(
            title=f"Promotion : {instance.nom}",
            message=f"Bonne nouvelle ! {msg}.",
            url=f'/api/v1/shop/accessoires/?type={instance.slug}',
            metadata={
                'cible': 'type_accessoire',
                'type_id': instance.pk,
                'taux_reduction': str(instance.taux_reduction),
            },
        )


@receiver(post_save, sender=TypeFlacon)
def mettre_a_jour_prix_flacons(sender, instance, **kwargs):
    pass


# ============================================================
# ALERTS DE STOCK — NOTIFICATIONS CATALOGUE
# ============================================================
def creer_notification_alerte(type_produit, product_id, product_name, stock_actuel, seuil_alerte, metadata=None):
    """Helper pour créer une notification de catalogue ET envoyer un push FCM aux admins."""
    from .models import NotificationCatalogue
    from utilisateur.fcm_service import send_fcm_notification
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if metadata is None:
        metadata = {}

    message = (
        f"⚠️ Alerte stock: {product_name} a atteint le seuil d'alerte "
        f"(stock: {stock_actuel}, seuil: {seuil_alerte})"
    )

    # 1. Notification en base (NotificationCatalogue — visible dans l'admin)
    NotificationCatalogue.objects.create(
        type_produit=type_produit,
        product_id=product_id,
        product_name=product_name,
        stock_actuel=stock_actuel,
        seuil_alerte=seuil_alerte,
        message=message,
        metadata=metadata,
    )

    # 2. Push FCM vers tous les admins et staff actifs
    admins = User.objects.filter(is_active=True, is_staff=True)
    if admins.exists():
        send_fcm_notification(
            users=admins,
            title=f"⚠️ Alerte stock — {product_name}",
            message=message,
            data={
                'type': 'alerte_stock',
                'type_produit': str(type_produit),
                'product_id': str(product_id),
                'product_name': product_name,
                'stock_actuel': str(stock_actuel),
                'seuil_alerte': str(seuil_alerte),
            },
        )


# ============================================================
# HELPER — enregistrement mouvement de stock
# ============================================================
def _enregistrer_mouvement(type_produit, instance, nom_produit, quantite_avant, quantite_apres):
    """
    Crée un MouvementStock si la quantité a réellement changé.
    quantite_avant=None signifie création (1ère sauvegarde) — aucune ligne créée.
    L'utilisateur courant est récupéré via le middleware thread-local.
    """
    if quantite_avant is None:
        return  # premier enregistrement, pas de mouvement à tracer

    q_avant = Decimal(str(quantite_avant))
    q_apres = Decimal(str(quantite_apres))
    delta = q_apres - q_avant

    if delta == 0:
        return  # aucun changement

    from utilisateur.middleware import get_current_user
    from .models import MouvementStock

    utilisateur = get_current_user()  # None si appel hors contexte HTTP (ex: signal JWT)

    MouvementStock.objects.create(
        utilisateur=utilisateur,  # Peut être None : le champ doit être null=True, blank=True
        type_produit=type_produit,
        produit_id=instance.pk,
        nom_produit=nom_produit,
        quantite_avant=q_avant,
        quantite_apres=q_apres,
        quantite_ajoutee=delta,
    )


# ============================================================
# ESSENCE
# ============================================================
@receiver(pre_save, sender=Essence)
def capturer_ancien_seuil_essence(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = Essence.objects.get(pk=instance.pk)
            instance._ancien_seuil_alerte_ml = ancien.seuil_alerte_ml
        except Essence.DoesNotExist:
            instance._ancien_seuil_alerte_ml = None
    else:
        instance._ancien_seuil_alerte_ml = None


@receiver(post_save, sender=Essence)
def verifier_alerte_essence(sender, instance, created, **kwargs):
    """Alerte quand le seuil est AUGMENTÉ et passe au-dessus du stock existant.
    
    On ne déclenche PAS d'alerte à la création de l'essence : il n'y a pas
    encore de lots, c'est un état initial attendu.
    """
    # À la création, aucun lot n'existe encore → pas d'alerte
    if created:
        return

    ancien_seuil = getattr(instance, '_ancien_seuil_alerte_ml', None)

    if instance.seuil_alerte_ml is None:
        return

    # Alerte uniquement si le seuil a été augmenté (et qu'il dépasse le stock actuel)
    if ancien_seuil is None or instance.seuil_alerte_ml <= ancien_seuil:
        return

    total_stock = instance.stock_total_ml()
    if total_stock <= instance.seuil_alerte_ml:
        from django.utils import timezone
        from .models import NotificationCatalogue
        minute_ago = timezone.now() - timezone.timedelta(minutes=1)
        exists = NotificationCatalogue.objects.filter(
            type_produit='essence',
            product_id=instance.id,
            created_at__gte=minute_ago
        ).exists()
        if not exists:
            creer_notification_alerte(
                type_produit='essence',
                product_id=instance.id,
                product_name=instance.nom_complet,
                stock_actuel=total_stock,
                seuil_alerte=instance.seuil_alerte_ml,
                metadata={
                    'essence_id': instance.id,
                    'essence_name': instance.nom_complet,
                },
            )



# ============================================================
# LOT ESSENCE
# ============================================================
@receiver(pre_save, sender=LotEssence)
def capturer_ancien_stock_lot_essence(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = LotEssence.objects.get(pk=instance.pk)
            instance._ancien_stock_ml = ancien.stock_ml
        except LotEssence.DoesNotExist:
            instance._ancien_stock_ml = None
    else:
        instance._ancien_stock_ml = None


@receiver(post_save, sender=LotEssence)
def verifier_alerte_lot_essence(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_ml', None)

    # Alerte de stock global au niveau de l'essence (Alternative 1)
    seuil_alerte = instance.essence.seuil_alerte_ml
    if seuil_alerte is not None:
        total_stock = instance.essence.stock_total_ml()
        delta_lot = instance.stock_ml - (ancien_stock if ancien_stock is not None else Decimal('0'))
        ancien_total = total_stock - delta_lot

        # On alerte uniquement si le stock vient de FRANCHIR le seuil à la baisse
        # (passage de ancien_total > seuil à total_stock <= seuil)
        if ancien_total > seuil_alerte and total_stock <= seuil_alerte:
            creer_notification_alerte(
                type_produit='essence',
                product_id=instance.essence.id,
                product_name=instance.essence.nom_complet,
                stock_actuel=total_stock,
                seuil_alerte=seuil_alerte,
                metadata={
                    'essence_id': instance.essence.id,
                    'essence_name': instance.essence.nom_complet,
                },
            )

    _enregistrer_mouvement(
        type_produit='lot_essence',
        instance=instance,
        nom_produit=f"{instance.essence.nom_complet} (Lot #{instance.pk})",
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_ml,
    )


# ============================================================
# ACCESSOIRE
# ============================================================
@receiver(pre_save, sender=Accessoire)
def capturer_ancien_stock_accessoire(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = Accessoire.objects.get(pk=instance.pk)
            instance._ancien_stock_quantite = ancien.stock_quantite
            instance._promotion_etait_active = ancien.prix_promotionnel_effectif is not None
        except Accessoire.DoesNotExist:
            instance._ancien_stock_quantite = None
            instance._promotion_etait_active = False
    else:
        instance._ancien_stock_quantite = None
        instance._promotion_etait_active = False

    # Désactivation automatique uniquement quand le stock vient d'être épuisé (mise à jour)
    ancien = getattr(instance, '_ancien_stock_quantite', None)
    if instance.stock_quantite <= 0 and ancien is not None and ancien > 0:
        instance.actif = False


@receiver(post_save, sender=Accessoire)
def verifier_alerte_accessoire(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_quantite', None)

    if instance.stock_quantite <= instance.seuil_alerte_stock:
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_stock:
            creer_notification_alerte(
                type_produit='accessoire',
                product_id=instance.id,
                product_name=instance.nom,
                stock_actuel=instance.stock_quantite,
                seuil_alerte=instance.seuil_alerte_stock,
                metadata={
                    'type_accessoire': instance.type_accessoire.nom if instance.type_accessoire else 'N/A',
                    'sku': instance.reference_sku,
                },
            )

    _enregistrer_mouvement(
        type_produit='accessoire',
        instance=instance,
        nom_produit=instance.nom,
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_quantite,
    )

    etait_active = getattr(instance, '_promotion_etait_active', False)
    est_active = instance.prix_promotionnel_effectif is not None
    if _promotion_vient_de_devenir_active(etait_active, est_active) and instance.actif:
        prix_promo = instance.prix_promotionnel_effectif
        _notifier_clients_promotion(
            title=f"Promotion : {instance.nom}",
            message=(
                f"L'accessoire {instance.nom} est en promotion à {prix_promo} FCFA "
                f"(au lieu de {instance.prix_unitaire} FCFA)."
            ),
            url=f'/api/v1/shop/accessoires/{instance.slug}/',
            metadata={
                'cible': 'accessoire',
                'accessoire_id': instance.pk,
                'prix_promotionnel': str(prix_promo),
                'prix_unitaire': str(instance.prix_unitaire),
            },
        )


# ============================================================
# FLACON
# ============================================================
@receiver(pre_save, sender=Flacon)
def capturer_ancien_stock_flacon(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = Flacon.objects.get(pk=instance.pk)
            instance._ancien_stock_quantite = ancien.stock_quantite
        except Flacon.DoesNotExist:
            instance._ancien_stock_quantite = None
    else:
        instance._ancien_stock_quantite = None

    # Désactivation automatique uniquement quand le stock vient d'être épuisé (mise à jour)
    ancien = getattr(instance, '_ancien_stock_quantite', None)
    if instance.stock_quantite <= 0 and ancien is not None and ancien > 0:
        instance.actif = False


@receiver(post_save, sender=Flacon)
def verifier_alerte_flacon(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_quantite', None)

    if instance.stock_quantite <= instance.seuil_alerte_stock:
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_stock:
            creer_notification_alerte(
                type_produit='flacon',
                product_id=instance.id,
                product_name=f"{instance.nom} ({instance.contenance_ml}ml)",
                stock_actuel=instance.stock_quantite,
                seuil_alerte=instance.seuil_alerte_stock,
                metadata={
                    'type_flacon': instance.type_flacon.nom if instance.type_flacon else 'N/A',
                    'contenance_ml': instance.contenance_ml,
                    'sku': instance.reference_sku,
                },
            )

    _enregistrer_mouvement(
        type_produit='flacon',
        instance=instance,
        nom_produit=f"{instance.nom} ({instance.contenance_ml}ml)",
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_quantite,
    )


# ============================================================
# INGREDIENT
# ============================================================
@receiver(pre_save, sender=Ingredient)
def capturer_ancien_stock_ingredient(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = Ingredient.objects.get(pk=instance.pk)
            instance._ancien_stock_ml = ancien.stock_ml
        except Ingredient.DoesNotExist:
            instance._ancien_stock_ml = None
    else:
        instance._ancien_stock_ml = None


@receiver(post_save, sender=Ingredient)
def verifier_alerte_ingredient(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_ml', None)

    if instance.seuil_alerte_ml is not None and instance.stock_ml <= instance.seuil_alerte_ml:
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_ml:
            creer_notification_alerte(
                type_produit='ingredient',
                product_id=instance.id,
                product_name=instance.nom,
                stock_actuel=instance.stock_ml,
                seuil_alerte=instance.seuil_alerte_ml,
                metadata={
                    'ingredient_id': instance.id,
                    'ingredient_name': instance.nom,
                },
            )

    _enregistrer_mouvement(
        type_produit='ingredient',
        instance=instance,
        nom_produit=instance.nom,
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_ml,
    )


# ============================================================
# PARFUM
# ============================================================
@receiver(pre_save, sender=Parfum)
def capturer_ancien_stock_parfum(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = Parfum.objects.get(pk=instance.pk)
            instance._ancien_stock_quantite = ancien.stock_quantite
            instance._promotion_etait_active = ancien.prix_promotionnel_effectif is not None
        except Parfum.DoesNotExist:
            instance._ancien_stock_quantite = None
            instance._promotion_etait_active = False
    else:
        instance._ancien_stock_quantite = None
        instance._promotion_etait_active = False

    # Désactivation automatique uniquement quand le stock vient d'être épuisé (mise à jour)
    ancien = getattr(instance, '_ancien_stock_quantite', None)
    if instance.stock_quantite <= 0 and ancien is not None and ancien > 0:
        instance.actif = False


@receiver(post_save, sender=Parfum)
def enregistrer_mouvement_parfum(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_quantite', None)
    
    if instance.stock_quantite <= instance.seuil_alerte_stock:
        if (ancien_stock is None or ancien_stock > instance.seuil_alerte_stock) and instance.actif:
            creer_notification_alerte(
                type_produit='parfum',
                product_id=instance.id,
                product_name=instance.nom,
                stock_actuel=instance.stock_quantite,
                seuil_alerte=instance.seuil_alerte_stock,
                metadata={
                    'categorie': instance.categorie.nom if instance.categorie else 'N/A',
                    'sku': instance.reference_sku,
                },
            )

    _enregistrer_mouvement(
        type_produit='parfum',
        instance=instance,
        nom_produit=instance.nom,
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_quantite,
    )

    etait_active = getattr(instance, '_promotion_etait_active', False)
    est_active = instance.prix_promotionnel_effectif is not None
    if _promotion_vient_de_devenir_active(etait_active, est_active) and instance.actif:
        prix_promo = instance.prix_promotionnel_effectif
        _notifier_clients_promotion(
            title=f"Promotion : {instance.nom}",
            message=(
                f"Le parfum {instance.nom} est en promotion à {prix_promo} FCFA "
                f"(au lieu de {instance.prix_unitaire} FCFA)."
            ),
            url=f'/api/v1/shop/parfums/{instance.slug}/',
            metadata={
                'cible': 'parfum',
                'parfum_id': instance.pk,
                'prix_promotionnel': str(prix_promo),
                'prix_unitaire': str(instance.prix_unitaire),
            },
        )


# ============================================================
# PRODUIT FINI ESSENCE
# ============================================================
@receiver(pre_save, sender=ProduitFiniEssence)
def capturer_ancien_stock_produit_fini(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = ProduitFiniEssence.objects.get(pk=instance.pk)
            instance._ancien_stock_disponible = ancien.stock_disponible
        except ProduitFiniEssence.DoesNotExist:
            instance._ancien_stock_disponible = None
    else:
        instance._ancien_stock_disponible = None

    # Désactivation automatique uniquement quand le stock vient d'être épuisé (mise à jour)
    ancien = getattr(instance, '_ancien_stock_disponible', None)
    if instance.stock_disponible <= 0 and ancien is not None and ancien > 0:
        instance.actif = False


@receiver(post_save, sender=ProduitFiniEssence)
def enregistrer_mouvement_produit_fini(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_disponible', None)
    nom_produit = f"{instance.essence.nom_complet} {instance.taille_ml}ml"

    # Alerte stock (manquait pour ProduitFiniEssence)
    if (instance.seuil_alerte_stock is not None
            and instance.stock_disponible <= instance.seuil_alerte_stock):
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_stock:
            creer_notification_alerte(
                type_produit='produit_fini_essence',
                product_id=instance.id,
                product_name=nom_produit,
                stock_actuel=instance.stock_disponible,
                seuil_alerte=instance.seuil_alerte_stock,
                metadata={
                    'essence_id': instance.essence_id,
                    'essence_name': instance.essence.nom_complet,
                    'taille_ml': instance.taille_ml,
                },
            )

    _enregistrer_mouvement(
        type_produit='produit_fini_essence',
        instance=instance,
        nom_produit=nom_produit,
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_disponible,
    )


@receiver(pre_delete, sender=ProduitFiniEssence)
def restituer_stock_produit_fini(sender, instance, **kwargs):
    with transaction.atomic():
        instance.restituer_stock_lot()
