from django.shortcuts import render, get_object_or_404
from django.http import FileResponse
import random
import string
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
    Facture
)
from orders.utils import get_or_create_panier
from orders.serializers import (
    AjouterParfumSerializer,
    AjouterAccessoireSerializer,
    AjouterProduitFiniEssenceSerializer,
    AjouterParfumPersonnaliseSerializer,
    AjouterEssencePersonnaliseeSerializer,
    PanierSerializer,
    AppliquerCodePromoSerializer,
    CommandeSerializer,
    PasserCommandeSerializer,
    FactureSerializer
)
from utilisateur.permissions import CommandePermission, is_active_serveuse


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
                if produit.stock_disponible < total_quantite:
                    return Response(
                        {"quantite": f"Stock insuffisant. Seulement {produit.stock_disponible} disponibles (vous en avez déjà {ligne.quantite} dans le panier)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ligne.quantite = total_quantite
                ligne.prix_unitaire_snapshot = produit.prix_actuel
                ligne.save()
            
            panier.recalculer_total()
            
        return Response(PanierSerializer(panier, context={'request': request}).data, status=status.HTTP_200_OK)


class AjouterParfumPersonnaliseView(APIView):
    """
    Ajoute un parfum personnalisé au panier actif (requiert d'être connecté).
    """
    # Note: La permission_classes est à AllowAny mais la validation du serializer 
    # lèvera une exception si l'utilisateur n'est pas connecté. Cela évite les erreurs de pré-requête CORS.
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AjouterParfumPersonnaliseSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        panier_id = serializer.validated_data.get('panier_id')
        parfum_perso = serializer.validated_data['parfum_perso_obj']
        quantite = serializer.validated_data['quantite']
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
                    'note_client': note_client
                }
            )
            
            if not created:
                ligne.quantite += quantite
                ligne.prix_calcule = parfum_perso.prix_total
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
            if ligne.produit_fini_essence.stock_disponible < quantite:
                return Response({"quantite": f"Stock insuffisant. Seulement {ligne.produit_fini_essence.stock_disponible} disponibles."}, status=status.HTTP_400_BAD_REQUEST)

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
        prestataire = serializer.validated_data['prestataire_obj']
        code_promo = serializer.validated_data['code_promo'].strip()
        
        with transaction.atomic():
            panier = get_or_create_panier(request, panier_id)
            panier.code_promo_applique = code_promo
            panier.prestataire = prestataire
            panier.remise_pourcentage = prestataire.reduction_client_pourcentage
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
            commandes = Commande.objects.filter(livreur=user.client.livreur).order_by('-date_creation')
        elif is_active_client(user):
            commandes = Commande.objects.filter(client=user.client).order_by('-date_creation')
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
        
        if is_admin_or_serv:
            # Liste des champs modifiables par admin/serveuse
            allowed_fields = {
                'statut', 'statut_livraison', 'livreur', 'date_livraison_estimee', 
                'note_interne', 'motif_echec_livraison', 'frais_livraison'
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
            # Le livreur ne peut modifier que le statut_paiement, statut_livraison et motif d'échec
            statut_paiement = data.get('statut_paiement')
            statut_livraison = data.get('statut_livraison')
            motif_echec = data.get('motif_echec_livraison')
            
            # Support de payload action=livrer/echouer (cf section 4.4)
            action = data.get('action')
            motif = data.get('motif')
            if action == 'livrer':
                statut_paiement = 'payé'
                statut_livraison = 'livrée'
            elif action == 'echouer':
                statut_paiement = 'échoué'
                statut_livraison = 'échouée'
                motif_echec = motif
                
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
                
            if motif_echec is not None:
                commande.motif_echec_livraison = motif_echec
                updated = True
                
            if not updated:
                return Response({"detail": "Aucune modification autorisée pour votre rôle n'a été transmise."}, status=status.HTTP_400_BAD_REQUEST)
                
            # Mettre à jour l'affectation correspondante
            from orders.models import AffectationLivraison
            aff = AffectationLivraison.objects.filter(commande=commande, livreur=user.client.livreur).last()
            if aff:
                if statut_livraison == 'livrée':
                    aff.statut = 'livrée'
                    aff.date_livraison_reelle = timezone.now()
                elif statut_livraison == 'échouée':
                    aff.statut = 'échouée'
                    if motif_echec:
                        aff.motif_echec = motif_echec
                aff.save()
                
            commande.save()
            return Response(CommandeSerializer(commande, context={'request': request}).data, status=status.HTTP_200_OK)
            
        else:
            return Response({"detail": "Vous n'avez pas la permission de modifier cette commande."}, status=status.HTTP_403_FORBIDDEN)


class PasserCommandeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PasserCommandeSerializer(data=request.data, context={'request': request})
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
            
        factures = Facture.objects.all().order_by('-date_emission')
        
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
            serializer = FactureSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
            
        serializer = FactureSerializer(factures, many=True, context={'request': request})
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