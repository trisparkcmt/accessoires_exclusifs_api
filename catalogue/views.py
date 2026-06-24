# views.py
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Sum
from django.db import models
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework.permissions import IsAuthenticated
from orders.models import CommandeLigneAccessoire
from .permissions import IsAdminOrReadOnly, IsAdmin, IsAdminOrServeuse, IsAdminOrServeuseOrReadOnly

from .models import CategorieParfum, LotEssence, Parfum, Essence, Accessoire, Flacon, Favori, Ingredient, ProduitFiniEssence, Tag, TypeAccessoire, TypeFlacon, NotificationCatalogue, MouvementStock
from .serializers import (
    AccessoireAdminDetailSerializer, AccessoireAdminListSerializer, AccessoirePublicDetailSerializer, AccessoirePublicListSerializer, AccessoireSimilaireSerializer, CategorieParfumSerializer, EssenceLaboDetailSerializer, EssenceLaboListSerializer, LotEssenceSerializer, ParfumAdminDetailSerializer, ParfumAdminListSerializer, ParfumPublicDetailSerializer, ParfumPublicListSerializer, ParfumSerializer, EssenceSerializer,
    AccessoireSerializer, FlaconSerializer, FlaconPublicSerializer, ParfumSimilaireSerializer, EssenceCreateFullSerializer,
    IngredientSerializer, FavoriSerializer, ProduitFiniEssencePublicSerializer, ProduitFiniEssenceSerializer, PromotionSerializer, TagSelectSerializer, TagSerializer, TypeAccessoireSerializer, TypeFlaconSerializer, NotificationCatalogueSerializer, NotificationCatalogueUpdateSerializer,
    get_image_url,
)
from django.db.models import Case, When
from .filters import (
    ParfumFilter, EssenceFilter,
    AccessoireFilter, FlaconFilter,
)
from .pagination import StandardPagination


