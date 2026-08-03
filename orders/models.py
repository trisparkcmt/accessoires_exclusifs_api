from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import random
import string



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
        total_produit_fini_essence = sum(ligne.sous_total for ligne in self.lignes_produit_fini_essence.all())
        total_essence_personnalisee = sum(ligne.sous_total for ligne in self.lignes_essence_personnalisee.all())
        total_diffuseurs = sum(ligne.sous_total for ligne in self.lignes_diffuseurs.all())
        
        self.sous_total = total_parfums + total_persos + total_accessoires + total_produit_fini_essence + total_essence_personnalisee + total_diffuseurs
        
        # Recalculate discount: verify promo code validity and reapply discount
        self.remise_montant = Decimal('0')
        self.remise_pourcentage = Decimal('0')
        
        if self.code_promo_applique:
            # 1. Chercher si c'est un code promo admin actif
            promo_admin = CodePromoAdmin.objects.filter(
                code__iexact=self.code_promo_applique, 
                est_actif=True
            ).first()
            
            # 2. Chercher si c'est un code prestataire actif
            from utilisateur.models import Prestataire
            prestataire = Prestataire.objects.filter(
                code_promo__iexact=self.code_promo_applique,
                statut='actif'
            ).first()
            
            # Vérifier l'usage unique pour le code admin
            usage_unique_ok = True
            if promo_admin and self.client:
                usage_unique_ok = not Commande.objects.filter(
                    client=self.client, 
                    code_promo_utilise__iexact=self.code_promo_applique
                ).exclude(statut__in=['annulée', 'remboursée']).exists()
            
            if promo_admin and self.client and usage_unique_ok and promo_admin.clients_autorises.filter(pk=self.client.pk).exists():
                self.prestataire = None
                self.remise_pourcentage = promo_admin.reduction_pourcentage
                self.remise_montant = self.sous_total * (self.remise_pourcentage / 100)
            elif prestataire:
                self.prestataire = prestataire
                self.remise_pourcentage = prestataire.reduction_client_pourcentage
                self.remise_montant = self.sous_total * (self.remise_pourcentage / 100)
            else:
                # Code promo invalide, expiré, déjà utilisé ou non autorisé
                self.code_promo_applique = ""
                self.prestataire = None
        elif self.prestataire:
            # Apply prestataire discount if no promo code
            if self.prestataire.statut == 'actif':
                self.remise_pourcentage = self.prestataire.reduction_client_pourcentage
                self.remise_montant = self.sous_total * (self.remise_pourcentage / 100)
            else:
                self.prestataire = None
        
        self.total = self.sous_total - self.remise_montant + self.frais_livraison
        self.save(update_fields=['sous_total', 'remise_montant', 'remise_pourcentage', 'code_promo_applique', 'prestataire', 'total'])
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



class PanierLigneProduitFiniEssence(models.Model):
    panier = models.ForeignKey('orders.Panier', on_delete=models.CASCADE, related_name='lignes_produit_fini_essence')
    produit_fini_essence = models.ForeignKey('catalogue.ProduitFiniEssence', on_delete=models.CASCADE)

    quantite = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        db_table = 'panier_ligne_produit_fini_essence'
    
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



