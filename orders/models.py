from django.db import models
from django.core.validators import MinValueValidator



# ============================================================
# PANIER
# ============================================================
class Panier(models.Model):
    STATUT_CHOICES = [
        ('actif', 'Actif'),
        
        ('converti', 'Converti'),
    ]
    
    client = models.ForeignKey('utilisateur.Client', on_delete=models.CASCADE, null=True, blank=True, related_name='paniers')
    
    code_promo_applique = models.CharField(max_length=50, blank=True)
    prestataire = models.ForeignKey('utilisateur.Prestataire', on_delete=models.SET_NULL, null=True, blank=True, related_name='paniers')
    remise_montant = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remise_pourcentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frais_livraison = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'panier'
        verbose_name = 'Panier'
        verbose_name_plural = 'Paniers'
    
    def __str__(self):
        if self.client:
            return f"Panier de {self.client.user.email}"
        return f"Panier #{self.id}"
    
    def recalculer_total(self):
        total_parfums = sum(ligne.sous_total for ligne in self.lignes_parfums.all())
        total_persos = sum(ligne.sous_total for ligne in self.lignes_parfums_perso.all())
        total_accessoires = sum(ligne.sous_total for ligne in self.lignes_accessoires.all())
        
        self.sous_total = total_parfums + total_persos + total_accessoires
        
        if self.remise_pourcentage:
            self.remise_montant = self.sous_total * (self.remise_pourcentage / 100)
        
        self.total = self.sous_total - self.remise_montant + self.frais_livraison
        self.save(update_fields=['sous_total', 'remise_montant', 'total'])
        return self.total


class PanierLigneParfum(models.Model):
    panier = models.ForeignKey('orders.Panier', on_delete=models.CASCADE, related_name='lignes_parfums')
    parfum = models.ForeignKey('catalogue.Parfum', on_delete=models.CASCADE)
    quantite = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        db_table = 'panier_ligne_parfum'
    
    def save(self, *args, **kwargs):
        self.sous_total = self.prix_unitaire_snapshot * self.quantite
        super().save(*args, **kwargs)


class PanierLigneParfumPerso(models.Model):
    panier = models.ForeignKey('orders.Panier', on_delete=models.CASCADE, related_name='lignes_parfums_perso')
    parfum_personnalise = models.ForeignKey('laboratoire.ParfumPersonnalise', on_delete=models.CASCADE)
    quantite = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    prix_calcule = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    note_client = models.TextField(blank=True)
    
    class Meta:
        db_table = 'panier_ligne_parfum_perso'
    
    def save(self, *args, **kwargs):
        self.sous_total = self.prix_calcule * self.quantite
        super().save(*args, **kwargs)


class PanierLigneAccessoire(models.Model):
    panier = models.ForeignKey('orders.Panier', on_delete=models.CASCADE, related_name='lignes_accessoires')
    accessoire = models.ForeignKey('catalogue.Accessoire', on_delete=models.CASCADE)
    quantite = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        db_table = 'panier_ligne_accessoire'
    
    def save(self, *args, **kwargs):
        self.sous_total = self.prix_unitaire_snapshot * self.quantite
        super().save(*args, **kwargs)


