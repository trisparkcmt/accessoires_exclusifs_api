from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    Panier, PanierLigneParfum, PanierLigneParfumPerso, PanierLigneAccessoire,
    Commande, CommandeLigneParfum, CommandeLigneParfumPerso, CommandeLigneAccessoire,
    AffectationLivraison
)


# ============================================================
# INLINES POUR PANIER
# ============================================================
class PanierLigneParfumInline(admin.TabularInline):
    model = PanierLigneParfum
    extra = 0
    fields = ('parfum', 'quantite', 'prix_unitaire_snapshot', 'sous_total')
    readonly_fields = ('sous_total',)
    autocomplete_fields = ('parfum',)


class PanierLigneParfumPersoInline(admin.TabularInline):
    model = PanierLigneParfumPerso
    extra = 0
    fields = ('parfum_personnalise', 'quantite', 'prix_calcule', 'sous_total', 'note_client')
    readonly_fields = ('sous_total',)
    autocomplete_fields = ('parfum_personnalise',)


class PanierLigneAccessoireInline(admin.TabularInline):
    model = PanierLigneAccessoire
    extra = 0
    fields = ('accessoire', 'quantite', 'prix_unitaire_snapshot', 'sous_total')
    readonly_fields = ('sous_total',)
    autocomplete_fields = ('accessoire',)


