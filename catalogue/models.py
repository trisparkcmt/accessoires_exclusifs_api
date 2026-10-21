from django.db import models
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
import random
import string

# UTILITAIRE — chemin dynamique pour les uploads

def upload_to_parfum(instance, filename):
    """Range les images dans media/parfums/{slug}/"""
    return f'parfums/{instance.slug}/{filename}'
 
def upload_to_parfum_galerie(instance, filename):
    return f'parfums/{instance.slug}/galerie/{filename}'

def upload_to_essence_galerie(instance, filename):
    # Gère instance = Essence ou ProduitFiniEssence
    ref = getattr(instance, 'code_reference', None) or instance.essence.code_reference
    return f'essences/{ref}/galerie/{filename}'

def upload_to_essence(instance, filename):
    # Gère instance = Essence ou ProduitFiniEssence
    ref = getattr(instance, 'code_reference', None) or instance.essence.code_reference
    return f'essences/{ref}/{filename}'
 
def upload_to_accessoire(instance, filename):
    return f'accessoires/{instance.slug}/{filename}'
 
def upload_to_accessoire_galerie(instance, filename):
    return f'accessoires/{instance.slug}/galerie/{filename}'
 
def upload_to_flacon(instance, filename):
    return f'flacons/{instance.reference_sku}/{filename}'
 
def upload_to_flacon_galerie(instance, filename):
    return f'flacons/{instance.reference_sku}/galerie/{filename}'
 
def upload_to_categorie(instance, filename):
    return f'categories/{instance.slug}/{filename}'
 
def upload_to_type_accessoire(instance, filename):
    return f'types/accessoires/{instance.slug}/{filename}'
 
def upload_to_type_flacon(instance, filename):
    return f'types/flacons/{instance.pk}/{filename}'


class EntrepriseInfo(models.Model):
    nom = models.CharField(max_length=255)
    jours_ouverture = models.JSONField(default=list, blank=True)
    telephone_principal = models.CharField(max_length=30, blank=True)
    telephone_secondaire = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    localisation = models.CharField(max_length=500, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'entreprise_info'
        verbose_name = 'Informations entreprise'
        verbose_name_plural = 'Informations entreprise'

    def __str__(self):
        return self.nom or 'Informations entreprise'


#Favoris 
class Favori(models.Model):
    client = models.ForeignKey('utilisateur.Client', on_delete=models.CASCADE, related_name='favoris')
    parfum = models.ForeignKey('catalogue.Parfum', on_delete=models.CASCADE, null=True, blank=True)
    accessoire = models.ForeignKey('catalogue.Accessoire', on_delete=models.CASCADE, null=True, blank=True)
    produit_fini_essence = models.ForeignKey('catalogue.ProduitFiniEssence', on_delete=models.CASCADE, null=True, blank=True, related_name='favoris')
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favori'
        verbose_name = 'Favori'
        verbose_name_plural = 'Favoris'
        constraints = [
            models.UniqueConstraint(fields=['client', 'parfum'], condition=models.Q(parfum__isnull=False), name='unique_favori_parfum'),
            models.UniqueConstraint(fields=['client', 'accessoire'], condition=models.Q(accessoire__isnull=False), name='unique_favori_accessoire'),
            models.UniqueConstraint(fields=['client', 'produit_fini_essence'], condition=models.Q(produit_fini_essence__isnull=False), name='unique_favori_produit_fini_essence'),
        ]

    def __str__(self):
        if self.parfum:
            produit = self.parfum.nom
        elif self.accessoire:
            produit = self.accessoire.nom
        elif self.produit_fini_essence:
            produit = f"{self.produit_fini_essence.essence.nom} - {self.produit_fini_essence.taille_ml}ml"
        else:
            produit = '(sans produit)'
        return f"{self.client.user.email} - {produit}"


# ============================================================
# TAGS CENTRALISÉS
# ============================================================
# TAGS CENTRALISÉS
# ============================================================
class Tag(models.Model):
    """
    Table centralisée pour les types/catégories de tags définis par l'administrateur
    Exemples de nom : Sillage, Tenue, Famille olfactive, Saison, Occasion, Matériau
    """
    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, null=True, blank=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tag'
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
    
    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)


