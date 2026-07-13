from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from catalogue.models import Parfum, Accessoire, ProduitFiniEssence, Essence, LotEssence
from orders.models import Commande, Facture
from utilisateur.models import Client, Serveuse, Prestataire
from allauth.account.models import EmailAddress

User = get_user_model()


class POSTestCase(APITestCase):

    def setUp(self):
        # 1. Création des utilisateurs
        self.superadmin = User.objects.create_superuser(
            email="admin@accessoireexclusif.com",
            password="adminpassword123",
            telephone="+22501020304"
        )
        # Client lié à la serveuse
        self.serveuse_user = User.objects.create_user(
            username="serveuse",
            email="serveuse@accessoireexclusif.com",
            password="serveusepassword",
            telephone="+22502030405",
            first_name="Marie",
            last_name="Koffi"
        )
        self.serveuse_client = self.serveuse_user.client
        self.serveuse_profile = Serveuse.objects.create(
            client=self.serveuse_client,
            actif=True
        )

        # Client standard
        self.client_user = User.objects.create_user(
            username="client1",
            email="client1@accessoireexclusif.com",
            password="clientpassword",
            telephone="+22503040506",
            first_name="Jean",
            last_name="Dupont"
        )

        # Livreur
        self.livreur_user = User.objects.create_user(
            username="livreur1",
            email="livreur1@accessoireexclusif.com",
            password="livreurpassword",
            telephone="+22504050607"
        )

        # Prestataire
        self.prestataire_user = User.objects.create_user(
            username="prestataire1",
            email="prestataire1@accessoireexclusif.com",
            password="prestapas",
            telephone="+22505060708"
        )
        self.prestataire_profile = Prestataire.objects.create(
            client=self.prestataire_user.client,
            code_promo="PRESTA10",
            taux_commission=Decimal("15.00"),
            reduction_client_pourcentage=Decimal("10.00"),
            statut="actif"
        )

        # 2. Création de produits dans le catalogue
        self.parfum_actif = Parfum.objects.create(
            nom="Parfum Test Actif",
            contenance_ml=100,
            prix_unitaire=Decimal("35000.00"),
            stock_quantite=10,
            actif=True,
            reference_sku="SKU-PARF-ACTIF"
        )
        self.parfum_inactif = Parfum.objects.create(
            nom="Parfum Test Inactif",
            contenance_ml=50,
            prix_unitaire=Decimal("20000.00"),
            stock_quantite=5,
            actif=False,
            reference_sku="SKU-PARF-INACTIF"
        )

        self.accessoire_actif = Accessoire.objects.create(
            nom="Bracelet Test Actif",
            prix_unitaire=Decimal("15000.00"),
            prix_promotionnel=Decimal("12000.00"),
            stock_quantite=8,
            actif=True,
            reference_sku="SKU-ACC-ACTIF"
        )

        self.essence_base = Essence.objects.create(
            marque="Marque Ess",
            nom="Essence Lavande",
            code_reference="ESS-LAV-01",
            actif=True
        )
        LotEssence.objects.create(
            essence=self.essence_base,
            stock_ml=Decimal("1000.00"),
        )
        self.essence_produit = ProduitFiniEssence.objects.create(
            essence=self.essence_base,
            taille_ml=30,
            prix=Decimal("5000.00"),
            actif=True
        )

        # URLs
        self.search_url = reverse('pos-produits-recherche')
        self.creer_url = reverse('pos-commandes-creer')

    def test_search_permissions(self):
        # Client simple non autorisé (403)
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Livreur non autorisé (403)
        self.client.force_authenticate(user=self.livreur_user)
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Serveuse active autorisée (200)
        self.client.force_authenticate(user=self.serveuse_user)
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Admin autorisé (200)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_product_search_logic(self):
        self.client.force_authenticate(user=self.serveuse_user)

        # Recherche globale : doit retourner tous les produits actifs, triés par nom
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)  # parfum_actif, accessoire_actif, essence_produit

        # Recherche par type 'parfum'
        response = self.client.get(self.search_url, {'type': 'parfum'})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['nom'], "Parfum Test Actif")

        # Recherche par terme spécifique
        response = self.client.get(self.search_url, {'q': 'Bracelet'})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['nom'], "Bracelet Test Actif")
        self.assertEqual(response.data[0]['prix'], 12000.00)  # Utilise le prix promotionnel

        # Recherche sur un produit inactif (ne doit pas apparaître)
        response = self.client.get(self.search_url, {'q': 'Inactif'})
        self.assertEqual(len(response.data), 0)

    def test_commande_creer_permissions(self):
        # Client simple refusé (403)
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(self.creer_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Serveuse autorisée
        self.client.force_authenticate(user=self.serveuse_user)
        payload = {
            "lignes": [
                {"type": "parfum", "id": self.parfum_actif.id, "quantite": 1}
            ]
        }
        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_commande_creer_validation_stocks(self):
        self.client.force_authenticate(user=self.serveuse_user)

        # Commande d'une quantité supérieure au stock disponible (10)
        payload = {
            "lignes": [
                {"type": "parfum", "id": self.parfum_actif.id, "quantite": 15}
            ]
        }
        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Stock insuffisant", response.data['lignes'][0])

    def test_commande_creer_produit_inactif(self):
        self.client.force_authenticate(user=self.serveuse_user)

        payload = {
            "lignes": [
                {"type": "parfum", "id": self.parfum_inactif.id, "quantite": 1}
            ]
        }
        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_commande_creer_anonyme_boutique(self):
        self.client.force_authenticate(user=self.serveuse_user)

        payload = {
            "lignes": [
                {"type": "parfum", "id": self.parfum_actif.id, "quantite": 2},
                {"type": "accessoire", "id": self.accessoire_actif.id, "quantite": 1}
            ],
            "note_interne": "Paiement en espèces"
        }
        
        # État des stocks avant la commande
        parfum_stock_avant = self.parfum_actif.stock_quantite # 10
        accessoire_stock_avant = self.accessoire_actif.stock_quantite # 8

        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Vérifier la commande créée
        numero = response.data['numero_commande']
        commande = Commande.objects.get(numero_commande=numero)
        
        self.assertEqual(commande.client.user.email, "boutique@accessoireexclusif.com")
        self.assertEqual(commande.statut, "livrée")
        self.assertEqual(commande.statut_paiement, "payé")
        self.assertEqual(commande.livraison_nom_complet, "Client Boutique")
        self.assertEqual(commande.livraison_telephone, "00000000")

        # Vérifier la déduction des stocks
        self.parfum_actif.refresh_from_db()
        self.accessoire_actif.refresh_from_db()
        self.assertEqual(self.parfum_actif.stock_quantite, parfum_stock_avant - 2)
        self.assertEqual(self.accessoire_actif.stock_quantite, accessoire_stock_avant - 1)

        # Vérifier la facture générée automatiquement
        self.assertTrue(hasattr(commande, 'facture'))
        self.assertIsNotNone(commande.facture.fichier_pdf)

    def test_commande_creer_client_existant_par_email(self):
        self.client.force_authenticate(user=self.serveuse_user)

        payload = {
            "client_email": "client1@accessoireexclusif.com",
            "client_nom_complet": "Jean Dupont",
            "lignes": [
                {"type": "essence", "id": self.essence_produit.id, "quantite": 2}
            ]
        }

        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        numero = response.data['numero_commande']
        commande = Commande.objects.get(numero_commande=numero)

        self.assertEqual(commande.client, self.client_user.client)
        self.assertEqual(commande.livraison_nom_complet, "Jean Dupont")

    def test_commande_creer_nouveau_client_avec_email_allauth(self):
        self.client.force_authenticate(user=self.serveuse_user)

        email_nouveau = "nouveau.client@example.com"
        payload = {
            "client_email": email_nouveau,
            "client_nom_complet": "Marc Dogo",
            "client_telephone": "+22507080910",
            "lignes": [
                {"type": "parfum", "id": self.parfum_actif.id, "quantite": 1}
            ]
        }

        # Vérifier que le user n'existe pas encore
        self.assertFalse(User.objects.filter(email=email_nouveau).exists())

        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Le user doit maintenant exister
        user = User.objects.get(email=email_nouveau)
        self.assertEqual(user.first_name, "Marc")
        self.assertEqual(user.last_name, "Dogo")
        self.assertEqual(user.telephone, "+22507080910")

        # Son email doit être vérifié dans allauth
        email_addr = EmailAddress.objects.get(user=user, email=email_nouveau)
        self.assertTrue(email_addr.verified)
        self.assertTrue(email_addr.primary)

        # La commande doit être liée à lui
        commande = Commande.objects.get(numero_commande=response.data['numero_commande'])
        self.assertEqual(commande.client, user.client)

    def test_commande_creer_avec_code_promo_prestataire(self):
        self.client.force_authenticate(user=self.serveuse_user)

        payload = {
            "code_promo": "PRESTA10",
            "lignes": [
                {"type": "parfum", "id": self.parfum_actif.id, "quantite": 1} # 35000 FCFA
            ]
        }

        response = self.client.post(self.creer_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        commande = Commande.objects.get(numero_commande=response.data['numero_commande'])

        # Vérifier la remise appliquée (10% de 35000 = 3500)
        self.assertEqual(commande.sous_total, Decimal("35000.00"))
        self.assertEqual(commande.remise_code_promo, Decimal("3500.00"))
        self.assertEqual(commande.total_ttc, Decimal("31500.00"))
        self.assertEqual(commande.prestataire, self.prestataire_user.client.prestataire)
        self.assertEqual(commande.commission_montant, Decimal("5250.00")) # 15% de 35000
        self.assertEqual(commande.commission_statut, "versée") # la commission est versée car statut_paiement='payé'
