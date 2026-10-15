from rest_framework import serializers
from django.conf import settings
from django.db import transaction
from django.contrib.auth import authenticate
from django.urls import reverse
from dj_rest_auth.serializers import LoginSerializer, PasswordChangeSerializer
from dj_rest_auth.registration.serializers import RegisterSerializer
from drf_spectacular.utils import extend_schema_serializer
from .models import User, Client, Prestataire, CommissionLog, Notification, PayoutTransaction, Livreur, Serveuse, Boutique, Depense
from catalogue.models import Favori
from laboratoire.models import ParfumPersonnalise, ParfumPersonnaliseLigne
from orders.models import (
    Commande,
    CommandeLigneAccessoire,
    CommandeLigneParfum,
    CommandeLigneParfumPerso,
    CommandeProduitFiniEssence,
    CommandeLigneEssencePersonnalisee,
    CommandeLigneDiffuseurParfum,
)
from orders.serializers import ParfumPersoDetailSerializer


@extend_schema_serializer(
    exclude_fields=['username'],
)
class EmailOrTelephoneLoginSerializer(LoginSerializer):
    """Connexion avec email ou téléphone sans changer l'inscription."""
    email = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On retire le champ username par défaut pour nettoyer l'interface Swagger et l'API
        self.fields.pop('username', None)

    def validate(self, attrs):
        identifier = (
            attrs.get('email')
            or attrs.get('telephone')
        )
        password = attrs.get('password')

        if not identifier or not password:
            raise serializers.ValidationError(
                'Veuillez fournir un email ou un téléphone avec le mot de passe.'
            )

        user = self._get_user(identifier)
        if not user:
            raise serializers.ValidationError('Identifiants invalides.')

        authenticated_user = authenticate(
            self.context['request'],
            email=user.email,
            password=password
        )
        if not authenticated_user:
            # Si le mot de passe est correct mais que l'utilisateur est inactif car non vérifié
            if user.check_password(password) and not user.is_active:
                from allauth.account.models import EmailAddress
                email_address = EmailAddress.objects.filter(user=user, email=user.email).first()
                if email_address and not email_address.verified:
                    try:
                        email_address.send_confirmation(self.context.get('request'), signup=False)
                    except Exception:
                        pass
                    raise serializers.ValidationError({
                        "non_field_errors": [
                            "Votre compte n'est pas encore activé. Un email de validation a été envoyé automatiquement."
                        ],
                        "email_non_verifie": True,
                        "email": user.email
                    })
                else:
                    raise serializers.ValidationError("Ce compte est désactivé par un administrateur.")
            raise serializers.ValidationError('Identifiants invalides.')

        self.validate_auth_user_status(authenticated_user)
        if 'dj_rest_auth.registration' in settings.INSTALLED_APPS:
            from allauth.account.models import EmailAddress
            email_address = EmailAddress.objects.filter(user=authenticated_user, email=authenticated_user.email).first()
            if email_address and not email_address.verified:
                try:
                    email_address.send_confirmation(self.context.get('request'), signup=False)
                except Exception:
                    pass
                raise serializers.ValidationError({
                    "non_field_errors": [
                        "Votre adresse email n'est pas vérifiée. Un email de validation a été envoyé automatiquement."
                    ],
                    "email_non_verifie": True,
                    "email": authenticated_user.email
                })

        attrs['user'] = authenticated_user
        return attrs

    def _get_user(self, identifier):
        identifier = identifier.strip()
        lookup = {'email__iexact': identifier} if '@' in identifier else {'telephone': identifier}
        try:
            return User.objects.get(**lookup)
        except User.DoesNotExist:
            return None