class TagParfum(models.Model):
    """
    Table de liaison entre Parfum et Tag (ManyToMany avec valeur spécifique au parfum)
    """
    parfum = models.ForeignKey('Parfum', on_delete=models.CASCADE, related_name='tags_associes')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='parfums_associes')
    valeur = models.TextField(blank=True, default='', help_text="Valeur du tag pour ce parfum (ex: Élevée, Gourmand, etc.)")
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tag_parfum'
        verbose_name = 'Tag de parfum'
        verbose_name_plural = 'Tags de parfums'
        unique_together = [['parfum', 'tag']]
    
    def __str__(self):
        return f"{self.parfum.nom} → {self.tag.nom}: {self.valeur}"


class TagEssence(models.Model):
    """
    Table de liaison entre Essence et Tag (ManyToMany avec valeur spécifique à l'essence)
    """
    essence = models.ForeignKey('Essence', on_delete=models.CASCADE, related_name='tags_associes')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='essences_associes')
    valeur = models.TextField(blank=True, default='', help_text="Valeur du tag pour cette essence")
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tag_essence'
        verbose_name = 'Tag d\'essence'
        verbose_name_plural = 'Tags d\'essences'
        unique_together = [['essence', 'tag']]
    
    def __str__(self):
        return f"{self.essence.nom} → {self.tag.nom}: {self.valeur}"


class TagAccessoire(models.Model):
    """
    Table de liaison entre Accessoire et Tag (ManyToMany avec valeur spécifique à l'accessoire)
    """
    accessoire = models.ForeignKey('Accessoire', on_delete=models.CASCADE, related_name='tags_associes')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='accessoires_associes')
    valeur = models.TextField(blank=True, default='', help_text="Valeur du tag pour cet accessoire")
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tag_accessoire'
        verbose_name = 'Tag d\'accessoire'
        verbose_name_plural = 'Tags d\'accessoires'
        unique_together = [['accessoire', 'tag']]
    
    def __str__(self):
        return f"{self.accessoire.nom} → {self.tag.nom}: {self.valeur}"


# ============================================================
# CATALOGUE PARFUMS
# ============================================================
class CategorieParfum(models.Model):
    nom = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to=upload_to_categorie,blank=True, null=True,
        help_text="Image de la catégorie (jpg, png, webp)"
    )

    ordre_affichage = models.IntegerField(default=0)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    taux_reduction = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(99)],
        help_text="Réduction en % appliquée à tous les parfums de cette catégorie (0 = pas de réduction)"
    )
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    message_promotion = models.CharField(max_length=255, blank=True)


    class Meta:
        db_table = 'categorie_parfum'
        verbose_name = 'Catégorie de parfum'
        verbose_name_plural = 'Catégories de parfums'
    
    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)

    def promotion_active(self, maintenant=None):
        if self.taux_reduction <= 0:
            return False
        maintenant = maintenant or timezone.now()
        if self.date_debut and self.date_debut > maintenant:
            return False
        if self.date_fin and self.date_fin < maintenant:
            return False
        return True