# ============================================================
# PARFUMS
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des parfums",
        description="""
Retourne la liste paginée de tous les parfums **actifs** du catalogue.

**Pagination** : 50 résultats par page. Utilisez `?page=2` pour naviguer.

**Filtres disponibles** :
- Par tags : `famille_olfactive`, `humeur`, `saison`, `occasion`
- Par caractéristiques : `genre`, `intensite`, `contenance_ml`
- Par prix : `prix_min`, `prix_max`
- Par statut : `est_nouveau`, `est_bestseller`

**Tri** : `?ordering=prix_unitaire` ou `?ordering=-date_creation`

**Recherche textuelle** : `?search=rose` (cherche dans nom, description, notes)
        """,
        tags=["Parfums"],
        parameters=[
            OpenApiParameter(
                name="famille_olfactive",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Famille olfactive (ex: Floral, Boisé, Oriental, Aquatique)",
                required=False,
            ),
            OpenApiParameter(
                name="humeur",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Humeur compatible (ex: Romantique, Détendu, Énergique)",
                required=False,
            ),
            OpenApiParameter(
                name="saison",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Saison compatible (ex: Été, Hiver, Printemps, Automne)",
                required=False,
            ),
            OpenApiParameter(
                name="occasion",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Occasion (ex: Soirée, Bureau, Sport, Quotidien)",
                required=False,
            ),
            OpenApiParameter(
                name="genre",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Genre cible",
                enum=["homme", "femme", "mixte"],
                required=False,
            ),
            OpenApiParameter(
                name="intensite",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Intensité du parfum",
                enum=["légère", "moyenne", "forte", "très forte"],
                required=False,
            ),
            OpenApiParameter(
                name="contenance_ml",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Contenance exacte en ml (ex: 30, 50, 75, 100)",
                required=False,
            ),
            OpenApiParameter(
                name="prix_min",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Prix minimum en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="prix_max",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Prix maximum en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="est_nouveau",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filtrer les nouveautés uniquement",
                required=False,
            ),
            OpenApiParameter(
                name="est_bestseller",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filtrer les bestsellers uniquement",
                required=False,
            ),
            OpenApiParameter(
                name="tags",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="IDs de tags séparés par virgule (ex: ?tags=1,3,5)",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Recherche textuelle dans nom, description et notes olfactives",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Tri des résultats (ex: prix_unitaire, -prix_unitaire, nom, -date_creation)",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Numéro de page (défaut: 1)",
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Nombre de résultats par page (défaut: 50, max: 100)",
                required=False,
            ),
        ],
        examples=[
            OpenApiExample(
                name="Parfums floraux féminins",
                summary="Filtrer par famille olfactive et genre",
                value={"famille_olfactive": "Floral", "genre": "femme"},
            ),
            OpenApiExample(
                name="Parfums dans une fourchette de prix",
                summary="Filtrer par prix",
                value={"prix_min": 15000, "prix_max": 50000},
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Détail d'un parfum",
        description="""
Récupère les informations complètes d'un parfum via son **slug**.

Retourne également :
- Les tags associés (famille olfactive, humeur, saison, occasion)
- Le `prix_actuel` (prix promotionnel si disponible, sinon prix normal)
- Les notes olfactives (tête, cœur, fond)
        """,
        tags=["Parfums"],
        examples=[
            OpenApiExample(
                name="Exemple de réponse",
                summary="Parfum Royal Oud",
                value={
                    "id": 1,
                    "nom": "Royal Oud",
                    "slug": "royal-oud",
                    "prix_actuel": "35000.00",
                    "famille_olfactive": ["Boisé", "Oriental"],
                    "humeurs_compatibles": ["Romantique"],
                    "saisons_compatibles": ["Hiver", "Automne"],
                },
            ),
        ],
    ),
)
class ParfumViewSet(viewsets.ModelViewSet):
    serializer_class   = ParfumSerializer
    pagination_class   = StandardPagination
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    filterset_class    = ParfumFilter
    search_fields      = ['marque', 'nom', 'description_courte', 'notes_tete', 'notes_coeur', 'notes_fond']
    ordering_fields    = ['prix_unitaire', 'date_creation', 'nom', 'contenance_ml']
    ordering           = ['?']
    lookup_field       = 'slug'

    def get_queryset(self):
        if self.request.user.is_staff:
            return Parfum.objects.all().select_related('categorie').prefetch_related('tags')
        return Parfum.objects.filter(actif=True).select_related('categorie').prefetch_related('tags')

    def get_serializer_class(self):
        is_admin = self.request.user.is_staff
        if self.action == 'list':
            if is_admin:
                return ParfumAdminListSerializer
            return ParfumPublicListSerializer
        else:
            if is_admin:
                return ParfumAdminDetailSerializer
            return ParfumPublicDetailSerializer

 #Hotseller les parfums les plus vendus    
    @action(detail=False, methods=['get'], url_path='bestsellers')
    def bestsellers(self, request):
        """Top 20 parfums les plus vendus (toutes périodes)"""
        from orders.models import CommandeLigneParfum
        ventes = (
            CommandeLigneParfum.objects.filter(parfum__isnull=False)
            .values('parfum_id')
            .annotate(total=Sum('quantite'))
            .order_by('-total')[:20]
        )
        ids = [v['parfum_id'] for v in ventes if v['total'] > 0]
        # Garder l'ordre du classement
        queryset = Parfum.objects.filter(actif=True, id__in=ids)
        preserved_order = Case(*[When(id=pk, then=pos) for pos, pk in enumerate(ids)])
        queryset = Parfum.objects.filter(actif=True, id__in=ids).order_by(preserved_order)
        serializer = ParfumSimilaireSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

#Hotseller les parfums les plus vendus du moment 
    @action(detail=False, methods=['get'], url_path='hotsellers')
    def hotsellers(self, request):
        """Top 10 parfums les plus vendus du mois en cours"""
        from orders.models import CommandeLigneParfum
        now = timezone.now()
        debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ventes = (
            CommandeLigneParfum.objects.filter(
                parfum__isnull=False,
                commande__date_creation__gte=debut_mois
            )
            .values('parfum_id')
            .annotate(total=Sum('quantite'))
            .order_by('-total')[:10]
        )
        ids = [v['parfum_id'] for v in ventes if v['total'] > 0]
        queryset = Parfum.objects.filter(actif=True, id__in=ids)
        preserved_order = Case(*[When(id=pk, then=pos) for pos, pk in enumerate(ids)])
        queryset = Parfum.objects.filter(actif=True, id__in=ids).order_by(preserved_order)
        serializer = ParfumSimilaireSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    
    #methodes pour les parfums favoris 
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def favori(self, request, slug=None):
        parfum = self.get_object()
        try:
            client = request.user.client
        except AttributeError:
            return Response({'detail': 'Client non associé'}, status=400)
        favori, created = Favori.objects.get_or_create(client=client, parfum=parfum)
        if not created:
            favori.delete()
            return Response({'status': 'retiré', 'is_favori': False})
        return Response({'status': 'ajouté', 'is_favori': True})
    pass  

