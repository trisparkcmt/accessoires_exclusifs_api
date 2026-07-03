# tests.py
from decimal import Decimal
from io import BytesIO
from PIL import Image as PILImage
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
import tempfile, os
from .utils import get_similar_products

from .models import (
    Tag, Parfum, Essence, Accessoire, Flacon, LotEssence, ProduitFiniEssence,
    CategorieParfum, TypeAccessoire, TypeFlacon
)


# ============================================================
# HELPER — créer une image factice pour les tests
# ============================================================
def creer_image_test(nom='test.jpg', format='JPEG', couleur=(255, 0, 0)):
    """
    Génère une image PNG/JPEG en mémoire pour les tests.
    Évite de créer de vrais fichiers sur le disque.
    """
    img = PILImage.new('RGB', (100, 100), color=couleur)
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return SimpleUploadedFile(nom, buffer.read(), content_type=f'image/{format.lower()}')


# ============================================================
# TESTS IMAGES
# ============================================================
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ParfumImageTest(APITestCase):
    """
    Vérifie que les images sont correctement uploadées
    et que les URLs retournées par l'API sont absolues.
    """

    def setUp(self):
        self.categorie = CategorieParfum.objects.create(
            nom="Oriental", slug="oriental", taux_reduction=0
        )
        self.parfum = Parfum.objects.create(
            nom="Rose Éternelle", slug="rose-eternelle",
            reference_sku="SKU001", contenance_ml=50,
            prix_unitaire=Decimal('25000'),
            categorie=self.categorie, actif=True
        )

    def test_image_nulle_par_defaut(self):
        """Sans image uploadée, image_principale doit être None."""
        response = self.client.get('/api/v1/shop/parfums/rose-eternelle/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['image_principale'])

    def test_url_absolue_retournee(self):
        """Après upload, l'URL retournée doit être absolue (http://...)."""
        self.parfum.image_principale = creer_image_test('rose.jpg')
        self.parfum.save()

        response = self.client.get('/api/v1/shop/parfums/rose-eternelle/')
        self.assertEqual(response.status_code, 200)

        url = response.data['image_principale']
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith('http'))
        self.assertIn('/media/', url)
        self.assertIn('rose-eternelle', url)   # rangé dans le bon dossier

    def tearDown(self):
        """Nettoyage des fichiers créés pendant les tests."""
        import shutil
        if os.path.exists(settings.MEDIA_ROOT):
            shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AccessoireImageTest(APITestCase):

    def setUp(self):
        self.type_diffuseur = TypeAccessoire.objects.create(
            nom="Diffuseur", slug="diffuseur", taux_reduction=0
        )
        self.accessoire = Accessoire.objects.create(
            nom="Diffuseur Bois", slug="diffuseur-bois",
            reference_sku="ACC001",
            type_accessoire=self.type_diffuseur,
            prix_unitaire=Decimal('12000'),
            stock_quantite=10, actif=True
        )

    def test_image_nulle_par_defaut(self):
        response = self.client.get('/api/v1/shop/accessoires/diffuseur-bois/')
        self.assertIsNone(response.data['image_principale'])

    def test_url_absolue_retournee(self):
        self.accessoire.image_principale = creer_image_test('diffuseur.jpg')
        self.accessoire.save()

        response = self.client.get('/api/v1/shop/accessoires/diffuseur-bois/')
        url = response.data['image_principale']
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith('http'))
        self.assertIn('/media/', url)

    def tearDown(self):
        import shutil
        if os.path.exists(settings.MEDIA_ROOT):
            shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)


