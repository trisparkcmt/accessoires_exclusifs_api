from decimal import Decimal
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from utilisateur.models import User, Client, Boutique
from catalogue.models import CategorieParfum, Parfum, TypeAccessoire, Accessoire
from orders.models import Commande, CommandeLigneParfum, CommandeLigneAccessoire, CodePromoAdmin, VenteBoutique, VersementBoutique
from orders.serializers import CodePromoAdminSerializer
from utilisateur.serializers import BoutiqueAdminUpdateSerializer, BoutiqueValidationSerializer


class BoutiqueVentesTest(TestCase):
    def setUp(self):
        # User & Client Boutique
        self.user_boutique = User.objects.create_user(
            email='boutique@example.com',
            username='boutique_user',
            password='Password123!',
            first_name='Boutique',
            last_name='Owner'
        )
        self.client_boutique, _ = Client.objects.get_or_create(user=self.user_boutique)
        self.boutique = Boutique.objects.create(
            client=self.client_boutique,
            nom='Boutique Luxe',
            taux_commission=Decimal('10.00'),
            statut='actif'
        )

        # User & Client Admin
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            username='admin_user',
            password='Password123!'
        )

        # Products
        self.cat_parfum = CategorieParfum.objects.create(nom='Niche')
        self.parfum_boutique = Parfum.objects.create(
            nom='Parfum Boutique 1',
            categorie=self.cat_parfum,
            boutique=self.boutique,
            contenance_ml=100,
            prix_unitaire=Decimal('10000.00'),
            stock_quantite=10,
            actif=True
        )

        self.type_acc = TypeAccessoire.objects.create(nom='Bijou')
        self.accessoire_boutique = Accessoire.objects.create(
            nom='Accessoire Boutique 1',
            type_accessoire=self.type_acc,
            boutique=self.boutique,
            prix_unitaire=Decimal('5000.00'),
            stock_quantite=10,
            actif=True
        )

    def test_garde_fou_code_promo_empeche_perte(self):
        """Test que la création d'un code promo avec taux > commission boutique est bloquée."""
        # Code promo avec 15% de réduction alors que la boutique a 10% de commission
        serializer = CodePromoAdminSerializer(data={
            'code': 'PROMO15',
            'reduction_pourcentage': '15.00',
            'est_actif': True
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('reduction_pourcentage', serializer.errors)

    def test_garde_fou_code_promo_valide(self):
        """Test qu'un code promo avec taux <= commission boutique est accepté."""
        serializer = CodePromoAdminSerializer(data={
            'code': 'PROMO5',
            'reduction_pourcentage': '5.00',
            'est_actif': True
        })
        self.assertTrue(serializer.is_valid())

    def test_garde_fou_boutique_commission_reduction(self):
        """Test que baisser la commission d'une boutique sous le taux du code promo actif est bloqué."""
        CodePromoAdmin.objects.create(code='PROMO8', reduction_pourcentage=Decimal('8.00'), est_actif=True)

        serializer = BoutiqueValidationSerializer(instance=self.boutique, data={'taux_commission': '5.00'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('taux_commission', serializer.errors)

    def test_calcul_vente_boutique_sur_paiement(self):
        """Test que le paiement d'une commande génère VenteBoutique et crédite le solde."""
        commande = Commande.objects.create(
            client=self.client_boutique,
            sous_total=Decimal('0'),
            total_ttc=Decimal('0'),
            statut='en_attente',
            statut_paiement='non_payé'
        )

        CommandeLigneParfum.objects.create(
            commande=commande,
            parfum=self.parfum_boutique,
            nom_snapshot=self.parfum_boutique.nom,
            quantite=1,
            prix_unitaire_snapshot=Decimal('10000.00')
        )

        CommandeLigneAccessoire.objects.create(
            commande=commande,
            accessoire=self.accessoire_boutique,
            nom_snapshot=self.accessoire_boutique.nom,
            quantite=1,
            prix_unitaire_snapshot=Decimal('5000.00')
        )

        # Montant brut = 15 000 FCFA. Commission 10% = 1 500 FCFA. Net boutique = 13 500 FCFA.
        commande.statut_paiement = 'payé'
        commande.save()

        ventes = VenteBoutique.objects.filter(commande=commande, boutique=self.boutique)
        self.assertEqual(ventes.count(), 1)

        vente = ventes.first()
        self.assertEqual(vente.montant_brut, Decimal('15000.00'))
        self.assertEqual(vente.montant_commission_admin, Decimal('1500.00'))
        self.assertEqual(vente.montant_net_boutique, Decimal('13500.00'))

        self.boutique.refresh_from_db()
        self.assertEqual(self.boutique.solde_disponible, Decimal('13500.00'))

    def test_versement_idempotent(self):
        """Test que le versement d'un solde avec idempotency_key est idempotent et n'effectue pas de double débit."""
        from rest_framework.test import APIClient
        self.boutique.solde_disponible = Decimal('50000.00')
        self.boutique.save()

        client = APIClient()
        client.force_authenticate(user=self.admin_user)

        # Appel sans clé d'idempotence -> 400 Bad Request
        resp_missing_key = client.post(f'/api/v1/auth/admin/boutiques/{self.boutique.id}/effectuer-versement/', {'montant': '20000.00'}, format='json')
        self.assertEqual(resp_missing_key.status_code, 400)
        self.assertIn("obligatoire", resp_missing_key.data.get('detail', ''))

        payload = {
            'montant': '20000.00',
            'idempotency_key': 'KEY-IDEMPOTENT-12345',
            'mode_paiement': 'OM'
        }

        # Premier appel -> 201 Created
        resp1 = client.post(f'/api/v1/auth/admin/boutiques/{self.boutique.id}/effectuer-versement/', payload, format='json')
        self.assertEqual(resp1.status_code, 201)
        self.boutique.refresh_from_db()
        self.assertEqual(self.boutique.solde_disponible, Decimal('30000.00'))
        self.assertEqual(self.boutique.solde_total_recu, Decimal('20000.00'))

        # Second appel identique (Retry / Double-clic) -> 200 OK (Idempotent)
        resp2 = client.post(f'/api/v1/auth/admin/boutiques/{self.boutique.id}/effectuer-versement/', payload, format='json')
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.data.get('idempotent'))
        self.boutique.refresh_from_db()
        # Le solde n'a PAS été débité une deuxième fois !
        self.assertEqual(self.boutique.solde_disponible, Decimal('30000.00'))
        self.assertEqual(self.boutique.solde_total_recu, Decimal('20000.00'))

    def test_admin_boutique_produits_pagination_et_filtres(self):
        """Test la pagination à 100 éléments et les filtres (catégorie, search, type) sur les produits d'une boutique."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.admin_user)

        # 1. Tester GET /api/v1/auth/admin/boutiques/<id>/
        resp_detail = client.get(f'/api/v1/auth/admin/boutiques/{self.boutique.id}/')
        self.assertEqual(resp_detail.status_code, 200)
        self.assertIn('produits', resp_detail.data)
        self.assertEqual(resp_detail.data['produits']['count'], 2)  # 1 parfum + 1 accessoire
        self.assertEqual(resp_detail.data['produits']['page_size'], 100)

        # 2. Tester GET /api/v1/auth/admin/boutiques/<id>/produits/ avec filtre type=parfum
        resp_parfums = client.get(f'/api/v1/auth/admin/boutiques/{self.boutique.id}/produits/?type=parfum')
        self.assertEqual(resp_parfums.status_code, 200)
        self.assertEqual(resp_parfums.data['count'], 1)
        self.assertEqual(resp_parfums.data['results'][0]['nom'], self.parfum_boutique.nom)

        # 3. Tester filtre search
        resp_search = client.get(f'/api/v1/auth/admin/boutiques/{self.boutique.id}/produits/?search=Accessoire')
        self.assertEqual(resp_search.status_code, 200)
        self.assertEqual(resp_search.data['count'], 1)
        self.assertEqual(resp_search.data['results'][0]['nom'], self.accessoire_boutique.nom)

    def test_vendeur_me_boutique_produits(self):
        """Test que le vendeur accède à tous ses propres produits paginés par 100 avec filtres."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user_boutique)

        # GET /api/v1/auth/me/boutique/produits/
        resp = client.get('/api/v1/auth/me/boutique/produits/?page_size=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 2)
        self.assertEqual(resp.data['page_size'], 100)
