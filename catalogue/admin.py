# admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    Favori, Tag, TagParfum, TagEssence,
    CategorieParfum, Parfum, Essence, Ingredient,
    TypeAccessoire, Accessoire, TypeFlacon, Flacon, NotificationCatalogue
)


# ============================================================
# HELPERS PARTAGÉS
# ============================================================
def apercu_image(image_field, hauteur=50):
    url = None
    if image_field:
        try:
            url = image_field.url
        except (AttributeError, ValueError):
            pass
    elif isinstance(image_field, str) and image_field:
        url = image_field
    if url:
        return format_html(
            '<img src="{}" style="height:{}px; border-radius:4px;" />',
            url, hauteur
        )
    return "—"


def statut_stock_html(stock_quantite, seuil):
    if stock_quantite <= 0:
        return mark_safe('<span style="color:red;font-weight:bold;">⛔ Épuisé</span>')
    elif stock_quantite <= seuil:
        return format_html(
            '<span style="color:orange;font-weight:bold;">⚠️ Faible ({})</span>',
            stock_quantite
        )
    return format_html(
        '<span style="color:green;font-weight:bold;">✅ OK ({})</span>',
        stock_quantite
    )


def badge_reduction(taux):
    if taux and taux > 0:
        return format_html(
            '<span style="background:#e53e3e;color:white;padding:2px 8px;'
            'border-radius:12px;font-weight:bold;">-{}%</span>',
            taux
        )
    return mark_safe('<span style="color:#aaa;">Aucune</span>')


# ============================================================
# FILTRES PERSONNALISÉS PAR TYPE DE TAG
# Un filtre par type → une classe → réutilisable sur Parfum et Essence
# ============================================================
def creer_filtre_tag(type_tag, titre):
    """
    Factory qui crée dynamiquement un filtre admin pour un type de tag donné.
    Usage : FamilleOlfactiveFilter = creer_filtre_tag('famille_olfactive', 'Famille olfactive')
    """
    class FiltreTag(admin.SimpleListFilter):
        title        = titre
        parameter_name = f'tag_{type_tag}'

        def lookups(self, request, model_admin):
            """Retourne tous les tags actifs du type concerné."""
            tags = Tag.objects.filter(type=type_tag, actif=True).order_by('nom')
            return [(tag.pk, tag.nom) for tag in tags]

        def queryset(self, request, queryset):
            if self.value():
                return queryset.filter(tags__pk=self.value()).distinct()
            return queryset

    FiltreTag.__name__ = f'Filtre_{type_tag}'
    return FiltreTag


# Filtres pour Parfum
FamilleOlfactiveParfumFilter = creer_filtre_tag('famille_olfactive', 'Famille olfactive')
HumeurParfumFilter           = creer_filtre_tag('humeur',            'Humeur compatible')
SaisonParfumFilter           = creer_filtre_tag('saison',            'Saison compatible')
OccasionParfumFilter         = creer_filtre_tag('occasion',          'Occasion')

# Filtres pour Essence (inclut signes astro et moments journée)
FamilleOlfactiveEssenceFilter  = creer_filtre_tag('famille_olfactive',  'Famille olfactive')
HumeurEssenceFilter            = creer_filtre_tag('humeur',             'Humeur compatible')
SaisonEssenceFilter            = creer_filtre_tag('saison',             'Saison compatible')
OccasionEssenceFilter          = creer_filtre_tag('occasion',           'Occasion')
SigneAstroEssenceFilter        = creer_filtre_tag('signe_astrologique', 'Signe astrologique')
MomentJourneeEssenceFilter     = creer_filtre_tag('moment_journee',     'Moment de la journée')


# ============================================================
# TAGS
# ============================================================
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display  = ('id', 'nom', 'type', 'actif', 'date_creation')
    list_filter   = ('type', 'actif')
    search_fields = ('nom',)
    list_editable = ('actif',)
    list_per_page = 50

    fieldsets = (
        ('Informations', {
            'fields': ('nom', 'type', 'actif')
        }),
    )


@admin.register(TagParfum)
class TagParfumAdmin(admin.ModelAdmin):
    list_display = ('id', 'parfum', 'tag')
    search_fields = ('parfum__nom', 'tag__nom')
    autocomplete_fields = ('parfum', 'tag')


