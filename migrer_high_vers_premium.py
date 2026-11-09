#!/usr/bin/env python
"""
=============================================================================
SCRIPT : migrer_high_vers_premium.py
=============================================================================
Objectif :
  - Déplacer toutes les essences de la catégorie "high" vers "premium".
  - Si une essence de même NOM + même MARQUE existe déjà en "premium" :
      → Supprimer l'essence "high" (cascade : ses ProduitFiniEssence + LotEssence)
      → Laisser l'ancienne essence "premium" intacte, sans aucune modification.
  - Si aucun doublon n'existe en "premium" :
      → Changer la catégorie de l'essence "high" → "premium".

Usage (depuis la racine du projet Django) :
  python migrer_high_vers_premium.py

OU via manage.py shell :
  python manage.py shell < migrer_high_vers_premium.py
=============================================================================
"""

import os
import sys
import django

# ---------------------------------------------------------------------------
# Initialisation Django (si lancé directement, pas via manage.py shell)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

# ---------------------------------------------------------------------------
# Imports après setup Django
# ---------------------------------------------------------------------------
from django.db import transaction
from catalogue.models import Essence, ProduitFiniEssence, LotEssence

# ---------------------------------------------------------------------------
# Couleurs terminal
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def log(msg, color=RESET):
    print(f"{color}{msg}{RESET}")

# ---------------------------------------------------------------------------
# SCRIPT PRINCIPAL
# ---------------------------------------------------------------------------
def migrer():
    essences_high = Essence.objects.filter(categorie='high').order_by('marque', 'nom')
    total = essences_high.count()

    if total == 0:
        log("✅  Aucune essence en catégorie 'high' trouvée. Rien à faire.", GREEN)
        return

    log(f"\n{'='*65}", BOLD)
    log(f"  MIGRATION : high → premium  ({total} essence(s) à traiter)", BOLD)
    log(f"{'='*65}\n", BOLD)

    deplacees     = []
    supprimees    = []
    erreurs       = []

    for essence_high in essences_high:
        label = f"{essence_high.marque} - {essence_high.nom}  [id={essence_high.id}]"

        # Cherche un doublon en premium (même nom + même marque, insensible à la casse)
        doublon_premium = Essence.objects.filter(
            marque__iexact=essence_high.marque,
            nom__iexact=essence_high.nom,
            categorie='premium'
        ).first()

        try:
            with transaction.atomic():
                if doublon_premium:
                    # ── Doublon trouvé → on supprime l'essence high ──────────
                    nb_pf   = ProduitFiniEssence.objects.filter(essence=essence_high).count()
                    nb_lots = LotEssence.objects.filter(essence=essence_high).count()

                    # La suppression cascade automatiquement ProduitFiniEssence et LotEssence
                    essence_high.delete()

                    supprimees.append({
                        'label'   : label,
                        'doublon' : f"{doublon_premium.marque} - {doublon_premium.nom}  [id={doublon_premium.id}]",
                        'nb_pf'   : nb_pf,
                        'nb_lots' : nb_lots,
                    })
                    log(f"  🗑️  SUPPRIMÉ  : {label}", YELLOW)
                    log(f"       ↳ Doublon premium conservé : id={doublon_premium.id}", YELLOW)
                    log(f"       ↳ Produits finis supprimés : {nb_pf}", YELLOW)
                    log(f"       ↳ Lots d'essence supprimés : {nb_lots}", YELLOW)

                else:
                    # ── Pas de doublon → on déplace vers premium ─────────────
                    # Mise à jour de la catégorie uniquement
                    # Note : unique_together = ['marque', 'nom', 'categorie']
                    # Donc passer 'high' → 'premium' est safe si pas de doublon premium.
                    essence_high.categorie = 'premium'
                    essence_high.save(update_fields=['categorie'])

                    nb_pf   = ProduitFiniEssence.objects.filter(essence=essence_high).count()
                    nb_lots = LotEssence.objects.filter(essence=essence_high).count()

                    deplacees.append({
                        'label'   : label,
                        'nb_pf'   : nb_pf,
                        'nb_lots' : nb_lots,
                    })
                    log(f"  ✅  DÉPLACÉ   : {label}", GREEN)
                    log(f"       ↳ Produits finis liés : {nb_pf}", GREEN)
                    log(f"       ↳ Lots d'essence liés : {nb_lots}", GREEN)

        except Exception as e:
            erreurs.append({'label': label, 'erreur': str(e)})
            log(f"  ❌  ERREUR sur {label} : {e}", RED)

    # ── Résumé ────────────────────────────────────────────────────────────
    log(f"\n{'='*65}", BOLD)
    log(f"  RÉSUMÉ", BOLD)
    log(f"{'='*65}", BOLD)
    log(f"  Essences déplacées (high → premium) : {len(deplacees)}", GREEN)
    log(f"  Essences supprimées (doublons)       : {len(supprimees)}", YELLOW)
    log(f"  Erreurs                              : {len(erreurs)}", RED if erreurs else RESET)

    if deplacees:
        log(f"\n{CYAN}── Déplacées ──{RESET}")
        for e in deplacees:
            log(f"   • {e['label']}  (pf={e['nb_pf']}, lots={e['nb_lots']})")

    if supprimees:
        log(f"\n{YELLOW}── Supprimées (doublon premium existant) ──{RESET}")
        for e in supprimees:
            log(f"   • {e['label']}")
            log(f"     ↳ Conservé : {e['doublon']}")
            log(f"     ↳ Supprimé avec {e['nb_pf']} produit(s) fini(s) et {e['nb_lots']} lot(s)")

    if erreurs:
        log(f"\n{RED}── Erreurs ──{RESET}")
        for e in erreurs:
            log(f"   • {e['label']} → {e['erreur']}", RED)

    log(f"\n{'='*65}\n", BOLD)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    migrer()