@admin.register(Panier)
class PanierAdmin(admin.ModelAdmin):
    list_display = ('id', 'client_info', 'sous_total', 'total', 'statut', 'date_creation')
    list_filter = ('statut', 'date_creation', 'date_modification')
    search_fields = ('client__user__email', 'client__user__username')
    readonly_fields = ('date_creation', 'date_modification', 'sous_total', 'total')
    inlines = [PanierLigneParfumInline, PanierLigneParfumPersoInline, PanierLigneAccessoireInline]
    
    fieldsets = (
        ('Client', {
            'fields': ('client',)
        }),
        ('Promotions', {
            'fields': ('code_promo_applique', 'prestataire', 'remise_montant', 'remise_pourcentage')
        }),
        ('Totaux', {
            'fields': ('sous_total', 'frais_livraison', 'total')
        }),
        ('Statut', {
            'fields': ('statut',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    def client_info(self, obj):
        if obj.client:
            return format_html(
                '<b>{}</b><br/><small>{}</small>',
                obj.client.user.get_full_name() or obj.client.user.email,
                obj.client.telephone
            )
        return f"Panier #{obj.id}"
    client_info.short_description = 'Client'


# ============================================================
# INLINES POUR COMMANDE
# ============================================================
class CommandeLigneParfumInline(admin.TabularInline):
    model = CommandeLigneParfum
    extra = 0
    fields = ('nom_snapshot', 'quantite', 'prix_unitaire_snapshot', 'remise_ligne', 'sous_total')
    readonly_fields = ('sous_total',)


class CommandeLigneParfumPersoInline(admin.TabularInline):
    model = CommandeLigneParfumPerso
    extra = 0
    fields = ('parfum_personnalise', 'quantite', 'prix_snapshot', 'sous_total', 'statut_laboratoire')
    readonly_fields = ('sous_total',)


class CommandeLigneAccessoireInline(admin.TabularInline):
    model = CommandeLigneAccessoire
    extra = 0
    fields = ('nom_snapshot', 'quantite', 'prix_unitaire_snapshot', 'remise_ligne', 'sous_total')
    readonly_fields = ('sous_total',)


class AffectationLivraisonInline(admin.TabularInline):
    model = AffectationLivraison
    extra = 0
    fields = ('livreur', 'statut', 'date_affectation', 'date_livraison_reelle')
    readonly_fields = ('date_affectation', 'date_livraison_reelle')
    autocomplete_fields = ('livreur',)


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ('id', 'numero_commande', 'client_info', 'total_ttc', 'statut', 'statut_paiement', 'date_creation', 'actions_links')
    list_filter = ('statut', 'statut_paiement', 'statut_livraison', 'date_creation')
    search_fields = (
        'numero_commande', 'client__user__email', 'client__user__username', 
        'client__user__first_name', 'client__user__last_name', 'livraison_nom_complet'
    )
    list_per_page = 100
    readonly_fields = ('date_creation', 'date_modification', 'numero_commande')
    inlines = [
        CommandeLigneParfumInline, 
        CommandeLigneParfumPersoInline, 
        CommandeLigneAccessoireInline,
        AffectationLivraisonInline
    ]
    
    fieldsets = (
        ('Identifiant', {
            'fields': ('numero_commande', 'client', 'prestataire', 'panier')
        }),
        ('Statuts', {
            'fields': ('statut', 'statut_livraison', 'statut_paiement')
        }),
        ('Totaux', {
            'fields': ('sous_total', 'remise_code_promo', 'code_promo_utilise', 'frais_livraison', 'total_ttc')
        }),
        ('Commission', {
            'fields': ('commission_montant', 'commission_statut')
        }),
        ('Livraison', {
            'fields': ('livreur', 'livraison_nom_complet', 'livraison_quartier', 'livraison_ville', 'livraison_telephone')
        }),
        ('Suivi livraison', {
            'fields': ('date_livraison_estimee', 'date_livraison_reelle')
        }),
        
        ('Notes', {
            'fields': ('note_client', 'note_interne')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    def client_info(self, obj):
        return format_html(
            '<b>{}</b><br/><small>{}</small>',
            obj.client.user.get_full_name() or obj.client.user.email,
            obj.client.telephone
        )
    client_info.short_description = 'Client'
    
    def actions_links(self, obj):
        """Liens d'action rapide"""
        links = []
        # Lien pour voir dans le panier associé
        if obj.panier:
            panier_url = reverse('admin:orders_panier_change', args=[obj.panier.id])
            links.append(format_html('<a href="{}" target="_blank">Voir panier</a>', panier_url))
        # Lien pour affecter un livreur
        if obj.statut == 'en_attente':
            links.append(format_html('<a href="#" style="color:green;">Affecter livreur</a>'))
        return format_html(' | '.join(links))
    actions_links.short_description = 'Actions'
    actions_links.allow_tags = True
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'client__user', 'prestataire', 'livreur', 'panier')
    
    actions = ['marquer_livrees']
    
    def marquer_livrees(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(statut='livrée', statut_livraison='livrée', date_livraison_reelle=timezone.now())
        self.message_user(request, f'{updated} commande(s) marquée(s) comme livrée(s).')
    marquer_livrees.short_description = 'Marquer comme livrées'


@admin.register(AffectationLivraison)
class AffectationLivraisonAdmin(admin.ModelAdmin):
    list_display = ('id', 'commande_numero', 'livreur', 'statut', 'date_affectation', 'date_livraison_reelle')
    list_filter = ('statut', 'date_affectation')
    search_fields = ('commande__numero_commande', 'livreur__client__user__last_name', 'livreur__client__user__telephone')
    readonly_fields = ('date_affectation', 'date_modification')
    autocomplete_fields = ('commande', 'livreur', 'affecte_par')
    
    fieldsets = (
        ('Relations', {
            'fields': ('commande', 'livreur', 'affecte_par')
        }),
        ('Statut', {
            'fields': ('statut', 'motif_echec')
        }),
        ('Dates', {
            'fields': ('date_affectation', 'date_livraison_reelle')
        }),
        ('Informations livraison', {
            'fields': ('frais_livraison',)
        }),
        ('Notes', {
            'fields': ('note_admin', 'note_livreur')
        }),
        ('Dates modification', {
            'fields': ('date_modification',),
            'classes': ('collapse',)
        }),
    )
    
    def commande_numero(self, obj):
        return obj.commande.numero_commande
    commande_numero.short_description = 'Commande'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('commande', 'livreur', 'livreur__client', 'livreur__client__user', 'affecte_par')


# Enregistrement simple pour les modèles sans configuration spéciale
@admin.register(PanierLigneParfum)
class PanierLigneParfumAdmin(admin.ModelAdmin):
    list_display = ('id', 'panier', 'parfum', 'quantite', 'sous_total')
    autocomplete_fields = ('panier', 'parfum')


@admin.register(PanierLigneParfumPerso)
class PanierLigneParfumPersoAdmin(admin.ModelAdmin):
    list_display = ('id', 'panier', 'parfum_personnalise', 'quantite', 'sous_total')
    autocomplete_fields = ('panier', 'parfum_personnalise')


@admin.register(PanierLigneAccessoire)
class PanierLigneAccessoireAdmin(admin.ModelAdmin):
    list_display = ('id', 'panier', 'accessoire', 'quantite', 'sous_total')
    autocomplete_fields = ('panier', 'accessoire')


@admin.register(CommandeLigneParfum)
class CommandeLigneParfumAdmin(admin.ModelAdmin):
    list_display = ('id', 'commande', 'nom_snapshot', 'quantite', 'remise_ligne', 'sous_total')
    autocomplete_fields = ('commande',)


@admin.register(CommandeLigneParfumPerso)
class CommandeLigneParfumPersoAdmin(admin.ModelAdmin):
    list_display = ('id', 'commande', 'parfum_personnalise', 'quantite', 'prix_snapshot', 'sous_total', 'statut_laboratoire')
    autocomplete_fields = ('commande', 'parfum_personnalise')


@admin.register(CommandeLigneAccessoire)
class CommandeLigneAccessoireAdmin(admin.ModelAdmin):
    list_display = ('id', 'commande', 'nom_snapshot', 'quantite', 'remise_ligne', 'sous_total')
    autocomplete_fields = ('commande',)