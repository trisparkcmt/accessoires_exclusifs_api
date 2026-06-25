from rest_framework import serializers
from django.core.validators import MinValueValidator
from django.db import transaction
from decimal import Decimal
from orders.models import (
    Panier, 
    PanierLigneParfum, 
    PanierLigneAccessoire, 
    PanierLigneParfumPerso, 
    PanierLigneProduitFiniEssence, 
    PanierLigneEssencePersonnalisee,
    Commande,
    CommandeLigneParfum,
    CommandeLigneAccessoire,
    CommandeProduitFiniEssence,
    CommandeLigneParfumPerso,
    CommandeLigneEssencePersonnalisee,
    Facture,
    CodePromoAdmin
)
from catalogue.models import Parfum, Accessoire, ProduitFiniEssence
from laboratoire.models import ParfumPersonnalise, EssencePersonnalisee, ParfumPersonnaliseLigne

# ============================================================
# READ SERIALIZERS (Affichage du panier)
# ============================================================

class LigneParfumReadSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='parfum.nom', read_only=True)
    contenance_ml = serializers.IntegerField(source='parfum.contenance_ml', read_only=True)
    image = serializers.SerializerMethodField()
    
    class Meta:
        model = PanierLigneParfum
        fields = ['id', 'parfum', 'nom', 'image', 'contenance_ml', 'quantite', 'prix_unitaire_snapshot', 'sous_total']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.parfum.image_principale:
            return request.build_absolute_uri(obj.parfum.image_principale.url) if request else obj.parfum.image_principale.url
        return None


class LigneAccessoireReadSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='accessoire.nom', read_only=True)
    image = serializers.SerializerMethodField()
    
    class Meta:
        model = PanierLigneAccessoire
        fields = ['id', 'accessoire', 'nom', 'image', 'quantite', 'prix_unitaire_snapshot', 'sous_total']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.accessoire.image_principale:
            return request.build_absolute_uri(obj.accessoire.image_principale.url) if request else obj.accessoire.image_principale.url
        return None


class LigneProduitFiniEssenceReadSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='produit_fini_essence.essence.nom', read_only=True)
    marque = serializers.CharField(source='produit_fini_essence.essence.marque', read_only=True)
    taille_ml = serializers.IntegerField(source='produit_fini_essence.taille_ml', read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = PanierLigneProduitFiniEssence
        fields = ['id', 'produit_fini_essence', 'nom', 'marque', 'image', 'taille_ml', 'quantite', 'prix_unitaire_snapshot', 'sous_total']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.produit_fini_essence.image_principale:
            return request.build_absolute_uri(obj.produit_fini_essence.image_principale.url) if request else obj.produit_fini_essence.image_principale.url
        return None


class LigneParfumPersoReadSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='parfum_personnalise.nom', read_only=True)

    class Meta:
        model = PanierLigneParfumPerso
        fields = ['id', 'parfum_personnalise', 'nom', 'quantite', 'prix_calcule', 'sous_total', 'note_client']


class LigneEssencePersonnaliseeReadSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='essence_personnalisee.nom', read_only=True)

    class Meta:
        model = PanierLigneEssencePersonnalisee
        fields = ['id', 'essence_personnalisee', 'nom', 'quantite', 'prix_calcule', 'sous_total']


class PanierSerializer(serializers.ModelSerializer):
    lignes_parfums = LigneParfumReadSerializer(many=True, read_only=True)
    lignes_accessoires = LigneAccessoireReadSerializer(many=True, read_only=True)
    lignes_produit_fini_essence = LigneProduitFiniEssenceReadSerializer(many=True, read_only=True)
    lignes_parfums_perso = LigneParfumReadSerializer(many=True, read_only=True) # Wait, is it LigneParfumReadSerializer? Typo check.
    # Ah, lines_parfums_perso should map to LigneParfumPersoReadSerializer. Correcting below.
    lignes_parfums_perso = LigneParfumPersoReadSerializer(many=True, read_only=True)
    lignes_essence_personnalisee = LigneEssencePersonnaliseeReadSerializer(many=True, read_only=True)

    class Meta:
        model = Panier
        fields = [
            'id', 'client', 'code_promo_applique', 'remise_montant', 
            'remise_pourcentage', 'sous_total', 'frais_livraison', 'total', 
            'statut', 'lignes_parfums', 'lignes_accessoires', 
            'lignes_produit_fini_essence', 'lignes_parfums_perso', 
            'lignes_essence_personnalisee', 'date_creation', 'date_modification'
        ]