# ============================================================
# ESSENCES
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des essences",
        description="""
Retourne la liste paginée de toutes les essences **actives**.

Les essences sont les matières premières utilisées pour la création de parfums DIY
dans le laboratoire.

**Filtres disponibles** :
- Par tags : `famille_olfactive`, `humeur`, `saison`, `occasion`, `signe_astrologique`, `moment_journee`
- Par caractéristiques : `genre`, `intensite`
- Par prix : `prix_min`, `prix_max` (prix par ml en FCFA)
- Par stock : `stock_min` (en ml)
        """,
        tags=["Essences"],
        parameters=[
            OpenApiParameter(
                name="famille_olfactive",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Famille olfactive (ex: Floral, Boisé, Musqué)",
                required=False,
            ),
            OpenApiParameter(
                name="humeur",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Humeur compatible (ex: Romantique, Détendu)",
                required=False,
            ),
            OpenApiParameter(
                name="saison",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Saison compatible (ex: Été, Hiver)",
                required=False,
            ),
            OpenApiParameter(
                name="occasion",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Occasion (ex: Soirée, Quotidien)",
                required=False,
            ),
            OpenApiParameter(
                name="signe_astrologique",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Signe astrologique compatible (ex: Lion, Verseau, Scorpion)",
                required=False,
            ),
            OpenApiParameter(
                name="moment_journee",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Moment de la journée (ex: Matin, Soir, Nuit)",
                required=False,
            ),
            OpenApiParameter(
                name="genre",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Genre cible",
                enum=["homme", "femme", "mixte"],
                required=False,
            ),
            OpenApiParameter(
                name="intensite",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Intensité de l'essence",
                enum=["légère", "moyenne", "forte", "très forte"],
                required=False,
            ),
            OpenApiParameter(
                name="prix_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix minimum par ml en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="prix_max",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix maximum par ml en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="stock_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Stock minimum disponible en ml",
                required=False,
            ),
            OpenApiParameter(
                name="tags",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="IDs de tags séparés par virgule (ex: ?tags=1,3,5)",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Recherche textuelle dans nom, description, fournisseur",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Tri (ex: prix_par_ml, -stock_ml_total_reel, nom)",
                required=False,
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Détail d'une essence",
        description="""
Récupère les informations complètes d'une essence via son **ID**.

Retourne également les compatibilités astrologiques et les moments
de la journée recommandés.
        """,
        tags=["Essences"],
    ),
)

# ============================================================
# ESSENCES
# ============================================================

class EssenceViewSet(viewsets.ModelViewSet):
    serializer_class = EssenceSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = EssenceFilter   # vous devrez adapter EssenceFilter plus tard
    search_fields = ['marque', 'nom', 'code_reference']
    ordering_fields = ['marque', 'nom', 'date_creation']
    ordering = ['marque', 'nom']
    lookup_field = 'slug'

    def get_queryset(self):
        if self.request.user.is_staff:
            return Essence.objects.all().prefetch_related('tags')
        return Essence.objects.filter(actif=True).prefetch_related('tags')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return EssenceCreateFullSerializer
        return EssenceSerializer

class LotEssenceViewSet(viewsets.ModelViewSet):
    serializer_class = LotEssenceSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]   # lecture publique, écriture admin
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['essence', 'actif']
    ordering           = ['date_reception']

    def get_queryset(self):
        if self.request.user.is_staff:
            return LotEssence.objects.all().select_related('essence')
        return LotEssence.objects.filter(actif=True).select_related('essence')
    
class ProduitFiniEssenceViewSet(viewsets.ModelViewSet):
    serializer_class = ProduitFiniEssencePublicSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['essence', 'taille_ml']
    search_fields = ['essence__marque', 'essence__nom'] 
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
             return ProduitFiniEssenceSerializer   # sérialiseur d'écriture
        return ProduitFiniEssencePublicSerializer  # lecture publique

    def get_queryset(self):
        return ProduitFiniEssence.objects.filter(actif=True, stock_disponible__gt=0).select_related('essence')


