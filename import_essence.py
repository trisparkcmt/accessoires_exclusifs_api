#!/usr/bin/env python3
import csv
import os
import re
import sys
from decimal import Decimal, InvalidOperation

import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.db import transaction
from catalogue.models import Essence, LotEssence, Tag, TagEssence

CSV_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "catalogue_parfums_accessoires_exclusifs.csv",
)
EXPECTED_COLUMNS = [
    "marque", "nom", "categorie", "code_reference", "description", "description_ia",
    "fournisseur", "origine_pays", "concentration_max", "couleur", "duree", "intensite",
    "genre_cible", "notes_tete", "notes_coeur", "notes_fond", "famille_olfactive",
    "humeurs_compatibles", "occasions", "saisons_compatibles",
    "signes_astrologiques_compatibles", "moments_journee", "prix_par_ml",
]

# Les champs suivants existent directement sur Essence. Les autres sont des tags.
NATIVE_FIELDS = {
    "marque", "nom", "categorie", "code_reference", "description", "description_ia",
    "fournisseur", "origine_pays", "concentration_max", "couleur", "duree", "intensite",
    "genre_cible", "notes_tete", "notes_coeur", "notes_fond", "prix_par_ml",
}
TAG_NAMES = {
    "famille_olfactive": "Famille olfactive",
    "humeurs_compatibles": "Humeur",
    "occasions": "Occasion",
    "saisons_compatibles": "Saison",
    "signes_astrologiques_compatibles": "Signe astrologique",
    "moments_journee": "Moment de la journée",
}


def clean(value):
    return (value or "").strip()


def normalize_category(value):
    value = clean(value).lower()
    if value not in {choice[0] for choice in Essence.CATEGORIE_CHOICES}:
        raise ValueError(f"categorie invalide: {value!r} (valeurs attendues: high, premium, super_premium)")
    return value


def normalize_intensity(value):
    value = clean(value).lower()
    return {
        "légère": "légère", "legere": "légère",
        "modérée": "moyenne", "moderee": "moyenne", "moyenne": "moyenne",
        "forte": "forte",
        "très forte": "très forte", "tres forte": "très forte",
        "": "",
    }.get(value, value)


def normalize_gender(value):
    value = clean(value).lower()
    return {
        "h": "homme", "f": "femme",
        "féminin": "femme", "feminin": "femme", "femme": "femme",
        "masculin": "homme", "homme": "homme",
        "mixte": "mixte", "unisexe": "mixte",
    }.get(value, value)


def decimal_value(value, field_name, line_number):
    raw_value = clean(value).replace(",", ".")
    if not raw_value:
        return None if field_name == "concentration_max" else Decimal("0")
    numbers = re.findall(r"\d+(?:\.\d+)?", raw_value)
    if not numbers:
        raise ValueError(f"Ligne {line_number}: {field_name} invalide: {value!r}")
    # Pour une plage (ex: 20-30 %), concentration_max conserve la borne haute.
    value = numbers[-1] if field_name == "concentration_max" else numbers[0]
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Ligne {line_number}: {field_name} invalide: {value!r}") from exc


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as csv_file:
        first_line = csv_file.readline()
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
        csv_file.seek(0)
        reader = csv.reader(csv_file, delimiter=delimiter)
        header = next(reader, None)
        if header != EXPECTED_COLUMNS:
            raise ValueError(
                "En-têtes CSV invalides.\n"
                f"Attendu: {EXPECTED_COLUMNS}\n"
                f"Reçu:   {header}"
            )

        for line_number, row in enumerate(reader, start=2):
            if not any(clean(value) for value in row):
                continue
            if len(row) != len(EXPECTED_COLUMNS):
                raise ValueError(
                    f"Ligne {line_number} invalide: {len(row)} colonnes au lieu de "
                    f"{len(EXPECTED_COLUMNS)}. Les valeurs contenant des virgules "
                    "doivent être entourées de guillemets."
                )
            yield line_number, dict(zip(EXPECTED_COLUMNS, map(clean, row)))


def tag_for(field_name):
    tag, _ = Tag.objects.get_or_create(nom=TAG_NAMES[field_name])
    return tag


def import_essences(path=CSV_PATH):
    rows = list(read_rows(path))
    created_count = 0
    updated_count = 0
    lots_created_count = 0

    with transaction.atomic():
        for line_number, row in rows:
            nom = row["nom"]
            code_reference = row["code_reference"]
            if not nom or not code_reference:
                raise ValueError(f"Ligne {line_number}: nom et code_reference sont obligatoires.")

            defaults = {
                "marque": row["marque"],
                "nom": nom,
                "categorie": normalize_category(row["categorie"]),
                "description": row["description"],
                "description_ia": row["description_ia"],
                "fournisseur": row["fournisseur"],
                "origine_pays": row["origine_pays"],
                "concentration_max": decimal_value(row["concentration_max"], "concentration_max", line_number),
                "couleur": row["couleur"],
                "duree": row["duree"],
                "intensite": normalize_intensity(row["intensite"]),
                "genre_cible": normalize_gender(row["genre_cible"]),
                "notes_tete": row["notes_tete"],
                "notes_coeur": row["notes_coeur"],
                "notes_fond": row["notes_fond"],
                "prix_par_ml": decimal_value(row["prix_par_ml"], "prix_par_ml", line_number),
            }
            essence = Essence.objects.filter(code_reference=code_reference).first()
            if essence:
                for field, value in defaults.items():
                    setattr(essence, field, value)
                essence.actif = True
                essence.save()
                updated_count += 1
            else:
                essence = Essence.objects.create(code_reference=code_reference, **defaults)
                created_count += 1

            # Lot initial idempotent : une réexécution ne crée pas de doublon.
            lot_reference = f"IMPORT-INITIAL-{code_reference}"
            _, lot_created = LotEssence.objects.get_or_create(
                essence=essence,
                reference_fournisseur=lot_reference,
                defaults={
                    "stock_ml": Decimal("1000"),
                    "stock_precedent_ml": Decimal("0"),
                    "quantite_initiale_ml": Decimal("1000"),
                    "prix_achat_par_ml": Decimal("0"),
                    "actif": True,
                },
            )
            if lot_created:
                lots_created_count += 1

            TagEssence.objects.filter(essence=essence).delete()
            for field_name, tag_name in TAG_NAMES.items():
                value = row[field_name]
                if value:
                    TagEssence.objects.create(
                        essence=essence,
                        tag=tag_for(field_name),
                        valeur=value,
                    )

    print(
        f"Import terminé : {created_count} créées, {updated_count} mises à jour, "
        f"{lots_created_count} lots initiaux créés (1000 ml)."
    )


if __name__ == "__main__":
    import_essences()
