from datetime import timezone

from django.shortcuts import render, get_object_or_404
from django.http import FileResponse
import random
import string
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db import transaction


from orders.models import (
    Panier, 
    PanierLigneParfum, 
    PanierLigneAccessoire, 
    PanierLigneParfumPerso, 
    PanierLigneProduitFiniEssence, 
    PanierLigneEssencePersonnalisee,
    Commande,
    Facture,
    CodePromoAdmin
)
from laboratoire.models import ParfumPersonnalise
from orders.utils import get_or_create_panier
from orders.serializers import (
    AjouterParfumSerializer,
    AjouterAccessoireSerializer,
    AjouterProduitFiniEssenceSerializer,
    AjouterEssencePersonnaliseeSerializer,
    AjouterParfumPersoLabSerializer,
    PanierSerializer,
    AppliquerCodePromoSerializer,
    CommandeSerializer,
    PasserCommandeSerializer,
    FactureSerializer,
    AdminFactureSerializer,
    CodePromoAdminSerializer,
    CommanderCompositionDirecteSerializer,
    PasserCommandeCompositionDirecteSerializer
)
from utilisateur.permissions import CommandePermission, is_active_serveuse
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission


def generate_cmd_code(length=4):
    """Génère un code promo unique de type ACC-XXXXXX"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(chars) for _ in range(length))
    return f"CMD-{code}"


class PanierDetailView(APIView):
    """
    Récupère le panier actif courant (session ou utilisateur connecté).
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        panier_id = request.query_params.get('panier_id')
        panier = get_or_create_panier(request, panier_id)
        # Recalculate totals to ensure promo codes are applied correctly
        panier.recalculer_total()
        return Response(PanierSerializer(panier, context={'request': request}).data)


