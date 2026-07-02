from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from catalogue.models import Flacon, Essence, LotEssence
from orders.models import Commande, Panier
from laboratoire.models import ParfumPersonnalise
from utilisateur.models import Client

User = get_user_model()


class AnonymousCheckoutTestCase(APITestCase):

    def setUp(self):
        # 1. Clients et Utilisateurs
        self.client_user = User.objects.create_user(
            username="client_test",
            email="client_test@exclusif.com",
            password="testpassword123",
            telephone="+22507070707",
            first_name="Jean",
            last_name="Eudes"
        )
        self.client_profile = self.client_user.client

        # 2. Flacons
        self.flacon_30ml = Flacon.objects.create(
            nom="Flacon Premium 30ml",
            contenance_ml=30,
            prix_unitaire=Decimal("5000.00"),
            stock_quantite=100,
            actif=True
        )
        self.flacon_100ml = Flacon.objects.create(
            nom="Flacon Luxe 100ml",
            contenance_ml=100,
            prix_unitaire=Decimal("12000.00"),
            stock_quantite=5,
            actif=True
        )

        # 3. Essences
        self.essence_rose = Essence.objects.create(
            marque="Accessoire Exclusif",
            nom="Rose de Grasse",
            code_reference="ESS-ROSE",
            prix_par_ml=Decimal("100.00"),
            actif=True
        )
        self.lot_rose = LotEssence.objects.create(
            essence=self.essence_rose,
            stock_ml=Decimal("500.00"),
            actif=True
        )

        self.essence_oud = Essence.objects.create(
            marque="Accessoire Exclusif",
            nom="Oud Précieux",
            code_reference="ESS-OUD",
            prix_par_ml=Decimal("250.00"),
            actif=True
        )
        self.lot_oud = LotEssence.objects.create(
            essence=self.essence_oud,
            stock_ml=Decimal("10.00"),  # Low stock
            actif=True
        )

        # URLs
        self.composition_directe_url = reverse('panier-ajouter-composition-directe')
        self.passer_commande_url = reverse('commande-passer')
        self.panier_detail_url = reverse('panier-detail')

    def test_direct_composition_anonymous_success(self):
        # Créer un panier anonyme initial (facultatif car get_or_create_panier s'en charge)
        payload = {
            "panier_id": None,
            "quantite": 2,
            "nom": "Création Rose-Oud",
            "note_client": "Léger sur le Oud",
            "flacon_id": self.flacon_30ml.id,
            "lignes": [
                {"lot_essence_id": self.lot_rose.id, "quantite_ml": 8.0},
                {"lot_essence_id": self.lot_oud.id, "quantite_ml": 4.0}
            ]
        }
        # volume total = 8 + 4 = 12 ml. Max autorise pour 30ml = 30 * 0.45 = 13.5 ml. 12 <= 13.5 -> OK.
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Vérifier que le parfum a été créé
        parfums = ParfumPersonnalise.objects.all()
        self.assertEqual(parfums.count(), 1)
        p = parfums.first()
        self.assertEqual(p.nom, "Création Rose-Oud")
        self.assertFalse(p.enregistre)
        self.assertEqual(p.statut, "validé")
        self.assertIsNone(p.client)

        # Vérifier le prix du parfum
        # essences: 8 * 100 + 4 * 250 = 800 + 1000 = 1800
        # flacon: 5000
        # total: 6800
        self.assertEqual(p.prix_total, Decimal("6800.00"))

        # Vérifier que la ligne a été ajoutée au panier retourné
        self.assertIn('lignes_parfums_perso', response.data)
        lignes = response.data['lignes_parfums_perso']
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]['quantite'], 2)
        self.assertEqual(Decimal(lignes[0]['sous_total']), Decimal("13600.00"))

    def test_direct_composition_validation_rules(self):
        # A. Flacon inexistant ou inactif
        payload = {
            "flacon_id": 9999,
            "lignes": [{"lot_essence_id": self.lot_rose.id, "quantite_ml": 5.0}]
        }
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("flacon_id", response.data)

        # B. Règle des 45% dépassée
        # Pour 30ml flacon, le max est 13.5ml. Demandons 14ml de rose.
        payload = {
            "flacon_id": self.flacon_30ml.id,
            "lignes": [{"lot_essence_id": self.lot_rose.id, "quantite_ml": 14.0}]
        }
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lignes", response.data)

        # C. Stock insuffisant pour un lot d'essence
        # oud a seulement 10 ml de disponible, demandons 11 ml dans un flacon de 100ml (limite 45ml)
        payload = {
            "flacon_id": self.flacon_100ml.id,
            "lignes": [{"lot_essence_id": self.lot_oud.id, "quantite_ml": 11.0}]
        }
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_checkout_flow(self):
        # 1. Ajouter un parfum personnalisé au panier anonyme
        payload = {
            "flacon_id": self.flacon_30ml.id,
            "quantite": 1,
            "lignes": [{"lot_essence_id": self.lot_rose.id, "quantite_ml": 10.0}]
        }
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        panier_id = response.data['id']

        # 2. Commander sans coordonnées de livraison (doit réussir désormais)
        payload_cmd_incomplet = {
            "panier_id": panier_id,
            "livraison_nom_complet": "",
            "livraison_telephone": ""
        }
        response_cmd_err = self.client.post(self.passer_commande_url, payload_cmd_incomplet, format='json')
        self.assertEqual(response_cmd_err.status_code, status.HTTP_201_CREATED)
        cmd_incomplet = Commande.objects.get(id=response_cmd_err.data['id'])
        self.assertEqual(cmd_incomplet.livraison_nom_complet, "")
        self.assertEqual(cmd_incomplet.livraison_telephone, "")

        # 3. Recréer un panier pour commander avec coordonnées (Client de passage sans téléphone existant)
        response_2 = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response_2.status_code, status.HTTP_200_OK)
        panier_id_2 = response_2.data['id']

        payload_cmd = {
            "panier_id": panier_id_2,
            "livraison_nom_complet": "Passant de passage",
            "livraison_telephone": "+22501020304",
            "livraison_ville": "Abidjan",
            "livraison_quartier": "Plateau"
        }
        response_cmd = self.client.post(self.passer_commande_url, payload_cmd, format='json')
        self.assertEqual(response_cmd.status_code, status.HTTP_201_CREATED)
        
        # Vérifier la commande en base
        commande_id = response_cmd.data['id']
        cmd = Commande.objects.get(id=commande_id)
        self.assertIsNone(cmd.client)
        self.assertEqual(cmd.livraison_nom_complet, "Passant de passage")
        self.assertEqual(cmd.livraison_telephone, "+22501020304")

    def test_anonymous_checkout_attaches_to_existing_client_by_phone(self):
        # 1. Ajouter un parfum personnalisé au panier anonyme
        payload = {
            "flacon_id": self.flacon_30ml.id,
            "quantite": 1,
            "lignes": [{"lot_essence_id": self.lot_rose.id, "quantite_ml": 10.0}]
        }
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        panier_id = response.data['id']

        # 2. Commander en fournissant le téléphone d'un client existant
        payload_cmd = {
            "panier_id": panier_id,
            "livraison_nom_complet": "Jean Eudes",
            "livraison_telephone": "+22507070707",
            "client_telephone": "+22507070707",
            "livraison_ville": "Abidjan",
            "livraison_quartier": "Cocody"
        }
        response_cmd = self.client.post(self.passer_commande_url, payload_cmd, format='json')
        self.assertEqual(response_cmd.status_code, status.HTTP_201_CREATED)

        # Vérifier la commande en base
        commande_id = response_cmd.data['id']
        cmd = Commande.objects.get(id=commande_id)
        self.assertEqual(cmd.client, self.client_profile)
        self.assertEqual(cmd.livraison_nom_complet, "Jean Eudes")

    def test_authenticated_checkout_unchanged(self):
        # Connecter le client
        self.client.force_authenticate(user=self.client_user)

        # 1. Ajouter au panier direct en tant que connecté
        payload = {
            "flacon_id": self.flacon_30ml.id,
            "quantite": 1,
            "lignes": [{"lot_essence_id": self.lot_rose.id, "quantite_ml": 10.0}]
        }
        response = self.client.post(self.composition_directe_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        panier_id = response.data['id']
        
        # Vérifier que le parfum perso créé est bien lié au client connecté
        p = ParfumPersonnalise.objects.latest('id')
        self.assertEqual(p.client, self.client_profile)

        # 2. Passer la commande sans nom/téléphone de livraison (doit auto-remplir depuis le profil)
        payload_cmd = {
            "panier_id": panier_id,
            "livraison_ville": "Abidjan",
            "livraison_quartier": "Cocody"
        }
        response_cmd = self.client.post(self.passer_commande_url, payload_cmd, format='json')
        self.assertEqual(response_cmd.status_code, status.HTTP_201_CREATED)

        cmd = Commande.objects.get(id=response_cmd.data['id'])
        self.assertEqual(cmd.client, self.client_profile)
        self.assertEqual(cmd.livraison_nom_complet, "Jean Eudes")  # auto-rempli
        self.assertEqual(cmd.livraison_telephone, "+22507070707")  # auto-rempli
