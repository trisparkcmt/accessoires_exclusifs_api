# catalogue/filters.py
import django_filters
from django.db import models
from .models import Parfum, Essence, Accessoire, Flacon


# ============================================================
# HELPER — filtre par type de tag
# ============================================================
def filtrer_par_tag_type(queryset, tag_type, valeur):
    """
    Filtre un queryset par nom de tag ET type de tag.
    Utilise icontains pour la recherche partielle.
    Ex: filtrer_par_tag_type(qs, 'famille_olfactive', 'Floral')
    """
    return queryset.filter(
        tags__nom__icontains=valeur,
        tags__type=tag_type
    ).distinct()


# ============================================================
# FILTRE PARFUMS
# ============================================================
class ParfumFilter(django_filters.FilterSet):

    # --- Filtres par tags ---
    tags              = django_filters.BaseInFilter(field_name='tags__id', lookup_expr='in')
    famille_olfactive = django_filters.CharFilter(method='filter_famille_olfactive')
    humeur            = django_filters.CharFilter(method='filter_humeur')
    saison            = django_filters.CharFilter(method='filter_saison')
    occasion          = django_filters.CharFilter(method='filter_occasion')

    # --- Autres filtres ---
    marque        = django_filters.CharFilter(field_name='marque', lookup_expr='icontains')
    genre         = django_filters.CharFilter(field_name='genre_cible')
    intensite     = django_filters.CharFilter(field_name='intensite')
    contenance_ml = django_filters.NumberFilter(field_name='contenance_ml')
    prix_min      = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='gte')
    prix_max      = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='lte')
    est_nouveau      = django_filters.BooleanFilter(field_name='est_nouveau')
    est_bestseller   = django_filters.BooleanFilter(field_name='est_bestseller')

    def filter_famille_olfactive(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'famille_olfactive', value)

    def filter_humeur(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'humeur', value)

    def filter_saison(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'saison', value)

    def filter_occasion(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'occasion', value)

    class Meta:
        model  = Parfum
        fields = ['marque', 'genre', 'intensite', 'contenance_ml', 'prix_min', 'prix_max']


# ============================================================
# FILTRE ESSENCES
# ============================================================
class EssenceFilter(django_filters.FilterSet):

    # --- Filtres par tags ---
    tags               = django_filters.BaseInFilter(field_name='tags__id', lookup_expr='in')
    famille_olfactive  = django_filters.CharFilter(method='filter_famille_olfactive')
    humeur             = django_filters.CharFilter(method='filter_humeur')
    saison             = django_filters.CharFilter(method='filter_saison')
    occasion           = django_filters.CharFilter(method='filter_occasion')
    signe_astrologique = django_filters.CharFilter(method='filter_signe_astrologique')
    moment_journee     = django_filters.CharFilter(method='filter_moment_journee')

    # --- Autres filtres ---
    genre     = django_filters.CharFilter(field_name='genre_cible')
    intensite = django_filters.CharFilter(field_name='intensite')
    prix_min  = django_filters.NumberFilter(field_name='prix_par_ml', lookup_expr='gte')
    prix_max  = django_filters.NumberFilter(field_name='prix_par_ml', lookup_expr='lte')
    stock_min = django_filters.NumberFilter(field_name='stock_ml_total_reel', lookup_expr='gte')

    def filter_famille_olfactive(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'famille_olfactive', value)

    def filter_humeur(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'humeur', value)

    def filter_saison(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'saison', value)

    def filter_occasion(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'occasion', value)

    def filter_signe_astrologique(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'signe_astrologique', value)

    def filter_moment_journee(self, queryset, name, value):
        return filtrer_par_tag_type(queryset, 'moment_journee', value)

    class Meta:
        model  = Essence
        fields = ['genre', 'intensite', 'prix_min', 'prix_max', 'stock_min']


# ============================================================
# FILTRE ACCESSOIRES
# ============================================================
class AccessoireFilter(django_filters.FilterSet):

    marque          = django_filters.CharFilter(field_name='marque', lookup_expr='icontains')
    type_accessoire = django_filters.NumberFilter(field_name='type_accessoire__id')
    type_nom        = django_filters.CharFilter(
        field_name='type_accessoire__nom',
        lookup_expr='icontains'
    )
    prix_min  = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='gte')
    prix_max  = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='lte')
    couleur   = django_filters.CharFilter(field_name='couleur',  lookup_expr='icontains')
    matiere   = django_filters.CharFilter(field_name='matiere',  lookup_expr='icontains')
    taille    = django_filters.CharFilter(field_name='taille',   lookup_expr='icontains')
    en_stock  = django_filters.BooleanFilter(method='filter_en_stock')

    def filter_en_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantite__gt=models.F('seuil_alerte_stock'))
        return queryset.filter(stock_quantite__lte=models.F('seuil_alerte_stock'))

    class Meta:
        model  = Accessoire
        fields = ['marque', 'type_accessoire', 'couleur', 'matiere', 'taille']


# ============================================================
# FILTRE FLACONS
# ============================================================
class FlaconFilter(django_filters.FilterSet):

    type_flacon    = django_filters.NumberFilter(field_name='type_flacon__id')
    type_nom       = django_filters.CharFilter(
        field_name='type_flacon__nom',
        lookup_expr='icontains'
    )
    contenance_ml  = django_filters.NumberFilter(field_name='contenance_ml')
    contenance_min = django_filters.NumberFilter(field_name='contenance_ml', lookup_expr='gte')
    contenance_max = django_filters.NumberFilter(field_name='contenance_ml', lookup_expr='lte')
    stock_min      = django_filters.NumberFilter(field_name='stock_quantite', lookup_expr='gte')
    stock_max      = django_filters.NumberFilter(field_name='stock_quantite', lookup_expr='lte')
    en_stock       = django_filters.BooleanFilter(method='filter_en_stock')
    matiere        = django_filters.CharFilter(field_name='matiere', lookup_expr='icontains')
    couleur        = django_filters.CharFilter(field_name='couleur', lookup_expr='icontains')

    def filter_en_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantite__gt=models.F('seuil_alerte_stock'))
        return queryset.filter(stock_quantite__lte=models.F('seuil_alerte_stock'))

    class Meta:
        model  = Flacon
        fields = ['type_flacon', 'contenance_ml', 'matiere', 'couleur']


# ============================================================
# FUTURE_UPDATE_DIFFUSEUR: FILTRE DIFFUSEURS (COMMENTÉ)
# ============================================================
# class DiffuseurParfumFilter(django_filters.FilterSet):
#     marque    = django_filters.CharFilter(field_name='marque', lookup_expr='icontains')
#     prix_min  = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='gte')
#     prix_max  = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='lte')
#     couleur   = django_filters.CharFilter(field_name='couleur',  lookup_expr='icontains')
#     materiau  = django_filters.CharFilter(field_name='materiau', lookup_expr='icontains')
#     en_stock  = django_filters.BooleanFilter(method='filter_en_stock')
#
#     def filter_en_stock(self, queryset, name, value):
#         if value:
#             return queryset.filter(stock_quantite__gt=models.F('seuil_alerte_stock'))
#         return queryset.filter(stock_quantite__lte=models.F('seuil_alerte_stock'))
#
#     class Meta:
#         model  = DiffuseurParfum
#         fields = ['marque', 'couleur', 'materiau']