class Parfum(models.Model):
    GENRE_CHOICES = [
        ('homme', 'Homme'),
        ('femme', 'Femme'),
        ('mixte', 'Mixte'),
    ]
    INTENSITE_CHOICES = [
        ('légère', 'Légère'),
        ('moyenne', 'Moyenne'),
        ('forte', 'Forte'),
        ('très forte', 'Très forte'),
    ]
    
    categorie = models.ForeignKey(CategorieParfum, on_delete=models.SET_NULL, null=True, related_name='parfums')
    boutique = models.ForeignKey('utilisateur.Boutique', on_delete=models.CASCADE, null=True, blank=True, related_name='parfums')
    nom = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    marque = models.CharField(max_length=200 ,blank=True)
    duree = models.CharField(max_length=200 ,blank=True)
    reference_sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description_courte = models.CharField(max_length=500, blank=True)
    description_longue = models.TextField(blank=True)
    inspire_de = models.CharField(
        max_length=200,
        blank=True,
        help_text="Parfum de luxe dont ce produit est inspiré (ex: Sauvage Dior, Bleu de Chanel…)"
    )
    
    # Notes olfactives
    notes_tete = models.CharField(max_length=300, blank=True)
    notes_coeur = models.CharField(max_length=300, blank=True)
    notes_fond = models.CharField(max_length=300, blank=True)
    
    # Caractéristiques
    contenance_ml = models.IntegerField(help_text="30, 50, 75, 100 ml")
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    prix_promotionnel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Prix d'achat unitaire (visible admin uniquement)")
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    stock_quantite = models.IntegerField(default=0)
    seuil_alerte_stock = models.IntegerField(default=5)
    
    # Images
    image_principale = models.ImageField(
        upload_to=upload_to_parfum,
        blank=True, null=True,
        help_text="Image principale du parfum (jpg, png, webp — max 2Mo)"
    )

    image_supp_1 = models.ImageField(upload_to=upload_to_parfum_galerie, blank=True, null=True, help_text="Image supplémentaire 1")
    image_supp_2 = models.ImageField(upload_to=upload_to_parfum_galerie, blank=True, null=True, help_text="Image supplémentaire 2")
    image_supp_3 = models.ImageField(upload_to=upload_to_parfum_galerie, blank=True, null=True, help_text="Image supplémentaire 3")
    image_supp_4 = models.ImageField(upload_to=upload_to_parfum_galerie, blank=True, null=True, help_text="Image supplémentaire 4")
    
    # Tags (ManyToMany via la table de liaison)
    tags = models.ManyToManyField(Tag, through='TagParfum', related_name='parfums', blank=True)
    
    # Autres attributs conservés
    genre_cible = models.CharField(max_length=20, choices=GENRE_CHOICES, default='mixte')
    intensite = models.CharField(max_length=20, choices=INTENSITE_CHOICES, blank=True)
    
    # IA
    description_ia = models.TextField(blank=True, help_text="Description narrative envoyée à l'IA")
    embedding = models.JSONField(blank=True, null=True, help_text="Vecteur d'embedding pour recherche sémantique")
    
    # Statut
    est_nouveau = models.BooleanField(default=False)
    est_bestseller = models.BooleanField(default=False)
    est_hotseller = models.BooleanField(default=False) 
    actif = models.BooleanField(default=True)
    
    # Dates
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'parfum'
        verbose_name = 'Parfum'
        verbose_name_plural = 'Parfums'
    
    def __str__(self):
        return f"{self.nom} - {self.prix_unitaire} FCFA"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)

    @property
    def prix_promotionnel_effectif(self):
        if not self.actif:
            return None
        if self.prix_promotionnel is not None and self.promotion_article_active():
            return self.prix_promotionnel
        if self.categorie and self.categorie.promotion_active():
            reduction = Decimal(str(self.categorie.taux_reduction)) / Decimal('100')
            return (self.prix_unitaire * (1 - reduction)).quantize(Decimal('0.01'))
        return None

    def promotion_article_active(self, maintenant=None):
        maintenant = maintenant or timezone.now()
        if self.date_debut and self.date_debut > maintenant:
            return False
        if self.date_fin and self.date_fin < maintenant:
            return False
        return True

    @property
    def prix_actuel(self):
        promo = self.prix_promotionnel_effectif
        return promo if promo is not None else self.prix_unitaire
    
    # Méthodes pour récupérer les tags par type
    # Le champ 'type' n'existe plus — Tag.nom EST le type (ex: "Sillage", "Famille olfactive")
    # Ces propriétés retournent les valeurs depuis la table de liaison TagParfum
    def get_tags_by_type(self, tag_nom):
        """Récupère les valeurs des tags dont le nom de type correspond à tag_nom."""
        return (
            self.tags_associes
            .filter(tag__nom__iexact=tag_nom)
            .select_related('tag')
        )

    @property
    def famille_olfactive(self):
        return [tp.valeur for tp in self.get_tags_by_type('Famille olfactive') if tp.valeur]

    @property
    def humeurs_compatibles(self):
        return [tp.valeur for tp in self.get_tags_by_type('Humeur') if tp.valeur]

    @property
    def occasions(self):
        return [tp.valeur for tp in self.get_tags_by_type('Occasion') if tp.valeur]

    @property
    def saisons_compatibles(self):
        return [tp.valeur for tp in self.get_tags_by_type('Saison') if tp.valeur]


class Ingredient(models.Model):
    nom = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)

    prix_par_ml = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat_par_ml = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Prix d'achat par ml (visible admin uniquement)")
    stock_ml = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    seuil_alerte_ml = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, default=0, help_text="Alerte si stock <= seuil")
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ingredient'
        verbose_name = 'Ingrédient'
        verbose_name_plural = 'Ingrédients'
        

    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom



from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import math


# ============================================================
# ESSENCE (catalogue)
# ============================================================

