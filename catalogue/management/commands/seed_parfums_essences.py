import random
import uuid
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from catalogue.models import (
    CategorieParfum,
    Parfum,
    Essence,
    LotEssence,
    ProduitFiniEssence,
    Tag,
    TagParfum,
    TagEssence,
)

ONLINE_IMAGE_URLS = [
    "https://images.unsplash.com/photo-1592945403244-b3fbafd7f539?w=800&q=80",
    "https://images.unsplash.com/photo-1547887537-6158d64c35b3?w=800&q=80",
    "https://images.unsplash.com/photo-1523293182086-7651a899d37f?w=800&q=80",
    "https://images.unsplash.com/photo-1594035910387-fea47794261f?w=800&q=80",
    "https://images.unsplash.com/photo-1588405748880-12d1d2a59f75?w=800&q=80",
    "https://images.unsplash.com/photo-1527632984437-114449716082?w=800&q=80",
    "https://images.unsplash.com/photo-1563178406-4cdc2923acbc?w=800&q=80",
    "https://images.unsplash.com/photo-1615397349754-cfa2066a298e?w=800&q=80",
    "https://images.unsplash.com/photo-1583445013765-46c20c4a6772?w=800&q=80",
    "https://images.unsplash.com/photo-1592914610354-fd354ea45e48?w=800&q=80",
    "https://images.unsplash.com/photo-1541643600914-78b084683601?w=800&q=80",
    "https://images.unsplash.com/photo-1595425970377-c9703cf48b6d?w=800&q=80",
    "https://images.unsplash.com/photo-1616949755610-8c9bbc08f138?w=800&q=80",
    "https://images.unsplash.com/photo-1512777576244-b846ac3d816f?w=800&q=80",
    "https://images.unsplash.com/photo-1508746829417-e6f548d8d6ed?w=800&q=80",
]

MARQUES_PARFUMS = [
    "Dior", "Chanel", "Tom Ford", "Creed", "Lattafa", "Maison Francis Kurkdjian",
    "Guerlain", "Kilian Paris", "Byredo", "Roja Dove", "Amouage", "Penhaligon's",
    "Yves Saint Laurent", "Armani Privé", "Xerjoff", "Parfums de Marly", "Nishane",
    "Mancera", "Montale", "Jo Malone London", "Diptyque", "Acqua di Parma"
]

MARQUES_ESSENCES = [
    "Givaudan Exclusif", "Firmenich Sélection", "Mane & Fils Grasse", "IFF Rare Extracts",
    "Symrise Fine Fragrance", "Expressions Parfumées", "Robertet Haute Parfumerie",
    "Laboratoire Monique Rémy", "LMR Naturals", "Albert Vieille"
]

PREFIXES_NOMS = [
    "Royal", "Impérial", "Santal", "Ambre", "Oud", "Musc", "Rose", "Cuir", "Vanille",
    "Vétiver", "Patchouli", "Cèdre", "Iris", "Fleur", "Néroli", "Jasmin", "Élixir",
    "Sultan", "Prince", "Majestic", "Velours", "Or", "Diamant", "Ébène", "Nocturne"
]

QUALIFICATIFS = [
    "Absolu", "Intense", "Noir", "Blanc", "Doré", "Céleste", "Mystique", "Sauvage",
    "Sublime", "Éternel", "Précieux", "Souverain", "Sensuel", "Élégant", "Magnifique",
    "Envoûtant", "Secret", "Impérial", "Suprême", "Fascinant", "Nocturne"
]

NOTES_TETE_POOL = [
    "Bergamote de Calabre, Citron d'Italie et Poivre rose",
    "Mandarine de Sicile, Cardamome et Baies de genièvre",
    "Pamplemousse rose, Menthe fraîche et Coriandre",
    "Pomme croquante, Lavande de Provence et Gingembre frais",
    "Safran d'Orient, Noix de muscade et Cannelle de Ceylan",
    "Néroli de Tunisie, Petitgrain et Accord marin ozoné",
    "Orange sanguine, Cassis noir et Thym blanc",
    "Poire williams, Accord aldéhydé et Élémi des Philippines",
]

