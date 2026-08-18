from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status

User = get_user_model()


TEST_THROTTLE_SETTINGS = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'dj_rest_auth.jwt_auth.JWTCookieAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'login_ip': '5/min',
        'login_credential': '3/min',
        'register_ip': '3/min',
        'register_email': '2/min',
        'resend_email_short': '2/min',
        'resend_email_daily': '5/day',
        'password_reset_ip': '3/min',
        'password_reset_email': '2/min',
        'change_email': '2/min',
        'ia_anon': '2/min',
        'ia_user': '3/min',
    },
}


@override_settings(REST_FRAMEWORK=TEST_THROTTLE_SETTINGS)
class RateLimitingAPITestCase(APITestCase):

    def setUp(self):
        from django.core.cache import cache
        from rest_framework.settings import api_settings
        from utilisateur.throttles import (
            ConfigurableRateThrottle, LoginIPThrottle, LoginCredentialThrottle,
            RegisterIPThrottle, RegisterEmailThrottle, IARecommandationThrottle
        )
        cache.clear()

        # Configurer directement les taux de test dans DRF api_settings et les classes de throttle
        rates = TEST_THROTTLE_SETTINGS['DEFAULT_THROTTLE_RATES']
        api_settings.DEFAULT_THROTTLE_RATES.update(rates)
        ConfigurableRateThrottle.THROTTLE_RATES.update(rates)

        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='Password123!',
            telephone='+237699999999'
        )

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_web_login_rate_limiting_credential(self):
        """Teste que les tentatives répétées de connexion Web avec le même identifiant lèvent un HTTP 429."""
        url = '/api/v1/auth/web/login/'
        payload = {'email': 'testuser@example.com', 'password': 'WrongPassword123!'}

        # 3 premières requêtes (limite à 3/min)
        for i in range(3):
            res = self.client.post(url, payload, format='json')
            self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED])

        # 4ème requête dépassera la limite 'login_credential' (3/min) -> HTTP 429
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_mobile_login_rate_limiting_ip(self):
        """Teste la limitation par IP/identifiant sur le login mobile."""
        url = '/api/v1/auth/mobile/login/'
        headers = {'HTTP_X_CLIENT_TYPE': 'mobile'}
        payload = {'email': 'nonexistent@example.com', 'password': 'WrongPassword'}

        # 3 requêtes avec le même email -> bloque à la 4ème
        for i in range(3):
            self.client.post(url, payload, format='json', **headers)

        res = self.client.post(url, payload, format='json', **headers)
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_register_rate_limiting_email(self):
        """Teste que les inscriptions répétées avec le même email retournent HTTP 429."""
        url = '/api/v1/auth/registration/'
        payload = {
            'email': 'spam_user@example.com',
            'password1': 'Password123!',
            'password2': 'Password123!',
        }

        # 2 requêtes autorisées (register_email = 2/min)
        for i in range(2):
            self.client.post(url, payload, format='json')

        # 3ème requête doit renvoyer HTTP 429
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch('laboratoire.views.demander_recommandation_ia')
    def test_ia_recommandation_rate_limiting_anonymous(self, mock_ia):
        """Teste que les requêtes d'IA anonymes sont limitées (ia_anon = 2/min)."""
        mock_ia.return_value = {
            'message': 'Voici des recommandations',
            'parfums_existants_recommandes': []
        }
        url = '/api/v1/lab/ia-recommandation/'
        payload = {'prompt': 'Je cherche un parfum ambré'}

        # 2 requêtes autorisées
        for i in range(2):
            res = self.client.post(url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 3ème requête anonyme -> HTTP 429
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch('laboratoire.views.demander_recommandation_ia')
    def test_ia_recommandation_rate_limiting_authenticated_user(self, mock_ia):
        """Teste que les requêtes d'IA connectées bénéficient d'un quota propre (ia_user = 3/min)."""
        mock_ia.return_value = {
            'message': 'Voici des recommandations',
            'parfums_existants_recommandes': []
        }
        url = '/api/v1/lab/ia-recommandation/'
        payload = {'prompt': 'Je cherche une essence de fleur'}

        self.client.force_authenticate(self.user)

        # 3 requêtes autorisées pour l'utilisateur connecté
        for i in range(3):
            res = self.client.post(url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 4ème requête connectée -> HTTP 429
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
