#!/usr/bin/env python3
"""
Script d'importation des essences depuis numba_essences_complet.csv

Règles appliquées :
  - Catégorie : 'high' pour toutes les essences.
  - Formats des produits finis : 10 ml (3 000 FCFA), 15 ml (4 500 FCFA), 30 ml (9 000 FCFA).
  - Lot de laboratoire : 2 000 ml pour chaque essence.
  - Essences existantes : Les informations de base sont préservées,
    le lot de 2 000 ml et les produits finis correspondants sont créés s'ils n'existent pas.
  - Support de l'option --dry-run pour tester sans persister en base.
"""

import argparse
import csv
import os
import sys
from decimal import Decimal

import django

# Configuration de l'environnement Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.db import transaction
from django.utils.text import slugify
from catalogue.models import Essence, LotEssence, ProduitFiniEssence

DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "numba_essences_complet.csv",
)

# Configuration métier
CATEGORIE_CIBLE = "high"
LOT_QUANTITE_ML = Decimal("2000")
PRIX_PAR_ML_DEFAULT = Decimal("300.00")

FORMATS_PRIX = {
    10: Decimal("3000.00"),
    15: Decimal("4500.00"),
    30: Decimal("9000.00"),
}

INTENSITE_MAP = {
    "légère": "légère",
    "legere": "légère",
    "faible": "légère",
    "douce": "légère",
    "modérée": "moyenne",
    "moderee": "moyenne",
    "moyenne": "moyenne",
    "forte": "forte",
    "intense": "forte",
    "très forte": "très forte",
    "tres forte": "très forte",
}

GENRE_MAP = {
    "homme": "homme",
    "man": "homme",
    "femme": "femme",
    "woman": "femme",
    "mixte": "mixte",
    "unisex": "mixte",
    "unisexe": "mixte",
}


def clean_text(value):
    return (value or "").strip()


def normalize_intensite(raw):
    return INTENSITE_MAP.get(clean_text(raw).lower(), "forte")


def normalize_genre(raw):
    return GENRE_MAP.get(clean_text(raw).lower(), "mixte")


def generate_code_reference(marque, nom, index):
    base_slug = slugify(f"{marque}-{nom}")[:20].upper()
    base_code = f"NUMBA-{index:03d}"
    candidate = base_code
    suffix = 0
    while Essence.objects.filter(code_reference=candidate).exists():
        suffix += 1
        candidate = f"NUMBA-{base_slug}-{suffix}"
    return candidate


