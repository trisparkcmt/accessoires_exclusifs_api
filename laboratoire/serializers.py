from rest_framework import serializers
from catalogue.models import Essence, Flacon, Accessoire, Parfum, Ingredient, LotEssence, DiffuseurParfum
from laboratoire.models import ParfumPersonnalise, ParfumPersonnaliseLigne, EssencePersonnalisee, EssencePersonnaliseeLigne
from django.db import transaction
from decimal import Decimal

class EssenceLabSerializer(serializers.ModelSerializer):
    class Meta:
        model = Essence
        fields = ['id', 'nom', 'code_reference', 'prix_par_ml']
        read_only_fields = fields

class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ['id', 'nom', 'description', 'prix_par_ml', 'stock_ml', 'seuil_alerte_ml']
        read_only_fields = fields

class FlaconLabSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flacon
        fields = ['id', 'nom', 'contenance_ml', 'prix_unitaire', 'image_principale']
        read_only_fields = fields

class AccessoireLabSerializer(serializers.ModelSerializer):
    class Meta:
        model = Accessoire
        fields = ['id', 'nom', 'prix_unitaire', 'image_principale']
        read_only_fields = fields

class ParfumLabSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parfum
        fields = ['id', 'nom', 'prix_unitaire', 'image_principale']
        read_only_fields = fields

class DiffuseurLabSerializer(serializers.ModelSerializer):
    prix_actuel = serializers.SerializerMethodField()

    class Meta:
        model = DiffuseurParfum
        fields = ['id', 'nom', 'prix_unitaire', 'prix_promotionnel', 'prix_actuel', 'image_principale']
        read_only_fields = fields

    def get_prix_actuel(self, obj):
        return str(obj.prix_promotionnel if obj.prix_promotionnel is not None else obj.prix_unitaire)

class EssencePersonnaliseeLigneSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    ingredient_detail = IngredientSerializer(source='ingredient', read_only=True)
    ingredient = serializers.PrimaryKeyRelatedField(queryset=Ingredient.objects.all())

    class Meta:
        model = EssencePersonnaliseeLigne
        fields = ['id', 'ingredient', 'ingredient_detail', 'quantite_ml', 'prix_ligne']
        read_only_fields = ['prix_ligne']

class EssencePersonnaliseeSerializer(serializers.ModelSerializer):
    lignes = EssencePersonnaliseeLigneSerializer(many=True)

    class Meta:
        model = EssencePersonnalisee
        fields = ['id', 'nom', 'prix_par_ml_calcule', 'lignes', 'date_creation']
        read_only_fields = ['prix_par_ml_calcule']

    def create(self, validated_data):
        lignes_data = validated_data.pop('lignes')
        request = self.context.get('request')
        
        if not request or not hasattr(request.user, 'client'):
            raise serializers.ValidationError("L'utilisateur doit avoir un profil client.")
            
        client = request.user.client

        with transaction.atomic():
            essence_perso = EssencePersonnalisee.objects.create(client=client, **validated_data)
            for ligne_data in lignes_data:
                EssencePersonnaliseeLigne.objects.create(essence_personnalisee=essence_perso, **ligne_data)
            
            essence_perso.recalculer_prix()
            
        return essence_perso

    def update(self, instance, validated_data):
        lignes_data = validated_data.pop('lignes', None)
        request = self.context.get('request')

        if not request or not hasattr(request.user, 'client'):
            raise serializers.ValidationError("L'utilisateur doit avoir un profil client.")

        with transaction.atomic():
            essence_perso = super().update(instance, validated_data)

            if lignes_data is not None:
                existing_lignes = {ligne.id: ligne for ligne in essence_perso.lignes.all()}
                sent_ids = []

                for ligne_data in lignes_data:
                    ligne_id = ligne_data.get('id')
                    if ligne_id:
                        if ligne_id not in existing_lignes:
                            raise serializers.ValidationError(f"Ligne d'essence personnalisée introuvable : {ligne_id}")
                        sent_ids.append(ligne_id)
                        ligne = existing_lignes[ligne_id]
                        
                        origine_ingredient = ligne.ingredient
                        nouvel_ingredient = ligne_data.get('ingredient', ligne.ingredient)
                        
                        ligne.ingredient = nouvel_ingredient
                        ligne.quantite_ml = ligne_data.get('quantite_ml', ligne.quantite_ml)
                        
                        if not ligne.prix_par_ml_snapshot or nouvel_ingredient != origine_ingredient:
                            ligne.prix_par_ml_snapshot = None  # Force le recalcul dans save()
                            
                        ligne.save()
                    else:
                        EssencePersonnaliseeLigne.objects.create(essence_personnalisee=essence_perso, **ligne_data)

                for ligne_id, ligne in existing_lignes.items():
                    if ligne_id not in sent_ids:
                        ligne.delete()

            essence_perso.recalculer_prix()

        return essence_perso


