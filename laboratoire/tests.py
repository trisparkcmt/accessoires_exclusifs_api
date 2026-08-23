from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from rest_framework.test import APITestCase

from laboratoire.models import ParfumPersonnalise, ParfumPersonnaliseLigne
from laboratoire.serializers import ParfumPersonnaliseSerializer
from laboratoire.utils_ia import ajuster_composition_45_percent, normaliser_reponse_composition
from catalogue.models import Essence, Flacon, LotEssence
from utilisateur.models import Client


class DummyRequest:
    def __init__(self, user):
        self.user = user


class ParfumPersonnaliseSerializerTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='test1234',
            telephone='+1234567890'
        )
        self.client_profile = self.user.client

        self.flacon = Flacon.objects.create(
            type_flacon=None,
            nom='Flacon test',
            reference_sku='FL-TEST',
            contenance_ml=50,
            prix_unitaire=Decimal('1000.00'),
            stock_quantite=10,
            actif=True
        )

        self.essence1 = Essence.objects.create(
            nom='Essence 1',
            code_reference='ESS1',
            prix_par_ml=Decimal('10.00'),
            actif=True
        )
        self.lot1 = LotEssence.objects.create(
            essence=self.essence1,
            stock_ml=Decimal('100.00'),
            actif=True
        )

        self.essence2 = Essence.objects.create(
            nom='Essence 2',
            code_reference='ESS2',
            prix_par_ml=Decimal('20.00'),
            actif=True
        )
        self.lot2 = LotEssence.objects.create(
            essence=self.essence2,
            stock_ml=Decimal('100.00'),
            actif=True
        )

        self.parfum = ParfumPersonnalise.objects.create(
            client=self.client_profile,
            flacon=self.flacon,
            nom='Parfum Origine',
            description='Description initiale',
            prix_essences=Decimal('0.00'),
            prix_flacon_snapshot=self.flacon.prix_unitaire,
            prix_total=self.flacon.prix_unitaire
        )

        self.ligne = ParfumPersonnaliseLigne.objects.create(
            parfum_personnalise=self.parfum,
            essence=self.lot1,
            quantite_ml=Decimal('10.00'),
            prix_par_ml_snapshot=self.essence1.prix_par_ml
        )

    def test_update_parfum_personnalise_with_lignes(self):
        payload = {
            'nom': 'Parfum Modifié',
            'description': 'Nouvelle description',
            'lignes': [
                {
                    'id': self.ligne.id,
                    'essence': self.lot2.id,
                    'quantite_ml': '15.00'
                }
            ]
        }
        serializer = ParfumPersonnaliseSerializer(
            self.parfum,
            data=payload,
            partial=True,
            context={'request': DummyRequest(self.user)}
        )
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)
        parfum = serializer.save()

        self.parfum.refresh_from_db()
        self.assertEqual(self.parfum.nom, 'Parfum Modifié')
        self.assertEqual(self.parfum.description, 'Nouvelle description')
        self.assertEqual(self.parfum.lignes.count(), 1)

        ligne = self.parfum.lignes.first()
        self.assertEqual(ligne.essence, self.lot2)
        self.assertEqual(ligne.quantite_ml, Decimal('15.00'))
        self.assertEqual(ligne.prix_par_ml_snapshot, self.essence2.prix_par_ml)
        self.assertEqual(self.parfum.prix_essences, ligne.prix_ligne)
        self.assertEqual(self.parfum.prix_total, self.parfum.prix_essences + self.parfum.prix_flacon_snapshot)

    def test_add_new_ligne_to_parfum_personnalise(self):
        payload = {
            'lignes': [
                {
                    'id': self.ligne.id,
                    'essence': self.lot1.id,
                    'quantite_ml': '10.00'
                },
                {
                    'essence': self.lot2.id,
                    'quantite_ml': '5.00'
                }
            ]
        }
        serializer = ParfumPersonnaliseSerializer(
            self.parfum,
            data=payload,
            partial=True,
            context={'request': DummyRequest(self.user)}
        )
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)
        parfum = serializer.save()

        self.parfum.refresh_from_db()
        self.assertEqual(self.parfum.lignes.count(), 2)
        self.assertTrue(self.parfum.lignes.filter(essence=self.lot1).exists())
        self.assertTrue(self.parfum.lignes.filter(essence=self.lot2).exists())
        self.assertEqual(self.parfum.prix_essences, sum(l.prix_ligne for l in self.parfum.lignes.all()))

    def test_remove_ligne_from_parfum_personnalise(self):
        payload = {
            'lignes': []
        }
        serializer = ParfumPersonnaliseSerializer(
            self.parfum,
            data=payload,
            partial=True,
            context={'request': DummyRequest(self.user)}
        )
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)
        parfum = serializer.save()

        self.parfum.refresh_from_db()
        self.assertEqual(self.parfum.lignes.count(), 0)
        self.assertEqual(self.parfum.prix_essences, Decimal('0.00'))
        self.assertEqual(self.parfum.prix_total, self.parfum.prix_flacon_snapshot)


class ParfumPersonnaliseAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='parfum-perso-api',
            email='parfum-perso-api@example.com',
            password='test1234',
            telephone='+1234567891',
        )
        self.flacon = Flacon.objects.create(
            nom='Flacon API',
            reference_sku='FL-API',
            contenance_ml=50,
            prix_unitaire=Decimal('1000.00'),
            stock_quantite=10,
            actif=True,
        )
        self.parfum = ParfumPersonnalise.objects.create(
            client=self.user.client,
            flacon=self.flacon,
            nom='Parfum API',
            prix_essences=Decimal('1200.00'),
            prix_flacon_snapshot=Decimal('1000.00'),
            prix_total=Decimal('2200.00'),
            enregistre=True,
        )

    def test_liste_parfums_personnalises_contient_prix_total(self):
        self.client.force_authenticate(self.user)

        response = self.client.get('/api/v1/lab/parfums-perso/')

        self.assertEqual(response.status_code, 200)
        resultat = response.data['resultats'][0]
        self.assertEqual(resultat['id'], self.parfum.id)
        self.assertIn('prix_total', resultat)
        self.assertEqual(Decimal(resultat['prix_total']), Decimal('2200.00'))


class IACompositionRulesTests(TestCase):
    def test_normaliser_reponse_composition_keeps_only_essences_and_deduplicates_suggestions(self):
        response = {
            'message': 'Voici une proposition personnalisée',
            'quantite_demandee_ml': 50,
            'budget_max_fcfa': 150000,
            'flacon_id': 42,
            'essences_pre_faites': [
                {'id': 1, 'quantite_ml': 20},
                {'id': 2, 'quantite_ml': 20},
            ],
            'ingredients_sur_mesure': [
                {'id': 9, 'quantite_ml': 10},
            ],
            'parfums_existants_recommandes': [1],
            'accessoires': [5, 5, 6],
            'diffuseurs': [3, 3],
        }

        normalized = normaliser_reponse_composition(response)

        self.assertEqual(normalized['ingredients_sur_mesure'], [])
        self.assertEqual(len(normalized['essences_pre_faites']), 2)
        self.assertEqual(normalized['accessoires'], [5, 6])
        self.assertEqual(normalized['diffuseurs'], [3])

    def test_ajuster_composition_45_percent_uses_exact_target_with_essences_only(self):
        flacon = Flacon.objects.create(
            nom='Flacon test 45%',
            reference_sku='FL-45',
            contenance_ml=100,
            prix_unitaire=Decimal('2000.00'),
            stock_quantite=10,
            actif=True,
        )

        response = {
            'flacon_id': flacon.id,
            'essences_pre_faites': [
                {'id': 1, 'quantite_ml': 20},
                {'id': 2, 'quantite_ml': 20},
            ],
            'ingredients_sur_mesure': [
                {'id': 8, 'quantite_ml': 20},
            ],
        }

        normalized = normaliser_reponse_composition(response)
        adjusted = ajuster_composition_45_percent(normalized)
        total = sum(float(item['quantite_ml']) for item in adjusted['essences_pre_faites'])

        self.assertAlmostEqual(total, 45.0, places=2)
        self.assertEqual(adjusted['ingredients_sur_mesure'], [])


class IALanguageDetectionTests(TestCase):
    from unittest.mock import patch

    @patch('google.genai.Client')
    def test_demander_recommandation_ia_includes_current_prompt_language_rules(self, mock_genai):
        from laboratoire.utils_ia import demander_recommandation_ia
        import json

        # Mock de la réponse Gemini
        mock_response = mock_genai.return_value.models.generate_content.return_value
        mock_response.text = json.dumps({
            "message": "Hello! I recommend our sweet vanilla fragrance.",
            "quantite_demandee_ml": 0,
            "budget_max_fcfa": 0,
            "flacon_id": 0,
            "essences_pre_faites": [],
            "ingredients_sur_mesure": [],
            "parfums_existants_recommandes": [1],
            "accessoires": [],
            "diffuseurs": []
        })

        result = demander_recommandation_ia("I want a sweet vanilla perfume", history=[])
        self.assertNotIn("error", result)
        self.assertEqual(result["message"], "Hello! I recommend our sweet vanilla fragrance.")

        # Vérifier que l'appel Gemini inclut les règles de détection de langue
        args, kwargs = mock_genai.return_value.models.generate_content.call_args
        contents_sent = kwargs.get('contents', '')
        self.assertIn("DÉTECTION DE LA LANGUE ET RÉPONSE", contents_sent)
        self.assertIn("ANGLAIS", contents_sent)
        self.assertIn("FRANÇAIS", contents_sent)