class AjouterParfumView(APIView):
    """
    Ajoute un parfum au panier actif.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AjouterParfumSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        panier_id = serializer.validated_data.get('panier_id')
        parfum = serializer.validated_data['parfum_obj']
        quantite = serializer.validated_data['quantite']
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            
            ligne, created = PanierLigneParfum.objects.get_or_create(
                panier=panier,
                parfum=parfum,
                defaults={
                    'prix_unitaire_snapshot': parfum.prix_actuel,
                    'quantite': quantite,
                    'sous_total': parfum.prix_actuel * quantite
                }
            )
            
            if not created:
                total_quantite = ligne.quantite + quantite
                if parfum.stock_quantite < total_quantite:
                    return Response(
                        {"quantite": f"Stock insuffisant. Seulement {parfum.stock_quantite} disponibles (vous en avez déjà {ligne.quantite} dans le panier)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ligne.quantite = total_quantite
                ligne.prix_unitaire_snapshot = parfum.prix_actuel
                ligne.save()
            
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class AjouterAccessoireView(APIView):
    """
    Ajoute un accessoire au panier actif.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AjouterAccessoireSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        panier_id = serializer.validated_data.get('panier_id')
        accessoire = serializer.validated_data['accessoire_obj']
        quantite = serializer.validated_data['quantite']
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            
            ligne, created = PanierLigneAccessoire.objects.get_or_create(
                panier=panier,
                accessoire=accessoire,
                defaults={
                    'prix_unitaire_snapshot': accessoire.prix_actuel,
                    'quantite': quantite,
                    'sous_total': accessoire.prix_actuel * quantite
                }
            )
            
            if not created:
                total_quantite = ligne.quantite + quantite
                if accessoire.stock_quantite < total_quantite:
                    return Response(
                        {"quantite": f"Stock insuffisant. Seulement {accessoire.stock_quantite} disponibles (vous en avez déjà {ligne.quantite} dans le panier)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ligne.quantite = total_quantite
                ligne.prix_unitaire_snapshot = accessoire.prix_actuel
                ligne.save()
            
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class AjouterProduitFiniEssenceView(APIView):
    """
    Ajoute un produit fini essence (essence en flacon) au panier actif.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AjouterProduitFiniEssenceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        panier_id = serializer.validated_data.get('panier_id')
        produit = serializer.validated_data['produit_fini_essence_obj']
        quantite = serializer.validated_data['quantite']
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            
            ligne, created = PanierLigneProduitFiniEssence.objects.get_or_create(
                panier=panier,
                produit_fini_essence=produit,
                defaults={
                    'prix_unitaire_snapshot': produit.prix_actuel,
                    'quantite': quantite,
                    'sous_total': produit.prix_actuel * quantite
                }
            )
            
            if not created:
                total_quantite = ligne.quantite + quantite
                quantite_ml = Decimal(str(total_quantite)) * Decimal(str(produit.taille_ml))
                if produit.essence.stock_total_ml() < quantite_ml:
                    return Response(
                        {"quantite": f"Stock d'essence insuffisant pour {produit.essence.nom}. (vous en avez déjà {ligne.quantite} dans le panier)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ligne.quantite = total_quantite
                ligne.prix_unitaire_snapshot = produit.prix_actuel
                ligne.save()
            
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class CommanderCompositionDirecteView(APIView):
    """
    Crée un parfum personnalisé et l'ajoute directement au panier (LIA & Borne boutique).
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = CommanderCompositionDirecteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        parfum_perso = serializer.save()
        
        panier_id = serializer.validated_data.get('panier_id')
        quantite = serializer.validated_data.get('quantite', 1)
        note_client = serializer.validated_data.get('note_client', '')
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            
            ligne, created = PanierLigneParfumPerso.objects.get_or_create(
                panier=panier,
                parfum_personnalise=parfum_perso,
                defaults={
                    'prix_calcule': parfum_perso.prix_total,
                    'quantite': quantite,
                    'sous_total': parfum_perso.prix_total * quantite,
                    'couleur': parfum_perso.couleur,
                    'nom_sur_flacon': parfum_perso.nom_sur_flacon,
                    'note_client': note_client
                }
            )
            
            if not created:
                ligne.quantite += quantite
                ligne.prix_calcule = parfum_perso.prix_total
                if parfum_perso.couleur:
                    ligne.couleur = parfum_perso.couleur
                if parfum_perso.nom_sur_flacon:
                    ligne.nom_sur_flacon = parfum_perso.nom_sur_flacon
                if note_client:
                    ligne.note_client = note_client
                ligne.save()
            
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class AjouterParfumPersoLabView(APIView):
    """
    Ajoute au panier un parfum personnalisé déjà enregistré dans le labo du client.
    ✔ Requiert d'être connecté (le parfum doit appartenir au client).
    ✔ Le parfum doit avoir enregistre=True (créé via POST /labo/compositions/).

    Payload :
        parfum_personnalise_id  (int, requis)   - ID du ParfumPersonnalise
        quantite                (int, défaut 1) - Nombre d'exemplaires
        panier_id               (int, optionnel) - ID du panier cible
        couleur                 (str, optionnel) - Couleur personnalisée
        nom_sur_flacon          (str, optionnel) - Texte personnalisé sur le flacon
        note_client             (str, optionnel) - Note associée à la ligne
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AjouterParfumPersoLabSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        parfum_perso = serializer.validated_data['parfum_perso_obj']
        quantite = serializer.validated_data.get('quantite', 1)
        note_client = serializer.validated_data.get('note_client', '')
        panier_id = serializer.validated_data.get('panier_id')
        couleur = serializer.validated_data.get('couleur') or parfum_perso.couleur
        nom_sur_flacon = serializer.validated_data.get('nom_sur_flacon') or parfum_perso.nom_sur_flacon

        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)

            ligne, created = PanierLigneParfumPerso.objects.get_or_create(
                panier=panier,
                parfum_personnalise=parfum_perso,
                defaults={
                    'prix_calcule': parfum_perso.prix_total,
                    'quantite': quantite,
                    'sous_total': parfum_perso.prix_total * quantite,
                    'couleur': couleur,
                    'nom_sur_flacon': nom_sur_flacon,
                    'note_client': note_client
                }
            )

            if not created:
                ligne.quantite += quantite
                ligne.prix_calcule = parfum_perso.prix_total
                ligne.sous_total = ligne.prix_calcule * ligne.quantite
                if couleur:
                    ligne.couleur = couleur
                if nom_sur_flacon:
                    ligne.nom_sur_flacon = nom_sur_flacon
                if note_client:
                    ligne.note_client = note_client
                ligne.save()

            panier.recalculer_total()

        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)



class AjouterEssencePersonnaliseeView(APIView):
    """
    Ajoute une essence personnalisée au panier actif (requiert d'être connecté).
    """
    permission_classes = [AllowAny]


    def post(self, request, *args, **kwargs):
        serializer = AjouterEssencePersonnaliseeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        panier_id = serializer.validated_data.get('panier_id')
        essence_perso = serializer.validated_data['essence_perso_obj']
        quantite = serializer.validated_data['quantite']
        total_prix = serializer.validated_data['total_prix']
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            
            ligne, created = PanierLigneEssencePersonnalisee.objects.get_or_create(
                panier=panier,
                essence_personnalisee=essence_perso,
                defaults={
                    'prix_calcule': total_prix,
                    'quantite': quantite,
                    'sous_total': total_prix * quantite
                }
            )
            
            if not created:
                ligne.quantite += quantite
                ligne.prix_calcule = total_prix
                ligne.save()
            
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class PanierLigneDetailView(APIView):
    """s
    Modifie la quantité ou supprime une ligne de panier spécifique.
    Le paramètre type_ligne doit être l'un des suivants :
    - 'parfum'
    - 'accessoire'
    - 'produit-fini-essence'
    - 'parfum-personnalise'
    - 'essence-personnalisee'
    """
    permission_classes = [AllowAny]
    
    def get_model_and_line(self, type_ligne, ligne_id, panier):
        if type_ligne == 'parfum':
            return PanierLigneParfum, PanierLigneParfum.objects.filter(id=ligne_id, panier=panier).first()
        elif type_ligne == 'accessoire':
            return PanierLigneAccessoire, PanierLigneAccessoire.objects.filter(id=ligne_id, panier=panier).first()
        elif type_ligne == 'produit-fini-essence':
            return PanierLigneProduitFiniEssence, PanierLigneProduitFiniEssence.objects.filter(id=ligne_id, panier=panier).first()
        elif type_ligne == 'parfum-personnalise':
            return PanierLigneParfumPerso, PanierLigneParfumPerso.objects.filter(id=ligne_id, panier=panier).first()
        elif type_ligne == 'essence-personnalisee':
            return PanierLigneEssencePersonnalisee, PanierLigneEssencePersonnalisee.objects.filter(id=ligne_id, panier=panier).first()
        elif type_ligne == 'diffuseur-parfum':
            from .models import PanierLigneDiffuseurParfum
            return PanierLigneDiffuseurParfum, PanierLigneDiffuseurParfum.objects.filter(id=ligne_id, panier=panier).first()
        return None, None

    def patch(self, request, type_ligne, ligne_id, *args, **kwargs):
        panier_id = request.data.get('panier_id') or request.query_params.get('panier_id')
        panier = get_or_create_panier(request, panier_id)
        
        model_cls, ligne = self.get_model_and_line(type_ligne, ligne_id, panier)
        if not ligne:
            return Response({"detail": f"Ligne de panier '{type_ligne}' avec ID {ligne_id} introuvable dans ce panier."}, status=status.HTTP_404_NOT_FOUND)
            
        quantite = request.data.get('quantite')
        if quantite is None:
            return Response({"quantite": "Ce champ est requis."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            quantite = int(quantite)
            if quantite < 1:
                raise ValueError()
        except ValueError:
            return Response({"quantite": "La quantité doit être un entier supérieur ou égal à 1."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Validation des stocks pour les produits du catalogue
        if type_ligne == 'parfum':
            if ligne.parfum.stock_quantite < quantite:
                return Response({"quantite": f"Stock insuffisant. Seulement {ligne.parfum.stock_quantite} disponibles."}, status=status.HTTP_400_BAD_REQUEST)
        elif type_ligne == 'accessoire':
            if ligne.accessoire.stock_quantite < quantite:
                return Response({"quantite": f"Stock insuffisant. Seulement {ligne.accessoire.stock_quantite} disponibles."}, status=status.HTTP_400_BAD_REQUEST)
        elif type_ligne == 'produit-fini-essence':
            quantite_ml = Decimal(str(quantite)) * Decimal(str(ligne.produit_fini_essence.taille_ml))
            if ligne.produit_fini_essence.essence.stock_total_ml() < quantite_ml:
                return Response({"quantite": f"Stock d'essence insuffisant pour {ligne.produit_fini_essence.essence.nom}."}, status=status.HTTP_400_BAD_REQUEST)
        elif type_ligne == 'diffuseur-parfum':
            if ligne.diffuseur.stock_quantite < quantite:
                return Response({"quantite": f"Stock insuffisant. Seulement {ligne.diffuseur.stock_quantite} disponibles."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            ligne.quantite = quantite
            ligne.save()
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)

    def delete(self, request, type_ligne, ligne_id, *args, **kwargs):
        panier_id = request.data.get('panier_id') or request.query_params.get('panier_id')
        panier = get_or_create_panier(request, panier_id)
        
        model_cls, ligne = self.get_model_and_line(type_ligne, ligne_id, panier)
        if not ligne:
            return Response({"detail": f"Ligne de panier '{type_ligne}' avec ID {ligne_id} introuvable dans ce panier."}, status=status.HTTP_404_NOT_FOUND)
            
        with transaction.atomic():
            ligne.delete()
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class AppliquerCodePromoView(APIView):
    """
    Applique un code promo au panier.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AppliquerCodePromoSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        panier_id = serializer.validated_data.get('panier_id')
        prestataire = serializer.validated_data.get('prestataire_obj')
        promo_admin = serializer.validated_data.get('promo_admin_obj')
        code_promo = serializer.validated_data['code_promo'].strip()
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            panier.code_promo_applique = code_promo
            if prestataire:
                panier.prestataire = prestataire
                panier.remise_pourcentage = prestataire.reduction_client_pourcentage
            elif promo_admin:
                panier.prestataire = None
                panier.remise_pourcentage = promo_admin.reduction_pourcentage
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class RetirerCodePromoView(APIView):
    """
    Retire le code promo appliqué au panier.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        panier_id = request.data.get('panier_id') or request.query_params.get('panier_id')
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            panier.code_promo_applique = ""
            panier.prestataire = None
            panier.remise_pourcentage = 0
            panier.remise_montant = 0
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class CommandePagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class CommandeListView(APIView):
    permission_classes = [IsAuthenticated, CommandePermission]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        from utilisateur.permissions import is_active_serveuse, is_active_livreur, is_active_client
        if user.is_superuser or is_active_serveuse(user):
            commandes = Commande.objects.all().order_by('-date_creation')
        elif is_active_livreur(user):
            client = getattr(user, 'client', None)
            livreur = getattr(client, 'livreur', None) if client else None
            if livreur:
                commandes = Commande.objects.filter(livreur=livreur).order_by('-date_creation')
            else:
                commandes = Commande.objects.none()
        elif is_active_client(user):
            client = getattr(user, 'client', None)
            if client:
                commandes = Commande.objects.filter(client=client).order_by('-date_creation')
            else:
                commandes = Commande.objects.none()
        else:
            commandes = Commande.objects.none()
            
        # Filtres par statuts
        statut = request.query_params.get('statut')
        if statut:
            commandes = commandes.filter(statut=statut)
            
        statut_paiement = request.query_params.get('statut_paiement')
        if statut_paiement:
            commandes = commandes.filter(statut_paiement=statut_paiement)
            
        statut_livraison = request.query_params.get('statut_livraison')
        if statut_livraison:
            commandes = commandes.filter(statut_livraison=statut_livraison)
            
        # Filtre par nom du client (ou nom complet de livraison)
        nom = request.query_params.get('nom')
        if nom:
            from django.db.models import Q
            commandes = commandes.filter(
                Q(client__user__first_name__icontains=nom) |
                Q(client__user__last_name__icontains=nom) |
                Q(livraison_nom_complet__icontains=nom)
            )
            
        # Recherche générale (numéro de commande, e-mail, téléphone)
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            commandes = commandes.filter(
                Q(numero_commande__icontains=search) |
                Q(client__user__email__icontains=search) |
                Q(client__user__telephone__icontains=search) |
                Q(livraison_telephone__icontains=search)
            )
            
        # Pagination
        paginator = CommandePagination()
        page = paginator.paginate_queryset(commandes, request, view=self)
        if page is not None:
            serializer = CommandeSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
            
        serializer = CommandeSerializer(commandes, many=True, context={'request': request})
        return Response(serializer.data)



class CommandeDetailView(APIView):
    permission_classes = [IsAuthenticated, CommandePermission]

    def get(self, request, numero, *args, **kwargs):
        commande = get_object_or_404(Commande, numero_commande=numero)
        self.check_object_permissions(request, commande)
        return Response(CommandeSerializer(commande, context={'request': request}).data)

    def patch(self, request, numero, *args, **kwargs):
        commande = get_object_or_404(Commande, numero_commande=numero)
        self.check_object_permissions(request, commande)

        user = request.user
        data = request.data

        from utilisateur.permissions import is_active_serveuse, is_active_livreur
        is_admin_or_serv = user.is_superuser or is_active_serveuse(user)
        is_liv = is_active_livreur(user)
        is_client_owner = hasattr(user, 'client') and commande.client == user.client

        if is_admin_or_serv:
            # 1. Commande annulée ou remboursée -> Figée
            if commande.statut == 'annulée':
                return Response(
                    {"detail": "Cette commande est annulée. Aucune modification de statut n'est possible sur une commande annulée."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if commande.statut == 'remboursée':
                return Response(
                    {"detail": "Cette commande est remboursée. Elle est définitivement figée et ne peut plus être modifiée."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Rejet de la tentative de retour à 'en_attente'
            nouveau_statut = data.get('statut')
            if nouveau_statut == 'en_attente' and commande.statut != 'en_attente':
                return Response(
                    {"detail": "Dès qu'une commande quitte le statut 'en attente', elle ne peut plus y revenir."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 3. Validation des champs de statut secondaires (livraison, paiement, commission)
            CHAMPS_PROTEGES = {'statut_livraison', 'statut_paiement', 'commission_statut'}
            champs_proteges_demandes = CHAMPS_PROTEGES.intersection(data.keys())

            target_statut = nouveau_statut or commande.statut
            if champs_proteges_demandes and target_statut != 'validé':
                if commande.statut == 'en_attente':
                    return Response(
                        {"detail": "Veuillez d'abord mettre la commande au statut 'validé' avant tout autre opération."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {"detail": "Les statuts de livraison, paiement et commission ne peuvent être modifiés que lorsque la commande est au statut 'validé'."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # 4. Passage au statut 'remboursée' : uniquement si statut_paiement == 'payé'
            if nouveau_statut == 'remboursée':
                statut_paiement_apres = data.get('statut_paiement', commande.statut_paiement)
                if statut_paiement_apres != 'payé':
                    return Response(
                        {"detail": "Une commande ne peut être mise au statut 'remboursée' que si son statut de paiement est 'payé'."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Application des modifications autorisées
            allowed_fields = {
                'statut', 'statut_livraison', 'livreur', 'date_livraison_estimee',
                'note_interne', 'motif_echec_livraison', 'frais_livraison',
                'statut_paiement', 'commission_statut'
            }
            update_data = {k: v for k, v in data.items() if k in allowed_fields}

            if 'livreur' in update_data:
                if update_data['livreur'] is not None:
                    from utilisateur.models import Livreur
                    try:
                        livreur_obj = Livreur.objects.get(id=update_data['livreur'])
                        update_data['livreur'] = livreur_obj
                    except (Livreur.DoesNotExist, ValueError):
                        return Response({"livreur": "Livreur introuvable."}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    update_data['livreur'] = None

            for k, v in update_data.items():
                setattr(commande, k, v)

            commande.save()
            return Response(CommandeSerializer(commande, context={'request': request}).data, status=status.HTTP_200_OK)

        elif is_liv:
            statut_paiement = data.get('statut_paiement')
            statut_livraison = data.get('statut_livraison')
            motif_echec = data.get('motif_echec_livraison')

            action = data.get('action')
            motif = data.get('motif')
            if action == 'livrer':
                statut_paiement = 'payé'
                statut_livraison = 'livrée'
            elif action == 'echouer':
                statut_paiement = 'échoué'
                statut_livraison = 'échouée'
                motif_echec = motif

            if commande.statut != 'validé':
                return Response(
                    {"detail": "Vous ne pouvez mettre à jour la livraison que sur une commande au statut 'validé'."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            updated = False
            if statut_paiement is not None:
                if statut_paiement not in ['payé', 'échoué']:
                    return Response({"statut_paiement": "Le livreur peut uniquement définir le paiement sur 'payé' ou 'échoué'."}, status=status.HTTP_400_BAD_REQUEST)
                commande.statut_paiement = statut_paiement
                updated = True

            if statut_livraison is not None:
                if statut_livraison not in ['livrée', 'échouée']:
                    return Response({"statut_livraison": "Le livreur peut uniquement définir la livraison sur 'livrée' ou 'échouée'."}, status=status.HTTP_400_BAD_REQUEST)
                commande.statut_livraison = statut_livraison
                updated = True

                if statut_livraison == 'livrée':
                    commande.statut_paiement = 'payé'
                    commande.statut = 'validé'
                    commande.date_livraison_reelle = timezone.now()
                elif statut_livraison == 'échouée':
                    commande.statut_paiement = 'échoué'

            if motif_echec is not None:
                commande.motif_echec_livraison = motif_echec
                updated = True

            if not updated:
                return Response({"detail": "Aucune modification autorisée pour votre rôle n'a été transmise."}, status=status.HTTP_400_BAD_REQUEST)

            from orders.models import AffectationLivraison
            aff = AffectationLivraison.objects.filter(commande=commande, livreur=user.client.livreur).last()
            if aff:
                if statut_livraison == 'livrée':
                    aff.statut = 'livrée'
                    aff.date_livraison_reelle = commande.date_livraison_reelle
                elif statut_livraison == 'échouée':
                    aff.statut = 'échouée'
                    if motif_echec:
                        aff.motif_echec = motif_echec
                aff.save()

            commande.save()
            return Response(CommandeSerializer(commande, context={'request': request}).data, status=status.HTTP_200_OK)

        elif is_client_owner:
            # Annulation par le client propriétaire
            action = data.get('action')
            nouveau_statut = data.get('statut')
            if nouveau_statut == 'annulée' or action == 'annuler':
                if commande.statut != 'en_attente':
                    return Response(
                        {"detail": "Vous ne pouvez annuler la commande que lorsqu'elle est au statut 'en attente'. Dès qu'elle est validée, annulée ou remboursée, vous ne pouvez plus l'annuler."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                commande.statut = 'annulée'
                commande.save()
                return Response(CommandeSerializer(commande, context={'request': request}).data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"detail": "En tant que client, la seule modification autorisée est l'annulation de votre commande en attente."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response({"detail": "Vous n'avez pas la permission de modifier cette commande."}, status=status.HTTP_403_FORBIDDEN)

    def delete(self, request, numero, *args, **kwargs):
        """
        Permet d'annuler une commande (met son statut à 'annulée' au lieu de supprimer le record).
        Client : autorisé uniquement si la commande est au statut 'en_attente'.
        Admin/Serveuse : autorisé si la commande n'est pas déjà 'annulée' ou 'remboursée'.
        """
        commande = get_object_or_404(Commande, numero_commande=numero)
        self.check_object_permissions(request, commande)

        user = request.user
        from utilisateur.permissions import is_active_serveuse
        is_admin_or_serv = user.is_superuser or is_active_serveuse(user)

        if is_admin_or_serv:
            if commande.statut in ('annulée', 'remboursée'):
                return Response(
                    {"detail": f"Cette commande est déjà au statut '{commande.statut}' et ne peut plus être annulée."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            commande.statut = 'annulée'
            commande.save()
            return Response(
                {"detail": f"Commande {numero} annulée avec succès.", "statut": commande.statut},
                status=status.HTTP_200_OK
            )

        client = getattr(user, 'client', None)
        if not client or commande.client != client:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à annuler cette commande."},
                status=status.HTTP_403_FORBIDDEN
            )

        if commande.statut != 'en_attente':
            return Response(
                {"detail": "Vous ne pouvez annuler la commande que lorsqu'elle est au statut 'en attente'. Dès qu'elle est validée, annulée ou remboursée, vous ne pouvez plus l'annuler."},
                status=status.HTTP_400_BAD_REQUEST
            )

        commande.statut = 'annulée'
        commande.save()
        return Response(
            {"detail": f"Votre commande {numero} a été annulée avec succès.", "statut": commande.statut},
            status=status.HTTP_200_OK
        )


class CommandeAnnulerView(APIView):
    """
    Endpoint POST /api/v1/orders/commandes/<numero>/annuler/
    Permet à un client d'annuler sa propre commande (si elle est 'en_attente').
    Permet aussi à l'admin/serveuse d'annuler une commande.
    """
    permission_classes = [IsAuthenticated, CommandePermission]

    def post(self, request, numero, *args, **kwargs):
        commande = get_object_or_404(Commande, numero_commande=numero)
        self.check_object_permissions(request, commande)

        user = request.user
        from utilisateur.permissions import is_active_serveuse
        is_admin_or_serv = user.is_superuser or is_active_serveuse(user)

        if is_admin_or_serv:
            if commande.statut in ('annulée', 'remboursée'):
                return Response(
                    {"detail": f"Cette commande est déjà au statut '{commande.statut}' et ne peut plus être annulée."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            commande.statut = 'annulée'
            commande.save()
            return Response(
                {"detail": f"Commande {numero} annulée avec succès.", "statut": commande.statut},
                status=status.HTTP_200_OK
            )

        client = getattr(user, 'client', None)
        if not client or commande.client != client:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à annuler cette commande."},
                status=status.HTTP_403_FORBIDDEN
            )

        if commande.statut != 'en_attente':
            return Response(
                {"detail": "Vous ne pouvez annuler la commande que lorsqu'elle est au statut 'en attente'. Dès qu'elle est validée, annulée ou remboursée, vous ne pouvez plus l'annuler."},
                status=status.HTTP_400_BAD_REQUEST
            )

        commande.statut = 'annulée'
        commande.save()
        return Response(
            {"detail": f"Votre commande {numero} a été annulée avec succès.", "statut": commande.statut},
            status=status.HTTP_200_OK
        )


class PasserCommandeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasserCommandeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        commande = serializer.save()
        return Response(CommandeSerializer(commande, context={'request': request}).data, status=status.HTTP_201_CREATED)


class PasserCommandeCompositionDirecteView(APIView):
    """
    Crée une composition personnalisée sur-mesure et passe la commande immédiatement
    sans affecter ni utiliser le panier d'achat actif de l'utilisateur.
    Tous les champs d'identification/livraison/nom sont facultatifs.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasserCommandeCompositionDirecteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        commande = serializer.save()
        return Response(CommandeSerializer(commande, context={'request': request}).data, status=status.HTTP_201_CREATED)



class FactureDownloadView(APIView):
    """
    Télécharger le PDF d'une facture.
    Accessible par :
    - Le client propriétaire de la commande.
    - L'administrateur (staff / superuser).
    - La serveuse active.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, numero, *args, **kwargs):
        commande = get_object_or_404(Commande, numero_commande=numero)
        
        # Vérifier si la facture existe
        if not hasattr(commande, 'facture') or not commande.facture:
            return Response(
                {"detail": "Aucune facture disponible pour cette commande. Elle n'est peut-être pas encore payée."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        facture = commande.facture
        user = request.user
        
        # Vérification des droits d'accès
        is_owner = (commande.client and commande.client.user == user)
        is_staff_or_admin = user.is_superuser or user.is_staff
        is_serv = is_active_serveuse(user)
        
        if not (is_owner or is_staff_or_admin or is_serv):
            return Response(
                {"detail": "Vous n'avez pas la permission de consulter cette facture."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Renvoyer le fichier PDF
        if not facture.fichier_pdf:
            return Response(
                {"detail": "Le fichier PDF de la facture est introuvable sur le serveur."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        return FileResponse(facture.fichier_pdf, content_type='application/pdf')


class AdminFactureListView(APIView):
    """
    Liste toutes les factures.
    Accessible uniquement par les administrateurs et les serveuses actives.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        is_staff_or_admin = user.is_superuser or user.is_staff
        is_serv = is_active_serveuse(user)
        
        if not (is_staff_or_admin or is_serv):
            return Response(
                {"detail": "Accès réservé aux administrateurs et serveuses actives."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        factures = Facture.objects.select_related(
            'commande',
            'commande__client',
            'commande__client__user'
        ).all().order_by('-date_emission')
        
        # Filtres possibles par recherche de numéro de facture ou de commande
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            factures = factures.filter(
                Q(numero_facture__icontains=search) |
                Q(commande__numero_commande__icontains=search) |
                Q(commande__client__user__email__icontains=search)
            )
            
        paginator = CommandePagination() # réutilisation du paginateur de commande
        page = paginator.paginate_queryset(factures, request, view=self)
        if page is not None:
            serializer = AdminFactureSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
            
        serializer = AdminFactureSerializer(factures, many=True, context={'request': request})
        return Response(serializer.data)


class AdminFactureRenvoyerView(APIView):
    """
    Renvoyer la facture PDF d'une commande par email.
    Accessible uniquement par les administrateurs et les serveuses actives.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, numero_facture, *args, **kwargs):
        user = request.user
        is_staff_or_admin = user.is_superuser or user.is_staff
        is_serv = is_active_serveuse(user)
        
        if not (is_staff_or_admin or is_serv):
            return Response(
                {"detail": "Accès réservé aux administrateurs et serveuses actives."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        facture = get_object_or_404(Facture, numero_facture=numero_facture)
        email_client = facture.commande.client.user.email
        
        if not email_client:
            return Response(
                {"detail": "Le client n'a pas d'adresse e-mail configurée."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not facture.fichier_pdf:
            return Response(
                {"detail": "Le fichier PDF de la facture est introuvable sur le serveur."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        try:
            from orders.services import envoyer_email_facture
            # Lire le contenu du fichier PDF
            pdf_content = facture.fichier_pdf.read()
            envoyer_email_facture(facture, pdf_content, email_client)
            return Response(
                {"detail": f"Facture {facture.numero_facture} renvoyée avec succès à {email_client}."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"detail": f"Erreur lors de l'envoi de l'e-mail : {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class IsSuperUser(BasePermission):
    """
    Permet l'accès uniquement aux super-utilisateurs.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser


class AdminCodePromoViewSet(viewsets.ModelViewSet):
    """
    CRUD des codes promo réservé au Super-Admin.
    Envoie des notifications FCM/Emails à la création.
    """
    queryset = CodePromoAdmin.objects.all().order_by('-date_creation')
    serializer_class = CodePromoAdminSerializer
    permission_classes = [IsAuthenticated, IsSuperUser]

    def perform_create(self, serializer):
        instance = serializer.save()
        
        # Envoi de la notification et de l'e-mail uniquement lors de la création
        from utilisateur.models import Notification
        from django.core.mail import send_mail
        from django.conf import settings
        
        for client in instance.clients_autorises.all():
            user = client.user
            subject = "Nouveau code promo exclusif pour vous !"
            message = (
                f"Bonjour {user.get_full_name() or user.username},\n\n"
                f"Vous avez été sélectionné pour bénéficier d'un code promo exclusif !\n"
                f"Utilisez le code suivant lors de votre prochaine commande : {instance.code}\n"
                f"Ce code vous donne droit à une réduction de {instance.reduction_pourcentage}%.\n\n"
                f"À bientôt chez Accessoires Exclusifs !"
            )
            
            # Notification FCM via base
            Notification.objects.create(
                recipient=user,
                type='code_promo_admin',
                title='Code promo exclusif disponible !',
                message=f"Profitez de {instance.reduction_pourcentage}% de réduction avec le code : {instance.code}",
                url='/api/v1/orders/panier/',
                metadata={
                    'code_promo': instance.code,
                    'reduction_pourcentage': str(instance.reduction_pourcentage)
                }
            )
            
            # Envoi d'email
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )


# ============================================================
# STATISTIQUES FINANCIÈRES — ADMIN UNIQUEMENT
# ============================================================

class IsAdminUser(BasePermission):
    """Accès réservé aux utilisateurs is_staff (admin / superuser)."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class AdminStatistiquesBeneficesView(APIView):
    """
    Vue admin-only qui retourne un rapport financier complet :
    
    - Ventes et bénéfices par essence (regroupés par lots, basés sur
      LotEssenceConsommation pour un calcul historique exact).
    - Ventes et bénéfices pour les parfums, accessoires et produits labo.
    - Totaux globaux.
    
    Paramètres de filtrage optionnels :
      ?date_debut=YYYY-MM-DD  &date_fin=YYYY-MM-DD
      ?statut=validé          (filtre sur le statut de commande)
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, *args, **kwargs):
        from django.db.models import Sum, Count, Q
        from catalogue.models import Essence, LotEssence, LotEssenceConsommation
        from decimal import Decimal

        # ---- Filtres de date / statut ----------------------------------------
        date_debut = request.query_params.get('date_debut')
        date_fin   = request.query_params.get('date_fin')
        statut_cmd = request.query_params.get('statut', 'validé')  # par défaut : commandes validées

        # Filtre de base sur les commandes
        filtre_commande = Q(statut=statut_cmd) if statut_cmd else Q()
        if date_debut:
            filtre_commande &= Q(date_creation__date__gte=date_debut)
        if date_fin:
            filtre_commande &= Q(date_creation__date__lte=date_fin)

        # ---- Commandes sélectionnées -----------------------------------------
        commandes_ids = list(Commande.objects.filter(filtre_commande).values_list('id', flat=True))

        # ===================================================================
        # 1. ESSENCES — bénéfice par lot puis regroupement par essence
        # ===================================================================
        lots_qs = LotEssence.objects.select_related('essence').prefetch_related('consommations')

        rapport_essences = {}

        for lot in lots_qs:
            # CA généré sur ce lot pour les commandes filtrées
            consommations = lot.consommations.filter(
                commande__in=commandes_ids
            ).aggregate(
                ca=Sum('prix_vente_attribue'),
                ml_consommes=Sum('quantite_ml_utilisee')
            )
            ca_lot = Decimal(str(consommations['ca'] or 0))
            ml_lot = Decimal(str(consommations['ml_consommes'] or 0))

            # Coût d'achat proratisé aux ml consommés dans ce lot
            if lot.prix_achat_par_ml and ml_lot > 0:
                cout_lot = ml_lot * lot.prix_achat_par_ml
                benefice_lot = ca_lot - cout_lot
            else:
                cout_lot = Decimal('0')
                benefice_lot = None  # pas de prix d'achat → bénéfice inconnu

            essence_id = lot.essence_id
            if essence_id not in rapport_essences:
                rapport_essences[essence_id] = {
                    'essence_id':       essence_id,
                    'essence_nom':      f"{lot.essence.marque} – {lot.essence.nom}",
                    'essence_categorie': lot.essence.categorie,
                    'ca_total':         Decimal('0'),
                    'cout_total':       Decimal('0'),
                    'benefice_total':   Decimal('0'),
                    'benefice_connu':   True,  # passe à False si un lot n'a pas de prix
                    'lots': [],
                }

            rapport_essences[essence_id]['ca_total']    += ca_lot
            rapport_essences[essence_id]['cout_total']  += cout_lot
            if benefice_lot is not None:
                rapport_essences[essence_id]['benefice_total'] += benefice_lot
            else:
                rapport_essences[essence_id]['benefice_connu'] = False

            rapport_essences[essence_id]['lots'].append({
                'lot_id':            lot.id,
                'reference':         lot.reference_fournisseur or f'Lot #{lot.id}',
                'date_reception':    lot.date_reception.strftime('%Y-%m-%d') if lot.date_reception else None,
                'quantite_initiale': str(lot.quantite_initiale_ml or 0),
                'stock_restant':     str(lot.stock_ml),
                'est_termine':       lot.stock_ml <= Decimal('0'),
                'prix_achat_par_ml': str(lot.prix_achat_par_ml) if lot.prix_achat_par_ml else None,
                'ca_lot':            str(ca_lot.quantize(Decimal('0.01'))),
                'cout_lot':          str(cout_lot.quantize(Decimal('0.01'))),
                'benefice_lot':      str(benefice_lot.quantize(Decimal('0.01'))) if benefice_lot is not None else None,
            })

        # Formater pour la réponse
        essences_list = []
        for data in rapport_essences.values():
            essences_list.append({
                'essence_id':       data['essence_id'],
                'essence_nom':      data['essence_nom'],
                'essence_categorie': data['essence_categorie'],
                'benefice_connu':   data['benefice_connu'],
                'ca_total':         str(data['ca_total'].quantize(Decimal('0.01'))),
                'cout_total':       str(data['cout_total'].quantize(Decimal('0.01'))),
                'benefice_total':   str(data['benefice_total'].quantize(Decimal('0.01'))) if data['benefice_connu'] else None,
                'lots':             data['lots'],
            })

        # ===================================================================
        # 2. PARFUMS — ventes + bénéfice (snapshot)
        # ===================================================================
        from orders.models import CommandeLigneParfum
        parfums_agg = CommandeLigneParfum.objects.filter(
            commande__in=commandes_ids
        ).aggregate(
            nb_ventes=Count('id'),
            ca=Sum('sous_total'),
            cout=Sum('prix_achat_total_snapshot'),
        )
        ca_parfums   = Decimal(str(parfums_agg['ca']   or 0))
        cout_parfums = Decimal(str(parfums_agg['cout'] or 0))

        # ===================================================================
        # 3. ACCESSOIRES — ventes + bénéfice (snapshot)
        # ===================================================================
        from orders.models import CommandeLigneAccessoire
        access_agg = CommandeLigneAccessoire.objects.filter(
            commande__in=commandes_ids
        ).aggregate(
            nb_ventes=Count('id'),
            ca=Sum('sous_total'),
            cout=Sum('prix_achat_total_snapshot'),
        )
        ca_access   = Decimal(str(access_agg['ca']   or 0))
        cout_access = Decimal(str(access_agg['cout'] or 0))

        # ===================================================================
        # 4. PARFUMS PERSONNALISÉS (Labo) — ventes + bénéfice (snapshot)
        # ===================================================================
        from orders.models import CommandeLigneParfumPerso
        perso_agg = CommandeLigneParfumPerso.objects.filter(
            commande__in=commandes_ids
        ).aggregate(
            nb_ventes=Count('id'),
            ca=Sum('sous_total'),
            cout=Sum('prix_achat_total_snapshot'),
        )
        ca_perso   = Decimal(str(perso_agg['ca']   or 0))
        cout_perso = Decimal(str(perso_agg['cout'] or 0))

        # ===================================================================
        # 5. ESSENCES PERSONNALISÉES (Labo direct) — ventes + bénéfice
        # ===================================================================
        from orders.models import CommandeLigneEssencePersonnalisee
        ep_agg = CommandeLigneEssencePersonnalisee.objects.filter(
            commande__in=commandes_ids
        ).aggregate(
            nb_ventes=Count('id'),
            ca=Sum('sous_total'),
            cout=Sum('prix_achat_total_snapshot'),
        )
        ca_ep   = Decimal(str(ep_agg['ca']   or 0))
        cout_ep = Decimal(str(ep_agg['cout'] or 0))

        # ===================================================================
        # 6. TOTAUX GLOBAUX
        # ===================================================================
        ca_essences_total   = sum((Decimal(e['ca_total'])   for e in essences_list), Decimal('0'))
        cout_essences_total = sum((Decimal(e['cout_total']) for e in essences_list), Decimal('0'))

        ca_global      = ca_essences_total + ca_parfums + ca_access + ca_perso + ca_ep
        cout_global    = cout_essences_total + cout_parfums + cout_access + cout_perso + cout_ep
        benefice_global = ca_global - cout_global

        nb_commandes = len(commandes_ids)

        return Response({
            'filtres_appliques': {
                'statut_commande': statut_cmd or 'tous',
                'date_debut': date_debut,
                'date_fin':   date_fin,
            },
            'nb_commandes': nb_commandes,
            'totaux': {
                'chiffre_affaires': str(ca_global.quantize(Decimal('0.01'))),
                'cout_total':       str(cout_global.quantize(Decimal('0.01'))),
                'benefice_net':     str(benefice_global.quantize(Decimal('0.01'))),
            },
            'par_categorie': {
                'essences': {
                    'chiffre_affaires':    str(ca_essences_total.quantize(Decimal('0.01'))),
                    'cout_total':          str(cout_essences_total.quantize(Decimal('0.01'))),
                    'benefice':            str((ca_essences_total - cout_essences_total).quantize(Decimal('0.01'))),
                    'detail_par_essence':  essences_list,
                },
                'parfums': {
                    'nb_ventes':        parfums_agg['nb_ventes'] or 0,
                    'chiffre_affaires': str(ca_parfums.quantize(Decimal('0.01'))),
                    'cout_total':       str(cout_parfums.quantize(Decimal('0.01'))),
                    'benefice':         str((ca_parfums - cout_parfums).quantize(Decimal('0.01'))),
                },
                'accessoires': {
                    'nb_ventes':        access_agg['nb_ventes'] or 0,
                    'chiffre_affaires': str(ca_access.quantize(Decimal('0.01'))),
                    'cout_total':       str(cout_access.quantize(Decimal('0.01'))),
                    'benefice':         str((ca_access - cout_access).quantize(Decimal('0.01'))),
                },
                'parfums_personnalises': {
                    'nb_ventes':        perso_agg['nb_ventes'] or 0,
                    'chiffre_affaires': str(ca_perso.quantize(Decimal('0.01'))),
                    'cout_total':       str(cout_perso.quantize(Decimal('0.01'))),
                    'benefice':         str((ca_perso - cout_perso).quantize(Decimal('0.01'))),
                },
                'essences_personnalisees': {
                    'nb_ventes':        ep_agg['nb_ventes'] or 0,
                    'chiffre_affaires': str(ca_ep.quantize(Decimal('0.01'))),
                    'cout_total':       str(cout_ep.quantize(Decimal('0.01'))),
                    'benefice':         str((ca_ep - cout_ep).quantize(Decimal('0.01'))),
                },
            },
        }, status=status.HTTP_200_OK)

# ============================================================
# VIEW — AJOUTER DIFFUSEUR AU PANIER
# ============================================================
class AjouterDiffuseurParfumView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        from .serializers import AjouterDiffuseurParfumSerializer
        from .models import PanierLigneDiffuseurParfum
        from .serializers import PanierSerializer

        serializer = AjouterDiffuseurParfumSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        panier_id = serializer.validated_data.get('panier_id')
        diffuseur = serializer.validated_data['diffuseur_obj']
        quantite = serializer.validated_data['quantite']

        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)

            ligne, created = PanierLigneDiffuseurParfum.objects.get_or_create(
                panier=panier,
                diffuseur=diffuseur,
                defaults={
                    'prix_calcule': diffuseur.prix_actuel,
                    'quantite': quantite,
                    'sous_total': diffuseur.prix_actuel * quantite
                }
            )

            if not created:
                total_quantite = ligne.quantite + quantite
                if diffuseur.stock_quantite < total_quantite:
                    return Response(
                        {"quantite": f"Stock insuffisant. Seulement {diffuseur.stock_quantite} disponibles (vous en avez déjà {ligne.quantite} dans le panier)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ligne.quantite = total_quantite
                ligne.prix_calcule = diffuseur.prix_actuel
                ligne.save()

            panier.recalculer_total()

        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)