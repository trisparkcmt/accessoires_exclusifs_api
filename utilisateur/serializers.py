from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import authenticate
from django.urls import reverse
from dj_rest_auth.serializers import LoginSerializer, PasswordChangeSerializer
from dj_rest_auth.registration.serializers import RegisterSerializer
from drf_spectacular.utils import extend_schema_serializer
from .models import User, Client, Prestataire, CommissionLog, Notification, PayoutTransaction, Livreur, Serveuse, Depense
from catalogue.models import Favori
from laboratoire.models import ParfumPersonnalise, ParfumPersonnaliseLigne
from orders.models import (
    Commande,
    CommandeLigneAccessoire,
    CommandeLigneParfum,
    CommandeLigneParfumPerso,
)


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
        user.first_name = self.validated_data.get('first_name', '')
        user.last_name = self.validated_data.get('last_name', '')
        user.telephone = self.validated_data.get('telephone', '')
        
        from django.conf import settings
        if getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional') == 'mandatory':
            user.is_active = False  # Par sécurité
            
        user.save()

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
            'id', 'solde_commission', 'taux_commission', 'reduction_client_pourcentage', 
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
    """Serializer pour la demande initiale de l'utilisateur"""
    class Meta:
        model = Prestataire
        fields = [] # L'utilisateur ne remplit rien, on crée juste l'objet en attente

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

    class Meta:
        model = User
        fields = ['id', 'email', 'telephone', 'first_name', 'last_name', 'roles']
        read_only_fields = ['roles']
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
        return roles


class MeUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier le profil sans gérer le changement d'email."""
    class Meta:
        model = User
        fields = ['telephone', 'first_name', 'last_name']


class ClientSerializer(serializers.ModelSerializer):
    """Serializer pour le profil Client complet"""
    user_details = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = Client
        fields = ['id', 'user_details', 'date_naissance', 'genre', 'points_fidelite']


class MeClientSerializer(serializers.ModelSerializer):
    """Données client rattachées au profil connecté."""
    class Meta:
        model = Client
        fields = ['id', 'date_naissance', 'genre', 'points_fidelite', 'date_creation']