class Essence(models.Model):
    INTENSITE_CHOICES = [
        ('légère', 'Légère'),
        ('moyenne', 'Moyenne'),
        ('forte', 'Forte'),
        ('très forte', 'Très forte'),
    ]
    GENRE_CHOICES = [
        ('homme', 'Homme'),
        ('femme', 'Femme'),
        ('mixte', 'Mixte'),
    ]
    CATEGORIE_CHOICES = [
        ('super_premium', 'Super Premium'),
        ('premium', 'Premium'),
        ('high', 'High'),]

    # --- Identité ---


    # Identité (triplet unique)
    marque = models.CharField(max_length=100)
    nom = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, null=True, blank=True)
    categorie = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='premium')
    code_reference = models.CharField(max_length=50, unique=True)


    # Descriptions
    description = models.TextField(blank=True)
    description_ia = models.TextField(blank=True)

    # Fournisseur & technique

    fournisseur = models.CharField(max_length=200, blank=True)
    origine_pays = models.CharField(max_length=100, blank=True)
    concentration_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    couleur = models.CharField(max_length=50, blank=True)
    duree = models.CharField(max_length=50, blank=True)


    # Attributs olfactifs
    intensite = models.CharField(max_length=20, choices=INTENSITE_CHOICES, blank=True)
    genre_cible = models.CharField(max_length=20, choices=GENRE_CHOICES, default='mixte')

    notes_tete = models.CharField(max_length=300, blank=True)
    notes_coeur = models.CharField(max_length=300, blank=True)
    notes_fond = models.CharField(max_length=300, blank=True)


    # Tags
    tags = models.ManyToManyField('Tag', through='TagEssence', related_name='essences', blank=True)

    # Prix pour le laboratoire (au ml)
    prix_par_ml = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Prix au ml utilisé dans le laboratoire")
    seuil_alerte_ml = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Alerte si stock total de l'essence <= seuil")
    embedding = models.JSONField(blank=True, null=True, help_text="Vecteur d'embedding pour recherche sémantique")

    # Statut
    actif = models.BooleanField(default=True)
    
    

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'essence'
        verbose_name = 'Essence'
        verbose_name_plural = 'Essences'

        ordering = ['marque', 'nom']
        unique_together = [['marque', 'nom', 'categorie']]   # ← triplet unique

    def __str__(self):
        return f"{self.marque} - {self.nom} ({self.get_categorie_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(f'{self.marque}-{self.nom}')}-{random_suffix}"
        super().save(*args, **kwargs)

    @property
    def nom_complet(self):
        return f"{self.marque} - {self.nom}"

    # Le champ 'type' n'existe plus — Tag.nom EST le type (ex: "Sillage", "Famille olfactive")
    # Ces propriétés retournent les valeurs depuis la table de liaison TagEssence
    def get_tags_by_type(self, tag_nom):
        """Récupère les valeurs des tags dont le nom de type correspond à tag_nom."""
        return (
            self.tags_associes
            .filter(tag__nom__iexact=tag_nom)
            .select_related('tag')
        )

    @property
    def famille_olfactive(self):
        return [te.valeur for te in self.get_tags_by_type('Famille olfactive') if te.valeur]

    @property
    def humeurs_compatibles(self):
        return [te.valeur for te in self.get_tags_by_type('Humeur') if te.valeur]

    @property
    def moments_journee(self):
        return [te.valeur for te in self.get_tags_by_type('Moment de la journée') if te.valeur]

    @property
    def occasions(self):
        return [te.valeur for te in self.get_tags_by_type('Occasion') if te.valeur]

    @property
    def saisons_compatibles(self):
        return [te.valeur for te in self.get_tags_by_type('Saison') if te.valeur]

    @property
    def signes_astrologiques_compatibles(self):
        return [te.valeur for te in self.get_tags_by_type('Signe astrologique') if te.valeur]


    def stock_total_ml(self):
        """Retourne le stock total en ml pour le laboratoire (somme des lots actifs)."""
        from .models import LotEssence
        total = self.lots.filter(actif=True).aggregate(total=models.Sum('stock_ml'))['total'] or 0
        return total
    
    def prelever_lots(self, quantite_ml):
        restant = Decimal(str(quantite_ml))
        lots = list(self.lots.select_for_update().filter(actif=True).order_by('date_reception', 'id'))
        total_disponible = sum((lot.stock_ml for lot in lots), Decimal('0'))
        if total_disponible < restant:
            raise ValidationError(
                f"Stock insuffisant pour {self.nom_complet}: "
                f"{restant} ml requis, {total_disponible} ml disponible."
            )

        prelevements = []
        for lot in lots:
            if restant <= 0:
                break
            prelevement = min(lot.stock_ml, restant)
            lot.stock_ml -= prelevement
            lot.save(update_fields=['stock_ml'])
            prelevements.append((lot, prelevement))
            restant -= prelevement
        return prelevements

    def restituer_lots(self, quantite_ml):
        if quantite_ml <= 0:
            return
        lot = (
            self.lots.select_for_update()
            .filter(actif=True)
            .order_by('-date_reception', '-id')
            .first()
        )
        if lot is None:
            raise ValidationError(f"Aucun lot actif disponible pour restituer {self.nom_complet}.")
        lot.stock_ml += Decimal(str(quantite_ml))
        lot.save(update_fields=['stock_ml'])

    
    # ============================================================
