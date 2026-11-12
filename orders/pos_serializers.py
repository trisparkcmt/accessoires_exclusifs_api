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
    CommandeLigneDiffuseurParfum,
    CommandeLigneParfumPerso,
    CommandeLigneEssencePersonnalisee,
    Panier,
    CodePromoAdmin,
)
from catalogue.models import Parfum, Accessoire, ProduitFiniEssence, DiffuseurParfum
from laboratoire.models import ParfumPersonnalise, EssencePersonnalisee
from utilisateur.models import Client, Prestataire
from allauth.account.models import EmailAddress

User = get_user_model()


class POSCompositionLigneSerializer(serializers.Serializer):
    lot_essence_id = serializers.IntegerField(required=True)
    quantite_ml = serializers.DecimalField(max_digits=8, decimal_places=3, min_value=Decimal('0.1'))


class POSCompositionRecetteSerializer(serializers.Serializer):
    flacon_id = serializers.IntegerField(required=True)
    nom = serializers.CharField(required=False, allow_blank=True, max_length=200, default='')
    couleur = serializers.CharField(required=False, allow_blank=True, max_length=50, default='')
    nom_sur_flacon = serializers.CharField(required=False, allow_blank=True, max_length=150, default='')
    lignes = POSCompositionLigneSerializer(many=True, required=True)


class POSCommandLineSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['parfum', 'accessoire', 'essence', 'diffuseur', 'parfum_perso', 'essence_perso'])
    id = serializers.IntegerField(required=False, allow_null=True)
    quantite = serializers.IntegerField(min_value=1, default=1)
    couleur = serializers.CharField(required=False, allow_blank=True, max_length=50, default='')
    nom_sur_flacon = serializers.CharField(required=False, allow_blank=True, max_length=150, default='')
    recette = POSCompositionRecetteSerializer(required=False, allow_null=True)


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
                if Commande.objects.filter(client=client_found, code_promo_utilise__iexact=code_clean).exclude(statut='annulée').exists():
                    raise serializers.ValidationError({"code_promo": "Ce client a déjà utilisé ce code promo."})
                
                data['promo_admin_obj'] = promo_admin

        # 2. Valider les lignes et les stocks
        validated_lines = []

        for idx, line in enumerate(data.get('lignes', [])):
            product_type = line['type']
            product_id = line.get('id')
            qty = line['quantite']
            recette = line.get('recette')

            if product_type == 'parfum':
                if not product_id:
                    raise serializers.ValidationError({"lignes": f"L'ID du parfum est requis (ligne {idx+1})."})
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
                if not product_id:
                    raise serializers.ValidationError({"lignes": f"L'ID de l'accessoire est requis (ligne {idx+1})."})
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
                if not product_id:
                    raise serializers.ValidationError({"lignes": f"L'ID du produit fini essence est requis (ligne {idx+1})."})
                try:
                    product = ProduitFiniEssence.objects.get(id=product_id)
                except ProduitFiniEssence.DoesNotExist:
                    raise serializers.ValidationError({"lignes": f"Produit fini essence avec l'ID {product_id} introuvable."})
                if not product.actif:
                    raise serializers.ValidationError({"lignes": f"Le produit fini essence '{product.essence.nom_complet}' ({product.taille_ml}ml) n'est pas actif."})
                quantite_ml = Decimal(str(qty)) * Decimal(str(product.taille_ml))
                if product.essence.stock_total_ml() < quantite_ml:
                    raise serializers.ValidationError({"lignes": f"Stock d'essence insuffisant pour '{product.essence.nom_complet}'. Demandé: {qty} flacons de {product.taille_ml}ml."})
                validated_lines.append({
                    'type': 'essence',
                    'product_obj': product,
                    'quantite': qty,
                    'prix_unitaire': product.prix_promotionnel if (product.prix_promotionnel is not None) else product.prix
                })

            elif product_type == 'diffuseur':
                if not product_id:
                    raise serializers.ValidationError({"lignes": f"L'ID du diffuseur est requis (ligne {idx+1})."})
                try:
                    product = DiffuseurParfum.objects.get(id=product_id)
                except DiffuseurParfum.DoesNotExist:
                    raise serializers.ValidationError({"lignes": f"Diffuseur avec l'ID {product_id} introuvable."})
                if not product.actif:
                    raise serializers.ValidationError({"lignes": f"Le diffuseur '{product.nom}' n'est pas actif."})
                if product.stock_quantite < qty:
                    raise serializers.ValidationError({"lignes": f"Stock insuffisant pour le diffuseur '{product.nom}'. Disponible: {product.stock_quantite}, Demandé: {qty}."})
                validated_lines.append({
                    'type': 'diffuseur',
                    'product_obj': product,
                    'quantite': qty,
                    'prix_unitaire': product.prix_promotionnel if (product.prix_promotionnel is not None) else product.prix_unitaire
                })

            elif product_type == 'parfum_perso':
                if recette:
                    # Validation d'une recette sur-mesure directe envoyée dans le POS
                    flacon_id = recette.get('flacon_id')
                    nom_perso = recette.get('nom', '')
                    lignes_recette = recette.get('lignes', [])

                    if not lignes_recette:
                        raise serializers.ValidationError({"lignes": f"La recette de création sur-mesure (ligne {idx+1}) ne contient aucune essence."})

                    from catalogue.models import Flacon, LotEssence
                    try:
                        flacon = Flacon.objects.get(id=flacon_id, actif=True)
                    except Flacon.DoesNotExist:
                        raise serializers.ValidationError({"lignes": f"Le flacon #{flacon_id} n'existe pas ou n'est pas actif."})

                    if flacon.stock_quantite < qty:
                        raise serializers.ValidationError({"lignes": f"Stock de flacon insuffisant pour '{flacon.nom}'. Disponible: {flacon.stock_quantite}."})

                    lot_ids = [l['lot_essence_id'] for l in lignes_recette]
                    lots = LotEssence.objects.filter(id__in=lot_ids, actif=True).select_related('essence')
                    lots_dict = {lot.id: lot for lot in lots}

                    total_volume = Decimal('0')
                    recette_lignes_valid = []
                    for l_idx, l_item in enumerate(lignes_recette):
                        lot_id = l_item['lot_essence_id']
                        qty_ml = Decimal(str(l_item['quantite_ml']))
                        if lot_id not in lots_dict:
                            raise serializers.ValidationError({"lignes": f"Le lot d'essence #{lot_id} n'existe pas ou n'est pas actif."})
                        lot = lots_dict[lot_id]
                        if lot.stock_ml < qty_ml * Decimal(str(qty)):
                            raise serializers.ValidationError({"lignes": f"Stock d'essence insuffisant pour '{lot.essence.nom}'. Disponible: {lot.stock_ml}ml."})
                        total_volume += qty_ml
                        recette_lignes_valid.append((lot, qty_ml))

                    contenance = Decimal(str(flacon.contenance_ml))
                    volume_max = contenance * Decimal('0.45')
                    if total_volume > volume_max:
                        raise serializers.ValidationError({"lignes": f"Le volume total d'essences ({total_volume}ml) dépasse 45% de la contenance du flacon ({volume_max}ml max)."})

                    couleur_val = line.get('couleur') or (recette.get('couleur') if recette else '')
                    nom_flacon_val = line.get('nom_sur_flacon') or (recette.get('nom_sur_flacon') if recette else '')

                    validated_lines.append({
                        'type': 'parfum_perso',
                        'product_obj': None,
                        'recette_data': {
                            'flacon': flacon,
                            'nom': nom_perso,
                            'lignes': recette_lignes_valid,
                        },
                        'couleur': couleur_val,
                        'nom_sur_flacon': nom_flacon_val,
                        'quantite': qty,
                        'prix_unitaire': None
                    })
                elif product_id:
                    try:
                        product = ParfumPersonnalise.objects.get(id=product_id)
                    except ParfumPersonnalise.DoesNotExist:
                        raise serializers.ValidationError({"lignes": f"Parfum personnalisé avec l'ID {product_id} introuvable."})
                    
                    couleur_val = line.get('couleur') or product.couleur or ''
                    nom_flacon_val = line.get('nom_sur_flacon') or product.nom_sur_flacon or ''

                    validated_lines.append({
                        'type': 'parfum_perso',
                        'product_obj': product,
                        'couleur': couleur_val,
                        'nom_sur_flacon': nom_flacon_val,
                        'quantite': qty,
                        'prix_unitaire': product.prix_total
                    })
                else:
                    raise serializers.ValidationError({"lignes": f"Pour un parfum_perso (ligne {idx+1}), vous devez fournir un 'id' ou une 'recette'."})

            elif product_type == 'essence_perso':
                if not product_id:
                    raise serializers.ValidationError({"lignes": f"L'ID de l'essence personnalisée est requis (ligne {idx+1})."})
                try:
                    product = EssencePersonnalisee.objects.get(id=product_id)
                except EssencePersonnalisee.DoesNotExist:
                    raise serializers.ValidationError({"lignes": f"Essence personnalisée avec l'ID {product_id} introuvable."})
                validated_lines.append({
                    'type': 'essence_perso',
                    'product_obj': product,
                    'quantite': qty,
                    'prix_unitaire': product.prix_par_ml_calcule
                })

        if not validated_lines:
            raise serializers.ValidationError({"lignes": "La commande ne contient aucun article."})

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

            vendeur_user = request.user if (request and request.user.is_authenticated) else None
            vendeur_info = f" | Vendeur: {vendeur_user.get_full_name() or vendeur_user.email}" if vendeur_user else ""

            # Créer la Commande (les totaux initiaux sont mis à 0, recalculer_commande s'en occupera)
            commande = Commande.objects.create(
                client=client_obj,
                vendeur=vendeur_user,
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
                note_interne=f"Achat Direct Boutique{vendeur_info}. {note_interne}".strip(),
                statut='validé',
                statut_livraison='en_attente_affectation',
                statut_paiement='en_attente',  # Initialisé à en_attente pour que les lignes soient insérées avant le trigger facture
                commission_statut='non_versée'
            )

            # 3. Ajouter les lignes de commande
            for line in validated_data['validated_lines']:
                l_type = line['type']
                prod = line.get('product_obj')
                qty = line['quantite']
                prix_unitaire = line.get('prix_unitaire')
                recette_data = line.get('recette_data')

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
                elif l_type == 'diffuseur':
                    CommandeLigneDiffuseurParfum.objects.create(
                        commande=commande,
                        diffuseur=prod,
                        nom_snapshot=prod.nom,
                        quantite=qty,
                        prix_unitaire_snapshot=prix_unitaire,
                        remise_ligne=Decimal('0'),
                        sous_total=prix_unitaire * qty
                    )
                elif l_type == 'parfum_perso':
                    couleur = line.get('couleur', '')
                    nom_sur_flacon = line.get('nom_sur_flacon', '')
                    if not prod and recette_data:
                        from laboratoire.models import ParfumPersonnaliseLigne
                        flacon = recette_data['flacon']
                        nom_recette = recette_data['nom'] or f"Création Sur Mesure POS #{random.randint(100, 999)}"

                        prod = ParfumPersonnalise.objects.create(
                            client=client_obj,
                            flacon=flacon,
                            nom=nom_recette,
                            couleur=couleur,
                            nom_sur_flacon=nom_sur_flacon,
                            prix_essences=Decimal('0'),
                            prix_flacon_snapshot=flacon.prix_unitaire,
                            prix_total=flacon.prix_unitaire,
                            statut='brouillon',
                            enregistre=False
                        )
                        for lot, qty_ml in recette_data['lignes']:
                            ParfumPersonnaliseLigne.objects.create(
                                parfum_personnalise=prod,
                                essence=lot,
                                quantite_ml=qty_ml,
                                prix_par_ml_snapshot=lot.essence.prix_par_ml
                            )
                        prod.recalculer_prix()
                        prix_unitaire = prod.prix_total

                    CommandeLigneParfumPerso.objects.create(
                        commande=commande,
                        parfum_personnalise=prod,
                        quantite=qty,
                        prix_snapshot=prix_unitaire,
                        sous_total=prix_unitaire * qty,
                        couleur=couleur or (prod.couleur if prod else ''),
                        nom_sur_flacon=nom_sur_flacon or (prod.nom_sur_flacon if prod else '')
                    )
                elif l_type == 'essence_perso':
                    CommandeLigneEssencePersonnalisee.objects.create(
                        commande=commande,
                        essence_personnalisee=prod,
                        quantite=qty,
                        prix_calcule=prix_unitaire,
                        sous_total=prix_unitaire * qty
                    )

            # 4. Recalculer les totaux de la commande et passer le statut à 'payé'
            # (ceci met à jour les stocks et déclenche la génération asynchrone de la facture PDF via Celery)
            commande.recalculer_commande()
            commande.statut_paiement = 'payé'
            commande.save()

            return commande


