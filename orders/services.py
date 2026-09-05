"""
Service de génération de factures PDF pour Accessoires Exclusifs.

Flux :
  1. Générer le numéro de facture (FAC-YYYY-NNNN)
  2. Rendre le template HTML avec les données de la commande
  3. Convertir HTML → PDF via xhtml2pdf
  4. Sauvegarder le fichier dans media/factures/YYYY/MM/
  5. Créer/mettre à jour l'objet Facture en base
  6. Envoyer l'email au client avec le PDF en pièce jointe
"""

import io
import logging
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import IntegrityError
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def generer_facture(commande):
    """
    Génère (ou régénère) la facture PDF d'une commande payée.

    - Si une facture existe déjà pour cette commande, elle est régénérée
      (le fichier PDF est écrasé et la date de modification mise à jour).
    - L'email est renvoyé à chaque régénération.

    Retourne l'objet Facture créé ou mis à jour.
    """
    from orders.models import Facture

    # ── 1. Récupérer ou créer l'objet Facture ──────────────────────────
    try:
        facture = commande.facture  # existe déjà → régénération
        logger.info(f"[FACTURE] Régénération de {facture.numero_facture} pour {commande.numero_commande}")
    except Facture.DoesNotExist:
        facture = Facture(commande=commande)
        facture.numero_facture = Facture.generer_numero()
        max_retries = 5
        for attempt in range(max_retries): 
            try:
            
                facture.save()
                break
            except IntegrityError as e:
                if 'numero_facture' in str(e):     
                    logger.warning(
                        f"[FACTURE] Conflit numéro facture {facture.numero_facture}, tentative {attempt + 1}/{max_retries}"
                    )
                    facture.numero_facture = Facture.generer_numero()
                    continue
                raise
        else:
            logger.error(
                f"[FACTURE] Échec création facture après {max_retries} tentatives pour {commande.numero_commande}"
            )
            raise
        logger.info(f"[FACTURE] Création de {facture.numero_facture} pour {commande.numero_commande}")

    # ── 2. Préparer le contexte du template ───────────────────────────
    # Chemin absolu du logo pour que xhtml2pdf puisse le lire
    logo_path = os.path.join(settings.BASE_DIR, 'staticfiles', 'img', 'logo.png')

    # gérer le cas où la commande est passée par un invité (client peut être None)
    client_obj = commande.client if getattr(commande, 'client', None) else None
    user_obj = getattr(client_obj, 'user', None) if client_obj else None

    # Informations sur l'entreprise pour l'en-tête de la facture
    try:
        from catalogue.models import EntrepriseInfo
        entreprise = EntrepriseInfo.objects.first()
    except Exception:
        entreprise = None

    entreprise_telephone = (
        (entreprise.telephone_principal or entreprise.telephone_secondaire or entreprise.whatsapp)
        if entreprise else None
    )
    entreprise_email = 'accessoiresexclusifs@gmail.com'

    context = {
        'facture': facture,
        'commande': commande,
        'client': client_obj,
        'user': user_obj,
        'logo_path': logo_path,
        'date_emission': facture.date_emission,
        'lignes_parfums': commande.lignes_parfums.all(),
        'lignes_accessoires': commande.lignes_accessoires.all(),
        'lignes_produit_fini_essence': commande.lignes_produit_fini_essence.all(),
        'lignes_parfums_perso': commande.lignes_parfums_perso.all(),
        'lignes_essence_personnalisee': commande.lignes_essence_personnalisee.all(),
        'lignes_diffuseurs': commande.lignes_diffuseurs.all(),
        'entreprise_telephone': entreprise_telephone,
        'entreprise_email': entreprise_email,
        'DEVISE': 'FCFA',
    }

    # ── 3. Rendre le template HTML ────────────────────────────────────
    html_string = render_to_string('factures/facture_pdf.html', context)

    # ── 4. Convertir HTML → PDF ───────────────────────────────────────
    pdf_buffer = io.BytesIO()
    try:
        from xhtml2pdf import pisa

        pisa_status = pisa.CreatePDF(
            src=html_string,
            dest=pdf_buffer,
            encoding='utf-8',
        )
        if pisa_status.err:
            logger.error(f"[FACTURE] Erreur xhtml2pdf pour {commande.numero_commande}: {pisa_status.err}")
            raise RuntimeError(f"Erreur lors de la génération du PDF : {pisa_status.err}")
    except ImportError:
        logger.error("[FACTURE] xhtml2pdf n'est pas installé. Lance : pip install xhtml2pdf")
        raise

    pdf_content = pdf_buffer.getvalue()
    pdf_buffer.close()

    # ── 5. Sauvegarder le fichier PDF ─────────────────────────────────
    nom_fichier = f"facture_{facture.numero_facture}.pdf"

    # Supprimer l'ancien fichier si régénération
    if facture.pk and facture.fichier_pdf:
        try:
            facture.fichier_pdf.delete(save=False)
        except Exception:
            pass  # Pas bloquant si le fichier n'existe plus

    facture.fichier_pdf.save(
        nom_fichier,
        ContentFile(pdf_content),
        save=False  # On sauvegarde l'objet après
    )

    # ── 6. Sauvegarder l'objet Facture en base ────────────────────────
    facture.save()

    # ── 7. Envoyer l'email au client ──────────────────────────────────
    # L'adresse peut être absente si commande.client est None (invité)
    email_client = None
    if client_obj and getattr(client_obj, 'user', None) and getattr(client_obj.user, 'email', None):
        email_client = client_obj.user.email

    if email_client:
        try:
            envoyer_email_facture(facture, pdf_content, email_client)
        except Exception as e:
            logger.error(f"[FACTURE] Erreur envoi email pour {facture.numero_facture}: {e}")
            # L'email en échec ne doit pas bloquer la sauvegarde

    return facture