# ============================================================
# TESTS SIGNALS & RÉDUCTIONS
# ============================================================
class ProduitFiniEssenceStockLotTest(TestCase):
    def setUp(self):
        self.essence = Essence.objects.create(
            marque="Maison Test",
            nom="Oud Royal",
            categorie="premium",
            code_reference="ESS-STOCK-001",
            seuil_alerte_ml=Decimal('50.00'),  # seuil global sur l'essence
        )
        self.lot_ancien = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('100.00'),
        )
        self.lot_recent = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('80.00'),
        )

    def test_creation_preleve_sur_lots_fifo(self):
        ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=30,
            prix=Decimal('5000'),
            stock_disponible=4,
        )
        self.lot_ancien.refresh_from_db()
        self.lot_recent.refresh_from_db()
        self.assertEqual(self.lot_ancien.stock_ml, Decimal('0.00'))
        self.assertEqual(self.lot_recent.stock_ml, Decimal('60.00'))

    def test_mise_a_jour_stock_preleve_variation_seulement(self):
        produit = ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=10,
            prix=Decimal('5000'),
            stock_disponible=2,
        )
        produit.stock_disponible = 5
        produit.save()
        produit.refresh_from_db()
        self.lot_ancien.refresh_from_db()
        self.assertEqual(produit.stock_precedent, 2)
        self.assertEqual(self.lot_ancien.stock_ml, Decimal('50.00'))

    def test_vente_ne_touche_pas_le_lot(self):
        produit = ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=10,
            prix=Decimal('5000'),
            stock_disponible=5,
        )
        self.lot_ancien.refresh_from_db()
        stock_lot_apres_fabrication = self.lot_ancien.stock_ml
        produit.vendre(2)
        self.lot_ancien.refresh_from_db()
        self.assertEqual(self.lot_ancien.stock_ml, stock_lot_apres_fabrication)

    def test_suppression_restitue_stock_restant(self):
        produit = ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=10,
            prix=Decimal('5000'),
            stock_disponible=5,
        )
        produit.delete()
        self.lot_recent.refresh_from_db()
        self.assertEqual(self.lot_recent.stock_ml, Decimal('130.00'))