class PromotionViewSet(viewsets.GenericViewSet):
    serializer_class = PromotionSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]

    def list(self, request, *args, **kwargs):
        promotions = []

        parfums = Parfum.objects.filter(actif=True).select_related('categorie')
        for parfum in parfums:
            item = self._promotion_parfum(parfum, request)
            if item:
                promotions.append(item)

        accessoires = Accessoire.objects.filter(actif=True).select_related('type_accessoire')
        for accessoire in accessoires:
            item = self._promotion_accessoire(accessoire, request)
            if item:
                promotions.append(item)

        produits_essence = ProduitFiniEssence.objects.filter(
            actif=True,
            stock_disponible__gt=0,
            prix_promotionnel__isnull=False,
        ).select_related('essence')
        for produit in produits_essence:
            item = self._promotion_produit_essence(produit, request)
            if item:
                promotions.append(item)

        promotions.sort(key=lambda item: item['taux_reduction'], reverse=True)
        page = self.paginate_queryset(promotions)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(promotions, many=True)
        return Response(serializer.data)

    def _promotion_parfum(self, parfum, request):
        promo = parfum.prix_promotionnel_effectif
        if promo is None or promo >= parfum.prix_unitaire:
            return None

        manuel = parfum.prix_promotionnel is not None and parfum.promotion_article_active() and promo == parfum.prix_promotionnel
        source = parfum if manuel else parfum.categorie
        return self._build_item(
            type_article='parfum',
            identifiant=parfum.id,
            slug=parfum.slug,
            nom=parfum.nom,
            marque=parfum.marque,
            image=get_image_url(request, parfum.image_principale),
            prix_original=parfum.prix_unitaire,
            prix_promotionnel=promo,
            message='' if manuel or source is None else source.message_promotion,
            date_debut=getattr(source, 'date_debut', None),
            date_fin=getattr(source, 'date_fin', None),
        )

    def _promotion_accessoire(self, accessoire, request):
        promo = accessoire.prix_promotionnel_effectif
        if promo is None or promo >= accessoire.prix_unitaire:
            return None

        manuel = accessoire.prix_promotionnel is not None and accessoire.promotion_article_active() and promo == accessoire.prix_promotionnel
        source = accessoire if manuel else accessoire.type_accessoire
        return self._build_item(
            type_article='accessoire',
            identifiant=accessoire.id,
            slug=accessoire.slug,
            nom=accessoire.nom,
            marque=accessoire.marque,
            image=get_image_url(request, accessoire.image_principale),
            prix_original=accessoire.prix_unitaire,
            prix_promotionnel=promo,
            message='' if manuel or source is None else source.message_promotion,
            date_debut=getattr(source, 'date_debut', None),
            date_fin=getattr(source, 'date_fin', None),
        )

    def _promotion_produit_essence(self, produit, request):
        promo = produit.prix_promotionnel
        if promo is None or promo >= produit.prix:
            return None

        return self._build_item(
            type_article='produit_essence',
            identifiant=produit.id,
            slug=None,
            nom=f"{produit.essence.nom} {produit.taille_ml}ml",
            marque=produit.essence.marque,
            image=get_image_url(request, produit.image_principale),
            prix_original=produit.prix,
            prix_promotionnel=promo,
            message='',
            date_debut=None,
            date_fin=None,
        )

    def _build_item(self, type_article, identifiant, slug, nom, marque, image, prix_original, prix_promotionnel, message, date_debut, date_fin):
        taux = (1 - prix_promotionnel / prix_original) * 100
        return {
            'type_article': type_article,
            'id': identifiant,
            'slug': slug,
            'nom': nom,
            'marque': marque or '',
            'image_principale': image,
            'prix_original': prix_original,
            'prix_promotionnel': prix_promotionnel,
            'taux_reduction': round(float(taux), 1),
            'message_promotion': message or '',
            'date_debut': date_debut,
            'date_fin': date_fin,
        }
    

class EssenceLaboViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'], url_path='disponible')
    def disponible(self, request):
        essences = Essence.objects.filter(actif=True).prefetch_related('lots')
        serializer = EssenceLaboListSerializer(essences, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='detail', lookup_field='slug')
    def detail_labo(self, request, slug=None):
        essence = get_object_or_404(Essence, slug=slug, actif=True)
        serializer = EssenceLaboDetailSerializer(essence, context={'request': request})
        return Response(serializer.data)

    
    
