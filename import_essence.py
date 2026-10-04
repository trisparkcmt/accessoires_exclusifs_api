#!/usr/bin/env python3
"""
Import d'essences depuis catalogue_parfums_accessoires_exclusifs.csv

Colonnes CSV :
  marque, nom, intensite, genre cible,
  famille olfative, note de tete, note de coeur, note de fond,
  saison, occasion, humeur, climat conseille,
  description longue, description courte, description ia

Comportement :
  - Même marque + même nom en BD          → SKIP (log, BD intacte)
  - Nouveau                               → CRÉATION essence
                                          → CRÉATION lot 1000 ml
                                          → CRÉATION produits finis 10 / 15 / 30 ml
                                          → CRÉATION tags (colonnes non-directes)
"""

import csv
import os
import sys

import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from decimal import Decimal

from django.db import transaction
from django.utils.text import slugify

from catalogue.models import Essence, LotEssence, ProduitFiniEssence, Tag, TagEssence

# ─── Fichier CSV ──────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "catalogue_parfums_accessoires_exclusifs.csv",
)

# ─── Formats de flacons à créer pour chaque essence ──────────────────────────
FORMATS_ML = [10, 15, 30]
PRIX_PAR_FORMAT = {
    10: Decimal("2500"),
    15: Decimal("3500"),
    30: Decimal("6000"),
}

# ─── Colonnes CSV → champs directs du modèle Essence ─────────────────────────
DIRECT_FIELDS = {
    "marque":             "marque",
    "nom":                "nom",
    "intensite":          "intensite",
    "genre cible":        "genre_cible",
    "note de tete":       "notes_tete",
    "note de coeur":      "notes_coeur",
    "note de fond":       "notes_fond",
    "description longue": "description",
    "description courte": "description",      # fallback si description longue vide
    "description ia":     "description_ia",
}

# ─── Colonnes CSV → Tags (toutes les colonnes non-directes) ──────────────────
TAG_COLUMNS = {
    "famille olfative": "Famille olfactive",
    "saison":           "Saison",
    "occasion":         "Occasion",
    "humeur":           "Humeur",
    "climat conseille": "Climat conseillé",
}

# ─── Normalisation des valeurs ────────────────────────────────────────────────
INTENSITE_MAP = {
    "légère":     "légère",
    "legere":     "légère",
    "faible":     "légère",
    "douce":      "légère",
    "modérée":    "moyenne",
    "moderee":    "moyenne",
    "moyenne":    "moyenne",
    "forte":      "forte",
    "intense":    "forte",
    "très forte": "très forte",
    "tres forte": "très forte",
}

GENRE_MAP = {
    "homme":   "homme",
    "man":     "homme",
    "femme":   "femme",
    "woman":   "femme",
    "mixte":   "mixte",
    "unisex":  "mixte",
    "unisexe": "mixte",
}


# ─── Utilitaires ─────────────────────────────────────────────────────────────
def clean(val):
    return (val or "").strip()


def normalize_intensite(raw):
    return INTENSITE_MAP.get(clean(raw).lower(), "forte")


def normalize_genre(raw):
    return GENRE_MAP.get(clean(raw).lower(), "mixte")


def generate_code_reference(marque, nom, line_no):
    base = slugify(f"{marque}-{nom}")[:25].upper()
    code = f"ESS-{base}-{line_no:03d}"
    suffix = 0
    candidate = code
    while Essence.objects.filter(code_reference=candidate).exists():
        suffix += 1
        candidate = f"{code}-{suffix}"
    return candidate


# ─── Logger ──────────────────────────────────────────────────────────────────
class Logger:
    SEP = "=" * 64

    def __init__(self):
        self.created  = []
        self.skipped  = []
        self.errors   = []

    def created_line(self, msg):
        print(f"  [+] CRÉÉ      — {msg}")
        self.created.append(msg)

    def skipped_line(self, msg):
        print(f"  [~] EXISTANT  — {msg}  →  ignoré (BD intacte)")
        self.skipped.append(msg)

    def error_line(self, msg):
        print(f"  [!] ERREUR    — {msg}")
        self.errors.append(msg)

    def detail(self, msg):
        print(f"         {msg}")

    def summary(self):
        total = len(self.created) + len(self.skipped) + len(self.errors)
        print(f"\n{self.SEP}")
        print(f"  RÉSUMÉ : {total} ligne(s) traitée(s)")
        print(f"   ✅  Créées      : {len(self.created)}")
        print(f"   ⏭   Ignorées    : {len(self.skipped)}")
        print(f"   ❌  Erreurs     : {len(self.errors)}")
        print(self.SEP)
        if self.skipped:
            print("\n  Essences déjà présentes (BD non modifiée) :")
            for s in self.skipped:
                print(f"    • {s}")
        if self.errors:
            print("\n  Erreurs :")
            for e in self.errors:
                print(f"    • {e}")
        print()


