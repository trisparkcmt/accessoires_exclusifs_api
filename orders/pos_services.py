import io
import os
import logging
from decimal import Decimal
from collections import defaultdict
from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from django.db.models import Sum, Count, Q

logger = logging.getLogger(__name__)


def calculer_donnees_journee_caissiere(caissiere_user, target_date=None):
    """
    Calcule en temps réel l'ensemble des activités enregistrées pour une caissière à une date donnée :
    - Sorties d'articles (ventes POS avec quantités et montants)
    - Recette totale du jour
    - Entrées de stock effectuées par elle
    - Dépenses de caisse saisies par elle
    """
    from orders.models import (
        Commande,
        CommandeLigneParfum,
        CommandeLigneAccessoire,
        CommandeProduitFiniEssence,
        CommandeLigneDiffuseurParfum,
        CommandeLigneParfumPerso,
        CommandeLigneEssencePersonnalisee,
    )
    from catalogue.models import MouvementStock
    from utilisateur.models import Depense

    if not target_date:
        target_date = timezone.now().date()

    # 1. Commandes POS vendues par cette caissière (payées, non annulées)
    commandes_qs = Commande.objects.filter(
        vendeur=caissiere_user,
        date_creation__date=target_date,
        statut_paiement='payé'
    ).exclude(statut='annulée')

    cmd_ids = list(commandes_qs.values_list('id', flat=True))

    recette_totale = commandes_qs.aggregate(total=Sum('total_ttc'))['total'] or Decimal('0.00')
    nombre_ventes = len(cmd_ids)

    # 2. Sorties d'articles (détail par produit vendu)
    sorties_map = defaultdict(lambda: {'nom': '', 'quantite': 0, 'sous_total': Decimal('0.00'), 'type': ''})

    # A. Parfums
    for ligne in CommandeLigneParfum.objects.filter(commande_id__in=cmd_ids):
        nom = ligne.nom_snapshot or (ligne.parfum.nom if ligne.parfum else "Parfum inconnu")
        key = f"parfum_{nom}"
        sorties_map[key]['nom'] = nom
        sorties_map[key]['quantite'] += ligne.quantite
        sorties_map[key]['sous_total'] += ligne.sous_total
        sorties_map[key]['type'] = 'parfum'

    # B. Accessoires
    for ligne in CommandeLigneAccessoire.objects.filter(commande_id__in=cmd_ids):
        nom = ligne.nom_snapshot or (ligne.accessoire.nom if ligne.accessoire else "Accessoire inconnu")
        key = f"accessoire_{nom}"
        sorties_map[key]['nom'] = nom
        sorties_map[key]['quantite'] += ligne.quantite
        sorties_map[key]['sous_total'] += ligne.sous_total
        sorties_map[key]['type'] = 'accessoire'

    # C. Produits finis essences
    for ligne in CommandeProduitFiniEssence.objects.filter(commande_id__in=cmd_ids):
        nom = ligne.nom_snapshot or (ligne.produit_fini_essence.essence.nom_complet if ligne.produit_fini_essence else "Essence")
        key = f"essence_{nom}"
        sorties_map[key]['nom'] = nom
        sorties_map[key]['quantite'] += ligne.quantite
        sorties_map[key]['sous_total'] += ligne.sous_total
        sorties_map[key]['type'] = 'essence'

    # D. Diffuseurs
    for ligne in CommandeLigneDiffuseurParfum.objects.filter(commande_id__in=cmd_ids):
        nom = ligne.nom_snapshot or (ligne.diffuseur.nom if ligne.diffuseur else "Diffuseur")
        key = f"diffuseur_{nom}"
        sorties_map[key]['nom'] = nom
        sorties_map[key]['quantite'] += ligne.quantite
        sorties_map[key]['sous_total'] += ligne.sous_total
        sorties_map[key]['type'] = 'diffuseur'

    # E. Parfums personnalisés
    for ligne in CommandeLigneParfumPerso.objects.filter(commande_id__in=cmd_ids):
        nom = ligne.parfum_personnalise.nom if ligne.parfum_personnalise else "Parfum personnalisé"
        key = f"parfum_perso_{nom}"
        sorties_map[key]['nom'] = nom
        sorties_map[key]['quantite'] += ligne.quantite
        sorties_map[key]['sous_total'] += ligne.sous_total
        sorties_map[key]['type'] = 'parfum_perso'

    # F. Essences personnalisées
    for ligne in CommandeLigneEssencePersonnalisee.objects.filter(commande_id__in=cmd_ids):
        nom = ligne.essence_personnalisee.nom if ligne.essence_personnalisee else "Essence personnalisée"
        key = f"essence_perso_{nom}"
        sorties_map[key]['nom'] = nom
        sorties_map[key]['quantite'] += ligne.quantite
        sorties_map[key]['sous_total'] += ligne.sous_total
        sorties_map[key]['type'] = 'essence_perso'

    sorties_list = []
    for item in sorties_map.values():
        sorties_list.append({
            'nom': item['nom'],
            'quantite': int(item['quantite']),
            'sous_total': float(item['sous_total']),
            'type': item['type'],
        })
    sorties_list.sort(key=lambda x: x['nom'])

    # Rattrapage automatique pour les produits créés ce jour avec du stock mais sans mouvement tracé
    from catalogue.models import Parfum, Accessoire
    parfums_du_jour = Parfum.objects.filter(date_creation__date=target_date, stock_quantite__gt=0)
    for p in parfums_du_jour:
        if not MouvementStock.objects.filter(type_produit='parfum', produit_id=p.id).exists():
            MouvementStock.objects.create(
                utilisateur=caissiere_user if not getattr(caissiere_user, 'is_superuser', False) else None,
                type_produit='parfum',
                produit_id=p.id,
                nom_produit=p.nom,
                quantite_avant=Decimal('0'),
                quantite_apres=Decimal(str(p.stock_quantite)),
                quantite_ajoutee=Decimal(str(p.stock_quantite)),
            )

    accessoires_du_jour = Accessoire.objects.filter(date_creation__date=target_date, stock_quantite__gt=0)
    for a in accessoires_du_jour:
        if not MouvementStock.objects.filter(type_produit='accessoire', produit_id=a.id).exists():
            MouvementStock.objects.create(
                utilisateur=caissiere_user if not getattr(caissiere_user, 'is_superuser', False) else None,
                type_produit='accessoire',
                produit_id=a.id,
                nom_produit=a.nom,
                quantite_avant=Decimal('0'),
                quantite_apres=Decimal(str(a.stock_quantite)),
                quantite_ajoutee=Decimal(str(a.stock_quantite)),
            )

    # 3. Entrées de stock effectuées par cette caissière (ou au niveau de la boutique)
    mouvements_qs = MouvementStock.objects.filter(
        utilisateur=caissiere_user,
        date_ajout__date=target_date,
        quantite_ajoutee__gt=0
    ).order_by('-date_ajout')

    if not mouvements_qs.exists():
        # Fallback : toutes les entrées de stock enregistrées pour la boutique ce jour
        mouvements_qs = MouvementStock.objects.filter(
            date_ajout__date=target_date,
            quantite_ajoutee__gt=0
        ).order_by('-date_ajout')

    entrees_list = []
    for m in mouvements_qs:
        entrees_list.append({
            'nom': m.nom_produit,
            'quantite_ajoutee': float(m.quantite_ajoutee),
            'type_produit': m.type_produit,
            'date': m.date_ajout.strftime('%H:%M'),
        })

    # 4. Dépenses de caisse effectuées par cette caissière (ou au niveau de la caisse boutique)
    depenses_qs = Depense.objects.filter(
        cree_par=caissiere_user,
        date_depense=target_date
    ).order_by('date_creation')

    if not depenses_qs.exists():
        # Fallback : toutes les dépenses enregistrées en boutique ce jour
        depenses_qs = Depense.objects.filter(
            Q(date_depense=target_date) | Q(date_creation__date=target_date)
        ).order_by('date_creation')

    total_depenses = depenses_qs.aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

    depenses_list = []
    for d in depenses_qs:
        depenses_list.append({
            'id': d.id,
            'titre': d.titre,
            'montant': float(d.montant),
            'description': d.description or '',
        })

    reste_en_caisse = recette_totale - total_depenses

    return {
        'date': target_date.strftime('%Y-%m-%d'),
        'recette_totale': float(recette_totale),
        'nombre_ventes': nombre_ventes,
        'sorties_articles': sorties_list,
        'entrees_stock': entrees_list,
        'total_depenses': float(total_depenses),
        'depenses': depenses_list,
        'reste_en_caisse': float(reste_en_caisse),
    }