# ============================================================
# INGRÉDIENTS
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des ingrédients",
        description="""
Retourne la liste paginée de tous les ingrédients **actifs**.

Les ingrédients sont les composants individuels utilisés dans le laboratoire
pour créer des parfums personnalisés.

**Filtres disponibles** :
- Par prix : `prix_min`, `prix_max` (prix par ml en FCFA)
- Par stock : `stock_min` (en ml)
        """,
        tags=["Ingrédients"],
        parameters=[
            OpenApiParameter(
                name="prix_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix minimum par ml en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="prix_max",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix maximum par ml en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="stock_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Stock minimum disponible en ml",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Recherche textuelle dans nom et description",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Tri (ex: prix_par_ml, -stock_ml, nom)",
                required=False,
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Détail d'un ingrédient",
        description="Récupère les informations complètes d'un ingrédient via son **ID**.",
        tags=["Ingrédients"],
    ),
)
class IngredientViewSet(viewsets.ModelViewSet):
    serializer_class   = IngredientSerializer
    pagination_class   = StandardPagination
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    search_fields      = ['nom', 'description']
    ordering_fields    = ['prix_par_ml', 'date_creation', 'nom', 'stock_ml']

    ordering           = ['-nom']
    lookup_field       = 'slug'

    def get_queryset(self):
        return Ingredient.objects.filter(actif=True)


# ============================================================
# INGRÉDIENTS
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des ingrédients",
        description="""
Retourne la liste paginée de tous les ingrédients **actifs**.

Les ingrédients sont les composants individuels utilisés dans le laboratoire
pour créer des parfums personnalisés.

**Filtres disponibles** :
- Par prix : `prix_min`, `prix_max` (prix par ml en FCFA)
- Par stock : `stock_min` (en ml)
        """,
        tags=["Ingrédients"],
        parameters=[
            OpenApiParameter(
                name="prix_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix minimum par ml en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="prix_max",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix maximum par ml en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="stock_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Stock minimum disponible en ml",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Recherche textuelle dans nom et description",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Tri (ex: prix_par_ml, -stock_ml, nom)",
                required=False,
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Détail d'un ingrédient",
        description="Récupère les informations complètes d'un ingrédient via son **ID**.",
        tags=["Ingrédients"],
    ),
)
class IngredientViewSet(viewsets.ModelViewSet):
    serializer_class   = IngredientSerializer
    pagination_class   = StandardPagination
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields      = ['nom', 'description']
    ordering_fields    = ['prix_par_ml', 'date_creation', 'nom', 'stock_ml']
    ordering           = ['-nom']

    def get_queryset(self):
        return Ingredient.objects.filter(actif=True)