# LOT D'ESSENCE (stock laboratoire)
# ============================================================
class LotEssence(models.Model):
    essence = models.ForeignKey(Essence, on_delete=models.CASCADE, related_name='lots')
    stock_ml = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Quantité en ml disponible pour le laboratoire")
    stock_precedent_ml = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False, help_text="Stock total de l'essence avant cet ajout")
    quantite_initiale_ml = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Quantité reçue à l'origine")
    prix_achat_par_ml = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Prix d'achat par ml pour ce lot (visible admin uniquement)")
    actif = models.BooleanField(default=True)
    date_reception = models.DateTimeField(auto_now_add=True)   # optionnel, pour traçabilité
    reference_fournisseur = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new and not self.quantite_initiale_ml:
            self.quantite_initiale_ml = self.stock_ml
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'lot_essence'
        verbose_name = 'Lot d\'essence (labo)'
        verbose_name_plural = 'Lots d\'essence (labo)'
        ordering = ['date_reception']

    def __str__(self):
        return f"{self.essence.nom_complet} - {self.stock_ml} ml"

    @property
    def stock_insuffisant(self):
        return (self.essence.seuil_alerte_ml is not None 
                and self.essence.stock_total_ml() <= self.essence.seuil_alerte_ml)
   # ============================================================
# PRODUIT FINI (essence vendue en flacon)
# ============================================================
class ProduitFiniEssence(models.Model):
    essence = models.ForeignKey(Essence, on_delete=models.CASCADE, related_name='produits_finis')
    taille_ml = models.PositiveIntegerField(help_text="Taille du flacon vendu (ex: 10, 15, 30, 50)")
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    prix_promotionnel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    actif = models.BooleanField(default=True)
    

    class Meta:
        db_table = 'produit_fini_essence'
        verbose_name = 'Produit fini (essence)'
        verbose_name_plural = 'Produits finis (essences)'
        unique_together = [['essence', 'taille_ml']]

    def __str__(self):
        return f"{self.essence.nom_complet} - {self.taille_ml}ml - {self.prix} FCFA"

    @property
    def prix_actuel(self):
        return self.prix_promotionnel if self.prix_promotionnel else self.prix

    @property
    def prix_par_ml(self):
        return self.prix_actuel / self.taille_ml if self.taille_ml else 0


# ============================================================
# ACCESSOIRES
# ============================================================
class TypeAccessoire(models.Model):
    nom = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icone = models.ImageField(
        upload_to=upload_to_type_accessoire,
        blank=True, null=True,
        help_text="Icône du type d'accessoire (svg, png — fond transparent recommandé)"
    )

    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
     
    taux_reduction = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(99)],
        help_text="Réduction en % appliquée à tous les accessoires de ce type (0 = pas de réduction)"
    )
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    message_promotion = models.CharField(max_length=255, blank=True)

    
    class Meta:
        db_table = 'type_accessoire'
        verbose_name = 'Type d\'accessoire'
        verbose_name_plural = 'Types d\'accessoires'
    
    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)

    def promotion_active(self, maintenant=None):
        if self.taux_reduction <= 0:
            return False
        maintenant = maintenant or timezone.now()
        if self.date_debut and self.date_debut > maintenant:
            return False
        if self.date_fin and self.date_fin < maintenant:
            return False
        return True


