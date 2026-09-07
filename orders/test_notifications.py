from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from catalogue.models import CategorieParfum, Parfum
from laboratoire.models import ParfumPersonnalise
from orders.models import (
    Commande, CommandeLigneParfum, CommandeLigneParfumPerso,
)
from utilisateur.models import Client, Livreur, Notification, Prestataire

User = get_user_model()


class NotificationCommandeTest(APITestCase):

    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client_notif",
            email="client_notif@test.com",
            password="password123",
            telephone="+22501000001",
        )
        self.client_profile = self.client_user.client

        self.prestataire_user = User.objects.create_user(
            username="prest_notif",
            email="prest_notif@test.com",
            password="password123",
            telephone="+22501000002",
        )
        self.prestataire = Prestataire.objects.create(
            client=self.prestataire_user.client,
            code_promo="NOTIF20",
            taux_commission=Decimal("5.00"),
            reduction_client_pourcentage=Decimal("10.00"),
            statut="actif",
        )

        self.livreur_user = User.objects.create_user(
            username="livreur_notif",
            email="livreur_notif@test.com",
            password="password123",
            telephone="+22501000003",
        )
        self.livreur = Livreur.objects.create(client=self.livreur_user.client)

        self.admin_user = User.objects.create_user(
            username="admin_notif",
            email="admin_notif@test.com",
            password="password123",
            telephone="+22501000004",
            is_staff=True,
        )

        self.commande = Commande.objects.create(
            client=self.client_profile,
            prestataire=self.prestataire,
            code_promo_utilise="NOTIF20",
            sous_total=Decimal("40000.00"),
            remise_code_promo=Decimal("4000.00"),
            total_ttc=Decimal("36000.00"),
            commission_montant=Decimal("1800.00"),
            livraison_nom_complet="Client Test",
            livraison_telephone="+22501000001",
            statut="en_attente",
            statut_paiement="en_attente",
            commission_statut="non_versée",
        )
        self.parfum = Parfum.objects.create(
            nom="Parfum Notif",
            slug="parfum-notif",
            reference_sku="SKU-NOTIF",
            contenance_ml=50,
            prix_unitaire=Decimal("40000.00"),
            actif=True,
        )
        CommandeLigneParfum.objects.create(
            commande=self.commande,
            parfum=self.parfum,
            nom_snapshot=self.parfum.nom,
            quantite=1,
            prix_unitaire_snapshot=self.parfum.prix_unitaire,
            sous_total=self.parfum.prix_unitaire,
        )

    def test_prestataire_notifie_au_paiement_avec_code_promo(self):
        Notification.objects.all().delete()

        self.commande.statut_paiement = "payé"
        self.commande.save()

        notif = Notification.objects.filter(
            recipient=self.prestataire_user,
            type="commission",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("NOTIF20", notif.message)
        self.assertIn("1800", notif.message)

    def test_livreur_notifie_a_l_assignation(self):
        Notification.objects.all().delete()

        self.commande.livreur = self.livreur
        self.commande.save()

        notif = Notification.objects.filter(
            recipient=self.livreur_user,
            type="livreur_commande_assignee",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn(self.commande.numero_commande, notif.message)

    def test_livreur_notifie_a_l_annulation(self):
        self.commande.livreur = self.livreur
        self.commande.statut_livraison = "assignée"
        self.commande.save()
        Notification.objects.all().delete()

        self.commande.statut = "annulée"
        self.commande.save()

        notif = Notification.objects.filter(
            recipient=self.livreur_user,
            type="livreur_commande_annulee",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("annulée", notif.message.lower())

    def test_admin_notifie_validation_parfum_perso(self):
        from catalogue.models import Flacon, TypeFlacon

        type_flacon = TypeFlacon.objects.create(nom="Flacon test")
        flacon = Flacon.objects.create(
            type_flacon=type_flacon,
            nom="Flacon 50ml",
            reference_sku="FL-50",
            contenance_ml=50,
            prix_unitaire=Decimal("5000.00"),
            stock_quantite=10,
        )
        parfum_perso = ParfumPersonnalise.objects.create(
            client=self.client_profile,
            flacon=flacon,
            nom="Mon parfum",
            prix_essences=Decimal("0.00"),
            prix_flacon_snapshot=flacon.prix_unitaire,
            prix_total=flacon.prix_unitaire,
            statut="validé",
        )
        CommandeLigneParfumPerso.objects.create(
            commande=self.commande,
            parfum_personnalise=parfum_perso,
            quantite=1,
            prix_snapshot=Decimal("5000.00"),
            sous_total=Decimal("5000.00"),
        )
        Notification.objects.all().delete()

        self.commande.statut = "validé"
        self.commande.save()

        notif = Notification.objects.filter(
            recipient=self.admin_user,
            type="commande_parfum_perso",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn(self.commande.numero_commande, notif.message)


class NotificationPromotionTest(APITestCase):

    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client_promo",
            email="client_promo@test.com",
            password="password123",
            telephone="+22502000001",
        )
        self.categorie = CategorieParfum.objects.create(
            nom="Oriental",
            slug="oriental-promo",
            taux_reduction=Decimal("0"),
        )

    def test_clients_notifies_promotion_categorie(self):
        Notification.objects.all().delete()

        self.categorie.taux_reduction = Decimal("20.00")
        self.categorie.message_promotion = "20% sur tous les parfums orientaux"
        self.categorie.save()

        notifs = Notification.objects.filter(
            recipient=self.client_user,
            type="promotion_catalogue",
        )
        self.assertEqual(notifs.count(), 1)
        self.assertIn("20%", notifs.first().message)

    def test_clients_notifies_promotion_produit(self):
        parfum = Parfum.objects.create(
            nom="Rose Promo",
            slug="rose-promo",
            reference_sku="SKU-ROSE",
            contenance_ml=50,
            prix_unitaire=Decimal("25000.00"),
            prix_promotionnel=Decimal("20000.00"),
            categorie=self.categorie,
            actif=True,
        )
        Notification.objects.all().delete()

        parfum.prix_promotionnel = Decimal("18000.00")
        parfum.save()

        # Pas de notif si promotion déjà active (changement de prix seulement)
        self.assertEqual(
            Notification.objects.filter(type="promotion_catalogue").count(),
            0,
        )

        parfum.prix_promotionnel = None
        parfum.save()

        parfum.prix_promotionnel = Decimal("18000.00")
        parfum.save()

        notif = Notification.objects.filter(
            recipient=self.client_user,
            type="promotion_catalogue",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("Rose Promo", notif.message)