# ============================================================
# COMMANDE
# ============================================================
class Commande(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('validé', 'validé'),
        ('annulée', 'Annulée'),
        ('remboursée', 'Remboursée'),
    ]
    STATUT_LIVRAISON_CHOICES = [
        ('en_attente_affectation', 'En attente affectation'),
        ('assignée', 'Assignée'),
        
        ('livrée', 'Livrée'),
        ('échouée', 'Échouée'),
    ]
    STATUT_PAIEMENT_CHOICES = [
        ('en_attente', 'En attente'),
        ('payé', 'Payé'),
        ('échoué', 'Échoué'),
        ('remboursé', 'Remboursé'),
    ]
    COMMISSION_STATUT_CHOICES = [
        ('non_versée', 'Non versée'),
        ('versée', 'Versée'),
        ('annulée', 'Annulée'),
    ]
    METHODE_PAIEMENT_CHOICES = [
        ('cash', 'cash'),
        ('mobile_money', 'mobile_money'),
    ]
    
    numero_commande = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey('utilisateur.Client', on_delete=models.CASCADE, related_name='commandes')
    prestataire = models.ForeignKey('utilisateur.Prestataire', on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes')
    panier = models.ForeignKey('orders.Panier', on_delete=models.SET_NULL, null=True, blank=True, related_name='commande_associee')
    livreur = models.ForeignKey('utilisateur.Livreur', on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes')
    statut = models.CharField(max_length=30, choices=STATUT_CHOICES, default='en_attente')
    statut_livraison = models.CharField(max_length=30, choices=STATUT_LIVRAISON_CHOICES, null=True, blank=True)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    remise_code_promo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    code_promo_utilise = models.CharField(max_length=50, blank=True)
    frais_livraison = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_ttc = models.DecimalField(max_digits=10, decimal_places=2)
    commission_montant = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commission_statut = models.CharField(max_length=20, choices=COMMISSION_STATUT_CHOICES, default='non_versée')
    
    livraison_nom_complet = models.CharField(max_length=200)
    livraison_quartier = models.CharField(max_length=200, blank=True)
    livraison_ville = models.CharField(max_length=100, blank=True)
    livraison_telephone = models.CharField(max_length=20)
    
    methode_paiement = models.CharField(max_length=50, choices=METHODE_PAIEMENT_CHOICES)
    statut_paiement = models.CharField(max_length=20, choices=STATUT_PAIEMENT_CHOICES, default='en_attente')

    date_livraison_estimee = models.DateField(null=True, blank=True)
    date_livraison_reelle = models.DateTimeField(null=True, blank=True)
    
    note_client = models.TextField(blank=True)
    note_interne = models.TextField(blank=True)
    motif_echec_livraison = models.TextField(blank=True, null=True)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'commande'
        verbose_name = 'Commande'
        verbose_name_plural = 'Commandes'
    
    def __str__(self):
        return f"{self.numero_commande} - {self.client.user.email} - {self.statut}"


class CommandeLigneParfum(models.Model):
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_parfums')
    parfum = models.ForeignKey('catalogue.Parfum', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    nom_snapshot = models.CharField(max_length=200)
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    remise_ligne = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    mouvement_stock_genere = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'commande_ligne_parfum'
    
    def save(self, *args, **kwargs):
        self.sous_total = (self.prix_unitaire_snapshot - self.remise_ligne) * self.quantite
        super().save(*args, **kwargs)


class CommandeLigneParfumPerso(models.Model):
    STATUT_LABO_CHOICES = [
        ('en_attente', 'En attente'),
        ('validée', 'Validée'),
 
        ('livrée', 'Livrée'),
    ]
    
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_parfums_perso')
    parfum_personnalise = models.ForeignKey('laboratoire.ParfumPersonnalise', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    statut_laboratoire = models.CharField(max_length=30, choices=STATUT_LABO_CHOICES, default='en_attente')
    proportions_mises_a_jour = models.BooleanField(default=False, help_text="True quand stock essence et flacon décrémentés")
    note_laboratoire = models.TextField(blank=True)
    
    class Meta:
        db_table = 'commande_ligne_parfum_perso'
    
    def save(self, *args, **kwargs):
        self.sous_total = self.prix_snapshot * self.quantite
        super().save(*args, **kwargs)


class CommandeLigneAccessoire(models.Model):
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_accessoires')
    accessoire = models.ForeignKey('catalogue.Accessoire', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    nom_snapshot = models.CharField(max_length=200)
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    remise_ligne = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    mouvement_stock_genere = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'commande_ligne_accessoire'
    
    def save(self, *args, **kwargs):
        self.sous_total = (self.prix_unitaire_snapshot - self.remise_ligne) * self.quantite
        super().save(*args, **kwargs)


class AffectationLivraison(models.Model):
    STATUT_CHOICES = [
        ('assignée', 'Assignée'),
       
        ('livrée', 'Livrée'),
        ('échouée', 'Échouée'),
     
    ]
    
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='affectations')
    livreur = models.ForeignKey('utilisateur.Livreur', on_delete=models.CASCADE, related_name='affectations')
    affecte_par = models.ForeignKey('utilisateur.User', on_delete=models.SET_NULL, null=True, related_name='affectations_faites')
    statut = models.CharField(max_length=30, choices=STATUT_CHOICES, default='assignée')
    date_affectation = models.DateTimeField(auto_now_add=True)
    date_livraison_reelle = models.DateTimeField(null=True, blank=True)

  
    frais_livraison = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    motif_echec = models.TextField(blank=True)
    
    note_admin = models.TextField(blank=True)
    note_livreur = models.TextField(blank=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'affectation_livraison'
        verbose_name = 'Affectation de livraison'
        verbose_name_plural = 'Affectations de livraisons'
    
    def __str__(self):
        return f"Livraison #{self.commande.numero_commande} - {self.livreur.nom} ({self.statut})"
