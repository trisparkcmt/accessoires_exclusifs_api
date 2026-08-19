from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

from catalogue.models import Flacon, Essence, LotEssence
from laboratoire.models import ParfumPersonnalise
from orders.models import Panier, PanierLigneParfumPerso, Commande, CommandeLigneParfumPerso
from utilisateur.models import Client

User = get_user_model()


class FlaconCustomizationAPITestCase(APITestCase):
    def setUp(self):
        # 1. Créer un utilisateur et client
        self.user = User.objects.create_user(
            username='client_custom_test',
            email='client_custom@example.com',
            password='Password123!',
            first_name='Jean',
            last_name='Dupont',
            telephone='+237699001122'
        )
        self.client_obj = self.user.client

        # 2. Créer un utilisateur admin
        self.admin = User.objects.create_superuser(
            username='admin_custom_test',
            email='admin_custom@example.com',
            password='AdminPassword123!'
        )

        # 3. Flacon test
        self.flacon = Flacon.objects.create(
            nom="Flacon Cristal 100ml",
            contenance_ml=100,
            prix_unitaire=Decimal('2000.00'),
            stock_quantite=50,
            actif=True
        )

        # 4. Essence et Lot
        self.essence = Essence.objects.create(
            nom="Vanille Bourbon",
            code_reference="VAN-001",
            prix_par_ml=Decimal('100.00'),
            actif=True
        )
        self.lot_essence = LotEssence.objects.create(
            essence=self.essence,
            stock_ml=Decimal('1000.00'),
            actif=True
        )

    def test_1_lab_creation_with_customization(self):
        """Vérifie la création d'un parfum personnalisé avec couleur et nom sur flacon dans le labo."""
        self.client.force_authenticate(user=self.user)
        url = '/api/v1/lab/parfums-perso/'
        payload = {
            'nom': 'Mon Parfum Rose',
            'couleur': 'Rose Gold',
            'nom_sur_flacon': 'Pour Marie',
            'flacon': self.flacon.id,
            'lignes': [
                {'essence': self.essence.id, 'quantite_ml': 10.0}
            ]
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['couleur'], 'Rose Gold')
        self.assertEqual(response.data['nom_sur_flacon'], 'Pour Marie')

        parfum = ParfumPersonnalise.objects.get(id=response.data['id'])
        self.assertEqual(parfum.couleur, 'Rose Gold')
        self.assertEqual(parfum.nom_sur_flacon, 'Pour Marie')

    def test_2_ajouter_composition_directe_au_panier(self):
        """Vérifie l'ajout direct au panier avec couleur et nom_sur_flacon."""
        self.client.force_authenticate(user=self.user)
        url = '/api/v1/orders/panier/ajouter/composition-directe/'
        payload = {
            'flacon_id': self.flacon.id,
            'nom': 'Composition Ambrée',
            'couleur': '#FF5733',
            'nom_sur_flacon': 'Alexandre',
            'quantite': 2,
            'lignes': [
                {'lot_essence_id': self.lot_essence.id, 'quantite_ml': 15.0}
            ]
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ligne = PanierLigneParfumPerso.objects.latest('id')
        self.assertEqual(ligne.couleur, '#FF5733')
        self.assertEqual(ligne.nom_sur_flacon, 'Alexandre')
        self.assertEqual(ligne.parfum_personnalise.couleur, '#FF5733')
        self.assertEqual(ligne.parfum_personnalise.nom_sur_flacon, 'Alexandre')

    def test_3_passer_commande_composition_directe(self):
        """Vérifie le passage direct de commande avec couleur et nom_sur_flacon."""
        self.client.force_authenticate(user=self.user)
        url = '/api/v1/orders/commandes/passer-composition-directe/'
        payload = {
            'flacon_id': self.flacon.id,
            'nom': 'Commande Directe Custom',
            'couleur': 'Bleu Nuit',
            'nom_sur_flacon': 'Boss Edition',
            'quantite': 1,
            'livraison_nom_complet': 'Jean Dupont',
            'livraison_telephone': '+237699001122',
            'lignes': [
                {'lot_essence_id': self.lot_essence.id, 'quantite_ml': 20.0}
            ]
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        commande = Commande.objects.get(id=response.data['id'])
        ligne_cmd = commande.lignes_parfums_perso.first()
        self.assertIsNotNone(ligne_cmd)
        self.assertEqual(ligne_cmd.couleur, 'Bleu Nuit')
        self.assertEqual(ligne_cmd.nom_sur_flacon, 'Boss Edition')

    def test_4_checkout_panier_preserves_customization(self):
        """Vérifie que la validation du panier transfère la couleur et le nom_sur_flacon à la commande."""
        self.client.force_authenticate(user=self.user)
        
        # 1. Créer le parfum perso
        parfum = ParfumPersonnalise.objects.create(
            client=self.client_obj,
            flacon=self.flacon,
            nom="Composition Panier",
            couleur="Or Liquide",
            nom_sur_flacon="Mon Amour",
            prix_essences=Decimal('1000.00'),
            prix_flacon_snapshot=Decimal('2000.00'),
            prix_total=Decimal('3000.00')
        )
        
        # 2. Créer le panier
        panier = Panier.objects.create(client=self.client_obj)
        PanierLigneParfumPerso.objects.create(
            panier=panier,
            parfum_personnalise=parfum,
            quantite=1,
            prix_calcule=Decimal('3000.00'),
            sous_total=Decimal('3000.00'),
            couleur="Or Liquide",
            nom_sur_flacon="Mon Amour"
        )
        panier.recalculer_total()

        # 3. Passer la commande panier
        url = '/api/v1/orders/commandes/passer/'
        payload = {
            'panier_id': panier.id,
            'livraison_nom_complet': 'Jean Dupont',
            'livraison_telephone': '+237699001122'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        commande = Commande.objects.get(id=response.data['id'])
        ligne_cmd = commande.lignes_parfums_perso.first()
        self.assertEqual(ligne_cmd.couleur, "Or Liquide")
        self.assertEqual(ligne_cmd.nom_sur_flacon, "Mon Amour")

    def test_5_pos_order_creation_with_customization(self):
        """Vérifie la création d'une commande POS avec couleur et nom sur flacon."""
        self.client.force_authenticate(user=self.admin)
        url = '/api/v1/pos/commandes/creer/'
        payload = {
            'client_telephone': '+237699001122',
            'client_nom_complet': 'Jean Dupont',
            'lignes': [
                {
                    'type': 'parfum_perso',
                    'quantite': 1,
                    'couleur': 'Emeraude',
                    'nom_sur_flacon': 'Cuvée Spéciale',
                    'recette': {
                        'flacon_id': self.flacon.id,
                        'nom': 'Parfum POS Custom',
                        'lignes': [
                            {'lot_essence_id': self.lot_essence.id, 'quantite_ml': 10.0}
                        ]
                    }
                }
            ]
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        commande = Commande.objects.get(id=response.data['id'])
        ligne_cmd = commande.lignes_parfums_perso.first()
        self.assertEqual(ligne_cmd.couleur, 'Emeraude')
        self.assertEqual(ligne_cmd.nom_sur_flacon, 'Cuvée Spéciale')
        self.assertEqual(ligne_cmd.parfum_personnalise.couleur, 'Emeraude')
        self.assertEqual(ligne_cmd.parfum_personnalise.nom_sur_flacon, 'Cuvée Spéciale')