@extend_schema_serializer(
    exclude_fields=['username', 'password1', 'password2'],
)
class CustomRegisterSerializer(RegisterSerializer):
    """
    Sérialiseur d'inscription personnalisé :
    - Rend le téléphone, prénom et nom optionnels.
    - Utilise les noms de champs définis dans ApiDoc.md.
    - Préserve la validation de robustesse du mot de passe de Django.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On retire les champs par défaut de dj-rest-auth pour qu'ils ne polluent pas Swagger
        # ni l'interface API, car on utilise nos propres noms (password, password_confirm)
        self.fields.pop('username', None)
        self.fields.pop('password1', None)
        self.fields.pop('password2', None)

    def validate_telephone(self, value):
        if value:
            value = value.strip()
            if not value:
                return None
            if User.objects.filter(telephone=value).exists():
                raise serializers.ValidationError("Ce numéro de téléphone est déjà utilisé.")
            return value
        return None

    def validate(self, attrs):
        # Validation manuelle de la correspondance des mots de passe
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({"password_confirm": "Les mots de passe ne correspondent pas."})
        
        # SOLUTION : On génère le username ici à partir de l'email.
        # Cela évite l'erreur "Enter a valid username" car on fournit une valeur valide (ex: 'djouffogregoire')
        # avant que les validateurs de Django ne s'exécutent.
        if not attrs.get('username') and attrs.get('email'):
            attrs['username'] = attrs.get('email').split('@')[0]

        # On mappe les champs pour que le validateur interne d'allauth (robustesse) fonctionne
        attrs['password1'] = attrs.get('password')
        attrs['password2'] = attrs.get('password_confirm')
        
        return super().validate(attrs)

    def get_cleaned_data(self):
        # Prépare les données nettoyées pour la création de l'utilisateur
        cleaned_data = super().get_cleaned_data()
        cleaned_data.update({
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
            'telephone': self.validated_data.get('telephone', ''),
            # On s'assure que password1/2 sont transmis
            'password1': self.validated_data.get('password'),
            'password2': self.validated_data.get('password_confirm'),
        })
        return cleaned_data

    def custom_signup(self, request, user):
        # Enregistre les données supplémentaires sur l'objet User
        user.first_name = self.validated_data.get('first_name', '').strip()
        user.last_name = self.validated_data.get('last_name', '').strip()
        telephone = self.validated_data.get('telephone')
        user.telephone = telephone if telephone else None
        
        from django.conf import settings
        if getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional') == 'mandatory':
            user.is_active = False  # Par sécurité
            
        user.save()

    @transaction.atomic
    def save(self, request):
        return super().save(request)

@extend_schema_serializer(
    exclude_fields=['new_password1', 'new_password2'],
)
class CustomPasswordChangeSerializer(PasswordChangeSerializer):
    """
    Sérialiseur pour changer le mot de passe, aligné sur ApiDoc.md.
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    new_password_confirm = serializers.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('new_password1', None)
        self.fields.pop('new_password2', None)

    def validate(self, attrs):
        if attrs.get('new_password') != attrs.get('new_password_confirm'):
            raise serializers.ValidationError(
                {"new_password_confirm": "Les nouveaux mots de passe ne correspondent pas."}
            )
        
        # On mappe vers les noms attendus par Allauth en interne
        attrs['new_password1'] = attrs.get('new_password')
        attrs['new_password2'] = attrs.get('new_password_confirm')
        
        # On vérifie la robustesse via le validateur standard
        from django.contrib.auth.password_validation import validate_password
        validate_password(attrs.get('new_password'), self.context['request'].user)
        
        return attrs

class CommissionLogSerializer(serializers.ModelSerializer):
    """Serializer pour l'historique des gains"""
    class Meta:
        model = CommissionLog
        fields = ['id', 'type_operation', 'montant', 'reference_commande', 'date_operation', 'description']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'title', 'message', 'url', 'is_read', 'metadata', 'created_at']

class PrestataireDashboardSerializer(serializers.ModelSerializer):
    """Serializer pour le résumé du dashboard prestataire"""
    total_gains = serializers.SerializerMethodField()
    total_retraits = serializers.SerializerMethodField()
    solde_bloque = serializers.SerializerMethodField()
    payouts_recents = serializers.SerializerMethodField()
    historique_recent = serializers.SerializerMethodField()
    
    class Meta:
        model = Prestataire
        fields = [
            'id', 'photo', 'solde_commission', 'taux_commission', 'reduction_client_pourcentage', 
            'code_promo', 'statut', 'total_gains', 'total_retraits', 'solde_bloque', 
            'payouts_recents', 'historique_recent'
        ]

    def get_total_gains(self, obj):
        from django.db.models import Sum
        res = obj.historique_commissions.filter(montant__gt=0).aggregate(Sum('montant'))['montant__sum']
        val = res or Decimal('0.00')
        return f"{val:.2f}"

    def get_total_retraits(self, obj):
        from django.db.models import Sum
        res = obj.historique_commissions.filter(montant__lt=0).aggregate(Sum('montant'))['montant__sum']
        val = abs(res) if res else Decimal('0.00')
        return f"{val:.2f}"

    def get_solde_bloque(self, obj):
        from django.db.models import Sum
        res = obj.payouts.filter(statut='en_cours').aggregate(Sum('montant'))['montant__sum']
        val = res or Decimal('0.00')
        return f"{val:.2f}"

    def get_payouts_recents(self, obj):
        recent = obj.payouts.all()[:5]
        return PayoutTransactionSerializer(recent, many=True).data

    def get_historique_recent(self, obj):
        recent = obj.historique_commissions.all()[:10]
        return CommissionLogSerializer(recent, many=True).data



class PrestataireApplicationSerializer(serializers.ModelSerializer):
    """Serializer pour la demande initiale de l'utilisateur (photo obligatoire)"""
    photo = serializers.ImageField(required=True)

    class Meta:
        model = Prestataire
        fields = ['photo']

class PrestataireValidationSerializer(serializers.ModelSerializer):
    """Serializer pour la validation par l'administrateur"""
    class Meta:
        model = Prestataire
        fields = ['taux_commission', 'reduction_client_pourcentage'] # L'admin doit obligatoirement remplir le taux et la réduction client
        extra_kwargs = {
            'taux_commission': {'required': True},
            'reduction_client_pourcentage': {'required': True}
        }