class PanierLigneEssencePersonnalisee(models.Model):
    panier = models.ForeignKey('orders.Panier', on_delete=models.CASCADE, related_name='lignes_essence_personnalisee')
    essence_personnalisee = models.ForeignKey('laboratoire.EssencePersonnalisee', on_delete=models.CASCADE)
    quantite = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    prix_calcule = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        db_table = 'panier_ligne_essence_personnalisee'
    
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
# ==============================    ==============================
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
        
    ]
    COMMISSION_STATUT_CHOICES = [
        ('non_versée', 'Non versée'),
        ('versée', 'Versée'),
        ('annulée', 'Annulée'),
    ]

    
    numero_commande = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey('utilisateur.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes')
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
    
    livraison_nom_complet = models.CharField(max_length=200, blank=True, default='')
    livraison_quartier = models.CharField(max_length=200, blank=True)
    livraison_ville = models.CharField(max_length=100, blank=True)
    livraison_telephone = models.CharField(max_length=20, blank=True, default='')
    
   
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
        email = self.client.user.email if self.client else "Invité"
        return f"{self.numero_commande} - {email} - {self.statut}"

    def recalculer_commande(self):
        total_parfums = sum(ligne.sous_total for ligne in self.lignes_parfums.all())
        total_persos = sum(ligne.sous_total for ligne in self.lignes_parfums_perso.all())
        total_accessoires = sum(ligne.sous_total for ligne in self.lignes_accessoires.all())
        total_produits_finis = sum(ligne.sous_total for ligne in self.lignes_produit_fini_essence.all())
        total_essences_perso = sum(ligne.sous_total for ligne in self.lignes_essence_personnalisee.all())
        total_diffuseurs = sum(ligne.sous_total for ligne in self.lignes_diffuseurs.all())
        
        self.sous_total = total_parfums + total_persos + total_accessoires + total_produits_finis + total_essences_perso + total_diffuseurs

        
        if self.prestataire:
            self.remise_code_promo = self.sous_total * (self.prestataire.reduction_client_pourcentage / 100)
            self.commission_montant = self.sous_total * (self.prestataire.taux_commission / 100)
        elif self.code_promo_utilise:
            # Chercher si c'est un code promo admin
            promo_admin = CodePromoAdmin.objects.filter(code__iexact=self.code_promo_utilise, est_actif=True).first()
            
            # Vérifier l'usage unique pour le code admin (en excluant cette commande elle-même)
            usage_unique_ok = True
            if promo_admin and self.client:
                usage_unique_ok = not Commande.objects.filter(
                    client=self.client, 
                    code_promo_utilise__iexact=self.code_promo_utilise
                ).exclude(pk=self.pk).exclude(statut__in=['annulée', 'remboursée']).exists()
                
            if promo_admin and self.client and usage_unique_ok and promo_admin.clients_autorises.filter(pk=self.client.pk).exists():
                self.remise_code_promo = self.sous_total * (promo_admin.reduction_pourcentage / 100)
            else:
                self.remise_code_promo = Decimal('0')
            self.commission_montant = Decimal('0')
        else:
            self.remise_code_promo = Decimal('0')
            self.commission_montant = Decimal('0')
            
        self.total_ttc = self.sous_total - self.remise_code_promo + self.frais_livraison

    def liberer_stocks(self):
        # Pour les matières premières (ingrédients et essences), la règle métier stipule qu'une fois
        # mélangés, ils ne peuvent plus être séparés. On n'effectue donc aucun retour en stock pour eux.
        # Seuls les produits finis standards (Parfums, Accessoires, Produits Finis Essences) sont réintégrés.
        
        # 1. Parfums standard
        for ligne in self.lignes_parfums.all():
            if ligne.mouvement_stock_genere:
                if ligne.parfum:
                    parfum = ligne.parfum
                    parfum.stock_quantite += ligne.quantite
                    parfum.save(update_fields=['stock_quantite'])
                ligne.mouvement_stock_genere = False
                ligne.save(update_fields=['mouvement_stock_genere'])

        # 2. Accessoires standard
        for ligne in self.lignes_accessoires.all():
            if ligne.mouvement_stock_genere:
                if ligne.accessoire:
                    accessoire = ligne.accessoire
                    accessoire.stock_quantite += ligne.quantite
                    accessoire.save(update_fields=['stock_quantite'])
                ligne.mouvement_stock_genere = False
                ligne.save(update_fields=['mouvement_stock_genere'])

        # 3. Produits finis essence standard
        for ligne in self.lignes_produit_fini_essence.all():
            if ligne.mouvement_stock_genere:
                if ligne.produit_fini_essence:
                    prod = ligne.produit_fini_essence
                    quantite_ml = Decimal(str(ligne.quantite)) * Decimal(str(prod.taille_ml))
                    prod.essence.restituer_lots(quantite_ml)
                    # Supprimer les consommations associées
                    ligne.lot_consommations.all().delete()
                ligne.mouvement_stock_genere = False
                ligne.save(update_fields=['mouvement_stock_genere'])

            # 4. Diffuseurs standard
            for ligne in self.lignes_diffuseurs.all():
                if ligne.mouvement_stock_genere:
                    if ligne.diffuseur:
                        diffuseur = ligne.diffuseur
                        diffuseur.stock_quantite += ligne.quantite
                        diffuseur.save(update_fields=['stock_quantite'])
                    ligne.mouvement_stock_genere = False
                    ligne.save(update_fields=['mouvement_stock_genere'])

    def appliquer_stocks(self):
        if self.statut in ['annulée', 'remboursée']:
            return

        # 1. Produits personnalisés : décrémentation lors du passage à "validé"
        if self.statut == 'validé':
            # Parfums personnalisés
            for ligne in self.lignes_parfums_perso.all():
                if not ligne.proportions_mises_a_jour:
                    cost_total = Decimal('0')
                    # Flacon
                    if ligne.parfum_personnalise.flacon:
                        flacon = ligne.parfum_personnalise.flacon
                        flacon.stock_quantite -= ligne.quantite
                        flacon.save(update_fields=['stock_quantite'])
                        cost_total += Decimal(str(ligne.quantite)) * (flacon.prix_achat or Decimal('0'))
                    # Essences
                    p_perso = ligne.parfum_personnalise
                    total_prix_p_perso = p_perso.prix_total if p_perso.prix_total else Decimal('1')
                    for l_perf in p_perso.lignes.all():
                        if l_perf.essence:
                            lot = l_perf.essence
                            quantite_prelevee_ml = Decimal(str(ligne.quantite)) * l_perf.quantite_ml
                            lot.stock_ml -= quantite_prelevee_ml
                            lot.save(update_fields=['stock_ml'])
                            
                            # Calcul de la part de vente et création de la consommation
                            ratio_vente = l_perf.prix_ligne / total_prix_p_perso
                            vente_attribuee = ratio_vente * ligne.sous_total
                            
                            from catalogue.models import LotEssenceConsommation
                            LotEssenceConsommation.objects.create(
                                lot_essence=lot,
                                ligne_parfum_perso=ligne,
                                quantite_ml=quantite_prelevee_ml,
                                prix_vente_attribue=vente_attribuee
                            )
                            cost_total += quantite_prelevee_ml * (lot.prix_achat_par_ml or Decimal('0'))
                        elif l_perf.essence_personnalisee:
                            essence_perso = l_perf.essence_personnalisee
                            for l_ess in essence_perso.lignes.all():
                                ing = l_ess.ingredient
                                quantite_prelevee_ml = Decimal(str(ligne.quantite)) * l_perf.quantite_ml * l_ess.quantite_ml
                                ing.stock_ml -= quantite_prelevee_ml
                                ing.save(update_fields=['stock_ml'])
                                cost_total += quantite_prelevee_ml * (ing.prix_achat_par_ml or Decimal('0'))
                    
                    ligne.prix_achat_total_snapshot = cost_total
                    ligne.proportions_mises_a_jour = True
                    ligne.save(update_fields=['proportions_mises_a_jour', 'prix_achat_total_snapshot'])

            # Essences personnalisées
            for ligne in self.lignes_essence_personnalisee.all():
                if not ligne.proportions_mises_a_jour:
                    cost_total = Decimal('0')
                    essence_perso = ligne.essence_personnalise
                    if essence_perso:
                        for l_ess in essence_perso.lignes.all():
                            ing = l_ess.ingredient
                            quantite_prelevee_ml = Decimal(str(ligne.quantite)) * l_ess.quantite_ml
                            ing.stock_ml -= quantite_prelevee_ml
                            ing.save(update_fields=['stock_ml'])
                            cost_total += quantite_prelevee_ml * (ing.prix_achat_par_ml or Decimal('0'))
                    
                    ligne.prix_achat_total_snapshot = cost_total
                    ligne.proportions_mises_a_jour = True
                    ligne.save(update_fields=['proportions_mises_a_jour', 'prix_achat_total_snapshot'])

        # 2. Produits standards : décrémentation lors du paiement
        if self.statut_paiement == 'payé':
            # Parfums standard
            for ligne in self.lignes_parfums.all():
                if not ligne.mouvement_stock_genere:
                    if ligne.parfum:
                        parfum = ligne.parfum
                        parfum.stock_quantite -= ligne.quantite
                        parfum.save(update_fields=['stock_quantite'])
                        ligne.prix_achat_total_snapshot = Decimal(str(ligne.quantite)) * (parfum.prix_achat or Decimal('0'))
                    ligne.mouvement_stock_genere = True
                    ligne.save(update_fields=['mouvement_stock_genere', 'prix_achat_total_snapshot'])

            # Accessoires standard
            for ligne in self.lignes_accessoires.all():
                if not ligne.mouvement_stock_genere:
                    if ligne.accessoire:
                        accessoire = ligne.accessoire
                        accessoire.stock_quantite -= ligne.quantite
                        accessoire.save(update_fields=['stock_quantite'])
                        ligne.prix_achat_total_snapshot = Decimal(str(ligne.quantite)) * (accessoire.prix_achat or Decimal('0'))
                    ligne.mouvement_stock_genere = True
                    ligne.save(update_fields=['mouvement_stock_genere', 'prix_achat_total_snapshot'])

            # Produits finis essence standard
            for ligne in self.lignes_produit_fini_essence.all():
                if not ligne.mouvement_stock_genere:
                    if ligne.produit_fini_essence:
                        prod = ligne.produit_fini_essence
                        quantite_ml = Decimal(str(ligne.quantite)) * Decimal(str(prod.taille_ml))
                        prelevements = prod.essence.prelever_lots(quantite_ml)
                        
                        # Enregistrer les consommations par lot
                        cost_total = Decimal('0')
                        for lot, prelevement_ml in prelevements:
                            vente_attribuee = (prelevement_ml / quantite_ml) * ligne.sous_total
                            
                            from catalogue.models import LotEssenceConsommation
                            LotEssenceConsommation.objects.create(
                                lot_essence=lot,
                                ligne_produit_fini_essence=ligne,
                                quantite_ml=prelevement_ml,
                                prix_vente_attribue=vente_attribuee
                            )
                            cost_total += prelevement_ml * (lot.prix_achat_par_ml or Decimal('0'))
                        
                        ligne.prix_achat_total_snapshot = cost_total
                    ligne.mouvement_stock_genere = True
                    ligne.save(update_fields=['mouvement_stock_genere', 'prix_achat_total_snapshot'])

                # Diffuseurs standard
                for ligne in self.lignes_diffuseurs.all():
                    if not ligne.mouvement_stock_genere:
                        if ligne.diffuseur:
                            diffuseur = ligne.diffuseur
                            diffuseur.stock_quantite -= ligne.quantite
                            diffuseur.save(update_fields=['stock_quantite'])
                            ligne.prix_achat_total_snapshot = Decimal(str(ligne.quantite)) * (diffuseur.prix_achat or Decimal('0'))
                        ligne.mouvement_stock_genere = True
                        ligne.save(update_fields=['mouvement_stock_genere', 'prix_achat_total_snapshot'])

    def traiter_commissions(self, original):
        from utilisateur.models import CommissionLog, Notification
        
        # Données de l'ancien état
        prev_commission_montant = original.commission_montant if original else Decimal('0')
        
        is_paid = self.statut_paiement == 'payé' and self.statut not in ['annulée', 'remboursée']
        
        if is_paid:
            if self.prestataire:
                if self.commission_statut == 'non_versée':
                    # Attribution de la commission
                    self.prestataire.solde_commission += self.commission_montant
                    self.prestataire.save(update_fields=['solde_commission'])
                    
                    CommissionLog.objects.create(
                        prestataire=self.prestataire,
                        type_operation='vente',
                        montant=self.commission_montant,
                        reference_commande=self.numero_commande,
                        description=f"Commission sur vente pour la commande {self.numero_commande}"
                    )
                    
                    self.commission_statut = 'versée'
                    Commande.objects.filter(pk=self.pk).update(commission_statut='versée')
                    
                    # Notification prestataire
                    code_msg = (
                        f" grâce à votre code promo {self.code_promo_utilise}"
                        if self.code_promo_utilise
                        else ""
                    )
                    Notification.objects.create(
                        recipient=self.prestataire.user,
                        type='commission',
                        title="Commission reçue !",
                        message=(
                            f"Vous avez reçu {self.commission_montant} FCFA de commission"
                            f"{code_msg} pour la commande {self.numero_commande}."
                        ),
                        url=f'/api/v1/orders/commandes/{self.numero_commande}/',
                        metadata={
                            'commande_id': self.pk,
                            'numero_commande': self.numero_commande,
                            'commission_montant': str(self.commission_montant),
                            'code_promo': self.code_promo_utilise or '',
                        },
                    )
                elif self.commission_statut == 'versée' and self.commission_montant != prev_commission_montant:
                    # Ajustement si modification de la commande
                    diff = self.commission_montant - prev_commission_montant
                    self.prestataire.solde_commission += diff
                    self.prestataire.save(update_fields=['solde_commission'])
                    
                    CommissionLog.objects.create(
                        prestataire=self.prestataire,
                        type_operation='bonus',
                        montant=diff,
                        reference_commande=self.numero_commande,
                        description=f"Ajustement de commission pour la commande {self.numero_commande}"
                    )
            else:
                # Si le prestataire a été retiré après versement
                if self.commission_statut == 'versée' and original and original.prestataire:
                    original.prestataire.solde_commission -= prev_commission_montant
                    original.prestataire.save(update_fields=['solde_commission'])
                    
                    CommissionLog.objects.create(
                        prestataire=original.prestataire,
                        type_operation='bonus',
                        montant=-prev_commission_montant,
                        reference_commande=self.numero_commande,
                        description=f"Annulation de commission suite au retrait du code promo de la commande {self.numero_commande}"
                    )
                    self.commission_statut = 'annulée'
                    Commande.objects.filter(pk=self.pk).update(commission_statut='annulée')
                    
                    # Notification prestataire pour annulation/retrait
                    Notification.objects.create(
                        recipient=original.prestataire.user,
                        type='commission',
                        title="Commission retirée",
                        message=f"La commission de {prev_commission_montant} FCFA pour la commande {self.numero_commande} a été retirée suite à la modification du code promo."
                    )
        else:
            # Commande non payée, annulée ou remboursée
            if self.commission_statut == 'versée':
                prestataire_obj = self.prestataire or (original.prestataire if original else None)
                if prestataire_obj:
                    prestataire_obj.solde_commission -= prev_commission_montant
                    prestataire_obj.save(update_fields=['solde_commission'])
                    
                    CommissionLog.objects.create(
                        prestataire=prestataire_obj,
                        type_operation='bonus',
                        montant=-prev_commission_montant,
                        reference_commande=self.numero_commande,
                        description=f"Annulation de commission suite à l'annulation/remboursement de la commande {self.numero_commande}"
                    )
                    
                    # Notification prestataire pour remboursement / annulation
                    Notification.objects.create(
                        recipient=prestataire_obj.user,
                        type='commission',
                        title="Commission annulée",
                        message=f"La commission de {prev_commission_montant} FCFA pour la commande {self.numero_commande} a été retirée suite à l'annulation ou au remboursement de la commande."
                    )
                self.commission_statut = 'annulée'
                Commande.objects.filter(pk=self.pk).update(commission_statut='annulée')
            elif self.statut in ['annulée', 'remboursée'] and self.commission_statut == 'non_versée':
                self.commission_statut = 'annulée'
                Commande.objects.filter(pk=self.pk).update(commission_statut='annulée')

    def traiter_livreur_notification(self, original):
        from utilisateur.models import Notification

        old_livreur = original.livreur if original else None
        old_statut = original.statut if original else None

        if self.livreur and self.livreur != old_livreur:
            Notification.objects.create(
                recipient=self.livreur.user,
                type='livreur_commande_assignee',
                title="Nouvelle commande assignée",
                message=(
                    f"La commande {self.numero_commande} vous a été assignée.\n\n"
                    f"Client : {self.livraison_nom_complet}\n"
                    f"Adresse : {self.livraison_quartier}, {self.livraison_ville}\n"
                    f"Téléphone : {self.livraison_telephone}\n"
                    f"Total : {self.total_ttc} FCFA"
                ),
                url=f'/api/v1/orders/commandes/{self.numero_commande}/',
                metadata={
                    'commande_id': self.pk,
                    'numero_commande': self.numero_commande,
                    'livreur_id': self.livreur.pk,
                    'montant': str(self.total_ttc),
                },
            )

            from orders.models import AffectationLivraison
            AffectationLivraison.objects.get_or_create(
                commande=self,
                livreur=self.livreur,
                defaults={'statut': 'assignée'},
            )

            if not self.statut_livraison or self.statut_livraison == 'en_attente_affectation':
                self.statut_livraison = 'assignée'
                Commande.objects.filter(pk=self.pk).update(statut_livraison='assignée')

        livreur_annulation = self.livreur or old_livreur
        if (
            self.statut == 'annulée'
            and old_statut != 'annulée'
            and livreur_annulation
        ):
            Notification.objects.create(
                recipient=livreur_annulation.user,
                type='livreur_commande_annulee',
                title="Commande annulée",
                message=(
                    f"La commande {self.numero_commande} qui vous était assignée a été annulée.\n\n"
                    f"Client : {self.livraison_nom_complet}"
                ),
                url=f'/api/v1/orders/commandes/{self.numero_commande}/',
                metadata={
                    'commande_id': self.pk,
                    'numero_commande': self.numero_commande,
                    'livreur_id': livreur_annulation.pk,
                },
            )

    def traiter_notification_parfum_perso(self, original):
        """Notifie le laboratoire quand une commande avec parfum personnalisé est validée."""
        from django.contrib.auth import get_user_model
        from utilisateur.models import Notification

        old_statut = original.statut if original else None
        if self.statut != 'validé' or old_statut == 'validé':
            return

        has_parfum_perso = (
            self.lignes_parfums_perso.exists()
            or self.lignes_essence_personnalisee.exists()
        )
        if not has_parfum_perso:
            return

        User = get_user_model()
        admin_users = User.objects.filter(is_staff=True, is_active=True)
        client_email = self.client.user.email if self.client else 'Invité'

        for admin in admin_users:
            Notification.objects.create(
                recipient=admin,
                type='commande_parfum_perso',
                title="Commande parfum personnalisé à traiter",
                message=(
                    f"La commande {self.numero_commande} contient un parfum personnalisé "
                    f"et vient d'être validée.\n\n"
                    f"Client : {client_email}\n"
                    f"Montant : {self.total_ttc} FCFA\n"
                    f"À traiter par le laboratoire."
                ),
                url=f'/api/v1/orders/commandes/{self.numero_commande}/',
                metadata={
                    'commande_id': self.pk,
                    'numero_commande': self.numero_commande,
                    'client_email': client_email,
                },
            )

    def save(self, *args, **kwargs):
        if not self.numero_commande:
            for _ in range(10):
                code = f"CMD-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
                if not Commande.objects.filter(numero_commande=code).exists():
                    self.numero_commande = code
                    break
        
        original = None
        if self.pk:
            try:
                original = Commande.objects.get(pk=self.pk)
            except Commande.DoesNotExist:
                pass
                
        # Passage automatique à livrée si la commande est payée
        if self.statut_paiement == 'payé':
            self.statut_livraison = 'livrée'
            self.statut = 'livrée'
            from django.utils import timezone
            if not self.date_livraison_reelle:
                self.date_livraison_reelle = timezone.now()
        
        # 1. Recalculer le total
        # Remarque : recalculer_commande s'appuie sur les relations inverses. Si la commande est nouvelle,
        # elle n'a pas encore de lignes associées en base, le calcul donnera 0. C'est normal, le recalcul
        # sera relancé après l'ajout des lignes par le view/serializer.
        if self.pk:
            self.recalculer_commande()
            
        super().save(*args, **kwargs)
        
        # 2. Gestion des stocks
        with transaction.atomic():
            self.liberer_stocks()
            self.appliquer_stocks()
            
        # 3. Commissions et Notifications
        self.traiter_commissions(original)
        self.traiter_livreur_notification(original)
        self.traiter_notification_parfum_perso(original)

        # 4. Génération / régénération de la facture PDF
        # Déclenché uniquement quand statut_paiement devient ou reste "payé"
        if self.statut_paiement == 'payé':
            vient_detre_paye = (
                original is None or original.statut_paiement != 'payé'
            )
            commande_modifiee_apres_paiement = (
                original is not None
                and original.statut_paiement == 'payé'
                and self.total_ttc != original.total_ttc
            )
            if vient_detre_paye or commande_modifiee_apres_paiement:
                try:
                    from orders.services import generer_facture
                    generer_facture(self)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[FACTURE] Erreur génération facture pour {self.numero_commande}: {e}")