# ============================================================
# SERIALIZERS DU RAPPORT JOURNALIER DE CAISSE
# ============================================================
from orders.models import RapportJournalierCaisse
from orders.pos_services import (
    calculer_donnees_journee_caissiere,
    formater_texte_whatsapp,
    generer_rapport_caisse_pdf,
)
from django.utils import timezone


class RapportJournalierCaisseSerializer(serializers.ModelSerializer):
    caissiere_nom = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = RapportJournalierCaisse
        fields = [
            'id',
            'caissiere',
            'caissiere_nom',
            'date',
            'heure_arrivee',
            'heure_depart',
            'recette_totale',
            'total_depenses',
            'reste_en_caisse',
            'sorties_articles',
            'entrees_stock',
            'depenses',
            'autres_donnees_manuelles',
            'actions_communication',
            'observations',
            'texte_formate',
            'fichier_pdf',
            'pdf_url',
            'date_creation',
            'date_modification',
        ]

    def get_caissiere_nom(self, obj):
        if obj.caissiere:
            return obj.caissiere.get_full_name() or obj.caissiere.email or obj.caissiere.username
        return ""

    def get_pdf_url(self, obj):
        request = self.context.get('request')
        if obj.fichier_pdf and hasattr(obj.fichier_pdf, 'url'):
            if request:
                return request.build_absolute_uri(obj.fichier_pdf.url)
            return obj.fichier_pdf.url
        return None


