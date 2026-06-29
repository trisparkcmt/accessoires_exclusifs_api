from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.conf import settings

from catalogue.models import Parfum, Accessoire, ProduitFiniEssence
from orders.pos_serializers import POSCommandeCreateSerializer
from orders.serializers import CommandeSerializer
from utilisateur.permissions import IsSuperadminOrActiveServeuse


class POSProductSearchView(APIView):
    """
    Endpoint de recherche unifiée de produits pour le POS.
    Accessible uniquement aux serveuses actives et administrateurs.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def get(self, request, *args, **kwargs):
        q = request.query_params.get('q', '').strip()
        product_type = request.query_params.get('type', '').strip().lower()

        results = []

        # 1. Recherche des Parfums (actifs, en stock, prix > 0)
        if not product_type or product_type == 'parfum':
            parfums = Parfum.objects.filter(
                actif=True,
                stock_quantite__gt=0,
                prix_unitaire__gt=0,
            )
            if q:
                parfums = parfums.filter(
                    Q(nom__icontains=q) |
                    Q(marque__icontains=q) |
                    Q(reference_sku__icontains=q)
                )
            for p in parfums[:50]:
                prix = p.prix_promotionnel if p.prix_promotionnel is not None else p.prix_unitaire
                if prix <= 0:
                    continue
                image_url = request.build_absolute_uri(p.image_principale.url) if p.image_principale else None
                results.append({
                    "id": p.id,
                    "type": "parfum",
                    "nom": p.nom,
                    "marque": p.marque,
                    "reference_sku": p.reference_sku or "",
                    "prix": float(prix),
                    "stock_disponible": p.stock_quantite,
                    "image_url": image_url
                })

        # 2. Recherche des Accessoires (actifs, en stock, prix > 0)
        if not product_type or product_type == 'accessoire':
            accessoires = Accessoire.objects.filter(
                actif=True,
                stock_quantite__gt=0,
                prix_unitaire__gt=0,
            )
            if q:
                accessoires = accessoires.filter(
                    Q(nom__icontains=q) |
                    Q(marque__icontains=q) |
                    Q(reference_sku__icontains=q)
                )
            for a in accessoires[:50]:
                prix = a.prix_promotionnel if a.prix_promotionnel is not None else a.prix_unitaire
                if prix <= 0:
                    continue
                image_url = request.build_absolute_uri(a.image_principale.url) if a.image_principale else None
                results.append({
                    "id": a.id,
                    "type": "accessoire",
                    "nom": a.nom,
                    "marque": a.marque,
                    "reference_sku": a.reference_sku or "",
                    "prix": float(prix),
                    "stock_disponible": a.stock_quantite,
                    "image_url": image_url
                })

        # 3. Recherche des Produits Finis Essences (actifs, en stock, prix > 0)
        if not product_type or product_type == 'essence':
            essences = ProduitFiniEssence.objects.filter(
                actif=True,
                stock_disponible__gt=0,
                prix__gt=0,
            ).select_related('essence')
            if q:
                essences = essences.filter(
                    Q(essence__nom__icontains=q) |
                    Q(essence__marque__icontains=q)
                )
            for e in essences[:50]:
                prix = e.prix_promotionnel if e.prix_promotionnel is not None else e.prix
                if prix <= 0:
                    continue
                image_url = request.build_absolute_uri(e.image_principale.url) if e.image_principale else None
                results.append({
                    "id": e.id,
                    "type": "essence",
                    "nom": f"{e.essence.nom_complet} - {e.taille_ml}ml",
                    "marque": e.essence.marque,
                    "reference_sku": f"ESS-{e.essence.id}-{e.taille_ml}",
                    "prix": float(prix),
                    "stock_disponible": e.stock_disponible,
                    "image_url": image_url
                })

        # Trier les résultats par nom
        results.sort(key=lambda x: x['nom'])

        return Response(results, status=status.HTTP_200_OK)


class POSCommandeCreateView(APIView):
    """
    Endpoint de création directe de commande POS (Point de Vente).
    Accessible uniquement aux serveuses actives et administrateurs.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def post(self, request, *args, **kwargs):
        serializer = POSCommandeCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        commande = serializer.save()
        
        # Renvoyer les détails complets de la commande créée via le CommandeSerializer
        # (ce serializer inclut l'objet 'facture' avec l'URL de téléchargement PDF)
        response_serializer = CommandeSerializer(commande, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
