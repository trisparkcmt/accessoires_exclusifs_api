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


def number_to_words_fr(number: float) -> str:
    """Convertit un montant en FCFA en toutes lettres (ex: 35000 -> Trente-cinq mille FCFA)."""
    try:
        n = int(round(float(number)))
    except (ValueError, TypeError):
        return ""
    if n <= 0:
        return "Zéro FCFA"

    units = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"]
    teens = ["dix", "onze", "douze", "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
    tens = ["", "dix", "vingt", "trente", "quarante", "cinquante", "soixante", "soixante-dix", "quatre-vingts", "quatre-vingt-dix"]

    def convert_below_1000(num):
        if num == 0:
            return ""
        res = []
        c = num // 100
        r = num % 100
        if c > 0:
            if c == 1:
                res.append("cent")
            else:
                res.append(units[c] + " cent" + ("s" if r == 0 else ""))
        if r > 0:
            if r < 10:
                res.append(units[r])
            elif r < 20:
                res.append(teens[r - 10])
            else:
                t = r // 10
                u = r % 10
                if t in (7, 9):
                    base_t = tens[t - 1]
                    rem_val = r - (t - 1) * 10
                    res.append(base_t + (" et " if u == 1 and t == 7 else "-") + teens[rem_val - 10])
                else:
                    base_t = tens[t]
                    if t == 8 and u == 0:
                        res.append("quatre-vingts")
                    elif u == 1 and t != 8:
                        res.append(base_t + " et un")
                    elif u > 0:
                        res.append(base_t + "-" + units[u])
                    else:
                        res.append(base_t)
        return " ".join(res)

    parts = []
    millions = n // 1_000_000
    remainder = n % 1_000_000
    thousands = remainder // 1_000
    units_part = remainder % 1_000

    if millions > 0:
        parts.append("un million" if millions == 1 else convert_below_1000(millions) + " millions")
    if thousands > 0:
        parts.append("mille" if thousands == 1 else convert_below_1000(thousands) + " mille")
    if units_part > 0:
        parts.append(convert_below_1000(units_part))

    words = " ".join(parts).strip()
    return (words.capitalize() + " FCFA") if words else ""


def extraire_lignes_commande(commande):
    """
    Extrait une liste unifiée et ordonnée de tous les articles d'une commande
    (parfums, accessoires, essences, diffuseurs, créations sur-mesure)
    pour un rendu soigné et harmonieux dans la facture PDF et l'email client.
    """
    lignes = []

    # 1. Parfums standard
    for lp in commande.lignes_parfums.select_related('parfum').all():
        contenance = f" ({lp.parfum.contenance_ml} ml)" if (lp.parfum and lp.parfum.contenance_ml) else ""
        lignes.append({
            'type': 'Parfum',
            'nom': f"{lp.nom_snapshot}{contenance}",
            'quantite': lp.quantite,
            'prix_unitaire': lp.prix_unitaire_snapshot,
            'sous_total': lp.sous_total,
        })

    # 2. Accessoires standard
    for la in commande.lignes_accessoires.select_related('accessoire').all():
        lignes.append({
            'type': 'Accessoire',
            'nom': la.nom_snapshot,
            'quantite': la.quantite,
            'prix_unitaire': la.prix_unitaire_snapshot,
            'sous_total': la.sous_total,
        })

    # 3. Produits finis essence
    for le in commande.lignes_produit_fini_essence.select_related('produit_fini_essence__essence').all():
        taille = f" ({le.produit_fini_essence.taille_ml} ml)" if (le.produit_fini_essence and le.produit_fini_essence.taille_ml) else ""
        lignes.append({
            'type': 'Essence',
            'nom': f"{le.nom_snapshot}{taille}",
            'quantite': le.quantite,
            'prix_unitaire': le.prix_unitaire_snapshot,
            'sous_total': le.sous_total,
        })

    # 4. Diffuseurs de parfum
    for ld in commande.lignes_diffuseurs.select_related('diffuseur').all():
        lignes.append({
            'type': 'Diffuseur',
            'nom': ld.nom_snapshot,
            'quantite': ld.quantite,
            'prix_unitaire': ld.prix_unitaire_snapshot,
            'sous_total': ld.sous_total,
        })

    # 5. Parfums personnalisés
    for lpp in commande.lignes_parfums_perso.select_related('parfum_personnalise__flacon').all():
        flacon_nom = lpp.parfum_personnalise.flacon.nom if (lpp.parfum_personnalise and lpp.parfum_personnalise.flacon) else ""
        flacon_txt = f" (Flacon {flacon_nom})" if flacon_nom else ""
        nom = lpp.parfum_personnalise.nom if lpp.parfum_personnalise else "Parfum sur-mesure"
        lignes.append({
            'type': 'Sur-Mesure',
            'nom': f"{nom}{flacon_txt}",
            'quantite': lpp.quantite,
            'prix_unitaire': lpp.prix_snapshot,
            'sous_total': lpp.sous_total,
        })

    # 6. Essences personnalisées
    for lep in commande.lignes_essence_personnalisee.select_related('essence_personnalise').all():
        nom = lep.essence_personnalise.nom if lep.essence_personnalise else "Essence personnalisée"
        lignes.append({
            'type': 'Essence Sur-Mesure',
            'nom': nom,
            'quantite': lep.quantite,
            'prix_unitaire': getattr(lep, 'prix_snapshot', getattr(lep, 'prix_calcule', 0)),
            'sous_total': lep.sous_total,
        })

    return lignes


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
            except Exception:
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
    if not os.path.exists(logo_path):
        logo_path = None

    # Gérer le client et l'utilisateur
    client_obj = commande.client if getattr(commande, 'client', None) else None
    user_obj = getattr(client_obj, 'user', None) if client_obj else None

    # Informations sur l'entreprise pour l'en-tête de la facture
    try:
        from catalogue.models import EntrepriseInfo
        entreprise = EntrepriseInfo.objects.first()
    except Exception:
        entreprise = None

    telephones = []
    if entreprise:
        if entreprise.telephone_principal:
            telephones.append(entreprise.telephone_principal)
        if entreprise.telephone_secondaire:
            telephones.append(entreprise.telephone_secondaire)
        if not telephones and entreprise.whatsapp:
            telephones.append(entreprise.whatsapp)

    entreprise_telephone = " / ".join(telephones) if telephones else "+237 693 835 601 / 680 215 310"
    entreprise_email = 'accessoiresexclusifs@gmail.com'

    total_en_lettres = number_to_words_fr(commande.total_ttc)
    lignes_articles = extraire_lignes_commande(commande)
    vendeur_nom = (commande.vendeur.get_full_name() or commande.vendeur.first_name) if commande.vendeur else None

    context = {
        'facture': facture,
        'commande': commande,
        'client': client_obj,
        'user': user_obj,
        'logo_path': logo_path,
        'date_emission': facture.date_emission,
        'lignes_articles': lignes_articles,
        'vendeur_nom': vendeur_nom,
        'entreprise_telephone': entreprise_telephone,
        'entreprise_email': entreprise_email,
        'total_en_lettres': total_en_lettres,
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
    email_client = None
    if client_obj and getattr(client_obj, 'user', None) and getattr(client_obj.user, 'email', None):
        email_client = client_obj.user.email

    if email_client:
        try:
            envoyer_email_facture(facture, pdf_content, email_client)
        except Exception as e:
            logger.error(f"[FACTURE] Erreur envoi email pour {facture.numero_facture}: {e}")

    return facture


from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

def envoyer_email_facture(facture, pdf_content: bytes, email_destinataire: str):
    """
    Envoie la facture PDF par email au client avec un design HTML Premium.
    """
    commande = facture.commande
    client = commande.client
    user = getattr(client, 'user', None) if client else None
    prenom = (user.first_name or user.username) if user else (commande.livraison_nom_complet or 'Cher client')
    vendeur_nom = (commande.vendeur.get_full_name() or commande.vendeur.first_name) if commande.vendeur else None

    try:
        from catalogue.models import EntrepriseInfo
        entreprise = EntrepriseInfo.objects.first()
    except Exception:
        entreprise = None

    telephones = []
    if entreprise:
        if entreprise.telephone_principal:
            telephones.append(entreprise.telephone_principal)
        if entreprise.telephone_secondaire:
            telephones.append(entreprise.telephone_secondaire)
        if not telephones and entreprise.whatsapp:
            telephones.append(entreprise.whatsapp)

    entreprise_telephone = " / ".join(telephones) if telephones else "+237 693 835 601 / 680 215 310"
    entreprise_email = 'accessoiresexclusifs@gmail.com'

    sujet = f"Votre facture {facture.numero_facture} — Accessoires Exclusifs"
    
    # 1. Version texte brut (Fallback)
    corps_texte = f"""Bonjour {prenom},

Nous vous remercions pour votre achat.
Votre commande {commande.numero_commande} a bien été enregistrée et réglée avec succès.
Veuillez trouver ci-joint votre facture officielle {facture.numero_facture} d'un montant de {commande.total_ttc:,.0f} FCFA.

Pour voir les détails en ligne, visitez : {settings.FRONTEND_URL}/mes-commandes/{commande.numero_commande}

Cordialement,
L'équipe Accessoires Exclusifs
Redefine your style
"""

    # 2. Construction de l'URL pour le bouton
    url_commande = f"{settings.FRONTEND_URL.rstrip('/')}/mes-commandes/{commande.numero_commande}"

    # 3. Version HTML générée à partir du template
    context = {
        'prenom': prenom,
        'commande': commande,
        'facture': facture,
        'url_commande': url_commande,
        'lignes_articles': extraire_lignes_commande(commande),
        'vendeur_nom': vendeur_nom,
        'entreprise_telephone': entreprise_telephone,
        'entreprise_email': entreprise_email,
        'DEVISE': 'FCFA',
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
