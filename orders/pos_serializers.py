from rest_framework import serializers
from django.db import transaction
from django.contrib.auth import get_user_model
from decimal import Decimal
import random
import string

from orders.models import (
    Commande,
    CommandeLigneParfum,
    CommandeLigneAccessoire,
    CommandeProduitFiniEssence,
    CodePromoAdmin,
)
from catalogue.models import Parfum, Accessoire, ProduitFiniEssence
from utilisateur.models import Client, Prestataire
from allauth.account.models import EmailAddress

User = get_user_model()


class POSCommandLineSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['parfum', 'accessoire', 'essence'])
    id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)


class POSCommandeCreateSerializer(serializers.Serializer):
    client_email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    client_telephone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    client_nom_complet = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    livraison_nom_complet = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    livraison_telephone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    code_promo = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    note_interne = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    lignes = POSCommandLineSerializer(many=True, required=True)

    def validate_lignes(self, value):
        if not value:
            raise serializers.ValidationError("La liste des lignes de commande ne peut pas être vide.")
        return value

    def validate(self, data):
        # 1. Valider le code promo si présent
        code_promo = data.get('code_promo')
        if code_promo:
            code_clean = code_promo.strip()
            # Chercher d'abord si c'est un prestataire actif
            prestataire = Prestataire.objects.filter(code_promo=code_clean, statut='actif').first()
            if prestataire:
                data['prestataire_obj'] = prestataire
            else:
                # Sinon chercher si c'est un code promo admin actif
                promo_admin = CodePromoAdmin.objects.filter(code__iexact=code_clean, est_actif=True).first()
                if not promo_admin:
                    raise serializers.ValidationError({"code_promo": "Code promotionnel invalide ou inactif."})
                
                # Résoudre le client potentiel pour valider l'autorisation et l'usage unique
                client_email = data.get('client_email')
                client_telephone = data.get('client_telephone')
                client_found = None
                
                if client_telephone and client_telephone.strip():
                    client_found = Client.objects.filter(user__telephone=client_telephone.strip()).first()
                if not client_found and client_email and client_email.strip():
                    client_found = Client.objects.filter(user__email=client_email.strip().lower()).first()
                
                if not client_found:
                    raise serializers.ValidationError({"code_promo": "Ce code promo ne peut être utilisé que par un client existant enregistré."})
                
                # Vérifier l'autorisation
                if not promo_admin.clients_autorises.filter(pk=client_found.pk).exists():
                    raise serializers.ValidationError({"code_promo": "Ce client n'est pas autorisé à utiliser ce code promo."})
                
                # Vérifier l'usage unique
                if Commande.objects.filter(client=client_found, code_promo_utilise__iexact=code_clean).exclude(statut__in=['annulée', 'remboursée']).exists():
                    raise serializers.ValidationError({"code_promo": "Ce client a déjà utilisé ce code promo."})
                
                data['promo_admin_obj'] = promo_admin

        # 2. Valider les lignes et les stocks
        validated_lines = []
        for line in data.get('lignes', []):
            product_type = line['type']
            product_id = line['id']
            qty = line['quantite']

            if product_type == 'parfum':
                try:
                    product = Parfum.objects.get(id=product_id)
                except Parfum.DoesNotExist:
                    raise serializers.ValidationError({"lignes": f"Parfum avec l'ID {product_id} introuvable."})
                if not product.actif:
                    raise serializers.ValidationError({"lignes": f"Le parfum '{product.nom}' n'est pas actif."})
                if product.stock_quantite < qty:
                    raise serializers.ValidationError({"lignes": f"Stock insuffisant pour le parfum '{product.nom}'. Disponible: {product.stock_quantite}, Demandé: {qty}."})
                validated_lines.append({
                    'type': 'parfum',
                    'product_obj': product,
                    'quantite': qty,
                    'prix_unitaire': product.prix_promotionnel if (product.prix_promotionnel is not None) else product.prix_unitaire
                })

            elif product_type == 'accessoire':
                try:
                    product = Accessoire.objects.get(id=product_id)
                except Accessoire.DoesNotExist:
                    raise serializers.ValidationError({"lignes": f"Accessoire avec l'ID {product_id} introuvable."})
                if not product.actif:
                    raise serializers.ValidationError({"lignes": f"L'accessoire '{product.nom}' n'est pas actif."})
                if product.stock_quantite < qty:
                    raise serializers.ValidationError({"lignes": f"Stock insuffisant pour l'accessoire '{product.nom}'. Disponible: {product.stock_quantite}, Demandé: {qty}."})
                validated_lines.append({
                    'type': 'accessoire',
                    'product_obj': product,
                    'quantite': qty,
                    'prix_unitaire': product.prix_promotionnel if (product.prix_promotionnel is not None) else product.prix_unitaire
                })

            elif product_type == 'essence':
                try:
                    product = ProduitFiniEssence.objects.get(id=product_id)
                except ProduitFiniEssence.DoesNotExist:
                    raise serializers.ValidationError({"lignes": f"Produit fini essence avec l'ID {product_id} introuvable."})
                if not product.actif:
                    raise serializers.ValidationError({"lignes": f"Le produit fini essence '{product.essence.nom_complet}' ({product.taille_ml}ml) n'est pas actif."})
                if product.stock_disponible < qty:
                    raise serializers.ValidationError({"lignes": f"Stock insuffisant pour '{product.essence.nom_complet}' ({product.taille_ml}ml). Disponible: {product.stock_disponible}, Demandé: {qty}."})
                validated_lines.append({
                    'type': 'essence',
                    'product_obj': product,
                    'quantite': qty,
                    'prix_unitaire': product.prix_promotionnel if (product.prix_promotionnel is not None) else product.prix
                })

        data['validated_lines'] = validated_lines
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        client_email = validated_data.get('client_email')
        client_telephone = validated_data.get('client_telephone')
        client_nom_complet = validated_data.get('client_nom_complet')
        livraison_nom_complet = (validated_data.get('livraison_nom_complet') or '').strip()
        livraison_telephone = (validated_data.get('livraison_telephone') or '').strip()
        code_promo = validated_data.get('code_promo')
        note_interne = validated_data.get('note_interne', '')

        # 1. Gestion / Résolution du client
        client_obj = None

        with transaction.atomic():
            # A. Par téléphone (prioritaire pour éviter les doublons sur le numéro de téléphone unique)
            if client_telephone and client_telephone.strip():
                phone_clean = client_telephone.strip()
                user = User.objects.filter(telephone=phone_clean).first()
                if user:
                    if hasattr(user, 'client'):
                        client_obj = user.client
                    else:
                        client_obj = Client.objects.create(user=user)
                elif client_email and client_email.strip():
                    # Si le téléphone n'existe pas, mais qu'un e-mail a été fourni, vérifier l'e-mail
                    email_clean = client_email.strip().lower()
                    user = User.objects.filter(email=email_clean).first()
                    if user:
                        # Mettre à jour le téléphone du client existant
                        user.telephone = phone_clean
                        user.save(update_fields=['telephone'])
                        if hasattr(user, 'client'):
                            client_obj = user.client
                        else:
                            client_obj = Client.objects.create(user=user)

            # B. Par E-mail (si pas résolu par téléphone)
            if not client_obj and client_email and client_email.strip():
                email_clean = client_email.strip().lower()
                user = User.objects.filter(email=email_clean).first()
                if user:
                    if hasattr(user, 'client'):
                        client_obj = user.client
                    else:
                        client_obj = Client.objects.create(user=user)
                else:
                    # Créer un nouvel utilisateur avec e-mail
                    parts = client_nom_complet.strip().split(' ', 1) if client_nom_complet else ["Client", "POS"]
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""
                    
                    random_pw = User.objects.make_random_password()
                    username = email_clean.split('@')[0]
                    base_username = username
                    for i in range(10):
                        if not User.objects.filter(username=username).exists():
                            break
                        username = f"{base_username}_{random.randint(100, 999)}"

                    user = User.objects.create_user(
                        username=username,
                        email=email_clean,
                        password=random_pw,
                        first_name=first_name,
                        last_name=last_name,
                        telephone=client_telephone.strip() if client_telephone else None
                    )
                    client_obj = user.client

                    EmailAddress.objects.create(
                        user=user,
                        email=email_clean,
                        verified=True,
                        primary=True
                    )

            # C. Par téléphone seul (si pas d'e-mail fourni ni résolu)
            if not client_obj and client_telephone and client_telephone.strip():
                phone_clean = client_telephone.strip()
                # Créer un utilisateur invité
                parts = client_nom_complet.strip().split(' ', 1) if client_nom_complet else ["Client", "POS"]
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
                
                random_pw = User.objects.make_random_password()
                email_clean = f"tel_{phone_clean.replace('+', '')}@accessoireexclusif.com"
                username = f"tel_{phone_clean.replace('+', '')}"
                base_username = username
                for i in range(10):
                    if not User.objects.filter(username=username).exists():
                        break
                    username = f"{base_username}_{random.randint(100, 999)}"
                
                user = User.objects.create_user(
                    username=username,
                    email=email_clean,
                    password=random_pw,
                    first_name=first_name,
                    last_name=last_name,
                    telephone=phone_clean
                )
                client_obj = user.client

                EmailAddress.objects.create(
                    user=user,
                    email=email_clean,
                    verified=True,
                    primary=True
                )

            # D. Fallback Boutique (anonyme)
            if not client_obj:
                email_clean = "boutique@accessoireexclusif.com"
                user = User.objects.filter(email=email_clean).first()
                if not user:
                    random_pw = User.objects.make_random_password()
                    user = User.objects.create_user(
                        username="boutique",
                        email=email_clean,
                        password=random_pw,
                        first_name="Client",
                        last_name="Boutique",
                        telephone="00000000"
                    )
                    EmailAddress.objects.create(
                        user=user,
                        email=email_clean,
                        verified=True,
                        primary=True
                    )
                client_obj = user.client

            # 2. Préparation de la commande
            prestataire = validated_data.get('prestataire_obj')

            # Livraison : champs optionnels ; si client connecté / résolu, remplir depuis le profil
            connected_user = request.user if request and request.user.is_authenticated else None
            if connected_user and hasattr(connected_user, 'client'):
                if client_obj and client_obj.user_id == connected_user.id:
                    if not livraison_nom_complet:
                        livraison_nom_complet = f"{connected_user.first_name} {connected_user.last_name}".strip()
                    if not livraison_telephone and connected_user.telephone:
                        livraison_telephone = connected_user.telephone

            if client_obj and client_obj.user:
                client_user = client_obj.user
                if not livraison_nom_complet:
                    livraison_nom_complet = f"{client_user.first_name} {client_user.last_name}".strip()
                if not livraison_telephone and client_user.telephone:
                    livraison_telephone = client_user.telephone

            display_name = livraison_nom_complet
            if not display_name and client_nom_complet:
                display_name = client_nom_complet.strip()
            if not display_name and client_obj and client_obj.user:
                display_name = f"{client_obj.user.first_name} {client_obj.user.last_name}".strip()
            if not display_name:
                display_name = "Client Boutique"

            display_phone = livraison_telephone
            if not display_phone and client_telephone:
                display_phone = client_telephone.strip()
            if not display_phone and client_obj and client_obj.user and client_obj.user.telephone:
                display_phone = client_obj.user.telephone
            if not display_phone:
                display_phone = "00000000"

            # Créer la Commande (les totaux initiaux sont mis à 0, recalculer_commande s'en occupera)
            commande = Commande.objects.create(
                client=client_obj,
                prestataire=prestataire,
                code_promo_utilise=code_promo.strip() if code_promo else '',
                frais_livraison=Decimal('0'),
                sous_total=Decimal('0'),
                remise_code_promo=Decimal('0'),
                total_ttc=Decimal('0'),
                livraison_nom_complet=display_name,
                livraison_quartier='',
                livraison_ville='Boutique',
                livraison_telephone=display_phone,
                note_client='',
                note_interne=f"Achat Direct Boutique. {note_interne}".strip(),
                statut='validé',  # statut_paiement='payé' passera automatiquement la commande à 'livrée' dans save()
                statut_livraison='en_attente_affectation',
                statut_paiement='payé',  # Forcer le statut de paiement à PAYÉ
                commission_statut='non_versée'
            )

            # 3. Ajouter les lignes de commande
            for line in validated_data['validated_lines']:
                l_type = line['type']
                prod = line['product_obj']
                qty = line['quantite']
                prix_unitaire = line['prix_unitaire']

                if l_type == 'parfum':
                    CommandeLigneParfum.objects.create(
                        commande=commande,
                        parfum=prod,
                        nom_snapshot=prod.nom,
                        quantite=qty,
                        prix_unitaire_snapshot=prix_unitaire,
                        remise_ligne=Decimal('0'),
                        sous_total=prix_unitaire * qty
                    )
                elif l_type == 'accessoire':
                    CommandeLigneAccessoire.objects.create(
                        commande=commande,
                        accessoire=prod,
                        nom_snapshot=prod.nom,
                        quantite=qty,
                        prix_unitaire_snapshot=prix_unitaire,
                        remise_ligne=Decimal('0'),
                        sous_total=prix_unitaire * qty
                    )
                elif l_type == 'essence':
                    CommandeProduitFiniEssence.objects.create(
                        commande=commande,
                        produit_fini_essence=prod,
                        nom_snapshot=prod.essence.nom,
                        quantite=qty,
                        prix_unitaire_snapshot=prix_unitaire,
                        remise_ligne=Decimal('0'),
                        sous_total=prix_unitaire * qty
                    )

            # 4. Recalculer les totaux de la commande et sauvegarder pour déclencher le cycle standard
            # (ceci met à jour les stocks via appliquer_stocks() et génère le fichier de facture PDF)
            commande.recalculer_commande()
            commande.save()

            return commande