@admin.register(TagEssence)
class TagEssenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'essence', 'tag')
    search_fields = ('essence__nom', 'tag__nom')
    autocomplete_fields = ('essence', 'tag')


@admin.register(Favori)
class FavoriAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'parfum', 'accessoire', 'date_ajout')
    list_filter = ('date_ajout',)
    search_fields = ('client__user__email', 'parfum__nom', 'accessoire__nom')
    autocomplete_fields = ('client', 'parfum', 'accessoire')


class TagParfumInline(admin.TabularInline):
    model               = TagParfum
    extra               = 1
    autocomplete_fields = ('tag',)


class TagEssenceInline(admin.TabularInline):
    model               = TagEssence
    extra               = 1
    autocomplete_fields = ('tag',)


# ============================================================
# CATÉGORIES & PARFUMS
# ============================================================
@admin.register(CategorieParfum)
class CategorieParfumAdmin(admin.ModelAdmin):
    list_display        = (
        'id', 'nom', 'slug', 'ordre_affichage',
        'badge_taux_reduction',
        'message_promotion',
        'nb_parfums_en_promo',
        'actif', 'date_creation'
    )
    list_filter         = ('actif', 'date_creation')
    search_fields       = ('nom', 'description')
    prepopulated_fields = {'slug': ('nom',)}
    ordering            = ('ordre_affichage', 'nom')
    list_per_page       = 50
    readonly_fields     = ('date_creation',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'slug', 'description', 'image')
        }),
        ('Promotion catégorie', {
            'description': (
                '⚠️ Définir un taux ici mettra automatiquement à jour le prix promotionnel '
                'de TOUS les parfums actifs de cette catégorie. Mettre à 0 pour désactiver.'
            ),
            'fields': ('taux_reduction', 'date_debut', 'date_fin', 'message_promotion'),
        }),
        ('Affichage', {
            'fields': ('ordre_affichage', 'actif')
        }),
        ('Dates', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description="Réduction")
    def badge_taux_reduction(self, obj):
        return badge_reduction(obj.taux_reduction)

    @admin.display(description="Parfums en promo")
    def nb_parfums_en_promo(self, obj):
        count = obj.parfums.filter(actif=True, prix_promotionnel__isnull=False).count()
        total = obj.parfums.filter(actif=True).count()
        if count == 0:
            return format_html('<span style="color:#aaa;">0 / {}</span>', total)
        return format_html(
            '<span style="color:#e53e3e;font-weight:bold;">{} / {}</span>',
            count, total
        )


