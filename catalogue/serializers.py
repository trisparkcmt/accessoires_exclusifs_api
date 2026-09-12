# serializers.py
from decimal import Decimal
import json
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from .utils import get_similar_products

from .models import CategorieParfum, LotEssence, ProduitFiniEssence, Tag, TagParfum, TagEssence, TagAccessoire, Parfum, Essence, Accessoire, Flacon, TypeAccessoire, TypeFlacon, Favori, Ingredient, NotificationCatalogue, MouvementStock, DiffuseurParfum, EntrepriseInfo


# catalogue/serializers.py (ajouter après les imports existants)

class ParfumSimilaireSerializer(serializers.ModelSerializer):
    prix_actuel = serializers.SerializerMethodField()
    image_principale = serializers.SerializerMethodField()

    class Meta:
        model = Parfum
        fields = ['id', 'nom', 'slug', 'prix_actuel', 'image_principale']

    def get_prix_actuel(self, obj):
        prix = obj.prix_promotionnel or obj.prix_unitaire
        return formater_prix(prix)

    def get_image_principale(self, obj):
        return get_image_url(self.context.get('request'), obj.image_principale)


class AccessoireSimilaireSerializer(serializers.ModelSerializer):
    prix_actuel = serializers.SerializerMethodField()
    image_principale = serializers.SerializerMethodField()

    class Meta:
        model = Accessoire
        fields = ['id', 'nom', 'slug', 'prix_actuel', 'image_principale']

    def get_prix_actuel(self, obj):
        prix = obj.prix_promotionnel or obj.prix_unitaire
        return formater_prix(prix)

    def get_image_principale(self, obj):
        return get_image_url(self.context.get('request'), obj.image_principale)
    

# ============================================================
# HELPER
# ============================================================
def formater_prix(valeur):
    """
    Formate un Decimal en str avec 2 décimales,
    cohérent avec le format DRF (DecimalField → '25000.00').
    """
    return str(valeur.quantize(Decimal('0.01')))

def get_image_url(request, image_field):
    """
    Retourne l'URL absolue d'un ImageField.
    Ex : https://d3fr3l8gi93hp1.cloudfront.net/parfums/royal-oud/image.jpg
    Retourne None si pas d'image.
    """
    if not image_field:
        return None
    try:
        url = image_field.url
    except Exception:
        return None
    if url.startswith('http://') or url.startswith('https://'):
        return url
    if request:
        return request.build_absolute_uri(url)
    return url



# TAGS

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Tag
        fields = ['id', 'nom', 'slug']


class TagParfumSerializer(serializers.ModelSerializer):
    tag_nom = serializers.CharField(source='tag.nom', read_only=True)

    class Meta:
        model = TagParfum
        fields = ['id', 'tag', 'tag_nom', 'valeur']


class TagEssenceSerializer(serializers.ModelSerializer):
    tag_nom = serializers.CharField(source='tag.nom', read_only=True)

    class Meta:
        model = TagEssence
        fields = ['id', 'tag', 'tag_nom', 'valeur']


class TagAccessoireSerializer(serializers.ModelSerializer):
    tag_nom = serializers.CharField(source='tag.nom', read_only=True)

    class Meta:
        model = TagAccessoire
        fields = ['id', 'tag', 'tag_nom', 'valeur']


def _sauvegarder_tags(instance, tags_input, model_liaison, fk_field_name):
    if tags_input is None:
        return
    model_liaison.objects.filter(**{fk_field_name: instance}).delete()
    for item in tags_input:
        if isinstance(item, dict):
            tag_id = item.get('tag') or item.get('tag_id')
            if isinstance(tag_id, Tag):
                tag_id = tag_id.id
            valeur = item.get('valeur', '')
            if tag_id:
                model_liaison.objects.create(**{fk_field_name: instance, 'tag_id': tag_id, 'valeur': valeur})
        elif isinstance(item, Tag):
            model_liaison.objects.create(**{fk_field_name: instance, 'tag': item, 'valeur': ''})
        elif isinstance(item, int):
            model_liaison.objects.create(**{fk_field_name: instance, 'tag_id': item, 'valeur': ''})


class TagSelectSerializer(serializers.ModelSerializer):
    libelle = serializers.CharField(source='nom', read_only=True)

    class Meta:
        model = Tag
        fields = ['id', 'libelle', 'nom', 'slug']


class JourOuvertureSerializer(serializers.Serializer):
    jour = serializers.CharField(required=True)
    ouvert = serializers.BooleanField(required=True)
    heure_ouverture = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    heure_fermeture = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        ouvert = attrs.get('ouvert', True)
        if ouvert:
            if not attrs.get('heure_ouverture') or not attrs.get('heure_fermeture'):
                raise serializers.ValidationError({
                    'heure_ouverture': 'Les horaires sont requis pour un jour ouvert.',
                    'heure_fermeture': 'Les horaires sont requis pour un jour ouvert.'
                })
        return attrs


class EntrepriseInfoSerializer(serializers.ModelSerializer):
    jours_ouverture = serializers.ListField(
        child=JourOuvertureSerializer(),
        required=False,
        allow_empty=True,
        default=list,
    )

    class Meta:
        model = EntrepriseInfo
        fields = [
            'id', 'nom', 'jours_ouverture', 'telephone_principal',
            'telephone_secondaire', 'whatsapp', 'facebook_url',
            'instagram_url', 'localisation', 'date_creation', 'date_modification'
        ]



