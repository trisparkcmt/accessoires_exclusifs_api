# catalogue/signals.py
from decimal import Decimal
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import CategorieParfum, TypeAccessoire, TypeFlacon, Essence, Accessoire, Flacon, LotEssence


# ============================================================
# HELPER — calcul du prix après réduction
# ============================================================
def appliquer_reduction(prix_unitaire, taux):
    """Calcule le prix après réduction, arrondi à 2 décimales."""
    reduction = Decimal(str(taux)) / Decimal('100')
    return (prix_unitaire * (1 - reduction)).quantize(Decimal('0.01'))


# ============================================================
# CAPTURE DE L'ANCIENNE VALEUR — via pre_save
#
# pre_save se déclenche AVANT l'écriture en base.
# On y récupère la valeur actuelle en BDD (l'ancienne)
# et on la stocke sur l'instance avec un attribut temporaire
# _ancien_taux_reduction, disponible dans post_save.
# ============================================================
@receiver(pre_save, sender=CategorieParfum)
def capturer_ancien_taux_categorie(sender, instance, **kwargs):
    """
    Avant la sauvegarde, on lit le taux actuel en base
    et on le stocke sur l'instance pour le comparer dans post_save.
    Si l'objet est nouveau (pas encore en base), _ancien_taux = 0.
    """
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
# APPLICATION DES RÉDUCTIONS — via post_save
#
# Après la sauvegarde, on compare le nouveau taux avec l'ancien
# (_ancien_taux_reduction capturé dans pre_save) pour décider
# quoi faire sur les produits liés.
# ============================================================
@receiver(post_save, sender=CategorieParfum)
def mettre_a_jour_prix_parfums(sender, instance, **kwargs):
    """
    Cas 1 — Nouveau taux > 0 :
        Calcule prix_promotionnel = prix_unitaire * (1 - taux/100)
        SAUF si le produit a déjà un prix_promotionnel manuel
        plus avantageux (inférieur au prix calculé).

    Cas 2 — Nouveau taux = 0 (réduction désactivée) :
        Retire prix_promotionnel UNIQUEMENT sur les produits
        dont le prix_promotionnel correspond exactement au calcul
        fait avec l'ANCIEN taux (donc auto, pas manuel).
    """
    nouveau_taux = instance.taux_reduction
    ancien_taux  = getattr(instance, '_ancien_taux_reduction', Decimal('0'))

    # Aucun changement de taux → rien à faire
    if nouveau_taux == ancien_taux:
        return

    parfums = instance.parfums.filter(actif=True)

    if nouveau_taux > 0:
        for parfum in parfums:
            prix_calcule = appliquer_reduction(parfum.prix_unitaire, nouveau_taux)

            # Prix manuel plus avantageux → priorité au manuel
            if parfum.prix_promotionnel and parfum.prix_promotionnel < prix_calcule:
                continue

            parfum.prix_promotionnel = prix_calcule
            parfum.save(update_fields=['prix_promotionnel'])

    else:
        # taux → 0 : on retire uniquement les prix calculés automatiquement
        for parfum in parfums:
            if parfum.prix_promotionnel is None:
                continue

            # Recalcul avec l'ANCIEN taux (valeur fiable capturée avant save)
            prix_auto_precedent = appliquer_reduction(parfum.prix_unitaire, ancien_taux)

            # Si le prix stocké correspond exactement au calcul auto → c'est auto
            if parfum.prix_promotionnel == prix_auto_precedent:
                parfum.prix_promotionnel = None
                parfum.save(update_fields=['prix_promotionnel'])
            # Sinon → prix manuel, on ne touche pas


@receiver(post_save, sender=TypeAccessoire)
def mettre_a_jour_prix_accessoires(sender, instance, **kwargs):
    """Même logique que pour CategorieParfum, appliquée aux accessoires."""
    nouveau_taux = instance.taux_reduction
    ancien_taux  = getattr(instance, '_ancien_taux_reduction', Decimal('0'))

    if nouveau_taux == ancien_taux:
        return

    accessoires = instance.accessoires.filter(actif=True)

    if nouveau_taux > 0:
        for accessoire in accessoires:
            prix_calcule = appliquer_reduction(accessoire.prix_unitaire, nouveau_taux)

            if accessoire.prix_promotionnel and accessoire.prix_promotionnel < prix_calcule:
                continue

            accessoire.prix_promotionnel = prix_calcule
            accessoire.save(update_fields=['prix_promotionnel'])

    else:
        for accessoire in accessoires:
            if accessoire.prix_promotionnel is None:
                continue

            prix_auto_precedent = appliquer_reduction(accessoire.prix_unitaire, ancien_taux)

            if accessoire.prix_promotionnel == prix_auto_precedent:
                accessoire.prix_promotionnel = None
                accessoire.save(update_fields=['prix_promotionnel'])


