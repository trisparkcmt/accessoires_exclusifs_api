from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator

class CustomUserManager(BaseUserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        if email is None:
            if username is not None and '@' in username:
                email = username
                username = None
            else:
                email = extra_fields.pop('email', None)

        if not email:
            raise ValueError("L'adresse email doit être fournie.")
        
        email = self.normalize_email(email)
        
        if not username:
            username = email.split('@')[0]
            
        extra_fields['username'] = username
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username=username, email=email, password=password, **extra_fields)

class User(AbstractUser):
    """Utilisateur de base (connexion email/téléphone)"""
    email = models.EmailField(unique=True)
    telephone_validator = RegexValidator(regex=r'^\+?[0-9]{8,15}$', message="Format invalide")
    telephone = models.CharField(max_length=20, unique=True, null=True, blank=True, validators=[telephone_validator])
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['telephone']
    
    objects = CustomUserManager()
    
    class Meta:
        db_table = 'auth_user'
    
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email.split('@')[0]
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.email} ({self.telephone})"
    
    @property
    def role(self):
        """Détermine le rôle de l'utilisateur dynamiquement"""
        if self.is_superuser:
            return "superadmin"

        # On vérifie les relations OneToOne - retourne les TOUS les rôles actifs
        if not hasattr(self, 'client'):
            return "client"

        roles = []
        if hasattr(self.client, 'serveuse') and self.client.serveuse.actif:
            roles.append("serveuse")
        if hasattr(self.client, 'prestataire') and self.client.prestataire.statut == 'actif':
            roles.append("prestataire")
        if hasattr(self.client, 'livreur') and self.client.livreur.statut != 'inactif':
            roles.append("livreur")
        if hasattr(self.client, 'boutique') and self.client.boutique.statut == 'actif':
            roles.append("boutique")

        return roles if roles else "client"


class Client(models.Model):
    """Tout client (client simple, prestataire, livreur)"""
    GENRE_CHOICES = [('homme', 'Homme'), ('femme', 'Femme'), ('autre', 'Autre')]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client')
    date_naissance = models.DateField(null=True, blank=True)
    genre = models.CharField(max_length=10, choices=GENRE_CHOICES, blank=True)
    points_fidelite = models.IntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'client'
    
    @property
    def telephone(self):
        return self.user.telephone
    
    @property
    def email(self):
        return self.user.email
    
    def __str__(self):
        return self.user.email


class Prestataire(models.Model):
    """Prestataire = Client + spécificités"""
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('actif', 'Actif'),
        ('suspendu', 'Suspendu'),
        ('inactif', 'Inactif')
    ]
    
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='prestataire')
    photo = models.ImageField(upload_to='photos_profil/prestataires/', null=True, blank=True)
    code_promo = models.CharField(max_length=50, unique=True, null=True, blank=True)
    taux_commission = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reduction_client_pourcentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    solde_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'prestataire'
    
    @property
    def user(self):
        return self.client.user
    
    @property
    def nom(self):
        return self.user.last_name
    
    @property
    def prenom(self):
        return self.user.first_name
    
    def __str__(self):
        return f"{self.nom} {self.prenom} - {self.code_promo}"


class Livreur(models.Model):
    """Livreur = Client + spécificités"""
    STATUT_CHOICES = [('disponible', 'Disponible'), ('en_livraison', 'En livraison'), ('inactif', 'Inactif'), ('suspendu', 'Suspendu')]
    
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='livreur')
    photo = models.ImageField(upload_to='photos_profil/livreurs/', null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='disponible')
    note_moyenne = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    nombre_livraisons = models.IntegerField(default=0)
    date_embauche = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'livreur'
    
    @property
    def user(self):
        return self.client.user
    
    @property
    def nom(self):
        return self.user.last_name
    
    @property
    def prenom(self):
        return self.user.first_name
    
    @property
    def telephone(self):
        return self.user.telephone
    
    @property
    def email(self):
        return self.user.email
    
    def __str__(self):
        return f"{self.nom} {self.prenom} - {self.telephone}"


class Serveuse(models.Model):
    """Serveuse = Client + spécificités"""

    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='serveuse')
    photo = models.ImageField(upload_to='photos_profil/serveuses/', null=True, blank=True)
    actif = models.BooleanField(default=False)
    note_moyenne = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    nombre_services = models.IntegerField(default=0)
    date_embauche = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'serveuse'
    
    @property
    def user(self):
        return self.client.user
    
    @property
    def nom(self):
        return self.user.last_name
    
    @property
    def prenom(self):
        return self.user.first_name
    
    @property
    def telephone(self):
        return self.user.telephone
    
    @property
    def email(self):
        return self.user.email
    
    def __str__(self):
        return f"{self.nom} {self.prenom} - {self.telephone}"