# ============================================================
# ACCESSOIRES
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des accessoires",
        description="""
Retourne la liste paginée de tous les accessoires **actifs**.

**Filtres disponibles** :
- Par type : `type_accessoire` (ID) ou `type_nom` (nom partiel)
- Par prix : `prix_min`, `prix_max`
- Par caractéristiques : `couleur`, `matiere`, `taille`
- Par stock : `en_stock=true` (stock > seuil d'alerte)
        """,
        tags=["Accessoires"],
        parameters=[
            OpenApiParameter(
                name="type_accessoire",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="ID du type d'accessoire",
                required=False,
            ),
            OpenApiParameter(
                name="type_nom",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Nom partiel du type (ex: Diffuseur, Bougie, Pochette)",
                required=False,
            ),
            OpenApiParameter(
                name="prix_min",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix minimum en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="prix_max",
                type=OpenApiTypes.NUMBER,
                location=OpenApiParameter.QUERY,
                description="Prix maximum en FCFA",
                required=False,
            ),
            OpenApiParameter(
                name="couleur",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Couleur de l'accessoire (ex: Noir, Doré, Transparent)",
                required=False,
            ),
            OpenApiParameter(
                name="matiere",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Matière (ex: Bois, Cuir, Verre, Métal)",
                required=False,
            ),
            OpenApiParameter(
                name="taille",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Taille (ex: S, M, L, XL)",
                required=False,
            ),
            OpenApiParameter(
                name="en_stock",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="`true` = stock suffisant | `false` = stock faible ou épuisé",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Recherche textuelle dans nom, description, matière, couleur",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Tri (ex: prix_unitaire, -prix_unitaire, nom)",
                required=False,
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Détail d'un accessoire",
        description="Récupère les informations complètes d'un accessoire via son **slug**.",
        tags=["Accessoires"],
    ),
)
class AccessoireViewSet(viewsets.ModelViewSet):
    serializer_class   = AccessoireSerializer
    pagination_class   = StandardPagination
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    filterset_class    = AccessoireFilter
    search_fields      = ['marque', 'nom', 'description_courte', 'matiere', 'couleur']
    ordering_fields    = ['prix_unitaire', 'date_creation', 'nom', 'poids_grammes']
    # L'attribut 'ordering' par défaut est maintenant géré dynamiquement dans get_queryset
    ordering           = [] 
    lookup_field       = 'slug'

    def get_queryset(self):
        if self.request.user.is_staff:
            # Pour l'admin, afficher tous les accessoires, triés par date de création (du plus récent au plus ancien)
            return Accessoire.objects.all().select_related('type_accessoire').order_by('-date_creation')
        # Pour les utilisateurs non-admin, afficher uniquement les accessoires actifs, triés aléatoirement
        return Accessoire.objects.filter(actif=True).select_related('type_accessoire').order_by('?')

    def get_serializer_class(self):
        is_admin = self.request.user.is_staff
        if self.action == 'list':
            if is_admin:
                return AccessoireAdminListSerializer
            return AccessoirePublicListSerializer
        else:
            if is_admin:
                return AccessoireAdminDetailSerializer
            return AccessoirePublicDetailSerializer
    
    @action(detail=False, methods=['get'], url_path='bestsellers')
    def bestsellers(self, request):
        """Top 20 parfums les plus vendus (toutes périodes)"""
        from orders.models import CommandeLigneAccessoire
        ventes = (
            CommandeLigneAccessoire.objects.filter(accessoire__isnull=False)
            .values('accessoire_id')
            .annotate(total=Sum('quantite'))
            .order_by('-total')[:20]
        )
        ids = [v['accessoire_id'] for v in ventes if v['total'] > 0]
        # Garder l'ordre du classement
        queryset = Accessoire.objects.filter(actif=True, id__in=ids)
        order = {id: idx for idx, id in enumerate(ids)}
        queryset = sorted(queryset, key=lambda p: order.get(p.id, 999))
        serializer = AccessoireSimilaireSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='hotsellers')
    def hotsellers(self, request):
        """Top 10 parfums les plus vendus du mois en cours"""
        from orders.models import CommandeLigneAccessoire
        now = timezone.now()
        debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ventes = (
            CommandeLigneAccessoire.objects.filter(
                accessoire__isnull=False,
                commande__date_creation__gte=debut_mois
            )
            .values('accessoire_id')
            .annotate(total=Sum('quantite'))
            .order_by('-total')[:10]
        )
        ids = [v['accessoire_id'] for v in ventes if v['total'] > 0]
        queryset = Accessoire.objects.filter(actif=True, id__in=ids)
        order = {id: idx for idx, id in enumerate(ids)}
        queryset = sorted(queryset, key=lambda p: order.get(p.id, 999))
        serializer = AccessoireSimilaireSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    #accessoires favoris 
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def favori(self, request, slug=None):
        accessoire = self.get_object()
        try:
            client = request.user.client
        except AttributeError:
            return Response({'detail': 'Client non associé'}, status=400)
        favori, created = Favori.objects.get_or_create(client=client, accessoire=accessoire)
        if not created:
            favori.delete()
            return Response({'status': 'retiré', 'is_favori': False})
        return Response({'status': 'ajouté', 'is_favori': True})