def run_import(csv_path=DEFAULT_CSV_PATH, dry_run=False):
    if not os.path.exists(csv_path):
        print(f"❌ Erreur : Le fichier CSV est introuvable à l'emplacement : {csv_path}")
        sys.exit(1)

    print("=" * 70)
    print(f" IMPORT DES ESSENCES NUMBA (Catégorie : {CATEGORIE_CIBLE.upper()})")
    print(f" Fichier : {os.path.basename(csv_path)}")
    print(f" Mode    : {'[SIMULATION - DRY RUN]' if dry_run else '[RÉEL - ÉCRITURE BD]'}")
    print("=" * 70)

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total_rows = len(rows)
    print(f"-> {total_rows} ligne(s) détectée(s) dans le fichier CSV.\n")

    stats = {
        "essences_creees": 0,
        "essences_existantes": 0,
        "lots_crees": 0,
        "lots_deja_presents": 0,
        "produits_finis_crees": 0,
        "produits_finis_deja_presents": 0,
        "erreurs": [],
    }

    try:
        with transaction.atomic():
            for line_no, row in enumerate(rows, start=1):
                nom = clean_text(row.get("Nom"))
                marque = clean_text(row.get("Marque"))

                if not nom or not marque:
                    msg = f"Ligne {line_no} : Nom ou Marque manquant -> ignorée"
                    stats["erreurs"].append(msg)
                    print(f"  [!] {msg}")
                    continue

                label = f"{nom} ({marque})"

                # 1. Recherche ou Création de l'Essence
                essence = Essence.objects.filter(
                    nom__iexact=nom,
                    marque__iexact=marque,
                    categorie=CATEGORIE_CIBLE
                ).first()

                if essence:
                    stats["essences_existantes"] += 1
                    status_essence = "EXISTANTE (infos préservées)"
                else:
                    status_essence = "NOUVELLE"
                    code_ref = generate_code_reference(marque, nom, line_no)
                    description = clean_text(row.get("Description"))
                    couleur = clean_text(row.get("Couleur")) or "Ambré / Doré"
                    duree = clean_text(row.get("Durée")) or "Longue (8-10h)"
                    intensite = normalize_intensite(row.get("Intensité"))
                    genre = normalize_genre(row.get("Genre Cible"))
                    notes_tete = clean_text(row.get("Note de Tête"))
                    notes_coeur = clean_text(row.get("Note de Coeur"))
                    notes_fond = clean_text(row.get("Note de Fond"))

                    if not dry_run:
                        essence = Essence.objects.create(
                            marque=marque,
                            nom=nom,
                            code_reference=code_ref,
                            categorie=CATEGORIE_CIBLE,
                            description=description,
                            description_ia=description,
                            couleur=couleur,
                            duree=duree,
                            intensite=intensite,
                            genre_cible=genre,
                            notes_tete=notes_tete,
                            notes_coeur=notes_coeur,
                            notes_fond=notes_fond,
                            prix_par_ml=PRIX_PAR_ML_DEFAULT,
                            fournisseur="Numba",
                            actif=True,
                        )
                    else:
                        essence = Essence(
                            marque=marque,
                            nom=nom,
                            code_reference=code_ref,
                            categorie=CATEGORIE_CIBLE,
                            prix_par_ml=PRIX_PAR_ML_DEFAULT,
                            actif=True,
                        )
                    stats["essences_creees"] += 1

                print(f"[{line_no:>3}/{total_rows}] {label} -> {status_essence}")

                # 2. Gestion du Lot de 2 000 ml
                ref_fournisseur_lot = f"LOT-NUMBA-2000-{essence.code_reference if essence.code_reference else line_no}"
                
                if not dry_run:
                    lot_existant = LotEssence.objects.filter(
                        essence=essence,
                        reference_fournisseur=ref_fournisseur_lot
                    ).first()

                    if lot_existant:
                        stats["lots_deja_presents"] += 1
                    else:
                        stock_prec = essence.stock_total_ml()
                        LotEssence.objects.create(
                            essence=essence,
                            stock_ml=LOT_QUANTITE_ML,
                            quantite_initiale_ml=LOT_QUANTITE_ML,
                            stock_precedent_ml=stock_prec,
                            prix_achat_par_ml=Decimal("0.00"),
                            reference_fournisseur=ref_fournisseur_lot,
                            actif=True,
                        )
                        stats["lots_crees"] += 1
                        print(f"       + Lot {LOT_QUANTITE_ML} ml créé")
                else:
                    stats["lots_crees"] += 1

                # 3. Gestion des Produits Finis (10 ml, 15 ml, 30 ml)
                for taille, prix in FORMATS_PRIX.items():
                    if not dry_run:
                        pf, pf_created = ProduitFiniEssence.objects.get_or_create(
                            essence=essence,
                            taille_ml=taille,
                            defaults={"prix": prix, "actif": True}
                        )
                        if pf_created:
                            stats["produits_finis_crees"] += 1
                            print(f"       + Produit fini {taille:>2} ml : {prix} FCFA")
                        else:
                            stats["produits_finis_deja_presents"] += 1
                            if pf.prix != prix:
                                pf.prix = prix
                                pf.save(update_fields=["prix"])
                                print(f"       ~ Produit fini {taille:>2} ml : prix mis à jour à {prix} FCFA")
                    else:
                        stats["produits_finis_crees"] += 1

            if dry_run:
                # En mode dry-run, on force le rollback
                transaction.set_rollback(True)

    except Exception as exc:
        print(f"\n❌ Une erreur critique est survenue : {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 70)
    print(" RÉSUMÉ DE L'IMPORTATION")
    print("=" * 70)
    print(f"  • Essences créées (nouvelles)      : {stats['essences_creees']}")
    print(f"  • Essences existantes conservées   : {stats['essences_existantes']}")
    print(f"  • Lots de {LOT_QUANTITE_ML} ml créés             : {stats['lots_crees']}")
    print(f"  • Lots déjà présents               : {stats['lots_deja_presents']}")
    print(f"  • Produits finis créés             : {stats['produits_finis_crees']}")
    print(f"  • Produits finis déjà présents     : {stats['produits_finis_deja_presents']}")
    if stats["erreurs"]:
        print(f"  • Erreurs rencontrées              : {len(stats['erreurs'])}")
        for err in stats["erreurs"]:
            print(f"     - {err}")
    print("=" * 70)
    if dry_run:
        print(" [SIMULATION TERMINÉE] Aucune donnée n'a été modifiée en base de données.")
    else:
        print(" [SUCCÈS] Toutes les données ont été enregistrées avec succès en base de données !")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importer les essences Numba depuis un fichier CSV.")
    parser.add_argument(
        "--csv",
        type=str,
        default=DEFAULT_CSV_PATH,
        help="Chemin vers le fichier CSV (défaut : numba_essences_complet.csv)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simuler l'exécution sans enregistrer de modifications en base de données."
    )
    args = parser.parse_args()

    run_import(csv_path=args.csv, dry_run=args.dry_run)