# PARFUMS

class ParfumSerializer(serializers.ModelSerializer):
    tags = serializers.JSONField(required=False, allow_null=True)
    famille_olfactive   = serializers.ListField(child=serializers.CharField(), read_only=True)
    humeurs_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    occasions           = serializers.ListField(child=serializers.CharField(), read_only=True)
    saisons_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    prix_actuel         = serializers.SerializerMethodField()
    taux_reduction      = serializers.SerializerMethodField()
    en_promotion        = serializers.SerializerMethodField()
    image_principale    = serializers.ImageField(required=False, allow_null=True)
    image_supp_1        = serializers.ImageField(required=False, allow_null=True)
    image_supp_2        = serializers.ImageField(required=False, allow_null=True)
    image_supp_3        = serializers.ImageField(required=False, allow_null=True)
    image_supp_4        = serializers.ImageField(required=False, allow_null=True)
    produits_similaires = serializers.SerializerMethodField()
    is_favori = serializers.SerializerMethodField()

    class Meta:
        model  = Parfum
        fields = [
            'id', 'marque','nom', 'slug', 'reference_sku',
            'description_courte', 'contenance_ml',
            'prix_unitaire', 'prix_actuel',
            'prix_promotionnel', 'date_debut', 'date_fin',
            'taux_reduction', 'en_promotion',
            'genre_cible', 'intensite',
            'notes_tete', 'notes_coeur', 'notes_fond',
            'tags', 'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles',
            'est_nouveau', 'est_bestseller',
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4',  'stock_quantite', 'seuil_alerte_stock',
            'date_creation','produits_similaires', 'is_favori', 'categorie','description_longue','description_ia',
        ]

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', None)
        parfum = super().create(validated_data)
        if tags_data is not None:
            _sauvegarder_tags(parfum, tags_data, TagParfum, 'parfum')
        return parfum

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        parfum = super().update(instance, validated_data)
        if tags_data is not None:
            _sauvegarder_tags(parfum, tags_data, TagParfum, 'parfum')
        return parfum

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['tags'] = TagParfumSerializer(instance.tags_associes.all(), many=True).data
        representation['image_principale'] = get_image_url(self.context.get('request'), instance.image_principale)
        for i in range(1, 5):
            img_field = f'image_supp_{i}'
            representation[img_field] = get_image_url(self.context.get('request'), getattr(instance, img_field))
        return representation

    @extend_schema_field(OpenApiTypes.STR)
    def get_prix_actuel(self, obj):
        """
        Retourne le prix final en str formatée '25000.00'.
        Priorité : prix_promotionnel > prix_unitaire.
        """
        prix = obj.prix_actuel
        return formater_prix(prix)

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_taux_reduction(self, obj):
        """
        Calcule le taux affiché au client.
        Retourne None si aucune réduction n'est appliquée.
        """
        promo = obj.prix_promotionnel_effectif
        if not promo:
            return None
        taux = (1 - promo / obj.prix_unitaire) * 100
        return round(float(taux), 1)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_en_promotion(self, obj):
        return obj.prix_promotionnel_effectif is not None

    def get_produits_similaires(self, obj):
        from .utils import get_similar_products
        from .models import Parfum
        similaires = get_similar_products(obj, Parfum, limit=6)
        return ParfumSimilaireSerializer(similaires, many=True, context=self.context).data
  
    def get_is_favori(self, obj):
        request = self.context.get('request')
        # On vérifie si l'utilisateur est connecté[cite: 11]
        if request and request.user.is_authenticated:
            try:
                # On récupère le profil client
                client = request.user.client
                # On filtre spécifiquement sur le champ 'parfum' du modèle Favori
                return Favori.objects.filter(client=client, parfum=obj).exists()
            except AttributeError:
                return False
        return False
# ============================================================

# PARFUMS : sérialiseurs admin/public + list/detail
# ============================================================

class ParfumAdminListSerializer(ParfumSerializer):
    """Admin : liste (sans produits similaires, avec prix d'achat et bénéfice)"""
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(ParfumSerializer.Meta):
        fields = [f for f in ParfumSerializer.Meta.fields if f != 'produits_similaires'] + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat is not None and obj.prix_unitaire:
            prix_vente = obj.prix_promotionnel if (obj.prix_promotionnel is not None) else obj.prix_unitaire
            return str((prix_vente - obj.prix_achat).quantize(Decimal('0.01')))
        return None

class ParfumAdminDetailSerializer(ParfumSerializer):
    """Admin : détail (avec produits similaires et prix d'achat)"""
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(ParfumSerializer.Meta):
        fields = ParfumSerializer.Meta.fields + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat is not None and obj.prix_unitaire:
            prix_vente = obj.prix_promotionnel if (obj.prix_promotionnel is not None) else obj.prix_unitaire
            return str((prix_vente - obj.prix_achat).quantize(Decimal('0.01')))
        return None

class ParfumPublicListSerializer(ParfumSerializer):
    """Public : liste (sans produits similaires, champs réduits)"""
    class Meta(ParfumSerializer.Meta):
        fields = [f for f in ParfumSerializer.Meta.fields if f not in ('produits_similaires', 'reference_sku',  'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'taux_reduction','description_courte',
            'notes_tete', 'notes_coeur', 'notes_fond',
            'tags', 'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles',)]

class ParfumPublicDetailSerializer(ParfumSerializer):
    """Public : détail (avec produits similaires)"""
    class Meta(ParfumSerializer.Meta):
        fields = [f for f in ParfumSerializer.Meta.fields if f not in ('reference_sku',  'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4')]
    
