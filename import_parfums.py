#!/usr/bin/env python3
import os
import sys
import django
from decimal import Decimal

# Configuration de l'environnement Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from catalogue.models import Parfum, CategorieParfum
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
    for cat_name in ["MARQUE", "DUPE"]:
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
    categories = get_or_create_categories()
    cat_marque = categories["MARQUE"]
    cat_dupe = categories["DUPE"]

    parfums_data = [
        # 4. Paris Corner – Shahaf : Oud Tonka
        {
            "sku": "PARFUM-PC-SHAHAF-004",
            "nom": "Shahaf : Oud Tonka",
            "marque": "Paris Corner",
            "categorie": cat_marque, # Original / Inspiration Niche
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
        # 5. Fragrance World – Invicto Absolu
        {
            "sku": "PARFUM-FW-INVICTO-005",
            "nom": "INVICTO ABSOLU",
            "marque": "Fragrance World",
            "categorie": cat_dupe, # Clone (Inspiré d'Invictus Victory Absolu)
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
        # 6. Maison Alhambra – Le Secret de Séduction de la Rose
        {
            "sku": "PARFUM-MA-ROSE-006",
            "nom": "Le secret de séduction de la rose",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe, # Clone (Inspiré de Rose Prick)
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
        # 7. Chanel – Bleu de Chanel
        {
            "sku": "PARFUM-CH-BLEU-007",
            "nom": "Bleu de Chanel",
            "marque": "Chanel",
            "categorie": cat_marque, # Original Designer
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
        # 8. Lattafa – Raghba pour Homme
        {
            "sku": "PARFUM-LA-RAGHBA-008",
            "nom": "Raghba pour Homme",
            "marque": "Lattafa",
            "categorie": cat_dupe, # Clone (Inspiré de Green Irish Tweed)
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
        # 9. Lattafa – KHAMRAH
        {
            "sku": "PARFUM-LA-KHAMRAH-009",
            "nom": "KHAMRAH",
            "marque": "Lattafa",
            "categorie": cat_marque, # Original / Inspiration Angels' Share
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
        # 10. Leonard – Cuir Ambre
        {
            "sku": "PARFUM-LE-CUIRAMBRE-010",
            "nom": "Cuir Ambre",
            "marque": "Leonard Paris",
            "categorie": cat_marque, # Original
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
        # 11. Lattafa – Hayaati Rose
        {
            "sku": "PARFUM-LA-HAYAATIROSE-011",
            "nom": "Hayaati Rose",
            "marque": "Lattafa",
            "categorie": cat_marque, # Original
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
        # 12. Maison Alhambra – Kismet For Men
        {
            "sku": "PARFUM-MA-KISMET-012",
            "nom": "Kismet For Men",
            "marque": "Maison Alhambra",
            "categorie": cat_dupe, # Clone (Inspiré de Tuxedo YSL)
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
        # 13. Pascal Morabito – Rose Édition Oud
        {
            "sku": "PARFUM-PM-ROSEOUD-013",
            "nom": "Rose Édition Oud",
            "marque": "Pascal Morabito",
            "categorie": cat_marque, # Original
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
        # 14. Tom Ford – Oud Wood
        {
            "sku": "PARFUM-TF-OUDWOOD-014",
            "nom": "Oud Wood",
            "marque": "Tom Ford",
            "categorie": cat_marque, # Original Niche
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
        # 15. Zara – Red Temptation
        {
            "sku": "PARFUM-ZA-REDTEMPT-015",
            "nom": "Red Temptation",
            "marque": "Zara",
            "categorie": cat_dupe, # Clone (Baccarat Rouge 540)
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
        # 16. Zara – Tender Amber
        {
            "sku": "PARFUM-ZA-TENDERAMBER-016",
            "nom": "Tender Amber",
            "marque": "Zara",
            "categorie": cat_dupe, # Clone (Erba Pura / Kirkè)
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
        # 17. Hugo Boss – Boss Bottled Night
        {
            "sku": "PARFUM-HB-BOSSNIGHT-017",
            "nom": "Boss Bottled Night",
            "marque": "Hugo Boss",
            "categorie": cat_marque, # Original Designer
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
        # 18. Lattafa – Proud Of You
        {
            "sku": "PARFUM-LA-PROUDOFYOU-018",
            "nom": "Proud Of You",
            "marque": "Lattafa",
            "categorie": cat_dupe, # Clone (Stronger With You)
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
        }
    ]

    print("\n--- Importation des parfums dans la base de données ---")
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