class MeFavoriSerializer(serializers.ModelSerializer):
    type_produit = serializers.SerializerMethodField()
    produit_id = serializers.SerializerMethodField()
    nom_produit = serializers.SerializerMethodField()
    prix_produit = serializers.SerializerMethodField()
    image_produit = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    class Meta:
        model = Favori
        fields = [
            'id', 'type_produit', 'produit_id', 'nom_produit',
            'prix_produit', 'image_produit', 'detail_url', 'date_ajout'
        ]

    def get_type_produit(self, obj):
        return 'parfum' if obj.parfum_id else 'accessoire'

    def get_produit_id(self, obj):
        if obj.parfum_id:
            return obj.parfum_id
        return obj.accessoire_id

    def get_nom_produit(self, obj):
        produit = obj.parfum or obj.accessoire
        return produit.nom if produit else None

    def get_prix_produit(self, obj):
        produit = obj.parfum or obj.accessoire
        return str(produit.prix_actuel) if produit else None

    def get_image_produit(self, obj):
        produit = obj.parfum or obj.accessoire
        image = getattr(produit, 'image_principale', None)
        if not image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(image.url)
        return image.url

    def get_detail_url(self, obj):
        produit = obj.parfum or obj.accessoire
        if not produit:
            return None

        if obj.parfum_id:
            url = reverse('parfum-detail', kwargs={'slug': produit.slug})
        else:
            url = reverse('accessoire-detail', kwargs={'slug': produit.slug})

        request = self.context.get('request')
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
            'id', 'nom', 'description', 'detail_url', 'flacon_id', 'flacon_nom',
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

    class Meta:
        model = CommandeLigneParfumPerso
        fields = [
            'id', 'parfum_personnalise_id', 'parfum_personnalise_nom',
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


class MeCommandeSerializer(serializers.ModelSerializer):
    lignes_parfums = MeCommandeLigneParfumSerializer(many=True, read_only=True)
    lignes_parfums_perso = MeCommandeLigneParfumPersoSerializer(many=True, read_only=True)
    lignes_accessoires = MeCommandeLigneAccessoireSerializer(many=True, read_only=True)

    class Meta:
        model = Commande
        fields = [
            'id', 'numero_commande', 'statut', 'statut_livraison',
            'statut_paiement', 'methode_paiement', 'sous_total',
            'remise_code_promo', 'code_promo_utilise', 'frais_livraison',
            'total_ttc', 'livraison_nom_complet', 'livraison_quartier',
            'livraison_ville', 'livraison_telephone',
            'date_livraison_estimee', 'date_livraison_reelle',
            'note_client', 'lignes_parfums', 'lignes_parfums_perso',
            'lignes_accessoires', 'date_creation', 'date_modification'
        ]


class MeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    telephone = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    roles = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()
    favoris = serializers.SerializerMethodField()
    parfums_personnalises = serializers.SerializerMethodField()
    commandes = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'telephone', 'first_name', 'last_name', 'roles', 'client', 'preferences', 'favoris', 'parfums_personnalises', 'commandes']

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
        return roles

    def _get_client(self, obj):
        return getattr(obj, 'client', None)

    def get_client(self, obj):
        client = self._get_client(obj)
        if not client:
            return None
        return MeClientSerializer(client).data

    def get_favoris(self, obj):
        client = self._get_client(obj)
        if not client:
            return []
        return MeFavoriSerializer(
            client.favoris.all(),
            many=True,
            context=self.context
        ).data

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
            'famille_olfactive': 'familles_olfactives',
            'humeur': 'humeurs',
            'saison': 'saisons',
            'occasion': 'occasions',
            'signe_astrologique': 'signes_astrologiques',
            'moment_journee': 'moments_journee',
        }
        values = {key: set() for key in preferences}

        for favori in client.favoris.all():
            parfum = favori.parfum
            if not parfum:
                continue
            if parfum.genre_cible:
                values['genres'].add(parfum.genre_cible)
            for tag in parfum.tags.all():
                target = tag_mapping.get(tag.type)
                if target:
                    values[target].add(tag.nom)

        return {key: sorted(value) for key, value in values.items()}

    def get_parfums_personnalises(self, obj):
        client = self._get_client(obj)
        if not client:
            return []
        return MeParfumPersonnaliseSerializer(
            client.parfums_personnalises.all(),
            many=True
        ).data

    def get_commandes(self, obj):
        client = self._get_client(obj)
        if not client:
            return []
        return MeCommandeSerializer(
            client.commandes.all(),
            many=True
        ).data


class PrestataireSerializer(serializers.ModelSerializer):
    """Serializer complet pour l'affichage (Admin)"""
    user_details = UserSerializer(source='client.user', read_only=True)
    class Meta:
        model = Prestataire
        fields = '__all__'

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


class LivreurSerializer(serializers.ModelSerializer):
    """Serializer complet pour le profil Livreur"""
    user_details = UserSerializer(source='client.user', read_only=True)
    
    class Meta:
        model = Livreur
        fields = [
            'id', 'user_details', 'photo', 'statut', 
            'nombre_livraisons', 'date_embauche', 'date_creation'
        ]
        read_only_fields = ['nombre_livraisons', 'date_creation']

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
            'livraison_telephone', 'methode_paiement', 'statut_paiement',
            'total_ttc', 'date_creation', 'date_livraison_reelle', 'note_client',
            'motif_echec_livraison', 'client_nom'
        ]
        read_only_fields = fields

    def get_client_nom(self, obj):
        user = obj.client.user
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.email


class ServeusesSerializer(serializers.ModelSerializer):
    """Serializer complet pour le profil Serveuse"""
    user_details = UserSerializer(source='client.user', read_only=True)

    class Meta:
        model = Serveuse
        fields = [
            'id', 'user_details', 'actif',
            'nombre_services', 'note_moyenne', 'date_embauche', 'date_creation'
        ]
        read_only_fields = ['nombre_services', 'date_creation']


class ServeusesUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier le statut de la serveuse depuis l'admin"""
    class Meta:
        model = Serveuse
        fields = ['actif']


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