class UserSerializer(serializers.ModelSerializer):
    """Serializer pour les données de base de l'utilisateur"""
    roles = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'telephone', 'first_name', 'last_name', 'roles', 'photo']
        read_only_fields = ['roles', 'photo']
        extra_kwargs = {
            'email': {'read_only': True},
        }

    def get_roles(self, obj):
        """
        Retourne la liste de tous les rôles actifs de l'utilisateur.
        Un même utilisateur peut être à la fois client, prestataire, livreur et/ou serveuse.
        Le frontend utilise cette liste pour décider quel(s) dashboard(s) afficher.
        """
        roles = []
        if obj.is_superuser or obj.is_staff:
            roles.append('superadmin')
        # Tout utilisateur ayant un profil Client est au moins 'client'
        if hasattr(obj, 'client'):
            roles.append('client')
            client = obj.client
            if hasattr(client, 'prestataire'):
                roles.append('prestataire')
            if hasattr(client, 'livreur'):
                roles.append('livreur')
            if hasattr(client, 'serveuse'):
                roles.append('serveuse')
            if hasattr(client, 'boutique'):
                roles.append('boutique')
        return roles

    def get_photo(self, obj):
        if hasattr(obj, 'client'):
            client = obj.client
            for role_attr in ['serveuse', 'livreur', 'prestataire', 'boutique']:
                if hasattr(client, role_attr):
                    profile = getattr(client, role_attr)
                    if profile and profile.photo:
                        request = self.context.get('request')
                        if request:
                            return request.build_absolute_uri(profile.photo.url)
                        return profile.photo.url
        return None


class MeUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier le profil sans gérer le changement d'email."""
    class Meta:
        model = User
        fields = ['telephone', 'first_name', 'last_name']


class ClientSerializer(serializers.ModelSerializer):
    """Serializer pour le profil Client complet — utilisé dans le leaderboard admin."""
    user_details = UserSerializer(source='user', read_only=True)
    # Ces champs sont optionnellement injectés par annotation dans admin_best_clients
    total_spent = serializers.SerializerMethodField()
    total_paid_orders = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ['id', 'user_details', 'date_naissance', 'genre', 'points_fidelite', 'total_spent', 'total_paid_orders']

    def get_total_spent(self, obj):
        # Récupère la valeur annotée si disponible, sinon None
        val = getattr(obj, 'total_spent', None)
        return float(val) if val is not None else 0.0

    def get_total_paid_orders(self, obj):
        return getattr(obj, 'total_paid_orders', 0) or 0



class MeClientSerializer(serializers.ModelSerializer):
    """Données client rattachées au profil connecté, incluant les statistiques de fidélité."""
    total_depenses = serializers.SerializerMethodField()
    reste_pour_prochain_point = serializers.SerializerMethodField()
    progression_pourcentage = serializers.SerializerMethodField()
    rang_classement = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'date_naissance', 'genre',
            'total_depenses', 'points_fidelite',
            'reste_pour_prochain_point', 'progression_pourcentage',
            'rang_classement', 'date_creation',
        ]

    def _get_total_depenses(self, obj):
        from django.db.models import Sum, Q
        total = obj.commandes.filter(
            statut_paiement='payé'
        ).aggregate(
            total=Sum('total_ttc')
        )['total']
        return float(total or 0)

    def get_total_depenses(self, obj):
        return round(self._get_total_depenses(obj), 2)

    def get_reste_pour_prochain_point(self, obj):
        total = self._get_total_depenses(obj)
        reste = 25000 - (total % 25000)
        # Si total est un multiple parfait de 25000 (ex: 50000), le reste est 0, pas 25000
        return round(reste if (total % 25000) != 0 else 0, 2)

    def get_progression_pourcentage(self, obj):
        total = self._get_total_depenses(obj)
        return round(((total % 25000) / 25000) * 100, 1)

    def get_rang_classement(self, obj):
        """Position du client dans le classement général par points."""
        return Client.objects.filter(
            points_fidelite__gt=obj.points_fidelite
        ).count() + 1