# ============================================================
# WRITE SERIALIZERS (Validation des entrées)
# ============================================================

class AjouterParfumSerializer(serializers.Serializer):
    parfum_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1, default=1)
    panier_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        try:
            parfum = Parfum.objects.get(id=data['parfum_id'])
        except Parfum.DoesNotExist:
            raise serializers.ValidationError({"parfum_id": "Parfum introuvable."})
        
        if not parfum.actif:
            raise serializers.ValidationError({"parfum_id": "Ce parfum n'est pas actif."})
        
        if parfum.stock_quantite < data['quantite']:
            raise serializers.ValidationError({"quantite": f"Stock insuffisant. Seulement {parfum.stock_quantite} disponibles."})
        
        data['parfum_obj'] = parfum
        return data


class AjouterAccessoireSerializer(serializers.Serializer):
    accessoire_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1, default=1)
    panier_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        try:
            accessoire = Accessoire.objects.get(id=data['accessoire_id'])
        except Accessoire.DoesNotExist:
            raise serializers.ValidationError({"accessoire_id": "Accessoire introuvable."})
        
        if not accessoire.actif:
            raise serializers.ValidationError({"accessoire_id": "Cet accessoire n'est pas actif."})
        
        if accessoire.stock_quantite < data['quantite']:
            raise serializers.ValidationError({"quantite": f"Stock insuffisant. Seulement {accessoire.stock_quantite} disponibles."})
        
        data['accessoire_obj'] = accessoire
        return data


class AjouterProduitFiniEssenceSerializer(serializers.Serializer):
    produit_fini_essence_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1, default=1)
    panier_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        try:
            produit = ProduitFiniEssence.objects.get(id=data['produit_fini_essence_id'])
        except ProduitFiniEssence.DoesNotExist:
            raise serializers.ValidationError({"produit_fini_essence_id": "Produit fini essence introuvable."})
        
        if not produit.actif:
            raise serializers.ValidationError({"produit_fini_essence_id": "Ce produit n'est pas actif."})
        
        if produit.stock_disponible < data['quantite']:
            raise serializers.ValidationError({"quantite": f"Stock insuffisant. Seulement {produit.stock_disponible} disponibles."})
        
        data['produit_fini_essence_obj'] = produit
        return data


class AjouterEssencePersonnaliseeSerializer(serializers.Serializer):
    essence_personnalisee_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1, default=1)
    panier_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError({"detail": "Vous devez être connecté pour ajouter une essence personnalisée."})
        
        client = getattr(request.user, 'client', None)
        if not client:
            raise serializers.ValidationError({"detail": "Profil client introuvable."})

        try:
            essence_perso = EssencePersonnalisee.objects.get(
                id=data['essence_personnalisee_id'],
                client=client
            )
        except EssencePersonnalisee.DoesNotExist:
            raise serializers.ValidationError({"essence_personnalisee_id": "Essence personnalisée introuvable ou ne vous appartient pas."})
        
        # Vérification et recalcul du prix
        essence_perso.recalculer_prix()
        total_prix = sum(ligne.prix_ligne for ligne in essence_perso.lignes.all())
        if total_prix <= 0:
            raise serializers.ValidationError({"essence_personnalisee_id": "Le prix de cette essence est invalide."})
        
        data['essence_perso_obj'] = essence_perso
        data['total_prix'] = total_prix
        return data