@admin.register(Parfum)
class ParfumAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'apercu_image_col', 'nom', 'marque', 'categorie',
        'contenance_ml', 'prix_unitaire', 'prix_promotionnel',
        'date_debut', 'date_fin', 'badge_taux', 'statut_stock', 'actif',
        'est_nouveau', 'est_bestseller'
    )
    list_filter = (
        'marque', 'categorie', 'actif', 'est_nouveau', 'est_bestseller',
        'genre_cible', 'intensite',
        # ← Filtres par tags
        FamilleOlfactiveParfumFilter,
        HumeurParfumFilter,
        SaisonParfumFilter,
        OccasionParfumFilter,
        'date_creation',
    )
    search_fields       = ('marque', 'nom', 'slug', 'reference_sku', 'description_courte')
    readonly_fields     = ('date_creation', 'date_modification')
    prepopulated_fields = {'slug': ('nom',)}
    list_editable       = ('prix_unitaire', 'prix_promotionnel', 'actif')
    list_per_page       = 50
    inlines             = [TagParfumInline]

    fieldsets = (
        ('Informations générales', {
            'fields': ('categorie', 'nom', 'slug', 'reference_sku')
        }),
        ('Descriptions', {
            'fields': ('description_courte', 'description_longue', 'description_ia')
        }),
        ('Notes olfactives', {
            'fields': ('notes_tete', 'notes_coeur', 'notes_fond')
        }),
        ('Caractéristiques', {
            'fields': ('contenance_ml', 'genre_cible', 'intensite')
        }),
        ('Prix', {
            'description': (
                'Le prix promotionnel peut être défini manuellement ici, '
                'ou calculé automatiquement via la réduction de la catégorie.'
            ),
            'fields': ('prix_unitaire', 'prix_promotionnel', 'date_debut', 'date_fin', 'stock_quantite', 'seuil_alerte_stock')
        }),
        ('Images', {
            'fields': ('image_principale', 'image_supp_1',"image_supp_2","image_supp_3", 'image_supp_4')
        }),
        ('Statut', {
            'fields': ('actif', 'est_nouveau', 'est_bestseller')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description="Aperçu")
    def apercu_image_col(self, obj):
        return apercu_image(obj.image_principale)

    @admin.display(description="Stock")
    def statut_stock(self, obj):
        return statut_stock_html(obj.stock_quantite, obj.seuil_alerte_stock)

    @admin.display(description="Réduction")
    def badge_taux(self, obj):
        if obj.prix_promotionnel and obj.prix_unitaire:
            taux = (1 - obj.prix_promotionnel / obj.prix_unitaire) * 100
            return badge_reduction(round(taux, 1))
        return badge_reduction(None)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('categorie').prefetch_related('tags')
# catalogue/admin.py (extrait modifié)

# ... gardez toutes les importations et helpers existants ...
# Ajoutez les nouveaux modèles dans les imports
from .models import (
    Tag, TagParfum, TagEssence,
    CategorieParfum, Parfum, Essence, LotEssence, ProduitFiniEssence,
    TypeAccessoire, Accessoire, TypeFlacon, Flacon
)

# ============================================================
# ESSENCES (catalogue uniquement)
# ============================================================
@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom', 'prix_par_ml', 'stock_ml', 'seuil_alerte_ml', 'actif', 'date_creation')
    list_filter = ('actif', 'date_creation')
    search_fields = ('nom', 'description')
    readonly_fields = ('date_creation',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'description', 'prix_par_ml', 'stock_ml', 'seuil_alerte_ml')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Essence)
class EssenceAdmin(admin.ModelAdmin):
    list_display = (

        'id', 'marque', 'nom', 'code_reference', 'categorie',
        'intensite', 'genre_cible', 'actif', 'date_creation'
    )
    list_filter = (
        'categorie', 'intensite', 'genre_cible', 'actif',
        'date_creation',
        # Filtres par tags

        FamilleOlfactiveEssenceFilter,
        HumeurEssenceFilter,
        SaisonEssenceFilter,
        OccasionEssenceFilter,
        SigneAstroEssenceFilter,
        MomentJourneeEssenceFilter,
    )

    search_fields = ('nom', 'code_reference', 'marque', 'fournisseur', 'origine_pays')
    readonly_fields = ('date_creation', 'date_modification')
    list_per_page = 50
    inlines = [TagEssenceInline]

    fieldsets = (
        ('Identité', {
            'fields': ('marque', 'nom', 'code_reference', 'categorie')
        }),
        ('Descriptions', {
            'fields': ('description', 'description_ia')
        }),
        ('Fournisseur & Technique', {
            'fields': ('fournisseur', 'origine_pays', 'concentration_max', 'couleur', 'duree')
        }),
        ('Caractéristiques olfactives', {
            'fields': ('intensite', 'genre_cible', 'notes_tete', 'notes_coeur', 'notes_fond')

        }),
        # ('Tags', {
        #     'fields': ('tags',)
        # }),
        ('Statut', {

            'fields': ('actif', )

           
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )



# ============================================================
# LOTS D'ESSENCE (stock physique)
# ============================================================
@admin.register(LotEssence)
class LotEssenceAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'essence', 'stock_ml', 'stock_precedent_ml', 'seuil_alerte_ml',
        'date_reception', 'actif'
    )
    list_filter = ('actif', 'date_reception')
    search_fields = ('essence__marque', 'essence__nom', 'reference_fournisseur')
    list_editable = ('stock_ml', 'actif')
    readonly_fields = ('date_reception',)
    list_per_page = 50

    fieldsets = (
        ('Essence concernée', {
            'fields': ('essence',)
        }),
        ('Caractéristiques du lot', {
            'fields': ('stock_ml', 'stock_precedent_ml', 'seuil_alerte_ml', 'reference_fournisseur')
        }),
        ('Dates', {
            'fields': ('date_reception',)
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
    )
    readonly_fields = ('date_reception', 'stock_precedent_ml')


# ============================================================
# PRODUITS FINIS (essences vendues en flacon)
# ============================================================
@admin.register(ProduitFiniEssence)
class ProduitFiniEssenceAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'apercu_image_col', 'essence', 'taille_ml', 'prix', 'prix_promotionnel',
        'prix_actuel', 'stock_disponible', 'stock_precedent', 'actif'
    )
    list_filter = ('actif', 'taille_ml', 'essence__categorie')
    search_fields = ('essence__marque', 'essence__nom')
    list_editable = ('prix', 'prix_promotionnel', 'stock_disponible', 'actif')
    readonly_fields = ('prix_actuel',)
    list_per_page = 50

    fieldsets = (
        ('Essence', {
            'fields': ('essence', 'taille_ml')
        }),
        ('Prix', {
            'fields': ('prix', 'prix_promotionnel', 'prix_actuel')
        }),
        ('Stock', {
            'fields': ('stock_disponible', 'stock_precedent')
        }),
        ('Images', {
            'fields': ('image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
    )
    readonly_fields = ('prix_actuel', 'stock_precedent')

    @admin.display(description="Aperçu")
    def apercu_image_col(self, obj):
        return apercu_image(obj.image_principale)

    @admin.display(description="Prix actuel", ordering='prix')
    def prix_actuel(self, obj):
        return obj.prix_actuel




# ============================================================
# ACCESSOIRES
# ============================================================
@admin.register(TypeAccessoire)
class TypeAccessoireAdmin(admin.ModelAdmin):
    list_display        = (
        'id', 'nom', 'slug',
        'badge_taux_reduction',
        'message_promotion',
        'nb_accessoires_en_promo',
        'actif', 'date_creation'
    )
    list_filter         = ('actif',)
    search_fields       = ('nom', 'description')
    prepopulated_fields = {'slug': ('nom',)}
    list_per_page       = 50
    readonly_fields     = ('date_creation',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'slug', 'description', 'icone')
        }),
        ('Promotion type', {
            'description': (
                '⚠️ Définir un taux ici mettra automatiquement à jour le prix promotionnel '
                'de TOUS les accessoires actifs de ce type. Mettre à 0 pour désactiver.'
            ),
            'fields': ('taux_reduction', 'date_debut', 'date_fin', 'message_promotion'),
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description="Réduction")
    def badge_taux_reduction(self, obj):
        return badge_reduction(obj.taux_reduction)

    @admin.display(description="En promo")
    def nb_accessoires_en_promo(self, obj):
        count = obj.accessoires.filter(actif=True, prix_promotionnel__isnull=False).count()
        total = obj.accessoires.filter(actif=True).count()
        if count == 0:
            return format_html('<span style="color:#aaa;">0 / {}</span>', total)
        return format_html(
            '<span style="color:#e53e3e;font-weight:bold;">{} / {}</span>',
            count, total
        )


@admin.register(Accessoire)
class AccessoireAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'apercu_image_col', 'nom', 'marque', 'type_accessoire',
        'matiere', 'prix_unitaire', 'prix_promotionnel',
        'date_debut', 'date_fin', 'badge_taux', 'statut_stock', 'actif'
    )
    list_filter         = ('marque', 'type_accessoire', 'matiere', 'couleur', 'actif', 'date_creation')
    search_fields       = ('marque', 'nom', 'slug', 'reference_sku', 'description_courte')
    readonly_fields     = ('date_creation', 'date_modification')
    prepopulated_fields = {'slug': ('nom',)}
    list_editable       = ('prix_unitaire', 'prix_promotionnel', 'actif')
    list_per_page       = 50

    fieldsets = (
        ('Informations générales', {
            'fields': ('type_accessoire', 'nom', 'slug', 'reference_sku')
        }),
        ('Descriptions', {
            'fields': ('description_courte', 'description_longue')
        }),
        ('Caractéristiques', {
            'fields': ('matiere', 'couleur', 'taille', 'poids_grammes')
        }),
        ('Prix', {
            'fields': ('prix_unitaire', 'prix_promotionnel', 'date_debut', 'date_fin', 'stock_quantite', 'seuil_alerte_stock')
        }),
        ('Images', {
            'fields': ('image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description="Aperçu")
    def apercu_image_col(self, obj):
        return apercu_image(obj.image_principale)

    @admin.display(description="Stock")
    def statut_stock(self, obj):
        return statut_stock_html(obj.stock_quantite, obj.seuil_alerte_stock)

    @admin.display(description="Réduction")
    def badge_taux(self, obj):
        if obj.prix_promotionnel and obj.prix_unitaire:
            taux = (1 - obj.prix_promotionnel / obj.prix_unitaire) * 100
            return badge_reduction(round(taux, 1))
        return badge_reduction(None)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('type_accessoire')


# ============================================================
# FLACONS
# ============================================================
@admin.register(TypeFlacon)
class TypeFlaconAdmin(admin.ModelAdmin):
    list_display  = (
        'id', 'nom',
        'badge_taux_reduction',
        'actif', 'date_creation'
    )
    list_filter   = ('actif',)
    search_fields = ('nom', 'description')
    list_per_page = 50
    readonly_fields = ('date_creation',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'description', 'image')
        }),
        ('Promotion type', {
            'fields': ('taux_reduction',),
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description="Réduction")
    def badge_taux_reduction(self, obj):
        return badge_reduction(obj.taux_reduction)


@admin.register(Flacon)
class FlaconAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'apercu_image_col', 'nom', 'type_flacon',
        'contenance_ml', 'matiere', 'prix_unitaire',
        'statut_stock', 'actif'
    )
    list_filter     = ('type_flacon', 'matiere', 'couleur', 'actif', 'date_creation')
    search_fields   = ('nom', 'reference_sku')
    readonly_fields = ('date_creation', 'date_modification')
    list_editable   = ('prix_unitaire', 'actif')
    list_per_page   = 50

    fieldsets = (
        ('Informations générales', {
            'fields': ('type_flacon', 'nom', 'reference_sku')
        }),
        ('Caractéristiques', {
            'fields': ('contenance_ml', 'matiere', 'couleur', 'hauteur_cm', 'largeur_cm', 'poids_grammes')
        }),
        ('Prix et stock', {
            'fields': ('prix_unitaire', 'stock_quantite', 'seuil_alerte_stock')
        }),
        ('Images', {
            'fields': ('image_principale', 'image_supp_1', 'image_supp_2', 'image_supp_3', 'image_supp_4')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description="Aperçu")
    def apercu_image_col(self, obj):
        return apercu_image(obj.image_principale)

    @admin.display(description="Stock")
    def statut_stock(self, obj):
        return statut_stock_html(obj.stock_quantite, obj.seuil_alerte_stock)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('type_flacon')


# ============================================================
# NOTIFICATIONS CATALOGUE
# ============================================================
@admin.register(NotificationCatalogue)
class NotificationCatalogueAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'type_produit', 'product_name', 'stock_actuel_vs_seuil', 
        'est_lu_badge', 'created_at'
    )
    list_filter = ('type_produit', 'est_lu', 'created_at')
    search_fields = ('product_name', 'message')
    readonly_fields = ('created_at', 'updated_at', 'est_encore_en_alerte')
    list_per_page = 50
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Produit', {
            'fields': ('type_produit', 'product_id', 'product_name')
        }),
        ('Stock', {
            'fields': ('stock_actuel', 'seuil_alerte', 'est_encore_en_alerte')
        }),
        ('Message', {
            'fields': ('message',)
        }),
        ('Statut', {
            'fields': ('est_lu',)
        }),
        ('Métadonnées', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['marquer_comme_lu', 'marquer_comme_non_lu']
    
    @admin.display(description="Alerte")
    def stock_actuel_vs_seuil(self, obj):
        color = 'red' if obj.est_encore_en_alerte else 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}/{}</span>',
            color,
            obj.stock_actuel,
            obj.seuil_alerte
        )
    
    @admin.display(description="Lue", boolean=True)
    def est_lu_badge(self, obj):
        return obj.est_lu
    
    @admin.action(description="Marquer comme lue")
    def marquer_comme_lu(self, request, queryset):
        updated = queryset.update(est_lu=True)
        self.message_user(request, f"{updated} notification(s) marquée(s) comme lue(s).")
    
    @admin.action(description="Marquer comme non-lue")
    def marquer_comme_non_lu(self, request, queryset):
        updated = queryset.update(est_lu=False)
        self.message_user(request, f"{updated} notification(s) marquée(s) comme non-lue(s).")