# ============================================================
# FLACONS
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des flacons",
        description="""
Retourne la liste paginée de tous les flacons **actifs**.

Les flacons sont utilisés pour le conditionnement des parfums personnalisés
créés dans le laboratoire DIY.

> ⚠️ Un flacon dont le stock est **inférieur ou égal au seuil d'alerte**
> ne peut pas être sélectionné pour une commande.

**Filtres disponibles** :
- Par type : `type_flacon` (ID) ou `type_nom` (nom partiel)
- Par contenance : `contenance_ml` (exacte), `contenance_min`, `contenance_max`
- Par stock : `stock_min`, `stock_max`, `en_stock`
- Par caractéristiques : `matiere`, `couleur`
        """,
        tags=["Flacons"],
        parameters=[
            OpenApiParameter(
                name="type_flacon",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="ID du type de flacon",
                required=False,
            ),
            OpenApiParameter(
                name="type_nom",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Nom partiel du type (ex: Spray, Roll-on, Atomiseur)",
                required=False,
            ),
            OpenApiParameter(
                name="contenance_ml",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Contenance exacte en ml (ex: 30, 50, 75, 100)",
                required=False,
            ),
            OpenApiParameter(
                name="contenance_min",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Contenance minimum en ml",
                required=False,
            ),
            OpenApiParameter(
                name="contenance_max",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Contenance maximum en ml",
                required=False,
            ),
            OpenApiParameter(
                name="stock_min",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Quantité minimum en stock",
                required=False,
            ),
            OpenApiParameter(
                name="stock_max",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Quantité maximum en stock",
                required=False,
            ),
            OpenApiParameter(
                name="en_stock",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="`true` = commandable (stock > seuil) | `false` = bloqué (stock ≤ seuil)",
                required=False,
            ),
            OpenApiParameter(
                name="matiere",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Matière du flacon (ex: Verre, Plastique, Aluminium)",
                required=False,
            ),
            OpenApiParameter(
                name="couleur",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Couleur du flacon (ex: Transparent, Noir, Ambré)",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Recherche textuelle dans nom, matière, couleur",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Tri (ex: contenance_ml, -stock_quantite, prix_unitaire)",
                required=False,
            ),
        ],
        examples=[
            OpenApiExample(
                name="Flacons spray 50ml disponibles",
                summary="Filtrer par type et contenance",
                value={"type_nom": "Spray", "contenance_ml": 50, "en_stock": True},
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Détail d'un flacon",
        description="""
Récupère les informations complètes d'un flacon via son **ID**.

Le champ `stock_suffisant` indique si le flacon peut être utilisé
pour une commande (stock > seuil_alerte_stock).
        """,
        tags=["Flacons"],
    ),
)
class FlaconViewSet(viewsets.ModelViewSet):
    serializer_class   = FlaconSerializer
    pagination_class   = StandardPagination
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    filterset_class    = FlaconFilter
    search_fields      = ['nom', 'matiere', 'couleur']
    ordering_fields    = ['prix_unitaire', 'date_creation', 'nom', 'contenance_ml', 'stock_quantite']
    ordering           = ['-date_creation']
    lookup_field       = 'slug'

    def get_queryset(self):
        if self.request.user.is_staff:
            return Flacon.objects.all().select_related('type_flacon')
        return Flacon.objects.filter(actif=True).select_related('type_flacon')

    def get_serializer_class(self):
        if self.action == 'list':
            return FlaconPublicSerializer
        return FlaconSerializer
    
    

class FavoriViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FavoriSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            client = self.request.user.client
            # On ajoute select_related pour charger parfum et accessoire en une seule fois
            return (Favori.objects.filter(client=client)
                    .select_related('parfum', 'accessoire')
                    .order_by('-date_ajout'))
        except AttributeError:
            return Favori.objects.none()
        
class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    serializer_class = TagSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['nom', 'type']
    ordering_fields = ['nom', 'type', 'date_creation']
    ordering = ['nom']
    lookup_field = 'slug'