class AppliquerCodePromoSerializer(serializers.Serializer):
    code_promo = serializers.CharField(max_length=50)
    panier_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        code = data['code_promo'].strip()
        
        # 1. Chercher si c'est un prestataire actif
        try:
            from utilisateur.models import Prestataire
            prestataire = Prestataire.objects.get(code_promo=code, statut='actif')
            data['prestataire_obj'] = prestataire
            return data
        except Prestataire.DoesNotExist:
            pass
            
        # 2. Chercher si c'est un code promo admin
        try:
            promo_admin = CodePromoAdmin.objects.get(code__iexact=code, est_actif=True)
        except CodePromoAdmin.DoesNotExist:
            raise serializers.ValidationError({"code_promo": "Code promotionnel invalide ou inactif."})
            
        # Pour un code promo admin, l'utilisateur doit être connecté et avoir un profil client
        request = self.context.get('request')
        user = request.user if request else None
        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"code_promo": "Vous devez être connecté pour utiliser ce code promo."})
            
        try:
            client = user.client
        except AttributeError:
            raise serializers.ValidationError({"code_promo": "Profil client introuvable."})
            
        # Vérifier si le client est dans la liste autorisée
        if not promo_admin.clients_autorises.filter(pk=client.pk).exists():
            raise serializers.ValidationError({"code_promo": "Vous n'êtes pas autorisé à utiliser ce code promo."})
            
        # Vérifier l'usage unique
        if Commande.objects.filter(client=client, code_promo_utilise__iexact=code).exclude(statut__in=['annulée', 'remboursée']).exists():
            raise serializers.ValidationError({"code_promo": "Vous avez déjà utilisé ce code promo."})
            
        data['promo_admin_obj'] = promo_admin
        return data

  
class CodePromoAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodePromoAdmin
        fields = ['id', 'code', 'reduction_pourcentage', 'est_actif', 'clients_autorises', 'date_creation', 'date_modification']


class CommandeLigneParfumSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommandeLigneParfum
        fields = ['id', 'parfum', 'nom_snapshot', 'quantite', 'prix_unitaire_snapshot', 'remise_ligne', 'sous_total']


class CommandeLigneAccessoireSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommandeLigneAccessoire
        fields = ['id', 'accessoire', 'nom_snapshot', 'quantite', 'prix_unitaire_snapshot', 'remise_ligne', 'sous_total']


class CommandeProduitFiniEssenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommandeProduitFiniEssence
        fields = ['id', 'produit_fini_essence', 'nom_snapshot', 'quantite', 'prix_unitaire_snapshot', 'remise_ligne', 'sous_total']


class CommandeLigneParfumPersoSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='parfum_personnalise.nom', read_only=True)

    class Meta:
        model = CommandeLigneParfumPerso
        fields = ['id', 'parfum_personnalise', 'nom', 'quantite', 'prix_snapshot', 'sous_total', 'statut_laboratoire', 'note_laboratoire']


class CommandeLigneEssencePersonnaliseeSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source='essence_personnalise.nom', read_only=True)

    class Meta:
        model = CommandeLigneEssencePersonnalisee
        fields = ['id', 'essence_personnalise', 'nom', 'quantite', 'prix_snapshot', 'sous_total', 'statut_laboratoire', 'note_laboratoire']


class FactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facture
        fields = ['numero_facture', 'date_emission', 'envoye_par_email', 'fichier_pdf']