class Accessoire(models.Model):
    type_accessoire = models.ForeignKey(TypeAccessoire, on_delete=models.SET_NULL, null=True, related_name='accessoires')
    boutique = models.ForeignKey('utilisateur.Boutique', on_delete=models.CASCADE, null=True, blank=True, related_name='accessoires')
    nom = models.CharField(max_length=200)
    marque = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    reference_sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description_courte = models.CharField(max_length=500, blank=True)
    description_longue = models.TextField(blank=True)
    matiere = models.CharField(max_length=100, blank=True)
    couleur = models.CharField(max_length=50, blank=True)
    taille = models.CharField(max_length=50, blank=True)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    prix_promotionnel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Prix d'achat unitaire (visible admin uniquement)")
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    stock_quantite = models.IntegerField(default=0)
    seuil_alerte_stock = models.IntegerField(default=3)
    image_principale = models.ImageField(
        upload_to=upload_to_accessoire,
        blank=True, null=True,
        help_text="Image principale de l'accessoire"
    )
    embedding = models.JSONField(blank=True, null=True, help_text="Vecteur d'embedding pour recherche sémantique")

    image_supp_1 = models.ImageField(upload_to=upload_to_accessoire_galerie, blank=True, null=True, help_text="Image supplémentaire 1")
    image_supp_2 = models.ImageField(upload_to=upload_to_accessoire_galerie, blank=True, null=True, help_text="Image supplémentaire 2")
    image_supp_3 = models.ImageField(upload_to=upload_to_accessoire_galerie, blank=True, null=True, help_text="Image supplémentaire 3")
    image_supp_4 = models.ImageField(upload_to=upload_to_accessoire_galerie, blank=True, null=True, help_text="Image supplémentaire 4")
    poids_grammes = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    est_bestseller = models.BooleanField(default=False)
    est_hotseller = models.BooleanField(default=False)
    tags = models.ManyToManyField('Tag', through='TagAccessoire', related_name='accessoires', blank=True)
    
    class Meta:
        db_table = 'accessoire'
        verbose_name = 'Accessoire'
        verbose_name_plural = 'Accessoires'
    
    def __str__(self):
        return f"{self.nom} - {self.prix_unitaire} FCFA"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)

    @property
    def prix_promotionnel_effectif(self):
        if not self.actif:
            return None
        if self.prix_promotionnel is not None and self.promotion_article_active():
            return self.prix_promotionnel
        if self.type_accessoire and self.type_accessoire.promotion_active():
            reduction = Decimal(str(self.type_accessoire.taux_reduction)) / Decimal('100')
            return (self.prix_unitaire * (1 - reduction)).quantize(Decimal('0.01'))
        return None

    def promotion_article_active(self, maintenant=None):
        maintenant = maintenant or timezone.now()
        if self.date_debut and self.date_debut > maintenant:
            return False
        if self.date_fin and self.date_fin < maintenant:
            return False
        return True

    @property
    def prix_actuel(self):
        promo = self.prix_promotionnel_effectif
        return promo if promo is not None else self.prix_unitaire


# ============================================================
# FLACONS
# ============================================================
class TypeFlacon(models.Model):
    nom = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, null=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to=upload_to_type_flacon,
        blank=True, null=True,
        help_text="Image représentative du type de flacon"
    )

    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
     
    taux_reduction = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(99)],
        help_text="Réduction en % appliquée à tous les flacons de ce type (0 = pas de réduction)"
    )

    
    class Meta:
        db_table = 'type_flacon'
        verbose_name = 'Type de flacon'
        verbose_name_plural = 'Types de flacons'
    
    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(self.nom)}-{random_suffix}"
        super().save(*args, **kwargs)


class Flacon(models.Model):
    type_flacon = models.ForeignKey(TypeFlacon, on_delete=models.SET_NULL, null=True, related_name='flacons')
    nom = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, null=True, blank=True)
    reference_sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    contenance_ml = models.IntegerField(help_text="30, 50, 75, 100, 150 ml")
    matiere = models.CharField(max_length=100, blank=True)
    couleur = models.CharField(max_length=50, blank=True)
    hauteur_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    largeur_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    poids_grammes = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    image_principale = models.ImageField(
        upload_to=upload_to_flacon,
        blank=True, null=True,
        help_text="Image principale du flacon"
    )

    image_supp_1 = models.ImageField(upload_to=upload_to_flacon_galerie, blank=True, null=True, help_text="Image supplémentaire 1")
    image_supp_2 = models.ImageField(upload_to=upload_to_flacon_galerie, blank=True, null=True, help_text="Image supplémentaire 2")
    image_supp_3 = models.ImageField(upload_to=upload_to_flacon_galerie, blank=True, null=True, help_text="Image supplémentaire 3")
    image_supp_4 = models.ImageField(upload_to=upload_to_flacon_galerie, blank=True, null=True, help_text="Image supplémentaire 4")
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Prix d'achat unitaire (visible admin uniquement)")
    stock_quantite = models.IntegerField(default=0)
    seuil_alerte_stock = models.IntegerField(default=5, help_text="En dessous de ce seuil la commande est bloquée")
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'flacon'
        verbose_name = 'Flacon'
        verbose_name_plural = 'Flacons'
    
    def __str__(self):
        return f"{self.nom} ({self.contenance_ml}ml) - {self.prix_unitaire} FCFA"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            random_suffix = ''.join(random.choices(string.digits, k=5))
            self.slug = f"{slugify(f'{self.nom}-{self.contenance_ml}')}-{random_suffix}"
        super().save(*args, **kwargs)


