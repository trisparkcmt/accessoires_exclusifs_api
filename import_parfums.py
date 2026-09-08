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
        # --- PARFUMS 4 À 18 ---
        # 4. Paris Corner – Shahaf : Oud Tonka
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
        # 5. Fragrance World – Invicto Absolu
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
        # 6. Maison Alhambra – Le Secret de Séduction de la Rose
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
        # 7. Chanel – Bleu de Chanel
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
        # 8. Lattafa – Raghba pour Homme
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
        # 9. Lattafa – KHAMRAH
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
        # 10. Leonard – Cuir Ambre
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
        # 11. Lattafa – Hayaati Rose
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
        # 12. Maison Alhambra – Kismet For Men
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
        # 13. Pascal Morabito – Rose Édition Oud
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
        # 14. Tom Ford – Oud Wood
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
        # 15. Zara – Red Temptation
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
        # 16. Zara – Tender Amber
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
        # 17. Hugo Boss – Boss Bottled Night
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
        # 18. Lattafa – Proud Of You
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
        # 19. Iris Patchouli
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
        # 20. Fiero Blue Man
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
        # 21. Homme Authentique : Geovany
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
        # 22. Hamdaan
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
        # 23. L'Unique Explorer
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
        # 24. Noble Black
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
        # 25. Oud de Minuit
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
        # 26. Scandale (Pour Femme)
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
        # 27. Ambre et Néroli
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
        # 28. Hommes Intenses
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
        # 29. Paris Corner – Khair Pistachio
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
        # 30. Maison Alhambra – Jean Lowe Matière
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
        # 31. Maison Alhambra – Ombre Nomade Fab-lab
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
        # 32. Lattafa – Asad Bourbon
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
        # 33. Lattafa – Éclair
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
        # 34. Zara – Rose Gourmand
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
        # 35. Zara – Golden Decade (Ruby)
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
        # 36. Zara – Vibrant Leather Oud
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
        # 37. Fragrance World – Suave Le Parfum
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
        # 38. Lattafa – Raghba (Classique)
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
        # 39. Fragrance World – Sceptre Bronzite
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
        # 40. Lattafa – Hayaati Royale
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
        # 41. Montale – Black Aoud
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
        # 42. Lattafa – Yara (Rose)
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
        # 43. Christian Dior – Sauvage
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
        # 44. Paris Corner – Khair Fusion
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
        # 45. Fragrance World – Oniro
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
        # 46. Paris Corner – Ka-Ly Libre Intense
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
        # 47. Lattafa – Mazaaji
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
        # 48. Azzaro – Azzaro Pour Homme
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
        # 49. Paris Corner – Khair Confection
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
        # 50. Mauboussin – Mauboussin Pour Lui
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
        }
    ]

    print("\n--- Importation des parfums 4 à 50 dans la base de données ---")
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