class CommandeSerializer(serializers.ModelSerializer):
    lignes_parfums = CommandeLigneParfumSerializer(many=True, read_only=True)
    lignes_accessoires = CommandeLigneAccessoireSerializer(many=True, read_only=True)
    lignes_produit_fini_essence = CommandeProduitFiniEssenceSerializer(many=True, read_only=True)
    lignes_parfums_perso = CommandeLigneParfumPersoSerializer(many=True, read_only=True)
    lignes_essence_personnalisee = CommandeLigneEssencePersonnaliseeSerializer(many=True, read_only=True)
    facture = FactureSerializer(read_only=True)
    
    client_email = serializers.CharField(source='client.user.email', read_only=True)
    livreur_nom = serializers.SerializerMethodField()
    prestataire_code = serializers.CharField(source='prestataire.code_promo', read_only=True)
    
    class Meta:
        model = Commande
        fields = [
            'id', 'numero_commande', 'client', 'client_email', 'prestataire', 'prestataire_code',
            'livreur', 'livreur_nom', 'statut', 'statut_livraison', 'statut_paiement',
            'sous_total', 'remise_code_promo', 'code_promo_utilise', 'frais_livraison',
            'total_ttc', 'commission_montant', 'commission_statut',
            'livraison_nom_complet', 'livraison_quartier', 'livraison_ville', 'livraison_telephone',
            'date_livraison_estimee', 'date_livraison_reelle', 'note_client', 'note_interne',
            'motif_echec_livraison', 'date_creation', 'date_modification',
            'lignes_parfums', 'lignes_accessoires', 'lignes_produit_fini_essence',
            'lignes_parfums_perso', 'lignes_essence_personnalisee', 'facture'
        ]

    def get_livreur_nom(self, obj):
        if obj.livreur:
            return f"{obj.livreur.nom} {obj.livreur.prenom}"
        return None


class CompositionDirecteLigneSerializer(serializers.Serializer):
    lot_essence_id = serializers.IntegerField(required=True)
    quantite_ml = serializers.DecimalField(max_digits=8, decimal_places=3, min_value=Decimal('0.1'))


class CommanderCompositionDirecteSerializer(serializers.Serializer):
    panier_id = serializers.IntegerField(required=False, allow_null=True)
    quantite = serializers.IntegerField(required=False, default=1, min_value=1)
    nom = serializers.CharField(required=False, allow_blank=True, max_length=200, default='')
    note_client = serializers.CharField(required=False, allow_blank=True, default='')
    flacon_id = serializers.IntegerField(required=True)
    lignes = CompositionDirecteLigneSerializer(many=True, required=True)

    def validate(self, data):
        flacon_id = data.get('flacon_id')
        quantite = data.get('quantite')
        lignes_data = data.get('lignes')
        
        # 1. Valider Flacon
        from catalogue.models import Flacon
        try:
            flacon = Flacon.objects.get(id=flacon_id, actif=True)
        except Flacon.DoesNotExist:
            raise serializers.ValidationError({"flacon_id": "Le flacon sélectionné n'existe pas ou n'est pas actif."})
            
        if flacon.stock_quantite < quantite:
            raise serializers.ValidationError({"flacon_id": f"Stock de flacon insuffisant. Disponible : {flacon.stock_quantite}."})
            
        # 2. Valider les lots d'essences et les stocks
        from catalogue.models import LotEssence
        lot_ids = [ligne['lot_essence_id'] for ligne in lignes_data]
        lots = LotEssence.objects.filter(id__in=lot_ids, actif=True).select_related('essence')
        lots_dict = {lot.id: lot for lot in lots}
        
        errors = {}
        total_volume_essences = Decimal('0')
        validated_lignes = []
        
        for idx, ligne in enumerate(lignes_data):
            l_id = ligne['lot_essence_id']
            qty = Decimal(str(ligne['quantite_ml']))
            
            if l_id not in lots_dict:
                errors[f'lignes[{idx}].lot_essence_id'] = "Ce lot d'essence n'existe pas ou n'est pas actif."
                continue
                
            lot = lots_dict[l_id]
            if lot.stock_ml < qty:
                errors[f'lignes[{idx}].quantite_ml'] = f"Stock d'essence insuffisant pour {lot.essence.nom}. Disponible : {lot.stock_ml}ml."
                continue
                
            total_volume_essences += qty
            validated_lignes.append((lot, qty))
            
        if errors:
            raise serializers.ValidationError(errors)
            
        # 3. Règle des 45%
        contenance_flacon = Decimal(str(flacon.contenance_ml))
        volume_max_autorise = contenance_flacon * Decimal('0.45')
        if total_volume_essences > volume_max_autorise:
            raise serializers.ValidationError({
                "lignes": f"Le volume total d'essences ({total_volume_essences} ml) dépasse la limite autorisée de 45% pour le flacon sélectionné ({volume_max_autorise} ml max)."
            })
            
        data['flacon_obj'] = flacon
        data['validated_lignes'] = validated_lignes
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        
        flacon = validated_data['flacon_obj']
        nom = validated_data.get('nom') or f"Composition LIA"
        note_client = validated_data.get('note_client', '')
        
        client = None
        if user and user.is_authenticated:
            try:
                client = user.client
            except AttributeError:
                pass
                
        with transaction.atomic():
            parfum_perso = ParfumPersonnalise.objects.create(
                client=client,
                flacon=flacon,
                nom=nom,
                description=note_client,
                prix_essences=Decimal('0'),
                prix_flacon_snapshot=flacon.prix_unitaire,
                prix_total=flacon.prix_unitaire,
                statut='validé',
                enregistre=False
            )
            
            # Ajouter les lignes
            for lot, quantite_ml in validated_data['validated_lignes']:
                ParfumPersonnaliseLigne.objects.create(
                    parfum_personnalise=parfum_perso,
                    essence=lot,
                    quantite_ml=quantite_ml,
                    prix_par_ml_snapshot=lot.essence.prix_par_ml,
                    prix_ligne=lot.essence.prix_par_ml * quantite_ml
                )
            
            # Recalculer
            parfum_perso.recalculer_prix()
            
        validated_data['parfum_perso_obj'] = parfum_perso
        return parfum_perso