# ============================================================
# NOTIFICATIONS DE CATALOGUE
# ============================================================
class NotificationCatalogue(models.Model):
    """Notification générée quand un produit atteint son seuil d'alerte stock."""
    
    TYPE_CHOICES = [
        ('essence', 'Essence'),
        ('accessoire', 'Accessoire'),
        ('flacon', 'Flacon'),
        ('lot_essence', 'Lot Essence'),
        ('ingredient', 'Ingrédient'),
    ]
    
    # Type de produit et ID du produit
    type_produit = models.CharField(max_length=50, choices=TYPE_CHOICES)
    product_id = models.PositiveIntegerField()
    product_name = models.CharField(max_length=255, help_text="Nom du produit au moment de l'alerte")
    
    # Détails de l'alerte
    message = models.TextField()
    stock_actuel = models.DecimalField(max_digits=12, decimal_places=2)
    seuil_alerte = models.DecimalField(max_digits=12, decimal_places=2)
    est_lu = models.BooleanField(default=False)
    
    # Métadonnées
    metadata = models.JSONField(default=dict, blank=True, help_text="Données supplémentaires (ex: URL du produit)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_catalogue'
        verbose_name = 'Notification Catalogue'
        verbose_name_plural = 'Notifications Catalogue'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type_produit', 'product_id']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['est_lu']),
        ]
    
    def __str__(self):
        return f"[{self.type_produit}] {self.product_name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def est_encore_en_alerte(self):
        """Vérifie si le produit est toujours en alerte (stock toujours ≤ seuil)."""
        return self.stock_actuel <= self.seuil_alerte