class POSRapportJournalierClotureSerializer(serializers.Serializer):
    caissiere_id = serializers.IntegerField(required=False, help_text="Réservé aux superadmins pour clôturer au nom d'une caissière")
    date = serializers.DateField(required=False, default=timezone.now)
    heure_arrivee = serializers.CharField(required=False, allow_blank=True, default='')
    heure_depart = serializers.CharField(required=False, allow_blank=True, default='')
    reste_en_caisse = serializers.CharField(required=False, allow_blank=True, default='')
    actions_communication = serializers.CharField(required=False, allow_blank=True, default='')
    observations = serializers.CharField(required=False, allow_blank=True, default='')
    autres_donnees_manuelles = serializers.DictField(required=False, default=dict)
    sorties_articles_ajouts = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    entrees_stock_ajouts = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    def save(self):
        request = self.context.get('request')
        caissiere_user = request.user
        if request and request.user.is_superuser and self.validated_data.get('caissiere_id'):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            custom_caissiere = User.objects.filter(id=self.validated_data['caissiere_id']).first()
            if custom_caissiere:
                caissiere_user = custom_caissiere
        raw_date = self.validated_data.get('date')
        if hasattr(raw_date, 'date'):
            target_date = raw_date.date()
        elif raw_date:
            target_date = raw_date
        else:
            target_date = timezone.now().date()

        # 1. Calcul automatique des données de la journée
        donnees = calculer_donnees_journee_caissiere(caissiere_user, target_date=target_date)

        # 2. Fusionner avec d'éventuels ajouts manuels
        sorties = list(donnees['sorties_articles'])
        for item in self.validated_data.get('sorties_articles_ajouts', []):
            if item.get('nom'):
                sorties.append({
                    'nom': str(item.get('nom')),
                    'quantite': int(item.get('quantite', 1)),
                    'sous_total': float(item.get('sous_total', 0.0)),
                    'type': str(item.get('type', 'manuel')),
                })

        entrees = list(donnees['entrees_stock'])
        for item in self.validated_data.get('entrees_stock_ajouts', []):
            if item.get('nom'):
                entrees.append({
                    'nom': str(item.get('nom')),
                    'quantite_ajoutee': float(item.get('quantite_ajoutee', 0.0)),
                    'type_produit': str(item.get('type_produit', 'manuel')),
                    'date': str(item.get('date', 'manuel')),
                })

        # 3. Créer ou mettre à jour le rapport pour cette caissière à cette date
        rapport, created = RapportJournalierCaisse.objects.get_or_create(
            caissiere=caissiere_user,
            date=target_date,
            defaults={
                'heure_arrivee': self.validated_data.get('heure_arrivee', ''),
                'heure_depart': self.validated_data.get('heure_depart', ''),
                'recette_totale': Decimal(str(donnees['recette_totale'])),
                'total_depenses': Decimal(str(donnees['total_depenses'])),
                'reste_en_caisse': self.validated_data.get('reste_en_caisse', ''),
                'sorties_articles': sorties,
                'entrees_stock': entrees,
                'depenses': donnees['depenses'],
                'autres_donnees_manuelles': self.validated_data.get('autres_donnees_manuelles', {}),
                'actions_communication': self.validated_data.get('actions_communication', ''),
                'observations': self.validated_data.get('observations', ''),
            }
        )

        if not created:
            rapport.heure_arrivee = self.validated_data.get('heure_arrivee') or rapport.heure_arrivee
            rapport.heure_depart = self.validated_data.get('heure_depart') or rapport.heure_depart
            rapport.recette_totale = Decimal(str(donnees['recette_totale']))
            rapport.total_depenses = Decimal(str(donnees['total_depenses']))
            rapport.reste_en_caisse = self.validated_data.get('reste_en_caisse', rapport.reste_en_caisse)
            rapport.sorties_articles = sorties
            rapport.entrees_stock = entrees
            rapport.depenses = donnees['depenses']
            if self.validated_data.get('autres_donnees_manuelles'):
                rapport.autres_donnees_manuelles = self.validated_data.get('autres_donnees_manuelles')
            if self.validated_data.get('actions_communication'):
                rapport.actions_communication = self.validated_data.get('actions_communication')
            if self.validated_data.get('observations'):
                rapport.observations = self.validated_data.get('observations')

        # 4. Formater le texte WhatsApp
        rapport.texte_formate = formater_texte_whatsapp(rapport)
        rapport.save()

        # 5. Générer le fichier PDF
        generer_rapport_caisse_pdf(rapport)

        return rapport

