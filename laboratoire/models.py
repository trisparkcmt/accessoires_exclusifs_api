from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class EssencePersonnalisee(models.Model):
    client = models.ForeignKey('utilisateur.Client', on_delete=models.CASCADE, related_name='essences_personnalisees')
    nom = models.CharField(max_length=200, help_text="Nom donné par le client à son essence")
    prix_par_ml_calcule = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Prix calculé en fonction des ingrédients")
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'essence_personnalisee'
        verbose_name = 'Essence Personnalisée'
        verbose_name_plural = 'Essences Personnalisées'
        
    def __str__(self):
        return f"{self.nom} - {self.client.user.email}"
        
    def recalculer_prix(self):
        # Le prix de l'essence personnalisée au ml est la moyenne pondérée ou la somme des prix des ingrédients.
        # Pour simplifier, si 1ml d'essence perso contient 1ml d'ingrédients, le prix total des ingrédients donne le prix total de l'essence.
        # Le prix_par_ml sera calculé lors de l'ajout des ingrédients.
        total_prix = sum(ligne.prix_ligne for ligne in self.lignes.all())
        total_volume = sum(ligne.quantite_ml for ligne in self.lignes.all())
        if total_volume > 0:
            self.prix_par_ml_calcule = total_prix / total_volume
        else:
            self.prix_par_ml_calcule = Decimal('0')
        self.save()
        return self.prix_par_ml_calcule

class EssencePersonnaliseeLigne(models.Model):
    essence_personnalisee = models.ForeignKey(EssencePersonnalisee, on_delete=models.CASCADE, related_name='lignes')
    ingredient = models.ForeignKey('catalogue.Ingredient', on_delete=models.CASCADE, related_name='utilisations')
    quantite_ml = models.DecimalField(max_digits=8, decimal_places=3, validators=[MinValueValidator(Decimal('0.1'))])
    prix_par_ml_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    prix_ligne = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'essence_personnalisee_ligne'
        verbose_name = 'Ligne d\'essence personnalisée'
        verbose_name_plural = 'Lignes d\'essences personnalisées'
        unique_together = [['essence_personnalisee', 'ingredient']]
        
    def save(self, *args, **kwargs):
        if not self.prix_par_ml_snapshot:
            self.prix_par_ml_snapshot = self.ingredient.prix_par_ml
        self.prix_ligne = self.prix_par_ml_snapshot * self.quantite_ml
        super().save(*args, **kwargs)

