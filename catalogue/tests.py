# tests.py
from decimal import Decimal
from io import BytesIO
from PIL import Image as PILImage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
import tempfile, os
from .utils import get_similar_products

from .models import (
    Tag, TagParfum, Parfum, Essence, Accessoire, Flacon, LotEssence, ProduitFiniEssence, Favori,
    CategorieParfum, TypeAccessoire, TypeFlacon, Ingredient, EntrepriseInfo
)
from utilisateur.models import Serveuse


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


class EntrepriseInfoApiTest(APITestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_user(
            username='admin-entreprise',
            email='admin-entreprise@example.com',
            password='test1234',
            is_staff=True,
        )
        self.client.force_authenticate(self.admin_user)
        self.entreprise = EntrepriseInfo.objects.create(
            nom='Accessoires Exclusif',
            jours_ouverture=[
                {'jour': 'Lundi', 'ouvert': True, 'heure_ouverture': '09:00', 'heure_fermeture': '18:00'},
                {'jour': 'Mardi', 'ouvert': True, 'heure_ouverture': '09:00', 'heure_fermeture': '18:00'},
                {'jour': 'Mercredi', 'ouvert': False, 'heure_ouverture': None, 'heure_fermeture': None, 'note': 'Fermé'}
            ],
            telephone_principal='+2250700000000',
            whatsapp='+2250700000001',
            facebook_url='https://facebook.com/accessoiresexclusif',
            instagram_url='https://instagram.com/accessoiresexclusif',
            localisation='Abidjan, Côte d\'Ivoire',
        )

    def test_get_is_public(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/shop/infos-entreprise/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['nom'], 'Accessoires Exclusif')

    def test_non_admin_cannot_create(self):
        user = get_user_model().objects.create_user(
            username='simple-user',
            email='simple-user@example.com',
            password='test1234',
        )
        self.client.force_authenticate(user)
        response = self.client.post('/api/v1/shop/infos-entreprise/', {
            'nom': 'Nouvelle entreprise',
            'jours_ouverture': ['Vendredi'],
            'telephone_principal': '+2250700000002',
            'localisation': 'Yopougon',
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_patch(self):
        response = self.client.patch('/api/v1/shop/infos-entreprise/1/', {
            'nom': 'Accessoires Exclusif Updated',
            'localisation': 'Plateau, Abidjan',
            'jours_ouverture': [
                {'jour': 'Vendredi', 'ouvert': True, 'heure_ouverture': '10:00', 'heure_fermeture': '19:00'},
                {'jour': 'Samedi', 'ouvert': False, 'heure_ouverture': None, 'heure_fermeture': None, 'note': 'Fermé'}
            ],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.entreprise.refresh_from_db()
        self.assertEqual(self.entreprise.nom, 'Accessoires Exclusif Updated')
        self.assertEqual(self.entreprise.jours_ouverture[0]['jour'], 'Vendredi')
        self.assertFalse(self.entreprise.jours_ouverture[1]['ouvert'])


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
            prix_unitaire=Decimal('25000'), stock_quantite=10,
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
        self.assertTrue('/media/' in url or 'amazonaws.com' in url or 'cloudfront.net' in url)
        self.assertIn('rose-eternelle', url)   # rangé dans le bon dossier

    def test_conversion_automatique_en_webp(self):
        """Une image JPG/PNG uploadée doit être automatiquement convertie en WebP."""
        self.parfum.image_principale = creer_image_test('flacon_luxe.jpg', format='JPEG')
        self.parfum.save()

        self.parfum.refresh_from_db()
        self.assertTrue(self.parfum.image_principale.name.endswith('.webp'))

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
        self.assertTrue('/media/' in url or 'amazonaws.com' in url or 'cloudfront.net' in url)

    def tearDown(self):
        import shutil
        if os.path.exists(settings.MEDIA_ROOT):
            shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)


# ============================================================
# TESTS SIGNALS & RÉDUCTIONS
# ============================================================
class ProduitFiniEssenceFavoriTest(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='favori-produit-fini',
            email='favori-produit-fini@example.com',
            password='test1234',
            telephone='+1234567892',
        )
        self.essence = Essence.objects.create(
            marque='Maison Test',
            nom='Rose de Nuit',
            categorie='premium',
            code_reference='ESS-FAV-001',
            actif=True,
        )
        self.produit = ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=30,
            prix=Decimal('15000.00'),
            actif=True,
        )
        self.lot = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('100.00'),
            actif=True,
        )

    def test_toggle_favori_produit_fini_essence(self):
        self.client.force_authenticate(self.user)
        url = f'/api/v1/shop/produits-essence/{self.produit.id}/favori/'

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'ajouté')
        self.assertTrue(Favori.objects.filter(client=self.user.client, produit_fini_essence=self.produit).exists())

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'retiré')
        self.assertFalse(Favori.objects.filter(client=self.user.client, produit_fini_essence=self.produit).exists())