class PasserCommandeSerializer(serializers.Serializer):
    panier_id = serializers.IntegerField(required=False, allow_null=True)
    livraison_nom_complet = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    livraison_quartier = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    livraison_ville = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    livraison_telephone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    note_client = serializers.CharField(required=False, allow_blank=True, default='')
    client_telephone = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        request = self.context.get('request')
        panier_id = data.get('panier_id')
        
        # Récupérer le panier actif
        from orders.utils import get_or_create_panier
        panier = get_or_create_panier(request, panier_id)
        
        # Vérifier si le panier est vide
        has_items = (
            panier.lignes_parfums.exists() or
            panier.lignes_accessoires.exists() or
            panier.lignes_produit_fini_essence.exists() or
            panier.lignes_parfums_perso.exists() or
            panier.lignes_essence_personnalisee.exists()
        )
        if not has_items:
            raise serializers.ValidationError({"detail": "Le panier est vide."})
        
        user = request.user
        is_auth = user and user.is_authenticated
        
        # Auto-populate livraison_nom_complet from user if not provided
        if not data.get('livraison_nom_complet', '').strip():
            if is_auth:
                full_name = f"{user.first_name} {user.last_name}".strip()
                if full_name:
                    data['livraison_nom_complet'] = full_name
                else:
                    raise serializers.ValidationError({"detail": "Veuillez fournir un nom complet ou complétez votre profil."})
            else:
                raise serializers.ValidationError({"detail": "Veuillez fournir un nom complet pour la livraison."})
        
        # Auto-populate livraison_telephone from user if not provided
        if not data.get('livraison_telephone', '').strip():
            if is_auth:
                if getattr(user, 'telephone', None):
                    data['livraison_telephone'] = user.telephone
                else:
                    raise serializers.ValidationError({"detail": "Veuillez fournir un numéro de téléphone ou complétez votre profil."})
            else:
                raise serializers.ValidationError({"detail": "Veuillez fournir un numéro de téléphone pour la livraison."})
            
        data['panier_obj'] = panier
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        panier = validated_data['panier_obj']
        
        user = request.user
        client = None
        
        if user and user.is_authenticated:
            try:
                client = user.client
            except AttributeError:
                raise serializers.ValidationError({"detail": "Profil client introuvable."})
        else:
            client_telephone = validated_data.get('client_telephone', '').strip()
            if client_telephone:
                from utilisateur.models import Client
                client = Client.objects.filter(user__telephone=client_telephone).first()
            
        with transaction.atomic():
            # Créer la commande
            commande = Commande.objects.create(
                client=client,
                prestataire=panier.prestataire,
                panier=panier,
                code_promo_utilise=panier.code_promo_applique,
                frais_livraison=panier.frais_livraison,
                sous_total=panier.sous_total,
                remise_code_promo=panier.remise_montant,
                total_ttc=panier.total,
                livraison_nom_complet=validated_data['livraison_nom_complet'],
                livraison_quartier=validated_data.get('livraison_quartier', ''),
                livraison_ville=validated_data.get('livraison_ville', ''),
                livraison_telephone=validated_data['livraison_telephone'],
                note_client=validated_data.get('note_client', ''),
                statut='en_attente',
                statut_livraison='en_attente_affectation',
                statut_paiement='en_attente',
                commission_statut='non_versée'
            )
            
            # Copier les lignes de parfum
            for ligne in panier.lignes_parfums.all():
                CommandeLigneParfum.objects.create(
                    commande=commande,
                    parfum=ligne.parfum,
                    nom_snapshot=ligne.parfum.nom,
                    quantite=ligne.quantite,
                    prix_unitaire_snapshot=ligne.prix_unitaire_snapshot,
                    remise_ligne=Decimal('0'),
                    sous_total=ligne.sous_total
                )
                
            # Copier les lignes d'accessoires
            for ligne in panier.lignes_accessoires.all():
                CommandeLigneAccessoire.objects.create(
                    commande=commande,
                    accessoire=ligne.accessoire,
                    nom_snapshot=ligne.accessoire.nom,
                    quantite=ligne.quantite,
                    prix_unitaire_snapshot=ligne.prix_unitaire_snapshot,
                    remise_ligne=Decimal('0'),
                    sous_total=ligne.sous_total
                )
                
            # Copier les lignes de produits finis d'essences
            for ligne in panier.lignes_produit_fini_essence.all():
                CommandeProduitFiniEssence.objects.create(
                    commande=commande,
                    produit_fini_essence=ligne.produit_fini_essence,
                    nom_snapshot=ligne.produit_fini_essence.essence.nom,
                    quantite=ligne.quantite,
                    prix_unitaire_snapshot=ligne.prix_unitaire_snapshot,
                    remise_ligne=Decimal('0'),
                    sous_total=ligne.sous_total
                )
                
            # Copier les lignes de parfums personnalisés
            for ligne in panier.lignes_parfums_perso.all():
                CommandeLigneParfumPerso.objects.create(
                    commande=commande,
                    parfum_personnalise=ligne.parfum_personnalise,
                    quantite=ligne.quantite,
                    prix_snapshot=ligne.prix_calcule,
                    sous_total=ligne.sous_total,
                    statut_laboratoire='en_attente'
                )
                
            # Copier les lignes d'essences personnalisées
            for ligne in panier.lignes_essence_personnalisee.all():
                CommandeLigneEssencePersonnalisee.objects.create(
                    commande=commande,
                    essence_personnalise=ligne.essence_personnalisee,
                    quantite=ligne.quantite,
                    prix_snapshot=ligne.prix_calcule,
                    sous_total=ligne.sous_total,
                    statut_laboratoire='en_attente'
                )
                
            # Forcer le premier calcul exact
            commande.recalculer_commande()
            commande.save()
            
            # Convertir le panier
            panier.statut = 'converti'
            panier.save()
            
            return commande