class TagParfumSelectViewSet(viewsets.ModelViewSet):
    allowed_types = ['famille_olfactive', 'humeur', 'saison', 'occasion']
    serializer_class = TagSelectSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type']
    search_fields = ['nom', 'type']
    ordering_fields = ['nom', 'type']
    ordering = ['type', 'nom']
    lookup_field = 'slug'

    def get_queryset(self):
        return Tag.objects.filter(
            actif=True,
            type__in=self.allowed_types
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['allowed_types'] = self.allowed_types
        return context

class TagEssenceSelectViewSet(viewsets.ModelViewSet):
    serializer_class = TagSelectSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type']
    search_fields = ['nom', 'type']
    ordering_fields = ['nom', 'type']
    ordering = ['type', 'nom']
    lookup_field = 'slug'

    def get_queryset(self):
        return Tag.objects.filter(actif=True)

class CategorieParfumViewSet(viewsets.ModelViewSet):
    queryset = CategorieParfum.objects.filter(actif=True)
    serializer_class = CategorieParfumSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['nom', 'description']
    ordering_fields = ['nom', 'ordre_affichage', 'date_creation']
    ordering = [ 'nom']

class TypeAccessoireViewSet(viewsets.ModelViewSet):
    """
    API pour les types d'accessoires.
    """
    queryset = TypeAccessoire.objects.filter(actif=True)
    serializer_class = TypeAccessoireSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['nom', 'description']
    ordering_fields = ['nom', 'date_creation']
    ordering = ['nom']

class TypeFlaconViewSet(viewsets.ModelViewSet):
    """
    API pour les types de flacons.
    """
    queryset = TypeFlacon.objects.filter(actif=True)
    serializer_class = TypeFlaconSerializer
    permission_classes = [IsAdminOrServeuseOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['nom', 'description']
    ordering_fields = ['nom', 'date_creation']
    ordering = ['nom']


# ============================================================
# NOTIFICATIONS CATALOGUE
# ============================================================
@extend_schema_view(
    list=extend_schema(
        summary="Liste des notifications de stock",
        description="""
Retourne la liste paginée des notifications de catalogue (alertes de stock).

**Filtres disponibles** :
- `type_produit`: essense | accessoire | flacon | lot_essence
- `est_lu`: true | false (notifications lues ou non lues)

**Pagination** : 50 résultats par page. Utilisez `?page=2` pour naviguer.
        """,
    ),
    retrieve=extend_schema(
        summary="Détail d'une notification",
    ),
    partial_update=extend_schema(
        summary="Marquer une notification comme lue",
        description="PATCH /api/catalogue/notifications/{id}/ avec {\"est_lu\": true}",
    ),
)
class NotificationCatalogueViewSet(viewsets.ModelViewSet):
    """
    API pour gérer les notifications de catalogue (alertes de stock).
    
    Les notifications sont créées automatiquement via Django Signals quand un produit
    atteint son seuil d'alerte.
    
    Endpoints:
    - GET /api/catalogue/notifications/ — Liste avec filtres
    - GET /api/catalogue/notifications/{id}/ — Détail d'une notification
    - PATCH /api/catalogue/notifications/{id}/ — Marquer comme lue
    """
    queryset = NotificationCatalogue.objects.all()
    serializer_class = NotificationCatalogueSerializer
    permission_classes = [IsAdminOrServeuse]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type_produit', 'est_lu']
    search_fields = ['product_name', 'message']
    ordering_fields = ['created_at', 'type_produit']
    ordering = ['-created_at']
    pagination_class = StandardPagination
    
    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return NotificationCatalogueUpdateSerializer
        return NotificationCatalogueSerializer
    
    @action(detail=False, methods=['patch'])
    def marquer_tous_comme_lus(self, request):
        """Marquer toutes les notifications non-lues comme lues."""
        updated = NotificationCatalogue.objects.filter(est_lu=False).update(est_lu=True)
        return Response({'updated': updated, 'message': f'{updated} notifications marquées comme lues'})
    
    @action(detail=False, methods=['get'])
    def non_lues(self, request):
        """Retourne uniquement les notifications non-lues."""
        notifications = self.get_queryset().filter(est_lu=False)
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Retourne les statistiques des notifications."""
        total = NotificationCatalogue.objects.count()
        non_lues = NotificationCatalogue.objects.filter(est_lu=False).count()
        par_type = (NotificationCatalogue.objects
                   .values('type_produit')
                   .annotate(count=models.Count('id'))
                   .order_by('type_produit'))
        
        return Response({
            'total': total,
            'non_lues': non_lues,
            'lues': total - non_lues,
            'par_type_produit': list(par_type)
        })



# ============================================================
# MOUVEMENTS DE STOCK (lecture seule – admin uniquement)
# ============================================================
from .serializers import MouvementStockSerializer


class MouvementStockViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule des mouvements de stock.
    Accessible uniquement aux admins (is_staff).
    Les mouvements sont créés automatiquement via les signaux Django
    lors de toute modification d'un champ de stock.
    """
    serializer_class = MouvementStockSerializer
    permission_classes = [IsAdminOrServeuse]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type_produit', 'utilisateur']
    search_fields = ['nom_produit']
    ordering_fields = ['date_ajout', 'quantite_avant', 'quantite_apres', 'quantite_ajoutee']
    ordering = ['-date_ajout']

    def get_queryset(self):
        return MouvementStock.objects.select_related('utilisateur').all()
