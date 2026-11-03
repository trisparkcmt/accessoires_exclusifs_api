from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from unittest.mock import patch

from catalogue.models import Parfum
from orders.models import Commande, Panier, CodePromoAdmin
from utilisateur.models import Client, Notification, Serveuse

User = get_user_model()


class AdminPromoTestCase(APITestCase):

    def setUp(self):
        # 1. Création des utilisateurs
        self.superadmin = User.objects.create_superuser(
            email="superadmin@accessoireexclusif.com",
            password="superpassword123",
            telephone="+22501010101"
        )
        self.staff_user = User.objects.create_user(
            username="staff1",
            email="staff1@accessoireexclusif.com",
            password="staffpassword",
            telephone="+22502020202",
            is_staff=True,
            is_superuser=False
        )
        self.client_user1 = User.objects.create_user(
            username="client1",
            email="client1@accessoireexclusif.com",
            password="clientpassword1",
            telephone="+22503030303",
            first_name="Jean",
            last_name="Dupont"
        )
        self.client1 = self.client_user1.client

        self.client_user2 = User.objects.create_user(
            username="client2",
            email="client2@accessoireexclusif.com",
            password="clientpassword2",
            telephone="+22504040404",
            first_name="Awa",
            last_name="Koné"
        )
        self.client2 = self.client_user2.client

        # Serveuse active
        self.serveuse_user = User.objects.create_user(
            username="serveuse",
            email="serveuse@accessoireexclusif.com",
            password="serveusepassword",
            telephone="+22505050505"
        )
        self.serveuse_profile = Serveuse.objects.create(
            client=self.serveuse_user.client,
            actif=True
        )

        # 2. Création de produits
        self.parfum = Parfum.objects.create(
            nom="Parfum Test Exclusif",
            contenance_ml=100,
            prix_unitaire=Decimal("40000.00"),
            stock_quantite=10,
            actif=True,
            reference_sku="SKU-PARF-EXCL"
        )

        # URLs
        self.list_url = reverse('admin-codes-promo-list')
        self.appliquer_url = reverse('panier-appliquer-promo')
        self.pos_creer_url = reverse('pos-commandes-creer')

    @patch('django.core.mail.send_mail')
    def test_admin_crud_permissions(self, mock_send_mail):
        # A. Client standard ne peut pas faire de CRUD (403)
        self.client.force_authenticate(user=self.client_user1)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payload = {
            "code": "PROMO30",
            "reduction_pourcentage": "30.00",
            "clients_autorises": [self.client1.id]
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # B. Staff (non superuser) ne peut pas faire de CRUD (403)
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # C. Superadmin peut faire du CRUD (200/201)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        promo_id = response.data['id']
        detail_url = reverse('admin-codes-promo-detail', args=[promo_id])
        
        # Superadmin Get detail
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Superadmin Update
        update_payload = {
            "code": "PROMO30-UPD",
            "reduction_pourcentage": "25.00",
            "clients_autorises": [self.client1.id, self.client2.id]
        }
        response = self.client.put(detail_url, update_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['code'], "PROMO30-UPD")

        # Superadmin Delete
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @patch('django.core.mail.send_mail')
    def test_notifications_sent_on_creation(self, mock_send_mail):
        self.client.force_authenticate(user=self.superadmin)
        
        # Supprimer les notifications existantes pour repartir à zéro
        Notification.objects.all().delete()

        payload = {
            "code": "EXCLUSIF50",
            "reduction_pourcentage": "50.00",
            "clients_autorises": [self.client1.id]
        }

        # Création du code
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Vérifier que le mail a été envoyé et la notification en base créée
        mock_send_mail.assert_called_once()
        notifs = Notification.objects.filter(recipient=self.client_user1, type='code_promo_admin')
        self.assertEqual(notifs.count(), 1)
        self.assertIn("EXCLUSIF50", notifs.first().message)

        # Réinitialiser le mock
        mock_send_mail.reset_mock()
        Notification.objects.all().delete()

        # Une mise à jour du code promo (ex: modifier le code ou ajouter un client)
        # ne doit PAS renvoyer de notification/mail automatique (car "la notif s'envoie rien qu'au moment de la création")
        promo_id = response.data['id']
        detail_url = reverse('admin-codes-promo-detail', args=[promo_id])
        update_payload = {
            "code": "EXCLUSIF50",
            "reduction_pourcentage": "50.00",
            "clients_autorises": [self.client1.id, self.client2.id]
        }
        response = self.client.put(detail_url, update_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Pas de nouvel envoi
        mock_send_mail.assert_not_called()
        self.assertEqual(Notification.objects.filter(type='code_promo_admin').count(), 0)

    @patch('django.core.mail.send_mail')
    def test_apply_admin_promo_to_panier(self, mock_send_mail):
        # 1. Créer le code promo admin
        self.client.force_authenticate(user=self.superadmin)
        payload = {
            "code": "REDUC20",
            "reduction_pourcentage": "20.00",
            "clients_autorises": [self.client1.id]
        }
        self.client.post(self.list_url, payload, format='json')

        # 2. Créer un panier pour client1 et y ajouter le parfum
        panier = Panier.objects.create(client=self.client1)
        from orders.models import PanierLigneParfum
        PanierLigneParfum.objects.create(
            panier=panier,
            parfum=self.parfum,
            quantite=1,
            prix_unitaire_snapshot=self.parfum.prix_unitaire,
            sous_total=self.parfum.prix_unitaire
        )
        panier.recalculer_total() # 40000.00

        # 3. Client 1 (autorisé) applique le code promo REDUC20
        self.client.force_authenticate(user=self.client_user1)
        response = self.client.post(self.appliquer_url, {
            "code_promo": "REDUC20",
            "panier_id": panier.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['remise_montant']), 8000.0) # 20% de 40000
        self.assertEqual(float(response.data['total']), 32000.0)

        # 4. Client 2 (non autorisé) tente d'appliquer le code promo REDUC20
        panier2 = Panier.objects.create(client=self.client2)
        PanierLigneParfum.objects.create(
            panier=panier2,
            parfum=self.parfum,
            quantite=1,
            prix_unitaire_snapshot=self.parfum.prix_unitaire,
            sous_total=self.parfum.prix_unitaire
        )
        panier2.recalculer_total()

        self.client.force_authenticate(user=self.client_user2)
        response = self.client.post(self.appliquer_url, {
            "code_promo": "REDUC20",
            "panier_id": panier2.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Vous n'êtes pas autorisé", response.data['code_promo'][0])

    @patch('django.core.mail.send_mail')
    def test_usage_unique_rule(self, mock_send_mail):
        # 1. Créer le code promo admin
        self.client.force_authenticate(user=self.superadmin)
        payload = {
            "code": "ONETIME",
            "reduction_pourcentage": "10.00",
            "clients_autorises": [self.client1.id]
        }
        self.client.post(self.list_url, payload, format='json')

        # 2. Client 1 passe une commande avec ce code promo
        commande = Commande.objects.create(
            client=self.client1,
            code_promo_utilise="ONETIME",
            sous_total=Decimal("40000.00"),
            remise_code_promo=Decimal("4000.00"),
            total_ttc=Decimal("36000.00"),
            livraison_nom_complet="Jean Dupont",
            livraison_telephone="+22503030303",
            statut="validé",
            statut_paiement="payé"
        )

        # 3. Client 1 tente de réappliquer le code à un nouveau panier
        panier = Panier.objects.create(client=self.client1)
        from orders.models import PanierLigneParfum
        PanierLigneParfum.objects.create(
            panier=panier,
            parfum=self.parfum,
            quantite=1,
            prix_unitaire_snapshot=self.parfum.prix_unitaire,
            sous_total=self.parfum.prix_unitaire
        )
        panier.recalculer_total()

        self.client.force_authenticate(user=self.client_user1)
        response = self.client.post(self.appliquer_url, {
            "code_promo": "ONETIME",
            "panier_id": panier.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("déjà utilisé", response.data['code_promo'][0])

        # 4. Si la commande précédente est annulée, le code peut être réutilisé
        # On utilise .update() pour bypasser le hook save() qui force statut='livrée'
        # quand statut_paiement='payé'.
        Commande.objects.filter(pk=commande.pk).update(statut="annulée")

        response = self.client.post(self.appliquer_url, {
            "code_promo": "ONETIME",
            "panier_id": panier.id
        }, format='json')
        if response.status_code != 200:
            print("FAILURE DETAIL IN TEST:", response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('django.core.mail.send_mail')
    def test_pos_validation_code_promo_admin(self, mock_send_mail):
        # 1. Créer le code promo admin
        self.client.force_authenticate(user=self.superadmin)
        payload = {
            "code": "POSADMIN",
            "reduction_pourcentage": "15.00",
            "clients_autorises": [self.client1.id]
        }
        self.client.post(self.list_url, payload, format='json')

        # 2. Essai de création de commande POS avec le code
        self.client.force_authenticate(user=self.serveuse_user)

        # A. Avec un client non autorisé (client2)
        payload_pos_fail = {
            "client_email": "client2@accessoireexclusif.com",
            "code_promo": "POSADMIN",
            "lignes": [
                {"type": "parfum", "id": self.parfum.id, "quantite": 1}
            ]
        }
        response = self.client.post(self.pos_creer_url, payload_pos_fail, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Ce client n'est pas autorisé", response.data['code_promo'][0])

        # B. Avec le client autorisé (client1)
        payload_pos_success = {
            "client_email": "client1@accessoireexclusif.com",
            "code_promo": "POSADMIN",
            "lignes": [
                {"type": "parfum", "id": self.parfum.id, "quantite": 1}
            ]
        }
        response = self.client.post(self.pos_creer_url, payload_pos_success, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        commande = Commande.objects.get(numero_commande=response.data['numero_commande'])
        self.assertEqual(commande.remise_code_promo, Decimal("6000.00")) # 15% de 40000

        # C. Tenter de réutiliser le code une seconde fois pour client1 (doit échouer)
        response2 = self.client.post(self.pos_creer_url, payload_pos_success, format='json')
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("déjà utilisé", response2.data['code_promo'][0])

    @patch('django.core.mail.send_mail')
    def test_prestataire_commission_and_notification(self, mock_send_mail):
        from utilisateur.models import Prestataire, CommissionLog, Notification
        
        # 1. Créer un prestataire avec son code promo et taux de commission
        # client2.user sera le prestataire
        prestataire = Prestataire.objects.create(
            client=self.client2,
            code_promo="PREST20",
            reduction_client_pourcentage=Decimal("10.00"),
            taux_commission=Decimal("5.00"),
            solde_commission=Decimal("0.00"),
            statut="actif"
        )
        
        # 2. Créer un panier pour client1 et appliquer le code promo PREST20
        panier = Panier.objects.create(client=self.client1)
        from orders.models import PanierLigneParfum
        PanierLigneParfum.objects.create(
            panier=panier,
            parfum=self.parfum,
            quantite=1,
            prix_unitaire_snapshot=self.parfum.prix_unitaire,
            sous_total=self.parfum.prix_unitaire
        )
        panier.recalculer_total() # 40000.00
        
        # Appliquer le code promo du prestataire
        self.client.force_authenticate(user=self.client_user1)
        response = self.client.post(self.appliquer_url, {
            "code_promo": "PREST20",
            "panier_id": panier.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Rafraîchir le panier pour vérifier qu'il ne s'est pas effacé lors de la réactualisation !
        response_detail = self.client.get(reverse('panier-detail') + f"?panier_id={panier.id}")
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(response_detail.data['code_promo_applique'], "PREST20")
        self.assertEqual(float(response_detail.data['remise_montant']), 4000.0) # 10% de 40000
        
        # 3. Passer la commande directement après avoir appliqué le code promo
        payload_passer = {
            "panier_id": panier.id,
            "livraison_nom_complet": "Jean Dupont",
            "livraison_telephone": "+22503030303"
        }
        response_passer = self.client.post(reverse('commande-passer'), payload_passer, format='json')
        self.assertEqual(response_passer.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response_passer.data['code_promo_utilise'], "PREST20")
        self.assertEqual(float(response_passer.data['remise_code_promo']), 4000.0)
        
        # Récupérer l'objet commande
        commande = Commande.objects.get(numero_commande=response_passer.data['numero_commande'])
        self.assertEqual(commande.commission_montant, Decimal("1800.00")) # 5% de 36000 (40000 - 4000)
        self.assertEqual(commande.commission_statut, 'non_versée')
        self.assertEqual(prestataire.solde_commission, Decimal("0.00"))
        
        # 4. Payer la commande (statut_paiement = 'payé')
        # Nettoyer d'abord les notifications
        Notification.objects.all().delete()
        
        commande.statut_paiement = 'payé'
        commande.save()
        
        # Recharger le prestataire
        prestataire.refresh_from_db()
        self.assertEqual(prestataire.solde_commission, Decimal("1800.00"))
        
        # Vérifier que le prestataire a reçu une notification de versement
        notif_versement = Notification.objects.filter(recipient=self.client_user2, type='commission').first()
        self.assertIsNotNone(notif_versement)
        self.assertIn("FCFA de commission", notif_versement.message)
        self.assertIn("PREST20", notif_versement.message)
        
        # 5. Simulation de l'annulation d'une commande (statut = 'annulée')
        # Nettoyer les notifications
        Notification.objects.all().delete()
        
        Commande.objects.filter(pk=commande.pk).update(statut='annulée', statut_paiement='échoué')
        commande.refresh_from_db()
        commande.save()
        
        # Recharger le prestataire et vérifier que le solde a été récupéré
        prestataire.refresh_from_db()
        self.assertEqual(prestataire.solde_commission, Decimal("0.00"))
        
        # Vérifier que le prestataire a reçu une notification de remboursement/annulation
        notif_annulation = Notification.objects.filter(recipient=self.client_user2, type='commission').first()
        self.assertIsNotNone(notif_annulation)
        self.assertIn("retirée suite à l'annulation", notif_annulation.message)