class ReductionCategorieParfumTest(TestCase):

    def setUp(self):
        self.categorie = CategorieParfum.objects.create(
            nom="Oriental", slug="oriental", taux_reduction=0
        )
        self.parfum_a = Parfum.objects.create(
            nom="Rose Éternelle", slug="rose-eternelle",
            reference_sku="SKU001", contenance_ml=50,
            prix_unitaire=Decimal('25000'),
            categorie=self.categorie, actif=True
        )
        self.parfum_b = Parfum.objects.create(
            nom="Oud Noir", slug="oud-noir",
            reference_sku="SKU002", contenance_ml=100,
            prix_unitaire=Decimal('40000'),
            categorie=self.categorie, actif=True
        )
        self.parfum_manuel = Parfum.objects.create(
            nom="Musc Secret", slug="musc-secret",
            reference_sku="SKU003", contenance_ml=50,
            prix_unitaire=Decimal('20000'),
            prix_promotionnel=Decimal('14000'),
            categorie=self.categorie, actif=True
        )
        self.parfum_inactif = Parfum.objects.create(
            nom="Parfum Archivé", slug="parfum-archive",
            reference_sku="SKU004", contenance_ml=50,
            prix_unitaire=Decimal('15000'),
            categorie=self.categorie, actif=False
        )

    def test_reduction_appliquee_sur_parfums_sans_promo(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.parfum_a.refresh_from_db()
        self.parfum_b.refresh_from_db()
        self.assertEqual(self.parfum_a.prix_promotionnel_effectif, Decimal('20000.00'))
        self.assertEqual(self.parfum_b.prix_promotionnel_effectif, Decimal('32000.00'))

    def test_prix_manuel_prioritaire(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.parfum_manuel.refresh_from_db()
        self.assertEqual(self.parfum_manuel.prix_promotionnel_effectif, Decimal('14000'))

    def test_parfum_inactif_non_touche(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.parfum_inactif.refresh_from_db()
        self.assertIsNone(self.parfum_inactif.prix_promotionnel_effectif)

    def test_reduction_retiree_quand_taux_zero(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.categorie.taux_reduction = Decimal('0')
        self.categorie.save()
        self.parfum_a.refresh_from_db()
        self.assertIsNone(self.parfum_a.prix_promotionnel_effectif)

    def test_prix_manuel_conserve_quand_taux_zero(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.categorie.taux_reduction = Decimal('0')
        self.categorie.save()
        self.parfum_manuel.refresh_from_db()
        self.assertEqual(self.parfum_manuel.prix_promotionnel_effectif, Decimal('14000'))

    def test_changement_de_taux_recalcule(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.categorie.taux_reduction = Decimal('30')
        self.categorie.save()
        self.parfum_a.refresh_from_db()
        self.assertEqual(self.parfum_a.prix_promotionnel_effectif, Decimal('17500.00'))

    def test_meme_taux_ne_declenche_pas_signal(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.parfum_a.refresh_from_db()
        prix_avant = self.parfum_a.prix_promotionnel_effectif
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.parfum_a.refresh_from_db()
        self.assertEqual(self.parfum_a.prix_promotionnel_effectif, prix_avant)

    def test_reduction_categorie_expiree_non_appliquee(self):
        now = timezone.now()
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.date_debut = now - timezone.timedelta(days=3)
        self.categorie.date_fin = now - timezone.timedelta(days=1)
        self.categorie.save()
        self.assertIsNone(self.parfum_a.prix_promotionnel_effectif)


class ReductionTypeAccessoireTest(TestCase):

    def setUp(self):
        self.type_diffuseur = TypeAccessoire.objects.create(
            nom="Diffuseur", slug="diffuseur", taux_reduction=0
        )
        self.accessoire_a = Accessoire.objects.create(
            nom="Diffuseur Bois", slug="diffuseur-bois", reference_sku="ACC001",
            type_accessoire=self.type_diffuseur,
            prix_unitaire=Decimal('12000'), stock_quantite=10, actif=True
        )
        self.accessoire_b = Accessoire.objects.create(
            nom="Diffuseur Métal", slug="diffuseur-metal", reference_sku="ACC002",
            type_accessoire=self.type_diffuseur,
            prix_unitaire=Decimal('18000'), stock_quantite=5, actif=True
        )
        self.accessoire_manuel = Accessoire.objects.create(
            nom="Diffuseur Luxe", slug="diffuseur-luxe", reference_sku="ACC003",
            type_accessoire=self.type_diffuseur,
            prix_unitaire=Decimal('30000'), prix_promotionnel=Decimal('20000'),
            stock_quantite=3, actif=True
        )

    def test_reduction_appliquee_sur_accessoires(self):
        self.type_diffuseur.taux_reduction = Decimal('15')
        self.type_diffuseur.save()
        self.accessoire_a.refresh_from_db()
        self.accessoire_b.refresh_from_db()
        self.assertEqual(self.accessoire_a.prix_promotionnel_effectif, Decimal('10200.00'))
        self.assertEqual(self.accessoire_b.prix_promotionnel_effectif, Decimal('15300.00'))

    def test_prix_manuel_accessoire_prioritaire(self):
        self.type_diffuseur.taux_reduction = Decimal('15')
        self.type_diffuseur.save()
        self.accessoire_manuel.refresh_from_db()
        self.assertEqual(self.accessoire_manuel.prix_promotionnel_effectif, Decimal('20000'))

    def test_reduction_retiree_accessoire(self):
        self.type_diffuseur.taux_reduction = Decimal('15')
        self.type_diffuseur.save()
        self.type_diffuseur.taux_reduction = Decimal('0')
        self.type_diffuseur.save()
        self.accessoire_a.refresh_from_db()
        self.assertIsNone(self.accessoire_a.prix_promotionnel_effectif)

    def test_prix_manuel_accessoire_conserve_apres_zero(self):
        self.type_diffuseur.taux_reduction = Decimal('15')
        self.type_diffuseur.save()
        self.type_diffuseur.taux_reduction = Decimal('0')
        self.type_diffuseur.save()
        self.accessoire_manuel.refresh_from_db()
        self.assertEqual(self.accessoire_manuel.prix_promotionnel_effectif, Decimal('20000'))


# ============================================================
# TESTS API — PROMOTION
# ============================================================
class ParfumPromotionAPITest(APITestCase):

    def setUp(self):
        self.categorie = CategorieParfum.objects.create(
            nom="Oriental", slug="oriental", taux_reduction=0
        )
        self.parfum = Parfum.objects.create(
            nom="Rose Éternelle", slug="rose-eternelle",
            reference_sku="SKU001", contenance_ml=50,
            prix_unitaire=Decimal('25000'),
            categorie=self.categorie, actif=True
        )

    def test_pas_de_promotion_par_defaut(self):
        response = self.client.get('/api/v1/shop/parfums/rose-eternelle/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['en_promotion'])
        self.assertIsNone(response.data['taux_reduction'])
        self.assertEqual(response.data['prix_actuel'], '25000.00')

    def test_promotion_appliquee_via_categorie(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        self.parfum.refresh_from_db()
        response = self.client.get('/api/v1/shop/parfums/rose-eternelle/')
        self.assertTrue(response.data['en_promotion'])
        self.assertEqual(float(response.data['taux_reduction']), 20.0)
        self.assertEqual(response.data['prix_actuel'], '20000.00')

    def test_prix_unitaire_inchange(self):
        self.categorie.taux_reduction = Decimal('20')
        self.categorie.save()
        response = self.client.get('/api/v1/shop/parfums/rose-eternelle/')
        self.assertEqual(response.data['prix_unitaire'], '25000.00')
        self.assertEqual(response.data['prix_actuel'],   '20000.00')


class AccessoirePromotionAPITest(APITestCase):

    def setUp(self):
        self.type_diffuseur = TypeAccessoire.objects.create(
            nom="Diffuseur", slug="diffuseur", taux_reduction=0
        )
        self.accessoire = Accessoire.objects.create(
            nom="Diffuseur Bois", slug="diffuseur-bois", reference_sku="ACC001",
            type_accessoire=self.type_diffuseur,
            prix_unitaire=Decimal('12000'), stock_quantite=10, actif=True
        )

    def test_pas_de_promotion_par_defaut(self):
        response = self.client.get('/api/v1/shop/accessoires/diffuseur-bois/')
        self.assertFalse(response.data['en_promotion'])
        self.assertIsNone(response.data['taux_reduction'])

    def test_promotion_appliquee_via_type(self):
        self.type_diffuseur.taux_reduction = Decimal('15')
        self.type_diffuseur.save()
        self.accessoire.refresh_from_db()
        response = self.client.get('/api/v1/shop/accessoires/diffuseur-bois/')
        self.assertTrue(response.data['en_promotion'])
        self.assertEqual(float(response.data['taux_reduction']), 15.0)
        self.assertEqual(response.data['prix_actuel'], '10200.00')


class PromotionEndpointAPITest(APITestCase):
    def setUp(self):
        self.categorie = CategorieParfum.objects.create(
            nom="Oriental",
            slug="oriental-promo",
            taux_reduction=Decimal('20'),
            message_promotion="Offre spéciale",
        )
        self.parfum = Parfum.objects.create(
            nom="Rose Promo",
            slug="rose-promo",
            reference_sku="SKU-PROMO-001",
            contenance_ml=50,
            prix_unitaire=Decimal('25000'),
            categorie=self.categorie,
            actif=True,
        )
        self.type_accessoire = TypeAccessoire.objects.create(
            nom="Diffuseur Promo",
            slug="diffuseur-promo",
            taux_reduction=Decimal('10'),
            message_promotion="Semaine diffuseur",
        )
        self.accessoire = Accessoire.objects.create(
            nom="Diffuseur Promo",
            slug="diffuseur-promo-item",
            reference_sku="ACC-PROMO-001",
            type_accessoire=self.type_accessoire,
            prix_unitaire=Decimal('10000'),
            stock_quantite=5,
            actif=True,
        )

    def test_endpoint_promotions_unifie_et_trie(self):
        response = self.client.get('/api/v1/shop/promotions/')
        self.assertEqual(response.status_code, 200)
        resultats = response.data['resultats']
        self.assertEqual(len(resultats), 2)
        self.assertEqual(resultats[0]['type_article'], 'parfum')
        self.assertEqual(resultats[0]['message_promotion'], 'Offre spéciale')
        self.assertEqual(float(resultats[0]['taux_reduction']), 20.0)
        self.assertEqual(resultats[1]['type_article'], 'accessoire')
        self.assertEqual(resultats[1]['message_promotion'], 'Semaine diffuseur')


# ============================================================
# TESTS API EXISTANTS
# ============================================================
class ParfumAPITest(APITestCase):

    def setUp(self):
        self.categorie   = CategorieParfum.objects.create(nom="Oriental", slug="oriental")
        self.tag_floral  = Tag.objects.create(nom="Floral",     type="famille_olfactive")
        self.tag_boise   = Tag.objects.create(nom="Boisé",      type="famille_olfactive")
        self.tag_ete     = Tag.objects.create(nom="Été",        type="saison")
        self.tag_romance = Tag.objects.create(nom="Romantique", type="humeur")
        self.parfum_visible = Parfum.objects.create(
            nom="Rose Éternelle", slug="rose-eternelle",
            reference_sku="SKU001", contenance_ml=50,
            prix_unitaire=25000, categorie=self.categorie, actif=True
        )
        self.parfum_visible.tags.add(self.tag_floral, self.tag_ete, self.tag_romance)
        self.parfum_cache = Parfum.objects.create(
            nom="Parfum Secret", slug="parfum-secret",
            reference_sku="SKU002", contenance_ml=50,
            prix_unitaire=15000, categorie=self.categorie, actif=False
        )

    def test_liste_parfums_actifs_uniquement(self):
        response = self.client.get('/api/v1/shop/parfums/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['resultats']), 1)

    def test_parfum_inactif_invisible(self):
        response = self.client.get(f'/api/v1/shop/parfums/{self.parfum_cache.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_detail_parfum_par_slug(self):
        response = self.client.get(f'/api/v1/shop/parfums/{self.parfum_visible.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['nom'], "Rose Éternelle")

    def test_slug_inexistant_retourne_404(self):
        response = self.client.get('/api/v1/shop/parfums/slug-inexistant/')
        self.assertEqual(response.status_code, 404)

    def test_filtre_par_famille_olfactive(self):
        response = self.client.get('/api/v1/shop/parfums/?famille_olfactive=Floral')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/shop/parfums/?famille_olfactive=Boisé')
        self.assertEqual(response_vide.data['count'], 0)

    def test_filtre_par_saison(self):
        response = self.client.get('/api/v1/shop/parfums/?saison=Été')
        self.assertEqual(response.data['count'], 1)

    def test_filtre_par_humeur(self):
        response = self.client.get('/api/v1/shop/parfums/?humeur=Romantique')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/shop/parfums/?humeur=Triste')
        self.assertEqual(response_vide.data['count'], 0)

    def test_filtre_prix_max_excluant(self):
        response = self.client.get('/api/v1/shop/parfums/?prix_max=20000')
        self.assertEqual(response.data['count'], 0)

    def test_filtre_prix_dans_fourchette(self):
        response = self.client.get('/api/v1/shop/parfums/?prix_min=20000&prix_max=30000')
        self.assertEqual(response.data['count'], 1)

    def test_filtre_prix_min_excluant(self):
        response = self.client.get('/api/v1/shop/parfums/?prix_min=30000')
        self.assertEqual(response.data['count'], 0)

    def test_structure_pagination(self):
        response = self.client.get('/api/v1/shop/parfums/')
        self.assertIn('count',         response.data)
        self.assertIn('pages',         response.data)
        self.assertIn('page_actuelle', response.data)
        self.assertIn('suivant',       response.data)
        self.assertIn('precedent',     response.data)
        self.assertIn('resultats',     response.data)

    def test_recherche_textuelle(self):
        response = self.client.get('/api/v1/shop/parfums/?search=Rose')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/shop/parfums/?search=Inexistant')
        self.assertEqual(response_vide.data['count'], 0)


class EssenceAPITest(APITestCase):

    def setUp(self):
        self.tag_floral = Tag.objects.create(nom="Floral", type="famille_olfactive")
        self.tag_lion   = Tag.objects.create(nom="Lion",   type="signe_astrologique")
        self.essence_active = Essence.objects.create(
            marque="Maison Test", nom="Oud Royal", code_reference="ESS001",
            categorie="premium", prix_par_ml=Decimal('500.00'), actif=True
        )
        self.essence_active.tags.add(self.tag_floral, self.tag_lion)
        self.essence_inactive = Essence.objects.create(
            marque="Maison Test", nom="Musc Blanc", code_reference="ESS002",
            categorie="premium", prix_par_ml=Decimal('300.00'), actif=False
        )

    def test_liste_essences_actives_uniquement(self):
        response = self.client.get('/api/v1/lab/essences/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['resultats']), 1)

    def test_essence_inactive_invisible(self):
        response = self.client.get(f'/api/v1/lab/essences/{self.essence_inactive.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_filtre_par_signe_astrologique(self):
        response = self.client.get('/api/v1/lab/essences/?signe_astrologique=Lion')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/lab/essences/?signe_astrologique=Verseau')
        self.assertEqual(response_vide.data['count'], 0)

    def test_filtre_par_prix(self):
        response = self.client.get('/api/v1/lab/essences/?prix_min=400&prix_max=600')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/lab/essences/?prix_max=100')
        self.assertEqual(response_vide.data['count'], 0)


class AccessoireAPITest(APITestCase):

    def setUp(self):
        self.type_diffuseur = TypeAccessoire.objects.create(nom="Diffuseur", slug="diffuseur")
        self.type_bougie    = TypeAccessoire.objects.create(nom="Bougie",    slug="bougie")
        self.accessoire_actif = Accessoire.objects.create(
            nom="Diffuseur Bois", slug="diffuseur-bois", reference_sku="ACC001",
            type_accessoire=self.type_diffuseur, prix_unitaire=12000,
            stock_quantite=20, seuil_alerte_stock=3, actif=True
        )
        self.accessoire_inactif = Accessoire.objects.create(
            nom="Bougie Vanille", slug="bougie-vanille", reference_sku="ACC002",
            type_accessoire=self.type_bougie, prix_unitaire=8000,
            stock_quantite=0, seuil_alerte_stock=3, actif=False
        )

    def test_liste_accessoires_actifs_uniquement(self):
        response = self.client.get('/api/v1/shop/accessoires/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['resultats']), 1)

    def test_detail_par_slug(self):
        response = self.client.get(f'/api/v1/shop/accessoires/{self.accessoire_actif.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['nom'], "Diffuseur Bois")

    def test_filtre_par_type_id(self):
        response = self.client.get(f'/api/v1/shop/accessoires/?type_accessoire={self.type_diffuseur.pk}')
        self.assertEqual(response.data['count'], 1)

    def test_filtre_par_type_nom(self):
        response = self.client.get('/api/v1/shop/accessoires/?type_nom=Diffuseur')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/shop/accessoires/?type_nom=Inexistant')
        self.assertEqual(response_vide.data['count'], 0)

    def test_filtre_par_prix(self):
        response = self.client.get('/api/v1/shop/accessoires/?prix_min=10000&prix_max=15000')
        self.assertEqual(response.data['count'], 1)
        response_vide = self.client.get('/api/v1/shop/accessoires/?prix_max=5000')
        self.assertEqual(response_vide.data['count'], 0)

    def test_filtre_en_stock(self):
        response = self.client.get('/api/v1/shop/accessoires/?en_stock=true')
        self.assertEqual(response.data['count'], 1)


class FlaconAPITest(APITestCase):

    def setUp(self):
        self.type_spray = TypeFlacon.objects.create(nom="Spray",   actif=True)
        self.type_roll  = TypeFlacon.objects.create(nom="Roll-on", actif=True)
        self.flacon_actif = Flacon.objects.create(
            nom="Flacon Spray 50ml", reference_sku="FLA001",
            type_flacon=self.type_spray, contenance_ml=50,
            prix_unitaire=3500, stock_quantite=30, seuil_alerte_stock=5, actif=True
        )
        self.flacon_rupture = Flacon.objects.create(
            nom="Flacon Roll-on 10ml", reference_sku="FLA002",
            type_flacon=self.type_roll, contenance_ml=10,
            prix_unitaire=1500, stock_quantite=2, seuil_alerte_stock=5, actif=True
        )
        self.flacon_inactif = Flacon.objects.create(
            nom="Vieux Flacon", reference_sku="FLA003",
            type_flacon=self.type_spray, contenance_ml=100,
            prix_unitaire=5000, stock_quantite=10, seuil_alerte_stock=5, actif=False
        )

    def test_liste_flacons_actifs_uniquement(self):
        response = self.client.get('/api/v1/shop/flacons/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['resultats']), 2)

    def test_filtre_par_type_id(self):
        response = self.client.get(f'/api/v1/shop/flacons/?type_flacon={self.type_spray.pk}')
        self.assertEqual(response.data['count'], 1)

    def test_filtre_par_contenance_exacte(self):
        response = self.client.get('/api/v1/shop/flacons/?contenance_ml=50')
        self.assertEqual(response.data['count'], 1)

    def test_filtre_par_plage_contenance(self):
        response = self.client.get('/api/v1/shop/flacons/?contenance_min=10&contenance_max=50')
        self.assertEqual(response.data['count'], 2)
        response_vide = self.client.get('/api/v1/shop/flacons/?contenance_min=200')
        self.assertEqual(response_vide.data['count'], 0)

    def test_filtre_stock_min(self):
        response = self.client.get('/api/v1/shop/flacons/?stock_min=10')
        self.assertEqual(response.data['count'], 1)

    def test_filtre_en_stock(self):
        response = self.client.get('/api/v1/shop/flacons/?en_stock=true')
        self.assertEqual(response.data['count'], 1)
        response_rupture = self.client.get('/api/v1/shop/flacons/?en_stock=false')
        self.assertEqual(response_rupture.data['count'], 1)


class SimilarProductsUtilsTest(TestCase):
    def setUp(self):
        self.cat = CategorieParfum.objects.create(nom="Test", slug="test")
        self.tag_floral = Tag.objects.create(nom="Floral", type="famille_olfactive")
        self.tag_boise  = Tag.objects.create(nom="Boisé", type="famille_olfactive")
        self.tag_oriental = Tag.objects.create(nom="Oriental", type="famille_olfactive")

        # Parfum A : floral + boisé
        self.p1 = Parfum.objects.create(
            nom="Rose", slug="rose", reference_sku="P1",
            contenance_ml=50, prix_unitaire=10000,
            categorie=self.cat, actif=True
        )
        self.p1.tags.add(self.tag_floral, self.tag_boise)

        # Parfum B : floral + boisé (identique)
        self.p2 = Parfum.objects.create(
            nom="Jasmin", slug="jasmin", reference_sku="P2",
            contenance_ml=50, prix_unitaire=12000,
            categorie=self.cat, actif=True
        )
        self.p2.tags.add(self.tag_floral, self.tag_boise)

        # Parfum C : boisé seulement
        self.p3 = Parfum.objects.create(
            nom="Cèdre", slug="cedre", reference_sku="P3",
            contenance_ml=50, prix_unitaire=9000,
            categorie=self.cat, actif=True
        )
        self.p3.tags.add(self.tag_boise)

        # Parfum D : aucun tag commun
        self.p4 = Parfum.objects.create(
            nom="Vanille", slug="vanille", reference_sku="P4",
            contenance_ml=50, prix_unitaire=11000,
            categorie=self.cat, actif=True
        )
        self.p4.tags.add(self.tag_oriental)

        # Parfum inactif (ne doit pas remonter)
        self.p5 = Parfum.objects.create(
            nom="Inactif", slug="inactif", reference_sku="P5",
            contenance_ml=50, prix_unitaire=5000,
            categorie=self.cat, actif=False
        )
        self.p5.tags.add(self.tag_floral)

    def test_similarites_par_tags(self):
        # Pour p1, on doit trouver p2 (2 tags communs) et p3 (1 tag commun)
        similaires = get_similar_products(self.p1, Parfum, limit=4)
        self.assertEqual(len(similaires), 2)
        self.assertEqual(similaires[0], self.p2)  # p2 a plus de tags communs
        self.assertEqual(similaires[1], self.p3)

    def test_pas_d_auto_inclusion(self):
        similaires = get_similar_products(self.p1, Parfum, limit=4)
        self.assertNotIn(self.p1, similaires)

    def test_pas_de_tags_communs(self):
        similaires = get_similar_products(self.p4, Parfum, limit=4)
        self.assertEqual(len(similaires), 0)

    def test_produit_sans_tag(self):
        p_sans_tag = Parfum.objects.create(
            nom="Sans tag", slug="sans-tag", reference_sku="P6",
            contenance_ml=30, prix_unitaire=8000,
            categorie=self.cat, actif=True
        )
        similaires = get_similar_products(p_sans_tag, Parfum, limit=4)
        self.assertEqual(len(similaires), 0)

    def test_limit_max(self):
        # Créer 6 parfums avec tag floral
        for i in range(6):
            p = Parfum.objects.create(
                nom=f"Test{i}", slug=f"test{i}", reference_sku=f"P7{i}",
                contenance_ml=50, prix_unitaire=10000,
                categorie=self.cat, actif=True
            )
            p.tags.add(self.tag_floral)
        similaires = get_similar_products(self.p1, Parfum, limit=4)
        self.assertEqual(len(similaires), 4)


class UnifiedSalesAPITest(APITestCase):
    def setUp(self):
        from catalogue.models import CategorieParfum, Parfum, Accessoire, TypeAccessoire, ProduitFiniEssence, Essence
        self.cat = CategorieParfum.objects.create(nom="Test Cat", slug="test-cat")
        self.type_acc = TypeAccessoire.objects.create(nom="Test Type", slug="test-type")
        self.essence = Essence.objects.create(nom="Test Essence", marque="Brand", code_reference="ESS-TEST")
        self.lot = LotEssence.objects.create(essence=self.essence, stock_ml=1000.00)

        self.parfum = Parfum.objects.create(
            nom="Parfum Test", slug="parfum-test", reference_sku="PARF-1",
            contenance_ml=50, prix_unitaire=10000, stock_quantite=10,
            categorie=self.cat, actif=True
        )

        self.accessoire = Accessoire.objects.create(
            nom="Accessoire Test", slug="accessoire-test", reference_sku="ACC-1",
            type_accessoire=self.type_acc, prix_unitaire=5000, stock_quantite=10,
            actif=True
        )

        self.produit_essence = ProduitFiniEssence.objects.create(
            essence=self.essence, taille_ml=30, prix=3000, stock_disponible=10,
            actif=True
        )

        from orders.models import Commande, CommandeLigneParfum, CommandeLigneAccessoire, CommandeProduitFiniEssence
        self.cmd = Commande.objects.create(
            sous_total=18000,
            total_ttc=18000, statut='en_cours',
            livraison_nom_complet="Test User", livraison_telephone="+22501020304"
        )

        CommandeLigneParfum.objects.create(
            commande=self.cmd, parfum=self.parfum, quantite=5,
            prix_unitaire_snapshot=10000, sous_total=50000
        )

        CommandeLigneAccessoire.objects.create(
            commande=self.cmd, accessoire=self.accessoire, quantite=3,
            prix_unitaire_snapshot=5000, sous_total=15000
        )

        CommandeProduitFiniEssence.objects.create(
            commande=self.cmd, produit_fini_essence=self.produit_essence, quantite=2,
            prix_unitaire_snapshot=3000, sous_total=6000
        )

    def test_bestsellers_unified(self):
        response = self.client.get('/api/v1/shop/bestsellers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(response.data[0]['type_article'], 'parfum')
        self.assertEqual(response.data[0]['ventes'], 5)
        self.assertEqual(response.data[1]['type_article'], 'accessoire')
        self.assertEqual(response.data[1]['ventes'], 3)
        self.assertEqual(response.data[2]['type_article'], 'produit_essence')
        self.assertEqual(response.data[2]['ventes'], 2)

    def test_hotsellers_unified(self):
        response = self.client.get('/api/v1/shop/hotsellers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(response.data[0]['type_article'], 'parfum')
        self.assertEqual(response.data[0]['ventes'], 5)


# ============================================================
# TESTS ALERTES SEUIL GLOBAL ESSENCE
# ============================================================
class EssenceAlertStockTest(TestCase):
    """Valide la logique de seuil d'alerte global au niveau de l'essence."""

    def setUp(self):
        from catalogue.models import NotificationCatalogue
        NotificationCatalogue.objects.all().delete()
        self.essence = Essence.objects.create(
            marque="Test",
            nom="Oud Test",
            categorie="premium",
            code_reference="ESS-ALERT-001",
            seuil_alerte_ml=Decimal('100.00'),
        )
        # Le stock total est 150 ml (au-dessus du seuil de 100 ml)
        self.lot1 = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('100.00'),
        )
        self.lot2 = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('50.00'),
        )

    def test_stock_total_au_dessus_du_seuil(self):
        """Aucune notification ne doit exister si le stock total > seuil."""
        from catalogue.models import NotificationCatalogue
        self.assertEqual(self.essence.stock_total_ml(), Decimal('150.00'))
        count = NotificationCatalogue.objects.filter(
            type_produit='essence', product_id=self.essence.id
        ).count()
        self.assertEqual(count, 0)

    def test_alerte_declenchee_quand_stock_franchit_seuil(self):
        """Une notification doit être créée quand le stock total passe sous le seuil."""
        from catalogue.models import NotificationCatalogue
        NotificationCatalogue.objects.all().delete()
        # On réduit lot1 pour faire passer le total sous le seuil (150→80)
        self.lot1.stock_ml = Decimal('30.00')
        self.lot1.save()
        self.assertEqual(self.essence.stock_total_ml(), Decimal('80.00'))
        count = NotificationCatalogue.objects.filter(
            type_produit='essence', product_id=self.essence.id
        ).count()
        self.assertGreaterEqual(count, 1)

    def test_pas_de_double_notification_si_deja_sous_seuil(self):
        """Si le stock était déjà sous le seuil avant la modification, pas de nouvelle alerte."""
        from catalogue.models import NotificationCatalogue
        # Franchir le seuil une première fois
        self.lot1.stock_ml = Decimal('30.00')
        self.lot1.save()
        count_after_first = NotificationCatalogue.objects.filter(
            type_produit='essence', product_id=self.essence.id
        ).count()
        # Réduire encore (total reste sous seuil : pas de nouveau franchissement)
        self.lot2.stock_ml = Decimal('45.00')  # total : 30+45=75, toujours sous 100
        self.lot2.save()
        count_after_second = NotificationCatalogue.objects.filter(
            type_produit='essence', product_id=self.essence.id
        ).count()
        self.assertEqual(count_after_first, count_after_second)

    def test_alerte_si_seuil_mis_a_jour_au_dessus_stock(self):
        """Si le seuil est augmenté au-dessus du stock actuel, une alerte doit être créée."""
        from catalogue.models import NotificationCatalogue
        NotificationCatalogue.objects.all().delete()
        # Stock total = 150 ml → on monte le seuil à 200 ml
        self.essence.seuil_alerte_ml = Decimal('200.00')
        self.essence.save()
        count = NotificationCatalogue.objects.filter(
            type_produit='essence', product_id=self.essence.id
        ).count()
        self.assertGreaterEqual(count, 1)

    def test_propriete_stock_insuffisant_sur_lot(self):
        """La propriété stock_insuffisant sur LotEssence doit refléter le seuil global."""
        # Stock total = 150 ml, seuil = 100 ml → suffisant
        self.assertFalse(self.lot1.stock_insuffisant)
        # On réduit le total sous le seuil
        self.lot1.stock_ml = Decimal('30.00')
        self.lot1.save()
        self.lot1.refresh_from_db()
        # Total = 80 ml < 100 ml → insuffisant
        self.assertTrue(self.lot1.stock_insuffisant)
