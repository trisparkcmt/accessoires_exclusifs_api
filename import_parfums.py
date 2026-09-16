#!/usr/bin/env python3
import os
import sys
import django
import csv
import unicodedata
from decimal import Decimal

# Configuration de l'environnement Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from catalogue.models import Parfum, CategorieParfum, Tag, TagParfum
from django.utils.text import slugify

User = get_user_model()

def create_or_update_superuser():
    email = "handougregoire@gmail.com"
    password = "1234"
    print(f"--- Configuration du Superuser ({email}) ---")
    user, created = User.objects.get_or_create(email=email)
    user.username = email.split('@')[0]
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(password)
    user.save()
    if created:
        print(f"[+] Superutilisateur créé avec succès : {email}")
    else:
        print(f"[*] Superutilisateur mis à jour avec succès : {email}")

def get_or_create_categories():
    """
    Récupère ou crée les catégories 'MARQUE' et 'DUPE'
    en gérant les correspondances insensibles à la casse.
    """
    categories = {}
    for cat_name in ["MARQUE", "DUPE", "PARFUMS DE CREATEUR"]:
        cat = CategorieParfum.objects.filter(nom__iexact=cat_name).first()
        if not cat:
            cat = CategorieParfum.objects.create(
                nom=cat_name,
                description=f"Catégorie des parfums {cat_name.lower()}s"
            )
            print(f"[+] Catégorie créée : {cat.nom}")
        else:
            print(f"[*] Catégorie existante trouvée : {cat.nom}")
        categories[cat_name] = cat
    return categories

