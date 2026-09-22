from django.test import TestCase, override_settings
from rest_framework.test import APITestCase
from utilisateur.models import User


@override_settings(ACCOUNT_EMAIL_VERIFICATION='none', REST_FRAMEWORK={
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'dj_rest_auth.jwt_auth.JWTCookieAuthentication',
        'rest_framework.authtoken.models.Token',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'login_ip': '999999/day',
        'login_credential': '999999/day',
        'register_ip': '999999/day',
        'register_email': '999999/day',
    }
})
class AuthEndpointsTest(APITestCase):
    def setUp(self):
        # Désactiver le throttling pour les tests
        from utilisateur.throttles import (
            LoginIPThrottle, LoginCredentialThrottle,
            RegisterIPThrottle, RegisterEmailThrottle,
        )
        LoginIPThrottle.rate = '999999/day'
        LoginCredentialThrottle.rate = '999999/day'
        RegisterIPThrottle.rate = '999999/day'
        RegisterEmailThrottle.rate = '999999/day'

        self.registration_url = '/api/v1/auth/registration/'
        self.login_url = '/api/v1/auth/mobile/login/'
        self.me_url = '/api/v1/auth/me/'
        self.logout_url = '/api/v1/auth/logout/'
        self.apply_prestataire_url = '/api/v1/auth/prestataire/apply/'
        self.password = 'TestPass123!'

        self.user = User.objects.create_user(
            username='copilot_testuser',
            email='testuser+copilot@example.com',
            password=self.password,
        )

    def authenticate(self, payload):
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, 200, response.content.decode())
        return response.data['access']

    def test_registration_requires_matching_passwords(self):
        payload = {
            'email': 'newuser+copilot@example.com',
            'telephone': '+2250700000002',
            'password': self.password,
            'password_confirm': 'DifferentPass123!',
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(self.registration_url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password_confirm', response.data)

    def test_registration_creates_user_and_returns_tokens(self):
        payload = {
            'email': 'newuser+copilot@example.com',
            'telephone': '+2250700000002',
            'password': self.password,
            'password_confirm': self.password,
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(self.registration_url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertTrue(User.objects.filter(email='newuser+copilot@example.com').exists())

    def test_registration_fails_with_duplicate_telephone(self):
        User.objects.create_user(
            username='user_existing_phone',
            email='existing_phone@example.com',
            password=self.password,
            telephone='+2250700000002'
        )
        payload = {
            'email': 'another_user@example.com',
            'telephone': '+2250700000002',
            'password': self.password,
            'password_confirm': self.password,
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(self.registration_url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('telephone', response.data)
        self.assertEqual(response.data['telephone'][0], "Ce numéro de téléphone est déjà utilisé.")

    def test_registration_atomic_rollback_on_failure(self):
        User.objects.create_user(
            username='user_existing_phone_atomic',
            email='existing_phone_atomic@example.com',
            password=self.password,
            telephone='+2250700000002'
        )
        payload = {
            'email': 'should_not_exist@example.com',
            'telephone': '+2250700000002',
            'password': self.password,
            'password_confirm': self.password,
            'first_name': 'Test',
            'last_name': 'User'
        }
        user_count_before = User.objects.count()
        from utilisateur.models import Client
        client_count_before = Client.objects.count()

        response = self.client.post(self.registration_url, payload, format='json')
        self.assertEqual(response.status_code, 400)

        # Check rollback
        self.assertEqual(User.objects.count(), user_count_before)
        self.assertEqual(Client.objects.count(), client_count_before)
        self.assertFalse(User.objects.filter(email='should_not_exist@example.com').exists())

    def test_login_with_email_succeeds(self):
        payload = {'email': self.user.email, 'password': self.password}
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        # Verify roles injection
        self.assertIn('roles', response.data)
        self.assertEqual(response.data['roles'], ['client'])
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['email'], self.user.email)

    def test_patch_me_updates_telephone_and_allows_phone_login(self):
        access_token = self.authenticate({'email': self.user.email, 'password': self.password})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        response_patch = self.client.patch(
            self.me_url,
            {'telephone': '+2250700000009', 'current_password': self.password},
            format='json'
        )
        self.assertEqual(response_patch.status_code, 200)
        self.assertEqual(response_patch.data['telephone'], '+2250700000009')

        # Verify telephone is persisted and can be used to login
        self.user.refresh_from_db()
        self.assertEqual(self.user.telephone, '+2250700000009')

        response_login_phone = self.client.post(self.login_url, {'telephone': '+2250700000009', 'password': self.password}, format='json')
        self.assertEqual(response_login_phone.status_code, 200)
        self.assertIn('access', response_login_phone.data)

    def test_me_returns_authenticated_user_profile(self):
        access_token = self.authenticate({'email': self.user.email, 'password': self.password})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['roles'], ['client'])

    def test_logout_returns_200(self):
        access_token = self.authenticate({'email': self.user.email, 'password': self.password})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        response = self.client.post(self.logout_url, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('detail', response.data)

    def test_apply_prestataire_requires_photo(self):
        access_token = self.authenticate({'email': self.user.email, 'password': self.password})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # Sans photo -> 400
        response_no_photo = self.client.post(self.apply_prestataire_url, format='json')
        self.assertEqual(response_no_photo.status_code, 400)
        self.assertIn('photo', response_no_photo.data)

    def test_apply_prestataire_creates_request_with_photo(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        access_token = self.authenticate({'email': self.user.email, 'password': self.password})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        file = io.BytesIO()
        img = Image.new('RGB', (10, 10), color='red')
        img.save(file, 'jpeg')
        file.seek(0)

        photo = SimpleUploadedFile('test_photo.jpg', file.getvalue(), content_type='image/jpeg')
        response = self.client.post(self.apply_prestataire_url, {'photo': photo}, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['detail'], 'Demande envoyée avec succès.')


from unittest.mock import patch
from decimal import Decimal
import hmac
import hashlib
import json
from django.test import override_settings
from utilisateur.models import Prestataire, PayoutTransaction, CommissionLog, Client

class CampayPayoutsTest(APITestCase):
    def setUp(self):
        # 1. Admin user
        self.admin = User.objects.create_superuser(
            username='admin_test',
            email='admin@example.com',
            password='AdminPassword123!',
            telephone='+237600000001'
        )
        
        # 2. Prestataire user
        self.prestataire_user = User.objects.create_user(
            username='prestataire_test',
            email='prestataire@example.com',
            password='UserPassword123!',
            telephone='677123456' # Cameroon number to check cleaning
        )
        # In utilisateur/models.py, a Client profile is automatically created on User creation (via post_save signal)
        self.client_profile = self.prestataire_user.client
        
        # Create Prestataire profile
        self.prestataire = Prestataire.objects.create(
            client=self.client_profile,
            code_promo='TESTPROMO',
            taux_commission=Decimal('10.00'),
            reduction_client_pourcentage=Decimal('5.00'),
            solde_commission=Decimal('10000.00'),
            statut='actif'
        )

        self.payout_url = f'/api/v1/auth/admin/prestataires/{self.prestataire.pk}/payout/'
        self.webhook_url = '/api/v1/auth/payout/webhook/'

    def test_payout_requires_admin(self):
        # Authenticate as regular user
        self.client.force_authenticate(user=self.prestataire_user)
        response = self.client.post(self.payout_url, {'montant': '1000.00'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_payout_insufficient_funds(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.payout_url, {'montant': '15000.00'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Solde insuffisant', response.data['detail'])
        
        # Verify no balance deduction
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('10000.00'))

    def test_payout_invalid_phone(self):
        self.client.force_authenticate(user=self.admin)
        # Temporarily change telephone to invalid
        self.prestataire_user.telephone = '123'
        self.prestataire_user.save()
        
        response = self.client.post(self.payout_url, {'montant': '5000.00'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('n\'est pas valide', response.data['detail'])

    @patch('utilisateur.campay.payout_to_phone')
    def test_payout_successful_initiation(self, mock_payout):
        # Mock Campay adapter response (success)
        mock_payout.return_value = (True, {'transaction': 123456}, None)

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.payout_url, {'montant': '5000.00'}, format='json')
        self.assertEqual(response.status_code, 201)

        # Verify transaction database creation
        tx = PayoutTransaction.objects.get(reference_unique=response.data['reference_unique'])
        self.assertEqual(tx.montant, Decimal('5000.00'))
        self.assertEqual(tx.statut, 'en_cours')
        self.assertEqual(tx.telephone_destination, '237677123456')

        # Verify immediate debit
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('5000.00'))

    @patch('utilisateur.campay.payout_to_phone')
    def test_payout_idempotent_with_existing_external_reference(self, mock_payout):
        mock_payout.return_value = (True, {'transaction': 123456}, None)

        self.client.force_authenticate(user=self.admin)
        external_reference = 'idem-ref-123'

        response1 = self.client.post(self.payout_url, {
            'montant': '5000.00',
            'external_reference': external_reference
        }, format='json')
        self.assertEqual(response1.status_code, 201)
        self.assertEqual(PayoutTransaction.objects.count(), 1)

        tx1 = PayoutTransaction.objects.get(reference_unique=external_reference)
        self.assertEqual(tx1.montant, Decimal('5000.00'))

        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('5000.00'))

        response2 = self.client.post(self.payout_url, {
            'montant': '5000.00',
            'external_reference': external_reference
        }, format='json')
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(PayoutTransaction.objects.count(), 1)

        tx2 = PayoutTransaction.objects.get(reference_unique=external_reference)
        self.assertEqual(tx1.pk, tx2.pk)
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('5000.00'))
        mock_payout.assert_called_once()

    @patch('utilisateur.campay.payout_to_phone')
    def test_payout_rejected_by_campay(self, mock_payout):
        # Mock Campay API failure
        mock_payout.return_value = (False, {'message': 'Service balance insufficient.'}, 'Service balance insufficient.')

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.payout_url, {'montant': '5000.00'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('rejeté l\'opération', response.data['detail'])

        # Verify balance refunded
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('10000.00'))

        # Verify transaction is recorded as echec
        tx = PayoutTransaction.objects.get(prestataire=self.prestataire)
        self.assertEqual(tx.statut, 'echec')
        self.assertIn('Service balance insufficient', tx.motif_echec)

    def test_webhook_success_notification(self):
        # Create a pending transaction
        tx = PayoutTransaction.objects.create(
            prestataire=self.prestataire,
            montant=Decimal('4000.00'),
            telephone_destination='237677123456',
            reference_unique='tx_success_123',
            statut='en_cours'
        )
        # Deduct balance as done in initiation
        self.prestataire.solde_commission -= Decimal('4000.00')
        self.prestataire.save()

        # Send webhook notification (public client, no auth required)
        payload = {
            'processing_number': 'tx_success_123',
            'status': 'success',
            'message': 'Le transfert a été effectué'
        }
        response = self.client.post(self.webhook_url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction is marked success
        tx.refresh_from_db()
        self.assertEqual(tx.statut, 'succes')
        
        # Verify balance is NOT restored (remains at 6000)
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('6000.00'))
        
        # Verify CommissionLog retrait is created
        log = CommissionLog.objects.get(prestataire=self.prestataire, type_operation='retrait')
        self.assertEqual(log.montant, Decimal('-4000.00'))

    @override_settings(CAMPAY_WEBHOOK_SECRET='super-secret-webhook-key')
    def test_webhook_with_valid_signature(self):
        tx = PayoutTransaction.objects.create(
            prestataire=self.prestataire,
            montant=Decimal('4000.00'),
            telephone_destination='237677123456',
            reference_unique='tx_sig_success_123',
            statut='en_cours'
        )
        self.prestataire.solde_commission -= Decimal('4000.00')
        self.prestataire.save()

        payload = {
            'reference': 'tx_sig_success_123',
            'status': 'success',
            'message': 'Le transfert a été effectué'
        }
        body = json.dumps(payload).encode('utf-8')
        signature = 'sha256=' + hmac.new(
            b'super-secret-webhook-key',
            body,
            hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_X_CAMPAY_SIGNATURE=signature
        )
        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.statut, 'succes')

    @override_settings(CAMPAY_WEBHOOK_SECRET='super-secret-webhook-key')
    def test_webhook_rejects_invalid_signature(self):
        tx = PayoutTransaction.objects.create(
            prestataire=self.prestataire,
            montant=Decimal('4000.00'),
            telephone_destination='237677123456',
            reference_unique='tx_sig_fail_123',
            statut='en_cours'
        )
        self.prestataire.solde_commission -= Decimal('4000.00')
        self.prestataire.save()

        payload = {
            'reference': 'tx_sig_fail_123',
            'status': 'success',
            'message': 'Le transfert a été effectué'
        }
        body = json.dumps(payload).encode('utf-8')
        signature = 'sha256=' + '0' * 64

        response = self.client.post(
            self.webhook_url,
            data=body,
            content_type='application/json',
            HTTP_X_CAMPAY_SIGNATURE=signature
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['detail'], 'Signature webhook invalide.')

    def test_webhook_failure_notification_refunds_balance(self):
        # Create a pending transaction
        tx = PayoutTransaction.objects.create(
            prestataire=self.prestataire,
            montant=Decimal('4000.00'),
            telephone_destination='237677123456',
            reference_unique='tx_fail_123',
            statut='en_cours'
        )
        # Deduct balance as done in initiation
        self.prestataire.solde_commission -= Decimal('4000.00')
        self.prestataire.save()

        payload = {
            'processing_number': 'tx_fail_123',
            'status': 'failed',
            'message': 'Solde insuffisant sur le compte marchand'
        }
        response = self.client.post(self.webhook_url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction is marked echec
        tx.refresh_from_db()
        self.assertEqual(tx.statut, 'echec')
        self.assertEqual(tx.motif_echec, 'Solde insuffisant sur le compte marchand')
        
        # Verify balance is restored/refunded
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.solde_commission, Decimal('10000.00'))


class PrestataireDashboardEndpointsTest(APITestCase):
    def setUp(self):
        # 1. Admin user
        self.admin = User.objects.create_superuser(
            username='admin_dashboard_test',
            email='admin_db@example.com',
            password='AdminPassword123!'
        )
        
        # 2. Regular user (no prestataire)
        self.regular_user = User.objects.create_user(
            username='client_test',
            email='client@example.com',
            password='UserPassword123!'
        )
        
        # 3. Active Prestataire user
        self.prest_user = User.objects.create_user(
            username='prest_user',
            email='prest@example.com',
            password='UserPassword123!'
        )
        self.prest = Prestataire.objects.create(
            client=self.prest_user.client,
            code_promo='PREST1',
            taux_commission=Decimal('15.00'),
            reduction_client_pourcentage=Decimal('5.00'),
            solde_commission=Decimal('8000.00'),
            statut='actif'
        )
        
        # 4. Inactive Prestataire user
        self.inactive_user = User.objects.create_user(
            username='inactive_user',
            email='inactive@example.com',
            password='UserPassword123!'
        )
        self.inactive_prest = Prestataire.objects.create(
            client=self.inactive_user.client,
            code_promo='PREST_INACTIVE',
            statut='en_attente'
        )

        # Create some logs for prest
        # positive commissions (credits)
        CommissionLog.objects.create(prestataire=self.prest, type_operation='vente', montant=Decimal('5000.00'), description='Sale 1')
        CommissionLog.objects.create(prestataire=self.prest, type_operation='bonus', montant=Decimal('2000.00'), description='Bonus 1')
        # negative commissions (debits)
        CommissionLog.objects.create(prestataire=self.prest, type_operation='retrait', montant=Decimal('-3000.00'), description='Retrait 1')

        # Create some payouts
        PayoutTransaction.objects.create(
            prestataire=self.prest,
            montant=Decimal('1000.00'),
            telephone_destination='237677123456',
            reference_unique='tx_payout_1',
            statut='en_cours'
        )
        PayoutTransaction.objects.create(
            prestataire=self.prest,
            montant=Decimal('2000.00'),
            telephone_destination='237677123456',
            reference_unique='tx_payout_2',
            statut='succes'
        )

        self.dashboard_url = '/api/v1/auth/prestataire/dashboard/'
        self.history_url = '/api/v1/auth/prestataire/historique/'
        self.payouts_url = '/api/v1/auth/prestataire/payouts/'

    def test_dashboard_access_control(self):
        # Unauthenticated -> 401
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 401)

        # Regular user -> 403
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 403)

        # Inactive prestataire -> 403
        self.client.force_authenticate(user=self.inactive_user)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 403)

        # Active prestataire -> 200
        self.client.force_authenticate(user=self.prest_user)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_stats_and_data(self):
        self.client.force_authenticate(user=self.prest_user)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        
        # Verify stats
        self.assertEqual(response.data['solde_commission'], '8000.00')
        self.assertEqual(response.data['total_gains'], '7000.00') # 5000 + 2000
        self.assertEqual(response.data['total_retraits'], '3000.00') # abs(-3000)
        self.assertEqual(response.data['solde_bloque'], '1000.00') # payout in progress

        # Verify recent items are serialized
        self.assertEqual(len(response.data['historique_recent']), 3)
        self.assertEqual(len(response.data['payouts_recents']), 2)

    def test_admin_access_to_prestataire_dashboard(self):
        self.client.force_authenticate(user=self.admin)
        
        # Without prestataire_id query param -> returns 200 with global stats
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], None)
        self.assertEqual(response.data['solde_commission'], '8000.00')
        self.assertEqual(response.data['total_gains'], '7000.00')
        self.assertEqual(response.data['total_retraits'], '3000.00')
        self.assertEqual(response.data['solde_bloque'], '1000.00')
        
        # With prestataire_id query param -> returns specific prestataire stats
        response = self.client.get(f"{self.dashboard_url}?prestataire_id={self.prest.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['code_promo'], 'PREST1')

    def test_prestataire_finance_history_filtering_and_pagination(self):
        self.client.force_authenticate(user=self.prest_user)
        
        # General list (no filter) -> returns paginated results
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, 200)
        # Should have results (paginated envelope contains 'results')
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 3)

        # Filtering by type_operation = 'retrait'
        response = self.client.get(f"{self.history_url}?type_operation=retrait")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['type_operation'], 'retrait')

    def test_admin_access_to_finance_history(self):
        self.client.force_authenticate(user=self.admin)
        # With prestataire_id
        response = self.client.get(f"{self.history_url}?prestataire_id={self.prest.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 3)

        # Without prestataire_id -> global history of all prestataires
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 3)

    def test_prestataire_payouts_list(self):
        self.client.force_authenticate(user=self.prest_user)
        response = self.client.get(self.payouts_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2)

        # Filter by status
        response = self.client.get(f"{self.payouts_url}?statut=en_cours")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['statut'], 'en_cours')

    def test_admin_access_to_payouts_list(self):
        self.client.force_authenticate(user=self.admin)
        # With prestataire_id
        response = self.client.get(f"{self.payouts_url}?prestataire_id={self.prest.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2)

        # Without prestataire_id -> global payouts of all prestataires
        response = self.client.get(self.payouts_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2)


from utilisateur.models import Livreur
from orders.models import Commande

class LivreurEndpointsTest(APITestCase):
    def setUp(self):
        # Admin user
        self.admin = User.objects.create_superuser(
            username='admin_livreur_test',
            email='admin_livreur@example.com',
            password='AdminPassword123!',
            telephone='+237600000002'
        )

        # Standard client user
        self.client_user = User.objects.create_user(
            username='client_test',
            email='client@example.com',
            password='UserPassword123!',
            telephone='+237600000003'
        )

        # Livreur user (active)
        self.livreur_user = User.objects.create_user(
            username='livreur_test',
            email='livreur@example.com',
            password='LivreurPassword123!',
            telephone='+237600000004'
        )
        self.livreur = Livreur.objects.create(
            client=self.livreur_user.client,
            statut='disponible'
        )

        # Inactive Livreur user
        self.inactive_livreur_user = User.objects.create_user(
            username='inactive_livreur_test',
            email='inactive_livreur@example.com',
            password='LivreurPassword123!',
            telephone='+237600000005'
        )
        self.inactive_livreur = Livreur.objects.create(
            client=self.inactive_livreur_user.client,
            statut='inactif'
        )

        # Commandes (Orders)
        self.commande_cash = Commande.objects.create(
            numero_commande='CMD-CASH-123',
            client=self.client_user.client,
            statut='en_attente',
            statut_livraison='en_attente_affectation',
            sous_total=Decimal('5000.00'),
            total_ttc=Decimal('5500.00'),
            livraison_nom_complet='Jean Dupont',
            livraison_telephone='+237600000003',
            statut_paiement='en_attente'
        )

        self.commande_momo = Commande.objects.create(
            numero_commande='CMD-MOMO-123',
            client=self.client_user.client,
            statut='en_attente',
            statut_livraison=None,
            sous_total=Decimal('10000.00'),
            total_ttc=Decimal('10500.00'),
            livraison_nom_complet='Jean Dupont',
            livraison_telephone='+237600000003',
            statut_paiement='en_attente'
        )

    def test_access_restrictions(self):
        # 1. Unauthenticated client
        response = self.client.get('/api/v1/auth/livreur/dashboard/')
        self.assertEqual(response.status_code, 401)

        # 2. Standard client user on livreur dashboard
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/v1/auth/livreur/dashboard/')
        self.assertEqual(response.status_code, 403)

        # 3. Standard client user on admin endpoints
        response = self.client.get('/api/v1/auth/admin/livreurs/')
        self.assertEqual(response.status_code, 403)

    def test_livreur_dashboard_and_list(self):
        # Assign commande_cash to our livreur first
        self.commande_cash.livreur = self.livreur
        self.commande_cash.statut_livraison = 'assignée'
        self.commande_cash.save()

        self.client.force_authenticate(user=self.livreur_user)
        
        # Dashboard
        response = self.client.get('/api/v1/auth/livreur/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.livreur.id)
        self.assertEqual(response.data['statut'], 'disponible')
        self.assertEqual(len(response.data['livraisons_actives']), 1)
        self.assertEqual(response.data['livraisons_actives'][0]['numero_commande'], 'CMD-CASH-123')

        # History list
        response = self.client.get('/api/v1/auth/livreur/livraisons/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)

    def test_livreur_inactive_or_suspended_blocked(self):
        # Make the livreur inactive
        self.client.force_authenticate(user=self.inactive_livreur_user)

        response = self.client.get('/api/v1/auth/livreur/dashboard/')
        self.assertEqual(response.status_code, 403)
        self.assertIn("n'est pas actif", response.data['detail'])

        response = self.client.get('/api/v1/auth/livreur/livraisons/')
        self.assertEqual(response.status_code, 403)

        # Try updating status
        response = self.client.patch(
            f'/api/v1/auth/livreur/livraisons/{self.commande_cash.pk}/statut/',
            {'action': 'livrer'},
            format='json'
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_assign_delivery_to_livreur(self):
        self.client.force_authenticate(user=self.admin)
        self.commande_cash.statut = 'validé'
        self.commande_cash.save()
        self.commande_momo.statut = 'validé'
        self.commande_momo.save()

        # Assign to active livreur
        response = self.client.post(
            f'/api/v1/auth/admin/commandes/{self.commande_cash.pk}/affecter-livreur/',
            {'livreur_id': self.livreur.pk},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        
        self.commande_cash.refresh_from_db()
        self.assertEqual(self.commande_cash.livreur, self.livreur)
        self.assertEqual(self.commande_cash.statut_livraison, 'assignée')

        # Try assigning to inactive livreur
        response = self.client.post(
            f'/api/v1/auth/admin/commandes/{self.commande_momo.pk}/affecter-livreur/',
            {'livreur_id': self.inactive_livreur.pk},
            format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactif ou suspendu", response.data['detail'])

    def test_livreur_update_delivery_status_success_cash(self):
        # Setup assignment
        self.commande_cash.statut = 'validé'
        self.commande_cash.livreur = self.livreur
        self.commande_cash.statut_livraison = 'assignée'
        self.commande_cash.save()

        self.client.force_authenticate(user=self.livreur_user)

        # Complete delivery
        response = self.client.patch(
            f'/api/v1/auth/livreur/livraisons/{self.commande_cash.pk}/statut/',
            {'action': 'livrer'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)

        self.commande_cash.refresh_from_db()
        self.assertEqual(self.commande_cash.statut_livraison, 'livrée')
        self.assertEqual(self.commande_cash.statut, 'livrée')
        self.assertEqual(self.commande_cash.statut_paiement, 'payé')  # Cash-on-delivery automatically updated
        self.assertIsNotNone(self.commande_cash.date_livraison_reelle)

        self.livreur.refresh_from_db()
        self.assertEqual(self.livreur.nombre_livraisons, 1)

    def test_livreur_update_delivery_status_success_mobile_money(self):
        # Setup assignment
        self.commande_momo.statut = 'validé'
        self.commande_momo.livreur = self.livreur
        self.commande_momo.statut_livraison = 'assignée'
        self.commande_momo.save()

        self.client.force_authenticate(user=self.livreur_user)

        # Complete delivery
        response = self.client.patch(
            f'/api/v1/auth/livreur/livraisons/{self.commande_momo.pk}/statut/',
            {'action': 'livrer'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)

        self.commande_momo.refresh_from_db()
        self.assertEqual(self.commande_momo.statut_livraison, 'livrée')
        self.assertEqual(self.commande_momo.statut, 'livrée')
        self.assertEqual(self.commande_momo.statut_paiement, 'payé')

    def test_livreur_update_delivery_status_failed(self):
        # Setup assignment
        self.commande_cash.livreur = self.livreur
        self.commande_cash.statut_livraison = 'assignée'
        self.commande_cash.save()

        self.client.force_authenticate(user=self.livreur_user)

        # Failed delivery attempt without motif -> 400
        response = self.client.patch(
            f'/api/v1/auth/livreur/livraisons/{self.commande_cash.pk}/statut/',
            {'action': 'echouer'},
            format='json'
        )
        self.assertEqual(response.status_code, 400)

        # Failed delivery attempt with motif
        response = self.client.patch(
            f'/api/v1/auth/livreur/livraisons/{self.commande_cash.pk}/statut/',
            {'action': 'echouer', 'motif': 'Client injoignable par téléphone'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)

        self.commande_cash.refresh_from_db()
        self.assertEqual(self.commande_cash.statut_livraison, 'échouée')
        self.assertEqual(self.commande_cash.motif_echec_livraison, 'Client injoignable par téléphone')

    def test_admin_livreurs_management(self):
        self.client.force_authenticate(user=self.admin)

        # List all livreurs
        response = self.client.get('/api/v1/auth/admin/livreurs/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        # We created two livreurs in setUp
        self.assertEqual(len(response.data['results']), 2)

        # Promote another client user to livreur
        new_client_user = User.objects.create_user(
            username='new_client_to_promote',
            email='new_client@example.com',
            password='Password123!',
            telephone='+237600000009'
        )
        response = self.client.post(
            '/api/v1/auth/admin/livreurs/promote/',
            {'user_id': new_client_user.pk},
            format='json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Livreur.objects.filter(client=new_client_user.client).exists())

        # Update livreur status
        livreur_to_suspend = self.livreur
        response = self.client.patch(
            f'/api/v1/auth/admin/livreurs/{livreur_to_suspend.pk}/',
            {'statut': 'suspendu'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        livreur_to_suspend.refresh_from_db()
        self.assertEqual(livreur_to_suspend.statut, 'suspendu')

        # Monitor deliveries
        self.commande_cash.livreur = self.livreur
        self.commande_cash.statut_livraison = 'assignée'
        self.commande_cash.save()

        response = self.client.get('/api/v1/auth/admin/livraisons/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)

    def test_admin_create_livreur_from_scratch(self):
        self.client.force_authenticate(user=self.admin)
        
        payload = {
            'email': 'new_livreur_scratch@example.com',
            'telephone': '+237600000021',
            'password': 'LivreurPassword123!',
            'first_name': 'LivreurFirst',
            'last_name': 'LivreurLast',
            'genre': 'homme',
            'photo': 'http://example.com/photo.png'
        }
        
        response = self.client.post('/api/v1/auth/admin/livreurs/promote/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['statut'], 'disponible')
        
        # Verify database entities
        user = User.objects.get(email='new_livreur_scratch@example.com')
        self.assertEqual(user.first_name, 'LivreurFirst')
        self.assertEqual(user.last_name, 'LivreurLast')
        self.assertEqual(user.telephone, '+237600000021')
        self.assertTrue(hasattr(user, 'client'))
        self.assertTrue(hasattr(user.client, 'livreur'))
        self.assertEqual(user.client.livreur.photo, 'http://example.com/photo.png')


from utilisateur.models import Serveuse

class ServeuseEndpointsTest(APITestCase):
    def setUp(self):
        # Admin user
        self.admin = User.objects.create_superuser(
            username='admin_serveuse_test',
            email='admin_serveuse@example.com',
            password='AdminPassword123!',
            telephone='+237600000012'
        )

        # Standard client user
        self.client_user = User.objects.create_user(
            username='client_serveuse_test',
            email='client_serveuse@example.com',
            password='UserPassword123!',
            telephone='+237600000013'
        )
        
        # Serveuse user (active)
        self.serveuse_user = User.objects.create_user(
            username='serveuse_test',
            email='serveuse@example.com',
            password='ServeusePassword123!',
            telephone='+237600000014'
        )
        self.serveuse = Serveuse.objects.create(
            client=self.serveuse_user.client,
            actif=True
        )

    def test_access_restrictions(self):
        # 1. Unauthenticated client
        response = self.client.get('/api/v1/auth/admin/serveuses/')
        self.assertEqual(response.status_code, 401)

        # 2. Standard client user on admin endpoints
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/v1/auth/admin/serveuses/')
        self.assertEqual(response.status_code, 403)

    def test_admin_serveuses_management_promote(self):
        self.client.force_authenticate(user=self.admin)

        # List all serveuses
        response = self.client.get('/api/v1/auth/admin/serveuses/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        # We created one serveuse in setUp
        self.assertEqual(len(response.data['results']), 1)

        # Promote another client user to serveuse
        new_client_user = User.objects.create_user(
            username='new_client_to_promote_serveuse',
            email='new_client_serveuse@example.com',
            password='Password123!',
            telephone='+237600000019'
        )
        response = self.client.post(
            '/api/v1/auth/admin/serveuses/promote/',
            {'user_id': new_client_user.pk},
            format='json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Serveuse.objects.filter(client=new_client_user.client).exists())

        # Update serveuse status
        response = self.client.patch(
            f'/api/v1/auth/admin/serveuses/{self.serveuse.pk}/',
            {'actif': False},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.serveuse.refresh_from_db()
        self.assertEqual(self.serveuse.actif, False)

        # Delete serveuse
        response = self.client.delete(f'/api/v1/auth/admin/serveuses/{self.serveuse.pk}/delete/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Serveuse.objects.filter(pk=self.serveuse.pk).exists())

    def test_admin_create_serveuse_from_scratch(self):
        self.client.force_authenticate(user=self.admin)
        
        payload = {
            'email': 'new_serveuse_scratch@example.com',
            'telephone': '+237600000022',
            'password': 'ServeusePassword123!',
            'first_name': 'ServeuseFirst',
            'last_name': 'ServeuseLast',
            'genre': 'femme'
        }
        
        response = self.client.post('/api/v1/auth/admin/serveuses/promote/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['actif'], True)
        
        # Verify database entities
        user = User.objects.get(email='new_serveuse_scratch@example.com')
        self.assertEqual(user.first_name, 'ServeuseFirst')
        self.assertEqual(user.last_name, 'ServeuseLast')
        self.assertEqual(user.telephone, '+237600000022')
        self.assertTrue(hasattr(user, 'client'))
        self.assertTrue(hasattr(user.client, 'serveuse'))


from utilisateur.models import Serveuse
from django.core.files.uploadedfile import SimpleUploadedFile

class PhotoProfilTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_photo_test',
            email='admin_photo@example.com',
            password='AdminPassword123!'
        )

        self.serveuse_user = User.objects.create_user(
            username='serveuse_photo_user',
            email='serveuse_photo@example.com',
            password='UserPassword123!'
        )
        self.serveuse = Serveuse.objects.create(
            client=self.serveuse_user.client,
            actif=True
        )

        self.livreur_user = User.objects.create_user(
            username='livreur_photo_user',
            email='livreur_photo@example.com',
            password='UserPassword123!'
        )
        self.livreur = Livreur.objects.create(
            client=self.livreur_user.client,
            statut='disponible'
        )

    def test_admin_created_serveuse_and_livreur_have_no_photo_by_default(self):
        self.assertFalse(bool(self.serveuse.photo))
        self.assertFalse(bool(self.livreur.photo))

    def test_user_can_upload_profile_photo(self):
        import io
        from PIL import Image
        self.client.force_authenticate(user=self.serveuse_user)

        file = io.BytesIO()
        img = Image.new('RGB', (10, 10), color='blue')
        img.save(file, 'jpeg')
        file.seek(0)

        photo = SimpleUploadedFile('serveuse.jpg', file.getvalue(), content_type='image/jpeg')

        response = self.client.post('/api/v1/auth/me/photo/', {'photo': photo}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertIn('photo', response.data)
        self.assertIn('photos_profil/serveuses/serveuse', response.data['photo'])

        self.serveuse.refresh_from_db()
        self.assertTrue(bool(self.serveuse.photo))

    def test_admin_cannot_update_photo_via_admin_endpoints(self):
        self.client.force_authenticate(user=self.admin)
        photo = SimpleUploadedFile('hacked.jpg', b'hacked_content', content_type='image/jpeg')

        # Admin tries to update serveuse photo
        response_serveuse = self.client.patch(
            f'/api/v1/auth/admin/serveuses/{self.serveuse.pk}/',
            {'photo': photo, 'actif': True},
            format='multipart'
        )
        self.assertEqual(response_serveuse.status_code, 200)
        self.serveuse.refresh_from_db()
        self.assertFalse(bool(self.serveuse.photo))

        # Admin tries to update livreur photo
        response_livreur = self.client.patch(
            f'/api/v1/auth/admin/livreurs/{self.livreur.pk}/',
            {'photo': photo, 'statut': 'disponible'},
            format='multipart'
        )
        self.assertEqual(response_livreur.status_code, 200)
        self.livreur.refresh_from_db()
        self.assertFalse(bool(self.livreur.photo))


from utilisateur.models import Boutique

class BoutiqueTest(APITestCase):
    def setUp(self):
        import io
        from PIL import Image

        self.user = User.objects.create_user(
            username='client_boutique_test',
            email='client_boutique@example.com',
            password='Password123!',
            telephone='+225070000100'
        )
        self.admin = User.objects.create_superuser(
            username='admin_boutique_test',
            email='admin_boutique@example.com',
            password='AdminPassword123!'
        )

        file = io.BytesIO()
        img = Image.new('RGB', (10, 10), color='green')
        img.save(file, 'jpeg')
        file.seek(0)
        self.test_photo = SimpleUploadedFile('boutique_logo.jpg', file.getvalue(), content_type='image/jpeg')

    def test_apply_boutique_validation(self):
        self.client.force_authenticate(user=self.user)

        # Missing photo & nom -> 400
        res = self.client.post('/api/v1/auth/boutique/apply/', {}, format='multipart')
        self.assertEqual(res.status_code, 400)
        self.assertIn('photo', res.data)
        self.assertIn('nom', res.data)

    def test_apply_boutique_success_and_duplicate(self):
        self.client.force_authenticate(user=self.user)

        import io
        from PIL import Image
        file = io.BytesIO()
        img = Image.new('RGB', (10, 10), color='green')
        img.save(file, 'jpeg')
        photo = SimpleUploadedFile('logo.jpg', file.getvalue(), content_type='image/jpeg')

        payload = {
            'nom': 'Ma Super Boutique',
            'adresse': '123 Rue du Commerce',
            'ville': 'Abidjan',
            'telephone': '+225070000100',
            'photo': photo
        }
        res = self.client.post('/api/v1/auth/boutique/apply/', payload, format='multipart')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['boutique']['nom'], 'Ma Super Boutique')
        self.assertEqual(res.data['boutique']['statut'], 'en_attente')

        # Role remains 'client' while en_attente
        self.user.refresh_from_db()
        self.assertNotIn('boutique', self.user.role)

        # Duplicate application -> 400
        photo2 = SimpleUploadedFile('logo2.jpg', file.getvalue(), content_type='image/jpeg')
        res_dup = self.client.post('/api/v1/auth/boutique/apply/', {'nom': 'Deuxieme Boutique', 'photo': photo2}, format='multipart')
        self.assertEqual(res_dup.status_code, 400)

    def test_me_boutique_get_and_patch(self):
        boutique = Boutique.objects.create(
            client=self.user.client,
            nom='Boutique Initial',
            photo=self.test_photo,
            statut='en_attente'
        )
        self.client.force_authenticate(user=self.user)

        # GET /api/v1/auth/me/boutique/
        res_get = self.client.get('/api/v1/auth/me/boutique/')
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.data['nom'], 'Boutique Initial')

        # PATCH /api/v1/auth/me/boutique/
        res_patch = self.client.patch('/api/v1/auth/me/boutique/', {'nom': 'Boutique Modifiée', 'ville': 'Yamoussoukro'}, format='json')
        self.assertEqual(res_patch.status_code, 200)
        self.assertEqual(res_patch.data['nom'], 'Boutique Modifiée')
        self.assertEqual(res_patch.data['ville'], 'Yamoussoukro')

    def test_admin_boutique_list_and_activate(self):
        boutique = Boutique.objects.create(
            client=self.user.client,
            nom='Boutique En Attente',
            photo=self.test_photo,
            statut='en_attente'
        )
        self.client.force_authenticate(user=self.admin)

        # Admin GET list
        res_list = self.client.get('/api/v1/auth/admin/boutiques/')
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.data), 1)

        # Admin PATCH activate
        res_patch = self.client.patch(f'/api/v1/auth/admin/boutiques/{boutique.pk}/', {'statut': 'actif'}, format='json')
        self.assertEqual(res_patch.status_code, 200)
        self.assertEqual(res_patch.data['statut'], 'actif')

        # Now role includes 'boutique'
        self.user.refresh_from_db()
        self.assertIn('boutique', self.user.role)

    def test_cancel_boutique_application(self):
        boutique = Boutique.objects.create(
            client=self.user.client,
            nom='Boutique A Annuler',
            photo=self.test_photo,
            statut='en_attente'
        )
        self.client.force_authenticate(user=self.user)

        res_cancel = self.client.delete('/api/v1/auth/boutique/cancel/')
        self.assertEqual(res_cancel.status_code, 200)
        self.assertFalse(Boutique.objects.filter(pk=boutique.pk).exists())

    def test_admin_validate_boutique_requires_taux_commission(self):
        boutique = Boutique.objects.create(
            client=self.user.client,
            nom='Boutique A Valider',
            photo=self.test_photo,
            statut='en_attente'
        )
        self.client.force_authenticate(user=self.admin)

        # Validation sans taux_commission -> 400
        res_no_rate = self.client.patch(f'/api/v1/auth/admin/boutiques/validate/{boutique.pk}/', {}, format='json')
        self.assertEqual(res_no_rate.status_code, 400)
        self.assertIn('taux_commission', res_no_rate.data)

        # Validation avec taux_commission -> 200
        res_val = self.client.patch(
            f'/api/v1/auth/admin/boutiques/validate/{boutique.pk}/',
            {'taux_commission': '15.50'},
            format='json'
        )
        self.assertEqual(res_val.status_code, 200)
        self.assertEqual(res_val.data['boutique']['statut'], 'actif')

        # Verify DB and user role
        boutique.refresh_from_db()
        self.assertEqual(boutique.statut, 'actif')
        self.assertEqual(boutique.taux_commission, Decimal('15.50'))

        self.user.refresh_from_db()
        self.assertIn('boutique', self.user.role)


from utilisateur.models import Prestataire

class PrestataireCancelAndDeleteTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='user_prestataire_cancel',
            email='user_pres_cancel@example.com',
            password='Password123!'
        )
        self.admin = User.objects.create_superuser(
            username='admin_prestataire_delete',
            email='admin_pres_delete@example.com',
            password='AdminPassword123!'
        )

    def test_client_can_cancel_pending_prestataire_application(self):
        prestataire = Prestataire.objects.create(
            client=self.user.client,
            statut='en_attente'
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.delete('/api/v1/auth/prestataire/cancel/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Prestataire.objects.filter(pk=prestataire.pk).exists())

    def test_client_cannot_cancel_active_prestataire(self):
        prestataire = Prestataire.objects.create(
            client=self.user.client,
            statut='actif'
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.delete('/api/v1/auth/prestataire/cancel/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Prestataire.objects.filter(pk=prestataire.pk).exists())

    def test_admin_can_delete_prestataire(self):
        prestataire = Prestataire.objects.create(
            client=self.user.client,
            statut='en_attente'
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f'/api/v1/auth/admin/prestataires/{prestataire.pk}/delete/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Prestataire.objects.filter(pk=prestataire.pk).exists())


<<<<<<< HEAD
from catalogue.models import Parfum, Accessoire, CategorieParfum, TypeAccessoire

class BoutiqueProduitCatalogTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='user_boutique_owner',
            email='boutique_owner@example.com',
            password='Password123!'
        )
        self.boutique = Boutique.objects.create(
            client=self.user.client,
            nom='Ma Super Boutique',
            statut='actif'
        )
        self.categorie_parfum = CategorieParfum.objects.create(nom='Boise', slug='boise')
        self.type_accessoire = TypeAccessoire.objects.create(nom='Sac', slug='sac')

    def test_active_boutique_can_post_parfum_and_accessoire(self):
        self.client.force_authenticate(user=self.user)

        # Post Parfum
        res_parfum = self.client.post('/api/v1/shop/parfums/', {
            'nom': 'Parfum Boutique 1',
            'contenance_ml': 100,
            'prix_unitaire': '25000.00',
            'stock_quantite': 20,
            'seuil_alerte_stock': 2,
            'categorie': self.categorie_parfum.pk,
            'actif': True,
        }, format='json')
        self.assertEqual(res_parfum.status_code, 201)
        parfum_id = res_parfum.data['id']
        parfum = Parfum.objects.get(pk=parfum_id)
        self.assertEqual(parfum.boutique, self.boutique)

        # Post Accessoire
        res_acc = self.client.post('/api/v1/shop/accessoires/', {
            'nom': 'Accessoire Boutique 1',
            'prix_unitaire': '15000.00',
            'stock_quantite': 10,
            'seuil_alerte_stock': 1,
            'type_accessoire': self.type_accessoire.pk,
            'actif': True,
        }, format='json')
        self.assertEqual(res_acc.status_code, 201)
        accessoire_id = res_acc.data['id']
        accessoire = Accessoire.objects.get(pk=accessoire_id)
        self.assertEqual(accessoire.boutique, self.boutique)

    def test_public_cannot_see_boutique_info_in_product(self):
        parfum = Parfum.objects.create(
            nom='Parfum Discret',
            contenance_ml=100,
            prix_unitaire=Decimal('30000.00'),
            stock_quantite=15,
            seuil_alerte_stock=2,
            categorie=self.categorie_parfum,
            boutique=self.boutique,
            actif=True
        )
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/v1/shop/parfums/{parfum.slug}/')
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('boutique', res.data)

    def test_boutique_only_sees_own_products_in_dashboard(self):
        # Produit de l'admin (sans boutique)
        parfum_admin = Parfum.objects.create(
            nom='Parfum Admin',
            contenance_ml=100,
            prix_unitaire=Decimal('20000.00'),
            stock_quantite=10,
            seuil_alerte_stock=1,
            categorie=self.categorie_parfum,
            actif=True
        )
        # Produit de notre boutique
        parfum_boutique = Parfum.objects.create(
            nom='Parfum Ma Boutique',
            contenance_ml=100,
            prix_unitaire=Decimal('25000.00'),
            stock_quantite=10,
            seuil_alerte_stock=1,
            categorie=self.categorie_parfum,
            boutique=self.boutique,
            actif=True
        )

        self.client.force_authenticate(user=self.user)

        # 1. En mode Dashboard (avec header X-Dashboard-Context=true)
        res_dash = self.client.get('/api/v1/shop/parfums/', HTTP_X_DASHBOARD_CONTEXT='true')
        self.assertEqual(res_dash.status_code, 200)
        results_dash = res_dash.data.get('resultats', res_dash.data)
        slugs_dash = [p['slug'] for p in results_dash]
        self.assertIn(parfum_boutique.slug, slugs_dash)
        self.assertNotIn(parfum_admin.slug, slugs_dash)

        # 2. Avec paramètre ?mes_produits=true
        res_my = self.client.get('/api/v1/shop/parfums/?mes_produits=true')
        self.assertEqual(res_my.status_code, 200)
        results_my = res_my.data.get('resultats', res_my.data)
        slugs_my = [p['slug'] for p in results_my]
        self.assertIn(parfum_boutique.slug, slugs_my)
        self.assertNotIn(parfum_admin.slug, slugs_my)


from unittest.mock import patch
from utilisateur.models import Notification

class NotificationDeletionAndGoogleOneTapTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='user_notif_test',
            email='notif_user@example.com',
            password='Password123!'
        )
        self.admin = User.objects.create_superuser(
            username='admin_notif_test',
            email='notif_admin@example.com',
            password='AdminPassword123!'
        )
        self.notif_user = Notification.objects.create(
            recipient=self.user,
            title="Titre User",
            message="Message User"
        )
        self.notif_global = Notification.objects.create(
            is_global_admin=True,
            title="Titre Global",
            message="Message Global"
        )

    def test_delete_single_user_notification(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(f'/api/v1/utilisateur/notifications/?id={self.notif_user.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted'], 1)
        self.assertFalse(Notification.objects.filter(pk=self.notif_user.pk).exists())

    def test_delete_admin_global_notification(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/v1/utilisateur/notifications/?notification_id={self.notif_global.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted'], 1)
        self.assertFalse(Notification.objects.filter(pk=self.notif_global.pk).exists())

    def test_delete_all_user_notifications(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete('/api/v1/utilisateur/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted'], 1)
        self.assertFalse(Notification.objects.filter(pk=self.notif_user.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=self.notif_global.pk).exists())

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_one_tap_login(self, mock_verify):
        mock_verify.return_value = {
            'email': 'onetap@example.com',
            'sub': '1234567890',
            'given_name': 'One',
            'family_name': 'Tap',
            'email_verified': True
        }
        response = self.client.post('/api/v1/auth/google/', {'credential': 'fake_google_token_123'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['email'], 'onetap@example.com')
        self.assertTrue(User.objects.filter(email='onetap@example.com').exists())


class SupprimerCompteTest(APITestCase):
    """Tests pour l'endpoint de suppression de compte (DELETE /api/v1/auth/me/supprimer-compte/)."""

    def setUp(self):
        self.url = '/api/v1/auth/me/supprimer-compte/'
        self.user = User.objects.create_user(
            username='delete_me_user',
            email='deleteme@example.com',
            password='Password123!'
        )
        self.admin = User.objects.create_superuser(
            username='protected_admin',
            email='admin_nodelete@example.com',
            password='AdminPassword123!'
        )

    def test_user_can_delete_own_account(self):
        """Un utilisateur normal peut supprimer son propre compte."""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('supprimé', response.data['detail'])
        # Vérifier que le compte est bien supprimé
        self.assertFalse(User.objects.filter(email='deleteme@example.com').exists())

    def test_admin_cannot_delete_own_account(self):
        """Un administrateur ne peut PAS supprimer son propre compte."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 403)
        # Vérifier que le compte admin existe toujours
        self.assertTrue(User.objects.filter(email='admin_nodelete@example.com').exists())

    def test_unauthenticated_cannot_delete(self):
        """Un utilisateur non connecté ne peut pas appeler cet endpoint."""
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 401)