class LotOrEssenceRelatedField(serializers.PrimaryKeyRelatedField):
    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            try:
                from catalogue.models import Essence, LotEssence
                essence_obj = Essence.objects.get(pk=data)
                lot = LotEssence.objects.filter(essence=essence_obj, actif=True).first()
                if lot:
                    return lot
            except Exception:
                pass
            raise serializers.ValidationError(f"Invalid pk \"{data}\" - ni un lot d'essence ni une essence active valide.")


class ParfumPersonnaliseLigneSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    essence_detail = serializers.SerializerMethodField()
    
    essence = LotOrEssenceRelatedField(queryset=LotEssence.objects.all(), required=False, allow_null=True)
    essence_personnalisee = serializers.PrimaryKeyRelatedField(queryset=EssencePersonnalisee.objects.all(), required=False, allow_null=True)

    class Meta:
        model = ParfumPersonnaliseLigne
        fields = [
            'id', 'essence', 'essence_personnalisee', 
            'essence_detail', 
            'quantite_ml', 'prix_par_ml_snapshot', 'prix_ligne'
        ]
        read_only_fields = ['prix_par_ml_snapshot', 'prix_ligne']

    def get_essence_detail(self, obj):
        if obj.essence:
            return {
                'nom': obj.essence.essence.nom,
                'marque': obj.essence.essence.marque,
                'categorie': obj.essence.essence.categorie,
                'prix_par_ml': str(obj.essence.essence.prix_par_ml),
            }
        elif obj.essence_personnalisee:
            return {
                'nom': obj.essence_personnalisee.nom,
                'marque': "Création sur mesure",
                'categorie': "sur_mesure",
                'prix_par_ml': str(obj.essence_personnalisee.prix_par_ml_calcule),
            }
        return None

    def validate(self, data):
        essence = data.get('essence')
        essence_perso = data.get('essence_personnalisee')
        initial = getattr(self, 'initial_data', None)
        essence_provided = initial is not None and 'essence' in initial
        essence_perso_provided = initial is not None and 'essence_personnalisee' in initial
        
        # S'assurer qu'un seul des deux est fourni
        if essence and essence_perso:
            raise serializers.ValidationError("Vous ne pouvez pas fournir à la fois un lot d'essence du catalogue et une essence personnalisée pour la même ligne.")
        if not essence and not essence_perso:
            if self.instance and not essence_provided and not essence_perso_provided:
                return data
            raise serializers.ValidationError("Vous devez fournir soit un lot d'essence du catalogue, soit une essence personnalisée.")
            
        # S'assurer que l'essence personnalisée appartient au client connecté
        request = self.context.get('request')
        if essence_perso and request and hasattr(request.user, 'client'):
            if essence_perso.client != request.user.client:
                raise serializers.ValidationError({"essence_personnalisee": "L'essence personnalisée choisie doit vous appartenir."})
                
        return data