# ─── Import principal ─────────────────────────────────────────────────────────
def import_essences(csv_path=CSV_PATH):
    if not os.path.exists(csv_path):
        print(f"❌  Fichier introuvable : {csv_path}")
        sys.exit(1)

    log = Logger()
    tag_cache = {}

    # Détection automatique du délimiteur
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        sample = f.readline()
    delimiter = ";" if sample.count(";") > sample.count(",") else (
        "\t" if "\t" in sample else ","
    )

    print(f"\n{Logger.SEP}")
    print(f"  Import essences  —  {os.path.basename(csv_path)}")
    print(Logger.SEP)

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = list(reader.fieldnames or [])

        direct_found = [c for c in headers if c in DIRECT_FIELDS]
        tag_found    = [c for c in headers if c in TAG_COLUMNS]
        ignored      = [c for c in headers if c not in DIRECT_FIELDS and c not in TAG_COLUMNS]

        print(f"\n  Colonnes ({len(headers)}) :")
        print(f"   Champs directs  : {direct_found}")
        print(f"   Tags            : {tag_found}")
        if ignored:
            print(f"   ⚠  Ignorées     : {ignored}")

        rows = list(reader)
        print(f"\n  {len(rows)} essence(s) à traiter…\n")

        with transaction.atomic():
            for line_no, row in enumerate(rows, start=2):
                row = {k: clean(v) for k, v in row.items() if k is not None}

                marque = row.get("marque", "") or "Sans marque"
                nom    = row.get("nom", "")

                if not nom:
                    log.error_line(f"Ligne {line_no} : nom vide — ignorée")
                    continue

                label = f"{nom} ({marque})"

                # ── Doublon : même marque + même nom → SKIP ───────────────
                if Essence.objects.filter(
                    marque__iexact=marque, nom__iexact=nom
                ).exists():
                    log.skipped_line(label)
                    continue

                try:
                    intensite  = normalize_intensite(row.get("intensite", ""))
                    genre      = normalize_genre(row.get("genre cible", ""))
                    description = (
                        row.get("description longue", "")
                        or row.get("description courte", "")
                    )
                    code_ref = generate_code_reference(marque, nom, line_no)

                    # ── 1. Création de l'essence ──────────────────────────
                    essence = Essence.objects.create(
                        marque         = marque,
                        nom            = nom,
                        code_reference = code_ref,
                        categorie      = "premium",
                        description    = description,
                        description_ia = row.get("description ia", ""),
                        intensite      = intensite,
                        genre_cible    = genre,
                        notes_tete     = row.get("note de tete", ""),
                        notes_coeur    = row.get("note de coeur", ""),
                        notes_fond     = row.get("note de fond", ""),
                        fournisseur    = "",
                        origine_pays   = "",
                        prix_par_ml    = Decimal("0"),
                        actif          = True,
                    )
                    log.created_line(f"Essence : {label}  [{code_ref}]")

                    # ── 2. Lot d'essence : 1000 ml ────────────────────────
                    LotEssence.objects.create(
                        essence               = essence,
                        stock_ml              = Decimal("1000"),
                        stock_precedent_ml    = Decimal("0"),
                        quantite_initiale_ml  = Decimal("1000"),
                        prix_achat_par_ml     = Decimal("0"),
                        reference_fournisseur = f"IMPORT-{code_ref}",
                        actif                 = True,
                    )
                    log.detail("→ Lot 1 000 ml créé")

                    # ── 3. Produits finis : 10 / 15 / 30 ml ──────────────
                    for taille in FORMATS_ML:
                        prix = PRIX_PAR_FORMAT[taille]
                        ProduitFiniEssence.objects.get_or_create(
                            essence   = essence,
                            taille_ml = taille,
                            defaults  = {"prix": prix, "actif": True},
                        )
                        log.detail(f"→ Produit fini {taille:>2} ml — {prix} FCFA")

                    # ── 4. Tags (colonnes non-directes) ───────────────────
                    for col, tag_label in TAG_COLUMNS.items():
                        val = row.get(col, "")
                        if not val:
                            continue
                        if tag_label not in tag_cache:
                            tag_obj, _ = Tag.objects.get_or_create(nom=tag_label)
                            tag_cache[tag_label] = tag_obj
                        TagEssence.objects.create(
                            essence = essence,
                            tag     = tag_cache[tag_label],
                            valeur  = val,
                        )
                    tags_str = ", ".join(
                        f"{TAG_COLUMNS[c]}={row.get(c, '')}"
                        for c in TAG_COLUMNS if row.get(c)
                    )
                    if tags_str:
                        log.detail(f"→ Tags : {tags_str}")

                except Exception as exc:
                    log.error_line(f"Ligne {line_no} ({label}) : {exc}")

    log.summary()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else CSV_PATH
    import_essences(path)