class Boutique(models.Model):
    """Boutique = Client + vitrine commerciale en ligne"""
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('actif', 'Actif'),
        ('suspendu', 'Suspendu'),
        ('inactif', 'Inactif'),
    ]

    client    = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='boutique')
    photo     = models.ImageField(upload_to='photos_profil/boutiques/', null=True, blank=True)
    nom       = models.CharField(max_length=200)
    adresse   = models.CharField(max_length=300, blank=True)
    ville     = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    taux_commission = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Pourcentage de commission admin prélevé sur chaque vente")
    statut    = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'boutique'
        verbose_name = 'Boutique'
        verbose_name_plural = 'Boutiques'

    @property
    def user(self):
        return self.client.user

    @property
    def proprietaire_nom(self):
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email

    def __str__(self):
        return f"{self.nom} ({self.statut}) — {self.proprietaire_nom}"


class CommissionLog(models.Model):
    """Historique des gains d'un prestataire (Ventes, Retraits, Bonus)"""
    TYPE_CHOICES = [
        ('vente', 'Commission sur vente'),
        ('retrait', 'Retrait de solde'),
        ('bonus', 'Bonus / Ajustement'),
    ]

    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name='historique_commissions')
    type_operation = models.CharField(max_length=20, choices=TYPE_CHOICES, default='vente')
    montant = models.DecimalField(max_digits=10, decimal_places=2) # Positif pour vente, négatif pour retrait
    reference_commande = models.CharField(max_length=50, blank=True, null=True) # ID de la commande liée
    date_operation = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'commission_log'
        ordering = ['-date_operation']

    def __str__(self):
        return f"{self.prestataire.nom} - {self.type_operation} - {self.montant}€"


class PayoutTransaction(models.Model):
    """Transaction de virement (payout) Mobile Money vers un prestataire via Monetbil"""
    STATUT_CHOICES = [
        ('en_cours', 'En cours'),
        ('succes', 'Succès'),
        ('echec', 'Échec'),
    ]

    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name='payouts')
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    telephone_destination = models.CharField(max_length=20)
    reference_unique = models.CharField(max_length=100, unique=True)   # Notre UUID (external_reference envoyé à Campay)
    campay_processing_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)  # ID interne Campay (retourné par /withdraw/)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_cours')
    motif_echec = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_finalisation = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'payout_transaction'
        ordering = ['-date_creation']

    def __str__(self):
        return f"Payout {self.reference_unique} - {self.prestataire} - {self.montant} ({self.statut})"


class Notification(models.Model):
    """Notification envoyée à un administrateur ou à un utilisateur."""
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
        help_text='Utilisateur destinataire de la notification.'
    )
    type = models.CharField(max_length=100, default='general')
    title = models.CharField(max_length=200)
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    is_global_admin = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notification'
        ordering = ['-created_at']

    def __str__(self):
        target = self.recipient.email if self.recipient else 'admin'
        return f"Notification pour {target}: {self.title}"


# ============================================================
# SIGNALS (Automatisation)
# ============================================================
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_client_profile(sender, instance, created, **kwargs):
    """Crée automatiquement un profil Client lors de la création d'un User"""
    if created:
        Client.objects.create(user=instance)


class Depense(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='depenses')
    date_depense = models.DateField(auto_now_add=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'depense'
        ordering = ['-date_creation']
        verbose_name = 'Dépense'
        verbose_name_plural = 'Dépenses'

    def __str__(self):
        return f"{self.titre} - {self.montant} FCFA"


class FCMDevice(models.Model):
    """Token d'appareil Firebase Cloud Messaging associé à un utilisateur."""
    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='fcm_devices',
        help_text='Utilisateur propriétaire du token.'
    )
    registration_token = models.CharField(
        max_length=500,
        unique=True,
        help_text='Token FCM fourni par Firebase SDK côté client.'
    )
    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        default='web',
        help_text='Plateforme de l\'appareil.'
    )
    active = models.BooleanField(
        default=True,
        help_text='Désactiver lors de la déconnexion sans supprimer le token.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fcm_device'
        verbose_name = 'Appareil FCM'
        verbose_name_plural = 'Appareils FCM'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.platform} ({'actif' if self.active else 'inactif'})"