class MouvementStock(models.Model):
    utilisateur = models.ForeignKey('utilisateur.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='mouvements_stock')
    type_produit = models.CharField(max_length=50, help_text="parfum, essence, accessoire, flacon, produit_fini_essence, ingredient")
    produit_id = models.PositiveIntegerField()
    nom_produit = models.CharField(max_length=255)
    quantite_avant = models.DecimalField(max_digits=12, decimal_places=3)
    quantite_apres = models.DecimalField(max_digits=12, decimal_places=3)
    quantite_ajoutee = models.DecimalField(max_digits=12, decimal_places=3)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mouvement_stock'
        ordering = ['-date_ajout']
        verbose_name = 'Mouvement de stock'
        verbose_name_plural = 'Mouvements de stock'

    def __str__(self):
        user_str = self.utilisateur.email if self.utilisateur else "Système"
        return f"{self.date_ajout.strftime('%Y-%m-%d %H:%M')} - {user_str} a ajouté {self.quantite_ajoutee} à {self.nom_produit} ({self.type_produit})"


class LotEssenceConsommation(models.Model):
    lot_essence = models.ForeignKey('LotEssence', on_delete=models.CASCADE, related_name='consommations')
    
    ligne_produit_fini_essence = models.ForeignKey('orders.CommandeProduitFiniEssence', on_delete=models.CASCADE, null=True, blank=True, related_name='lot_consommations')
    ligne_parfum_perso = models.ForeignKey('orders.CommandeLigneParfumPerso', on_delete=models.CASCADE, null=True, blank=True, related_name='lot_consommations')
    
    quantite_ml = models.DecimalField(max_digits=10, decimal_places=2)
    prix_vente_attribue = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Part du prix de vente attribuée à cette consommation")
    date_consommation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lot_essence_consommation'
        verbose_name = "Consommation de lot d'essence"
        verbose_name_plural = "Consommations de lots d'essence"
        ordering = ['-date_consommation']

    def __str__(self):
        return f"{self.quantite_ml} ml du lot {self.lot_essence.id}"


# ============================================================
# FUTURE_UPDATE_DIFFUSEUR: MODÈLE DIFFUSEUR DE PARFUM
# ============================================================
def upload_to_diffuseur(instance, filename):
    import os
    import uuid
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join('diffuseurs', new_filename)

def upload_to_diffuseur_galerie(instance, filename):
    import os
    import uuid
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join('diffuseurs/galerie', new_filename)

class DiffuseurParfum(models.Model):
    TECHNOLOGIE_CHOICES = [
        ('nebulisation', 'Nébulisation'),
        ('ultrasons', 'Ultrasons'),
        ('chaleur_douce', 'Chaleur douce'),
        ('ventilation', 'Ventilation'),
    ]
    ALIMENTATION_CHOICES = [
        ('secteur', 'Secteur'),
        ('batterie_rechargeable', 'Batterie rechargeable'),
        ('usb', 'USB'),
        ('piles', 'Piles'),
    ]

    nom = models.CharField(max_length=200)
    marque = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    reference_sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description = models.TextField(blank=True)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    prix_promotionnel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Prix d'achat unitaire (visible admin uniquement)")
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    stock_quantite = models.IntegerField(default=0)
    seuil_alerte_stock = models.IntegerField(default=3)
    materiau = models.CharField(max_length=100, blank=True, help_text="Matériau principal (bois, verre, plastique, etc.)")
    couleur = models.CharField(max_length=50, blank=True)
    dimensions = models.CharField(max_length=100, blank=True, help_text="ex: 12cm x 12cm x 15cm")
    poids_grammes = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    image_principale = models.ImageField(
        upload_to=upload_to_diffuseur,
        blank=True, null=True,
        help_text="Image principale du diffuseur"
    )
    image_supp_1 = models.ImageField(upload_to=upload_to_diffuseur_galerie, blank=True, null=True, help_text="Image supplémentaire 1")
    image_supp_2 = models.ImageField(upload_to=upload_to_diffuseur_galerie, blank=True, null=True, help_text="Image supplémentaire 2")
    image_supp_3 = models.ImageField(upload_to=upload_to_diffuseur_galerie, blank=True, null=True, help_text="Image supplémentaire 3")
    image_supp_4 = models.ImageField(upload_to=upload_to_diffuseur_galerie, blank=True, null=True, help_text="Image supplémentaire 4")
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    est_bestseller = models.BooleanField(default=False)
    est_hotseller = models.BooleanField(default=False)

    # Nouveaux attributs physiques/technologiques
    type_technologie = models.CharField(
        max_length=50,
        choices=TECHNOLOGIE_CHOICES,
        default='ultrasons',
        help_text="Type de technologie de diffusion"
    )
    capacite_reservoir_ml = models.IntegerField(
        null=True,
        blank=True,
        help_text="Capacité du réservoir en ml"
    )
    type_alimentation = models.CharField(
        max_length=50,
        choices=ALIMENTATION_CHOICES,
        default='secteur',
        help_text="Type d'alimentation électrique"
    )
    nombre_vitesses = models.IntegerField(
        null=True,
        blank=True,
        help_text="Nombre de vitesses de diffusion"
    )
    est_connecte = models.BooleanField(
        default=False,
        help_text="Savoir si on peut contrôler le diffuseur à distance"
    )
    surface_couverture_m2 = models.IntegerField(
        null=True,
        blank=True,
        help_text="Surface de couverture maximale en m²"
    )
    a_jeux_de_lumiere = models.BooleanField(
        default=False,
        help_text="Indique si le diffuseur possède des jeux de lumière"
    )

    class Meta:
        db_table = 'diffuseur_parfum'
        verbose_name = 'Diffuseur de parfum'
        verbose_name_plural = 'Diffuseurs de parfum'

    def __str__(self):
        return f"{self.nom} - {self.prix_unitaire} FCFA"

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    @property
    def prix_actuel(self):
        from django.utils import timezone
        now = timezone.now()
        if self.prix_promotionnel:
            if self.date_debut and self.date_fin:
                if self.date_debut <= now <= self.date_fin:
                    return self.prix_promotionnel
            else:
                return self.prix_promotionnel
        return self.prix_unitaire

    @property
    def prix_promotionnel_effectif(self):
        from django.utils import timezone
        now = timezone.now()
        if self.prix_promotionnel:
            if self.date_debut and self.date_fin:
                if self.date_debut <= now <= self.date_fin:
                    return self.prix_promotionnel
            else:
                return self.prix_promotionnel
        return None
