# catalogue/signals.py
import json
import logging
import requests

from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save, m2m_changed
from django.dispatch import receiver
from .models import (
    CategorieParfum, TypeAccessoire, TypeFlacon, Essence,
    Accessoire, Flacon, LotEssence, Ingredient, Parfum, ProduitFiniEssence,
)

logger = logging.getLogger(__name__)


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


def _build_essence_embedding_text(instance):
    parts = [instance.nom or '']
    if instance.description_ia:
        parts.append(instance.description_ia)
    elif instance.description:
        parts.append(instance.description)

    for field_name in ('notes_tete', 'notes_coeur', 'notes_fond'):
        value = getattr(instance, field_name, None)
        if value:
            parts.append(value)

    if instance.categorie:
        parts.append(str(instance.get_categorie_display() if hasattr(instance, 'get_categorie_display') else instance.categorie))
    if instance.marque:
        parts.append(instance.marque)

    try:
        tags = instance.tags.all().values_list('nom', flat=True)
        tags_text = ' '.join([tag for tag in tags if tag])
        if tags_text:
            parts.append(tags_text)
    except Exception:
        pass

    text = ' '.join([part.strip() for part in parts if part and part.strip()])
    return text.strip() if text else instance.nom or ''


def _build_parfum_embedding_text(instance):
    parts = [instance.nom or '']
    if instance.description_ia:
        parts.append(instance.description_ia)
    elif instance.description_longue:
        parts.append(instance.description_longue)
    elif instance.description_courte:
        parts.append(instance.description_courte)

    for field_name in ('notes_tete', 'notes_coeur', 'notes_fond'):
        value = getattr(instance, field_name, None)
        if value:
            parts.append(value)

    if instance.marque:
        parts.append(instance.marque)
    if instance.categorie:
        parts.append(str(instance.categorie.nom if instance.categorie else instance.categorie))

    try:
        tags = instance.tags.all().values_list('nom', flat=True)
        tags_text = ' '.join([tag for tag in tags if tag])
        if tags_text:
            parts.append(tags_text)
    except Exception:
        pass

    text = ' '.join([part.strip() for part in parts if part and part.strip()])
    return text.strip() if text else instance.nom or ''


def _build_accessoire_embedding_text(instance):
    parts = [instance.nom or '']
    if instance.description_longue:
        parts.append(instance.description_longue)
    elif instance.description_courte:
        parts.append(instance.description_courte)

    if instance.marque:
        parts.append(instance.marque)
    if instance.type_accessoire:
        parts.append(str(instance.type_accessoire.nom if hasattr(instance.type_accessoire, 'nom') else instance.type_accessoire))
    if instance.matiere:
        parts.append(instance.matiere)
    if instance.couleur:
        parts.append(instance.couleur)
    if instance.taille:
        parts.append(instance.taille)

    text = ' '.join([part.strip() for part in parts if part and part.strip()])
    return text.strip() if text else instance.nom or ''


def _generate_ollama_embedding(text):
    if not text:
        return None

    ollama_url = getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    model_name = getattr(settings, 'OLLAMA_EMBEDDING_MODEL', 'all-minilm')
    timeout_seconds = int(getattr(settings, 'OLLAMA_TIMEOUT_SECONDS', '30'))

    payload = {
        'model': model_name,
        'input': [text],
    }

    try:
        response = requests.post(
            f"{ollama_url}/v1/embeddings",
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get('embeddings') or data.get('results')
        if isinstance(embeddings, list) and embeddings:
            first = embeddings[0]
            if isinstance(first, dict) and 'embedding' in first:
                return first['embedding']
            return first
        logger.warning('Ollama embeddings returned unexpected shape: %s', data)
    except requests.exceptions.RequestException as exc:
        logger.exception('Erreur HTTP Ollama embeddings')
    except ValueError:
        logger.exception('Réponse Ollama embeddings JSON invalide')

    return None


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


@receiver(post_save, sender=Essence)
def construire_embedding_essence(sender, instance, created, **kwargs):
    """Génère et stocke l'embedding de l'essence après sauvegarde."""
    text = _build_essence_embedding_text(instance)
    embedding = _generate_ollama_embedding(text)
    if embedding is not None:
        Essence.objects.filter(pk=instance.pk).update(embedding=embedding)


@receiver(post_save, sender=Parfum)
def construire_embedding_parfum(sender, instance, created, **kwargs):
    """Génère et stocke l'embedding du parfum après sauvegarde."""
    text = _build_parfum_embedding_text(instance)
    embedding = _generate_ollama_embedding(text)
    if embedding is not None:
        Parfum.objects.filter(pk=instance.pk).update(embedding=embedding)


@receiver(m2m_changed, sender=Parfum.tags.through)
def mettre_a_jour_embedding_parfum_tags(sender, instance, action, **kwargs):
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return

    text = _build_parfum_embedding_text(instance)
    embedding = _generate_ollama_embedding(text)
    if embedding is not None:
        Parfum.objects.filter(pk=instance.pk).update(embedding=embedding)


@receiver(post_save, sender=Accessoire)
def construire_embedding_accessoire(sender, instance, created, **kwargs):
    """Génère et stocke l'embedding de l'accessoire après sauvegarde."""
    text = _build_accessoire_embedding_text(instance)
    embedding = _generate_ollama_embedding(text)
    if embedding is not None:
        Accessoire.objects.filter(pk=instance.pk).update(embedding=embedding)


@receiver(m2m_changed, sender=Essence.tags.through)
def mettre_a_jour_embedding_essence_tags(sender, instance, action, **kwargs):
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return

    text = _build_essence_embedding_text(instance)
    embedding = _generate_ollama_embedding(text)
    if embedding is not None:
        Essence.objects.filter(pk=instance.pk).update(embedding=embedding)


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