def import_parfums():
    """Importe le catalogue CSV, affecte l'image principale et conserve les attributs en tags (y compris Type/concentration)."""
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalogue_parfums_complet.csv")
    colonnes_en_tags = [
        "Type / concentration", "Famille olfactive", "Durabilité", "Sillage", "Style",
        "Humeur compatible", "Saisons compatibles", "Climat conseillé",
        "Occasions recommandées", "Niveau de certitude",
        "Parfum original dont il s'inspire lorsqu'il est identifiable",
    ]
    noms_tags = {
        "Type / concentration": "Concentration",
        "Humeur compatible": "Humeur",
        "Saisons compatibles": "Saison",
        "Occasions recommandées": "Occasion",
        "Parfum original dont il s'inspire lorsqu'il est identifiable": "Parfum original",
    }

    # Les alias permettent de lire l'ancien CSV pendant la transition des en-têtes.
    aliases = {
        "nom": ["Nom du produit"],
        "prix": ["Prix (FCFA)"],
        "prix_affiche": ["Prix affiché"],
        "marque": ["Marque / maison"],
        "statut": ["Statut", "Statut / positionnement"],
        "concentration": ["Type / concentration", "Type (Concentration)", "Type", "Concentration"],
        "genre": ["Genre"],
        "famille": ["Famille olfactive"],
        "notes_tete": ["Notes de tête"],
        "notes_coeur": ["Notes de cœur"],
        "notes_fond": ["Notes de fond"],
        "duree_annoncee": ["Durabilité", "Durabilité annoncée"],
        "sillage": ["Sillage"],
        "intensite": ["Intensité"],
        "style": ["Style"],
        "humeur": ["Humeur compatible"],
        "saisons": ["Saisons compatibles"],
        "climat": ["Climat conseillé"],
        "occasions": ["Occasions recommandées"],
        "original": [
            "Parfum original dont il s'inspire lorsqu'il est identifiable",
            "Parfum original dont il s’inspire lorsqu’il est identifiable",
        ],
        "description_courte": ["Description courte"],
        "description_longue": ["Description longue"],
        "description_ia": ["Description IA"],
        "image": ["Images", "Image", "image_url", "image", "Image principale"],
        "image_supp_1": [
            "Images secondaire 1",
            "Image secondaire 1",
            "Images secondaires 1",
            "Image secondaire 1",
            "image_supp_1",
            "image_secondaire_1",
            "Image Supp 1",
            "Images Supp 1",
        ],
        "image_supp_2": [
            "Images secondaire 2",
            "Image secondaire 2",
            "Images secondaires 2",
            "Image secondaire 2",
            "image_supp_2",
            "image_secondaire_2",
            "Image Supp 2",
            "Images Supp 2",
        ],
        "image_supp_3": [
            "Images secondaire 3",
            "Image secondaire 3",
            "Images secondaires 3",
            "Image secondaire 3",
            "image_supp_3",
            "image_secondaire_3",
            "Image Supp 3",
            "Images Supp 3",
        ],
        "image_supp_4": [
            "Images secondaire 4",
            "Image secondaire 4",
            "Images secondaires 4",
            "Image secondaire 4",
            "image_supp_4",
            "image_secondaire_4",
            "Image Supp 4",
            "Images Supp 4",
        ],
    }

    def valeur(row, cle):
        for colonne in aliases.get(cle, [cle]):
            if colonne in row:
                return (row.get(colonne) or "").strip()
        row_lower = {k.strip().lower(): v for k, v in row.items() if k}
        for colonne in aliases.get(cle, [cle]):
            if colonne.strip().lower() in row_lower:
                return (row_lower.get(colonne.strip().lower()) or "").strip()
        return ""

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    img_dir = os.path.join(backend_dir, "images_parfum")
    dir_files = os.listdir(img_dir) if os.path.exists(img_dir) else []
    file_map = {}
    import re
    for f in dir_files:
        file_map[f.lower()] = f
        clean_stem = re.sub(r'[\._]NIGHT', '', os.path.splitext(f)[0], flags=re.IGNORECASE).lower()
        file_map[clean_stem] = f

    def attacher_image(parfum, field_name, image_val):
        if not image_val:
            return False
        base = os.path.basename(image_val).strip()
        if not base:
            return False

        img_full_path = None
        candidates = [
            os.path.join(backend_dir, image_val),
            os.path.join(img_dir, base),
            os.path.join(getattr(settings, "MEDIA_ROOT", backend_dir), image_val),
        ]
        alt1 = base.replace('_NIGHT', '.NIGHT').replace('_night', '.NIGHT')
        alt2 = base.replace('.NIGHT', '_NIGHT').replace('.night', '_NIGHT')
        candidates.extend([os.path.join(img_dir, alt1), os.path.join(img_dir, alt2)])

        img_full_path = next((p for p in candidates if os.path.exists(p)), None)

        if not img_full_path and base.lower() in file_map:
            img_full_path = os.path.join(img_dir, file_map[base.lower()])

        if not img_full_path:
            stem = re.sub(r'[\._]NIGHT', '', os.path.splitext(base)[0], flags=re.IGNORECASE).lower()
            if stem in file_map:
                img_full_path = os.path.join(img_dir, file_map[stem])

        if img_full_path and os.path.exists(img_full_path):
            from django.core.files import File
            field = getattr(parfum, field_name)
            with open(img_full_path, "rb") as img_file:
                filename = os.path.basename(img_full_path)
                field.save(filename, File(img_file), save=False)
            return True
        return False

    def prix_depuis_valeur(prix_brut):
        if not prix_brut:
            return None
        import re
        prix_clean = re.sub(r'[^\d.]', '', prix_brut.replace(",", ".").replace(" ", "").replace("FCFA", "").strip())
        try:
            return Decimal(prix_clean) if prix_clean else None
        except Exception:
            return None

    def genre_valide(genre):
        return {"homme": "homme", "femme": "femme", "unisexe": "mixte", "mixte": "mixte"}.get(
            genre.lower(), "mixte"
        )

    def intensite_valide(intensite):
        intensite_normalisee = intensite.lower().strip()
        return {
            "légère": "légère",
            "legere": "légère",
            "moyenne": "moyenne",
            "forte": "forte",
            "très forte": "très forte",
            "tres forte": "très forte",
        }.get(intensite_normalisee, "")

    def categorie_pour_statut(statut):
        statut_normalise = unicodedata.normalize("NFKD", statut.lower()).encode("ascii", "ignore").decode()
        if "dupe" in statut_normalise:
            nom = "DUPE"
        elif "marque" in statut_normalise:
            nom = "PARFUMS DE MARQUE"
        elif "createur" in statut_normalise:
            nom = "PARFUMS DE CREATEUR"
        else:
            # Les créations et les inspirations sont regroupées dans la catégorie Inspiration.
            nom = "INSPIRATION"

        categorie = CategorieParfum.objects.filter(nom__iexact=nom).first()
        if categorie:
            return categorie
        categorie, _ = CategorieParfum.objects.get_or_create(
            nom=nom,
            defaults={"description": f"Parfums : {nom}"},
        )
        return categorie

    def tag_pour_colonne(colonne):
        tag, _ = Tag.objects.get_or_create(nom=noms_tags.get(colonne, colonne))
        return tag

    print(f"\n--- Importation du catalogue {os.path.basename(csv_path)} ---")
    imported_skus = []
    created_count = 0
    updated_count = 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        rows = csv.DictReader(csv_file, delimiter="\t")
        for index, row in enumerate(rows, start=1):
            nom = valeur(row, "nom")
            if not nom:
                continue
            sku = f"PARFUM-CSV-{index:03d}"
            imported_skus.append(sku)
            statut = valeur(row, "statut")
            prix = prix_depuis_valeur(valeur(row, "prix"))
            prix_affiche = prix_depuis_valeur(valeur(row, "prix_affiche"))
            prix = prix or prix_affiche
            if not prix or prix <= Decimal("0"):
                prix = Decimal("18000.00")

            defaults = {
                "nom": nom,
                "marque": valeur(row, "marque"),
                "categorie": categorie_pour_statut(statut),
                "genre_cible": genre_valide(valeur(row, "genre")),
                "duree": valeur(row, "concentration"),
                "contenance_ml": 100,
                "intensite": intensite_valide(valeur(row, "intensite")),
                "prix_unitaire": prix,
                "prix_promotionnel": None,
                "notes_tete": valeur(row, "notes_tete"),
                "notes_coeur": valeur(row, "notes_coeur"),
                "notes_fond": valeur(row, "notes_fond"),
                "description_courte": valeur(row, "description_courte"),
                "description_longue": valeur(row, "description_longue"),
                "description_ia": valeur(row, "description_ia"),
                "est_nouveau": False,
                "est_bestseller": False,
                "stock_quantite": 20,
                "actif": True,
            }
            marque_csv = valeur(row, "marque")

            # 1. Chercher d'abord par nom + marque (priorité principale)
            parfum = None
            if marque_csv:
                parfum = Parfum.objects.filter(
                    nom__iexact=nom, marque__iexact=marque_csv
                ).first()

            # 2. Fallback : chercher par nom uniquement (si pas de marque dans le CSV)
            if not parfum and not marque_csv:
                parfum = Parfum.objects.filter(nom__iexact=nom).first()

            # 3. Dernier recours : chercher par SKU (réimport technique)
            if not parfum:
                parfum = Parfum.objects.filter(reference_sku=sku).first()

            def liberer_sku(target_sku, target_parfum=None):
                qs = Parfum.objects.filter(reference_sku=target_sku)
                if target_parfum and target_parfum.pk:
                    qs = qs.exclude(pk=target_parfum.pk)
                for c in qs:
                    c.reference_sku = None
                    c.save()

            if parfum:
                # Vérifier si le parfum existant possède déjà des images
                a_des_images = bool(parfum.image_principale)
                if not a_des_images:
                    # Vérifier aussi les images supplémentaires
                    for i in range(1, 5):
                        if getattr(parfum, f"image_supp_{i}", None):
                            a_des_images = True
                            break

                if a_des_images:
                    # Le parfum existant a des images → on le garde tel quel, on ne remplace pas
                    # On met quand même à jour le SKU et les données textuelles/prix, mais PAS les images
                    operation = "="
                    for key, val in defaults.items():
                        setattr(parfum, key, val)
                    if parfum.stock_quantite <= 0:
                        parfum.stock_quantite = 20
                    parfum.actif = True
                    liberer_sku(sku, parfum)
                    parfum.reference_sku = sku
                    parfum.save()
                    updated_count += 1
                    print(f"[{operation}] {nom} (images conservées, données mises à jour)")
                    # Mise à jour des tags uniquement
                    TagParfum.objects.filter(parfum=parfum).delete()
                    for colonne in colonnes_en_tags:
                        cle = {
                            "Type / concentration": "concentration",
                            "Famille olfactive": "famille",
                            "Durabilité": "duree_annoncee",
                            "Sillage": "sillage",
                            "Style": "style",
                            "Humeur compatible": "humeur",
                            "Saisons compatibles": "saisons",
                            "Climat conseillé": "climat",
                            "Occasions recommandées": "occasions",
                            "Niveau de certitude": "__ignore__",
                            "Parfum original dont il s'inspire lorsqu'il est identifiable": "original",
                        }[colonne]
                        if cle == "__ignore__":
                            continue
                        tag_valeur = valeur(row, cle)
                        if tag_valeur:
                            TagParfum.objects.create(
                                parfum=parfum,
                                tag=tag_pour_colonne(colonne),
                                valeur=tag_valeur,
                            )
                    continue  # Passer à la ligne suivante du CSV

                else:
                    # Le parfum existant n'a pas d'images → mise à jour complète
                    operation = "*"
                    for key, val in defaults.items():
                        setattr(parfum, key, val)
                    if parfum.stock_quantite <= 0:
                        parfum.stock_quantite = 20
                    parfum.actif = True
                    liberer_sku(sku, parfum)
                    parfum.reference_sku = sku
                    parfum.save()
                    updated_count += 1
            else:
                operation = "+"
                liberer_sku(sku, None)
                parfum = Parfum.objects.create(reference_sku=sku, **defaults)
                created_count += 1

            # Gestion des images principales et secondaires (1 à 4)
            img_modifiee = False
            image_val = valeur(row, "image")
            if attacher_image(parfum, "image_principale", image_val):
                img_modifiee = True

            for i in range(1, 5):
                img_supp_val = valeur(row, f"image_supp_{i}")
                if attacher_image(parfum, f"image_supp_{i}", img_supp_val):
                    img_modifiee = True

            if img_modifiee:
                parfum.save()

            TagParfum.objects.filter(parfum=parfum).delete()
            for colonne in colonnes_en_tags:
                cle = {
                    "Type / concentration": "concentration",
                    "Famille olfactive": "famille",
                    "Durabilité": "duree_annoncee",
                    "Sillage": "sillage",
                    "Style": "style",
                    "Humeur compatible": "humeur",
                    "Saisons compatibles": "saisons",
                    "Climat conseillé": "climat",
                    "Occasions recommandées": "occasions",
                    "Niveau de certitude": "__ignore__",
                    "Parfum original dont il s'inspire lorsqu'il est identifiable": "original",
                }[colonne]
                if cle == "__ignore__":
                    continue
                tag_valeur = valeur(row, cle)
                if tag_valeur:
                    TagParfum.objects.create(
                        parfum=parfum,
                        tag=tag_pour_colonne(colonne),
                        valeur=tag_valeur,
                    )
            print(f"[{operation}] {nom}")

    # Remplace le catalogue visible sans supprimer les produits liés à l'historique des commandes.
    Parfum.objects.exclude(reference_sku__in=imported_skus).update(actif=False)
    print(f"\nImportation terminée : {created_count} créés, {updated_count} mis à jour.")
    return

    # Ancien catalogue codé en dur conservé temporairement ci-dessous pour référence historique.
    categories = get_or_create_categories()
    cat_marque = categories["MARQUE"]
    cat_dupe = categories["DUPE"]

    parfums_data = [
        # --- PARFUMS 4 À 18 ---
        {
            "sku": "PARFUM-PC-SHAHAF-004",
            "nom": "Shahaf : Oud Tonka",
            "marque": "Paris Corner",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("50000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Fève Tonka, Amande amère, Cannelle",
            "notes_coeur": "Oud, Tabac blond, Rose",
            "notes_fond": "Vanille, Benjoin, Bois de santal, Ambre",
            "description_courte": "Un accord gourmand et envoûtant mêlant la douceur de la fève tonka à la profondeur du oud.",
            "description_longue": "Shahaf Oud Tonka est un parfum chaleureux et sophistiqué. La gourmandise de l'amande et de la tonka s'équilibre parfaitement avec la puissance sombre du oud, créant un parfum à la fois réconfortant et luxueux.",
            "description_ia": "Une symphonie olfactive suave et captivante où la fève tonka veloutée s'enlace dans un oud fumé et vanillé. Une fragrance de haute tenue pensée pour marquer les esprits lors des soirées froides.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-FW-INVICTO-005",
            "nom": "INVICTO ABSOLU",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": Decimal("15000.00"),
            "notes_tete": "Citron vert, Poivre rose",
            "notes_coeur": "Encens, Lavande",
            "notes_fond": "Fève Tonka, Amber, Vanille",
            "description_courte": "Un parfum frais, intense et boisé-sucré, taillé pour le dynamisme et la victoire.",
            "description_longue": "Invicto Absolu oppose un départ piquant et citronné à un cœur d'encens et de vanille fumée. Un parfum moderne, viril et énergique qui offre une excellente tenue.",
            "description_ia": "L'essence même de la puissance et du triomphe. Invicto Absolu combine l'éclat des agrumes au charisme boisé de l'encens et de la vanille pour vous accompagner avec assurance tout au long de la journée.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-MA-ROSE-006",
            "nom": "Le secret de séduction de la rose",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("17000.00"),
            "prix_promotionnel": Decimal("12000.00"),
            "notes_tete": "Rose de mai, Poivre du Sichuan, Curcuma",
            "notes_coeur": "Rose de Bulgarie, Rose de Turquie",
            "notes_fond": "Patchouli, Fève tonka",
            "description_courte": "Un bouquet de roses sauvages rehaussé d'épices et d'un fond terreux chic.",
            "description_longue": "Ce parfum rend hommage à la reine des fleurs. Il explore la rose sous toutes ses facettes : épicée en ouverture, suave et florale au cœur, puis enveloppée de patchouli sensuel en fond.",
            "description_ia": "Un élixir d'amour pur. Ce parfum dévoile un jardin de roses majestueuses piquées d'épices fines, créant une aura de féminité irrésistible et raffinée.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-CH-BLEU-007",
            "nom": "Bleu de Chanel",
            "marque": "Chanel",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 150,
            "intensite": "très forte",
            "prix_unitaire": Decimal("155000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pamplemousse, Citron, Menthe, Poivre rose",
            "notes_coeur": "Gingembre, Noix de muscade, Jasmin, Iso E Super",
            "notes_fond": "Encens, Vétiver, Cèdre, Bois de santal, Patchouli, Labdanum",
            "description_courte": "L'incarnation de la liberté masculine dans un aromatique-boisé intemporel.",
            "description_longue": "Bleu de Chanel Eau de Parfum est une composition élégante et pure. Il associe la fraîcheur fusante des agrumes à la profondeur boisée du cèdre et du santal de Nouvelle-Calédonie, soulignée par un accent d'encens mystérieux.",
            "description_ia": "Le chef-d'œuvre incontournable de la parfumerie moderne. Bleu de Chanel est l'expression d'un accomplissement personnel, offrant un sillage captivant, sophistiqué et universellement admiré.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-LA-RAGHBA-008",
            "nom": "Raghba pour Homme",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("22000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Citron, Verveine",
            "notes_coeur": "Feuilles de violette, Iris",
            "notes_fond": "Ambre gris, Bois de santal, Cèdre, Cuir",
            "description_courte": "Une fragrance verte, fraîche et boisée d'une élégance classique.",
            "description_longue": "Raghba pour Homme s'éloigne de la version orientale sucrée pour proposer un profil aromatique, herbacé et très propre. Idéal pour un usage professionnel et quotidien.",
            "description_ia": "La fraîcheur d'une campagne irlandaise après la pluie. Raghba pour Homme vous offre un souffle vert et boisé énergisant qui projette propreté et prestance toute la journée.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-LA-KHAMRAH-009",
            "nom": "KHAMRAH",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Cannelle, Noix de muscade, Bergamote",
            "notes_coeur": "Dattes, Praliné, Tubéreuse, Mahonial",
            "notes_fond": "Vanille, Fève tonka, Amberwood, Myrrhe, Benjoin",
            "description_courte": "Le Best-Seller mondial : un gourmand oriental liquoreux aux notes de cannelle, dattes et praliné.",
            "description_longue": "Khamrah est devenu un phénomène mondial grâce à sa richesse olfactive. Il s'ouvre sur des épices chaudes avant de dévoiler un cœur ultra-gourmand de dattes confites et de praliné, posé sur une vanille ambrée somptueuse.",
            "description_ia": "Une véritable addiction en flacon. Khamrah est un chef-d'œuvre sucré et épicé qui drape son porteur d'une chaleur gourmande hypnotique. Tenue et sillage monstrueux garantis.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-LE-CUIRAMBRE-010",
            "nom": "Cuir Ambre",
            "marque": "Leonard Paris",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("47000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Cardamome, Rhum",
            "notes_coeur": "Cuir, Patchouli, Cannelle",
            "notes_fond": "Ambre, Vanille, Benjoin",
            "description_courte": "Un cuir suave et chaleureux enrobé d'ambre résineux et de vanille.",
            "description_longue": "Cuir Ambre de Léonard explore le côté le plus noble du cuir, adouci par la rondeur ambrée et liquoreuse. C'est un parfum de caractère raffiné, idéal pour affirmer sa présence.",
            "description_ia": "Un hommage au travail du cuir et de la résine noble. Cuir Ambre dégage une aura chic, sombre et enveloppante pour ceux qui apprécient les parfums à forte personnalité.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-LA-HAYAATIROSE-011",
            "nom": "Hayaati Rose",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Chocolat noir, Vert de feuille",
            "notes_coeur": "Rose, Fleur d'oranger",
            "notes_fond": "Vanille, Musc, Bois de cèdre",
            "description_courte": "Une rose gourmande modernisée par des touches chocolatées et fruitées.",
            "description_longue": "Hayaati Rose revisite le parfum floral féminin en lui ajoutant une nuance chocolatée et sucrée subtile qui adoucit la rose classique.",
            "description_ia": "Doux, romantique et délicieusement gourmand. Hayaati Rose enlace la fraîcheur de la rose dans une caresse sucrée et vanillée pour un quotidien plein de douceur.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-MA-KISMET-012",
            "nom": "Kismet For Men",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("40000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Violette, Coriandre, Bergamote",
            "notes_coeur": "Rose, Poivre noir, Muguet",
            "notes_fond": "Patchouli, Ambre gris, Vanille Bourbon",
            "description_courte": "L'élégance masculine absolue : un accord boisé, poivré et vanillé très chic.",
            "description_longue": "Kismet For Men est une réplique saisissante du fameux Tuxedo. Il allie la noblesse du patchouli à la chaleur des épices et de la vanille, parfait pour les tenues de soirée et les costumes.",
            "description_ia": "Le parfum du gentleman parfait. Kismet For Men exhale un magnétisme irrésistible où les épices chaudes rencontrent la sophistication du patchouli et de l'ambre.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-PM-ROSEOUD-013",
            "nom": "Rose Édition Oud",
            "marque": "Pascal Morabito",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("31000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Framboise, Safran",
            "notes_coeur": "Rose, Géranium",
            "notes_fond": "Oud, Patchouli, Ambre, Cuir",
            "description_courte": "L'accord oriental mythique : une rose opulente mariée à un oud ténébreux.",
            "description_longue": "Pascal Morabito propose ici une interprétation accessible et très réussie du duo Rose-Oud. Le départ fruité s'efface vite devant un cœur majestueux de rose posé sur un fond oriental boisé et ambré.",
            "description_ia": "Une création dramatique et poétique où la douceur suave de la rose rencontre l'intensité mystérieuse du bois d'agar. Une signature olfactive à la hauteur du savoir-faire français.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-TF-OUDWOOD-014",
            "nom": "Oud Wood",
            "marque": "Tom Ford",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 50,
            "intensite": "forte",
            "prix_unitaire": Decimal("75000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bois de rose de Rio, Cardamome, Poivre de Sichuan",
            "notes_coeur": "Oud (Bois d'agar), Bois de santal, Vétiver",
            "notes_fond": "Fève tonka, Vanille, Ambre",
            "description_courte": "L'icône du luxe boisé : un oud fumé, épicé, exotique et totalement envoûtant.",
            "description_longue": "Oud Wood est l'un des parfums les plus célèbres de Tom Ford. Il met en scène un bois d'agar boisé et rare mélangé à la cardamome et au bois de santal pour un rendu d'une élégance rare et distinctive.",
            "description_ia": "Le luxe à son paroxysme. Oud Wood est un chef-d'œuvre de sobriété et de puissance qui habille la peau d'un voile boisé, épicé et sensuel absolument inégalé.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-ZA-REDTEMPT-015",
            "nom": "Red Temptation",
            "marque": "Zara",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 80,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Safran, Orange amère (Bigarade), Coriandre",
            "notes_coeur": "Praliné, Jasmin",
            "notes_fond": "Ambre boisé, Mousse de chêne, Musc",
            "description_courte": "Le dupe ultime de Baccarat Rouge 540 aux facettes sucrées, ambrées et safranées.",
            "description_longue": "Red Temptation diffuse une aura florale et boisée sophistiquée. Les notes de safran et de praliné créent cet effet 'cristallin sucré' et aérien emblématique.",
            "description_ia": "Moderne et irrésistiblement chic, Red Temptation capture la magie des parfums de niche à un prix abordable. Un sillage ambré et safrané qui attire immédiatement les compliments.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-ZA-TENDERAMBER-016",
            "nom": "Tender Amber",
            "marque": "Zara",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Fruits exotiques, Cassis",
            "notes_coeur": "Rose, Tubéreuse",
            "notes_fond": "Ambre, Bois de santal",
            "description_courte": "Une explosion de fruits exotiques sucrés posés sur un fond ambré chaleureux.",
            "description_longue": "Créé par Gaël Montero, Tender Amber combine l'acidité pétillante des fruits de la passion et du cassis avec un fond ambré ultra-tenace.",
            "description_ia": "Un cocktail fruité et solaire captivant. Tender Amber offre une tenue exceptionnelle et un sillage joyeux et attrayant, parfait pour toutes les saisons.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-HB-BOSSNIGHT-017",
            "nom": "Boss Bottled Night",
            "marque": "Hugo Boss",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum / Eau de Toilette Intense",
            "contenance_ml": 200,
            "intensite": "forte",
            "prix_unitaire": Decimal("107000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Lavande, Bouleau",
            "notes_coeur": "Violette, Cardamome, Jasmin",
            "notes_fond": "Notes boisées, Sandalwood, Musc",
            "description_courte": "L'arme de séduction nocturne : un boisé aromatique intense aux notes de bouleau et violette.",
            "description_longue": "Conçu pour le séducteur moderne, Boss Bottled Night apporte une dimension plus sombre et mystérieuse à la gamme Boss Bottled grâce à ses accords boisés profonds et floraux masculins.",
            "description_ia": "L'élégance de la nuit capturée dans un flacon. Boss Bottled Night assure une prestance ténébreuse et raffinée qui attire l'attention en soirée.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-LA-PROUDOFYOU-018",
            "nom": "Proud Of You",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20900.00"),
            "prix_promotionnel": None,
            "notes_tete": "Cardamome, Poivre rose, Feuilles de violette, Menthe",
            "notes_coeur": "Sauge, Melon, Ananas",
            "notes_fond": "Vanille, Châtaigne enrobée de sucre, Cèdre, Amberwood",
            "description_courte": "Un ambré gourmand et épicé dominé par des notes chaudes de vanille et de châtaigne.",
            "description_longue": "Ce parfum capte la masculinité moderne, élégante et chaleureuse. L'ouverture épicée glisse vers un cœur sucré de châtaigne et de vanille très réconfortant.",
            "description_ia": "Une caresse olfactive chaleureuse et irrésistible. Proud Of You est le parfum gourmand masculin par excellence pour séduire avec douceur et confiance.",
            "est_nouveau": False,
            "est_bestseller": False
        },

        # --- PARFUMS 19 À 31 ---
        {
            "sku": "PARFUM-MN-IRISPATCH-019",
            "nom": "Iris Patchouli",
            "marque": "Maison de Niche / Collection Privée",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("60000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Iris, Bergamote",
            "notes_coeur": "Patchouli, Violette",
            "notes_fond": "Ambre, Musc blanc, Bois de santal",
            "description_courte": "Une alliance noble entre l'élégance poudrée de l'iris et la terre cuite du patchouli.",
            "description_longue": "Ce parfum marie la délicatesse poudrée et aristocratique de l'iris à la profondeur terreuse et mystérieuse du patchouli. Un équilibre parfait entre douceur et caractère.",
            "description_ia": "Iris Patchouli offre une expérience olfactive raffinée et intemporelle. Sa signature poudrée-boisée habille la peau d'un voile de mystère et d'élégance distinguée.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-FW-FIEROBLUE-020",
            "nom": "Fiero Blue Man",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("21000.00"),
            "prix_promotionnel": Decimal("16000.00"),
            "notes_tete": "Pamplemousse, Poivre, Citron",
            "notes_coeur": "Lavande, Gingembre, Menthe",
            "notes_fond": "Cèdre, Vétiver, Ambroxan",
            "description_courte": "Un parfum masculin bleu, ultra-frais, aromatique et boisé.",
            "description_longue": "Fiero Blue Man propose un envol d'agrumes vibrants et d'épices fraîches se fondant dans un cœur marin et aromatique, posé sur un fond boisé très masculin.",
            "description_ia": "L'incarnation de la fraîcheur et du dynamisme au masculin. Fiero Blue Man vous procure une sensation de propreté et d'énergie instantanée toute la journée.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-GEO-HOMMEAUTH-021",
            "nom": "Homme authentique : Geovany",
            "marque": "Geovany / Collection Générique",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Cardamome",
            "notes_coeur": "Sauge, Iris",
            "notes_fond": "Cuir, Cèdre, Fève Tonka",
            "description_courte": "Un boisé cuiré moderne pensé pour l'homme affirmé au quotidien.",
            "description_longue": "Développé autour d'accords aromatiques et cuirés, ce parfum combine fraîcheur de tête et chaleur en fond pour offrir une présence rassurante et virile.",
            "description_ia": "Simple, direct et séduisant. Homme Authentique Geovany accompagne le quotidien de l'homme moderne avec une prestance équilibrée et accessible.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-LA-HAMDAAN-022",
            "nom": "Hamdaan",
            "marque": "Lattafa / Ard Al Zaafaran",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Safran, Noix de muscade, Épices",
            "notes_coeur": "Oud, Bois de rose",
            "notes_fond": "Ambre, Vanille, Sandalwood",
            "description_courte": "Une composition orientale royale riche en épices et bois précieux.",
            "description_longue": "Hamdaan s'ouvre sur une explosion safranée et épicée qui glisse rapidement vers des notes chaudes d'oud adouci par la vanille et l'ambre résineux.",
            "description_ia": "Riche et chaleureux, Hamdaan capture l'essence du luxe oriental avec son mélange captivant de bois sombres et d'épices dorées.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-FW-UNIQUEEXPL-023",
            "nom": "L'UNIQUE EXPLORER",
            "marque": "Fragrance World / Pendora Scents",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("22000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Poivre rose, Sauge",
            "notes_coeur": "Cuir, Vétiver de Haïti",
            "notes_fond": "Patchouli, Ambroxan, Cacao",
            "description_courte": "Un boisé aromatique frais et cuiré, taillé pour l'aventure.",
            "description_longue": "L'Unique Explorer combine l'éclat de la bergamote d'Italie avec la profondeur du vétiver et une touche de cuir souple. Idéal pour un sillage professionnel et polyvalent.",
            "description_ia": "Un appel au voyage et au dépassement de soi. L'Unique Explorer offre une fraîcheur élégante et boisée qui marque les esprits en toute sobriété.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-DU-NOBLEBLACK-024",
            "nom": "Noble Black",
            "marque": "Dumont / Collection Générique",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("15000.00"),
            "prix_promotionnel": Decimal("10000.00"),
            "notes_tete": "Citron, Menthe, Lavande",
            "notes_coeur": "Bois de cèdre, Epices fines",
            "notes_fond": "Musc noir, Ambre, Tabac",
            "description_courte": "Un boisé aromatique sombre et viril à prix accessible.",
            "description_longue": "Noble Black oppose des notes fraîches en ouverture à un fond sombre de musc et de tabac, créant un parfum mystérieux pour les sorties du soir.",
            "description_ia": "Mystérieux et élégant, Noble Black vous dote d'un charme ténébreux et boisé pour sublimer vos soirées.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-MO-OUDMINUIT-025",
            "nom": "Oud de minuit",
            "marque": "Maison Orientale",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Oregano, Piment, Bergamote",
            "notes_coeur": "Encens, Amber, Opoponax",
            "notes_fond": "Oud, Cuir, Patchouli, Sandalwood",
            "description_courte": "Un oud fumé, ambré et épicé d'une grande intensité nocturne.",
            "description_longue": "Oud de Minuit est une fragrance complexe et chaleureuse. L'encens et les rituels de résines s'associent au cuir et au bois d'agar pour créer un sillage envoutant et opulent.",
            "description_ia": "La magie de la nuit orientale dans un flacon. Oud de Minuit séduit par son caractère résineux, fumé et profondément boisé.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-FW-SCANDALE-026",
            "nom": "Scandale",
            "marque": "Fragrance World / Collection Générique",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("35000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Orange sanguine, Mandarine",
            "notes_coeur": "Miel, Gardénia, Fleur d'oranger, Jasmin, Pêche",
            "notes_fond": "Cire d'abeille, Caramel, Patchouli, Réglisse",
            "description_courte": "Un gourmand floral explosif gorgé de miel, de caramel et de fleurs blanches.",
            "description_longue": "Scandale est une ode à la gourmandise audacieuse. Le cœur de miel fondu et de gardenia s'épanouit sur un fond chaud de patchouli et de caramel pour un résultat ultra-sensuel.",
            "description_ia": "Insolent, sucré et irrésistible. Scandale capture l'attention par sa gourmandise miellée et son aura festive hors du commun.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-CP-AMBRENEROLI-027",
            "nom": "Ambre et néroli",
            "marque": "Collection Privée / Niche",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("12000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Néroli, Bergamote, Petitgrain",
            "notes_coeur": "Fleur d'oranger, Jasmin",
            "notes_fond": "Ambre doré, Vanille, Musc",
            "description_courte": "Le contraste solaire entre la fraîcheur de la fleur d'oranger et la chaleur de l'ambre.",
            "description_longue": "Ambre et Néroli fait briller la lumière du néroli méditerranéen en ouverture avant de se déposer sur un lit ambré et vanillé très doux.",
            "description_ia": "Un rayon de soleil lumineux et enveloppant. Ce parfum vous apporte une sensation de fraîcheur florale immédiatement réconfortée par un fond ambré chaud.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-FW-HOMMESINT-028",
            "nom": "Hommes Intenses",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Lavande",
            "notes_coeur": "Iris, Ambrette, Poire",
            "notes_fond": "Cèdre de Virginie, Vétiver",
            "description_courte": "Un boisé poudré d'une sophistication extrême axé sur l'iris et la lavande.",
            "description_longue": "Hommes Intenses reprend la formule légendaire combinant la noblesse poudrée de l'iris à la chaleur boisée du cèdre et de l'ambrette. Un choix de prédilection pour les occasions habillées.",
            "description_ia": "L'élégance à l'état pur. Hommes Intenses sublime le charme masculin avec un sillage poudré, noble et profondément séduisant.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-PC-KHAIRPIST-029",
            "nom": "Khair Pistache",
            "marque": "Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pistache, Glace, Noisette, Bergamote, Cardamome",
            "notes_coeur": "Muguet, Poire, Géranium, Pivoine, Framboise",
            "notes_fond": "Chantilly, Guimauve, Fève Tonka, Barbe à papa",
            "description_courte": "Une gourmandise glacée irrésistible à la pistache, crème chantilly et guimauve.",
            "description_longue": "Khair Pistachio est un délice olfactif. L'ouverture de pistache croquante et de crème glacée glisse vers un fond moelleux de guimauve et de chantilly sucrée.",
            "description_ia": "Un parfum plaisir ultra-gourmand. Khair Pistachio vous enveloppe d'une douceur crémeuse et fruitée qui réveille les sens avec gourmandise.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-MA-JEANLOWEMAT-030",
            "nom": "Jean Lowe : Matière",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Sirop de cassis, Notes aquatiques",
            "notes_coeur": "Rose, Cyclamen, Narcisse, Jasmin Sambac",
            "notes_fond": "Oud, Patchouli, Encens, Benzoin",
            "description_courte": "Une plongée ténébreuse et boisée éclairée par des fleurs blanches et du cassis.",
            "description_longue": "Jean Lowe Matière explore le contraste entre le bois d'agar sombre, l'encens mystique et la fraîcheur fruitée du cassis et de la rose de mai.",
            "description_ia": "Un voyage olfactivement riche et mystique. Ce parfum capture la beauté des bois rares illuminés par un cœur floral aérien et raffiné.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-MA-OMBREFAB-031",
            "nom": "Ombre Nomade Fab-lab",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("35000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Framboise, Saffron",
            "notes_coeur": "Rose, Bois de bouleau, Geranium",
            "notes_fond": "Oud, Encens, Amberwood, Benzoin",
            "description_courte": "La puissance pure du bois d'agar, du cuir fumé et de la framboise.",
            "description_longue": "Réplique du légendaire Ombre Nomade, cette fragrance associe un oud majestueux à la fumée de bouleau et au piquant fruité de la framboise. Une tenue et une projection hors normes.",
            "description_ia": "L'essence même du luxe oriental à l'état pur. Une composition intense et ténébreuse pensée pour imposer une présence inoubliable.",
            "est_nouveau": True,
            "est_bestseller": True
        },

        # --- PARFUMS 32 À 40 ---
        {
            "sku": "PARFUM-LA-ASADBOURBON-032",
            "nom": "Asad : Bourbon",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Poivre noir, Lavande, Cardamome",
            "notes_coeur": "Vanille Bourbon, Muscade, Patchouli",
            "notes_fond": "Amberwood, Bois de santal, Benjoin",
            "description_courte": "Une interprétation plus chaude et vanillée du célèbre Asad, dominée par une vanille bourbon intense.",
            "description_longue": "Asad Bourbon conserve le fond épicé et sombre de l'Asad original tout en l'enrichissant d'une note de vanille riche et liquoreuse qui apporte une sensualité gourmande irrésistible.",
            "description_ia": "Un concentré de séduction masculine. Asad Bourbon marie la puissance des épices chaudes à la rondeur enchanteresse d'une vanille d'exception.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-LA-ECLAIR-033",
            "nom": "Éclair",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Caramel, Lait chaud",
            "notes_coeur": "Miel, Fleurs blanches",
            "notes_fond": "Vanille, Praliné, Musc",
            "description_courte": "Le parfum gourmand viral par excellence : un milk-shake au caramel et à la vanille.",
            "description_longue": "Éclair est une véritable ode aux douceurs d'enfance. Il enveloppe la peau de notes réconfortantes de lait caramélisé et de miel liquide sur un fond vanillé crémeux.",
            "description_ia": "Une gourmandise absolue et addictive. Éclair vous drape dans un cocon de caramel chaud et de vanille veloutée pour un sillage d'une douceur infinie.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-ZA-ROSEGOURMAND-034",
            "nom": "Zara : Rose Gourmand",
            "marque": "Zara",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 80,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Rose, Œillet",
            "notes_coeur": "Ambre, Jasmin",
            "notes_fond": "Vanille, Sucre, Musc",
            "description_courte": "Une rose sucrée et confite plongée dans une vanille intense.",
            "description_longue": "Rose Gourmand est un incontournable de chez Zara. Il associe la fraîcheur de la rose fraîche à des notes de sucre caramélisé et de vanille pour un rendu floral et très gourmand.",
            "description_ia": "Féminin, moderne et irrésistiblement sucré. Rose Gourmand sublime la rose traditionnelle en la transformant en une douceur sucrée à fort pouvoir d'attraction.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-ZA-GOLDENDECADE-035",
            "nom": "Zara : Décennie dorée (Rubis)",
            "marque": "Zara",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 80,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Mandarine, Poivre rose",
            "notes_coeur": "Fleur d'oranger, Lavande, Jasmin",
            "notes_fond": "Vanille, Ambre, Tonka",
            "description_courte": "Une fleur d'oranger incandescente mariée à la lavande et à la vanille.",
            "description_longue": "Version enrichie de Golden Decade, l'édition Ruby met l'accent sur les notes fruitées et ambrées pour offrir une fragrance plus chaude, idéale pour l'hiver et les soirées.",
            "description_ia": "L'incarnation de l'élégance audacieuse. Golden Decade Ruby libère une aura florale et vanillée puissante qui ne passe pas inaperçue.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-ZA-VIBRANTOUD-036",
            "nom": "Zara : Cuir Oud Vibrant",
            "marque": "Zara",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 80,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Citron",
            "notes_coeur": "Encens, Cuir",
            "notes_fond": "Oud, Bois de santal",
            "description_courte": "L'accord hespéridé emblématique de Vibrant Leather rehaussé d'un oud léger et boisé.",
            "description_longue": "Cette déclinaison apporte de la maturité et du mystère au classique Vibrant Leather. La bergamote vive se mêle à un cuir souple et un bois d'agar subtil.",
            "description_ia": "L'alliance parfaite entre la fraîcheur urbaine et la noblesse orientale. Un boisé cuiré moderne et facile à porter en toute circonstance.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-FW-SUAVE-037",
            "nom": "Suave Le Parfum",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Mandarine",
            "notes_coeur": "Bois de santal, Cèdre",
            "notes_fond": "Absolu de vanille, Tonka, Amberwood",
            "description_courte": "Un boisé oriental concentré, mariant la fraîcheur de la bergamote à la chaleur du santal.",
            "description_longue": "Suave Le Parfum reprend le profil caractériel du Sauvage original en lui ajoutant de la profondeur avec un cœur de bois de santal chaud et un fond ambré sirupeux.",
            "description_ia": "Une fraîcheur nocturne intense et mystérieuse. Suave Le Parfum affirme votre prestance avec un sillage viril, boisé et enveloppant.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-LA-RAGHBA-038",
            "nom": "Raghba",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("15000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Sucre vanillé, Oud",
            "notes_coeur": "Encens, Musc",
            "notes_fond": "Bois de santal, Ambre",
            "description_courte": "Un classique oriental sucré et enfumé mêlant sucre vanillé, encens et oud.",
            "description_longue": "Raghba est l'un des plus grands succès de Lattafa. Il propose un accord chaleureux de vanille caramélisée enveloppée dans une fumée d'encens douce et boisée.",
            "description_ia": "L'emblème du parfum oriental gourmand. Raghba offre une sensation de chaleur sucrée et boisée d'une tenue remarquable.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-FW-SCEPTREBRONZ-039",
            "nom": "Sceptre : Bronzite",
            "marque": "Maison Alhambra / Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pamplemousse rose, Bergamote",
            "notes_coeur": "Gingembre, Notes minérales",
            "notes_fond": "Ambroxan, Bois de cèdre",
            "description_courte": "Un pamplemousse explosif associé à la puissance boisée et ambrée de l'ambroxan.",
            "description_longue": "Sceptre Bronzite offre une ouverture d'agrumes ultra-vibrante et pétillante qui laisse rapidement place à une signature d'ambroxan hautement séduisante et moderne.",
            "description_ia": "Une énergie brute et luxueuse. Sceptre Bronzite projette un sillage frais, élégant et irrésistiblement masculin.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-LA-HAYAATIROYALE-040",
            "nom": "Hayaati : Royale",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Citron, Lavande, Prune",
            "notes_coeur": "Fleur d'oranger, Cardamome",
            "notes_fond": "Vanille, Bois de santal, Vétiver",
            "description_courte": "Un parfum aromatique et fruité sur fond crémeux de vanille et lavande.",
            "description_longue": "Hayaati Royale marie l'éclat des agrumes et la douceur de la prune à un cœur floral-épicé, reposant sur un fond de bois chauds et de vanille sucrée.",
            "description_ia": "Un parfum moderne, jeune et dynamique qui combine fraîcheur fruitée et sensualité gourmande.",
            "est_nouveau": False,
            "est_bestseller": False
        },

        # --- PARFUMS 41 À 50 ---
        {
            "sku": "PARFUM-MO-BLACKAOUD-041",
            "nom": "Montale Black Oud",
            "marque": "Montale Paris",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("80000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Mandarine, Pétales de rose",
            "notes_coeur": "Oud (Bois d'agar), Cambrure de rose",
            "notes_fond": "Patchouli, Musc, Labdanum",
            "description_courte": "Le chef-d'œuvre de Montale : une alliance légendaire entre un oud sombre et une rose majestueuse.",
            "description_longue": "Black Aoud est un parfum de caractère exceptionnel. La puissance brute du bois d'agar rencontre la noblesse d'une rose ténébreuse soutenue par un patchouli terreux d'une tenue à toute épreuve.",
            "description_ia": "Incontournable dans le monde de la niche, Montale Black Aoud offre une projection magistrale. Une fragrance ténébreuse et élégante pour marquer les esprits.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-LA-YARA-042",
            "nom": "Yara",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Héliotrope, Orchidées, Tangerine",
            "notes_coeur": "Accord Gourmand, Fruits Tropicaux",
            "notes_fond": "Vanille, Bois de Santal, Musc",
            "description_courte": "Un milkshake crémeux aux fruits tropicaux et à la vanille, doux et enveloppant.",
            "description_longue": "Yara est devenu un best-seller absolu. Il combine des touches florales délicates à un cœur poudré-sucré qui rappelle la guimauve et les fruits tropicaux sur une base vanillée.",
            "description_ia": "Un nuage de douceur ultra-féminin. Yara séduit par sa texture crémeuse et gourmande qui apporte réconfort et fraîcheur tout au long de la journée.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-CD-SAUVAGE-043",
            "nom": "Dior Sauvage",
            "marque": "Christian Dior",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("95000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote de Calabre, Poivre de Sichuan",
            "notes_coeur": "Lavande, Poivre rose, Vétiver, Patchouli, Géranium",
            "notes_fond": "Ambroxan, Cèdre, Labdanum",
            "description_courte": "Un acte de création inspiré des grands espaces : un départ d'agrumes vifs sur un fond ambré boisé.",
            "description_longue": "Sauvage offre une fraîcheur radieuse et puissante. La bergamote poivrée s'appuie sur une Overdose d'ambroxan noble qui diffuse un sillage boisé, masculin et inimitable.",
            "description_ia": "La référence absolue de la parfumerie masculine moderne. Dior Sauvage vous assure un charme magnétique et un sillage irrésistible.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-PC-KHAIRFUSION-044",
            "nom": "Khair Fusion",
            "marque": "Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Litchi, Cassis, Pomme rouge, Citron",
            "notes_coeur": "Rose de mai, Violette, Jasmin",
            "notes_fond": "Sucre vanillé, Ambergris, Musc, Cèdre",
            "description_courte": "Un cocktail d'été fruité, juteux et pétillant dominé par le litchi et le cassis.",
            "description_longue": "Khair Fusion capture la joie des beaux jours. Le litchi croquant se marie à la rose et à un fond vanillé sucré pour offrir une fraîcheur gourmande et vibrante.",
            "description_ia": "Pétillant et plein de vie, Khair Fusion est une caresse fruitée et joyeuse qui réveille vos sens dès les premières pulvérisations.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-FW-ONIRO-045",
            "nom": "Oniro",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("10000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Notes marines, Pamplemousse, Mandarine",
            "notes_coeur": "Feuille de laurier, Jasmin",
            "notes_fond": "Ambre gris, Mousse de chêne, Bois de gaiac, Patchouli",
            "description_courte": "La fraîcheur héroïque : un accord marin et agrumes sur un fond boisé ambré.",
            "description_longue": "Oniro offre un départ aquatique et énergisant qui rencontre la poigne du laurier avant de se poser sur un fond boisé chaud. Parfait pour les journées actives.",
            "description_ia": "Energique et conquérant, Oniro apporte un souffle de fraîcheur tonique idéal pour l'homme dynamique au quotidien.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-PC-KALYLIBRE-046",
            "nom": "Ka-Ly Libre Intense",
            "marque": "Paris Corner / Pendora Scents",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Lavande, Bergamote, Mandarine",
            "notes_coeur": "Fleur d'oranger, Orchidée, Jasmin",
            "notes_fond": "Vanille de Madagascar, Tonka, Ambre gris, Vétiver",
            "description_courte": "Le contraste entre la masculinité de la lavande et la sensualité d'une fleur d'oranger embrasée par la vanille.",
            "description_longue": "Ce parfum offre une signature florale et incandescente. L'orchidée sauvage et la vanille de Madagascar apportent une rondeur opulente à la structure lavandée classique.",
            "description_ia": "Une fragrance de liberté et de pouvoir. Ka-Ly Libre Intense sublime la femme moderne avec un sillage chaleureux et noble.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-LA-MAZAAJI-047",
            "nom": "Mazaaji",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Fleur d'oranger, Jasmin",
            "notes_coeur": "Rose, Notes Poudrées",
            "notes_fond": "Miel, Musc blanc, Ambre",
            "description_courte": "Un bouquet de fleurs blanches enrobé de miel doux et de musc poudré.",
            "description_longue": "Mazaaji est une création féminine d'une grande délicatesse. Le jasmin et la fleur d'oranger s'y épanouissent dans un voile poudré et miellé très propre.",
            "description_ia": "Élégant et lumineux, Mazaaji entoure celle qui le porte d'une aura florale, douce et sophistiquée.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-AZ-POURHOMME-048",
            "nom": "Azzaro Pour Homme",
            "marque": "Azzaro",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Toilette (EDT)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("50000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Anis étoilé, Lavande, Citron, Basilic",
            "notes_coeur": "Bois de santal, Vétiver, Patchouli, Cardamome",
            "notes_fond": "Cuir, Mousse de chêne, Ambre, Musc",
            "description_courte": "L'icône de la séduction masculine : une fougère aromatique indémodable.",
            "description_longue": "Créé en 1978, Azzaro Pour Homme marie la fraîcheur de l'anis et de la lavande à la chaleur des bois précieux et du cuir. Un symbole de virilité élégante.",
            "description_ia": "Un intemporel de la séduction. Azzaro Pour Homme incarne le charisme et la classe au masculin depuis des générations.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        {
            "sku": "PARFUM-PC-KHAIRCONF-049",
            "nom": "Khair Confection",
            "marque": "Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Orchidée vanille, Jasmin",
            "notes_coeur": "Sucre brun, Tonka",
            "notes_fond": "Amberwood, Musc, Patchouli, Royale Vanille",
            "description_courte": "Une vanille riche, ambrée et caramélisée, parfaite pour le superposage (layering).",
            "description_longue": "Khair Confection est une ode à la vanille dans ce qu'elle a de plus chaud et réconfortant. Le sucre brun apporte une facette gourmande irrésistible soutenue par du bois d'ambre.",
            "description_ia": "Un pur délice vanillé. Khair Confection vous enveloppe d'un sillage sucré, chaud et profondément envoûtant.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        {
            "sku": "PARFUM-MA-POURLUI-050",
            "nom": "Mauboussin Pour Lui",
            "marque": "Mauboussin",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("45000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Lavande, Cèdre",
            "notes_coeur": "Anis étoilé, Carvi, Absinthe",
            "notes_fond": "Ambre, Ébène, Mousse de chêne",
            "description_courte": "Un boisé oriental aromatique mystérieux rehaussé par l'anis et la lavande.",
            "description_longue": "Mauboussin Pour Lui joue sur le contraste entre la fraîcheur aromatique de la lavande et la chaleur des bois sombres. Un parfum masculin viril, chic et captivant.",
            "description_ia": "Un bijou de la parfumerie masculine. Mauboussin Pour Lui apporte une signature sobre, classe et affirmée à votre style.",
            "est_nouveau": False,
            "est_bestseller": False
        },

        # --- PARFUMS 51 À 100 ---
        # 51. Tabac rouge
        {
            "sku": "PARFUM-FW-TABACROUGE-051",
            "nom": "Tabac rouge",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("22000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Gingembre, Miel, Cannelle",
            "notes_coeur": "Feuille de tabac, Prune, Maté",
            "notes_fond": "Ambre, Benjoin, Pêche, Fève tonka",
            "description_courte": "Un ambré épicé chaud et opulent mariant des feuilles de tabac blond au miel et aux fruits secs.",
            "description_longue": "Tabac Rouge propose une plongée envoûtante dans un univers oriental riche. La chaleur du tabac à pipe s'adoucit sous la gourmandise du miel et de la prune pour créer un sillage ténébreux et réconfortant.",
            "description_ia": "Chaleureux, mystérieux et profondément addictif. Tabac Rouge enveloppe votre peau d'une aura orientale et suave idéale pour les moments d'exception.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 52. Ra'ed Silver
        {
            "sku": "PARFUM-LA-RAEDSILVER-052",
            "nom": "Ra'ed (Ra'ed Luxe / Silver)",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("35000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Agrumes, Baies de genièvre, Ananas, Pastèque",
            "notes_coeur": "Lavande, Sauge, Poivre rose, Cannelle",
            "notes_fond": "Châtaigne, Vanille, Ambre, Bois de santal, Fraise",
            "description_courte": "Une fraîcheur fruitée et épicée posée sur un fond chaleureux de vanille et bois de santal.",
            "description_longue": "Ra'ed combine l'énergie pétillante des agrumes et des notes de fruits d'été à un cœur aromatique poivré, avant de s'épanouir sur une base douce et boisée très polyvalente.",
            "description_ia": "Un vent de fraîcheur moderne et raffiné. Ra'ed Silver séduit par son équilibre parfait entre énergie fruitée et élégance boisée.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 53. Suave / IS Intense
        {
            "sku": "PARFUM-FW-SUAVEINT-053",
            "nom": "Suave / IS Intense",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Sirop de cassis, Bergamote, Mandarine",
            "notes_coeur": "Rose de mai, Néroli, Davana, Osmanthus",
            "notes_fond": "Patchouli, Vanille, Benjoin, Notes boisées",
            "description_courte": "Un parfum féminin intense et sophistiqué dominé par le cassis et la rose sur fond ambré.",
            "description_longue": "Version plus profonde et envoûtante du chypré classique, il capture l'essence d'une féminité affirmée avec un nectar de cassis riche et un cœur floral sublimé par le patchouli.",
            "description_ia": "Incarnation de la grâce et de la puissance féminine. Un sillage fruité et boisé captivant qui marque les esprits.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 54. Musc Blanc
        {
            "sku": "PARFUM-LA-MUSCBLANC-054",
            "nom": "Musk Blanc / Musc Blanc",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("15000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Musc blanc, Notes poudrées",
            "notes_coeur": "Ylang-ylang, Fleur de lierre",
            "notes_fond": "Musc, Notes boisées, Ambre",
            "description_courte": "L'essence même de la propreté : un musc blanc pur, velouté, poudré et réconfortant.",
            "description_longue": "Musc Blanc procure une sensation immédiate de fraîcheur et de bien-être, rappelant le linge frais et la peau adoucie. Parfait pour une utilisation quotidienne discrète et raffinée.",
            "description_ia": "Un cocon de douceur et de propreté absolue. Musc Blanc vous enveloppe d'une fraîcheur délicate et poudrée tout au long de la journée.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 55. Prohibit Rouge
        {
            "sku": "PARFUM-FW-PROHIBITROUGE-055",
            "nom": "Prohibit Rouge",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Orange sanguine, Gingembre",
            "notes_coeur": "Tubéreuse, Jasmin, Feuille de piment",
            "notes_fond": "Patchouli, Bois de santal, Vétiver",
            "description_courte": "Un bouquet blanc charnel embrasé par l'orange sanguine et le gingembre poivré.",
            "description_longue": "Prohibit Rouge transgresse les codes avec son cœur floral blanc incandescent. L'association de la tubéreuse et des épices chaudes crée un contraste rouge passion ultra-séduisant.",
            "description_ia": "Sensuel, ténébreux et magnétique. Prohibit Rouge attire irrépressiblement les regards avec son sillage floral épicé.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 56. Sceptre Amazonite
        {
            "sku": "PARFUM-PC-AMAZONITE-056",
            "nom": "Sceptre : Amazonite",
            "marque": "Maison Alhambra / Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Geranium, Feuilles vertes",
            "notes_coeur": "Encens, Résines",
            "notes_fond": "Oud (Bois d'agar), Bois de cèdre",
            "description_courte": "Une composition boisée et résineuse noble articulée autour de l'encens et du geranium.",
            "description_longue": "Sceptre Amazonite capture la puissance des bois précieux mystiques. L'envolée fraîche de geranium laisse place à un cœur fumé d'encens posé sur un fond sombre d'oud.",
            "description_ia": "Une empreinte olfactive mystique et majestueuse. Conçu pour ceux qui recherchent un boisé oriental de haute prestance.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 57. Ramz Gold
        {
            "sku": "PARFUM-LA-RAMZGOLD-057",
            "nom": "Ramz Gold",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Pomme, Ananas",
            "notes_coeur": "Bois de santal, Gaïac, Jasmin, Patchouli",
            "notes_fond": "Ambre, Musc, Vanille, Oud",
            "description_courte": "Un parfum oriental fruité et boisé opulent infusé de pomme, d'ambre et de vanille.",
            "description_longue": "Ramz Gold offre une ouverture riche et sucrée soutenue par des bois chauds. La vanille et l'ambre se mélangent au santal pour offrir un rendu luxueux et enveloppant.",
            "description_ia": "L'opulence orientale à son apogée. Ramz Gold diffuse une aura dorée et boisée qui vous accompagne avec élégance.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 58. Scandant Homme Le Parfum
        {
            "sku": "PARFUM-FW-SCANDANTPARF-058",
            "nom": "Scandant Homme : Le Parfum",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Géranium",
            "notes_coeur": "Fève tonka",
            "notes_fond": "Bois de santal, Caramel chaud",
            "description_courte": "Une frappe gourmande et virile : un caramel chaud salé enrobé de fève tonka.",
            "description_longue": "Conçu pour séduire, Scandant Homme Le Parfum oppose la fraîcheur du géranium à la gourmandise extrême du caramel brun et du santal boisé.",
            "description_ia": "Sensuel et décapant. Ce parfum gourmand masculin offre une tenue explosive taillée pour les soirées.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 59. Now / RAVE Now
        {
            "sku": "PARFUM-LA-RAVENOW-059",
            "nom": "Maintenant (Now / RAVE Now)",
            "marque": "Lattafa / RAVE",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Ananas juteux, Bergamote, Pomme",
            "notes_coeur": "Bouleau, Patchouli, Jasmin",
            "notes_fond": "Musc, Mousse de chêne, Ambergris, Vanille",
            "description_courte": "Une bombe d'ananas frais et sucré posée sur un fond boisé fumé masculin.",
            "description_longue": "Connu pour son ouverture ultra-juteuse d'ananas, Now/RAVE offre une fraîcheur immédiate qui évolue vers un bois de bouleau masculin et du musc très séduisant.",
            "description_ia": "Une explosion fruitée irrésistible. Ce parfum vous apporte une dose d'énergie tropicale et boisée parfaite pour les beaux jours.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 60. Hayaati Beau
        {
            "sku": "PARFUM-LA-HAYAATIBEAU-060",
            "nom": "Hayaati (HAYAATI BEAU)",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pomme, Bergamote",
            "notes_coeur": "Cannelle, Bois de rose",
            "notes_fond": "Musc, Vanille, Bois de santal, Ambre",
            "description_courte": "Un classique frais et polyvalent mariant la pomme croquante, la cannelle et le santal.",
            "description_longue": "Hayaati est un passe-partout masculin très apprécié. Il associe la fraîcheur fruitée de la pomme à des notes d'épices douces sur une base ambrée et boisée.",
            "description_ia": "Un sillage jeune, frais et charismatique. Hayaati est le compagnon idéal de l'homme moderne au quotidien.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 61. Wood Essence
        {
            "sku": "PARFUM-BV-WOODESSENCE-061",
            "nom": "Wood Essence",
            "marque": "Bvlgari",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("85000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Agrumes cristallisés, Citron vert, Feuille de coriandre",
            "notes_coeur": "Cèdre, Vétiver, Cyprès",
            "notes_fond": "Résine de benjoin",
            "description_courte": "L'énergie urbaine associée à la force de la nature : un départ d'agrumes vifs sur un cœur boisé intense.",
            "description_longue": "Wood Essence capture l'harmonie entre la ville et la nature. Il associe la vitalité des zestes d'agrumes à la structure noble de trois bois précieux (cèdre, cyprès et vétiver) soutenus par la chaleur du benjoin.",
            "description_ia": "Une reconnexion avec les éléments. Bvlgari Man Wood Essence apporte une signature boisée moderne, fraîche et résolument masculine.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 62. Khamrah Qahwa
        {
            "sku": "PARFUM-LA-KHAMRAHQAHWA-062",
            "nom": "Khamrah Qahwa",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Gingembre, Cannelle, Cardamome",
            "notes_coeur": "Café Arabica, Praliné, Fruits confits, Fleurs blanches",
            "notes_fond": "Café, Vanille, Fève tonka, Benjoin, Bois de santal",
            "description_courte": "Une variation encore plus gourmande du célèbre Khamrah, enrichie d'une note de café torréfié.",
            "description_longue": "Khamrah Qahwa conserve la base épicée et caramélisée de l'original en y injectant l'amertume chaleureuse d'un espresso Arabica. Le résultat est un oriental liquoreux, riche et terriblement réconfortant.",
            "description_ia": "Un élixir d'une gourmandise absolue. Khamrah Qahwa marie l'intensité du café aux dattes sucrées pour un sillage inoubliable.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 63. Supreme Vanilla
        {
            "sku": "PARFUM-ZA-SUPREMEVANILLA-063",
            "nom": "Supreme Vanilla",
            "marque": "Zara",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 80,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Fleur d'oranger",
            "notes_coeur": "Sucre brun, Encre, Rose",
            "notes_fond": "Vanille de Madagascar, Tonka, Cèdre",
            "description_courte": "Une vanille sombre et sophistiquée relevée d'un accord d'encre et de sucre brun.",
            "description_longue": "Loin de la vanille simpliste, Supreme Vanilla explore une facette plus texturée et mystérieuse. La douceur de la vanille s'oppose à des notes boisées et encrées qui lui donnent une profondeur contemporaine.",
            "description_ia": "Moderne et intrigant, Supreme Vanilla réinvente la gourmandise avec un caractère affirmé et élégant.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 64. Mazaaji Rose Gold
        {
            "sku": "PARFUM-MA-MAZAAJIROSE-064",
            "nom": "Mazaaji (Rose Gold)",
            "marque": "Maison Alhambra / Lattafa",
            "categorie": cat_marque,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Fleur d'oranger, Jasmin",
            "notes_coeur": "Rose, Poudre de riz",
            "notes_fond": "Miel, Musc blanc, Ambre",
            "description_courte": "Un bouquet de fleurs blanches enrobé d'un voile poudré et d'un soupçon de miel.",
            "description_longue": "Mazaaji se distingue par sa délicatesse. Les fleurs d'oranger et les pétales de rose se posent doucement sur un lit de musc blanc poudré pour un rendu propre, féminin et chaleureux.",
            "description_ia": "Un hymne à la féminité et à la douceur. Mazaaji enveloppe celle qui le porte d'une aura florale lumineuse et raffinée.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 65. Barrakkat Rouge 540
        {
            "sku": "PARFUM-FW-BARRAKKAT540-065",
            "nom": "Barrakkat Rouge 540",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Safran, Jasmin de grandiflorum",
            "notes_coeur": "Amberwood, Ambre gris",
            "notes_fond": "Résine de sapin, Cèdre",
            "description_courte": "La signature ambrée et minérale iconique : une alchimie entre le safran et le bois de cèdre.",
            "description_longue": "Barrakkat Rouge 540 reproduit la magie du chef-d'œuvre de Francis Kurkdjian. L'envolée épicée du safran laisse place à la transparence cristalline du jasmin et à la chaleur enveloppante de l'amberwood.",
            "description_ia": "Sophistiqué, aérien et hypnotique. Ce parfum diffuse une aura luxueuse qui suscite l'admiration sur son passage.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 66. Velvet Rose
        {
            "sku": "PARFUM-LA-VELVETROSE-066",
            "nom": "Velvet Rose",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Rose de Damas, Patchouli",
            "notes_coeur": "Bois de gaiac, Labdanum",
            "notes_fond": "Ambre, Musc, Oud doux",
            "description_courte": "Une rose sombre et veloutée enlacée dans un bois de gaïac fumé et un ambre précieux.",
            "description_longue": "Velvet Rose capture la beauté d'une rose épanouie à l'obscurité. Sa gourmandise florale est sublimée par les facettes boisées et ambrées de la parfumerie orientale classique.",
            "description_ia": "Somptueux et envoûtant. Velvet Rose s'adresse aux amateurs de fragrances florales intenses et mystérieuses.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 67. Oud Satin
        {
            "sku": "PARFUM-PC-OUDSATIN-067",
            "nom": "Oud Satin",
            "marque": "Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Violette, Rose de Bulgarie",
            "notes_coeur": "Rose de Turquie, Oud du Laos",
            "notes_fond": "Vanille, Ambre, Benjoin",
            "description_courte": "Une caresse de soie orientale : l'alliance somptueuse de la rose, de la vanille et d'un oud délicat.",
            "description_longue": "Ce parfum transpose le toucher du satin en senteur. La violette et les deux roses enveloppent un fond boisé d'oud fondu dans une vanille ambrée et sucrée.",
            "description_ia": "L'élégance à l'état pur. Oud Satin diffuse une chaleur voluptueuse et aristocratique idéale pour les soirées.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 68. Maître de Blue
        {
            "sku": "PARFUM-FW-MAITREBLUE-068",
            "nom": "Maître de Blue",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Citron, Pamplemousse, Menthe, Poivre rose",
            "notes_coeur": "Gingembre, Iso E Super, Muscade, Jasmin",
            "notes_fond": "Encens, Vétiver, Cèdre, Bois de santal, Patchouli",
            "description_courte": "Le grand classique masculin : un élan d'agrumes frais s'ouvrant sur un fond boisé et fumé.",
            "description_longue": "Maître de Blue incarne la liberté masculine. Il offre une ouverture fraîche et dynamique de pamplemousse et menthe, stabilisée par un cœur de gingembre et un fond boisé à l'encens.",
            "description_ia": "Atemporel et charismatique. Maître de Blue apporte une touche de fraîcheur élégante pour toutes les occasions.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 69. Nebras
        {
            "sku": "PARFUM-LA-NEBRAS-069",
            "nom": "Nebras",
            "marque": "Lattafa (Gamme Pride)",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Baies rouges, Mandarine",
            "notes_coeur": "Cacao, Rose, Vanille",
            "notes_fond": "Sucre, Fève tonka, Amberwood, Musc",
            "description_courte": "Un délice gourmand aux notes de chocolat chaud, baies rouges et vanille poudrée.",
            "description_longue": "Nebras est une création enveloppante qui associe la fraîcheur des baies à l'opulence du cacao et du sucre vanillé. Son fond ambré apporte une tenue exceptionnelle sur la peau.",
            "description_ia": "Addictif et réconfortant. Nebras agit comme un cocon sucré aux nuances de chocolat riche et sensuel.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 70. Riggs Oud
        {
            "sku": "PARFUM-RG-RIGGSOUD-070",
            "nom": "Riggs Oud",
            "marque": "Riggs London",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum / Brume",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("8000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Épices douces, Bergamote",
            "notes_coeur": "Bois de cèdre, Notes cuirées",
            "notes_fond": "Oud léger, Ambre gris, Musc",
            "description_courte": "Une interprétation légère et accessible du bois d'oud pour un usage quotidien.",
            "description_longue": "Riggs Oud propose une porte d'entrée facile dans l'univers de l'oud. Il associe des touches épicées à un fond boisé ambré très propre et agréable pour la journée.",
            "description_ia": "Pratique et masculin. Riggs Oud offre une fraîcheur boisée quotidienne à un tarif très accessible.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 71. Cedar Shield
        {
            "sku": "PARFUM-PC-CEDARSHIELD-071",
            "nom": "Cedar Shield",
            "marque": "Paris Corner (Gamme Emir)",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Sève de cèdre, Bergamote",
            "notes_coeur": "Feuille de violette, Vétiver, Cyprès",
            "notes_fond": "Bois de cèdre de l'Atlas, Amberwood, Musc",
            "description_courte": "Une immersion en forêt résineuse : un cèdre majestueux rafraîchi par des feuilles vertes.",
            "description_longue": "Cedar Shield célèbre la puissance noble du cèdre. L'alliance de la violette et du cyprès apporte une sensation de fraîcheur sous-bois, sublimée par une base boisée et ambrée élégante.",
            "description_ia": "Naturel, pur et apaisant. Cedar Shield offre un souffle boisé et vert d'un grand raffinement.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 72. Honor & Glory
        {
            "sku": "PARFUM-LA-HONORGLORY-072",
            "nom": "Honor & Glory (Bade'e Al Oud Blanc/Jaune)",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Crème brûlée à l'ananas, Brûlé de sucre",
            "notes_coeur": "Cannelle, Benjoin, Turmeric, Poivre noir",
            "notes_fond": "Vanille, Cachemire, Bois de santal, Amber",
            "description_courte": "Un dessert oriental audacieux : ananas caramélisé, cannelle et crème brûlée sur fond vanillé.",
            "description_longue": "Dernier-né de la saga Bade'e Al Oud, Honor & Glory surprend par son accord gourmand unique d'ananas chaud et de crème brûlée, associé aux épices orientales et au bois de santal.",
            "description_ia": "Une créativité olfactive saisissante. Un parfum gourmand luxueux qui laisse un sillage vanillé et fruité inoubliable.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 73. Noir Afghan
        {
            "sku": "PARFUM-FW-NOIRAFGHAN-073",
            "nom": "Noir Afghan",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Cannabis, Notes vertes",
            "notes_coeur": "Résines, Notes boisées, Tabac, Café",
            "notes_fond": "Oud (Bois d'agar), Encens",
            "description_courte": "L'intensité à l'état pur : un élixir sombre et fumé d'encens, de tabac et d'oud mystique.",
            "description_longue": "Noir Afghan s'adresse aux amateurs de parfums complexes et ténébreux. Il capture l'odeur du hashish végétal, du café torréfié et du tabac dans une brume d'encens d'une ténacité incroyable.",
            "description_ia": "Mystique, puissant et hypnotique. Un parfum d'exception réservé à ceux qui osent imposer leur présence.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 74. Shaheen Silver
        {
            "sku": "PARFUM-LA-SHAHEENSILVER-074",
            "nom": "Shaheen Silver",
            "marque": "Lattafa (Gamme Pride)",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Cassis, Bergamote",
            "notes_coeur": "Patchouli, Rose",
            "notes_fond": "Mousse de chêne, Musc, Ambergris",
            "description_courte": "Un départ fruité et vif suivi d'une structure chyprée et boisée très royale.",
            "description_longue": "Shaheen Silver (le Faucon Argenté) incarne l'élégance et la prestance. Le cassis pétillant s'associe au patchouli et à une mousse de chêne terreuse pour un rendu noble et très masculin.",
            "description_ia": "Statut, élégance et fraîcheur. Shaheen Silver vous drape d'une aura charismatique taillée pour les leaders.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 75. Posh Malt
        {
            "sku": "PARFUM-FW-POSHMALT-075",
            "nom": "Posh Malt",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Notes fruitières, Orange, Bergamote",
            "notes_coeur": "Malt, Whisky, Patchouli, Café",
            "notes_fond": "Peat (Tourbe), Vanille, Ambre, Musk",
            "description_courte": "Une composition chaleureuse et liquoreuse inspirée des whiskies maltés vieillis en fût de chêne.",
            "description_longue": "Posh Malt marie la rondeur fruitée du départ à des effluves de barrique de malt, de café et de vanille. Un parfum masculin suave et réconfortant pour les soirées fraîches.",
            "description_ia": "Chaleureux et distingué. Posh Malt offre une signature gourmande et boisée idéale pour l'homme épicurien.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 76. Jean Lowe Immortal
        {
            "sku": "PARFUM-MA-JEANLOWEIMM-076",
            "nom": "Jean Lowe Immortal",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("24000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Gingembre, Pamplemousse, Bergamote",
            "notes_coeur": "Romarin, Sauge, Géranium, Notes aquatiques",
            "notes_fond": "Ambroxan, Ambergris, Labdanum",
            "description_courte": "L'énergie piquante du gingembre associée à un pamplemousse juteux et un ambroxan luxueux.",
            "description_longue": "Succès phénoménal de Maison Alhambra, Immortal procure une sensation de fraîcheur infinie. Le gingembre frais tranche avec l'amertume du pamplemousse sur un fond ambré moderne.",
            "description_ia": "Une fraîcheur vibrante et luxueuse. L'allié parfait de l'homme moderne en quête d'un sillage propre et dynamique.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 77. Musamam White Intense
        {
            "sku": "PARFUM-LA-MUSAMAMWHITE-077",
            "nom": "Musamam White Intense",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Épices douces, Cardamome",
            "notes_coeur": "Ylang-ylang, Mahonial, Bois de santal, Thé",
            "notes_fond": "Amberwood, Benzoin, Musc",
            "description_courte": "Un bois de santal crémeux et épicé, rafraîchi par une touche de thé et d'agrumes.",
            "description_longue": "Présenté dans son flacon orné du serpent d'argent, Musamam White Intense propose un santal ultra-raffiné. La cardamome et le thé apportent une élégance poudrée et moderne.",
            "description_ia": "Un luxe contemporain. Ce parfum diffuse une aura sophistiquée, douce et chaleureuse qui ne laisse personne indifférent.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 78. Amber & Leather
        {
            "sku": "PARFUM-FW-AMBERLEATHER-078",
            "nom": "Amber & Leather",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Cardamome",
            "notes_coeur": "Cuir noir, Jasmin Sambac",
            "notes_fond": "Patchouli, Amber, Mousse de chêne",
            "description_courte": "La sensation du cuir brut et souple réchauffé par l'ambre et la cardamome.",
            "description_longue": "Amber & Leather évoque les grands espaces du Far West. Le cuir intense est adouci par la délicatesse du jasmin floral et la chaleur enveloppante de l'ambre.",
            "description_ia": "Texturé, viril et captivant. Un cuir d'une élégance absolue pour affirmer sa personnalité.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 79. Violet Blossom
        {
            "sku": "PARFUM-ZA-VIOLETBLOSS-079",
            "nom": "Violet Blossom",
            "marque": "Zara",
            "categorie": cat_marque,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 90,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Fleur de cerisier",
            "notes_coeur": "Magnolia, Violette",
            "notes_fond": "Fève tonka, Vanille",
            "description_courte": "Un bouquet floral nocturne où la violette et le magnolia se fondent dans la fève tonka.",
            "description_longue": "Violet Blossom est une fragrance féminine douce et envoûtante. La fleur de cerisier apporte un départ fruité qui glisse vers un cœur poudré de violette et un fond d'amande tonka.",
            "description_ia": "Une douceur florale et amandée irrésistible, parfaite pour ajouter une touche de mystère au quotidien.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 80. Riggs Voyage
        {
            "sku": "PARFUM-RG-RIGGSVOYAGE-080",
            "nom": "Riggs Voyage",
            "marque": "Riggs London",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum / Brume",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("8000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Notes marines, Melon, Bergamote",
            "notes_coeur": "Menthe, Cardamome, Lavande",
            "notes_fond": "Bois de cèdre, Ambergris",
            "description_courte": "Une vague d'air marin et d'agrumes énergisante pour l'homme d'action.",
            "description_longue": "Riggs Voyage offre une fraîcheur océanique instantanée. Les notes aquatiques et la menthe apportent une sensation coup de fouet idéale après le sport ou lors des journées chaudes.",
            "description_ia": "Dynamique et tonique. Le parfum du grand large accessible à tous les instants de la journée.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 81. Qaed Al Fursan
        {
            "sku": "PARFUM-LA-QAEDFURSAN-081",
            "nom": "Qaed Al Fursan",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Ananas, Saffron",
            "notes_coeur": "Jasmine, Sapin baumier",
            "notes_fond": "Amber, Bois de cèdre, Agarwood (Oud)",
            "description_courte": "Un ananas caramélisé et safrané posé sur un fond boisé résineux.",
            "description_longue": "Qaed Al Fursan séduit immédiatement par son départ d'ananas mûr et sucré relevé d'une pointe de safran. L'évolution se fait plus boisée et masculine grâce au cèdre et au sapin baumier.",
            "description_ia": "Chaleureux, fruité et charismatique. Qaed Al Fursan apporte une gourmandise boisée unique qui attire les compliments.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 82. Berries Sample
        {
            "sku": "PARFUM-FW-BERRIESSAMPLE-082",
            "nom": "Berries Sample",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "femme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "moyenne",
            "prix_unitaire": Decimal("15000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Framboise, Mûre, Fraise des bois",
            "notes_coeur": "Pivoine, Rose, Violette",
            "notes_fond": "Vanille, Musc blanc, Amberwood",
            "description_courte": "Un panier de fruits rouges acidulés enrobé de pétales de rose et de vanille.",
            "description_longue": "Berries Sample est une fragrance joyeuse et pétillante. La gourmandise des baies sauvages s'équilibre avec la fraîcheur de la pivoine pour offrir un sillage jeune et sucré.",
            "description_ia": "Pétillant, gourmand et plein de fraîcheur. Une véritable caresse fruitée idéale pour sublimer vos journées.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 83. Sceptre Malachite
        {
            "sku": "PARFUM-MA-MALACHITE-083",
            "nom": "Sceptre : Malachite",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bitter Orange, Petitgrain",
            "notes_coeur": "Tubéreuse, Ylang-ylang, Jasmin Sambac",
            "notes_fond": "Vanille, Benjoin, Ambergris",
            "description_courte": "Une tubéreuse incandescente et solaire enveloppée dans un benjoin résineux et vanillé.",
            "description_longue": "Sceptre Malachite rend hommage aux fleurs blanches opulentes. La tubéreuse et l'ylang-ylang créent une sensation crémeuse et luxueuse soutenue par un fond ambré chaleureux.",
            "description_ia": "L'opulence florale à son sommet. Un sillage solaire, élégant et envoûtant pour marquer votre présence.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 84. Al Qiam Silver
        {
            "sku": "PARFUM-LA-ALQIAMSILVER-084",
            "nom": "Al Qiam Silver",
            "marque": "Lattafa (Gamme Pride)",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Grapefruit, Gingembre",
            "notes_coeur": "Ambrosia, Bois de santal",
            "notes_fond": "Ambroxan, Vetiver, Cèdre",
            "description_courte": "Un pamplemousse tonique et amer amplifié par une overdose d'ambroxan et de vétiver.",
            "description_longue": "Al Qiam Silver délivre une fraîcheur saisissante d'agrumes épicés au gingembre. Le fond ambré et boisé apporte une tenue remarquable et une signature masculine raffinée.",
            "description_ia": "Énergique, luxueux et vibrant. Le parfum idéal pour l'homme d'affaires moderne qui cherche un sillage propre et puissant.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 85. Des Tentaion
        {
            "sku": "PARFUM-FW-DESTENTAION-085",
            "nom": "Des Tentaion",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Menthe fraîche, Pomme verte, Citron",
            "notes_coeur": "Fève tonka, Ambrosia, Géranium",
            "notes_fond": "Vanille de Madagascar, Vétiver, Mousse de chêne, Cèdre",
            "description_courte": "L'ardeur de la passion : menthe fraîche, pomme croquante et vanille passionnée.",
            "description_longue": "Des Tentaion joue sur le contraste entre la fraîcheur glacée de la menthe et la chaleur sucrée de la vanille et de la tonka. Un parfum de séduction taillé pour les sorties nocturnes.",
            "description_ia": "Un pouvoir d'attraction irrésistible. Une fragrance masculine intense qui combine fraîcheur et gourmandise.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 86. Hayaati Al Maleky
        {
            "sku": "PARFUM-LA-HAYAATIMAL-086",
            "nom": "Hayaati Al Maleky",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Muscade, Cardamome, Baies de genièvre",
            "notes_coeur": "Lavande, Noisette, Notes boisées",
            "notes_fond": "Amber, Vétiver, Vanille",
            "description_courte": "Un accord aromatique et boisé agrémenté de notes épicées et gourmandes.",
            "description_longue": "Hayaati Al Maleky offre une ouverture épicée chaleureuse qui glisse vers un cœur lavandé et boisé. La noisette et la vanille apportent une touche gourmande moderne en fond.",
            "description_ia": "Aromatique et enveloppant, Hayaati Al Maleky apporte une signature masculine distinguée et contemporaine.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 87. Khair Pistachio
        {
            "sku": "PARFUM-PC-KHAIRPISTACHIO-087",
            "nom": "Khair Pistachio",
            "marque": "Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pistache, Glace italienne, Bergamote, Noisette, Cardamome",
            "notes_coeur": "Muguet, Poire, Géranium, Jasmine",
            "notes_fond": "Crème fouettée, Guimauve, Pierre de coton, Tonka, Cèdre",
            "description_courte": "Une glace à la pistache onctueuse garnie de crème fouettée et de guimauve.",
            "description_longue": "Khair Pistachio est la définition même du gourmand ludique. La pistache croquante s'associe à la fraîcheur de la poire et à la rondeur de la crème chantilly pour un résultat irrésistible.",
            "description_ia": "Gourmand, doux et réconfortant. Un parfum dessert captivant qui fait sensation dès les premières secondes.",
            "est_nouveau": True,
            "est_bestseller": True
        },
        # 88. Musamam
        {
            "sku": "PARFUM-LA-MUSAMAM-088",
            "nom": "Musamam",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("28000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Mandarine d'Italie, Cardamome, Saffron",
            "notes_coeur": "Géranium, Bois de cèdre, Amberwood",
            "notes_fond": "Cuir noir, Bois d'Agar (Oud), Patchouli",
            "description_courte": "Un cuir obscur et épicé relevé de mandarine et de bois de cèdre noble.",
            "description_longue": "Musamam (présenté dans son flacon noir au serpent) s'adresse aux amateurs de senteurs affirmées. Le cuir brut et l'oud sont contrebalancés par la fraîcheur de la mandarine et du safran.",
            "description_ia": "Sombre, viril et sophistiqué. Musamam est un parfum de caractère conçu pour marquer une empreinte inoubliable.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 89. Amber & Spice
        {
            "sku": "PARFUM-FW-AMBERSPICE-089",
            "nom": "Amber & Spice",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Amber, Encens",
            "notes_coeur": "Bois de santal, Cannelle, Épices d'Orient",
            "notes_fond": "Benjoin, Labdanum, Vanilla",
            "description_courte": "L'ambre résineux dans toute sa pureté : fumé, épicé et profondément chaleureux.",
            "description_longue": "Amber & Spice transporte dans un atelier de résines orientales. La richesse du labdanum et de l'encens est adoucie par la vanille et le bois de santal pour un sillage enveloppant.",
            "description_ia": "Opulent et mystérieux. Un ambre majestueux qui apporte chaleur et élégance lors des moments d'exception.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 90. Art of Arabia I
        {
            "sku": "PARFUM-LA-ARTOFARABIA1-090",
            "nom": "Art of Arabia I",
            "marque": "Lattafa (Gamme Pride)",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Menthe fraîche",
            "notes_coeur": "Thé noir, Gingembre, Lavender",
            "notes_fond": "Ambrosia, Cinnamon, Bois de cèdre",
            "description_courte": "Une tasse de thé noir au gingembre et à la menthe infusée d'épices d'Arabie.",
            "description_longue": "Première création de la collection Art of Arabia, ce parfum marie la fraîcheur aromatique de la menthe et du thé noir à des épices chaudes posées sur un fond boisé séduisant.",
            "description_ia": "Raffiné, frais et complexe. Un hommage moderne à la tradition de l'hospitalité orientale.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 91. Art of Arabia II
        {
            "sku": "PARFUM-LA-ARTOFARABIA2-091",
            "nom": "Art of Arabia II",
            "marque": "Lattafa (Gamme Pride)",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Cardamome, Heliotrope, Pink Pepper",
            "notes_coeur": "Jasmine, Lavender, Patchouli",
            "notes_fond": "Vanilla, Amber, Agarwood (Oud), Sandalwood",
            "description_courte": "Un oriental poudré et boisé sublimé par la cardamome et la vanille.",
            "description_longue": "Ce second volet met en avant la richesse des bois précieux. La cardamome poivrée s'adoucit au contact de l'héliotrope avant de se poser sur un lit d'oud vanillé.",
            "description_ia": "Chaud et majestueux. Une création équilibrée qui capture l'essence du luxe oriental contemporain.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 92. Supreme Amber
        {
            "sku": "PARFUM-FW-SUPREMEAMBER-092",
            "nom": "Supreme Amber",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Amber, Bergamote",
            "notes_coeur": "Cinnamon, Coriandre, Rose",
            "notes_fond": "Vanilla, Tonka, Benzoin, Patchouli",
            "description_courte": "Un ambre liquoreux et vanillé d'une grande rondeur.",
            "description_longue": "Supreme Amber enveloppe la peau d'un voile doré. L'ouverture légèrement agrumée laisse vite place à des résines chaudes de benjoin et de vanille.",
            "description_ia": "Chaleureux et réconfortant. Un parfum ambré idéal pour les moments d'élégance nocturne.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 93. Sheikh Al Shuyukh Lux Edition
        {
            "sku": "PARFUM-LA-SHEIKHLUXE-093",
            "nom": "Sheikh Al Shuyukh (Édition Luxe)",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Écorce de cannelle, Rose, Safran",
            "notes_coeur": "Caramel, Patchouli",
            "notes_fond": "Vanilla, Ambre, Bois de santal, Ambrosia",
            "description_courte": "Une gourmandise épicée mêlant cannelle, caramel chaud et bois précieux.",
            "description_longue": "Ce grand classique Lattafa combine la puissance de la cannelle et du safran à un cœur de caramel fondant sur un fond ambré et vanillé.",
            "description_ia": "Opulent et gourmand. Un parfum qui affirme votre prestance avec un sillage épicé et caramélisé.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 94. Strictly Oud
        {
            "sku": "PARFUM-PC-STRICTLYOUD-094",
            "nom": "Strictly Oud",
            "marque": "Paris Corner",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("25000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Labdanum",
            "notes_coeur": "Patchouli, Rose de Damas",
            "notes_fond": "Oud (Bois d'agar), Sandalwood, Cèdre",
            "description_courte": "L'accord oriental royal par excellence : rose intense et bois d'oud fumé.",
            "description_longue": "Strictly Oud reproduit la dualité entre la délicatesse d'une rose de caractère et la puissance d'un bois d'oud d'Orient posé sur du labdanum.",
            "description_ia": "Noblesse et caractère. Un sillage puissant et raffiné conçu pour les amateurs d'oud traditionnel.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 95. Khaltaat Al Arabia
        {
            "sku": "PARFUM-LA-KHALTAATARAB-095",
            "nom": "Khaltaat Al Arabia",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pomme, Ananas, Épices douces",
            "notes_coeur": "Cannelle, Muscade, Jasmine",
            "notes_fond": "Amber, Musk, Vanilla, Sandalwood",
            "description_courte": "Une compotée de pommes aux épices et à la cannelle sur fond ambré.",
            "description_longue": "Ce parfum offre une sensation de tarte aux pommes chaude saupoudrée de cannelle et de muscade, soutenue par de l'ambre et du musc.",
            "description_ia": "Gourmand et épicé. Une fragrance chaleureuse parfaite pour créer une atmosphère accueillante.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 96. Emerald Green
        {
            "sku": "PARFUM-FW-EMERALDGREEN-096",
            "nom": "Emerald Green",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("20000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bitter Orange, Petitgrain",
            "notes_coeur": "Jasmine Sambac, Ylang-Ylang, Pink Pepper",
            "notes_fond": "Lily, Vanilla, Benzoin",
            "description_courte": "Un bouquet de jasmin et de fleurs blanches relevé par l'orange amère.",
            "description_longue": "Emerald Green capture l'élégance des fleurs blanches solaires. Le jasmin sambac et le lys s'y fondent dans une vanille résineuse.",
            "description_ia": "Solaire et sophistiqué. Une empreinte florale lumineuse d'une grande distinction.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 97. Confidential Private Gold
        {
            "sku": "PARFUM-LA-CONFIDENTIAL-097",
            "nom": "Confidential Private Gold",
            "marque": "Lattafa",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Pêche, Fruit de la passion, Poire, Cassis",
            "notes_coeur": "Muguet",
            "notes_fond": "Musk, Vanilla, Sandalwood, Patchouli",
            "description_courte": "Une explosion de fruits tropicaux juteux sur un lit de musc blanc puissant.",
            "description_longue": "Très apprécié pour son caractère fruité intense, Confidential Private Gold associe la pêche et le fruit de la passion à un musc d'une ténacité remarquable.",
            "description_ia": "Vibrant et magnétique. Un cocktail de fruits exotiques qui laisse un sillage poudré et frais.",
            "est_nouveau": False,
            "est_bestseller": True
        },
        # 98. Intense Wood
        {
            "sku": "PARFUM-FW-INTENSEWOOD-098",
            "nom": "Intense Wood",
            "marque": "Fragrance World",
            "categorie": cat_dupe,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("18000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Violette, Feuille de violette, Eau de mer",
            "notes_coeur": "Vétiver, Cèdre",
            "notes_fond": "Ambre, Musc, Sapin",
            "description_courte": "Un boisé vert et aquatique dominé par la feuille de violette et le cèdre.",
            "description_longue": "Intense Wood rappelle une forêt mouillée après la pluie. La fraîcheur de la violette rencontre la structure séchante du cèdre et du vétiver.",
            "description_ia": "Élégant, propre et naturel. La fragrance idéale pour l'homme connecté à la nature.",
            "est_nouveau": False,
            "est_bestseller": False
        },
        # 99. Musamam Dark Intense
        {
            "sku": "PARFUM-LA-MUSAMAMDARK-099",
            "nom": "Musamam Dark Intense",
            "marque": "Lattafa",
            "categorie": cat_marque,
            "genre_cible": "homme",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "très forte",
            "prix_unitaire": Decimal("30000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Bergamote, Poivre noir, Oliban",
            "notes_coeur": "Cuir, Cacao, Patchouli",
            "notes_fond": "Amberwood, Oud, Vanilla",
            "description_courte": "Une interprétation sombre et cacao-cuirée de la collection Musamam.",
            "description_longue": "Ce parfum offre une signature mystérieuse. Le cacao amer et le cuir s'y marient à l'encens et au poivre pour un résultat ténébreux.",
            "description_ia": "Captivant et ténébreux. Un parfum de caractère taillé pour s'imposer en soirée.",
            "est_nouveau": True,
            "est_bestseller": False
        },
        # 100. Charuto Tobacco Vanille
        {
            "sku": "PARFUM-PC-CHARUTOVAN-100",
            "nom": "Charuto Tobacco Vanille",
            "marque": "Paris Corner / Pendora Scents",
            "categorie": cat_dupe,
            "genre_cible": "mixte",
            "duree": "Eau de Parfum (EDP)",
            "contenance_ml": 100,
            "intensite": "forte",
            "prix_unitaire": Decimal("24000.00"),
            "prix_promotionnel": None,
            "notes_tete": "Feuilles de tabac, Épices",
            "notes_coeur": "Vanille, Cacao, Fève tonka, Fleur de tabac",
            "notes_fond": "Fruits secs, Notes boisées",
            "description_courte": "L'accord légendaire entre le tabac à pipe opulent et la vanille gourmande.",
            "description_longue": "Charuto restitue l'ambiance chaleureuse d'un club privé. Le tabac séché est adouci par la tonka, le cacao et les fruits secs dans une vanille riche.",
            "description_ia": "Chaleureux, aristocratique et gourmand. Un grand classique ambré à la tenue irréprochable.",
            "est_nouveau": True,
            "est_bestseller": True
        }
    ]

    print("\n--- Importation des parfums 4 à 100 dans la base de données ---")
    created_count = 0
    updated_count = 0

    for item in parfums_data:
        # Recherche par référence SKU ou par nom exact
        parfum = Parfum.objects.filter(reference_sku=item["sku"]).first()
        if not parfum:
            parfum = Parfum.objects.filter(nom__iexact=item["nom"]).first()

        defaults = {
            "nom": item["nom"],
            "slug": slugify(item["nom"]),
            "marque": item["marque"],
            "categorie": item["categorie"],
            "genre_cible": item["genre_cible"],
            "duree": item["duree"],
            "contenance_ml": item["contenance_ml"],
            "intensite": item["intensite"],
            "prix_unitaire": item["prix_unitaire"],
            "prix_promotionnel": item["prix_promotionnel"],
            "notes_tete": item["notes_tete"],
            "notes_coeur": item["notes_coeur"],
            "notes_fond": item["notes_fond"],
            "description_courte": item["description_courte"],
            "description_longue": item["description_longue"],
            "description_ia": item["description_ia"],
            "est_nouveau": item["est_nouveau"],
            "est_bestseller": item["est_bestseller"],
            "stock_quantite": 20,
            "actif": True
        }

        if parfum:
            for key, val in defaults.items():
                setattr(parfum, key, val)
            parfum.save()
            updated_count += 1
            print(f"[*] Mis à jour : {parfum.nom} (Catégorie: {parfum.categorie.nom})")
        else:
            defaults["reference_sku"] = item["sku"]
            parfum = Parfum.objects.create(**defaults)
            created_count += 1
            print(f"[+] Ajouté : {parfum.nom} (Catégorie: {parfum.categorie.nom})")

    print(f"\n==========================================")
    print(f"Importation terminée : {created_count} créés, {updated_count} mis à jour.")
    print(f"==========================================")

if __name__ == "__main__":
    create_or_update_superuser()
    import_parfums()
