from django.db.models import Count, Q, Case, When, Value, IntegerField


def get_similar_products(instance, model, tag_field='tags', limit=6):
    """
    Sélectionne les produits similaires pour un produit donné :
    - Priorité 1 : Produits ayant les mêmes valeurs de tags (ex: temps=nuit)
    - Priorité 2 : Produits de la même marque (marque)
    - Trier par : Priorité (1 puis 2), nombre de valeurs en commun (décroissant), date de création (-date_creation)
    - Limite : 6 produits max.
    """
    if not instance.pk:
        return model.objects.none()

    # 1. Extraction des sous-tokens (tag_id, valeur) associés au produit
    tokens = []
    if hasattr(instance, 'tags_associes'):
        for ta in instance.tags_associes.all():
            if ta.valeur and str(ta.valeur).strip():
                parts = [p.strip() for p in str(ta.valeur).split(',') if p.strip()]
                for part in parts:
                    tokens.append((ta.tag_id, part))

    # 2. Marque du produit
    marque_val = getattr(instance, 'marque', None)
    has_marque = bool(marque_val and str(marque_val).strip() and str(marque_val).strip().lower() != 'non indiquée')

    if not tokens and not has_marque:
        return model.objects.none()

    qs = model.objects.filter(actif=True).exclude(pk=instance.pk)

    q_tag_valeurs = Q()
    for tag_id, val in tokens:
        q_tag_valeurs |= (Q(tags_associes__tag_id=tag_id) & Q(tags_associes__valeur__icontains=val))

    q_marque = Q(marque__iexact=marque_val.strip()) if has_marque else Q(pk__in=[])

    if tokens:
        qs = qs.filter(q_tag_valeurs | q_marque).annotate(
            communs_valeurs=Count('tags_associes', filter=q_tag_valeurs, distinct=True),
            priority=Case(
                When(communs_valeurs__gt=0, then=Value(1)),
                When(q_marque, then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            )
        ).order_by('priority', '-communs_valeurs', '-date_creation')
    elif has_marque:
        qs = qs.filter(q_marque).annotate(
            communs_valeurs=Value(0),
            priority=Value(1, output_field=IntegerField())
        ).order_by('-date_creation')

    return qs.distinct()[:limit]


# ============================================================
# COMPRESSION ET CONVERSION DES IMAGES EN WEBP (QUALITÉ 80%)
# ============================================================
import io
import os
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile


def compress_image_to_webp(image_field, max_dimension=1600, quality=80):
    """
    Compress et convertit une image de type ImageField au format WebP.
    - Qualité : 80%
    - Dimension max : 1600px par défaut (garde le ratio d'aspect)
    - Gestion de l'orientation EXIF
    - Conservation de la transparence pour PNG/RGBA
    """
    if not image_field:
        return None

    try:
        file_obj = getattr(image_field, 'file', None)
        if not file_obj:
            return None
    except Exception:
        return None

    # Vérification si c'est un nouveau fichier uploadé
    is_uploaded = isinstance(file_obj, UploadedFile)
    filename = getattr(image_field, 'name', '') or ''
    is_webp = filename.lower().endswith('.webp')

    # Si le fichier n'est pas nouvellement uploadé et est déjà en .webp, ne pas recompresser
    if not is_uploaded and is_webp:
        return None

    try:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        img = Image.open(file_obj)

        # Orientation EXIF automatique
        img = ImageOps.exif_transpose(img)

        # Gestion du mode couleur (Transparence vs RGB)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGBA')
        else:
            img = img.convert('RGB')

        # Redimensionnement si > max_dimension
        w, h = img.size
        if w > max_dimension or h > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        # Enregistrement WebP en mémoire avec qualité 80%
        output = io.BytesIO()
        img.save(output, format='WEBP', quality=quality, optimize=True)
        output.seek(0)

        # Génération du nouveau nom de fichier avec extension .webp
        base_name = os.path.splitext(os.path.basename(filename))[0] if filename else 'image'
        new_filename = f"{base_name}.webp"

        return ContentFile(output.getvalue(), name=new_filename)
    except Exception:
        return None


def compress_model_images(instance, image_field_names, max_dimension=1600, quality=80):
    """
    Parcourt tous les champs d'images spécifiés d'un modèle et les compresse en WebP (qualité 80%).
    À appeler dans un signal pre_save.
    """
    for field_name in image_field_names:
        image_field = getattr(instance, field_name, None)
        if image_field:
            new_content = compress_image_to_webp(image_field, max_dimension=max_dimension, quality=quality)
            if new_content:
                image_field.save(new_content.name, new_content, save=False)