NOTES_COEUR_POOL = [
    "Rose de Mai, Jasmin Sambac et Géranium Bourbon",
    "Fève tonka torréfiée, Encens d'Oman et Iris de Florence",
    "Cèdre de l'Atlas, Clou de girofle et Patchouli blanc",
    "Feuilles de violette, Cuir souple et Ambre chaud",
    "Absolu de vanille, Cannelle douce et Fleur d'oranger",
    "Magnolia précieux, Ylang-ylang des Comores et Héliotrope",
    "Tabac blond miellé, Bois de gaïac et Cardamome verte",
    "Pivoine soyeuse, Thé noir fumé et Racine d'iris",
]

NOTES_FOND_POOL = [
    "Oud du Cambodge, Santal de Mysore, Ambre gris et Musc pur",
    "Bois de santal blanc, Vanille Bourbon, Fève tonka et Mousse de chêne",
    "Ambre noir, Cuir de Russie, Patchouli d'Indonésie et Benjoin de Siam",
    "Musc blanc soyeux, Vétiver d'Haïti et Bois de cèdre de Virginie",
    "Résine d'oliban, Myrrhe sacrée, Bois de cachemire et Caramel ambré",
    "Vétiver fumé, Ciste labdanum, Ambrette et Bois ambrés modernes",
]

FOURNISSEURS_POOL = [
    "Mane & Fils (Grasse, France)",
    "Givaudan SA (Vernier, Suisse)",
    "Firmenich International (Genève, Suisse)",
    "International Flavors & Fragrances - IFF (New York, USA)",
    "Symrise AG (Holzminden, Allemagne)",
    "Expressions Parfumées (Grasse, France)",
    "Robertet (Grasse, France)",
]

PAYS_ORIGINE_POOL = [
    "France (Grasse)",
    "Suisse",
    "Italie",
    "Émirats Arabes Unis",
    "Inde",
    "Espagne",
    "Maroc",
]

COULEURS_POOL = [
    "Ambrée dorée",
    "Transparente cristalline",
    "Jaune ambré chaud",
    "Rubis subtil",
    "Cognac lumineux",
    "Émeraude claire",
]

DUREES_POOL = [
    "8h à 12h",
    "12h à 24h",
    "Plus de 24h",
    "Jusqu'à 48h",
]