# ============================================================
# INGREDIENTS
# ============================================================
class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Ingredient
        fields = [
            'id', 'nom', 'slug', 'description',
            'prix_par_ml', 'stock_ml', 'seuil_alerte_ml', 'actif',
            'date_creation',
        ]


class IngredientAdminSerializer(serializers.ModelSerializer):
    """Ingrédient avec prix d'achat (admin uniquement)"""
    class Meta:
        model  = Ingredient
        fields = [
            'id', 'nom', 'slug', 'description',
            'prix_par_ml', 'prix_achat_par_ml',
            'stock_ml', 'seuil_alerte_ml', 'actif',
            'date_creation',
        ]


# ============================================================
# ESSENCES (catalogue complet pour admin)
# ============================================================
class EssenceSerializer(serializers.ModelSerializer):
    tags = serializers.JSONField(required=False, allow_null=True)
    famille_olfactive = serializers.ListField(child=serializers.CharField(), read_only=True)
    humeurs_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    occasions = serializers.ListField(child=serializers.CharField(), read_only=True)
    saisons_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    signes_astrologiques_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    moments_journee = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Essence
        fields = [
            'id', 'marque', 'nom', 'slug', 'categorie', 'code_reference',
            'description', 'description_ia', 'fournisseur', 'origine_pays',
            'concentration_max', 'couleur', 'duree',
            'intensite', 'genre_cible',
            'notes_tete', 'notes_coeur', 'notes_fond',
            'tags', 'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles',
            'signes_astrologiques_compatibles', 'moments_journee',
            'prix_par_ml', 'seuil_alerte_ml', 'actif', 'date_creation', 'date_modification'
        ]

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', None) or validated_data.pop('tag_ids', None)
        essence = super().create(validated_data)
        if tags_data is not None:
            _sauvegarder_tags(essence, tags_data, TagEssence, 'essence')
        return essence

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None) or validated_data.pop('tag_ids', None)
        essence = super().update(instance, validated_data)
        if tags_data is not None:
            _sauvegarder_tags(essence, tags_data, TagEssence, 'essence')
        return essence

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['tags'] = TagEssenceSerializer(instance.tags_associes.all(), many=True).data
        ret['stock_total_ml'] = instance.stock_total_ml()
        ret['produits_finis'] = ProduitFiniEssenceInlineSerializer(
            instance.produits_finis.all(),
            many=True,
            context=self.context
        ).data
        return ret
# ============================================================
# ESSENCES : pour le labo et le catalogue
# ============================================================

class EssenceLaboListSerializer(serializers.ModelSerializer):
    stock_total_ml = serializers.SerializerMethodField()
    prix_par_ml = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Essence
        fields = ['id', 'marque', 'nom', 'categorie', 'stock_total_ml', 'prix_par_ml']

    def get_stock_total_ml(self, obj):
        return obj.stock_total_ml()


class EssenceLaboDetailSerializer(EssenceSerializer):
    stock_total_ml = serializers.SerializerMethodField()

    class Meta(EssenceSerializer.Meta):
        fields = EssenceSerializer.Meta.fields + ['stock_total_ml']

    def get_stock_total_ml(self, obj):
        return getattr(obj, 'total_stock_ml', obj.stock_total_ml())

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Pour le laboratoire, les produits finis pré-conditionnés ne sont pas nécessaires
        ret.pop('produits_finis', None)
        return ret

# ============================================================
# CATALOGUE : produits finis (essences vendues en flacon)
# ============================================================

