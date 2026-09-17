from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django import forms
from django.core.exceptions import ValidationError
from .models import User, Client, Prestataire, Livreur, CommissionLog, Serveuse, FCMDevice, Boutique


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'telephone', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'telephone')
    ordering = ('-date_joined',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Informations supplémentaires', {'fields': ('telephone',)}),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informations supplémentaires', {'fields': ('telephone',)}),
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'get_telephone', 'genre', 'points_fidelite', 'date_creation')
    list_filter = ('genre', 'date_creation')
    search_fields = ('user__email', 'user__username', 'user__first_name', 'user__last_name', 'user__telephone')
    readonly_fields = ('date_creation', 'date_modification', 'points_fidelite')
    
    fieldsets = (
        ('Informations utilisateur', {
            'fields': ('user', 'date_naissance', 'genre')
        }),
        ('Fidélité', {
            'fields': ('points_fidelite',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    def get_telephone(self, obj):
        return obj.telephone
    get_telephone.short_description = 'Téléphone'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(Prestataire)
class PrestataireAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_nom', 'get_prenom', 'code_promo', 'taux_commission', 'solde_commission', 'statut')
    list_filter = ('statut', 'date_creation')
    search_fields = ('client__user__last_name', 'client__user__first_name', 'code_promo')
    readonly_fields = ('date_creation', 'date_modification')
    
    fieldsets = (
        ('Client associé', {
            'fields': ('client',)
        }),
        
        ('Commission', {
            'fields': ('code_promo', 'taux_commission', 'solde_commission')
        }),
        ('Statut', {
            'fields': ('statut',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    def get_nom(self, obj):
        return obj.nom
    get_nom.short_description = 'Nom'
    
    def get_prenom(self, obj):
        return obj.prenom
    get_prenom.short_description = 'Prénom'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'client__user')


@admin.register(CommissionLog)
class CommissionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'prestataire', 'type_operation', 'montant', 'reference_commande', 'date_operation')
    list_filter = ('type_operation', 'date_operation')
    search_fields = ('prestataire__client__user__email', 'reference_commande', 'description')
    autocomplete_fields = ('prestataire',)


class LivreurAdminForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        required=False,
        label="Client existant",
        help_text="Sélectionnez un client existant pour lui attribuer le rôle de livreur."
    )
    email_creation = forms.EmailField(
        required=False,
        label="Email (Nouveau client)",
        help_text="Requis si aucun client existant n'est sélectionné."
    )
    telephone_creation = forms.CharField(
        required=False,
        label="Téléphone (Nouveau client)",
        help_text="Requis si aucun client existant n'est sélectionné."
    )
    password_creation = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label="Mot de passe (Nouveau client)",
        help_text="Requis si aucun client existant n'est sélectionné."
    )
    first_name_creation = forms.CharField(
        required=False,
        label="Prénom (Nouveau client)"
    )
    last_name_creation = forms.CharField(
        required=False,
        label="Nom (Nouveau client)"
    )
    genre_creation = forms.ChoiceField(
        choices=[('', '---------')] + Client.GENRE_CHOICES,
        required=False,
        label="Genre (Nouveau client)"
    )

    class Meta:
        model = Livreur
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get('client')
        
        email = cleaned_data.get('email_creation')
        telephone = cleaned_data.get('telephone_creation')
        password = cleaned_data.get('password_creation')
        
        if not client:
            missing = []
            if not email:
                missing.append("Email")
            if not telephone:
                missing.append("Téléphone")
            if not password:
                missing.append("Mot de passe")
                
            if missing:
                raise ValidationError(
                    f"Veuillez soit choisir un client existant, soit remplir tous les champs obligatoires pour le nouveau client: {', '.join(missing)}."
                )
            
            if User.objects.filter(email=email).exists():
                self.add_error('email_creation', "Un utilisateur avec cet email existe déjà.")
            if User.objects.filter(telephone=telephone).exists():
                self.add_error('telephone_creation', "Un utilisateur avec ce numéro de téléphone existe déjà.")
        else:
            if hasattr(client, 'livreur') and client.livreur != self.instance:
                raise ValidationError("Ce client a déjà un profil Livreur associé.")
                
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        client = self.cleaned_data.get('client')
        
        if not client:
            email = self.cleaned_data.get('email_creation')
            telephone = self.cleaned_data.get('telephone_creation')
            password = self.cleaned_data.get('password_creation')
            first_name = self.cleaned_data.get('first_name_creation')
            last_name = self.cleaned_data.get('last_name_creation')
            genre = self.cleaned_data.get('genre_creation')
            
            user = User.objects.create_user(
                email=email,
                username=email.split('@')[0],
                telephone=telephone,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            client = Client.objects.create(user=user, genre=genre or '')
            
        instance.client = client
        if commit:
            instance.save()
        return instance


class ServeuseAdminForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        required=False,
        label="Client existant",
        help_text="Sélectionnez un client existant pour lui attribuer le rôle de serveuse."
    )
    email_creation = forms.EmailField(
        required=False,
        label="Email (Nouveau client)",
        help_text="Requis si aucun client existant n'est sélectionné."
    )
    telephone_creation = forms.CharField(
        required=False,
        label="Téléphone (Nouveau client)",
        help_text="Requis si aucun client existant n'est sélectionné."
    )
    password_creation = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label="Mot de passe (Nouveau client)",
        help_text="Requis si aucun client existant n'est sélectionné."
    )
    first_name_creation = forms.CharField(
        required=False,
        label="Prénom (Nouveau client)"
    )
    last_name_creation = forms.CharField(
        required=False,
        label="Nom (Nouveau client)"
    )
    genre_creation = forms.ChoiceField(
        choices=[('', '---------')] + Client.GENRE_CHOICES,
        required=False,
        label="Genre (Nouveau client)"
    )

    class Meta:
        model = Serveuse
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get('client')
        
        email = cleaned_data.get('email_creation')
        telephone = cleaned_data.get('telephone_creation')
        password = cleaned_data.get('password_creation')
        
        if not client:
            missing = []
            if not email:
                missing.append("Email")
            if not telephone:
                missing.append("Téléphone")
            if not password:
                missing.append("Mot de passe")
                
            if missing:
                raise ValidationError(
                    f"Veuillez soit choisir un client existant, soit remplir tous les champs obligatoires pour le nouveau client: {', '.join(missing)}."
                )
            
            if User.objects.filter(email=email).exists():
                self.add_error('email_creation', "Un utilisateur avec cet email existe déjà.")
            if User.objects.filter(telephone=telephone).exists():
                self.add_error('telephone_creation', "Un utilisateur avec ce numéro de téléphone existe déjà.")
        else:
            if hasattr(client, 'serveuse') and client.serveuse != self.instance:
                raise ValidationError("Ce client a déjà un profil Serveuse associé.")
                
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        client = self.cleaned_data.get('client')
        
        if not client:
            email = self.cleaned_data.get('email_creation')
            telephone = self.cleaned_data.get('telephone_creation')
            password = self.cleaned_data.get('password_creation')
            first_name = self.cleaned_data.get('first_name_creation')
            last_name = self.cleaned_data.get('last_name_creation')
            genre = self.cleaned_data.get('genre_creation')
            
            user = User.objects.create_user(
                email=email,
                username=email.split('@')[0],
                telephone=telephone,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            client = Client.objects.create(user=user, genre=genre or '')
            
        instance.client = client
        if commit:
            instance.save()
        return instance


@admin.register(Livreur)
class LivreurAdmin(admin.ModelAdmin):
    form = LivreurAdminForm
    list_display = ('id', 'get_nom', 'get_prenom', 'get_telephone', 'statut', 'note_moyenne', 'nombre_livraisons')
    list_filter = ('statut', 'date_embauche')
    search_fields = ('client__user__last_name', 'client__user__first_name', 'client__user__telephone', 'client__user__email')
    readonly_fields = ('date_creation', 'date_modification', 'note_moyenne', 'nombre_livraisons')
    
    def get_fieldsets(self, request, obj=None):
        if obj:
            return (
                ('Client associé', {
                    'fields': ('client', 'photo')
                }),
                ('Informations professionnelles', {
                    'fields': ('date_embauche',)
                }),
                ('Statistiques', {
                    'fields': ('statut', 'note_moyenne', 'nombre_livraisons')
                }),
                ('Dates', {
                    'fields': ('date_creation', 'date_modification'),
                    'classes': ('collapse',)
                }),
            )
        return (
            ('Sélection Client Existant', {
                'fields': ('client',)
            }),
            ('OU Création à partir de zéro', {
                'fields': ('email_creation', 'telephone_creation', 'password_creation', 'first_name_creation', 'last_name_creation', 'genre_creation'),
                'description': 'Remplissez ces champs pour créer un nouvel utilisateur et un nouveau client automatiquement.',
            }),
            ('Informations professionnelles', {
                'fields': ('photo', 'date_embauche')
            }),
            ('Statistiques', {
                'fields': ('statut',)
            }),
        )
    
    def get_nom(self, obj):
        return obj.nom
    get_nom.short_description = 'Nom'
    
    def get_prenom(self, obj):
        return obj.prenom
    get_prenom.short_description = 'Prénom'
    
    def get_telephone(self, obj):
        return obj.telephone
    get_telephone.short_description = 'Téléphone'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'client__user')

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff
        
    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.is_staff
        
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff
        
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff


@admin.register(Serveuse)
class ServeuseAdmin(admin.ModelAdmin):
    form = ServeuseAdminForm
    list_display = ('id', 'get_nom', 'get_prenom', 'get_telephone', 'actif', 'note_moyenne', 'nombre_services')
    list_filter = ('actif', 'date_embauche')
    search_fields = ('client__user__last_name', 'client__user__first_name', 'client__user__telephone', 'client__user__email')
    readonly_fields = ('date_creation', 'date_modification', 'note_moyenne', 'nombre_services')

    def get_fieldsets(self, request, obj=None):
        if obj:
            return (
                ('Client associé', {
                    'fields': ('client',)
                }),
                ('Informations professionnelles', {
                    'fields': ('date_embauche',)
                }),
                ('Statistiques', {
                    'fields': ('actif', 'note_moyenne', 'nombre_services')
                }),
                ('Dates', {
                    'fields': ('date_creation', 'date_modification'),
                    'classes': ('collapse',)
                }),
            )
        return (
            ('Sélection Client Existant', {
                'fields': ('client',)
            }),
            ('OU Création à partir de zéro', {
                'fields': ('email_creation', 'telephone_creation', 'password_creation', 'first_name_creation', 'last_name_creation', 'genre_creation'),
                'description': 'Remplissez ces champs pour créer un nouvel utilisateur et un nouveau client automatiquement.',
            }),
            ('Informations professionnelles', {
                'fields': ('date_embauche',)
            }),
            ('Statistiques', {
                'fields': ('actif',)
            }),
        )
    
    def get_nom(self, obj):
        return obj.nom
    get_nom.short_description = 'Nom'
    
    def get_prenom(self, obj):
        return obj.prenom
    get_prenom.short_description = 'Prénom'
    
    def get_telephone(self, obj):
        return obj.telephone
    get_telephone.short_description = 'Téléphone'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'client__user')

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff
        
    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.is_staff
        
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff
        
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff


# ============================================================
# FCM DEVICES — Tokens push notification
# ============================================================
@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'platform', 'active', 'token_court', 'created_at', 'updated_at')
    list_filter = ('platform', 'active')
    search_fields = ('user__email', 'user__username', 'registration_token')
    readonly_fields = ('registration_token', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    list_per_page = 50

    @admin.display(description='Utilisateur', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description='Token (aperçu)')
    def token_court(self, obj):
        return f"{obj.registration_token[:40]}…"

    def has_add_permission(self, request):
        return False  # Les tokens sont créés par le SDK Firebase côté client

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff


@admin.register(Boutique)
class BoutiqueAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom', 'get_proprietaire', 'ville', 'telephone', 'statut', 'date_creation')
    list_filter = ('statut', 'date_creation', 'ville')
    search_fields = ('nom', 'adresse', 'ville', 'telephone', 'client__user__email', 'client__user__first_name', 'client__user__last_name')
    readonly_fields = ('date_creation', 'date_modification')

    fieldsets = (
        ('Client propriétaire', {
            'fields': ('client',)
        }),
        ('Informations Boutique', {
            'fields': ('nom', 'photo', 'adresse', 'ville', 'telephone')
        }),
        ('Statut', {
            'fields': ('statut',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )

    def get_proprietaire(self, obj):
        return obj.proprietaire_nom
    get_proprietaire.short_description = 'Propriétaire'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'client__user')