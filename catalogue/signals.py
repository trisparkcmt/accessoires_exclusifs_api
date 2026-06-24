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
        except CategorieParfum.DoesNotExist:
            instance._ancien_taux_reduction = Decimal('0')
    else:
        instance._ancien_taux_reduction = Decimal('0')


@receiver(pre_save, sender=TypeAccessoire)
def capturer_ancien_taux_accessoire(sender, instance, **kwargs):
    if instance.pk:
        try:
            ancien = TypeAccessoire.objects.get(pk=instance.pk)
            instance._ancien_taux_reduction = ancien.taux_reduction
        except TypeAccessoire.DoesNotExist:
            instance._ancien_taux_reduction = Decimal('0')
    else:
        instance._ancien_taux_reduction = Decimal('0')


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
    pass


@receiver(post_save, sender=TypeAccessoire)
def mettre_a_jour_prix_accessoires(sender, instance, **kwargs):
    """Les réductions de types d'accessoires sont maintenant calculées dynamiquement."""
    pass


@receiver(post_save, sender=TypeFlacon)
def mettre_a_jour_prix_flacons(sender, instance, **kwargs):
    pass


# ============================================================
# ALERTS DE STOCK — NOTIFICATIONS CATALOGUE
# ============================================================
def creer_notification_alerte(type_produit, product_id, product_name, stock_actuel, seuil_alerte, metadata=None):
    """Helper pour créer une notification de catalogue."""
    from .models import NotificationCatalogue

    if metadata is None:
        metadata = {}

    message = (
        f"⚠️ Alerte stock: {product_name} a atteint le seuil d'alerte "
        f"(stock: {stock_actuel}, seuil: {seuil_alerte})"
    )

    NotificationCatalogue.objects.create(
        type_produit=type_produit,
        product_id=product_id,
        product_name=product_name,
        stock_actuel=stock_actuel,
        seuil_alerte=seuil_alerte,
        message=message,
        metadata=metadata,
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

    if (instance.seuil_alerte_ml is not None
            and instance.stock_ml <= instance.seuil_alerte_ml):
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_ml:
            creer_notification_alerte(
                type_produit='lot_essence',
                product_id=instance.id,
                product_name=f"{instance.essence.nom_complet} (Lot)",
                stock_actuel=instance.stock_ml,
                seuil_alerte=instance.seuil_alerte_ml,
                metadata={
                    'essence_id': instance.essence_id,
                    'essence_name': instance.essence.nom_complet,
                    'lot_id': instance.id,
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
        except Accessoire.DoesNotExist:
            instance._ancien_stock_quantite = None
    else:
        instance._ancien_stock_quantite = None


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
        except Parfum.DoesNotExist:
            instance._ancien_stock_quantite = None
    else:
        instance._ancien_stock_quantite = None


@receiver(post_save, sender=Parfum)
def enregistrer_mouvement_parfum(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_quantite', None)
    _enregistrer_mouvement(
        type_produit='parfum',
        instance=instance,
        nom_produit=instance.nom,
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_quantite,
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


@receiver(post_save, sender=ProduitFiniEssence)
def enregistrer_mouvement_produit_fini(sender, instance, created, **kwargs):
    ancien_stock = getattr(instance, '_ancien_stock_disponible', None)
    _enregistrer_mouvement(
        type_produit='produit_fini_essence',
        instance=instance,
        nom_produit=f"{instance.essence.nom_complet} {instance.taille_ml}ml",
        quantite_avant=ancien_stock,
        quantite_apres=instance.stock_disponible,
    )


@receiver(pre_delete, sender=ProduitFiniEssence)
def restituer_stock_produit_fini(sender, instance, **kwargs):
    with transaction.atomic():
        instance.restituer_stock_lot()