class ProduitFiniEssenceInlineSerializer(serializers.ModelSerializer):
    """Présentation simplifiée des formats/tailles disponibles d'une essence dans la boutique."""
    stock_disponible = serializers.SerializerMethodField()

    class Meta:
        model = ProduitFiniEssence
        fields = [
            'id', 'taille_ml', 'prix', 'prix_promotionnel', 'prix_actuel',
            'stock_disponible', 'actif'
        ]

    @extend_schema_field(OpenApiTypes.INT)
    def get_stock_disponible(self, obj):
        if obj.taille_ml > 0:
            return int(obj.essence.stock_total_ml() // obj.taille_ml)
        return 0


class EssencePublicSerializer(serializers.ModelSerializer):
    """Informations publiques d'une essence parente pour la boutique (incluant ses formats de produits finis)."""
    famille_olfactive = serializers.ListField(child=serializers.CharField(), read_only=True)
    humeurs_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    occasions = serializers.ListField(child=serializers.CharField(), read_only=True)
    saisons_compatibles = serializers.ListField(child=serializers.CharField(), read_only=True)
    moments_journee = serializers.ListField(child=serializers.CharField(), read_only=True)
    stock_total_ml = serializers.SerializerMethodField()
    produits_finis = serializers.SerializerMethodField()

    class Meta:
        model = Essence
        fields = [
            'id', 'marque', 'nom', 'slug', 'categorie', 'code_reference',
            'description', 'origine_pays', 'concentration_max', 'couleur',
            'duree', 'intensite', 'genre_cible',
            'notes_tete', 'notes_coeur', 'notes_fond',
            'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles', 'moments_journee',
            'prix_par_ml', 'actif', 'stock_total_ml', 'produits_finis',
        ]

    def get_stock_total_ml(self, obj):
        return obj.stock_total_ml()

    def get_produits_finis(self, obj):
        stock_total = obj.stock_total_ml()
        if stock_total <= 0:
            return []
        prods = obj.produits_finis.filter(
            actif=True,
            prix__gt=0,
            taille_ml__gt=0,
            taille_ml__lte=stock_total
        )
        return ProduitFiniEssenceInlineSerializer(prods.order_by('taille_ml'), many=True, context=self.context).data


class ProduitFiniEssencePublicSerializer(serializers.ModelSerializer):
    marque = serializers.CharField(source='essence.marque', read_only=True)
    nom = serializers.CharField(source='essence.nom', read_only=True)
    categorie = serializers.CharField(source='essence.categorie', read_only=True)
    essence_details = EssencePublicSerializer(source='essence', read_only=True)
    stock_disponible = serializers.SerializerMethodField()
    is_favori = serializers.SerializerMethodField()

    class Meta:
        model = ProduitFiniEssence
        fields = ['id', 'essence', 'essence_details', 'marque', 'nom', 'categorie', 'taille_ml', 'prix', 'prix_promotionnel', 'prix_actuel', 'stock_disponible', 'is_favori', 'actif']

    @extend_schema_field(OpenApiTypes.INT)
    def get_stock_disponible(self, obj):
        if obj.taille_ml > 0:
            return int(obj.essence.stock_total_ml() // obj.taille_ml)
        return 0

    def get_is_favori(self, obj):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            try:
                client = request.user.client
                return Favori.objects.filter(client=client, produit_fini_essence=obj).exists()
            except Exception:
                pass
        return False

class LotEssenceSerializer(serializers.ModelSerializer):
    essence_details = EssenceLaboListSerializer(source='essence', read_only=True)
    cout_achat_total = serializers.SerializerMethodField()
    chiffre_affaires_genere = serializers.SerializerMethodField()
    benefice_lot = serializers.SerializerMethodField()
    est_termine = serializers.SerializerMethodField()

    class Meta:
        model = LotEssence
        fields = [
            'id', 'essence', 'essence_details', 'stock_ml',
            'stock_precedent_ml', 'quantite_initiale_ml',
            'prix_achat_par_ml',
            'cout_achat_total', 'chiffre_affaires_genere', 'benefice_lot', 'est_termine',
            'actif',
            'date_reception', 'reference_fournisseur'
        ]
        read_only_fields = ['date_reception', 'cout_achat_total', 'chiffre_affaires_genere', 'benefice_lot', 'est_termine']

    def create(self, validated_data):
        essence = validated_data.get('essence')
        validated_data['stock_precedent_ml'] = essence.stock_total_ml()
        return super().create(validated_data)

    def get_cout_achat_total(self, obj):
        if obj.prix_achat_par_ml and obj.quantite_initiale_ml:
            return str((obj.quantite_initiale_ml * obj.prix_achat_par_ml).quantize(Decimal('0.01')))
        return None

    def get_chiffre_affaires_genere(self, obj):
        from django.db.models import Sum
        total = obj.consommations.aggregate(total=Sum('prix_vente_attribue'))['total']
        return str(Decimal(str(total or 0)).quantize(Decimal('0.01')))

    def get_benefice_lot(self, obj):
        if not obj.prix_achat_par_ml:
            return None
        from django.db.models import Sum
        ca = obj.consommations.aggregate(total=Sum('prix_vente_attribue'))['total'] or Decimal('0')
        quantite_consommee = (obj.quantite_initiale_ml or Decimal('0')) - obj.stock_ml
        cout = quantite_consommee * obj.prix_achat_par_ml
        return str((Decimal(str(ca)) - cout).quantize(Decimal('0.01')))

    def get_est_termine(self, obj):
        return obj.stock_ml <= Decimal('0')


class ProduitFiniEssenceSerializer(serializers.ModelSerializer):
    essence_details = EssenceSerializer(source='essence', read_only=True)
    prix_actuel = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    prix_par_ml = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    stock_disponible = serializers.SerializerMethodField()

    class Meta:
        model = ProduitFiniEssence
        fields = [
            'id', 'essence', 'essence_details', 'taille_ml',
            'prix', 'prix_promotionnel', 'prix_actuel', 'prix_par_ml',
            'stock_disponible', 'actif'
        ]

    @extend_schema_field(OpenApiTypes.INT)
    def get_stock_disponible(self, obj):
        if obj.taille_ml > 0:
            return int(obj.essence.stock_total_ml() // obj.taille_ml)
        return 0

    def create(self, validated_data):
        essence = validated_data.get('essence')
        taille = validated_data.get('taille_ml')
        existing = ProduitFiniEssence.objects.filter(essence=essence, taille_ml=taille).first()
        if existing:
            return self.update(existing, validated_data)
        
        try:
            return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)

class _LotEssenceInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = LotEssence
        fields = ['stock_ml', 'quantite_initiale_ml', 'prix_achat_par_ml', 'reference_fournisseur', 'actif']
        extra_kwargs = {
            'stock_ml': {'required': False},
            'quantite_initiale_ml': {'required': False},
            'prix_achat_par_ml': {'required': False},
            'reference_fournisseur': {'required': False, 'allow_blank': True},
            'actif': {'required': False},
        }

class _ProduitFiniInputSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProduitFiniEssence
        fields = ['id', 'taille_ml', 'prix', 'prix_promotionnel', 'actif']
        extra_kwargs = {
            'prix_promotionnel': {'required': False, 'allow_null': True},
            'actif': {'required': False},
        }

class EssenceCreateFullSerializer(EssenceSerializer):
    initial_lot = _LotEssenceInputSerializer(write_only=True, required=False)
    produits_finis = _ProduitFiniInputSerializer(many=True, write_only=True, required=False)

    class Meta(EssenceSerializer.Meta):
        fields = EssenceSerializer.Meta.fields + ['initial_lot', 'produits_finis']

    def to_internal_value(self, data):
        # Support stringified JSON objects/lists for multipart/form-data requests
        if hasattr(data, 'dict'):
            data = data.dict()
        elif isinstance(data, dict):
            data = dict(data)

        initial_lot = data.get('initial_lot')
        if isinstance(initial_lot, str):
            try:
                data['initial_lot'] = json.loads(initial_lot)
            except (json.JSONDecodeError, TypeError):
                pass

        produits_finis = data.get('produits_finis')
        if isinstance(produits_finis, str):
            try:
                data['produits_finis'] = json.loads(produits_finis)
            except (json.JSONDecodeError, TypeError):
                pass

        return super().to_internal_value(data)

    def create(self, validated_data):
        lot_data = validated_data.pop('initial_lot', None)
        prods_data = validated_data.pop('produits_finis', [])
        tags = validated_data.pop('tags', [])
        
        try:
            with transaction.atomic():
                essence = Essence.objects.create(**validated_data)
                if tags:
                    essence.tags.set(tags)
                if lot_data:
                    LotEssence.objects.create(essence=essence, stock_precedent_ml=0, **lot_data)
                for prod in prods_data:
                    ProduitFiniEssence.objects.create(essence=essence, **prod)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
        return essence

    def update(self, instance, validated_data):
        lot_data = validated_data.pop('initial_lot', None)
        prods_data = validated_data.pop('produits_finis', None)
        tags = validated_data.pop('tags', None)

        try:
            with transaction.atomic():
                essence = super().update(instance, validated_data)
                if tags is not None:
                    essence.tags.set(tags)
                if lot_data:
                    LotEssence.objects.create(
                        essence=essence,
                        stock_precedent_ml=essence.stock_total_ml(),
                        **lot_data
                    )
                if prods_data is not None:
                    for prod in prods_data:
                        prod_id = prod.get('id')
                        taille = prod.get('taille_ml')
                        if prod_id:
                            ProduitFiniEssence.objects.filter(id=prod_id, essence=essence).update(**prod)
                        elif taille:
                            ProduitFiniEssence.objects.update_or_create(
                                essence=essence,
                                taille_ml=taille,
                                defaults=prod
                            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
        return essence

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['stock_total_ml'] = instance.stock_total_ml()
        ret['produits_finis'] = ProduitFiniEssenceInlineSerializer(
            instance.produits_finis.all(),
            many=True,
            context=self.context
        ).data
        return ret
        
class EssenceLaboSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    marque = serializers.CharField()
    nom = serializers.CharField()
    categorie = serializers.CharField()
    stock_total_ml = serializers.DecimalField(max_digits=12, decimal_places=2)
    prix_moyen_ml = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField()
    intensite = serializers.CharField()
    genre_cible = serializers.CharField()
    notes_tete = serializers.CharField()
    notes_coeur = serializers.CharField()
    notes_fond = serializers.CharField()
# ============================================================
# ACCESSOIRES
# ============================================================
class TypeAccessoireSerializer(serializers.ModelSerializer):
    icone = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model  = TypeAccessoire
        fields = [
            'id', 'nom', 'slug', 'description', 'icone',
            'actif', 'taux_reduction', 'date_debut', 'date_fin',
            'message_promotion', 'date_creation'
        ]
        read_only_fields = ['date_creation']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['icone'] = get_image_url(self.context.get('request'), instance.icone)
        return representation



class AccessoireSerializer(serializers.ModelSerializer):
    type_accessoire = serializers.PrimaryKeyRelatedField(queryset=TypeAccessoire.objects.all())
    tags            = serializers.JSONField(required=False, allow_null=True)
    prix_actuel     = serializers.SerializerMethodField()
    taux_reduction  = serializers.SerializerMethodField()
    en_promotion    = serializers.SerializerMethodField()
    image_principale = serializers.ImageField(required=False, allow_null=True)
    image_supp_1     = serializers.ImageField(required=False, allow_null=True)
    image_supp_2     = serializers.ImageField(required=False, allow_null=True)
    image_supp_3     = serializers.ImageField(required=False, allow_null=True)
    image_supp_4     = serializers.ImageField(required=False, allow_null=True)
    produits_similaires = serializers.SerializerMethodField()
    is_favori = serializers.SerializerMethodField()

    class Meta:
        model  = Accessoire
        fields = [
            'id', 'marque', 'nom', 'slug', 'reference_sku',
            'type_accessoire', 'tags',
            'description_courte', 'description_longue',
            'matiere', 'couleur', 'taille',
            'prix_unitaire', 'prix_promotionnel', 'prix_actuel',
            'date_debut', 'date_fin',
            'taux_reduction', 'en_promotion',
            'stock_quantite', 'seuil_alerte_stock', 'poids_grammes',
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4',
            'actif', 'est_bestseller', 'est_hotseller',
            'date_creation', 'date_modification', 'produits_similaires', 'is_favori',
        ]
        read_only_fields = ['date_creation', 'date_modification']

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', None)
        accessoire = super().create(validated_data)
        if tags_data is not None:
            _sauvegarder_tags(accessoire, tags_data, TagAccessoire, 'accessoire')
        return accessoire

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        accessoire = super().update(instance, validated_data)
        if tags_data is not None:
            _sauvegarder_tags(accessoire, tags_data, TagAccessoire, 'accessoire')
        return accessoire

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['tags'] = TagAccessoireSerializer(instance.tags_associes.all(), many=True).data
        if instance.type_accessoire:
            representation['type_accessoire'] = TypeAccessoireSerializer(instance.type_accessoire, context=self.context).data
        representation['image_principale'] = get_image_url(self.context.get('request'), instance.image_principale)
        for i in range(1, 5):
            img_field = f'image_supp_{i}'
            representation[img_field] = get_image_url(self.context.get('request'), getattr(instance, img_field))
        return representation

    @extend_schema_field(OpenApiTypes.STR)
    def get_prix_actuel(self, obj):
        prix = obj.prix_actuel
        return formater_prix(prix)

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_taux_reduction(self, obj):
        promo = obj.prix_promotionnel_effectif
        if not promo:
            return None
        taux = (1 - promo / obj.prix_unitaire) * 100
        return round(float(taux), 1)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_en_promotion(self, obj):
        return obj.prix_promotionnel_effectif is not None

    def get_produits_similaires(self, obj):
        from .utils import get_similar_products
        similaires = get_similar_products(obj, Accessoire, limit=6)
        return AccessoireSimilaireSerializer(similaires, many=True, context=self.context).data

    def get_is_favori(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                client = request.user.client
                # On filtre spécifiquement sur le champ 'accessoire' du modèle Favori
                return Favori.objects.filter(client=client, accessoire=obj).exists()
            except AttributeError:
                return False
        return False
# ============================================================
# ACCESSOIRES : sérialiseurs admin/public + list/detail
# ============================================================

class AccessoireAdminListSerializer(AccessoireSerializer):
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(AccessoireSerializer.Meta):
        fields = [f for f in AccessoireSerializer.Meta.fields if f != 'produits_similaires'] + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat and obj.prix_unitaire:
            return str((obj.prix_unitaire - obj.prix_achat).quantize(Decimal('0.01')))
        return None

class AccessoireAdminDetailSerializer(AccessoireSerializer):
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(AccessoireSerializer.Meta):
        fields = AccessoireSerializer.Meta.fields + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat and obj.prix_unitaire:
            return str((obj.prix_unitaire - obj.prix_achat).quantize(Decimal('0.01')))
        return None

class AccessoirePublicListSerializer(AccessoireSerializer):
    class Meta(AccessoireSerializer.Meta):
       fields = [f for f in AccessoireSerializer.Meta.fields if f not in ('description_courte',
            'matiere', 'couleur', 'taille','poids_grammes','produits_similaires', 'reference_sku',  'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4','taux_reduction')] 

class AccessoirePublicDetailSerializer(AccessoireSerializer):
    class Meta(AccessoireSerializer.Meta):
        fields = [f for f in AccessoireSerializer.Meta.fields if f not in ('reference_sku',  'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4')]

# ============================================================
# FLACONS
# ============================================================
class TypeFlaconSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)
    class Meta:
        model  = TypeFlacon
        fields = [
            'id', 'nom', 'slug', 'description', 'image',
            'actif', 'taux_reduction', 'date_creation'
        ]
        read_only_fields = ['date_creation']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['image'] = get_image_url(self.context.get('request'), instance.image)
        return representation


class FlaconSerializer(serializers.ModelSerializer):
    type_flacon = serializers.PrimaryKeyRelatedField(queryset=TypeFlacon.objects.all())
    stock_suffisant = serializers.SerializerMethodField()
    image_principale = serializers.ImageField(required=False, allow_null=True)
    image_supp_1     = serializers.ImageField(required=False, allow_null=True)
    image_supp_2     = serializers.ImageField(required=False, allow_null=True)
    image_supp_3     = serializers.ImageField(required=False, allow_null=True)
    image_supp_4     = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model  = Flacon
        fields = ['slug',
            'id', 'nom', 'reference_sku',
            'type_flacon',
            'contenance_ml',
            'matiere', 'couleur',
            'hauteur_cm', 'largeur_cm', 'poids_grammes',
            'prix_unitaire', 'stock_quantite',
            'seuil_alerte_stock', 'stock_suffisant',
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4',
            'actif', 'date_creation', 'date_modification',
        ]
        read_only_fields = ['date_creation', 'date_modification']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.type_flacon:
            representation['type_flacon'] = TypeFlaconSerializer(instance.type_flacon, context=self.context).data
        representation['image_principale'] = get_image_url(self.context.get('request'), instance.image_principale)
        for i in range(1, 5):
            img_field = f'image_supp_{i}'
            representation[img_field] = get_image_url(self.context.get('request'), getattr(instance, img_field))
        return representation

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_stock_suffisant(self, obj) -> bool:
        return obj.stock_quantite > obj.seuil_alerte_stock


class FlaconAdminSerializer(FlaconSerializer):
    """Flacon avec prix d'achat et bénéfice (admin uniquement)"""
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(FlaconSerializer.Meta):
        fields = FlaconSerializer.Meta.fields + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat and obj.prix_unitaire:
            return str((obj.prix_unitaire - obj.prix_achat).quantize(Decimal('0.01')))
        return None
    
class FlaconPublicSerializer(serializers.ModelSerializer):
    image_principale = serializers.SerializerMethodField()
    stock_suffisant = serializers.SerializerMethodField()

    class Meta:
        model = Flacon
        fields = [
            'id', 'nom', 'slug', 'image_principale',
            'prix_unitaire', 'contenance_ml',
            'stock_quantite', 'stock_suffisant',
            'matiere', 'couleur', 'type_flacon',
        ]

    @extend_schema_field(OpenApiTypes.URI)
    def get_image_principale(self, obj):
        return get_image_url(self.context.get('request'), obj.image_principale)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_stock_suffisant(self, obj) -> bool:
        return obj.stock_quantite > obj.seuil_alerte_stock

 
#favori 

from .models import Favori   # en haut du fichier

class FavoriSerializer(serializers.ModelSerializer):
    nom_produit = serializers.SerializerMethodField()
    prix_produit = serializers.SerializerMethodField()
    image_produit = serializers.SerializerMethodField()
    type_produit = serializers.SerializerMethodField()
    slug_produit = serializers.SerializerMethodField()
    id_produit = serializers.SerializerMethodField()

    class Meta:
        model = Favori
        fields = ['id', 'date_ajout', 'nom_produit', 'prix_produit', 'image_produit', 'type_produit', 'slug_produit', 'id_produit']

    def get_nom_produit(self, obj):
        if obj.parfum:
            return obj.parfum.nom
        if obj.accessoire:
            return obj.accessoire.nom
        if obj.produit_fini_essence:
            return f"{obj.produit_fini_essence.essence.nom} - {obj.produit_fini_essence.taille_ml}ml"
        return None

    def get_prix_produit(self, obj):
        if obj.parfum:
            return str(obj.parfum.prix_actuel)
        if obj.accessoire:
            return str(obj.accessoire.prix_actuel)
        if obj.produit_fini_essence:
            return str(obj.produit_fini_essence.prix_actuel)
        return None

    def get_image_produit(self, obj):
        request = self.context.get('request')
        image = None
        if obj.parfum and obj.parfum.image_principale:
            image = obj.parfum.image_principale
        elif obj.accessoire and obj.accessoire.image_principale:
            image = obj.accessoire.image_principale
        elif obj.produit_fini_essence and obj.produit_fini_essence.essence and obj.produit_fini_essence.essence.image_principale:
            image = obj.produit_fini_essence.essence.image_principale

        if image:
            if request:
                return request.build_absolute_uri(image.url)
            return image.url
        return None

    def get_type_produit(self, obj):
        if obj.produit_fini_essence:
            return 'produit_fini_essence'
        return 'parfum' if obj.parfum else 'accessoire'

    def get_slug_produit(self, obj):
        if obj.parfum:
            return obj.parfum.slug
        if obj.accessoire:
            return obj.accessoire.slug
        if obj.produit_fini_essence and obj.produit_fini_essence.essence:
            return obj.produit_fini_essence.essence.slug
        return None

    def get_id_produit(self, obj):
        if obj.parfum:
            return obj.parfum.id
        if obj.accessoire:
            return obj.accessoire.id
        if obj.produit_fini_essence:
            return obj.produit_fini_essence.id
        return None


class CategorieParfumSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieParfum
        fields = [
            'id', 'nom', 'slug', 'description', 'image', 'ordre_affichage',
            'actif', 'taux_reduction', 'date_debut', 'date_fin',
            'message_promotion', 'date_creation'
        ]
        read_only_fields = ['date_creation']


class PromotionSerializer(serializers.Serializer):
    type_article = serializers.CharField()
    id = serializers.IntegerField()
    slug = serializers.CharField(allow_null=True)
    nom = serializers.CharField()
    marque = serializers.CharField(allow_blank=True)
    image_principale = serializers.CharField(allow_null=True)
    prix_original = serializers.DecimalField(max_digits=10, decimal_places=2)
    prix_promotionnel = serializers.DecimalField(max_digits=10, decimal_places=2)
    taux_reduction = serializers.FloatField()
    message_promotion = serializers.CharField(allow_blank=True)
    date_debut = serializers.DateTimeField(allow_null=True)
    date_fin = serializers.DateTimeField(allow_null=True)


class UnifiedBestsellerHotsellerSerializer(serializers.Serializer):
    type_article = serializers.CharField()
    id = serializers.IntegerField()
    slug = serializers.CharField(allow_null=True)
    nom = serializers.CharField()
    marque = serializers.CharField(allow_blank=True, allow_null=True)
    image_principale = serializers.SerializerMethodField()
    prix_original = serializers.DecimalField(max_digits=10, decimal_places=2)
    prix_actuel = serializers.DecimalField(max_digits=10, decimal_places=2)
    en_promotion = serializers.BooleanField()
    stock_quantite = serializers.IntegerField()
    actif = serializers.BooleanField()
    ventes = serializers.IntegerField()

    @extend_schema_field(OpenApiTypes.STR)
    def get_image_principale(self, obj):
        image_field = obj.get('image_principale_field')
        return get_image_url(self.context.get('request'), image_field)


# ============================================================
# NOTIFICATIONS CATALOGUE
# ============================================================
class NotificationCatalogueSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationCatalogue
        fields = [
            'id',
            'type_produit',
            'product_id',
            'product_name',
            'message',
            'stock_actuel',
            'seuil_alerte',
            'est_lu',
            'est_encore_en_alerte',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'est_encore_en_alerte']


class NotificationCatalogueUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour marquer une notification comme lue."""
    class Meta:
        model = NotificationCatalogue
        fields = ['est_lu']


class MouvementStockSerializer(serializers.ModelSerializer):
    utilisateur_details = serializers.SerializerMethodField()

    class Meta:
        model = MouvementStock
        fields = [
            'id', 'utilisateur', 'utilisateur_details', 'type_produit',
            'produit_id', 'nom_produit', 'quantite_avant',
            'quantite_apres', 'quantite_ajoutee', 'date_ajout'
        ]
        read_only_fields = fields

    def get_utilisateur_details(self, obj):
        if obj.utilisateur:
            from utilisateur.serializers import UserSerializer
            return UserSerializer(obj.utilisateur, context=self.context).data
        return None


# ============================================================
# SERIALIZERS DIFFUSEURS DE PARFUM
# ============================================================
class DiffuseurParfumSerializer(serializers.ModelSerializer):
    prix_actuel = serializers.SerializerMethodField()
    en_promotion = serializers.SerializerMethodField()
    image_principale = serializers.ImageField(required=False, allow_null=True)
    image_supp_1 = serializers.ImageField(required=False, allow_null=True)
    image_supp_2 = serializers.ImageField(required=False, allow_null=True)
    image_supp_3 = serializers.ImageField(required=False, allow_null=True)
    image_supp_4 = serializers.ImageField(required=False, allow_null=True)
    produits_similaires = serializers.SerializerMethodField()

    class Meta:
        model = DiffuseurParfum
        fields = [
            'id', 'nom', 'marque', 'slug', 'reference_sku', 'description',
            'prix_unitaire', 'prix_promotionnel', 'prix_actuel', 'en_promotion',
            'date_debut', 'date_fin', 'stock_quantite', 'seuil_alerte_stock',
            'materiau', 'couleur', 'dimensions', 'poids_grammes',
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4',
            'actif', 'est_bestseller', 'est_hotseller', 'date_creation', 'date_modification',
            # Attributs physiques/technologiques
            'type_technologie', 'capacite_reservoir_ml', 'type_alimentation',
            'nombre_vitesses', 'est_connecte', 'surface_couverture_m2', 'a_jeux_de_lumiere',
            'produits_similaires',
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['image_principale'] = get_image_url(self.context.get('request'), instance.image_principale)
        for i in range(1, 5):
            img_field = f'image_supp_{i}'
            representation[img_field] = get_image_url(self.context.get('request'), getattr(instance, img_field))
        return representation

    @extend_schema_field(OpenApiTypes.STR)
    def get_prix_actuel(self, obj):
        return formater_prix(obj.prix_actuel)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_en_promotion(self, obj):
        return obj.prix_promotionnel_effectif is not None

    def get_produits_similaires(self, obj):
        similaires = get_similar_products(obj, DiffuseurParfum, limit=6)
        return DiffuseurParfumSimilaireSerializer(similaires, many=True, context=self.context).data


class DiffuseurParfumSimilaireSerializer(serializers.ModelSerializer):
    prix_actuel = serializers.SerializerMethodField()
    image_principale = serializers.SerializerMethodField()

    class Meta:
        model = DiffuseurParfum
        fields = ['id', 'nom', 'slug', 'prix_unitaire', 'prix_actuel', 'image_principale']

    @extend_schema_field(OpenApiTypes.STR)
    def get_prix_actuel(self, obj):
        return formater_prix(obj.prix_actuel)

    @extend_schema_field(OpenApiTypes.STR)
    def get_image_principale(self, obj):
        return get_image_url(self.context.get('request'), obj.image_principale)


class DiffuseurParfumAdminListSerializer(DiffuseurParfumSerializer):
    """Admin : liste (sans produits similaires, avec prix d'achat et bénéfice)"""
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(DiffuseurParfumSerializer.Meta):
        fields = [f for f in DiffuseurParfumSerializer.Meta.fields if f != 'produits_similaires'] + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat and obj.prix_unitaire:
            return str((obj.prix_unitaire - obj.prix_achat).quantize(Decimal('0.01')))
        return None


class DiffuseurParfumAdminDetailSerializer(DiffuseurParfumSerializer):
    """Admin : détail (avec produits similaires et prix d'achat)"""
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    benefice_unitaire = serializers.SerializerMethodField()

    class Meta(DiffuseurParfumSerializer.Meta):
        fields = DiffuseurParfumSerializer.Meta.fields + ['prix_achat', 'benefice_unitaire']

    def get_benefice_unitaire(self, obj):
        if obj.prix_achat and obj.prix_unitaire:
            return str((obj.prix_unitaire - obj.prix_achat).quantize(Decimal('0.01')))
        return None


class DiffuseurParfumPublicListSerializer(DiffuseurParfumSerializer):
    """Public : liste (champs réduits, sans infos admin)"""
    class Meta(DiffuseurParfumSerializer.Meta):
        fields = [f for f in DiffuseurParfumSerializer.Meta.fields if f not in (
            'produits_similaires', 'reference_sku',
            'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4',
            'description', 'poids_grammes',
        )]


class DiffuseurParfumPublicDetailSerializer(DiffuseurParfumSerializer):
    """Public : détail complet (sans champs admin)"""
    class Meta(DiffuseurParfumSerializer.Meta):
        fields = [f for f in DiffuseurParfumSerializer.Meta.fields if f not in (
            'reference_sku', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4',
        )]