class MeFavoriSerializer(serializers.ModelSerializer):
    type_produit = serializers.SerializerMethodField()
    produit_id = serializers.SerializerMethodField()
    id_produit = serializers.SerializerMethodField()
    nom_produit = serializers.SerializerMethodField()
    prix_produit = serializers.SerializerMethodField()
    image_produit = serializers.SerializerMethodField()
    slug_produit = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    class Meta:
        model = Favori
        fields = [
            'id', 'type_produit', 'produit_id', 'id_produit', 'nom_produit',
            'prix_produit', 'image_produit', 'slug_produit', 'detail_url', 'date_ajout'
        ]

    def get_type_produit(self, obj):
        if obj.parfum_id:
            return 'parfum'
        elif obj.accessoire_id:
            return 'accessoire'
        elif obj.produit_fini_essence_id:
            return 'produit_fini_essence'
        return 'inconnu'

    def get_produit_id(self, obj):
        return obj.parfum_id or obj.accessoire_id or obj.produit_fini_essence_id

    def get_id_produit(self, obj):
        return self.get_produit_id(obj)

    def get_nom_produit(self, obj):
        if obj.parfum:
            return obj.parfum.nom
        if obj.accessoire:
            return obj.accessoire.nom
        if obj.produit_fini_essence:
            essence = obj.produit_fini_essence.essence
            nom_essence = essence.nom if essence else "Huile de parfum"
            return f"{nom_essence} - {obj.produit_fini_essence.taille_ml}ml"
        return None

    def get_prix_produit(self, obj):
        if obj.parfum:
            return str(obj.parfum.prix_actuel)
        if obj.accessoire:
            return str(obj.accessoire.prix_actuel)
        if obj.produit_fini_essence:
            return str(obj.produit_fini_essence.prix_actuel)
        return None

    def get_image_produit(self, obj):
        image = None
        if obj.parfum and obj.parfum.image_principale:
            image = obj.parfum.image_principale
        elif obj.accessoire and obj.accessoire.image_principale:
            image = obj.accessoire.image_principale
        elif obj.produit_fini_essence:
            if getattr(obj.produit_fini_essence, 'image_principale', None):
                image = obj.produit_fini_essence.image_principale
            elif obj.produit_fini_essence.essence and getattr(obj.produit_fini_essence.essence, 'image_principale', None):
                image = obj.produit_fini_essence.essence.image_principale

        if not image:
            return None

        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(image.url)
        return image.url

    def get_slug_produit(self, obj):
        if obj.parfum:
            return obj.parfum.slug
        if obj.accessoire:
            return obj.accessoire.slug
        if obj.produit_fini_essence and obj.produit_fini_essence.essence:
            return obj.produit_fini_essence.essence.slug
        return None

    def get_detail_url(self, obj):
        request = self.context.get('request')
        url = None
        try:
            if obj.parfum:
                url = reverse('parfum-detail', kwargs={'slug': obj.parfum.slug})
            elif obj.accessoire:
                url = reverse('accessoire-detail', kwargs={'slug': obj.accessoire.slug})
            elif obj.produit_fini_essence:
                url = reverse('produitessence-detail', kwargs={'pk': obj.produit_fini_essence.pk})
        except Exception:
            return None

        if not url:
            return None

        if request:
            return request.build_absolute_uri(url)
        return url


class MeParfumPersonnaliseLigneSerializer(serializers.ModelSerializer):
    essence_type = serializers.SerializerMethodField()
    essence_id = serializers.SerializerMethodField()
    essence_nom = serializers.SerializerMethodField()

    class Meta:
        model = ParfumPersonnaliseLigne
        fields = [
            'id', 'essence_type', 'essence_id', 'essence_nom',
            'quantite_ml', 'prix_par_ml_snapshot', 'prix_ligne'
        ]

    def get_essence_type(self, obj):
        if obj.essence:
            return 'catalogue'
        if obj.essence_personnalisee:
            return 'personnalisee'
        return None

    def get_essence_id(self, obj):
        return obj.essence_id or obj.essence_personnalisee_id

    def get_essence_nom(self, obj):
        if obj.essence:
            return obj.essence.essence.nom
        if obj.essence_personnalisee:
            return obj.essence_personnalisee.nom
        return None


class MeParfumPersonnaliseSerializer(serializers.ModelSerializer):
    flacon_id = serializers.IntegerField(source='flacon.id', read_only=True)
    flacon_nom = serializers.CharField(source='flacon.nom', read_only=True)
    lignes = MeParfumPersonnaliseLigneSerializer(many=True, read_only=True)
    detail_url = serializers.SerializerMethodField()

    class Meta:
        model = ParfumPersonnalise
        fields = [
            'id', 'nom', 'couleur', 'nom_sur_flacon', 'description',
            'detail_url', 'flacon_id', 'flacon_nom',
            'prix_essences', 'prix_flacon_snapshot',
            'prix_total', 'statut', 'note_laboratoire', 'lignes',
            'date_creation', 'date_modification'
        ]

    def get_detail_url(self, obj):
        return None


class MeCommandeLigneParfumSerializer(serializers.ModelSerializer):
    parfum_id = serializers.IntegerField(source='parfum.id', read_only=True)

    class Meta:
        model = CommandeLigneParfum
        fields = [
            'id', 'parfum_id', 'nom_snapshot', 'quantite',
            'prix_unitaire_snapshot', 'remise_ligne', 'sous_total',
            'mouvement_stock_genere'
        ]