def formater_texte_whatsapp(rapport):
    """
    Formate le rapport exactement dans le style WhatsApp avec les emojis demandés.
    """
    date_str = rapport.date.strftime('%d %B %Y') if hasattr(rapport.date, 'strftime') else str(rapport.date)
    
    # 1. Horaires
    arrivee = rapport.heure_arrivee or "Non renseignée"
    depart = rapport.heure_depart or "Non renseignée"

    # 2. Sorties parfums / accessoires
    lignes_sorties = []
    if rapport.sorties_articles:
        for s in rapport.sorties_articles:
            lignes_sorties.append(f" {s.get('nom', 'Article')} ({s.get('quantite', 1)}) -")
    sorties_txt = "\n".join(lignes_sorties) if lignes_sorties else " RAS"

    # 3. Entrées parfums / accessoires
    lignes_entrees = []
    if rapport.entrees_stock:
        for e in rapport.entrees_stock:
            lignes_entrees.append(f" {e.get('nom', 'Produit')} (+{e.get('quantite_ajoutee', 0)}) -")
    entrees_txt = "\n".join(lignes_entrees) if lignes_entrees else " RAS"

    # 4. Bilan financier
    recette_fmt = f"{int(rapport.recette_totale):,} FCFA".replace(',', '.')
    
    # Dépenses
    lignes_depenses = []
    if rapport.depenses:
        for d in rapport.depenses:
            mt = f"{int(d.get('montant', 0)):,}f".replace(',', '.')
            titre = d.get('titre', 'Dépense')
            lignes_depenses.append(f"           Dépense  -  {mt} {titre}")
    depenses_txt = "\n".join(lignes_depenses) if lignes_depenses else "           Dépense  -  RAS"

    # Autres données manuelles (ex: Reçu cash, Reçu dépôt)
    autres_lignes = []
    if rapport.autres_donnees_manuelles and isinstance(rapport.autres_donnees_manuelles, dict):
        for k, v in rapport.autres_donnees_manuelles.items():
            autres_lignes.append(f"           {k} : {v}")
    autres_txt = "\n" + "\n".join(autres_lignes) if autres_lignes else ""

    reste_caisse = f"{int(rapport.reste_en_caisse):,} FCFA".replace(',', '.') if rapport.reste_en_caisse else "0 FCFA"

    # 5. Actions de communication digitale
    com_txt = rapport.actions_communication.strip() if rapport.actions_communication else "RAS"

    # 6. Observations éventuelles
    obs_block = f"\n\n📝 *Observations :*\n{rapport.observations.strip()}" if rapport.observations else ""

    texte = f"""📅 Rapport du {date_str}

🕒 Horaires :
	•	Arrivée : {arrivee} 
	•	Départ : {depart} 

🧴 sorties parfums / accessoires
{sorties_txt}

🧴 Entrées parfums / accessoires 
{entrees_txt}

*bilan financier*  
         Recette du jour: {recette_fmt}{autres_txt}
{depenses_txt}
      *Reste en caisse: * {reste_caisse}
    
📲 Actions de communication digitale :
{com_txt}{obs_block}"""

    return texte.strip()