class Command(BaseCommand):
    help = "Génère et insère 300 Parfums et 300 Essences complets avec liens d'images externes en BD (sans stockage local)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=300,
            help="Nombre d'éléments à créer par type de produit (défaut: 300)",
        )

    def handle(self, *args, **options):
        count = options["count"]
        self.stdout.write(self.style.NOTICE(f"=== SEEDING RAPIDE : {count} Parfums et {count} Essences (URLs directes en BD) ==="))

        # 1. Catégories Parfum
        categories_data = [
            ("Parfums Orientaux & Gourmands", "Fragrances chaudes, vanillées et orientales."),
            ("Parfums Boisés & Épicés", "Accords nobles de santal, cèdre et épices rares."),
            ("Parfums Floraux & Fruités", "Bouquets de roses délicates et notes pétillantes."),
            ("Parfums Frais & Aromatiques", "Fraîcheur vivifiante d'agrumes et d'herbes aromatiques."),
            ("Collection Privée & Niches", "Créations rares pour connaisseurs exigeants."),
        ]
        categories_obj = []
        for nom_cat, desc_cat in categories_data:
            cat, _ = CategorieParfum.objects.get_or_create(
                nom=nom_cat,
                defaults={"description": desc_cat, "actif": True}
            )
            categories_obj.append(cat)

        # 2. Tags olfactifs
        tags_def = {
            "Famille olfactive": ["Oriental", "Boisé", "Floral", "Ambré", "Gourmand", "Frais", "Chypré", "Aromatique"],
            "Sillage": ["Discret", "Modéré", "Intense", "Énorme"],
            "Humeur": ["Séducteur", "Confiant", "Élégant", "Romantique", "Mystérieux", "Audacieux"],
            "Occasion": ["Soirée de gala", "Quotidien chic", "Rendez-vous galant", "Cérémonie & Fête", "Affaires & Travail"],
            "Saison": ["Automne / Hiver", "Printemps / Été", "Toutes saisons"],
            "Moment de la journée": ["Soir", "Journée", "Nuit", "Tout moment"],
        }
        tag_instances = {}
        for tag_nom in tags_def.keys():
            t_obj, _ = Tag.objects.get_or_create(nom=tag_nom, defaults={"actif": True})
            tag_instances[tag_nom] = t_obj

        # 3. Génération des Parfums (avec liens d'images externes directement enregistrés)
        self.stdout.write(self.style.NOTICE(f"--- Création de {count} Parfums ---"))
        parfums_created = 0

        with transaction.atomic():
            for i in range(1, count + 1):
                unique_token = uuid.uuid4().hex[:6].upper()
                marque = random.choice(MARQUES_PARFUMS)
                prefixe = random.choice(PREFIXES_NOMS)
                qualif = random.choice(QUALIFICATIFS)
                nom = f"{prefixe} {qualif} {marque} N°{i}_{unique_token}"
                
                sku = f"SKU-PRF-{i:04d}-{unique_token}"
                contenance = random.choice([30, 50, 75, 100, 120])
                prix_unitaire = Decimal(random.randint(20, 130) * 1000)
                prix_achat = (prix_unitaire * Decimal(random.uniform(0.40, 0.55))).quantize(Decimal("0.01"))
                
                a_promo = (random.random() < 0.25)
                prix_promo = None
                date_debut = None
                date_fin = None
                if a_promo:
                    prix_promo = (prix_unitaire * Decimal("0.85")).quantize(Decimal("0.01"))
                    date_debut = timezone.now() - timedelta(days=2)
                    date_fin = timezone.now() + timedelta(days=45)

                genre = random.choice(["homme", "femme", "mixte"])
                intensite = random.choice(["légère", "moyenne", "forte", "très forte"])
                categorie = random.choice(categories_obj)

                # Liens d'images externes en ligne
                img_princ = random.choice(ONLINE_IMAGE_URLS)
                img_supp1 = random.choice(ONLINE_IMAGE_URLS)
                img_supp2 = random.choice(ONLINE_IMAGE_URLS)
                img_supp3 = random.choice(ONLINE_IMAGE_URLS)

                parfum = Parfum.objects.create(
                    nom=nom,
                    marque=marque,
                    categorie=categorie,
                    reference_sku=sku,
                    duree=random.choice(DUREES_POOL),
                    contenance_ml=contenance,
                    prix_unitaire=prix_unitaire,
                    prix_achat=prix_achat,
                    prix_promotionnel=prix_promo,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    stock_quantite=random.randint(15, 180),
                    seuil_alerte_stock=random.choice([5, 8, 10, 15]),
                    genre_cible=genre,
                    intensite=intensite,
                    notes_tete=random.choice(NOTES_TETE_POOL),
                    notes_coeur=random.choice(NOTES_COEUR_POOL),
                    notes_fond=random.choice(NOTES_FOND_POOL),
                    description_courte=f"Une eau de parfum luxueuse aux accords de {prefixe.lower()} et {qualif.lower()}.",
                    description_longue=(
                        f"Découvrez {nom}, une composition d'exception de la maison {marque}. "
                        f"Conçue pour un sillage inoubliable avec des notes sélectionnées chez les maîtres parfumeurs."
                    ),
                    description_ia=f"Parfum {genre} intense de la maison {marque}, profil {intensite}.",
                    est_nouveau=(random.random() < 0.20),
                    est_bestseller=(random.random() < 0.15),
                    est_hotseller=(random.random() < 0.10),
                    actif=True,
                    image_principale=img_princ,
                    image_supp_1=img_supp1,
                    image_supp_2=img_supp2,
                    image_supp_3=img_supp3,
                )

                # Associations de tags
                for nom_t, valeurs_possibles in tags_def.items():
                    t_obj = tag_instances[nom_t]
                    valeur_tag = random.choice(valeurs_possibles)
                    TagParfum.objects.create(
                        parfum=parfum,
                        tag=t_obj,
                        valeur=valeur_tag
                    )

                parfums_created += 1
                if parfums_created % 50 == 0 or parfums_created == count:
                    self.stdout.write(f"  -> {parfums_created}/{count} Parfums créés...")

        # 4. Génération des Essences
        self.stdout.write(self.style.NOTICE(f"--- Création de {count} Essences ---"))
        essences_created = 0

        with transaction.atomic():
            for j in range(1, count + 1):
                unique_token = uuid.uuid4().hex[:6].upper()
                marque = random.choice(MARQUES_ESSENCES)
                prefixe = random.choice(PREFIXES_NOMS)
                qualif = random.choice(QUALIFICATIFS)
                nom_essence = f"Essence {prefixe} {qualif} Lot-{j}_{unique_token}"
                categorie_essence = random.choice(["super_premium", "premium", "high"])
                code_ref = f"REF-ESS-{j:04d}-{unique_token}"

                prix_ml = Decimal(random.randint(15, 90) * 10)  # 150 à 900 FCFA / ml
                seuil_ml = Decimal(random.choice([50, 100, 150, 200]))

                essence = Essence.objects.create(
                    marque=marque,
                    nom=nom_essence,
                    categorie=categorie_essence,
                    code_reference=code_ref,
                    description=(
                        f"Concentré pur d'essence parfumée {nom_essence}. "
                        f"Extraction raffinée conçue pour les créations sur-mesure et l'aromathèque."
                    ),
                    description_ia=f"Essence pure de haute parfumerie ({categorie_essence}), notes riches.",
                    fournisseur=random.choice(FOURNISSEURS_POOL),
                    origine_pays=random.choice(PAYS_ORIGINE_POOL),
                    concentration_max=Decimal(random.choice(["25.00", "30.00", "35.00", "40.00"])),
                    couleur=random.choice(COULEURS_POOL),
                    duree=random.choice(DUREES_POOL),
                    intensite=random.choice(["légère", "moyenne", "forte", "très forte"]),
                    genre_cible=random.choice(["homme", "femme", "mixte"]),
                    notes_tete=random.choice(NOTES_TETE_POOL),
                    notes_coeur=random.choice(NOTES_COEUR_POOL),
                    notes_fond=random.choice(NOTES_FOND_POOL),
                    prix_par_ml=prix_ml,
                    seuil_alerte_ml=seuil_ml,
                    actif=True,
                )

                # 1 Lot d'essence avec stock laboratoire
                stock_reception = Decimal(random.randint(500, 2500))
                LotEssence.objects.create(
                    essence=essence,
                    stock_ml=stock_reception,
                    quantite_initiale_ml=stock_reception,
                    prix_achat_par_ml=(prix_ml * Decimal("0.45")).quantize(Decimal("0.01")),
                    reference_fournisseur=f"FOURN-{j:04d}-{unique_token}",
                    actif=True
                )

                # Produits finis vendus en boutique (flacons 15ml, 30ml, 50ml)
                for taille in [15, 30, 50]:
                    prix_produit = (prix_ml * Decimal(taille)).quantize(Decimal("0.01"))
                    prix_promo_prod = (prix_produit * Decimal("0.90")).quantize(Decimal("0.01")) if random.random() < 0.20 else None
                    ProduitFiniEssence.objects.create(
                        essence=essence,
                        taille_ml=taille,
                        prix=prix_produit,
                        prix_promotionnel=prix_promo_prod,
                        actif=True
                    )

                # Associations de tags
                for nom_t, valeurs_possibles in tags_def.items():
                    t_obj = tag_instances[nom_t]
                    valeur_tag = random.choice(valeurs_possibles)
                    TagEssence.objects.create(
                        essence=essence,
                        tag=t_obj,
                        valeur=valeur_tag
                    )

                essences_created += 1
                if essences_created % 50 == 0 or essences_created == count:
                    self.stdout.write(f"  -> {essences_created}/{count} Essences créées...")

        self.stdout.write(self.style.SUCCESS(
            f"=== SUCCÈS : {parfums_created} Parfums et {essences_created} Essences créés avec succès (liens d'images externes enregistrés) ! ==="
        ))