class ProduitFiniEssenceVirtualStockTest(TestCase):
    """Teste le nouveau modèle 'vente à la demande' où ProduitFiniEssence
    n'a plus de stock propre — le stock est calculé virtuellement depuis
    les lots de l'essence parente."""

    def setUp(self):
        self.essence = Essence.objects.create(
            marque="Maison Test",
            nom="Oud Royal",
            categorie="premium",
            code_reference="ESS-STOCK-001",
            seuil_alerte_ml=Decimal('50.00'),
        )
        self.lot_ancien = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('100.00'),
        )
        self.lot_recent = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('80.00'),
        )

    def test_creation_ne_preleve_pas_sur_lots(self):
        """Créer un ProduitFiniEssence ne doit plus prélever sur les lots."""
        ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=30,
            prix=25.00
        )
        self.lot_ancien.refresh_from_db()
        self.lot_recent.refresh_from_db()
        # Les lots restent intacts
        self.assertEqual(self.lot_ancien.stock_ml, Decimal('100.00'))
        self.assertEqual(self.lot_recent.stock_ml, Decimal('80.00'))

    def test_stock_virtuel_calcule_depuis_lots(self):
        """Le stock disponible est calculé : stock_total_ml / taille_ml."""
        produit = ProduitFiniEssence.objects.create(
            essence=self.essence,
            taille_ml=30,
            prix=25.00
        )
        # Total lots = 180 ml, taille = 30 ml → 6 flacons virtuels
        stock_virtuel = int(self.essence.stock_total_ml() // produit.taille_ml)
        self.assertEqual(stock_virtuel, 6)

    def test_prelever_lots_fifo(self):
        """essence.prelever_lots() prélève en FIFO sur les lots."""
        self.essence.prelever_lots(Decimal('120'))
        self.lot_ancien.refresh_from_db()
        self.lot_recent.refresh_from_db()
        # lot_ancien (100ml) vidé, 20ml prélevés sur lot_recent
        self.assertEqual(self.lot_ancien.stock_ml, Decimal('0.00'))
        self.assertEqual(self.lot_recent.stock_ml, Decimal('60.00'))

    def test_prelever_lots_stock_insuffisant(self):
        """prelever_lots lève une erreur si stock insuffisant."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.essence.prelever_lots(Decimal('200'))

    def test_restituer_lots(self):
        """essence.restituer_lots() restitue sur le lot le plus récent."""
        self.essence.prelever_lots(Decimal('100'))
        self.essence.restituer_lots(Decimal('50'))
        self.lot_recent.refresh_from_db()
        # lot_recent avait 80 - 0 = 80 (prélèvement a vidé lot_ancien), puis +50
        self.assertEqual(self.lot_recent.stock_ml, Decimal('130.00'))


class EssenceModifierEndpointTest(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='essence-modifier-admin',
            email='essence-modifier-admin@example.com',
            password='test1234',
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.essence = Essence.objects.create(
            marque='Maison Test',
            nom='Rose Éclatante',
            categorie='premium',
            code_reference='ESS-MOD-001',
            prix_par_ml=Decimal('150.00'),
            actif=True,
        )

    def test_modifier_endpoint_updates_essence(self):
        url = reverse('essence-modifier', kwargs={'slug': self.essence.slug})
        response = self.client.patch(
            url,
            {'nom': 'Rose Éclatante Update', 'prix_par_ml': '180.00', 'actif': False},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.essence.refresh_from_db()
        self.assertEqual(self.essence.nom, 'Rose Éclatante Update')
        self.assertEqual(self.essence.prix_par_ml, Decimal('180.00'))
        self.assertFalse(self.essence.actif)


class BeneficeEndpointTest(APITestCase):
    def setUp(self):
        self.categorie = CategorieParfum.objects.create(
            nom="Oriental", slug="oriental", taux_reduction=0
        )
        self.parfum = Parfum.objects.create(
            nom="Rose Éternelle", slug="rose-eternelle",
            reference_sku="SKU001", contenance_ml=50,
            prix_unitaire=Decimal('25000'),
            prix_achat=Decimal('15000'),
            categorie=self.categorie, actif=True
        )
        self.essence = Essence.objects.create(
            marque="Maison Test",
            nom="Oud Royal",
            categorie="premium",
            code_reference="ESS-BEN-001",
        )
        self.lot = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('100.00'),
            quantite_initiale_ml=Decimal('100.00'),
            prix_achat_par_ml=Decimal('2.50'),
        )
        self.admin = get_user_model().objects.create_user(
            username='benefice-admin',
            email='benefice-admin@example.com',
            password='test1234',
            is_staff=True,
        )
        self.client.force_authenticate(self.admin)

    def test_calcul_benefices_endpoint(self):
        response = self.client.get('/api/v1/lab/benefices/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('benefice_total', response.data)
        self.assertIn('marge_globale', response.data)
        self.assertIn('produits', response.data)
        self.assertIn('lots', response.data)


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
            prix_unitaire=Decimal('25000'), stock_quantite=10,
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
        self.tag_floral  = Tag.objects.create(nom="Floral")
        self.tag_boise   = Tag.objects.create(nom="Boisé")
        self.tag_ete     = Tag.objects.create(nom="Été")
        self.tag_romance = Tag.objects.create(nom="Romantique")
        self.parfum_visible = Parfum.objects.create(
            nom="Rose Éternelle", slug="rose-eternelle",
            reference_sku="SKU001", contenance_ml=50,
            prix_unitaire=25000, stock_quantite=10, categorie=self.categorie, actif=True
        )
        self.parfum_visible.tags.add(self.tag_floral, self.tag_ete, self.tag_romance)
        self.parfum_cache = Parfum.objects.create(
            nom="Parfum Secret", slug="parfum-secret",
            reference_sku="SKU002", contenance_ml=50,
            prix_unitaire=15000, stock_quantite=10, categorie=self.categorie, actif=False
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
        self.tag_floral = Tag.objects.create(nom="Floral")
        self.tag_lion   = Tag.objects.create(nom="Lion")
        self.essence_active = Essence.objects.create(
            marque="Maison Test", nom="Oud Royal", code_reference="ESS001",
            categorie="premium", prix_par_ml=Decimal('500.00'), actif=True
        )
        self.essence_active.tags.add(self.tag_floral, self.tag_lion)
        LotEssence.objects.create(
            essence=self.essence_active,
            stock_ml=Decimal('500.00'),
            quantite_initiale_ml=Decimal('500.00'),
            actif=True
        )
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

    def test_produits_finis_inclus_dans_boutique_et_exclus_dans_labo(self):
        from catalogue.models import ProduitFiniEssence
        ProduitFiniEssence.objects.create(
            essence=self.essence_active, taille_ml=50, prix=Decimal('15000.00'), actif=True
        )

        # 1. Vue Boutique (X-Context: boutique) -> produits_finis est présent
        resp_shop = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='boutique')
        self.assertEqual(resp_shop.status_code, 200)
        self.assertIn('produits_finis', resp_shop.data['resultats'][0])
        self.assertEqual(len(resp_shop.data['resultats'][0]['produits_finis']), 1)
        self.assertEqual(resp_shop.data['resultats'][0]['produits_finis'][0]['taille_ml'], 50)

        # 2. Vue Labo (X-Context: labo) -> produits_finis est exclu pour se concentrer sur le stock ml
        resp_labo = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='labo')
        self.assertEqual(resp_labo.status_code, 200)
        self.assertNotIn('produits_finis', resp_labo.data['resultats'][0])

        # 3. Vue Dashboard Admin (X-Context: dashboard) -> utilise EssenceSerializer d'administration
        user_model = get_user_model()
        admin = user_model.objects.create_user(email='admin-ess@example.com', password='password123', is_staff=True)
        self.client.force_authenticate(admin)
        resp_dash = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='dashboard')
        self.assertEqual(resp_dash.status_code, 200)

    def test_essence_sans_produit_fini_visible_au_labo_mais_masquee_en_boutique(self):
        from catalogue.models import Essence, LotEssence
        # Essence brute avec stock en ml mais SANS produit fini
        essence_brute = Essence.objects.create(
            marque="Maison Lab", nom="Jasmin Brut", code_reference="ESS-BRUTE-001",
            categorie="premium", prix_par_ml=Decimal('400.00'), actif=True
        )
        LotEssence.objects.create(
            essence=essence_brute, stock_ml=Decimal('200.00'), quantite_initiale_ml=Decimal('200.00'), actif=True
        )

        # 1. En Boutique (X-Context: boutique) -> L'essence brute sans produit fini n'apparaît pas
        resp_boutique = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='boutique')
        self.assertEqual(resp_boutique.status_code, 200)
        slugs_boutique = [e['slug'] for e in resp_boutique.data['resultats']]
        self.assertNotIn(essence_brute.slug, slugs_boutique)

        # 2. Au Labo (X-Context: labo) -> L'essence brute apparaît car elle a du stock brut (stock_total_ml > 0)
        resp_labo = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='labo')
        self.assertEqual(resp_labo.status_code, 200)
        slugs_labo = [e['nom'] for e in resp_labo.data['resultats']]
        self.assertIn("Jasmin Brut", slugs_labo)

    def test_essence_sans_stock_masquee_au_labo_et_en_boutique(self):
        from catalogue.models import Essence, ProduitFiniEssence
        # Essence créée à vide sans aucun lot de stock
        essence_vide = Essence.objects.create(
            marque="Maison Vide", nom="Musc Vide", code_reference="ESS-VIDE-001",
            categorie="premium", prix_par_ml=Decimal('300.00'), actif=True
        )
        ProduitFiniEssence.objects.create(
            essence=essence_vide, taille_ml=30, prix=Decimal('10000.00'), actif=True
        )

        # 1. En Boutique -> Masquée car stock_total_ml = 0 < min_taille_ml (30ml)
        resp_boutique = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='boutique')
        slugs_boutique = [e['slug'] for e in resp_boutique.data['resultats']]
        self.assertNotIn(essence_vide.slug, slugs_boutique)

        # 2. Au Labo -> Masquée car stock_total_ml = 0
        resp_labo = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='labo')
        slugs_labo = [e['nom'] for e in resp_labo.data['resultats']]
        self.assertNotIn("Musc Vide", slugs_labo)

        # 3. En Dashboard Admin -> Visible pour permettre l'approvisionnement
        user_model = get_user_model()
        admin = user_model.objects.create_user(email='admin-vide@example.com', password='password123', is_staff=True)
        self.client.force_authenticate(admin)
        resp_dash = self.client.get('/api/v1/lab/essences/', HTTP_X_CONTEXT='dashboard')
        slugs_dash = [e['slug'] for e in resp_dash.data['resultats']]
        self.assertIn(essence_vide.slug, slugs_dash)


class IngredientVisibilityAPITest(APITestCase):
    def setUp(self):
        self.ingredient_disponible = Ingredient.objects.create(
            nom='Huile disponible', prix_par_ml=Decimal('500.00'),
            stock_ml=Decimal('10.000'), actif=True,
        )
        self.ingredient_rupture = Ingredient.objects.create(
            nom='Huile en rupture', prix_par_ml=Decimal('500.00'),
            stock_ml=Decimal('0.000'), actif=True,
        )
        self.ingredient_sans_prix = Ingredient.objects.create(
            nom='Huile sans prix', prix_par_ml=Decimal('0.00'),
            stock_ml=Decimal('10.000'), actif=True,
        )

        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            email='admin-ingredients@example.com', password='password123',
            telephone='+237600000001', is_staff=True,
        )
        self.serveuse_user = user_model.objects.create_user(
            email='serveuse-ingredients@example.com', password='password123',
            telephone='+237600000002',
        )
        Serveuse.objects.create(client=self.serveuse_user.client, actif=True)

    def test_public_ne_voit_que_les_ingredients_en_stock_avec_prix(self):
        response = self.client.get('/api/v1/lab/ingredients/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['resultats'][0]['id'], self.ingredient_disponible.id)
        self.assertEqual(
            self.client.get(f'/api/v1/lab/ingredients/{self.ingredient_rupture.slug}/').status_code,
            404,
        )

    def test_admin_voit_aussi_ingredients_sans_stock_ou_prix(self):
        self.client.force_authenticate(self.admin)

        # Sans en-tête dashboard -> vue client (1 seul ingrédient disponible)
        response_client_view = self.client.get('/api/v1/lab/ingredients/')
        self.assertEqual(response_client_view.status_code, 200)
        self.assertEqual(response_client_view.data['count'], 1)

        # Avec en-tête dashboard -> vue admin (les 3 ingrédients)
        response = self.client.get('/api/v1/lab/ingredients/', HTTP_X_DASHBOARD_CONTEXT='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)

    def test_serveuse_active_voit_aussi_ingredients_sans_stock_ou_prix(self):
        self.client.force_authenticate(self.serveuse_user)

        # Sans en-tête dashboard -> vue client (1 seul ingrédient disponible)
        response_client_view = self.client.get('/api/v1/lab/ingredients/')
        self.assertEqual(response_client_view.status_code, 200)
        self.assertEqual(response_client_view.data['count'], 1)

        # Avec en-tête dashboard -> vue serveuse (les 3 ingrédients)
        response = self.client.get('/api/v1/lab/ingredients/', HTTP_X_DASHBOARD_CONTEXT='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)


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
        self.tag_floral = Tag.objects.create(nom="Floral")
        self.tag_boise  = Tag.objects.create(nom="Boisé")
        self.tag_oriental = Tag.objects.create(nom="Oriental")

        # Parfum A : floral + boisé
        self.p1 = Parfum.objects.create(
            nom="Rose", slug="rose", reference_sku="P1",
            contenance_ml=50, prix_unitaire=10000,
            stock_quantite=10, categorie=self.cat, actif=True
        )
        TagParfum.objects.create(parfum=self.p1, tag=self.tag_floral, valeur="Fleuri")
        TagParfum.objects.create(parfum=self.p1, tag=self.tag_boise, valeur="Boisé")

        # Parfum B : floral + boisé (identique)
        self.p2 = Parfum.objects.create(
            nom="Jasmin", slug="jasmin", reference_sku="P2",
            contenance_ml=50, prix_unitaire=12000,
            stock_quantite=10, categorie=self.cat, actif=True
        )
        TagParfum.objects.create(parfum=self.p2, tag=self.tag_floral, valeur="Fleuri")
        TagParfum.objects.create(parfum=self.p2, tag=self.tag_boise, valeur="Boisé")

        # Parfum C : boisé seulement
        self.p3 = Parfum.objects.create(
            nom="Cèdre", slug="cedre", reference_sku="P3",
            contenance_ml=50, prix_unitaire=9000,
            stock_quantite=10, categorie=self.cat, actif=True
        )
        TagParfum.objects.create(parfum=self.p3, tag=self.tag_boise, valeur="Boisé")

        # Parfum D : aucun tag commun
        self.p4 = Parfum.objects.create(
            nom="Vanille", slug="vanille", reference_sku="P4",
            contenance_ml=50, prix_unitaire=11000,
            stock_quantite=10, categorie=self.cat, actif=True
        )
        TagParfum.objects.create(parfum=self.p4, tag=self.tag_oriental, valeur="Oriental")

        # Parfum inactif (ne doit pas remonter)
        self.p5 = Parfum.objects.create(
            nom="Inactif", slug="inactif", reference_sku="P5",
            contenance_ml=50, prix_unitaire=5000,
            stock_quantite=10, categorie=self.cat, actif=False
        )
        TagParfum.objects.create(parfum=self.p5, tag=self.tag_floral, valeur="Fleuri")

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
            stock_quantite=10, categorie=self.cat, actif=True
        )
        similaires = get_similar_products(p_sans_tag, Parfum, limit=4)
        self.assertEqual(len(similaires), 0)

    def test_limit_max(self):
        # Créer 6 parfums avec tag floral
        for i in range(6):
            p = Parfum.objects.create(
                nom=f"Test{i}", slug=f"test{i}", reference_sku=f"P7{i}",
                contenance_ml=50, prix_unitaire=10000,
                stock_quantite=10, categorie=self.cat, actif=True
            )
            TagParfum.objects.create(parfum=p, tag=self.tag_floral, valeur="Fleuri")
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
            essence=self.essence, taille_ml=30, prix=3000,
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


class DashboardContextFilterTest(APITestCase):
    """
    Tests pour vérifier le filtrage selon le contexte Dashboard / Client Store:
    - Sans en-tête HTTP dashboard (X-Dashboard-Context), un utilisateur staff ne voit QUE les produits actifs (comportement client).
    - Avec l'en-tête X-Dashboard-Context: true, un utilisateur staff voit TOUS les produits (actifs ET inactifs).
    - Un client normal avec l'en-tête X-Dashboard-Context: true ne voit TOUJOURS QUE les produits actifs.
    """

    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username='dash-admin',
            email='dash-admin@example.com',
            password='password123',
            is_staff=True,
        )
        self.client_user = user_model.objects.create_user(
            username='dash-client',
            email='dash-client@example.com',
            password='password123',
        )

        self.categorie = CategorieParfum.objects.create(nom="Test Category", slug="test-cat-dash")

        self.parfum_actif = Parfum.objects.create(
            nom="Parfum Actif", slug="parfum-actif",
            reference_sku="SKU-ACT", contenance_ml=50,
            prix_unitaire=20000, stock_quantite=10,
            categorie=self.categorie, actif=True
        )

        self.parfum_inactif = Parfum.objects.create(
            nom="Parfum Inactif", slug="parfum-inactif",
            reference_sku="SKU-INACT", contenance_ml=50,
            prix_unitaire=20000, stock_quantite=10,
            categorie=self.categorie, actif=False
        )

    def test_admin_sans_en_tete_voit_uniquement_actifs(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/v1/shop/parfums/')
        self.assertEqual(response.status_code, 200)
        slugs = [p['slug'] for p in response.data['resultats']]
        self.assertIn('parfum-actif', slugs)
        self.assertNotIn('parfum-inactif', slugs)

    def test_admin_avec_en_tete_dashboard_voit_tout(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/v1/shop/parfums/', HTTP_X_DASHBOARD_CONTEXT='true')
        self.assertEqual(response.status_code, 200)
        slugs = [p['slug'] for p in response.data['resultats']]
        self.assertIn('parfum-actif', slugs)
        self.assertIn('parfum-inactif', slugs)

    def test_client_avec_en_tete_dashboard_voit_uniquement_actifs(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.get('/api/v1/shop/parfums/', HTTP_X_DASHBOARD_CONTEXT='true')
        self.assertEqual(response.status_code, 200)
        slugs = [p['slug'] for p in response.data['resultats']]
        self.assertIn('parfum-actif', slugs)
        self.assertNotIn('parfum-inactif', slugs)


class EssenceCreateFullSerializerTest(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username='admin-ess-create',
            email='admin-ess-create@example.com',
            password='password123',
            is_staff=True
        )
        self.client.force_authenticate(self.admin)

    def test_creation_essence_avec_initial_lot_et_produits_finis(self):
        payload = {
            "marque": "Guerlain",
            "nom": "Essence Oud Impérial",
            "slug": "essence-oud-imperial-test",
            "categorie": "premium",
            "code_reference": "ESS-OUD-001",
            "prix_par_ml": "150.00",
            "actif": True,
            "initial_lot": {
                "stock_ml": "1000.00",
                "prix_achat_par_ml": "50.00",
                "reference_fournisseur": "LOT-SUPPLIER-01"
            },
            "produits_finis": [
                {"taille_ml": 30, "prix": "15000.00"},
                {"taille_ml": 50, "prix": "22000.00"}
            ]
        }
        response = self.client.post('/api/v1/lab/essences/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        
        essence = Essence.objects.get(slug="essence-oud-imperial-test")
        self.assertEqual(essence.stock_total_ml(), Decimal('1000.00'))
        self.assertEqual(essence.produits_finis.count(), 2)
        
        # Vérifier que les détails sont présents dans la réponse JSON
        self.assertEqual(Decimal(str(response.data['stock_total_ml'])), Decimal('1000.00'))
        self.assertEqual(len(response.data['produits_finis']), 2)

    def test_creation_essence_avec_stringified_json_multipart(self):
        import json
        payload = {
            "marque": "Dior",
            "nom": "Essence Rose Royale",
            "slug": "essence-rose-royale-test",
            "categorie": "super_premium",
            "code_reference": "ESS-ROS-002",
            "prix_par_ml": "200.00",
            "actif": "true",
            "initial_lot": json.dumps({"stock_ml": "500.00", "reference_fournisseur": "LOT-ROSE"}),
            "produits_finis": json.dumps([{"taille_ml": 50, "prix": "30000.00"}])
        }
        response = self.client.post('/api/v1/lab/essences/', payload, format='multipart')
        self.assertEqual(response.status_code, 201)
        
        essence = Essence.objects.get(slug="essence-rose-royale-test")
        self.assertEqual(essence.stock_total_ml(), Decimal('500.00'))
        self.assertEqual(essence.produits_finis.count(), 1)


# ============================================================
# TESTS RECHERCHE ORDONNÉE & PRIORISÉE
# ============================================================
class OrderedSearchFilterTest(APITestCase):
    def setUp(self):
        self.cat1 = CategorieParfum.objects.create(nom="Catégorie Ordinaire")
        self.cat_pu = CategorieParfum.objects.create(nom="Catégorie Pura")
        self.tag_pu = Tag.objects.create(nom="Puissant")

        # Priorité 1: Nom commence par 'pu'
        self.p1 = Parfum.objects.create(
            nom="Pure Oud", marque="Lattafa", categorie=self.cat1, contenance_ml=100,
            prix_unitaire=10000, stock_quantite=50, seuil_alerte_stock=2, actif=True
        )
        # Priorité 2: Nom contient 'pu'
        self.p2 = Parfum.objects.create(
            nom="Bavaria Lapurd", marque="Lattafa", categorie=self.cat1, contenance_ml=100,
            prix_unitaire=10000, stock_quantite=50, seuil_alerte_stock=2, actif=True
        )
        # Priorité 3: Marque contient 'pu'
        self.p3 = Parfum.objects.create(
            nom="Royal Sillage", marque="Puma Fragrances", categorie=self.cat1, contenance_ml=100,
            prix_unitaire=10000, stock_quantite=50, seuil_alerte_stock=2, actif=True
        )
        # Priorité 4: Catégorie contient 'pu'
        self.p4 = Parfum.objects.create(
            nom="Velvet Rose", marque="Armani", categorie=self.cat_pu, contenance_ml=100,
            prix_unitaire=10000, stock_quantite=50, seuil_alerte_stock=2, actif=True
        )
        # Priorité 5: Tag contient 'pu'
        self.p5 = Parfum.objects.create(
            nom="Noir Extreme", marque="Tom Ford", categorie=self.cat1, contenance_ml=100,
            prix_unitaire=10000, stock_quantite=50, seuil_alerte_stock=2, actif=True
        )
        self.p5.tags.add(self.tag_pu)

    def test_parfum_ordered_search_hierarchy(self):
        response = self.client.get('/api/v1/shop/parfums/?search=pu')
        self.assertEqual(response.status_code, 200)
        data = response.data.get('resultats', response.data.get('results', response.data))
        noms = [item['nom'] for item in data]
        self.assertEqual(len(noms), 5)
        self.assertEqual(noms[0], "Pure Oud")          # Prio 1: istartswith
        self.assertEqual(noms[1], "Bavaria Lapurd")     # Prio 2: icontains
        self.assertEqual(noms[2], "Royal Sillage")      # Prio 3: marque
        self.assertEqual(noms[3], "Velvet Rose")        # Prio 4: categorie
        self.assertEqual(noms[4], "Noir Extreme")       # Prio 5: tag


class SimilarProductsTest(TestCase):
    def setUp(self):
        from .models import TagParfum
        self.tag_temps = Tag.objects.create(nom="Moment de la journée")

        # Target parfum (Marque: Lattafa, Tag "Moment de la journée" = "Nuit")
        self.p_target = Parfum.objects.create(
            nom="Target Oud", marque="Lattafa", contenance_ml=100, prix_unitaire=10000, actif=True
        )
        TagParfum.objects.create(parfum=self.p_target, tag=self.tag_temps, valeur="Nuit")

        # 5 items with matching tag value "Nuit" (Priority 1)
        for i in range(5):
            p = Parfum.objects.create(
                nom=f"Night Fragrance {i}", marque="Dior", contenance_ml=100, prix_unitaire=10000, actif=True
            )
            TagParfum.objects.create(parfum=p, tag=self.tag_temps, valeur="Nuit")

        # 3 items of same brand 'Lattafa' without matching tag value (Priority 2)
        for i in range(3):
            Parfum.objects.create(
                nom=f"Lattafa Item {i}", marque="Lattafa", contenance_ml=100, prix_unitaire=10000, actif=True
            )

    def test_get_similar_products_tag_valeur_then_brand_max_6(self):
        from .utils import get_similar_products
        similaires = list(get_similar_products(self.p_target, Parfum, limit=6))
        self.assertEqual(len(similaires), 6)
        # First 5 items must have matching tag value "Nuit" (Priority 1)
        for p in similaires[:5]:
            self.assertEqual(p.marque, "Dior")
        # 6th item must be same brand 'Lattafa' (Priority 2)
        self.assertEqual(similaires[5].marque, "Lattafa")


class ImportParfumsLogicTest(TestCase):
    def test_parfum_existant_nom_marque_preserve_et_sku_ignore(self):
        from catalogue.models import Parfum, CategorieParfum
        from import_parfums import import_parfums
        import unittest.mock as mock

        cat, _ = CategorieParfum.objects.get_or_create(nom="INSPIRATION")

        # Parfum existant en BDD
        parfum_existant = Parfum.objects.create(
            nom="Bleu de Chanel",
            marque="Chanel",
            reference_sku="SKU-EXISTANT-CUSTOM-123",
            prix_unitaire=Decimal("99999.00"),
            contenance_ml=150,
            description_courte="Description originale personnalisee",
            actif=True
        )

        mock_csv_content = (
            "Nom du produit\tMarque / maison\tPrix (FCFA)\tStatut\n"
            "Bleu de Chanel\tChanel\t155000\tMARQUE\n"
        )

        with mock.patch("builtins.open", mock.mock_open(read_data=mock_csv_content)):
            import_parfums()

        parfum_apres = Parfum.objects.get(pk=parfum_existant.pk)

        # Le parfum d'origine ne doit PAS être modifié (prix, description et SKU d'origine sont préservés)
        self.assertEqual(parfum_apres.prix_unitaire, Decimal("99999.00"))
        self.assertEqual(parfum_apres.description_courte, "Description originale personnalisee")
        self.assertEqual(parfum_apres.reference_sku, "SKU-EXISTANT-CUSTOM-123")
        self.assertTrue(parfum_apres.actif)






