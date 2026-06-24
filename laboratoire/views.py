from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import ParfumPersonnalise, EssencePersonnalisee
from .serializers import (
    ParfumPersonnaliseSerializer,
    EssencePersonnaliseeSerializer,
    ParfumLabSerializer,
    EssenceLabSerializer,
    AccessoireLabSerializer,
)
from .permissions import IsCreatorOrReadOnly
from catalogue.pagination import StandardPagination
from catalogue.models import Parfum, Essence, Accessoire, Flacon, Ingredient
from .utils_ia import demander_recommandation_ia


class ParfumPersonnaliseViewSet(viewsets.ModelViewSet):
    serializer_class = ParfumPersonnaliseSerializer
    permission_classes = [IsAuthenticated, IsCreatorOrReadOnly]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'statut',
        'flacon',
        'client__user__email',
        'nom',
        'date_creation',
        'date_modification',
        'prix_total',
    ]
    search_fields = [
        'nom',
        'description',
        'client__user__email',
        'lignes__essence__essence__nom',
        'lignes__essence_personnalisee__nom',
    ]
    ordering_fields = ['prix_total', 'date_creation', 'nom']
    ordering = ['-date_creation']

    def get_queryset(self):
        queryset = ParfumPersonnalise.objects.all().select_related(
            'flacon', 'client', 'client__user'
        ).prefetch_related(
            'lignes__essence__essence',
            'lignes__essence_personnalisee',
            'lignes__essence_personnalisee__lignes',
            'lignes__essence_personnalisee__lignes__ingredient',
        ).distinct()

        if self.request.user.is_staff:
            return queryset

        if hasattr(self.request.user, 'client'):
            if self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
                return queryset.filter(client=self.request.user.client)
            return queryset.filter(client=self.request.user.client, enregistre=True)

        return queryset.none()

    @action(detail=True, methods=['post'], url_path='recalculer')
    def recalculer(self, request, pk=None):
        parfum = self.get_object()
        parfum.recalculer_prix()
        serializer = self.get_serializer(parfum)
        return Response(serializer.data)


class EssencePersonnaliseeViewSet(viewsets.ModelViewSet):
    serializer_class = EssencePersonnaliseeSerializer
    permission_classes = [IsAuthenticated, IsCreatorOrReadOnly]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'nom',
        'client__user__email',
        'date_creation',
        'prix_par_ml_calcule',
    ]
    search_fields = ['nom', 'client__user__email', 'lignes__ingredient__nom']
    ordering_fields = ['prix_par_ml_calcule', 'date_creation', 'nom']
    ordering = ['-date_creation']

    def get_queryset(self):
        queryset = EssencePersonnalisee.objects.all().select_related(
            'client', 'client__user'
        ).prefetch_related('lignes__ingredient').distinct()

        if self.request.user.is_staff:
            return queryset

        if hasattr(self.request.user, 'client'):
            return queryset.filter(client=self.request.user.client)

        return queryset.none()


@api_view(['POST'])
@permission_classes([AllowAny])
def ia_recommandation(request):
    """
    Reçoit un prompt de l'utilisateur, interroge l'IA Gemini et renvoie des produits.
    """
    prompt = request.data.get('prompt')
    if not prompt:
        return Response({"error": "Veuillez fournir un 'prompt'."}, status=status.HTTP_400_BAD_REQUEST)

    reponse_ia = demander_recommandation_ia(prompt)
    if "error" in reponse_ia:
        return Response(reponse_ia, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    ids_parfums = reponse_ia.get('parfums_existants_recommandes', [])
    essences_data = reponse_ia.get('essences_pre_faites', [])
    ingredients_data = reponse_ia.get('ingredients_sur_mesure', [])
    ids_accessoires = reponse_ia.get('accessoires', [])
    flacon_id = reponse_ia.get('flacon_id')
    quantite_demandee_ml = reponse_ia.get('quantite_demandee_ml', 50)

    parfums = Parfum.objects.filter(id__in=ids_parfums, actif=True)
    accessoires = Accessoire.objects.filter(id__in=ids_accessoires, actif=True)
    flacon = None

    if flacon_id:
        try:
            flacon = Flacon.objects.get(id=flacon_id, actif=True)
        except Flacon.DoesNotExist:
            flacon = None

    if not flacon:
        flacon = Flacon.objects.filter(actif=True).order_by('-contenance_ml').first()
        if flacon:
            quantite_demandee_ml = flacon.contenance_ml

    essences_recommandees = []
    essence_ids = [e.get('id') for e in essences_data if isinstance(e, dict)]
    essences_db = {e.id: e for e in Essence.objects.filter(id__in=essence_ids, actif=True, prix_par_ml__gt=0)}
    
    # Précharger les lots d'essence actifs correspondants pour le laboratoire
    from catalogue.models import LotEssence
    lots_db = {}
    for lot in LotEssence.objects.filter(essence_id__in=essence_ids, actif=True, stock_ml__gt=0).select_related('essence'):
        if lot.essence_id not in lots_db:
            lots_db[lot.essence_id] = lot

    for essence_data in essences_data:
        if isinstance(essence_data, dict):
            essence_id = essence_data.get('id')
            quantite_ml = Decimal(str(essence_data.get('quantite_ml', 0)))
            if essence_id in essences_db:
                essence = essences_db[essence_id]
                lot = lots_db.get(essence.id)
                if lot:
                    essences_recommandees.append({
                        'id': essence.id,
                        'lot_essence_id': lot.id,
                        'nom': essence.nom,
                        'code_reference': essence.code_reference,
                        'prix_par_ml': str(essence.prix_par_ml),
                        'quantite_ml': quantite_ml,
                        'prix_total_quantite': str(essence.prix_par_ml * quantite_ml),
                    })

    ingredients_recommandes = []
    ingredient_ids = [i.get('id') for i in ingredients_data if isinstance(i, dict)]
    ingredients_db = {i.id: i for i in Ingredient.objects.filter(id__in=ingredient_ids, actif=True)}
    for ing_data in ingredients_data:
        if isinstance(ing_data, dict):
            ing_id = ing_data.get('id')
            quantite_ml = Decimal(str(ing_data.get('quantite_ml', 0)))
            if ing_id in ingredients_db:
                ingredient = ingredients_db[ing_id]
                ingredients_recommandes.append({
                    'id': ingredient.id,
                    'nom': ingredient.nom,
                    'prix_par_ml': str(ingredient.prix_par_ml),
                    'quantite_ml': quantite_ml,
                    'prix_total_quantite': str(ingredient.prix_par_ml * quantite_ml),
                })

    response_data = {
        'message': reponse_ia.get('message', 'Voici quelques recommandations :'),
        'quantite_demandee_ml': quantite_demandee_ml,
        'flacon': {
            'id': flacon.id,
            'nom': flacon.nom,
            'prix_unitaire': str(flacon.prix_unitaire),
        } if flacon else None,
        'parfums_existants': ParfumLabSerializer(parfums, many=True).data,
        'essences_pre_faites': essences_recommandees,
        'ingredients_sur_mesure': ingredients_recommandes,
        'accessoires': AccessoireLabSerializer(accessoires, many=True).data,
    }

    return Response(response_data)
