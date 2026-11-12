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
    Supporte GET et POST (avec payload JSON).
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def _build_apercu(self, request, params):
        from datetime import datetime
        from django.utils import timezone
        from decimal import Decimal
        from orders.models import RapportJournalierCaisse
        from orders.pos_services import calculer_donnees_journee_caissiere, formater_texte_whatsapp

        date_str = params.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(str(date_str).strip(), '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"detail": "Format de date invalide. Utilisez AAAA-MM-JJ (ex: 2026-11-12)."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            target_date = timezone.now().date()

        # Si admin demande l'aperçu pour une caissière spécifique via ?caissiere_id=...
        target_user = request.user
        caissiere_id = params.get('caissiere_id')
        if caissiere_id and request.user.is_superuser:
            from django.contrib.auth import get_user_model
            from django.shortcuts import get_object_or_404
            User = get_user_model()
            target_user = get_object_or_404(User, id=caissiere_id)

        donnees = calculer_donnees_journee_caissiere(target_user, target_date=target_date)

        # Vérifier si un rapport existe déjà en base pour initialiser les valeurs saisies
        rapport_existant = RapportJournalierCaisse.objects.filter(
            caissiere=target_user,
            date=target_date
        ).first()

        # Récupération souple avec gestion des alias
        def _get_val(keys, default=''):
            for k in keys:
                if params.get(k) is not None and str(params.get(k)).strip() != '':
                    return str(params.get(k)).strip()
            return default

        heure_arrivee = _get_val(['heure_arrivee'], rapport_existant.heure_arrivee if rapport_existant else '')
        heure_depart = _get_val(['heure_depart'], rapport_existant.heure_depart if rapport_existant else '')
        reste_en_caisse = _get_val(['reste_en_caisse', 'reste_caisse', 'reste', 'fond_de_caisse', 'fond_caisse'], rapport_existant.reste_en_caisse if rapport_existant else '')
        actions_communication = _get_val(['actions_communication', 'communication_digitale', 'communication', 'actions_communication_digitale'], rapport_existant.actions_communication if rapport_existant else '')
        observations = _get_val(['observations', 'observation', 'notes', 'remarques'], rapport_existant.observations if rapport_existant else '')
        autres_donnees = params.get('autres_donnees_manuelles') or (rapport_existant.autres_donnees_manuelles if rapport_existant else {})

        # Créer un objet fictif pour prévisualiser le formatage texte
        fake_rapport = RapportJournalierCaisse(
            caissiere=target_user,
            date=target_date,
            heure_arrivee=heure_arrivee,
            heure_depart=heure_depart,
            recette_totale=Decimal(str(donnees['recette_totale'])),
            total_depenses=Decimal(str(donnees['total_depenses'])),
            reste_en_caisse=reste_en_caisse,
            sorties_articles=donnees['sorties_articles'],
            entrees_stock=donnees['entrees_stock'],
            depenses=donnees['depenses'],
            actions_communication=actions_communication,
            observations=observations,
            autres_donnees_manuelles=autres_donnees if isinstance(autres_donnees, dict) else {},
        )

        texte_formate = formater_texte_whatsapp(fake_rapport)
        donnees['heure_arrivee'] = heure_arrivee
        donnees['heure_depart'] = heure_depart
        donnees['reste_en_caisse'] = reste_en_caisse
        donnees['reste_caisse'] = reste_en_caisse
        donnees['actions_communication'] = actions_communication
        donnees['communication_digitale'] = actions_communication
        donnees['observations'] = observations
        donnees['autres_donnees_manuelles'] = fake_rapport.autres_donnees_manuelles
        donnees['texte_apercu'] = texte_formate
        donnees['apercu_texte_whatsapp'] = texte_formate
        donnees['caissiere_id'] = target_user.id
        donnees['caissiere_nom'] = target_user.get_full_name() or target_user.email or target_user.username
        if rapport_existant and rapport_existant.fichier_pdf and hasattr(rapport_existant.fichier_pdf, 'url'):
            donnees['pdf_url'] = request.build_absolute_uri(rapport_existant.fichier_pdf.url)
        else:
            donnees['pdf_url'] = None

        return Response(donnees, status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        return self._build_apercu(request, request.query_params)

    def post(self, request, *args, **kwargs):
        # Permet aussi de prévisualiser l'aperçu via POST avec payload
        payload = dict(request.query_params)
        if isinstance(request.data, dict):
            payload.update(request.data)
        return self._build_apercu(request, payload)


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
    Détail d'un rapport journalier avec option de régénération du PDF via ?regenerer_pdf=true ou recalcul des données.
    Supporte GET, PATCH, PUT et POST pour mettre à jour et régénérer le PDF en direct.
    """
    permission_classes = [IsSuperadminOrActiveServeuse]

    def _update_and_regenerate(self, request, rapport, params=None):
        from decimal import Decimal
        from orders.pos_services import (
            calculer_donnees_journee_caissiere,
            formater_texte_whatsapp,
            generer_rapport_caisse_pdf,
        )

        params = params or {}

        # 1. Recalculer les activités de la journée pour rafraîchir ventes, entrées, dépenses
        donnees = calculer_donnees_journee_caissiere(rapport.caissiere, target_date=rapport.date)
        rapport.recette_totale = Decimal(str(donnees['recette_totale']))
        rapport.sorties_articles = donnees['sorties_articles']

        # Entrées de stock
        if donnees.get('entrees_stock'):
            rapport.entrees_stock = donnees['entrees_stock']

        # Dépenses
        if donnees.get('depenses'):
            rapport.depenses = donnees['depenses']
            rapport.total_depenses = Decimal(str(donnees['total_depenses']))

        # 2. Récupérer les paramètres passés (query_params ou body) pour écraser/mettre à jour les champs
        def _get_val(keys):
            for k in keys:
                val = params.get(k)
                if val is not None and str(val).strip() != '':
                    return str(val).strip()
            return None

        new_reste = _get_val(['reste_en_caisse', 'reste_caisse', 'reste', 'fond_de_caisse', 'fond_caisse'])
        if new_reste is not None:
            rapport.reste_en_caisse = new_reste

        new_com = _get_val(['actions_communication', 'communication_digitale', 'communication', 'actions_communication_digitale'])
        if new_com is not None:
            rapport.actions_communication = new_com

        new_obs = _get_val(['observations', 'observation', 'notes', 'remarques'])
        if new_obs is not None:
            rapport.observations = new_obs

        new_arr = _get_val(['heure_arrivee'])
        if new_arr is not None:
            rapport.heure_arrivee = new_arr

        new_dep = _get_val(['heure_depart'])
        if new_dep is not None:
            rapport.heure_depart = new_dep

        # Ajout éventuel de dépenses manuelles
        dep_manuelles = params.get('depenses') or params.get('depenses_ajouts')
        if dep_manuelles and isinstance(dep_manuelles, list):
            current_dep = list(rapport.depenses)
            for item in dep_manuelles:
                if item.get('titre') or item.get('montant'):
                    current_dep.append({
                        'id': item.get('id'),
                        'titre': str(item.get('titre', 'Dépense')),
                        'montant': float(item.get('montant', 0.0)),
                        'description': str(item.get('description', '')),
                    })
            rapport.depenses = current_dep
            rapport.total_depenses = sum((Decimal(str(d.get('montant', 0))) for d in current_dep), Decimal('0.00'))

        # 3. Mettre à jour le texte WhatsApp
        rapport.texte_formate = formater_texte_whatsapp(rapport)
        rapport.save()

        # 4. Régénérer le PDF
        generer_rapport_caisse_pdf(rapport)
        rapport.refresh_from_db()
        return rapport

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

        regenerer = (
            request.query_params.get('regenerer_pdf') in ('true', '1', 'yes')
            or request.query_params.get('recalculer') in ('true', '1', 'yes')
        )

        # Si l'utilisateur demande une régénération ou si des paramètres sont fournis dans l'URL
        has_override_params = any(
            request.query_params.get(k) for k in [
                'reste_en_caisse', 'reste_caisse', 'reste',
                'actions_communication', 'communication_digitale', 'communication',
                'heure_arrivee', 'heure_depart', 'observations'
            ]
        )

        if regenerer or has_override_params:
            self._update_and_regenerate(request, rapport, params=request.query_params)
        elif not rapport.fichier_pdf:
            generer_rapport_caisse_pdf(rapport)
            rapport.refresh_from_db()

        serializer = RapportJournalierCaisseSerializer(rapport, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk, *args, **kwargs):
        from django.shortcuts import get_object_or_404
        from orders.models import RapportJournalierCaisse
        from orders.pos_serializers import RapportJournalierCaisseSerializer

        user = request.user
        if user.is_superuser:
            rapport = get_object_or_404(RapportJournalierCaisse, pk=pk)
        else:
            rapport = get_object_or_404(RapportJournalierCaisse, pk=pk, caissiere=user)

        payload = dict(request.query_params)
        if isinstance(request.data, dict):
            payload.update(request.data)

        self._update_and_regenerate(request, rapport, params=payload)
        serializer = RapportJournalierCaisseSerializer(rapport, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        return self.patch(request, pk, *args, **kwargs)

    def post(self, request, pk, *args, **kwargs):
        return self.patch(request, pk, *args, **kwargs)

