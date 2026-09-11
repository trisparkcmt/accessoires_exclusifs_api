# catalogue/filters.py
import django_filters
from django.db import models
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q, Case, When, Value, IntegerField
from .models import Parfum, Essence, Accessoire, Flacon, DiffuseurParfum


# ============================================================
# RECHERCHE & TRI PERSONNALISÉS (Recherche ordonnée / priorisée)
# ============================================================
class OrderedSearchFilter(SearchFilter):
    """
    Filtre de recherche textuelle avec ordre de priorité strict :
    1. Nom commence par le terme recherché
    2. Nom contient le terme recherché
    3. Marque contient le terme recherché
    4. Catégorie / Type contient le terme recherché
    5. Tags (nom ou valeur associée) contiennent le terme recherché
    """
    def filter_queryset(self, request, queryset, view):
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        search_query = params.get(self.search_param, '').strip()
        if not search_query:
            return queryset

        model = queryset.model

        # 1. Nom commence par
        q_nom_start = Q(nom__istartswith=search_query)
        # 2. Nom contient (hors startswith)
        q_nom_contains = Q(nom__icontains=search_query) & ~q_nom_start
        # 3. Marque
        q_marque = Q(marque__icontains=search_query) if hasattr(model, 'marque') else Q()

        # 4. Catégorie / Type
        q_categorie = Q()
        if hasattr(model, 'categorie'):
            try:
                field = model._meta.get_field('categorie')
                if field.is_relation:
                    q_categorie = Q(categorie__nom__icontains=search_query)
                else:
                    q_categorie = Q(categorie__icontains=search_query)
            except Exception:
                q_categorie = Q()
        elif hasattr(model, 'type_accessoire'):
            q_categorie = Q(type_accessoire__nom__icontains=search_query)

        # 5. Tags (nom ou valeur associée)
        q_tags = Q()
        if hasattr(model, 'tags'):
            q_tags = Q(tags__nom__icontains=search_query) | Q(tags_associes__valeur__icontains=search_query)

        combined_filter = q_nom_start | q_nom_contains | q_marque | q_categorie | q_tags

        queryset = queryset.filter(combined_filter).annotate(
            search_priority=Case(
                When(q_nom_start, then=Value(1)),
                When(q_nom_contains, then=Value(2)),
                When(q_marque, then=Value(3)),
                When(q_categorie, then=Value(4)),
                When(q_tags, then=Value(5)),
                default=Value(6),
                output_field=IntegerField()
            )
        ).distinct()

        if not params.get('ordering'):
            queryset = queryset.order_by('search_priority', 'nom')

        return queryset


class CustomOrderingFilter(OrderingFilter):
    """
    Conserve le tri par priorité de recherche lorsque `search` est utilisé sans paramètre `ordering` explicite.
    """
    def filter_queryset(self, request, queryset, view):
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        if params.get('search') and not params.get(self.ordering_param):
            return queryset
        return super().filter_queryset(request, queryset, view)



# ============================================================
# HELPER — filtre par tag
# ============================================================
def filtrer_par_tag(queryset, valeur):
    """
    Filtre un queryset par nom de tag OU par la valeur du tag associée au produit.
    """
    return queryset.filter(
        models.Q(tags__nom__icontains=valeur) | models.Q(tags_associes__valeur__icontains=valeur)
    ).distinct()


# ============================================================
# FILTRE PARFUMS
# ============================================================
class ParfumFilter(django_filters.FilterSet):

    # --- Filtres par tags ---
    tags              = django_filters.BaseInFilter(field_name='tags__id', lookup_expr='in')
    famille_olfactive = django_filters.CharFilter(method='filter_by_tag')
    humeur            = django_filters.CharFilter(method='filter_by_tag')
    saison            = django_filters.CharFilter(method='filter_by_tag')
    occasion          = django_filters.CharFilter(method='filter_by_tag')
    tag               = django_filters.CharFilter(method='filter_by_tag')

    # --- Autres filtres ---
    categorie     = django_filters.NumberFilter(field_name='categorie__id')
    marque        = django_filters.CharFilter(field_name='marque', lookup_expr='icontains')
    genre         = django_filters.CharFilter(field_name='genre_cible')
    intensite     = django_filters.CharFilter(field_name='intensite')
    contenance_ml = django_filters.NumberFilter(field_name='contenance_ml')
    prix_min      = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='gte')
    prix_max      = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='lte')
    est_nouveau      = django_filters.BooleanFilter(field_name='est_nouveau')
    est_bestseller   = django_filters.BooleanFilter(field_name='est_bestseller')

    def filter_by_tag(self, queryset, name, value):
        return filtrer_par_tag(queryset, value)

    class Meta:
        model  = Parfum
        fields = ['categorie', 'marque', 'genre', 'intensite', 'contenance_ml', 'prix_min', 'prix_max']