class CommandeLigneParfum(models.Model):
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_parfums')
    parfum = models.ForeignKey('catalogue.Parfum', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    nom_snapshot = models.CharField(max_length=200)
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    remise_ligne = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat_total_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Coût d'achat total réel pour cette ligne (historisé)")
    mouvement_stock_genere = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'commande_ligne_parfum'
    
    def save(self, *args, **kwargs):
        self.sous_total = (self.prix_unitaire_snapshot - self.remise_ligne) * self.quantite
        super().save(*args, **kwargs)


class CommandeProduitFiniEssence(models.Model):
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_produit_fini_essence')
    produit_fini_essence = models.ForeignKey('catalogue.ProduitFiniEssence', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    nom_snapshot = models.CharField(max_length=200)
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    remise_ligne = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat_total_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Coût d'achat total réel pour cette ligne (historisé)")
    mouvement_stock_genere = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'commande_produit_fini_essence'
    
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
    prix_achat_total_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Coût d'achat total réel pour cette ligne (historisé)")
    statut_laboratoire = models.CharField(max_length=30, choices=STATUT_LABO_CHOICES, default='en_attente')
    proportions_mises_a_jour = models.BooleanField(default=False, help_text="True quand stock essence et flacon décrémentés")
    note_laboratoire = models.TextField(blank=True)
    
    class Meta:
        db_table = 'commande_ligne_parfum_perso'
    
    def save(self, *args, **kwargs):
        self.sous_total = self.prix_snapshot * self.quantite
        super().save(*args, **kwargs)






#  ajouttt--------------------------------------------
class CommandeLigneEssencePersonnalisee(models.Model):
    STATUT_LABO_CHOICES = [
        ('en_attente', 'En attente'),
        ('validée', 'Validée'),
 
        ('livrée', 'Livrée'),
    ]
    
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_essence_personnalisee')
    essence_personnalise = models.ForeignKey('laboratoire.EssencePersonnalisee', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat_total_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Coût d'achat total réel pour cette ligne (historisé)")
    statut_laboratoire = models.CharField(max_length=30, choices=STATUT_LABO_CHOICES, default='en_attente')
    proportions_mises_a_jour = models.BooleanField(default=False, help_text="True quand stock essence et flacon décrémentés")
    note_laboratoire = models.TextField(blank=True)
    
    class Meta:
        db_table = 'commande_ligne_essence_personnalisee'
    
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
    prix_achat_total_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Coût d'achat total réel pour cette ligne (historisé)")
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


# ============================================================
# FACTURE
# ============================================================
class Facture(models.Model):
    """
    Facture PDF générée automatiquement dès qu'une commande est payée.
    Le numéro de suivi suit le format FAC-YYYY-NNNN (ex: FAC-2026-0042).
    """
    commande = models.OneToOneField(
        'orders.Commande',
        on_delete=models.CASCADE,
        related_name='facture',
        verbose_name='Commande'
    )
    numero_facture = models.CharField(
        max_length=30,
        unique=True,
        verbose_name='Numéro de facture'
    )
    fichier_pdf = models.FileField(
        upload_to='factures/%Y/%m/',
        verbose_name='Fichier PDF'
    )
    date_emission = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'émission"
    )
    envoye_par_email = models.BooleanField(
        default=False,
        verbose_name='Email envoyé'
    )
    email_envoye_a = models.EmailField(
        blank=True,
        verbose_name='Email destinataire'
    )
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'facture'
        verbose_name = 'Facture'
        verbose_name_plural = 'Factures'
        ordering = ['-date_emission']

    def __str__(self):
        return f"{self.numero_facture} — {self.commande.numero_commande}"

    @classmethod
    def generer_numero(cls):
        """Génère le prochain numéro FAC-YYYY-NNNN auto-incrémenté par année."""
        from django.db.models import Max
        from django.utils import timezone

        annee = timezone.now().year
        prefix = f'FAC-{annee}-'
        dernier_numero = cls.objects.filter(numero_facture__startswith=prefix).aggregate(
            max_numero=Max('numero_facture')
        )['max_numero']

        if not dernier_numero:
            return f'{prefix}0001'

        try:
            dernier_suffix = int(dernier_numero.split('-')[-1])
        except (IndexError, ValueError):
            dernier_suffix = cls.objects.filter(numero_facture__startswith=prefix).count()

        return f'{prefix}{str(dernier_suffix + 1).zfill(4)}'


class CodePromoAdmin(models.Model):
    code = models.CharField(max_length=50, unique=True)
    reduction_pourcentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    est_actif = models.BooleanField(default=True)
    clients_autorises = models.ManyToManyField('utilisateur.Client', related_name='codes_promo_admin', blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'code_promo_admin'
        verbose_name = 'Code Promo Admin'
        verbose_name_plural = 'Codes Promo Admin'

    def __str__(self):
        return f"{self.code} (-{self.reduction_pourcentage}%)"


# ============================================================
# PANIER & COMMANDE DIFFUSEURS
# ============================================================
class PanierLigneDiffuseurParfum(models.Model):
    panier = models.ForeignKey('orders.Panier', on_delete=models.CASCADE, related_name='lignes_diffuseurs')
    diffuseur = models.ForeignKey('catalogue.DiffuseurParfum', on_delete=models.CASCADE, related_name='paniers_lignes')
    quantite = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    prix_calcule = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'panier_ligne_diffuseur_parfum'
        unique_together = [['panier', 'diffuseur']]

    def save(self, *args, **kwargs):
        self.prix_calcule = self.diffuseur.prix_actuel
        self.sous_total = self.prix_calcule * self.quantite
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantite}x {self.diffuseur.nom}"


class CommandeLigneDiffuseurParfum(models.Model):
    commande = models.ForeignKey('orders.Commande', on_delete=models.CASCADE, related_name='lignes_diffuseurs')
    diffuseur = models.ForeignKey('catalogue.DiffuseurParfum', on_delete=models.SET_NULL, null=True, related_name='commandes_lignes')
    nom_snapshot = models.CharField(max_length=200)
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    remise_ligne = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sous_total = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat_total_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Coût d'achat total réel pour cette ligne (historisé)"
    )
    mouvement_stock_genere = models.BooleanField(default=False)

    class Meta:
        db_table = 'commande_ligne_diffuseur_parfum'

    def save(self, *args, **kwargs):
        self.sous_total = (self.prix_unitaire_snapshot - self.remise_ligne) * self.quantite
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantite}x {self.nom_snapshot}"
