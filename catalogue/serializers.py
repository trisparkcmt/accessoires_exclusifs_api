# serializers.py
from decimal import Decimal
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from .utils import get_similar_products

from .models import CategorieParfum, LotEssence, ProduitFiniEssence, Tag, Parfum, Essence, Accessoire, Flacon, TypeAccessoire, TypeFlacon, Favori, Ingredient, NotificationCatalogue


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
    Ex : http://localhost:8000/media/parfums/royal-oud/image.jpg
    Retourne None si pas d'image.
    """
    if not image_field:
        return None
    if request:
        return request.build_absolute_uri(image_field.url)
    return image_field.url



# TAGS

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Tag
        fields = ['id', 'nom', 'slug', 'type']


class TagSelectSerializer(serializers.ModelSerializer):
    libelle = serializers.CharField(source='nom', read_only=True)

    class Meta:
        model = Tag
        fields = ['id', 'libelle', 'nom', 'slug', 'type']

    def validate_type(self, value):
        allowed_types = self.context.get('allowed_types')
        if allowed_types and value not in allowed_types:
            allowed = ', '.join(allowed_types)
            raise serializers.ValidationError(f"Type de tag non autorisé ici. Types autorisés : {allowed}.")
        return value



# PARFUMS

class ParfumSerializer(serializers.ModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.all(), required=False)
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
    images_supplementaires = serializers.SerializerMethodField(read_only=True)
    produits_similaires = serializers.SerializerMethodField()
    is_favori = serializers.SerializerMethodField()

    class Meta:
        model  = Parfum
        fields = [
            'id', 'marque','nom', 'slug', 'reference_sku',
            'description_courte', 'contenance_ml',
            'prix_unitaire', 'prix_actuel',
            'taux_reduction', 'en_promotion',
            'genre_cible', 'intensite',
            'notes_tete', 'notes_coeur', 'notes_fond',
            'tags', 'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles',
            'est_nouveau', 'est_bestseller',
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'images_supplementaires', 'stock_quantite',
            'date_creation','produits_similaires', 'is_favori', 'categorie'
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['tags'] = TagSerializer(instance.tags.all(), many=True).data
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
    
    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_images_supplementaires(self, obj):
        request = self.context.get('request')
        images_supp = []
        for i in range(1, 5):
            img = getattr(obj, f'image_supp_{i}')
            if img:
                images_supp.append(get_image_url(request, img))
        return images_supp
    
    def get_produits_similaires(self, obj):
        from .utils import get_similar_products
        from .models import Parfum
        similaires = get_similar_products(obj, Parfum, limit=4)
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
    """Admin : liste (sans produits similaires)"""
    class Meta(ParfumSerializer.Meta):
        fields = [f for f in ParfumSerializer.Meta.fields if f != 'produits_similaires']

class ParfumAdminDetailSerializer(ParfumSerializer):
    """Admin : détail (avec produits similaires)"""
    pass

class ParfumPublicListSerializer(ParfumSerializer):
    """Public : liste (sans produits similaires, champs réduits)"""
    class Meta(ParfumSerializer.Meta):
        fields = [f for f in ParfumSerializer.Meta.fields if f not in ('produits_similaires', 'reference_sku', 'images_supplementaires', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'stock_quantite', 'taux_reduction','description_courte',
            'notes_tete', 'notes_coeur', 'notes_fond',
            'tags', 'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles',)]

class ParfumPublicDetailSerializer(ParfumSerializer):
    """Public : détail (avec produits similaires)"""
    class Meta(ParfumSerializer.Meta):
        fields = [f for f in ParfumSerializer.Meta.fields if f not in ('reference_sku', 'images_supplementaires', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'stock_quantite', 'taux_reduction')]
    
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


# ============================================================
# ESSENCES (catalogue complet pour admin)
# ============================================================
class EssenceSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source='tags',
        many=True,
        queryset=Tag.objects.all(),
        required=False,
        write_only=True
    )
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
            'tags', 'tag_ids', 'famille_olfactive', 'humeurs_compatibles',
            'occasions', 'saisons_compatibles',
            'signes_astrologiques_compatibles', 'moments_journee',
            'prix_par_ml', 'actif', 'date_creation', 'date_modification'
        ]

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        essence = super().create(validated_data)
        if tags:
            essence.tags.set(tags)
        return essence

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)
        essence = super().update(instance, validated_data)
        if tags is not None:
            essence.tags.set(tags)
        return essence
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
        return obj.stock_total_ml()

# ============================================================
# CATALOGUE : produits finis (essences vendues en flacon)
# ============================================================
class ProduitFiniEssencePublicSerializer(serializers.ModelSerializer):
    marque = serializers.CharField(source='essence.marque', read_only=True)
    nom = serializers.CharField(source='essence.nom', read_only=True)
    categorie = serializers.CharField(source='essence.categorie', read_only=True)

    class Meta:
        model = ProduitFiniEssence
        fields = ['id', 'marque', 'nom', 'categorie', 'taille_ml', 'prix_actuel', 'stock_disponible']
# ============================================================
# LOTessence et produit finis 
# ============================================================
class LotEssenceSerializer(serializers.ModelSerializer):
    essence_details = EssenceLaboListSerializer(source='essence', read_only=True)

    class Meta:
        model = LotEssence
        fields = [
            'id', 'essence', 'essence_details', 'stock_ml', 
            'stock_precedent_ml', 'seuil_alerte_ml', 'actif', 
            'date_reception', 'reference_fournisseur'
        ]
        read_only_fields = ['date_reception']

    def create(self, validated_data):
        essence = validated_data.get('essence')
        validated_data['stock_precedent_ml'] = essence.stock_total_ml()
        return super().create(validated_data)


class ProduitFiniEssenceSerializer(serializers.ModelSerializer):
    essence_details = EssenceSerializer(source='essence', read_only=True)
    prix_actuel = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    prix_par_ml = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ProduitFiniEssence
        fields = [
            'id', 'essence', 'essence_details', 'taille_ml',
            'prix', 'prix_promotionnel', 'prix_actuel', 'prix_par_ml',
            'stock_disponible', 'stock_precedent', 'actif'
        ]

    def create(self, validated_data):
        essence = validated_data.get('essence')
        taille = validated_data.get('taille_ml')
        # Gestion du unique_together : si le format existe, on le met à jour
        existing = ProduitFiniEssence.objects.filter(essence=essence, taille_ml=taille).first()
        if existing:
            validated_data['stock_precedent'] = existing.stock_disponible
            return self.update(existing, validated_data)
        
        validated_data['stock_precedent'] = 0
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'stock_disponible' in validated_data:
            instance.stock_precedent = instance.stock_disponible
        return super().update(instance, validated_data)

class _LotEssenceInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = LotEssence
        fields = ['stock_ml', 'seuil_alerte_ml', 'reference_fournisseur']

class _ProduitFiniInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProduitFiniEssence
        fields = ['taille_ml', 'prix', 'prix_promotionnel', 'stock_disponible']

class EssenceCreateFullSerializer(EssenceSerializer):
    initial_lot = _LotEssenceInputSerializer(write_only=True, required=False)
    produits_finis = _ProduitFiniInputSerializer(many=True, write_only=True, required=False)

    class Meta(EssenceSerializer.Meta):
        fields = EssenceSerializer.Meta.fields + ['initial_lot', 'produits_finis']

    def create(self, validated_data):
        lot_data = validated_data.pop('initial_lot', None)
        prods_data = validated_data.pop('produits_finis', [])
        tags = validated_data.pop('tags', [])
        
        with transaction.atomic():
            essence = Essence.objects.create(**validated_data)
            if tags:
                essence.tags.set(tags)
            if lot_data:
                LotEssence.objects.create(essence=essence, stock_precedent_ml=0, **lot_data)
            for prod in prods_data:
                ProduitFiniEssence.objects.create(essence=essence, stock_precedent=0, **prod)
        return essence
        
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
            'actif', 'taux_reduction', 'date_creation'
        ]
        read_only_fields = ['date_creation']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['icone'] = get_image_url(self.context.get('request'), instance.icone)
        return representation



class AccessoireSerializer(serializers.ModelSerializer):
    type_accessoire = serializers.PrimaryKeyRelatedField(queryset=TypeAccessoire.objects.all())
    prix_actuel     = serializers.SerializerMethodField()
    taux_reduction  = serializers.SerializerMethodField()
    en_promotion    = serializers.SerializerMethodField()
    image_principale = serializers.ImageField(required=False, allow_null=True)
    image_supp_1     = serializers.ImageField(required=False, allow_null=True)
    image_supp_2     = serializers.ImageField(required=False, allow_null=True)
    image_supp_3     = serializers.ImageField(required=False, allow_null=True)
    image_supp_4     = serializers.ImageField(required=False, allow_null=True)
    images_supplementaires = serializers.SerializerMethodField(read_only=True)
    produits_similaires = serializers.SerializerMethodField()
    is_favori = serializers.SerializerMethodField()

    class Meta:
        model  = Accessoire
        fields = [
            'id', 'marque', 'nom', 'slug', 'reference_sku',
            'type_accessoire',
            'description_courte', 'description_longue',
            'matiere', 'couleur', 'taille',
            'prix_unitaire', 'prix_promotionnel', 'prix_actuel',
            'taux_reduction', 'en_promotion',
            'stock_quantite', 'seuil_alerte_stock', 'poids_grammes',
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'images_supplementaires',
            'actif', 'est_bestseller', 'est_hotseller',
            'date_creation', 'date_modification', 'produits_similaires', 'is_favori',
        ]
        read_only_fields = ['date_creation', 'date_modification']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
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
    
    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_images_supplementaires(self, obj):
        request = self.context.get('request')
        images_supp = []
        for i in range(1, 5):
            img = getattr(obj, f'image_supp_{i}')
            if img:
                images_supp.append(get_image_url(request, img))
        return images_supp
    
    def get_produits_similaires(self, obj):
        from .utils import get_similar_products
        similaires = get_similar_products(obj, Accessoire, limit=4)
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
    class Meta(AccessoireSerializer.Meta):
        fields = [f for f in AccessoireSerializer.Meta.fields if f != 'produits_similaires']

class AccessoireAdminDetailSerializer(AccessoireSerializer):
    pass

class AccessoirePublicListSerializer(AccessoireSerializer):
    class Meta(AccessoireSerializer.Meta):
       fields = [f for f in AccessoireSerializer.Meta.fields if f not in ('description_courte',
            'matiere', 'couleur', 'taille','poids_grammes','produits_similaires', 'reference_sku', 'images_supplementaires', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4','taux_reduction')] 

class AccessoirePublicDetailSerializer(AccessoireSerializer):
    class Meta(AccessoireSerializer.Meta):
        fields = [f for f in AccessoireSerializer.Meta.fields if f not in ('reference_sku', 'images_supplementaires', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'stock_quantite', 'taux_reduction')]

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
    images_supplementaires = serializers.SerializerMethodField(read_only=True)

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
            'image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4', 'images_supplementaires',
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

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_images_supplementaires(self, obj):
        request = self.context.get('request')
        images_supp = []
        for i in range(1, 5):
            img = getattr(obj, f'image_supp_{i}')
            if img:
                images_supp.append(get_image_url(request, img))
        return images_supp

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_stock_suffisant(self, obj) -> bool:
        """
        True  → stock > seuil_alerte_stock (commande possible)
        False → stock ≤ seuil_alerte_stock (commande bloquée)
        """
        return obj.stock_quantite > obj.seuil_alerte_stock
    
class FlaconPublicSerializer(serializers.ModelSerializer):
    image_principale = serializers.SerializerMethodField()

    class Meta:
        model = Flacon
        fields = ['id', 'nom', 'slug', 'image_principale', 'prix_unitaire', 'contenance_ml']

    @extend_schema_field(OpenApiTypes.URI)
    def get_image_principale(self, obj):
        return get_image_url(self.context.get('request'), obj.image_principale)
 
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
        return obj.accessoire.nom if obj.accessoire else None

    def get_prix_produit(self, obj):
        if obj.parfum:
            # Utilise le prix actuel (promotion ou non)
            return str(obj.parfum.prix_actuel)
        if obj.accessoire:
            return str(obj.accessoire.prix_actuel)
        return None

    def get_image_produit(self, obj):
        request = self.context.get('request')
        produit = obj.parfum if obj.parfum else obj.accessoire
        if produit and produit.image_principale:
            if request:
                return request.build_absolute_uri(produit.image_principale.url)
            return produit.image_principale.url
        return None

    def get_type_produit(self, obj):
        return "parfum" if obj.parfum else "accessoire"

    def get_slug_produit(self, obj):
        if obj.parfum:
            return obj.parfum.slug
        return obj.accessoire.slug if obj.accessoire else None

    def get_id_produit(self, obj):
        if obj.parfum:
            return obj.parfum.id
        return obj.accessoire.id if obj.accessoire else None


class CategorieParfumSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieParfum
        fields = ['id', 'nom', 'slug', 'description', 'image', 'ordre_affichage', 'actif', 'taux_reduction', 'date_creation']
        read_only_fields = ['date_creation']


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