class ParfumPersonnaliseSerializer(serializers.ModelSerializer):
    lignes = ParfumPersonnaliseLigneSerializer(many=True)
    flacon_detail = FlaconLabSerializer(source='flacon', read_only=True)
    
    class Meta:
        model = ParfumPersonnalise
        fields = [
            'id', 'client', 'flacon', 'flacon_detail', 'nom', 'couleur', 'nom_sur_flacon', 'description', 
            'prix_essences', 'prix_flacon_snapshot', 
            'prix_total', 'statut', 'note_laboratoire', 'lignes', 'enregistre', 'date_creation'
        ]
        read_only_fields = ['client', 'prix_essences', 'prix_flacon_snapshot', 'prix_total', 'statut', 'note_laboratoire']

    def validate_volume_essences(self, flacon, lignes_data):
        if not flacon:
            raise serializers.ValidationError("Un flacon est requis.")
            
        contenance_flacon = Decimal(str(flacon.contenance_ml))
        volume_max_autorise = contenance_flacon * Decimal('0.45')
        
        volume_total_essences = sum(Decimal(str(ligne.get('quantite_ml', 0))) for ligne in lignes_data)
        
        if volume_total_essences > volume_max_autorise:
            raise serializers.ValidationError({
                "lignes": f"La quantité totale d'essences ({volume_total_essences}ml) dépasse les 45% autorisés pour ce flacon ({volume_max_autorise}ml max)."
            })

    def create(self, validated_data):
        lignes_data = validated_data.pop('lignes')
        request = self.context.get('request')
        
        if not request or not hasattr(request.user, 'client'):
            raise serializers.ValidationError("L'utilisateur doit avoir un profil client.")
            
        client = request.user.client
        flacon = validated_data.get('flacon')
        
        # Validation de la règle des 45%
        self.validate_volume_essences(flacon, lignes_data)
        
        validated_data['prix_flacon_snapshot'] = flacon.prix_unitaire if flacon else Decimal('0')
        validated_data['prix_essences'] = Decimal('0')
        validated_data['prix_total'] = Decimal('0')
        
        # Gérer l'absence de nom
        if not validated_data.get('nom'):
            validated_data['nom'] = "Parfum personnalisé"
            
        with transaction.atomic():
            parfum = ParfumPersonnalise.objects.create(client=client, **validated_data)
            
            # Si le nom n'est pas fourni, le nommer dynamiquement
            if validated_data.get('nom') == "Parfum personnalisé":
                parfum.nom = f"Parfum personnalisé #{parfum.id}"
                parfum.save(update_fields=['nom'])
                
            for ligne_data in lignes_data:
                ParfumPersonnaliseLigne.objects.create(parfum_personnalise=parfum, **ligne_data)
            
            parfum.recalculer_prix()
            
        return parfum

    def update(self, instance, validated_data):
        lignes_data = validated_data.pop('lignes', None)
        request = self.context.get('request')

        if not request or not hasattr(request.user, 'client'):
            raise serializers.ValidationError("L'utilisateur doit avoir un profil client.")

        if 'flacon' in validated_data:
            flacon = validated_data.get('flacon')
            validated_data['prix_flacon_snapshot'] = flacon.prix_unitaire if flacon else Decimal('0')

        with transaction.atomic():
            parfum = super().update(instance, validated_data)

            if lignes_data is not None:
                # Validation de la règle des 45% lors de la modification
                flacon = parfum.flacon
                self.validate_volume_essences(flacon, lignes_data)
                
                existing_lignes = {ligne.id: ligne for ligne in parfum.lignes.all()}
                sent_ids = []

                for ligne_data in lignes_data:
                    ligne_id = ligne_data.get('id')
                    if ligne_id:
                        if ligne_id not in existing_lignes:
                            raise serializers.ValidationError(f"Ligne de parfum personnalisé introuvable : {ligne_id}")
                        sent_ids.append(ligne_id)
                        ligne = existing_lignes[ligne_id]
                        
                        ligne.essence = ligne_data.get('essence', ligne.essence)
                        ligne.essence_personnalisee = ligne_data.get('essence_personnalisee', ligne.essence_personnalisee)
                        ligne.quantite_ml = ligne_data.get('quantite_ml', ligne.quantite_ml)
                        
                        # Réinitialiser le snapshot si l'essence change
                        ligne.prix_par_ml_snapshot = None 
                        ligne.save()
                    else:
                        ParfumPersonnaliseLigne.objects.create(parfum_personnalise=parfum, **ligne_data)

                for ligne_id, ligne in existing_lignes.items():
                    if ligne_id not in sent_ids:
                        ligne.delete()

            parfum.recalculer_prix()

        return parfum