class ParfumPersonnalise(models.Model):
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('validé', 'Validé'),
    ]
    
    client = models.ForeignKey('utilisateur.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='parfums_personnalises')
    flacon = models.ForeignKey('catalogue.Flacon', on_delete=models.SET_NULL, null=True, related_name='parfums_personnalises')
    nom = models.CharField(max_length=200, blank=True, null=True)
    couleur = models.CharField(max_length=50, blank=True, null=True, help_text="Couleur optionnelle du parfum/flacon")
    nom_sur_flacon = models.CharField(max_length=150, blank=True, null=True, help_text="Nom/Texte optionnel gravé sur le flacon")
    description = models.TextField(blank=True)
    prix_essences = models.DecimalField(max_digits=10, decimal_places=2, help_text="Somme calculée des prix des essences")
    prix_flacon_snapshot = models.DecimalField(max_digits=10, decimal_places=2, help_text="Prix du flacon au moment de la création")
    prix_total = models.DecimalField(max_digits=10, decimal_places=2, help_text="prix_essences + prix_flacon_snapshot")
    statut = models.CharField(max_length=30, choices=STATUT_CHOICES, default='brouillon')
    note_laboratoire = models.TextField(blank=True, help_text="Retour du labo en cas de refus")
    enregistre = models.BooleanField(default=True, help_text="Détermine si le parfum est enregistré dans la collection du client.")
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'parfum_personnalise'
        verbose_name = 'Parfum personnalisé'
        verbose_name_plural = 'Parfums personnalisés'
    
    def __str__(self):
        email = self.client.user.email if self.client else "Invité"
        return f"{self.nom or 'Parfum sans nom'} - {email}"
    
    def recalculer_prix(self):
        total_essences = sum(ligne.prix_ligne for ligne in self.lignes.all())
        self.prix_essences = total_essences
        self.prix_total = total_essences + (self.prix_flacon_snapshot or 0)
        self.save()
        return self.prix_total

    def clean(self):
        """Valide que le volume total d'essences ne dépasse pas 45% de la contenance du flacon.

        La validation ne s'applique que si un flacon est défini et que des lignes existent.
        """
        if not self.flacon:
            return

        if not self.pk or not self.lignes.exists():
            return

        contenance_flacon = Decimal(str(self.flacon.contenance_ml))
        volume_total_essences = sum(ligne.quantite_ml for ligne in self.lignes.all())
        volume_max_autorise = contenance_flacon * Decimal('0.45')

        if volume_total_essences > volume_max_autorise:
            msg = (
                f"Le volume total d'essences ({volume_total_essences} ml) dépasse la limite autorisée de 45% "
                f"pour le flacon sélectionné ({volume_max_autorise} ml max). "
                "Réduisez les quantités d'essences ou choisissez un flacon de plus grande contenance."
            )
            raise ValidationError({
                '__all__': msg,
                'lignes': msg,
            })

    def save(self, *args, **kwargs):
        # Détection d'un changement de flacon pour mettre à jour le snapshot prix et recalculer
        flacon_changed = False
        if self.pk:
            try:
                previous = ParfumPersonnalise.objects.get(pk=self.pk)
                prev_flacon_id = previous.flacon.id if previous.flacon else None
                new_flacon_id = self.flacon.id if self.flacon else None
                if prev_flacon_id != new_flacon_id:
                    flacon_changed = True
                    self.prix_flacon_snapshot = self.flacon.prix_unitaire if self.flacon else Decimal('0')
            except ParfumPersonnalise.DoesNotExist:
                pass
        else:
            # Nouvel objet : initialiser le snapshot si non fourni
            if not self.prix_flacon_snapshot:
                self.prix_flacon_snapshot = self.flacon.prix_unitaire if self.flacon else Decimal('0')

        is_new = not self.pk
        if not self.nom:
            self.nom = "Parfum personnalisé"

        # Recalculer les prix avant sauvegarde si les lignes existent
        if self.pk and self.lignes.exists():
            total_essences = sum(ligne.prix_ligne for ligne in self.lignes.all())
            self.prix_essences = total_essences
            self.prix_total = total_essences + (self.prix_flacon_snapshot or Decimal('0'))
        else:
            # Pas de lignes connues (ex: création initiale) : mettre à jour le total avec le snapshot
            self.prix_total = (self.prix_essences or Decimal('0')) + (self.prix_flacon_snapshot or Decimal('0'))

        # Validation modèle : si on modifie le flacon ou si des lignes existent
        if (self.pk and self.lignes.exists()) or flacon_changed:
            self.full_clean()

        super().save(*args, **kwargs)

        # Si c'était une création et qu'aucun nom n'était fourni, on met à jour avec l'ID
        if is_new and self.nom == "Parfum personnalisé":
            self.nom = f"Parfum personnalisé #{self.id}"
            super().save(update_fields=['nom'])


class ParfumPersonnaliseLigne(models.Model):
    parfum_personnalise = models.ForeignKey('laboratoire.ParfumPersonnalise', on_delete=models.CASCADE, related_name='lignes')
    
    # L'essence utilisée peut provenir soit d'un lot d'essence du catalogue, soit d'une création perso du client
    essence = models.ForeignKey('catalogue.LotEssence', on_delete=models.CASCADE, related_name='utilisations_parfum', null=True, blank=True)
    essence_personnalisee = models.ForeignKey('laboratoire.EssencePersonnalisee', on_delete=models.CASCADE, related_name='utilisations_parfum', null=True, blank=True)
    
    quantite_ml = models.DecimalField(max_digits=8, decimal_places=3, validators=[MinValueValidator(Decimal('0.1'))])
    prix_par_ml_snapshot = models.DecimalField(max_digits=10, decimal_places=2, help_text="Prix de l'essence au ml au moment de la création")
    prix_ligne = models.DecimalField(max_digits=10, decimal_places=2, help_text="prix_par_ml_snapshot * quantite_ml")
    
    class Meta:
        db_table = 'parfum_personnalise_ligne'
        verbose_name = 'Ligne de parfum personnalisé'
        verbose_name_plural = 'Lignes de parfums personnalisés'
    
    def __str__(self):
        nom_essence = self.essence.essence.nom if self.essence else (self.essence_personnalisee.nom if self.essence_personnalisee else "Inconnu")
        return f"{self.parfum_personnalise.nom} - {nom_essence}: {self.quantite_ml}ml"
    
    def clean(self):
        # Valider qu'un seul des deux champs est renseigné
        if self.essence and self.essence_personnalisee:
            raise ValidationError("Une ligne de parfum ne peut pas contenir à la fois un lot d'essence du catalogue et une essence personnalisée.")
        if not self.essence and not self.essence_personnalisee:
            raise ValidationError("Vous devez spécifier soit un lot d'essence du catalogue, soit une essence personnalisée.")
            
        # Valider que l'essence personnalisée appartient bien au même client
        if self.essence_personnalisee and self.parfum_personnalise:
            if self.essence_personnalisee.client != self.parfum_personnalise.client:
                raise ValidationError("L'essence personnalisée choisie doit appartenir au même client que le parfum.")

    def save(self, *args, **kwargs):
        if not self.prix_par_ml_snapshot:
            if self.essence:
                self.prix_par_ml_snapshot = self.essence.essence.prix_par_ml
            elif self.essence_personnalisee:
                self.prix_par_ml_snapshot = self.essence_personnalisee.prix_par_ml_calcule
            else:
                self.prix_par_ml_snapshot = Decimal('0')

        self.prix_ligne = (self.prix_par_ml_snapshot * self.quantite_ml).quantize(Decimal('0.01'))

        self.full_clean()

        with transaction.atomic():
            super().save(*args, **kwargs)

            # Recalculer le prix du parfum parent
            parfum = self.parfum_personnalise
            try:
                parfum.recalculer_prix()
                parfum.full_clean()
            except ValidationError as e:
                detail = ''
                try:
                    essence_name = self.essence.essence.nom if self.essence else (
                        self.essence_personnalisee.nom if self.essence_personnalisee else 'essence inconnue'
                    )
                    detail = f" (ligne: {essence_name}, quantité: {self.quantite_ml} ml)"
                except Exception:
                    detail = ''

                if hasattr(e, 'message_dict'):
                    raise ValidationError({k: [f"{m} {detail}" for m in v] for k, v in e.message_dict.items()})
                else:
                    raise ValidationError(f"{e} {detail}")


class IAConversation(models.Model):
    client = models.ForeignKey(
        'utilisateur.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ia_conversations'
    )
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ia_conversation'
        verbose_name = 'Conversation IA'
        verbose_name_plural = 'Conversations IA'

    def __str__(self):
        if self.client:
            return f"Conversation IA de {self.client.user.email}"
        return f"Conversation IA session {self.session_key}"


class IAConversationMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'Utilisateur'),
        ('assistant', 'Assistant'),
    ]

    conversation = models.ForeignKey(
        IAConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Pour le rôle 'assistant' : JSON complet retourné par LIA (produits, essences, etc.)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ia_conversation_message'
        verbose_name = 'Message de conversation IA'
        verbose_name_plural = 'Messages de conversation IA'
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"


class IAConversationSummary(models.Model):
    """
    Résumé auto-généré par l'IA après chaque échange.
    Remplace l'envoi du full historique dans le system prompt, ce qui
    raccourcit les tokens et accélère les réponses.
    """
    conversation = models.OneToOneField(
        IAConversation,
        on_delete=models.CASCADE,
        related_name='summary'
    )
    summary_text = models.TextField(default='', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ia_conversation_summary'
        verbose_name = 'Résumé de conversation IA'
        verbose_name_plural = 'Résumés de conversations IA'

    def __str__(self):
        return f"Résumé conv #{self.conversation_id} ({self.updated_at.strftime('%d/%m/%Y %H:%M')})"