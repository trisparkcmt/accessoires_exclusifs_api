from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.conf import settings

from catalogue.models import Parfum, Accessoire, ProduitFiniEssence, DiffuseurParfum
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
                stock_ml = e.essence.stock_total_ml()
                stock_flacons = int(stock_ml // e.taille_ml) if e.taille_ml > 0 else 0
                if stock_flacons <= 0:
                    continue
                image_url = None
                results.append({
                    "id": e.id,
                    "type": "essence",
                    "nom": f"{e.essence.nom_complet} - {e.taille_ml}ml",
                    "marque": e.essence.marque,
                    "reference_sku": f"ESS-{e.essence.id}-{e.taille_ml}",
                    "prix": float(prix),
                    "stock_disponible": stock_flacons,
                    "image_url": image_url
                })

        # 4. Recherche des Diffuseurs (actifs, en stock, prix > 0)
        if not product_type or product_type == 'diffuseur':
            diffuseurs = DiffuseurParfum.objects.filter(
                actif=True,
                stock_quantite__gt=0,
                prix_unitaire__gt=0,
            )
            if q:
                diffuseurs = diffuseurs.filter(
                    Q(nom__icontains=q) |
                    Q(marque__icontains=q) |
                    Q(reference_sku__icontains=q)
                )
            for d in diffuseurs[:50]:
                prix = d.prix_promotionnel if d.prix_promotionnel is not None else d.prix_unitaire
                if prix <= 0:
                    continue
                image_url = request.build_absolute_uri(d.image_principale.url) if d.image_principale else None
                results.append({
                    "id": d.id,
                    "type": "diffuseur",
                    "nom": d.nom,
                    "marque": d.marque,
                    "reference_sku": d.reference_sku or "",
                    "prix": float(prix),
                    "stock_disponible": d.stock_quantite,
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


class POSRapportJournalierApercuView(APIView):
    """
    Endpoint d'aperçu en direct des activités de la caissière connectée pour aujourd'hui (ou une date donnée).
    Calcule automatiquement :
    - Sorties d'articles (ventes POS avec quantités et montants)
    - Entrées de stock
    - Dépenses enregistrées
    - Recette totale
    Fournit également une prévisualisation du texte formaté pour WhatsApp.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def get(self, request, *args, **kwargs):
        from datetime import datetime
        from django.utils import timezone
        from decimal import Decimal
        from orders.models import RapportJournalierCaisse
        from orders.pos_services import calculer_donnees_journee_caissiere, formater_texte_whatsapp

        date_str = request.query_params.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"detail": "Format de date invalide. Utilisez AAAA-MM-JJ (ex: 2026-11-12)."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            target_date = timezone.now().date()

        # Si admin demande l'aperçu pour une caissière spécifique via ?caissiere_id=...
        target_user = request.user
        caissiere_id = request.query_params.get('caissiere_id')
        if caissiere_id and request.user.is_superuser:
            from django.contrib.auth import get_user_model
            from django.shortcuts import get_object_or_404
            User = get_user_model()
            target_user = get_object_or_404(User, id=caissiere_id)

        donnees = calculer_donnees_journee_caissiere(target_user, target_date=target_date)

        # Créer un objet fictif pour prévisualiser le formatage texte
        fake_rapport = RapportJournalierCaisse(
            caissiere=target_user,
            date=target_date,
            heure_arrivee=request.query_params.get('heure_arrivee', ''),
            heure_depart=request.query_params.get('heure_depart', ''),
            recette_totale=Decimal(str(donnees['recette_totale'])),
            total_depenses=Decimal(str(donnees['total_depenses'])),
            reste_en_caisse=request.query_params.get('reste_en_caisse', ''),
            sorties_articles=donnees['sorties_articles'],
            entrees_stock=donnees['entrees_stock'],
            depenses=donnees['depenses'],
        )
        donnees['texte_apercu'] = formater_texte_whatsapp(fake_rapport)
        donnees['apercu_texte_whatsapp'] = donnees['texte_apercu']
        donnees['caissiere_id'] = target_user.id
        donnees['caissiere_nom'] = target_user.get_full_name() or target_user.email or target_user.username

        return Response(donnees, status=status.HTTP_200_OK)


class POSRapportJournalierClotureView(APIView):
    """
    Endpoint de clôture et sauvegarde du rapport journalier de caisse.
    Calcule les données réelles, applique les saisies manuelles (horaires, reste en caisse, com...),
    génère le PDF, enregistre en base et retourne le rapport ainsi que le texte WhatsApp prêt à copier.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def post(self, request, *args, **kwargs):
        from orders.pos_serializers import (
            POSRapportJournalierClotureSerializer,
            RapportJournalierCaisseSerializer,
        )

        serializer = POSRapportJournalierClotureSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        rapport = serializer.save()

        response_data = RapportJournalierCaisseSerializer(rapport, context={'request': request}).data
        return Response(response_data, status=status.HTTP_201_CREATED)


class POSRapportJournalierListView(APIView):
    """
    Liste de consultation des rapports journaliers de caisse.
    - Serveuse : voit l'historique de ses propres rapports.
    - Administrateur : voit tous les rapports, avec filtres par date ou par caissière.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def get(self, request, *args, **kwargs):
        from orders.models import RapportJournalierCaisse
        from orders.pos_serializers import RapportJournalierCaisseSerializer

        user = request.user
        qs = RapportJournalierCaisse.objects.all().select_related('caissiere')

        if not user.is_superuser:
            qs = qs.filter(caissiere=user)
        else:
            caissiere_id = request.query_params.get('caissiere_id')
            if caissiere_id:
                qs = qs.filter(caissiere_id=caissiere_id)

        date_filter = request.query_params.get('date')
        if date_filter:
            qs = qs.filter(date=date_filter)

        date_debut = request.query_params.get('date_debut')
        if date_debut:
            qs = qs.filter(date__gte=date_debut)

        date_fin = request.query_params.get('date_fin')
        if date_fin:
            qs = qs.filter(date__lte=date_fin)

        serializer = RapportJournalierCaisseSerializer(qs[:100], many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class POSRapportJournalierDetailView(APIView):
    """
    Détail d'un rapport journalier avec option de régénération du PDF via ?regenerer_pdf=true.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def get(self, request, pk, *args, **kwargs):
        from django.shortcuts import get_object_or_404
        from orders.models import RapportJournalierCaisse
        from orders.pos_serializers import RapportJournalierCaisseSerializer
        from orders.pos_services import generer_rapport_caisse_pdf

        user = request.user
        if user.is_superuser:
            rapport = get_object_or_404(RapportJournalierCaisse, pk=pk)
        else:
            rapport = get_object_or_404(RapportJournalierCaisse, pk=pk, caissiere=user)

        regenerer = request.query_params.get('regenerer_pdf') in ('true', '1', 'yes')
        if regenerer or not rapport.fichier_pdf:
            generer_rapport_caisse_pdf(rapport)
            rapport.refresh_from_db()

        serializer = RapportJournalierCaisseSerializer(rapport, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