from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

def envoyer_email_facture(facture, pdf_content: bytes, email_destinataire: str):
    """
    Envoie la facture PDF par email au client avec un design HTML Premium.
    """
    commande = facture.commande
    user = commande.client.user
    prenom = user.first_name or 'Cher client'

    sujet = f"Votre facture {facture.numero_facture} — Accessoires Exclusifs"
    
    # 1. Version texte brut (Fallback)
    corps_texte = f"""Bonjour {prenom},

Nous vous remercions pour votre commande {commande.numero_commande}.
Veuillez trouver ci-joint votre facture {facture.numero_facture} d'un montant de {commande.total_ttc:,.0f} FCFA.

Pour voir les détails en ligne, visitez : {settings.FRONTEND_URL}/mes-commandes/{commande.numero_commande}

Cordialement,
L'équipe Accessoires Exclusifs
redefine your style
"""

    # 2. Construction de l'URL pour le bouton
    url_commande = f"{settings.FRONTEND_URL.rstrip('/')}/mes-commandes/{commande.numero_commande}"

    # 3. Version HTML générée à partir du template
    context = {
        'prenom': prenom,
        'commande': commande,
        'facture': facture,
        'url_commande': url_commande
    }
    corps_html = render_to_string('emails/facture_email.html', context)

    # 4. Envoi de l'email avec MultiAlternatives
    message = EmailMultiAlternatives(
        subject=sujet,
        body=corps_texte,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email_destinataire],
    )
    message.attach_alternative(corps_html, "text/html")
    
    # Ajout du PDF
    message.attach(
        f"facture_{facture.numero_facture}.pdf",
        pdf_content,
        'application/pdf'
    )
    message.send(fail_silently=False)

    # Mettre à jour le statut d'envoi
    facture.envoye_par_email = True
    facture.email_envoye_a = email_destinataire
    facture.save(update_fields=['envoye_par_email', 'email_envoye_a'])
    logger.info(f"[FACTURE] Email HTML {facture.numero_facture} envoyé à {email_destinataire}")