def generer_rapport_caisse_pdf(rapport):
    """
    Génère le PDF du rapport de caisse via xhtml2pdf et l'associe à rapport.fichier_pdf.
    """
    from xhtml2pdf import pisa
    from catalogue.models import EntrepriseInfo

    entreprise = EntrepriseInfo.objects.first()
    logo_path = os.path.join(settings.BASE_DIR, 'staticfiles', 'img', 'logo.png')
    logo_existe = os.path.exists(logo_path)

    context = {
        'rapport': rapport,
        'entreprise': entreprise,
        'logo_path': logo_path if logo_existe else None,
        'now': timezone.now(),
    }

    html_string = render_to_string('pos/rapport_caisse_pdf.html', context)
    pdf_buffer = io.BytesIO()

    try:
        pisa_status = pisa.CreatePDF(
            html_string,
            dest=pdf_buffer,
            encoding='UTF-8',
        )
        if pisa_status.err:
            logger.error(f"[RAPPORT CAISSE] Erreur xhtml2pdf pour rapport #{rapport.id}: {pisa_status.err}")
            return None
    except Exception as e:
        logger.exception(f"[RAPPORT CAISSE] Exception xhtml2pdf pour rapport #{rapport.id}: {e}")
        return None

    pdf_content = pdf_buffer.getvalue()
    pdf_buffer.close()

    import time
    ts = int(time.time())
    date_label = str(rapport.date).replace('-', '')
    nom_fichier = f"rapport_caisse_{rapport.caissiere_id}_{date_label}_{rapport.id}_{ts}.pdf"

    if rapport.fichier_pdf:
        try:
            rapport.fichier_pdf.delete(save=False)
        except Exception:
            pass

    rapport.fichier_pdf.save(
        nom_fichier,
        ContentFile(pdf_content),
        save=True
    )

    logger.info(f"[RAPPORT CAISSE] PDF généré avec succès : {nom_fichier}")
    return rapport.fichier_pdf

