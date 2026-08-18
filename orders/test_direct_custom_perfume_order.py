from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from catalogue.models import Flacon, Essence, LotEssence, Parfum
from orders.models import Commande, Panier, PanierLigneParfum, CodePromoAdmin
from laboratoire.models import ParfumPersonnalise

User = get_user_model()


class DirectCustomPerfumeOrderTestCase(APITestCase):

    def setUp(self):
        # 1. User and Profile
        self.user = User.objects.create_user(
            username="client_sur_mesure",
            email="surmesure@exclusif.com",
            password="password123",
            telephone="+237699001122",
            first_name="Jean",
            last_name="Dupont"
        )
        self.client_profile = self.user.client

        # 2. Catalogue Items
        self.flacon_50ml = Flacon.objects.create(
            nom="Flacon Design 50ml",
            contenance_ml=50,
            prix_unitaire=Decimal("6000.00"),
            stock_quantite=50,
            actif=True
        )

        self.essence_vanille = Essence.objects.create(
            marque="Accessoire Exclusif",
            nom="Vanille Bourbon",
            code_reference="ESS-VAN",
            prix_par_ml=Decimal("150.00"),
            actif=True
        )
        self.lot_vanille = LotEssence.objects.create(
            essence=self.essence_vanille,
            stock_ml=Decimal("1000.00"),
            actif=True
        )

        self.essence_jasmin = Essence.objects.create(
            marque="Accessoire Exclusif",
            nom="Jasmin Royal",
            code_reference="ESS-JAS",
            prix_par_ml=Decimal("200.00"),
            actif=True
        )
        self.lot_jasmin = LotEssence.objects.create(
            essence=self.essence_jasmin,
            stock_ml=Decimal("1000.00"),
            actif=True
        )

        # Standard perfume for cart pollution testing (using the correct field: prix_unitaire)
        self.parfum_standard = Parfum.objects.create(
            nom="Eau de Paris",
            contenance_ml=100,
            prix_unitaire=Decimal("15000.00"),
            stock_quantite=20,
            actif=True
        )

        self.direct_order_url = reverse('commande-passer-composition-directe')

    def test_direct_order_custom_perfume_does_not_pollute_active_cart(self):
        """
        Vérifie qu'une commande directe de parfum personnalisé ne touche ni ne convertit
        le panier d'achat actif existant du client.
        """
        self.client.force_authenticate(user=self.user)

        # 1. Créer un panier actif pour l'utilisateur avec un article standard
        active_cart = Panier.objects.create(client=self.client_profile, statut='actif')
        PanierLigneParfum.objects.create(
            panier=active_cart,
            parfum=self.parfum_standard,
            quantite=1,
            prix_unitaire_snapshot=self.parfum_standard.prix_unitaire,
            sous_total=self.parfum_standard.prix_unitaire
        )
        active_cart.recalculer_total()

        self.assertEqual(active_cart.statut, 'actif')
        self.assertEqual(active_cart.lignes_parfums.count(), 1)

        # 2. Exécuter la commande directe sur-mesure
        # 10ml Vanille + 5ml Jasmin = 15ml total (<= 50 * 0.45 = 22.5ml)
        payload = {
            "quantite": 1,
            "flacon_id": self.flacon_50ml.id,
            "lignes": [
                {"lot_essence_id": self.lot_vanille.id, "quantite_ml": 10.0},
                {"lot_essence_id": self.lot_jasmin.id, "quantite_ml": 5.0}
            ],
            "enregistre": False
        }

        response = self.client.post(self.direct_order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

        # 3. Vérifier que la commande a été créée correctement
        commande = Commande.objects.get(id=response.data['id'])
        self.assertEqual(commande.client, self.client_profile)
        # Nom et téléphone doivent être auto-remplis depuis le profil connecté
        self.assertEqual(commande.livraison_nom_complet, "Jean Dupont")
        self.assertEqual(commande.livraison_telephone, "+237699001122")

        # Vérifier les lignes de la commande
        self.assertEqual(commande.lignes_parfums_perso.count(), 1)
        ligne_perso = commande.lignes_parfums_perso.first()
        # Prix flacon (6000) + Vanille (10*150=1500) + Jasmin (5*200=1000) = 8500
        self.assertEqual(ligne_perso.parfum_personnalise.prix_total, Decimal("8500.00"))
        self.assertEqual(commande.total_ttc, Decimal("8500.00"))

        # 4. CRUCIAL : le panier actif initial doit être INTACT
        active_cart.refresh_from_db()
        self.assertEqual(active_cart.statut, 'actif')
        self.assertEqual(active_cart.lignes_parfums.count(), 1)
        self.assertEqual(active_cart.lignes_parfums.first().parfum, self.parfum_standard)

    def test_direct_order_custom_perfume_all_fields_optional(self):
        """
        Vérifie que nom, livraison_nom_complet, livraison_telephone, livraison_quartier, livraison_ville
        sont tous facultatifs (commande anonyme).
        """
        payload = {
            "flacon_id": self.flacon_50ml.id,
            "lignes": [
                {"lot_essence_id": self.lot_vanille.id, "quantite_ml": 8.0}
            ]
        }

        response = self.client.post(self.direct_order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

        commande = Commande.objects.get(id=response.data['id'])
        self.assertIsNone(commande.client)
        self.assertEqual(commande.livraison_nom_complet, "")
        self.assertEqual(commande.livraison_telephone, "")

        parfum = ParfumPersonnalise.objects.latest('id')
        # Nom par défaut attendu si non fourni
        self.assertIn(parfum.nom, ["Création Sur Mesure Express", "Création Personnalisée"])
        self.assertFalse(parfum.enregistre)

    def test_direct_order_custom_perfume_saves_to_lab_when_requested(self):
        """
        Vérifie que la création est enregistrée dans la bibliothèque du labo si enregistre=True.
        """
        self.client.force_authenticate(user=self.user)

        payload = {
            "nom": "Élixir d'Or",
            "flacon_id": self.flacon_50ml.id,
            "enregistre": True,
            "lignes": [
                {"lot_essence_id": self.lot_vanille.id, "quantite_ml": 12.0}
            ]
        }

        response = self.client.post(self.direct_order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

        parfum = ParfumPersonnalise.objects.latest('id')
        self.assertEqual(parfum.nom, "Élixir d'Or")
        self.assertTrue(parfum.enregistre)
        self.assertEqual(parfum.client, self.client_profile)

    def test_direct_order_custom_perfume_not_saved_to_lab_when_enregistre_false(self):
        """
        Vérifie que la composition n'est pas enregistrée dans la bibliothèque si enregistre=False,
        même pour un client authentifié.
        """
        self.client.force_authenticate(user=self.user)

        payload = {
            "nom": "Composition Éphémère",
            "flacon_id": self.flacon_50ml.id,
            "enregistre": False,
            "lignes": [
                {"lot_essence_id": self.lot_vanille.id, "quantite_ml": 10.0}
            ]
        }

        response = self.client.post(self.direct_order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

        parfum = ParfumPersonnalise.objects.latest('id')
        self.assertFalse(parfum.enregistre)  # Respecte le choix du client

    def test_direct_order_custom_perfume_exceeding_45_percent_limit_fails(self):
        """
        Vérifie la règle des 45% max du flacon.
        Flacon 50ml -> Max essence 22.5ml. 25ml doit échouer.
        """
        payload = {
            "flacon_id": self.flacon_50ml.id,
            "lignes": [
                {"lot_essence_id": self.lot_vanille.id, "quantite_ml": 25.0}
            ]
        }

        response = self.client.post(self.direct_order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lignes", response.data)

    def test_direct_order_with_promo_code_admin(self):
        """
        Vérifie qu'un code promo admin peut être appliqué lors d'une commande directe.
        """
        code_promo = CodePromoAdmin.objects.create(
            code="OFFRE10",
            reduction_pourcentage=Decimal("10.00"),
            est_actif=True
        )
        # Autoriser le client sur ce code promo
        code_promo.clients_autorises.add(self.client_profile)

        self.client.force_authenticate(user=self.user)

        payload = {
            "flacon_id": self.flacon_50ml.id,
            "code_promo": "OFFRE10",
            "lignes": [
                {"lot_essence_id": self.lot_vanille.id, "quantite_ml": 10.0}
            ]
        }

        response = self.client.post(self.direct_order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

        # Flacon (6000) + Essences (10*150=1500) = 7500. -10% (750) = 6750.
        commande = Commande.objects.get(id=response.data['id'])
        self.assertEqual(commande.code_promo_utilise, "OFFRE10")
        self.assertEqual(commande.remise_code_promo, Decimal("750.00"))
        self.assertEqual(commande.total_ttc, Decimal("6750.00"))