class MeCommandeLigneParfumPersoSerializer(serializers.ModelSerializer):
    parfum_personnalise_id = serializers.IntegerField(source='parfum_personnalise.id', read_only=True)
    parfum_personnalise_nom = serializers.CharField(source='parfum_personnalise.nom', read_only=True)
    composition = ParfumPersoDetailSerializer(source='parfum_personnalise', read_only=True)

    class Meta:
        model = CommandeLigneParfumPerso
        fields = [
            'id', 'parfum_personnalise_id', 'parfum_personnalise_nom',
            'composition',
            'quantite', 'prix_snapshot', 'sous_total', 'statut_laboratoire',
            'proportions_mises_a_jour', 'note_laboratoire'
        ]


class MeCommandeLigneAccessoireSerializer(serializers.ModelSerializer):
    accessoire_id = serializers.IntegerField(source='accessoire.id', read_only=True)

    class Meta:
        model = CommandeLigneAccessoire
        fields = [
            'id', 'accessoire_id', 'nom_snapshot', 'quantite',
            'prix_unitaire_snapshot', 'remise_ligne', 'sous_total',
            'mouvement_stock_genere'
        ]


class MeCommandeLigneProduitFiniEssenceSerializer(serializers.ModelSerializer):
    produit_fini_essence_id = serializers.IntegerField(source='produit_fini_essence.id', read_only=True)

    class Meta:
        model = CommandeProduitFiniEssence
        fields = [
            'id', 'produit_fini_essence_id', 'nom_snapshot', 'quantite',
            'prix_unitaire_snapshot', 'remise_ligne', 'sous_total',
            'mouvement_stock_genere'
        ]


class MeCommandeLigneEssencePersoSerializer(serializers.ModelSerializer):
    essence_personnalise_id = serializers.IntegerField(source='essence_personnalise.id', read_only=True)
    nom = serializers.CharField(source='essence_personnalise.nom', read_only=True)

    class Meta:
        model = CommandeLigneEssencePersonnalisee
        fields = [
            'id', 'essence_personnalise_id', 'nom', 'quantite',
            'prix_snapshot', 'sous_total', 'statut_laboratoire', 'note_laboratoire'
        ]


class MeCommandeLigneDiffuseurSerializer(serializers.ModelSerializer):
    diffuseur_id = serializers.IntegerField(source='diffuseur.id', read_only=True)

    class Meta:
        model = CommandeLigneDiffuseurParfum
        fields = [
            'id', 'diffuseur_id', 'nom_snapshot', 'quantite',
            'prix_unitaire_snapshot', 'remise_ligne', 'sous_total',
            'mouvement_stock_genere'
        ]



class MeCommandeSerializer(serializers.ModelSerializer):
    lignes_parfums = MeCommandeLigneParfumSerializer(many=True, read_only=True)
    lignes_parfums_perso = MeCommandeLigneParfumPersoSerializer(many=True, read_only=True)
    lignes_accessoires = MeCommandeLigneAccessoireSerializer(many=True, read_only=True)
    lignes_produit_fini_essence = MeCommandeLigneProduitFiniEssenceSerializer(many=True, read_only=True)
    lignes_essence_personnalisee = MeCommandeLigneEssencePersoSerializer(many=True, read_only=True)
    lignes_diffuseurs = MeCommandeLigneDiffuseurSerializer(many=True, read_only=True)

    class Meta:
        model = Commande
        fields = [
            'id', 'numero_commande', 'statut', 'statut_livraison',
            'statut_paiement', 'sous_total',
            'remise_code_promo', 'code_promo_utilise', 'frais_livraison',
            'total_ttc', 'livraison_nom_complet', 'livraison_quartier',
            'livraison_ville', 'livraison_telephone',
            'date_livraison_estimee', 'date_livraison_reelle',
            'note_client', 'lignes_parfums', 'lignes_parfums_perso',
            'lignes_accessoires', 'lignes_produit_fini_essence',
            'lignes_essence_personnalisee', 'lignes_diffuseurs',
            'date_creation', 'date_modification'
        ]


class MeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    telephone = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    roles = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'telephone', 'first_name', 'last_name', 'roles', 'photo', 'client', 'preferences']

    def get_roles(self, obj):
        """
        Retourne la liste de tous les rôles actifs de l'utilisateur.
        """
        roles = []
        if obj.is_superuser or obj.is_staff:
            roles.append('superadmin')
        if hasattr(obj, 'client'):
            roles.append('client')
            client = obj.client
            if hasattr(client, 'prestataire'):
                roles.append('prestataire')
            if hasattr(client, 'livreur'):
                roles.append('livreur')
            if hasattr(client, 'serveuse'):
                roles.append('serveuse')
            if hasattr(client, 'boutique'):
                roles.append('boutique')
        return roles

    def get_photo(self, obj):
        if hasattr(obj, 'client'):
            client = obj.client
            for role_attr in ['serveuse', 'livreur', 'prestataire', 'boutique']:
                if hasattr(client, role_attr):
                    profile = getattr(client, role_attr)
                    if profile and profile.photo:
                        request = self.context.get('request')
                        if request:
                            return request.build_absolute_uri(profile.photo.url)
                        return profile.photo.url
        return None

    def _get_client(self, obj):
        return getattr(obj, 'client', None)

    def get_client(self, obj):
        client = self._get_client(obj)
        if not client:
            return None
        return MeClientSerializer(client).data

    def get_preferences(self, obj):
        client = self._get_client(obj)
        preferences = {
            'familles_olfactives': [],
            'humeurs': [],
            'saisons': [],
            'occasions': [],
            'signes_astrologiques': [],
            'moments_journee': [],
            'genres': [],
        }
        if not client:
            return preferences

        tag_mapping = {
            'famille olfactive': 'familles_olfactives',
            'famille_olfactive': 'familles_olfactives',
            'humeur': 'humeurs',
            'saison': 'saisons',
            'occasion': 'occasions',
            'signe astrologique': 'signes_astrologiques',
            'signe_astrologique': 'signes_astrologiques',
            'moment de la journée': 'moments_journee',
            'moment de la journee': 'moments_journee',
            'moment_journee': 'moments_journee',
        }
        values = {key: set() for key in preferences}

        for favori in client.favoris.select_related('parfum', 'produit_fini_essence__essence').all():
            parfum = favori.parfum
            if parfum:
                if getattr(parfum, 'genre_cible', None):
                    values['genres'].add(parfum.genre_cible)
                if hasattr(parfum, 'tags_associes'):
                    for tp in parfum.tags_associes.select_related('tag').all():
                        tag_nom = getattr(tp.tag, 'nom', '').lower().strip() if tp.tag else ''
                        target = tag_mapping.get(tag_nom)
                        if target and tp.valeur:
                            values[target].add(tp.valeur)

            pfe = favori.produit_fini_essence
            if pfe and pfe.essence:
                essence = pfe.essence
                if getattr(essence, 'genre_cible', None):
                    values['genres'].add(essence.genre_cible)
                if hasattr(essence, 'tags_associes'):
                    for te in essence.tags_associes.select_related('tag').all():
                        tag_nom = getattr(te.tag, 'nom', '').lower().strip() if te.tag else ''
                        target = tag_mapping.get(tag_nom)
                        if target and te.valeur:
                            values[target].add(te.valeur)

        return {key: sorted(value) for key, value in values.items()}


class PrestataireSerializer(serializers.ModelSerializer):
    """Serializer complet pour l'affichage (Admin)"""
    user_details = UserSerializer(source='client.user', read_only=True)
    photo = serializers.SerializerMethodField()
    total_gains = serializers.SerializerMethodField()
    total_paid_orders = serializers.SerializerMethodField()

    class Meta:
        model = Prestataire
        fields = [
            'id', 'client', 'user_details', 'photo', 'code_promo',
            'taux_commission', 'reduction_client_pourcentage',
            'solde_commission', 'statut', 'date_creation', 'date_modification',
            'total_gains', 'total_paid_orders'
        ]
        read_only_fields = ['photo']

    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None

    def get_total_gains(self, obj):
        val = getattr(obj, 'total_gains', None)
        return float(val) if val is not None else 0.0

    def get_total_paid_orders(self, obj):
        return getattr(obj, 'total_paid_orders', 0) or 0


# ============================================================
# SERIALIZERS ADMINISTRATION
# ============================================================

class AdminUserSerializer(serializers.ModelSerializer):
    """Serializer ultra-complet pour l'administration des utilisateurs"""
    is_prestataire = serializers.SerializerMethodField()
    prestataire_statut = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'telephone', 'first_name', 'last_name', 
            'role', 'is_active', 'is_staff', 'date_joined', 
            'is_prestataire', 'prestataire_statut'
        ]

    def get_is_prestataire(self, obj):
        return hasattr(obj, 'client') and hasattr(obj.client, 'prestataire')

    def get_prestataire_statut(self, obj):
        if hasattr(obj, 'client') and hasattr(obj.client, 'prestataire'):
            return obj.client.prestataire.statut
        return None

class AdminPrestataireUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier un prestataire depuis l'admin"""
    class Meta:
        model = Prestataire
        fields = ['taux_commission', 'reduction_client_pourcentage', 'statut']


class PayoutTransactionSerializer(serializers.ModelSerializer):
    """Serializer pour l'historique des virements"""
    class Meta:
        model = PayoutTransaction
        fields = [
            'id', 'prestataire', 'montant', 'telephone_destination',
            'reference_unique', 'statut', 'motif_echec', 'date_creation', 'date_finalisation'
        ]
        read_only_fields = fields


from decimal import Decimal

class PayoutRequestSerializer(serializers.Serializer):
    """Serializer pour valider une demande de virement admin"""
    montant = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    telephone = serializers.CharField(required=False, allow_blank=True)
    external_reference = serializers.CharField(required=False, allow_blank=True)


class LivreurSerializer(serializers.ModelSerializer):
    """Serializer complet pour le profil Livreur"""
    user_details = UserSerializer(source='client.user', read_only=True)
    photo = serializers.SerializerMethodField()
    
    class Meta:
        model = Livreur
        fields = [
            'id', 'user_details', 'photo', 'statut', 
            'nombre_livraisons', 'date_embauche', 'date_creation'
        ]
        read_only_fields = ['photo', 'nombre_livraisons', 'date_creation']

    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None

class LivreurUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier le statut du livreur depuis l'admin"""
    class Meta:
        model = Livreur
        fields = ['statut']

class LivreurCommandeSerializer(serializers.ModelSerializer):
    """Serializer allégé pour les livraisons attribuées à un livreur"""
    client_nom = serializers.SerializerMethodField()
    
    class Meta:
        model = Commande
        fields = [
            'id', 'numero_commande', 'statut', 'statut_livraison', 
            'livraison_nom_complet', 'livraison_quartier', 'livraison_ville', 
            'livraison_telephone', 'statut_paiement',
            'total_ttc', 'date_creation', 'date_livraison_reelle', 'note_client',
            'motif_echec_livraison', 'client_nom'
        ]
        read_only_fields = fields

    def get_client_nom(self, obj):
        try:
            user = obj.client.user
            full_name = f"{user.first_name} {user.last_name}".strip()
            return full_name or user.email
        except AttributeError:
            return "Client inconnu"


class ServeusesSerializer(serializers.ModelSerializer):
    """Serializer complet pour le profil Serveuse"""
    user_details = UserSerializer(source='client.user', read_only=True)
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Serveuse
        fields = [
            'id', 'user_details', 'photo', 'actif',
            'nombre_services', 'note_moyenne', 'date_embauche', 'date_creation'
        ]
        read_only_fields = ['photo', 'nombre_services', 'date_creation']

    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None


class ServeusesUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier le statut de la serveuse depuis l'admin"""
    class Meta:
        model = Serveuse
        fields = ['actif']


# ============================================================
# SERIALIZERS BOUTIQUE
# ============================================================

class BoutiqueSerializer(serializers.ModelSerializer):
    """Serializer complet pour le profil Boutique"""
    user_details = UserSerializer(source='client.user', read_only=True)
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Boutique
        fields = [
            'id', 'user_details', 'photo', 'nom', 'adresse', 'ville',
            'telephone', 'taux_commission', 'statut', 'date_creation', 'date_modification'
        ]
        read_only_fields = ['photo', 'statut', 'date_creation', 'date_modification']

    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None


class BoutiqueAdminDetailSerializer(serializers.ModelSerializer):
    """
    Serializer enrichi pour l'Admin : fiche complète d'une boutique partenaire.
    Inclut toutes les infos financières, le propriétaire et les statistiques.
    """
    user_details = UserSerializer(source='client.user', read_only=True)
    photo = serializers.SerializerMethodField()
    proprietaire_nom = serializers.SerializerMethodField()
    proprietaire_email = serializers.SerializerMethodField()
    proprietaire_telephone = serializers.SerializerMethodField()
    nb_produits_parfums = serializers.SerializerMethodField()
    nb_produits_accessoires = serializers.SerializerMethodField()
    nb_produits_total = serializers.SerializerMethodField()
    nb_ventes_total = serializers.SerializerMethodField()

    class Meta:
        model = Boutique
        fields = [
            # Identité
            'id', 'nom', 'photo', 'adresse', 'ville', 'telephone',
            # Propriétaire
            'user_details', 'proprietaire_nom', 'proprietaire_email', 'proprietaire_telephone',
            # Commission & Statut
            'taux_commission', 'statut',
            # Finances
            'solde_disponible', 'solde_total_recu',
            # Paiement
            'telephone_paiement', 'mode_paiement_prefere',
            # Statistiques
            'nb_produits_parfums', 'nb_produits_accessoires', 'nb_produits_total', 'nb_ventes_total',
            # Dates
            'date_creation', 'date_modification',
        ]
        read_only_fields = [
            'photo', 'statut', 'date_creation', 'date_modification',
            'solde_disponible', 'solde_total_recu',
        ]

    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None

    def get_proprietaire_nom(self, obj):
        return obj.proprietaire_nom

    def get_proprietaire_email(self, obj):
        return obj.client.user.email

    def get_proprietaire_telephone(self, obj):
        return obj.client.user.phone_number if hasattr(obj.client.user, 'phone_number') else obj.telephone

    def get_nb_produits_parfums(self, obj):
        return obj.parfums.count()

    def get_nb_produits_accessoires(self, obj):
        return obj.accessoires.count()

    def get_nb_produits_total(self, obj):
        return obj.parfums.count() + obj.accessoires.count()

    def get_nb_ventes_total(self, obj):
        from orders.models import VenteBoutique
        return VenteBoutique.objects.filter(boutique=obj, statut='valide').count()


class BoutiqueApplicationSerializer(serializers.ModelSerializer):
    """Serializer pour la demande initiale d'ouverture de boutique (photo obligatoire)"""
    photo = serializers.ImageField(required=True)

    class Meta:
        model = Boutique
        fields = ['nom', 'photo', 'adresse', 'ville', 'telephone']
        extra_kwargs = {
            'nom': {'required': True},
        }


class BoutiqueMeUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour que le propriétaire modifie les infos de sa boutique"""
    class Meta:
        model = Boutique
        fields = ['nom', 'adresse', 'ville', 'telephone']


class BoutiqueAdminUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour que l'admin modifie le statut, le taux de commission et les infos d'une boutique"""
    class Meta:
        model = Boutique
        fields = ['nom', 'adresse', 'ville', 'telephone', 'taux_commission', 'statut']

    def validate_taux_commission(self, value):
        from orders.models import CodePromoAdmin
        from django.db.models import Max
        
        cost_max = CodePromoAdmin.objects.filter(est_actif=True).aggregate(m=Max('reduction_pourcentage'))['m'] or Decimal('0')
        if value < cost_max:
            raise serializers.ValidationError(
                f"🚨 SÉCURITÉ FINANCIÈRE : Ce taux de commission ({value}%) est inférieur au "
                f"coût du code promo actif le plus élevé ({cost_max}%). "
                f"Ajustez d'abord vos codes promo pour éviter toute perte financière."
            )
        return value


class BoutiqueValidationSerializer(serializers.ModelSerializer):
    """Serializer pour la validation d'une boutique par l'admin (taux_commission obligatoire)"""
    taux_commission = serializers.DecimalField(max_digits=5, decimal_places=2, required=True, min_value=0, max_value=100)

    class Meta:
        model = Boutique
        fields = ['taux_commission']

    def validate_taux_commission(self, value):
        from orders.models import CodePromoAdmin
        from django.db.models import Max
        
        cost_max = CodePromoAdmin.objects.filter(est_actif=True).aggregate(m=Max('reduction_pourcentage'))['m'] or Decimal('0')
        if value < cost_max:
            raise serializers.ValidationError(
                f"🚨 SÉCURITÉ FINANCIÈRE : Ce taux de commission ({value}%) est inférieur au "
                f"coût du code promo actif le plus élevé ({cost_max}%). "
                f"Ajustez d'abord vos codes promo pour éviter toute perte financière."
            )
        return value



class DepenseSerializer(serializers.ModelSerializer):
    cree_par_details = UserSerializer(source='cree_par', read_only=True)

    class Meta:
        model = Depense
        fields = [
            'id', 'titre', 'description', 'montant', 
            'cree_par', 'cree_par_details', 'date_depense',
            'date_creation', 'date_modification'
        ]
        read_only_fields = ['cree_par', 'date_creation', 'date_modification']


class FCMDeviceSerializer(serializers.Serializer):
    """
    Sérialiseur pour enregistrer ou mettre à jour un token FCM d'appareil.

    Le frontend doit appeler POST /api/v1/auth/devices/register/ après chaque
    connexion pour associer le token FCM de l'appareil à l'utilisateur connecté.
    """
    registration_token = serializers.CharField(
        max_length=500,
        help_text="Token FCM fourni par Firebase SDK côté client."
    )
    platform = serializers.ChoiceField(
        choices=['android', 'ios', 'web'],
        default='web',
        help_text="Plateforme de l'appareil : 'android', 'ios' ou 'web'."
    )

    def save(self, user):
        """
        Crée ou met à jour l'appareil FCM.
        Si le token existe déjà (autre utilisateur), il est réassigné à cet utilisateur.
        """
        from utilisateur.models import FCMDevice
        token = self.validated_data['registration_token']
        platform = self.validated_data['platform']

        device, created = FCMDevice.objects.update_or_create(
            registration_token=token,
            defaults={
                'user': user,
                'platform': platform,
                'active': True,
            }
        )
        return device


class VenteBoutiqueSerializer(serializers.ModelSerializer):
    commande_numero = serializers.CharField(source='commande.numero_commande', read_only=True)
    boutique_nom = serializers.CharField(source='boutique.nom', read_only=True)

    class Meta:
        from orders.models import VenteBoutique
        model = VenteBoutique
        fields = [
            'id', 'commande', 'commande_numero', 'boutique', 'boutique_nom',
            'montant_brut', 'taux_commission_applique', 'montant_commission_admin',
            'montant_net_boutique', 'statut', 'date_creation', 'date_reglement'
        ]


class VersementBoutiqueSerializer(serializers.ModelSerializer):
    boutique_nom = serializers.CharField(source='boutique.nom', read_only=True)
    effectue_par_nom = serializers.SerializerMethodField()

    class Meta:
        from orders.models import VersementBoutique
        model = VersementBoutique
        fields = [
            'id', 'boutique', 'boutique_nom', 'montant', 'reference_transaction',
            'mode_paiement', 'telephone_destination', 'note_admin',
            'effectue_par', 'effectue_par_nom', 'date_versement'
        ]

    def get_effectue_par_nom(self, obj):
        if obj.effectue_par:
            return obj.effectue_par.get_full_name() or obj.effectue_par.email
        return None

