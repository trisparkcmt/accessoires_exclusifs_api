import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from catalogue.models import Parfum, Accessoire, MouvementStock
from orders.models import Commande, RapportJournalierCaisse
from utilisateur.models import Serveuse, Depense

User = get_user_model()


class POSRapportJournalierTests(APITestCase):

    def setUp(self):
        # 1. Superadmin
        self.superadmin = User.objects.create_superuser(
            email="admin@accessoireexclusif.com",
            password="adminpassword123",
            telephone="+22501020304"
        )

        # 2. Serveuse 1
        self.serveuse_user = User.objects.create_user(
            username="serveuse1",
            email="serveuse1@accessoireexclusif.com",
            password="serveusepassword",
            telephone="+22502030405",
            first_name="Marie",
            last_name="Koffi"
        )
        self.serveuse_profile = Serveuse.objects.create(
            client=self.serveuse_user.client,
            actif=True
        )

        # 3. Serveuse 2 (autre vendeuse)
        self.serveuse_user_2 = User.objects.create_user(
            username="serveuse2",
            email="serveuse2@accessoireexclusif.com",
            password="serveusepassword2",
            telephone="+22502030499",
            first_name="Awa",
            last_name="Traore"
        )
        self.serveuse_profile_2 = Serveuse.objects.create(
            client=self.serveuse_user_2.client,
            actif=True
        )

        # 4. Client standard (sans droits serveuse)
        self.client_user = User.objects.create_user(
            username="client1",
            email="client1@accessoireexclusif.com",
            password="clientpassword",
            telephone="+22503040506",
            first_name="Jean",
            last_name="Dupont"
        )

        # 5. Produits
        self.parfum = Parfum.objects.create(
            nom="Huile 30ml",
            contenance_ml=30,
            prix_unitaire=Decimal("15000.00"),
            stock_quantite=20,
            actif=True,
            reference_sku="SKU-HUILE-30"
        )
        self.accessoire = Accessoire.objects.create(
            nom="Bracelet Cuir",
            prix_unitaire=Decimal("10000.00"),
            stock_quantite=15,
            actif=True,
            reference_sku="SKU-BRACELET"
        )

        # URLs
        self.pos_creer_url = reverse('pos-commandes-creer')
        self.apercu_url = reverse('pos-rapport-apercu')
        self.cloturer_url = reverse('pos-rapport-cloturer')
        self.liste_url = reverse('pos-rapport-list')

    def test_permissions_rapport_endpoints(self):
        # Client standard -> 403
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(self.apercu_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(self.cloturer_url, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Serveuse active -> 200 sur aperçu
        self.client.force_authenticate(user=self.serveuse_user)
        response = self.client.get(self.apercu_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_apercu_et_cloture_journee_caissiere(self):
        # Authentification en tant que Marie
        self.client.force_authenticate(user=self.serveuse_user)

        # 1. Réalisation d'une vente POS par Marie
        payload_vente = {
            "lignes": [
                {"type": "parfum", "id": self.parfum.id, "quantite": 2},
                {"type": "accessoire", "id": self.accessoire.id, "quantite": 1}
            ]
        }
        res_vente = self.client.post(self.pos_creer_url, payload_vente, format='json')
        self.assertEqual(res_vente.status_code, status.HTTP_201_CREATED)
        total_attendu = (Decimal("15000.00") * 2) + Decimal("10000.00")  # 40000.00

        # Vérification que le vendeur a bien été enregistré sur la Commande
        numero_cmd = res_vente.data["numero_commande"]
        cmd = Commande.objects.get(numero_commande=numero_cmd)
        self.assertEqual(cmd.vendeur, self.serveuse_user)

        # 2. Ajout d'un mouvement de stock par Marie (réassort)
        MouvementStock.objects.create(
            type_produit="parfum",
            produit_id=self.parfum.id,
            nom_produit=self.parfum.nom,
            quantite_avant=Decimal("10.00"),
            quantite_apres=Decimal("20.00"),
            quantite_ajoutee=Decimal("10.00"),
            utilisateur=self.serveuse_user
        )

        # 3. Ajout d'une dépense de caisse par Marie (transport)
        Depense.objects.create(
            titre="Transport",
            description="Transport livraison urgence",
            montant=Decimal("2000.00"),
            cree_par=self.serveuse_user
        )

        # 4. Appel GET aperçu
        res_apercu = self.client.get(self.apercu_url)
        self.assertEqual(res_apercu.status_code, status.HTTP_200_OK)
        data_ap = res_apercu.data

        self.assertEqual(Decimal(str(data_ap["recette_totale"])), total_attendu)
        self.assertEqual(Decimal(str(data_ap["total_depenses"])), Decimal("2000.00"))
        self.assertEqual(len(data_ap["sorties_articles"]), 2)
        self.assertEqual(len(data_ap["entrees_stock"]), 1)
        self.assertEqual(len(data_ap["depenses"]), 1)
        self.assertIn("📅 Rapport du", data_ap["apercu_texte_whatsapp"])
        self.assertIn("Huile 30ml (2)", data_ap["apercu_texte_whatsapp"])
        self.assertIn("Bracelet Cuir (1)", data_ap["apercu_texte_whatsapp"])
        self.assertIn("2.000f Transport", data_ap["apercu_texte_whatsapp"])

        # 5. Clôture de la journée avec saisie manuelle
        payload_cloture = {
            "heure_arrivee": "09h00",
            "heure_depart": "18h30",
            "actions_communication": "WhatsApp statut + TikTok live",
            "observations": "Très bonne affluence l'après-midi.",
            "autres_donnees_manuelles": {
                "recu_cash": "40000 FCFA",
                "recu_depot": "0 FCFA"
            }
        }
        res_cloture = self.client.post(self.cloturer_url, payload_cloture, format='json')
        self.assertEqual(res_cloture.status_code, status.HTTP_201_CREATED)
        rapport_id = res_cloture.data["id"]

        # Vérification en base de données
        rapport = RapportJournalierCaisse.objects.get(id=rapport_id)
        self.assertEqual(rapport.caissiere, self.serveuse_user)
        self.assertEqual(rapport.heure_arrivee, "09h00")
        self.assertEqual(rapport.heure_depart, "18h30")
        # reste_en_caisse est calculé automatiquement = recette - dépenses
        self.assertEqual(rapport.reste_en_caisse, total_attendu - Decimal("2000.00"))
        self.assertEqual(rapport.actions_communication, "WhatsApp statut + TikTok live")
        self.assertEqual(rapport.recette_totale, total_attendu)
        self.assertEqual(rapport.total_depenses, Decimal("2000.00"))

        # Vérification que le texte WhatsApp est stocké avec le format demandé
        self.assertIn("📅 Rapport du", rapport.texte_formate)
        self.assertIn("🕒 Horaires :", rapport.texte_formate)
        self.assertIn("Arrivée : 09h00", rapport.texte_formate)
        self.assertIn("Départ : 18h30", rapport.texte_formate)
        self.assertIn("sorties parfums / accessoires", rapport.texte_formate)
        self.assertIn("Entrées parfums / accessoires", rapport.texte_formate)
        self.assertIn("*bilan financier*", rapport.texte_formate)
        self.assertIn("📲 Actions de communication digitale :", rapport.texte_formate)

        # Vérification du PDF généré
        self.assertTrue(bool(rapport.fichier_pdf))
        self.assertIsNotNone(res_cloture.data.get("pdf_url"))

        # 6. Consultation de la liste et du détail
        res_list = self.client.get(self.liste_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data["results"] if "results" in res_list.data else res_list.data), 1)

        detail_url = reverse('pos-rapport-detail', kwargs={'pk': rapport_id})
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data["id"], rapport_id)
        self.assertIn("pdf_url", res_detail.data)

    def test_isolation_entre_caissieres_et_acces_admin(self):
        """
        Vérifie strictement que :
        - Une caissière A ne voit QUE ses propres rapports et ne peut JAMAIS accéder au rapport de la caissière B.
        - Un superadmin a accès à tous les rapports, peut filtrer par caissière, et accéder au détail de n'importe quel rapport.
        """
        # Création d'un rapport pour Serveuse 1 (Marie)
        rapport_1 = RapportJournalierCaisse.objects.create(
            caissiere=self.serveuse_user,
            date=datetime.date(2026, 11, 10),
            heure_arrivee="09h00",
            heure_depart="18h00",
            recette_totale=Decimal("50000.00"),
            total_depenses=Decimal("0.00"),
            reste_en_caisse=Decimal("50000.00")
        )

        # Création d'un rapport pour Serveuse 2 (Awa)
        rapport_2 = RapportJournalierCaisse.objects.create(
            caissiere=self.serveuse_user_2,
            date=datetime.date(2026, 11, 10),
            heure_arrivee="10h00",
            heure_depart="19h00",
            recette_totale=Decimal("80000.00"),
            total_depenses=Decimal("5000.00"),
            reste_en_caisse=Decimal("75000.00")
        )

        # --- TEST 1 : Caissière 1 (Marie) ---
        self.client.force_authenticate(user=self.serveuse_user)

        # La liste ne doit contenir QUE le rapport 1 de Marie
        res_list = self.client.get(self.liste_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        ids_visibles = [r["id"] for r in res_list.data]
        self.assertIn(rapport_1.id, ids_visibles)
        self.assertNotIn(rapport_2.id, ids_visibles)
        self.assertEqual(len(ids_visibles), 1)

        # Accès au détail de son propre rapport -> 200 OK
        detail_1 = reverse('pos-rapport-detail', kwargs={'pk': rapport_1.id})
        res_d1 = self.client.get(detail_1)
        self.assertEqual(res_d1.status_code, status.HTTP_200_OK)

        # Tentative d'accès au rapport d'Awa (rapport 2) -> 404 (non trouvé dans son scope)
        detail_2 = reverse('pos-rapport-detail', kwargs={'pk': rapport_2.id})
        res_d2 = self.client.get(detail_2)
        self.assertEqual(res_d2.status_code, status.HTTP_404_NOT_FOUND)

        # Tentative de consulter l'aperçu d'Awa en passant ?caissiere_id -> ignoré, retourne l'aperçu de Marie
        res_ap = self.client.get(self.apercu_url, {'caissiere_id': self.serveuse_user_2.id})
        self.assertEqual(res_ap.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ap.data['caissiere_id'], self.serveuse_user.id)

        # --- TEST 2 : Caissière 2 (Awa) ---
        self.client.force_authenticate(user=self.serveuse_user_2)

        # La liste ne doit contenir QUE le rapport 2 d'Awa
        res_list_2 = self.client.get(self.liste_url)
        self.assertEqual(res_list_2.status_code, status.HTTP_200_OK)
        ids_visibles_2 = [r["id"] for r in res_list_2.data]
        self.assertIn(rapport_2.id, ids_visibles_2)
        self.assertNotIn(rapport_1.id, ids_visibles_2)

        # Accès au rapport 1 de Marie par Awa -> 404
        res_awa_vers_marie = self.client.get(detail_1)
        self.assertEqual(res_awa_vers_marie.status_code, status.HTTP_404_NOT_FOUND)

        # --- TEST 3 : Superadministrateur ---
        self.client.force_authenticate(user=self.superadmin)

        # L'admin voit TOUS les rapports
        res_admin_list = self.client.get(self.liste_url)
        self.assertEqual(res_admin_list.status_code, status.HTTP_200_OK)
        ids_admin = [r["id"] for r in res_admin_list.data]
        self.assertIn(rapport_1.id, ids_admin)
        self.assertIn(rapport_2.id, ids_admin)
        self.assertGreaterEqual(len(ids_admin), 2)

        # L'admin filtre par caissière_id=serveuse_user_2
        res_filter = self.client.get(self.liste_url, {'caissiere_id': self.serveuse_user_2.id})
        self.assertEqual(res_filter.status_code, status.HTTP_200_OK)
        ids_filtres = [r["id"] for r in res_filter.data]
        self.assertIn(rapport_2.id, ids_filtres)
        self.assertNotIn(rapport_1.id, ids_filtres)

        # L'admin a accès au détail de n'importe quel rapport
        res_ad_d1 = self.client.get(detail_1)
        self.assertEqual(res_ad_d1.status_code, status.HTTP_200_OK)
        res_ad_d2 = self.client.get(detail_2)
        self.assertEqual(res_ad_d2.status_code, status.HTTP_200_OK)

    def test_alias_cloture_depense_et_apercu_enrichi(self):
        """
        Vérifie :
        1. Que le reste_en_caisse est calculé automatiquement = recette_totale - total_depenses.
        2. Que 'Dépense' est utilisé dans le texte WhatsApp et le rapport au lieu de 'Retrait'.
        3. Que les dépenses passées manuellement dans le POST sont bien prises en compte.
        4. Que l'aperçu (GET et POST) retourne bien reste_en_caisse calculé et communication_digitale.
        """
        self.client.force_authenticate(user=self.serveuse_user)

        # 1. Clôture avec communication_digitale et liste de dépenses manuelles
        #    reste_en_caisse n'est PAS envoyé — il est calculé automatiquement
        payload = {
            "heure_arrivee": "08h30",
            "heure_depart": "19h00",
            "communication_digitale": "Campagne TikTok et WhatsApp live",
            "observations": "Rien à signaler",
            "depenses": [
                {"titre": "Achat emballages", "montant": 3000, "description": "Sacs kraft"}
            ]
        }
        res = self.client.post(self.cloturer_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.data

        # recette_totale = 0 (pas de vente POS dans ce test), total_depenses = 3000
        # reste_en_caisse calculé = 0 - 3000 = -3000
        expected_reste = Decimal("0.00") - Decimal("3000.00")
        self.assertEqual(Decimal(str(data["reste_en_caisse"])), expected_reste)
        self.assertEqual(Decimal(str(data["reste_caisse"])), expected_reste)
        self.assertEqual(data["actions_communication"], "Campagne TikTok et WhatsApp live")
        self.assertEqual(data["communication_digitale"], "Campagne TikTok et WhatsApp live")
        self.assertEqual(Decimal(str(data["total_depenses"])), Decimal("3000.00"))
        self.assertEqual(len(data["depenses"]), 1)

        # Vérifier que "Retrait" n'est PAS utilisé et que "Dépense" EST utilisé
        texte_wa = data["texte_formate"]
        self.assertIn("Dépense  -  3.000f Achat emballages", texte_wa)
        self.assertNotIn("Retrait  -", texte_wa)
        self.assertIn("Campagne TikTok et WhatsApp live", texte_wa)

        # 2. Vérification que l'aperçu GET après clôture retourne le reste calculé
        res_ap = self.client.get(self.apercu_url)
        self.assertEqual(res_ap.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(res_ap.data["reste_en_caisse"])), expected_reste)
        self.assertEqual(res_ap.data["communication_digitale"], "Campagne TikTok et WhatsApp live")
        self.assertIn("Campagne TikTok et WhatsApp live", res_ap.data["apercu_texte_whatsapp"])

        # 3. Vérification de l'aperçu POST avec surcharge dynamique (com uniquement, reste_en_caisse est auto)
        payload_preview = {
            "communication_digitale": "Reels Instagram publiés"
        }
        res_post_ap = self.client.post(self.apercu_url, payload_preview, format='json')
        self.assertEqual(res_post_ap.status_code, status.HTTP_200_OK)
        # reste_en_caisse est toujours calculé automatiquement
        self.assertEqual(Decimal(str(res_post_ap.data["reste_en_caisse"])), expected_reste)
        self.assertEqual(res_post_ap.data["communication_digitale"], "Reels Instagram publiés")
        self.assertIn("Reels Instagram publiés", res_post_ap.data["apercu_texte_whatsapp"])

    def test_isolation_stock_et_depenses_entre_caissieres(self):
        """
        Garantit que chaque caissière ne voit STRICTEMENT QUE ses propres actions :
        - Les entrées de stock de la caissière 1 n'apparaissent JAMAIS chez la caissière 2.
        - Les dépenses de la caissière 1 n'apparaissent JAMAIS chez la caissière 2.
        - Sur l'endpoint des mouvements de stock, une serveuse ne voit QUE ses propres mouvements.
        """
        # 1. Marie (caissière 1) effectue une entrée de stock et une dépense
        MouvementStock.objects.create(
            type_produit="parfum",
            produit_id=self.parfum.id,
            nom_produit=self.parfum.nom,
            quantite_avant=Decimal("0.00"),
            quantite_apres=Decimal("15.00"),
            quantite_ajoutee=Decimal("15.00"),
            utilisateur=self.serveuse_user  # Marie
        )
        Depense.objects.create(
            titre="Transport Marie",
            montant=Decimal("5000.00"),
            cree_par=self.serveuse_user  # Marie
        )

        # 2. Awa (caissière 2) consulte son aperçu
        self.client.force_authenticate(user=self.serveuse_user_2)
        res_awa = self.client.get(self.apercu_url)
        self.assertEqual(res_awa.status_code, status.HTTP_200_OK)
        # Awa ne doit avoir AUCUNE entrée de stock ni dépense
        self.assertEqual(len(res_awa.data["entrees_stock"]), 0)
        self.assertEqual(len(res_awa.data["depenses"]), 0)
        self.assertEqual(Decimal(str(res_awa.data["total_depenses"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(res_awa.data["reste_en_caisse"])), Decimal("0.00"))

        # 3. Awa consulte l'API générale des mouvements de stock
        mouvements_url = reverse('mouvementstock-list')
        res_mouvements_awa = self.client.get(mouvements_url)
        self.assertEqual(res_mouvements_awa.status_code, status.HTTP_200_OK)
        # Awa n'a pas créé de mouvement, elle ne doit rien voir
        items_awa = res_mouvements_awa.data if isinstance(res_mouvements_awa.data, list) else res_mouvements_awa.data.get('results', [])
        self.assertEqual(len(items_awa), 0)

        # 4. Superadmin consulte les mouvements de stock -> voit tous les mouvements (créations initiales + ajout Marie)
        self.client.force_authenticate(user=self.superadmin)
        res_mouvements_admin = self.client.get(mouvements_url)
        self.assertEqual(res_mouvements_admin.status_code, status.HTTP_200_OK)
        items_admin = res_mouvements_admin.data if isinstance(res_mouvements_admin.data, list) else res_mouvements_admin.data.get('results', [])
        self.assertGreaterEqual(len(items_admin), 3)