# ============================================================
# FILTRE ESSENCES
# ============================================================
class EssenceFilter(django_filters.FilterSet):

    # --- Filtres par tags ---
    tags               = django_filters.BaseInFilter(field_name='tags__id', lookup_expr='in')
    famille_olfactive  = django_filters.CharFilter(method='filter_by_tag')
    humeur             = django_filters.CharFilter(method='filter_by_tag')
    saison             = django_filters.CharFilter(method='filter_by_tag')
    occasion           = django_filters.CharFilter(method='filter_by_tag')
    signe_astrologique = django_filters.CharFilter(method='filter_by_tag')
    moment_journee     = django_filters.CharFilter(method='filter_by_tag')
    tag                = django_filters.CharFilter(method='filter_by_tag')

    # --- Autres filtres ---
    genre     = django_filters.CharFilter(field_name='genre_cible')
    intensite = django_filters.CharFilter(field_name='intensite')
    prix_min  = django_filters.NumberFilter(field_name='prix_par_ml', lookup_expr='gte')
    prix_max  = django_filters.NumberFilter(field_name='prix_par_ml', lookup_expr='lte')
    stock_min = django_filters.NumberFilter(field_name='stock_ml_total_reel', lookup_expr='gte')

    def filter_by_tag(self, queryset, name, value):
        return filtrer_par_tag(queryset, value)

    class Meta:
        model  = Essence
        fields = ['genre', 'intensite', 'prix_min', 'prix_max', 'stock_min']


# ============================================================
# FILTRE ACCESSOIRES
# ============================================================
class AccessoireFilter(django_filters.FilterSet):

    tags            = django_filters.BaseInFilter(field_name='tags__id', lookup_expr='in')
    tag             = django_filters.CharFilter(method='filter_by_tag')
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

    def filter_by_tag(self, queryset, name, value):
        return filtrer_par_tag(queryset, value)

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
# FILTRE DIFFUSEURS
# ============================================================
class DiffuseurParfumFilter(django_filters.FilterSet):
    marque              = django_filters.CharFilter(field_name='marque', lookup_expr='icontains')
    prix_min            = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='gte')
    prix_max            = django_filters.NumberFilter(field_name='prix_unitaire', lookup_expr='lte')
    couleur             = django_filters.CharFilter(field_name='couleur',  lookup_expr='icontains')
    materiau            = django_filters.CharFilter(field_name='materiau', lookup_expr='icontains')
    type_technologie    = django_filters.CharFilter(field_name='type_technologie')
    type_alimentation   = django_filters.CharFilter(field_name='type_alimentation')
    est_connecte        = django_filters.BooleanFilter(field_name='est_connecte')
    a_jeux_de_lumiere   = django_filters.BooleanFilter(field_name='a_jeux_de_lumiere')
    capacite_min        = django_filters.NumberFilter(field_name='capacite_reservoir_ml', lookup_expr='gte')
    capacite_max        = django_filters.NumberFilter(field_name='capacite_reservoir_ml', lookup_expr='lte')
    surface_min         = django_filters.NumberFilter(field_name='surface_couverture_m2', lookup_expr='gte')
    en_stock            = django_filters.BooleanFilter(method='filter_en_stock')

    def filter_en_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantite__gt=models.F('seuil_alerte_stock'))
        return queryset.filter(stock_quantite__lte=models.F('seuil_alerte_stock'))

    class Meta:
        model  = DiffuseurParfum
        fields = ['marque', 'couleur', 'materiau', 'type_technologie', 'type_alimentation']