@receiver(post_save, sender=TypeFlacon)
def mettre_a_jour_prix_flacons(sender, instance, **kwargs):
    """
    Flacon n'a pas de prix_promotionnel dans le modèle actuel.
    Signal prêt à être activé lors de l'ajout de ce champ.
    """
    pass


# ============================================================
# ALERTS DE STOCK — NOTIFICATIONS CATALOGUE
# ============================================================
def creer_notification_alerte(type_produit, product_id, product_name, stock_actuel, seuil_alerte, metadata=None):
    """Helper pour créer une notification de catalogue."""
    from .models import NotificationCatalogue
    
    if metadata is None:
        metadata = {}
    
    message = f"⚠️ Alerte stock: {product_name} a atteint le seuil d'alerte (stock: {stock_actuel}, seuil: {seuil_alerte})"
    
    notification = NotificationCatalogue.objects.create(
        type_produit=type_produit,
        product_id=product_id,
        product_name=product_name,
        stock_actuel=stock_actuel,
        seuil_alerte=seuil_alerte,
        message=message,
        metadata=metadata
    )
    return notification


# --- LotEssence ---
@receiver(pre_save, sender=LotEssence)
def capturer_ancien_stock_lot_essence(sender, instance, **kwargs):
    """Capture l'ancien stock pour détecter les baisses."""
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
    """Crée une notification si LotEssence atteint le seuil d'alerte."""
    ancien_stock = getattr(instance, '_ancien_stock_ml', None)
    
    if (instance.seuil_alerte_ml is not None and 
        instance.stock_ml <= instance.seuil_alerte_ml):
        
        # Nouvelle alerte ou baisse en dessous du seuil
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_ml:
            metadata = {
                'essence_id': instance.essence_id,
                'essence_name': instance.essence.nom_complet,
                'lot_id': instance.id,
            }
            creer_notification_alerte(
                type_produit='lot_essence',
                product_id=instance.id,
                product_name=f"{instance.essence.nom_complet} (Lot)",
                stock_actuel=instance.stock_ml,
                seuil_alerte=instance.seuil_alerte_ml,
                metadata=metadata
            )


# --- Accessoire ---
@receiver(pre_save, sender=Accessoire)
def capturer_ancien_stock_accessoire(sender, instance, **kwargs):
    """Capture l'ancien stock pour détecter les baisses."""
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
    """Crée une notification si Accessoire atteint le seuil d'alerte."""
    ancien_stock = getattr(instance, '_ancien_stock_quantite', None)
    
    if instance.stock_quantite <= instance.seuil_alerte_stock:
        # Nouvelle alerte ou baisse en dessous du seuil
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_stock:
            metadata = {
                'type_accessoire': instance.type_accessoire.nom if instance.type_accessoire else 'N/A',
                'sku': instance.reference_sku,
            }
            creer_notification_alerte(
                type_produit='accessoire',
                product_id=instance.id,
                product_name=instance.nom,
                stock_actuel=instance.stock_quantite,
                seuil_alerte=instance.seuil_alerte_stock,
                metadata=metadata
            )


# --- Flacon ---
@receiver(pre_save, sender=Flacon)
def capturer_ancien_stock_flacon(sender, instance, **kwargs):
    """Capture l'ancien stock pour détecter les baisses."""
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
    """Crée une notification si Flacon atteint le seuil d'alerte."""
    ancien_stock = getattr(instance, '_ancien_stock_quantite', None)
    
    if instance.stock_quantite <= instance.seuil_alerte_stock:
        # Nouvelle alerte ou baisse en dessous du seuil
        if ancien_stock is None or ancien_stock > instance.seuil_alerte_stock:
            metadata = {
                'type_flacon': instance.type_flacon.nom if instance.type_flacon else 'N/A',
                'contenance_ml': instance.contenance_ml,
                'sku': instance.reference_sku,
            }
            creer_notification_alerte(
                type_produit='flacon',
                product_id=instance.id,
                product_name=f"{instance.nom} ({instance.contenance_ml}ml)",
                stock_actuel=instance.stock_quantite,
                seuil_alerte=instance.seuil_alerte_stock,
                metadata=metadata
            )

