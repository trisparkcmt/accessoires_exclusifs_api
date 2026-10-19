from decimal import Decimal
from allauth.account.forms import AddEmailForm
from allauth.account.forms import default_token_generator
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from allauth.account.utils import url_str_to_user_pk
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from .permissions import (
    IsSuperadmin, IsActiveSuperadmin, IsActiveServeuse, IsSuperadminOrActiveServeuse,
    IsActivePrestataire, IsActiveLivreur, IsActiveClient, DepensePermission,
    IsSuperadminOrServeuseReadOnly, IsSuperadminOnly, is_active_serveuse,
)
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404, render
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from dj_rest_auth.views import LoginView, PasswordResetView, LogoutView
from dj_rest_auth.jwt_auth import get_refresh_view
from dj_rest_auth.app_settings import api_settings as dj_rest_auth_settings
from .serializers import (
    UserSerializer, PrestataireSerializer, PrestataireApplicationSerializer,
    PrestataireValidationSerializer, MeSerializer, MeUpdateSerializer,
    NotificationSerializer, PayoutTransactionSerializer, PayoutRequestSerializer,
    LivreurSerializer, LivreurUpdateSerializer, LivreurCommandeSerializer,
    ServeusesSerializer, ServeusesUpdateSerializer, DepenseSerializer, ClientSerializer,
    BoutiqueSerializer, BoutiqueApplicationSerializer, BoutiqueMeUpdateSerializer, BoutiqueAdminUpdateSerializer, BoutiqueValidationSerializer, BoutiqueAdminDetailSerializer,
    VenteBoutiqueSerializer, VersementBoutiqueSerializer
)
from .models import Prestataire, User, Notification, PayoutTransaction, CommissionLog, Livreur, Serveuse, Client, Depense, Boutique
from orders.models import Commande
from .throttles import (
    ChangeEmailThrottle,
    LoginCredentialThrottle,
    LoginIPThrottle,
    PasswordResetEmailThrottle,
    PasswordResetIPThrottle,
    RegisterEmailThrottle,
    RegisterIPThrottle,
    ResendEmailDailyThrottle,
    ResendEmailShortThrottle,
)
import random
import string
import requests
import uuid

AuthUser = get_user_model()

# ============================================================
# VUE DE CONNEXION HYBRIDE (Cookie pour web + JSON pour mobile)
# ============================================================

from rest_framework.views import APIView

class DeprecatedLoginView(APIView):
    """
    Vue obsolète pour empêcher l'utilisation du login générique non sécurisé.
    """
    permission_classes = (AllowAny,)
    throttle_classes = [LoginIPThrottle]

    def post(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "L'endpoint '/api/v1/auth/login/' est obsolète pour des raisons de sécurité. "
                          "Veuillez utiliser '/api/v1/auth/web/login/' pour les applications Web (sécurité HttpOnly) "
                          "ou '/api/v1/auth/mobile/login/' pour les clients Mobile/API."
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class WebLoginView(LoginView):
    """
    Vue de connexion spécifique pour le Web :
    - Génère et stocke les jetons d'accès et de rafraîchissement uniquement dans des cookies HttpOnly.
    - Supprime tout jeton (access et refresh) du corps JSON de la réponse pour empêcher l'accès via JavaScript (protection XSS).
    """
    throttle_classes = [LoginIPThrottle, LoginCredentialThrottle]

    def get_response(self):
        response = super().get_response()
        if response.status_code == 200:
            # Sécurité Web : on retire les tokens du corps de la réponse JSON.
            # Ils sont transmis de façon sécurisée via les cookies HttpOnly (Set-Cookie).
            response.data.pop('access', None)
            response.data.pop('refresh', None)
            if hasattr(self, 'user') and self.user:
                from utilisateur.serializers import UserSerializer
                serializer = UserSerializer(self.user, context={'request': self.request})
                response.data['user'] = serializer.data
                response.data['roles'] = serializer.data.get('roles', [])
        return response


class MobileLoginView(LoginView):
    """
    Vue de connexion spécifique pour Mobile / Clients API :
    - Retourne les jetons d'accès et de rafraîchissement directement dans le corps JSON de la réponse.
    - Supprime les cookies de la réponse pour ne pas polluer l'application mobile.
    """
    throttle_classes = [LoginIPThrottle, LoginCredentialThrottle]

    def post(self, request, *args, **kwargs):
        """
        Vérifie si la requête semble provenir d'un navigateur.
        Utilise les 'Fetch Metadata' (Sec-Fetch-*) que les navigateurs ne permettent pas de modifier via JS.
        """
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        client_type = request.headers.get('X-Client-Type', '').lower()
        
        # Sec-Fetch-Dest est envoyé par les navigateurs modernes. 'empty' est souvent utilisé par fetch/XHR.
        sec_fetch_dest = request.META.get('HTTP_SEC_FETCH_DEST', '').lower()
        origin = request.META.get('HTTP_ORIGIN', '').lower()

        # Un navigateur enverra presque toujours un Origin (pour CORS) ou Sec-Fetch-Dest
        is_browser = any(ua in user_agent for ua in ['mozilla', 'chrome', 'safari', 'firefox', 'edge']) or sec_fetch_dest != ''

        if (is_browser or origin) and client_type != 'mobile':
            return Response(
                {
                    "detail": "Accès refusé. Pour des raisons de sécurité, les navigateurs doivent utiliser '/api/v1/auth/web/login/'."
                },
                status=status.HTTP_403_FORBIDDEN
            )
        return super().post(request, *args, **kwargs)

    def get_response(self):
        response = super().get_response()
        if response.status_code == 200:
            # Client Mobile/API : on s'assure que les deux jetons sont présents dans le JSON
            if dj_rest_auth_settings.USE_JWT and hasattr(self, 'refresh_token') and self.refresh_token:
                response.data['refresh'] = str(self.refresh_token)
            if hasattr(self, 'user') and self.user:
                from utilisateur.serializers import UserSerializer
                serializer = UserSerializer(self.user, context={'request': self.request})
                response.data['user'] = serializer.data
                response.data['roles'] = serializer.data.get('roles', [])
            
            # Suppression des cookies de la réponse pour le client mobile
            if hasattr(response, 'cookies'):
                response.cookies.clear()
        return response


BaseRefreshView = get_refresh_view()

class HybridTokenRefreshView(BaseRefreshView):
    throttle_classes = [LoginIPThrottle]
    """
    Vue de rafraîchissement de jeton (refresh token) intelligente et adaptative :
    - Si la requête provient d'un Navigateur Web : les jetons sont transmis exclusivement
      dans les cookies HttpOnly (Set-Cookie). Ils sont retirés du corps JSON de la réponse
      pour empêcher tout accès JS (protection XSS).
    - Si la requête provient d'une App Mobile / Client API : les jetons sont retournés directement
      dans le corps JSON de la réponse, et aucun cookie n'est conservé.
    - Gère le cas où un compte utilisateur a été supprimé en nettoyant les cookies et en renvoyant un 401.
    """
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except AuthUser.DoesNotExist:
            response = Response(
                {"detail": "Utilisateur introuvable ou compte supprimé.", "code": "user_not_found"},
                status=status.HTTP_401_UNAUTHORIZED
            )
            cookie_name = dj_rest_auth_settings.JWT_AUTH_COOKIE
            refresh_cookie_name = dj_rest_auth_settings.JWT_AUTH_REFRESH_COOKIE
            refresh_cookie_path = dj_rest_auth_settings.JWT_AUTH_REFRESH_COOKIE_PATH
            cookie_samesite = dj_rest_auth_settings.JWT_AUTH_SAMESITE
            cookie_domain = dj_rest_auth_settings.JWT_AUTH_COOKIE_DOMAIN
            if cookie_name:
                response.delete_cookie(cookie_name, path='/', samesite=cookie_samesite, domain=cookie_domain)
            if refresh_cookie_name:
                response.delete_cookie(refresh_cookie_name, path=refresh_cookie_path, samesite=cookie_samesite, domain=cookie_domain)
            response.delete_cookie('sessionid', path='/')
            response.delete_cookie('csrftoken', path='/')
            return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
            client_type = request.headers.get('X-Client-Type', '').lower()
            sec_fetch_dest = request.META.get('HTTP_SEC_FETCH_DEST', '').lower()
            origin = request.META.get('HTTP_ORIGIN', '').lower()

            is_browser = (
                any(ua in user_agent for ua in ['mozilla', 'chrome', 'safari', 'firefox', 'edge'])
                or sec_fetch_dest != ''
                or bool(origin)
            ) and client_type != 'mobile'

            if is_browser:
                # Client WEB : Transmis dans le cookie HttpOnly, retiré du JSON pour la sécurité XSS
                response.data.pop('access', None)
                response.data.pop('refresh', None)
                response.data.pop('access_expiration', None)
                response.data.pop('refresh_expiration', None)
                response.data['detail'] = "Jeton rafraîchi avec succès."
            else:
                # Client MOBILE : Les jetons sont retournés dans le corps JSON
                if hasattr(response, 'cookies'):
                    response.cookies.clear()

        return response


class ThrottledPasswordResetView(PasswordResetView):
    throttle_classes = [PasswordResetIPThrottle, PasswordResetEmailThrottle]


class CustomLogoutView(LogoutView):
    """
    Vue de déconnexion personnalisée.
    - Désactive automatiquement les tokens FCM de l'utilisateur déconnecté.
    - S'assure que les cookies JWT sont correctement supprimés avec les attributs
      SameSite=None et Secure=True nécessaires pour le Cross-Origin/HTTPS.
    """
    def logout(self, request):
        # Désactiver les tokens FCM de l'utilisateur courant pour éviter tout push non désiré
        if request.user and request.user.is_authenticated:
            try:
                from utilisateur.models import FCMDevice
                token = None
                if hasattr(request, 'data') and isinstance(request.data, dict):
                    token = request.data.get('registration_token')

                logout_all = request.data.get('logout_all', False) if hasattr(request, 'data') and isinstance(request.data, dict) else False

                if token:
                    FCMDevice.objects.filter(registration_token=token, user=request.user).update(active=False)
                elif logout_all:
                    FCMDevice.objects.filter(user=request.user).update(active=False)
            except Exception as e:
                pass

        response = super().logout(request)
        
        cookie_name = dj_rest_auth_settings.JWT_AUTH_COOKIE
        refresh_cookie_name = dj_rest_auth_settings.JWT_AUTH_REFRESH_COOKIE
        refresh_cookie_path = dj_rest_auth_settings.JWT_AUTH_REFRESH_COOKIE_PATH
        cookie_secure = dj_rest_auth_settings.JWT_AUTH_SECURE
        cookie_samesite = dj_rest_auth_settings.JWT_AUTH_SAMESITE
        cookie_domain = dj_rest_auth_settings.JWT_AUTH_COOKIE_DOMAIN
        
        if cookie_name:
            response.delete_cookie(
                cookie_name,
                path='/',
                samesite=cookie_samesite,
                domain=cookie_domain
            )
        if refresh_cookie_name:
            response.delete_cookie(
                refresh_cookie_name,
                path=refresh_cookie_path,
                samesite=cookie_samesite,
                domain=cookie_domain
            )
        
        # Supprimer aussi les cookies de session classiques de Django pour éviter les conflits de session admin
        response.delete_cookie('sessionid', path='/')
        response.delete_cookie('csrftoken', path='/')
        
        return response


#==============================utils================================

def generate_promo_code(length=4):
    """Génère un code promo unique de type ACC-XXXXXX"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(chars) for _ in range(length))
    return f"ACC-{code}"

class AdminPagination(PageNumberPagination):
    """Configuration de la pagination pour l'admin (50 par page)"""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class PrestatairePagination(PageNumberPagination):
    """Configuration de la pagination pour le prestataire (20 par page)"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50



def confirm_email_direct(request, key):
    """Confirme directement l'email depuis le lien allauth."""
    confirmation = EmailConfirmationHMAC.from_key(key)
    if confirmation is None:
        try:
            confirmation = EmailConfirmation.objects.get(key=key)
        except EmailConfirmation.DoesNotExist:
            confirmation = None

    frontend_url = getattr(settings, 'FRONTEND_URL', 'https://dev.accessoiresexclusifs.com')

    if confirmation is None or confirmation.confirm(request) is None:
        error_html = """<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Lien expiré | Accessoires Exclusifs</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Outfit:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg-color: #08090c;
        --card-bg: rgba(17, 19, 26, 0.65);
        --border-color: rgba(197, 160, 89, 0.15);
        --primary-accent: #c5a059;
        --primary-accent-glow: rgba(197, 160, 89, 0.3);
        --text-primary: #ffffff;
        --text-secondary: #8e95a5;
        --error-color: #ef4444;
        --error-bg: rgba(239, 68, 68, 0.1);
        --error-border: rgba(239, 68, 68, 0.2);
      }
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }
      body {
        background-color: var(--bg-color);
        color: var(--text-primary);
        font-family: 'Inter', sans-serif;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow-x: hidden;
        position: relative;
      }
      body::before {
        content: "";
        position: absolute;
        width: 600px;
        height: 600px;
        background: radial-gradient(circle, rgba(197, 160, 89, 0.08) 0%, rgba(0,0,0,0) 70%);
        top: -150px;
        left: -150px;
        z-index: 0;
      }
      body::after {
        content: "";
        position: absolute;
        width: 600px;
        height: 600px;
        background: radial-gradient(circle, rgba(139, 92, 246, 0.05) 0%, rgba(0,0,0,0) 70%);
        bottom: -150px;
        right: -150px;
        z-index: 0;
      }
      main {
        position: relative;
        z-index: 10;
        padding: 24px;
        width: 100%;
        display: flex;
        justify-content: center;
      }
      .card {
        background: var(--card-bg);
        backdrop-filter: blur(24px);
        -webkit-backdrop-filter: blur(24px);
        border: 1px solid var(--border-color);
        box-shadow: 0 30px 60px rgba(0, 0, 0, 0.6), 0 0 80px rgba(197, 160, 89, 0.03);
        border-radius: 28px;
        padding: 48px 40px;
        width: 100%;
        max-width: 450px;
        text-align: center;
        animation: cardAppear 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
      }
      @keyframes cardAppear {
        from {
          opacity: 0;
          transform: translateY(20px) scale(0.98);
        }
        to {
          opacity: 1;
          transform: translateY(0) scale(1);
        }
      }
      .expired-icon {
        width: 80px;
        height: 80px;
        margin: 0 auto 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(197, 160, 89, 0.1);
        border-radius: 50%;
        color: var(--primary-accent);
        border: 1.5px solid rgba(197, 160, 89, 0.2);
        animation: pulseIcon 2s infinite ease-in-out;
      }
      @keyframes pulseIcon {
        0%, 100% {
          box-shadow: 0 0 0 0px rgba(197, 160, 89, 0.2);
        }
        50% {
          box-shadow: 0 0 0 12px rgba(197, 160, 89, 0);
        }
      }
      h1 {
        font-family: 'Outfit', sans-serif;
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 12px;
        background: linear-gradient(135deg, #ffffff 30%, #e5c07b 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      p {
        font-size: 15px;
        line-height: 1.6;
        color: var(--text-secondary);
        margin-bottom: 28px;
      }
      .input-group {
        position: relative;
        margin-bottom: 20px;
        text-align: left;
      }
      .input-group input {
        width: 100%;
        padding: 16px 20px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        color: var(--text-primary);
        font-size: 15px;
        font-family: 'Inter', sans-serif;
        transition: all 0.3s ease;
        outline: none;
      }
      .input-group input:focus {
        border-color: var(--primary-accent);
        box-shadow: 0 0 15px var(--primary-accent-glow);
        background: rgba(255, 255, 255, 0.04);
      }
      .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        padding: 16px 24px;
        background: linear-gradient(135deg, #c5a059 0%, #ab843c 100%);
        border: none;
        border-radius: 14px;
        color: #0b0c10;
        font-family: 'Outfit', sans-serif;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        box-shadow: 0 8px 20px rgba(197, 160, 89, 0.25);
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      }
      .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 28px rgba(197, 160, 89, 0.4);
      }
      .btn:active {
        transform: translateY(0);
      }
      .btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none !important;
        box-shadow: none !important;
      }
      .spinner {
        display: inline-block;
        width: 18px;
        height: 18px;
        border: 2px solid rgba(11, 12, 16, 0.3);
        border-radius: 50%;
        border-top-color: #0b0c10;
        animation: spin 0.8s linear infinite;
        margin-right: 10px;
      }
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
      .feedback {
        display: none;
        padding: 14px 16px;
        border-radius: 12px;
        font-size: 14px;
        margin-bottom: 20px;
        text-align: left;
        line-height: 1.5;
        animation: fadeIn 0.3s ease;
      }
      .feedback.error {
        background: var(--error-bg);
        border: 1px solid var(--error-border);
        color: #f87171;
      }
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-5px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .success-icon-container {
        width: 80px;
        height: 80px;
        margin: 0 auto 24px;
        position: relative;
      }
      .success-svg {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        display: block;
        stroke-width: 2;
        stroke: var(--primary-accent);
        stroke-miterlimit: 10;
        box-shadow: inset 0px 0px 0px var(--primary-accent);
        animation: fillSuccess .4s ease-in-out .4s forwards, scaleSuccess .3s ease-in-out .9s both;
      }
      .success-circle {
        stroke-dasharray: 166;
        stroke-dashoffset: 166;
        stroke-width: 2;
        stroke-miterlimit: 10;
        stroke: var(--primary-accent);
        fill: none;
        animation: strokeSuccess 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
      }
      .success-check {
        transform-origin: 50% 50%;
        stroke-dasharray: 48;
        stroke-dashoffset: 48;
        animation: strokeSuccess 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.8s forwards;
      }
      @keyframes fillSuccess {
        100% { box-shadow: inset 0px 0px 0px 40px rgba(197, 160, 89, 0.1); }
      }
      @keyframes scaleSuccess {
        0%, 100% { transform: none; }
        50% { transform: scale3d(1.1, 1.1, 1); }
      }
    </style>
  </head>
  <body>
    <main>
      <div class="card">
        <div class="expired-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h1>Lien expiré ou invalide</h1>
        <p>Ce lien de confirmation n'est plus valide. Entrez votre adresse email ci-dessous pour recevoir un nouveau lien de validation.</p>
        
        <div id="feedback" class="feedback"></div>
        
        <form id="resendForm">
          <div class="input-group">
            <input type="email" id="email" placeholder="Saisir votre adresse email" required>
          </div>
          <button type="submit" id="submitBtn" class="btn">Renvoyer le lien de confirmation</button>
        </form>
      </div>
    </main>
    <script>
      document.getElementById('resendForm').addEventListener('submit', function(e) {
        e.preventDefault();
        const emailInput = document.getElementById('email');
        const email = emailInput.value.trim();
        const button = document.getElementById('submitBtn');
        const feedback = document.getElementById('feedback');
        
        if (!email) return;
        
        button.disabled = true;
        button.innerHTML = '<span class="spinner"></span>Envoi en cours...';
        feedback.style.display = 'none';
        feedback.className = 'feedback';
        
        fetch('/api/v1/auth/registration/resend-email/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || ''
          },
          body: JSON.stringify({ email: email })
        })
        .then(async response => {
          const data = await response.json();
          if (response.ok) {
            document.querySelector('.card').innerHTML = `
              <div class="success-icon-container">
                <svg class="success-svg" viewBox="0 0 52 52">
                  <circle class="success-circle" cx="26" cy="26" r="25" fill="none"/>
                  <path class="success-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                </svg>
              </div>
              <h1 style="background: linear-gradient(135deg, #ffffff 30%, #10b981 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Lien envoyé !</h1>
              <p style="margin-bottom: 24px;">Un nouveau lien de confirmation a été envoyé avec succès à l'adresse <strong>${escapeHtml(email)}</strong>.</p>
              <p style="font-size: 13px; color: #64748b;">Pensez à vérifier vos spams ou courriers indésirables si vous ne le recevez pas dans quelques minutes.</p>
              <a href="{{ FRONTEND_URL }}" class="btn" style="margin-top: 32px;">Retourner à l'accueil</a>
            `;
          } else {
            button.disabled = false;
            button.innerHTML = 'Renvoyer le lien de confirmation';
            feedback.style.display = 'block';
            feedback.classList.add('error');
            
            let errorMsg = "Une erreur est survenue lors du renvoi.";
            if (data.detail) {
              errorMsg = data.detail;
            } else if (data.email) {
              errorMsg = Array.isArray(data.email) ? data.email[0] : data.email;
            } else if (data.non_field_errors) {
              errorMsg = Array.isArray(data.non_field_errors) ? data.non_field_errors[0] : data.non_field_errors;
            }
            feedback.innerHTML = errorMsg;
          }
        })
        .catch(error => {
          button.disabled = false;
          button.innerHTML = 'Renvoyer le lien de confirmation';
          feedback.style.display = 'block';
          feedback.classList.add('error');
          feedback.innerHTML = "Impossible de se connecter au serveur. Veuillez réessayer.";
        });
      });

      function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
          const cookies = document.cookie.split(';');
          for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
            }
          }
        }
        return cookieValue;
      }

      function escapeHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
      }
    </script>
  </body>
</html>""".replace('{{ FRONTEND_URL }}', frontend_url)
        return HttpResponse(error_html, status=400)

    success_html = """<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Email confirmé | Accessoires Exclusifs</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Outfit:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg-color: #08090c;
        --card-bg: rgba(17, 19, 26, 0.65);
        --border-color: rgba(197, 160, 89, 0.15);
        --primary-accent: #c5a059;
        --primary-accent-glow: rgba(197, 160, 89, 0.4);
        --text-primary: #ffffff;
        --text-secondary: #8e95a5;
        --glow: rgba(197, 160, 89, 0.15);
      }
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }
      body {
        background-color: var(--bg-color);
        color: var(--text-primary);
        font-family: 'Inter', sans-serif;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow-x: hidden;
        position: relative;
      }
      body::before {
        content: "";
        position: absolute;
        width: 600px;
        height: 600px;
        background: radial-gradient(circle, rgba(197, 160, 89, 0.08) 0%, rgba(0,0,0,0) 70%);
        top: -150px;
        left: -150px;
        z-index: 0;
      }
      body::after {
        content: "";
        position: absolute;
        width: 600px;
        height: 600px;
        background: radial-gradient(circle, rgba(139, 92, 246, 0.05) 0%, rgba(0,0,0,0) 70%);
        bottom: -150px;
        right: -150px;
        z-index: 0;
      }
      main {
        position: relative;
        z-index: 10;
        padding: 24px;
        width: 100%;
        display: flex;
        justify-content: center;
      }
      .card {
        background: var(--card-bg);
        backdrop-filter: blur(24px);
        -webkit-backdrop-filter: blur(24px);
        border: 1px solid var(--border-color);
        box-shadow: 0 30px 60px rgba(0, 0, 0, 0.6), 0 0 80px rgba(197, 160, 89, 0.03);
        border-radius: 28px;
        padding: 48px 40px;
        width: 100%;
        max-width: 450px;
        text-align: center;
        animation: cardAppear 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
      }
      @keyframes cardAppear {
        from {
          opacity: 0;
          transform: translateY(20px) scale(0.98);
        }
        to {
          opacity: 1;
          transform: translateY(0) scale(1);
        }
      }
      h1 {
        font-family: 'Outfit', sans-serif;
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 12px;
        background: linear-gradient(135deg, #ffffff 30%, #e5c07b 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      p {
        font-size: 15px;
        line-height: 1.6;
        color: var(--text-secondary);
        margin-bottom: 32px;
      }
      .success-icon-container {
        width: 80px;
        height: 80px;
        margin: 0 auto 24px;
        position: relative;
      }
      .success-svg {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        display: block;
        stroke-width: 2;
        stroke: var(--primary-accent);
        stroke-miterlimit: 10;
        box-shadow: inset 0px 0px 0px var(--primary-accent);
        animation: fillSuccess .4s ease-in-out .4s forwards, scaleSuccess .3s ease-in-out .9s both;
      }
      .success-circle {
        stroke-dasharray: 166;
        stroke-dashoffset: 166;
        stroke-width: 2;
        stroke-miterlimit: 10;
        stroke: var(--primary-accent);
        fill: none;
        animation: strokeSuccess 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
      }
      .success-check {
        transform-origin: 50% 50%;
        stroke-dasharray: 48;
        stroke-dashoffset: 48;
        animation: strokeSuccess 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.8s forwards;
      }
      @keyframes strokeSuccess {
        100% { stroke-dashoffset: 0; }
      }
      @keyframes fillSuccess {
        100% { box-shadow: inset 0px 0px 0px 40px rgba(197, 160, 89, 0.1); }
      }
      @keyframes scaleSuccess {
        0%, 100% { transform: none; }
        50% { transform: scale3d(1.1, 1.1, 1); }
      }
      .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        padding: 16px 24px;
        background: linear-gradient(135deg, #c5a059 0%, #ab843c 100%);
        border: none;
        border-radius: 14px;
        color: #0b0c10;
        font-family: 'Outfit', sans-serif;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        box-shadow: 0 8px 20px rgba(197, 160, 89, 0.25);
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      }
      .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 28px rgba(197, 160, 89, 0.4);
      }
      .btn:active {
        transform: translateY(0);
      }
    </style>
  </head>
  <body>
    <main>
      <div class="card">
        <div class="success-icon-container">
          <svg class="success-svg" viewBox="0 0 52 52">
            <circle class="success-circle" cx="26" cy="26" r="25" fill="none"/>
            <path class="success-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
          </svg>
        </div>
        <h1>Compte activé !</h1>
        <p>Votre adresse email a été confirmée avec succès. Vous pouvez maintenant retourner dans l'application pour vous connecter.</p>
        <a href="{{ FRONTEND_URL }}" class="btn">Retourner à l'application</a>
      </div>
    </main>
  </body>
</html>""".replace('{{ FRONTEND_URL }}', frontend_url)
    return HttpResponse(success_html, status=200)


def password_reset_confirm_page(request, uid, token):
    """Page backend pour choisir un nouveau mot de passe depuis le lien email."""
    try:
        user_pk = url_str_to_user_pk(uid)
        user = AuthUser.objects.get(pk=user_pk)
    except (AuthUser.DoesNotExist, TypeError, ValueError, OverflowError):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(
            request,
            'account/password_reset_result.html',
            {
                'success': False,
                'title': 'Lien invalide ou expire',
                'message': "Ce lien de reinitialisation n'est plus valide. Demandez un nouveau lien depuis l'application.",
                'frontend_url': settings.FRONTEND_URL,
            },
            status=400,
        )

    if request.method == 'POST':
        form = SetPasswordForm(user=user, data=request.POST)
        if form.is_valid():
            form.save()
            _send_password_changed_email(request, user)
            return render(
                request,
                'account/password_reset_result.html',
                {
                    'success': True,
                    'title': 'Mot de passe modifie',
                    'message': "Votre mot de passe a bien ete modifie. Vous pouvez retourner dans l'application.",
                    'frontend_url': settings.FRONTEND_URL,
                },
            )
    else:
        form = SetPasswordForm(user=user)

    return render(
        request,
        'account/password_reset_confirm_form.html',
        {
            'form': form,
            'frontend_url': settings.FRONTEND_URL,
        },
    )


def _send_password_changed_email(request, user):
    context = {
        'user': user,
        'frontend_url': settings.FRONTEND_URL,
        'request': request,
    }
    subject = 'Votre mot de passe a ete modifie'
    text_content = render_to_string('account/email/password_changed_message.txt', context)
    html_content = render_to_string('account/email/password_changed_message.html', context)

    msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)

#==============================utilisateur==========================

@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def manage_me(request):
    """
    Permet à l'utilisateur connecté de voir ou modifier son profil.
    """
    user = request.user

    if request.method == 'GET':
        user = (
            User.objects
            .select_related('client', 'client__prestataire', 'client__livreur', 'client__serveuse')
            .prefetch_related(
                'client__favoris__parfum__tags',
                'client__favoris__accessoire',
            )
            .get(pk=user.pk)
        )
        serializer = MeSerializer(user, context={'request': request})
        return Response(serializer.data) 

    elif request.method in ['PUT', 'PATCH']:        
        if 'email' in request.data:
            return Response(
                {"detail": "Utilisez /api/v1/auth/me/change-email/ pour modifier l'adresse email."},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_telephone = request.data.get('telephone')
        if new_telephone and new_telephone != user.telephone and user.has_usable_password():
            current_password = request.data.get('current_password')
            if not current_password or not user.check_password(current_password):
                return Response(
                    {"detail": "Le mot de passe actuel est requis pour modifier le numéro de téléphone."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        partial = request.method == 'PATCH'
        serializer = MeUpdateSerializer(user, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#==============================supprimer compte======================

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def supprimer_compte(request):
    """
    Permet à un utilisateur connecté de supprimer définitivement son propre compte.
    Les comptes administrateurs (is_superuser=True) ne peuvent PAS être supprimés,
    même par l'administrateur lui-même.
    """
    user = request.user

    if user.is_superuser:
        return Response(
            {"detail": "Les comptes administrateurs ne peuvent pas être supprimés."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Déconnecter l'utilisateur avant suppression (invalider les sessions/tokens)
    from django.contrib.auth import logout as django_logout
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
    try:
        # Blacklister tous les tokens JWT actifs de l'utilisateur
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
    except Exception:
        pass  # Si le blacklist n'est pas activé, on continue

    # Supprimer le compte (cascade sur les objets liés)
    email = user.email
    user.delete()

    import logging
    logger = logging.getLogger(__name__)
    logger.info("[Compte supprimé] %s a supprimé son compte.", email)

    return Response(
        {"detail": "Votre compte a été supprimé définitivement."},
        status=status.HTTP_200_OK
    )

#==============================email=================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ChangeEmailThrottle])
def change_email(request):
    """Demande le changement d'email via le flux de confirmation allauth."""
    user = request.user
    new_email = request.data.get('email')

    if not new_email:
        return Response({"detail": "L'adresse email est requise."}, status=status.HTTP_400_BAD_REQUEST)

    if new_email == user.email:
        return Response(
            {"detail": "Cette adresse est déjà associée à votre compte."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if user.has_usable_password():
        current_password = request.data.get('current_password')
        if not current_password or not user.check_password(current_password):
            return Response(
                {"detail": "Le mot de passe actuel est requis pour modifier l'adresse email."},
                status=status.HTTP_400_BAD_REQUEST
            )

    form = AddEmailForm(user, data={'email': new_email})
    if not form.is_valid():
        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

    email_address = form.save(request)
    return Response(
        {
            "detail": "Un email de confirmation a été envoyé à la nouvelle adresse.",
            "email": email_address.email,
        },
        status=status.HTTP_200_OK
    )

#==============================prestataire==========================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def apply_prestataire(request):
    """
    Endpoint pour qu'un utilisateur postule en tant que prestataire.
    La photo est obligatoire.
    """
    user = request.user
    
    # Sécurité : On s'assure que le profil Client existe (au cas où le signal aurait échoué)
    from .models import Client
    client, _ = Client.objects.get_or_create(user=user)
    
    if hasattr(client, 'prestataire'):
        return Response({"detail": "Vous avez déjà une demande en cours ou êtes déjà prestataire."}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = PrestataireApplicationSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(client=user.client, statut='en_attente')
        send_mail(
            "Demande de partenariat reçue",
            f"Bonjour {user.first_name}, votre demande pour devenir prestataire est bien reçue.",
            "noreply@accessoire-exclusif.com",
            [user.email],
            fail_silently=True,
        )
        return Response({"detail": "Demande envoyée avec succès."}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def cancel_prestataire_application(request):
    """
    Permet à un client d'annuler sa demande de prestataire en attente.
    """
    user = request.user
    if not hasattr(user, 'client') or not hasattr(user.client, 'prestataire'):
        return Response({"detail": "Aucune demande de prestataire trouvée."}, status=status.HTTP_404_NOT_FOUND)

    prestataire = user.client.prestataire
    if prestataire.statut != 'en_attente':
        return Response(
            {"detail": "Impossible d'annuler une demande qui a déjà été traitée ou activée."},
            status=status.HTTP_400_BAD_REQUEST
        )

    prestataire.delete()
    return Response({"detail": "Votre demande de prestataire a été annulée avec succès."}, status=status.HTTP_200_OK)


@api_view(['POST', 'PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_photo_profil(request):
    """
    Permet à une serveuse, un livreur, un prestataire ou une boutique connecté de mettre à jour sa photo de profil.
    L'admin ne peut pas modifier la photo via les endpoints d'administration.
    """
    user = request.user
    if not hasattr(user, 'client'):
        return Response({"detail": "Profil client introuvable."}, status=status.HTTP_400_BAD_REQUEST)

    client = user.client
    target_profiles = []

    if hasattr(client, 'serveuse'):
        target_profiles.append(client.serveuse)
    if hasattr(client, 'livreur'):
        target_profiles.append(client.livreur)
    if hasattr(client, 'prestataire'):
        target_profiles.append(client.prestataire)
    if hasattr(client, 'boutique'):
        target_profiles.append(client.boutique)

    if not target_profiles:
        return Response(
            {"detail": "Vous n'avez aucun rôle (serveuse, livreur, prestataire, boutique) permettant d'ajouter une photo."},
            status=status.HTTP_403_FORBIDDEN
        )

    photo_file = request.FILES.get('photo') or request.data.get('photo')
    if not photo_file:
        return Response({"detail": "Le fichier 'photo' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

    for profile in target_profiles:
        profile.photo = photo_file
        profile.save()

    updated_photo_url = request.build_absolute_uri(target_profiles[0].photo.url) if target_profiles[0].photo else None
    return Response({
        "detail": "Photo de profil mise à jour avec succès.",
        "photo": updated_photo_url
    }, status=status.HTTP_200_OK)


#============================== Boutique ==========================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def apply_boutique(request):
    """
    Endpoint pour qu'un client postule pour créer sa boutique.
    La photo et le nom sont obligatoires.
    """
    user = request.user
    client, _ = Client.objects.get_or_create(user=user)

    if hasattr(client, 'boutique'):
        return Response({"detail": "Vous avez déjà une demande de boutique en cours ou une boutique enregistrée."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = BoutiqueApplicationSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        boutique = serializer.save(client=client, statut='en_attente')

        # --- Notification in-app pour l'admin ---
        Notification.objects.create(
            type='demande_boutique',
            title="Nouvelle demande de boutique",
            message=f"{user.first_name or user.username} ({user.email}) a soumis une demande pour ouvrir la boutique '{boutique.nom}'.",
            is_global_admin=True,
            url=f"/admin/boutiques/{boutique.id}/",
            metadata={'boutique_id': boutique.id, 'client_email': user.email},
        )

        # --- Email HTML à l'admin ---
        try:
            admin_emails = list(
                User.objects.filter(is_superuser=True, is_active=True).values_list('email', flat=True)
            )
            if admin_emails:
                admin_context = {
                    'nom_boutique': boutique.nom,
                    'client_nom': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
                    'client_email': user.email,
                    'client_telephone': getattr(user, 'telephone', None) or '',
                    'ville': getattr(boutique, 'ville', '') or '',
                    'adresse': getattr(boutique, 'adresse', '') or '',
                }
                html_body = render_to_string('emails/boutique_request_admin.html', admin_context)
                from django.utils.html import strip_tags
                text_body = strip_tags(html_body)
                email_admin = EmailMultiAlternatives(
                    subject="[Accessoires Exclusifs] Nouvelle demande de boutique",
                    body=text_body,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@accessoire-exclusif.com'),
                    to=admin_emails,
                )
                email_admin.attach_alternative(html_body, "text/html")
                email_admin.send(fail_silently=True)
        except Exception:
            pass

        return Response({
            "detail": "Demande de boutique envoyée avec succès.",
            "boutique": BoutiqueSerializer(boutique, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def cancel_boutique_application(request):
    """
    Permet à un client d'annuler sa demande de création de boutique en attente.
    """
    user = request.user
    if not hasattr(user, 'client') or not hasattr(user.client, 'boutique'):
        return Response({"detail": "Aucune boutique trouvée pour ce compte."}, status=status.HTTP_404_NOT_FOUND)

    boutique = user.client.boutique
    if boutique.statut != 'en_attente':
        return Response(
            {"detail": "Impossible d'annuler une boutique qui a déjà été traitée ou activée."},
            status=status.HTTP_400_BAD_REQUEST
        )

    boutique.delete()
    return Response({"detail": "Votre demande de boutique a été annulée avec succès."}, status=status.HTTP_200_OK)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def me_boutique(request):
    """
    GET: Consulter les informations de sa propre boutique.
    PATCH: Modifier les informations de sa propre boutique (nom, adresse, ville, telephone).
    DELETE: Annuler sa demande de boutique.
    """
    user = request.user
    if not hasattr(user, 'client') or not hasattr(user.client, 'boutique'):
        return Response({"detail": "Vous n'avez pas de boutique."}, status=status.HTTP_404_NOT_FOUND)

    boutique = user.client.boutique

    if request.method == 'GET':
        serializer = BoutiqueSerializer(boutique, context={'request': request})
        data = serializer.data
        data['produits'] = get_boutique_produits_paginated(boutique, request)
        return Response(data)

    elif request.method == 'PATCH':
        serializer = BoutiqueMeUpdateSerializer(boutique, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(BoutiqueSerializer(boutique, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if boutique.statut != 'en_attente':
            return Response(
                {"detail": "Impossible d'annuler une boutique qui a déjà été traitée ou activée."},
                status=status.HTTP_400_BAD_REQUEST
            )
        boutique.delete()
        return Response({"detail": "Votre demande de boutique a été annulée avec succès."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_boutique_produits(request):
    """
    GET: Liste paginée à 100 par page de TOUS les produits (Parfums & Accessoires) postés par la boutique de l'utilisateur connecté.
    Filtres supportés :
    - ?type=all|parfum|accessoire (défaut: all)
    - ?categorie=<id_ou_slug> (id/slug de la CategorieParfum ou du TypeAccessoire)
    - ?search=<terme> (nom, marque, SKU)
    - ?actif=true|false
    - ?ordering=-date_creation|prix_unitaire|stock_quantite|nom
    - ?page=1
    - ?page_size=100 (défaut: 100, max: 100)
    """
    user = request.user
    if not hasattr(user, 'client') or not hasattr(user.client, 'boutique'):
        return Response({"detail": "Vous n'avez pas de boutique."}, status=status.HTTP_404_NOT_FOUND)

    boutique = user.client.boutique
    return Response(get_boutique_produits_paginated(boutique, request))


@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def admin_boutiques_list(request):
    """
    Liste toutes les boutiques (pour l'administrateur / serveuse).
    Possibilité de filtrer par statut via ?statut=en_attente|actif|suspendu|refuse.
    """
    statut = request.query_params.get('statut')
    queryset = Boutique.objects.select_related('client__user').all().order_by('-date_creation')
    if statut:
        queryset = queryset.filter(statut=statut)

    serializer = BoutiqueSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)


def get_boutique_produits_paginated(boutique, request):
    """
    Récupère, filtre et pagine les produits (Parfums & Accessoires) d'une boutique.
    Pagine à 100 éléments par page par défaut.
    """
    from catalogue.models import Parfum, Accessoire
    from catalogue.serializers import ParfumSerializer, AccessoireSerializer
    from django.db.models import Q

    type_produit = request.query_params.get('type', 'all').lower() if request else 'all'
    categorie = request.query_params.get('categorie') if request else None
    search = request.query_params.get('search') if request else None
    actif = request.query_params.get('actif') if request else None
    ordering = request.query_params.get('ordering', '-date_creation') if request else '-date_creation'

    try:
        page = max(1, int(request.query_params.get('page', 1))) if request else 1
    except (ValueError, TypeError):
        page = 1

    try:
        page_size = min(100, max(1, int(request.query_params.get('page_size', 100)))) if request else 100
    except (ValueError, TypeError):
        page_size = 100

    items = []

    # 1. Parfums
    if type_produit in ('all', 'parfum'):
        qs_parfums = Parfum.objects.filter(boutique=boutique).select_related('categorie', 'boutique').prefetch_related('tags')
        if search:
            qs_parfums = qs_parfums.filter(
                Q(nom__icontains=search) | Q(marque__icontains=search) | Q(reference_sku__icontains=search) | Q(description_courte__icontains=search)
            )
        if actif in ('true', '1', 'yes'):
            qs_parfums = qs_parfums.filter(actif=True)
        elif actif in ('false', '0', 'no'):
            qs_parfums = qs_parfums.filter(actif=False)
        if categorie:
            if str(categorie).isdigit():
                qs_parfums = qs_parfums.filter(categorie_id=int(categorie))
            else:
                qs_parfums = qs_parfums.filter(Q(categorie__slug=categorie) | Q(categorie__nom__icontains=categorie))
        
        for p in qs_parfums:
            data = ParfumSerializer(p, context={'request': request}).data
            data['type_produit'] = 'parfum'
            items.append((p.date_creation, p.id, data))

    # 2. Accessoires
    if type_produit in ('all', 'accessoire'):
        qs_accessoires = Accessoire.objects.filter(boutique=boutique).select_related('type_accessoire', 'boutique').prefetch_related('tags')
        if search:
            qs_accessoires = qs_accessoires.filter(
                Q(nom__icontains=search) | Q(marque__icontains=search) | Q(reference_sku__icontains=search) | Q(description_courte__icontains=search)
            )
        if actif in ('true', '1', 'yes'):
            qs_accessoires = qs_accessoires.filter(actif=True)
        elif actif in ('false', '0', 'no'):
            qs_accessoires = qs_accessoires.filter(actif=False)
        if categorie:
            if str(categorie).isdigit():
                qs_accessoires = qs_accessoires.filter(type_accessoire_id=int(categorie))
            else:
                qs_accessoires = qs_accessoires.filter(Q(type_accessoire__slug=categorie) | Q(type_accessoire__nom__icontains=categorie))
        
        for a in qs_accessoires:
            data = AccessoireSerializer(a, context={'request': request}).data
            data['type_produit'] = 'accessoire'
            items.append((a.date_creation, a.id, data))

    # Tri global
    reverse_sort = ordering.startswith('-')
    sort_key_name = ordering.lstrip('-')

    if sort_key_name == 'prix_unitaire':
        items.sort(key=lambda x: Decimal(str(x[2].get('prix_unitaire', 0))), reverse=reverse_sort)
    elif sort_key_name == 'nom':
        items.sort(key=lambda x: str(x[2].get('nom', '')).lower(), reverse=reverse_sort)
    elif sort_key_name in ('stock_quantite', 'stock'):
        items.sort(key=lambda x: int(x[2].get('stock_quantite', 0)), reverse=reverse_sort)
    else:
        items.sort(key=lambda x: x[0], reverse=reverse_sort)

    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = [item[2] for item in items[start_idx:end_idx]]

    return {
        "count": total_items,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "next": page + 1 if page < total_pages else None,
        "previous": page - 1 if page > 1 else None,
        "results": page_items
    }


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_boutique_detail(request, pk):
    """
    GET: Détails d'une boutique (Admin) incluant ses produits postés paginés à 100 par page.
    PATCH: Modifier une boutique (statut, nom, etc.) par un Admin.
    DELETE: Supprimer une boutique (Admin).
    """
    boutique = get_object_or_404(Boutique, pk=pk)

    if request.method == 'GET':
        serializer = BoutiqueAdminDetailSerializer(boutique, context={'request': request})
        data = dict(serializer.data)
        data['produits'] = get_boutique_produits_paginated(boutique, request)
        return Response(data)

    elif request.method == 'PATCH':
        serializer = BoutiqueAdminUpdateSerializer(boutique, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(BoutiqueSerializer(boutique, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        boutique.delete()
        return Response({"detail": "Boutique supprimée avec succès."}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def admin_boutique_produits(request, pk):
    """
    GET: Endpoint dédié pour lister les produits (Parfums & Accessoires) postés par la boutique <pk> avec pagination à 100 par page et filtres.
    Filtres supportés :
    - ?type=all|parfum|accessoire
    - ?categorie=<id_ou_slug>
    - ?search=<terme>
    - ?actif=true|false
    - ?ordering=-date_creation|prix_unitaire|stock_quantite|nom
    - ?page=1
    - ?page_size=100
    """
    boutique = get_object_or_404(Boutique, pk=pk)
    return Response(get_boutique_produits_paginated(boutique, request))


@api_view(['PATCH'])
@permission_classes([IsSuperadmin])
def admin_boutique_parfum_toggle_actif(request, pk, parfum_pk):
    """
    PATCH: Activer ou désactiver un parfum appartenant à une boutique (Admin uniquement).
    L'admin ne peut modifier QUE le champ `actif`. Toute autre modification est ignorée.

    Body: { "actif": true } ou { "actif": false }
    """
    from catalogue.models import Parfum
    boutique = get_object_or_404(Boutique, pk=pk)
    parfum = get_object_or_404(Parfum, pk=parfum_pk, boutique=boutique)

    actif = request.data.get('actif')
    if actif is None:
        return Response(
            {"detail": "Le champ 'actif' est requis."},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not isinstance(actif, bool):
        return Response(
            {"detail": "Le champ 'actif' doit être un booléen (true ou false)."},
            status=status.HTTP_400_BAD_REQUEST
        )

    parfum.actif = actif
    parfum.save(update_fields=['actif'])

    return Response({
        "detail": f"Parfum {'activé' if actif else 'désactivé'} avec succès.",
        "parfum_id": parfum.pk,
        "nom": parfum.nom,
        "actif": parfum.actif,
        "boutique_id": boutique.pk,
        "boutique_nom": boutique.nom,
    }, status=status.HTTP_200_OK)

@api_view(['POST', 'PATCH'])
@permission_classes([IsSuperadmin])
@parser_classes([JSONParser, FormParser])
def validate_boutique(request, pk):
    """
    Endpoint pour valider et activer une boutique (Réservé à l'Admin).
    L'admin doit renseigner le taux_commission (pourcentage).
    """
    boutique = get_object_or_404(Boutique, pk=pk)

    if boutique.statut != 'en_attente':
        return Response({"detail": "Cette boutique a déjà été traitée ou n'est plus en attente."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = BoutiqueValidationSerializer(boutique, data=request.data)
    if serializer.is_valid():
        boutique = serializer.save(statut='actif')

        user = boutique.client.user

        # --- Notification in-app pour le client ---
        Notification.objects.create(
            recipient=user,
            type='boutique_validee',
            title="Boutique activée !",
            message=f"Votre boutique '{boutique.nom}' a été validée et est maintenant active sur la plateforme.",
            url="/me/boutique/",
            metadata={'boutique_id': boutique.id, 'taux_commission': str(boutique.taux_commission)},
        )

        # --- Email HTML au client ---
        try:
            client_context = {
                'first_name': user.first_name or user.username,
                'nom_boutique': boutique.nom,
                'taux_commission': boutique.taux_commission,
            }
            html_body = render_to_string('emails/boutique_validee.html', client_context)
            from django.utils.html import strip_tags
            text_body = strip_tags(html_body)
            email_client = EmailMultiAlternatives(
                subject="Votre boutique est maintenant active ! 🛍️",
                body=text_body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@accessoire-exclusif.com'),
                to=[user.email],
            )
            email_client.attach_alternative(html_body, "text/html")
            email_client.send(fail_silently=True)
        except Exception:
            pass

        return Response({
            "detail": "Boutique validée et activée avec succès.",
            "boutique": BoutiqueSerializer(boutique, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_boutique_ventes(request):
    """
    GET: Liste des ventes des produits appartenant à la boutique de l'utilisateur connecté.
    """
    user = request.user
    if not hasattr(user, 'client') or not hasattr(user.client, 'boutique'):
        return Response({"detail": "Vous n'avez pas de boutique."}, status=status.HTTP_404_NOT_FOUND)

    boutique = user.client.boutique
    from orders.models import VenteBoutique
    ventes = VenteBoutique.objects.filter(boutique=boutique).select_related('commande')

    serializer = VenteBoutiqueSerializer(ventes, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_boutique_portefeuille(request):
    """
    GET: Synthèse du portefeuille et solde de la boutique de l'utilisateur connecté.
    """
    user = request.user
    if not hasattr(user, 'client') or not hasattr(user.client, 'boutique'):
        return Response({"detail": "Vous n'avez pas de boutique."}, status=status.HTTP_404_NOT_FOUND)

    boutique = user.client.boutique
    from orders.models import VenteBoutique, VersementBoutique
    from django.db.models import Sum

    total_brut = VenteBoutique.objects.filter(boutique=boutique, statut='valide').aggregate(s=Sum('montant_brut'))['s'] or Decimal('0.00')
    total_commission_admin = VenteBoutique.objects.filter(boutique=boutique, statut='valide').aggregate(s=Sum('montant_commission_admin'))['s'] or Decimal('0.00')
    total_net = VenteBoutique.objects.filter(boutique=boutique, statut='valide').aggregate(s=Sum('montant_net_boutique'))['s'] or Decimal('0.00')

    versements = VersementBoutique.objects.filter(boutique=boutique)
    versements_data = VersementBoutiqueSerializer(versements[:10], many=True).data

    return Response({
        "boutique_id": boutique.id,
        "nom_boutique": boutique.nom,
        "solde_disponible": str(boutique.solde_disponible),
        "solde_total_recu": str(boutique.solde_total_recu),
        "chiffre_affaires_brut": str(total_brut),
        "total_commissions_admin": str(total_commission_admin),
        "total_net_gagne": str(total_net),
        "telephone_paiement": boutique.telephone_paiement,
        "mode_paiement_prefere": boutique.mode_paiement_prefere,
        "versements_recents": versements_data
    })


@api_view(['GET'])
@permission_classes([IsSuperadmin])
def admin_boutiques_financier(request):
    """
    GET: Synthèse financière globale de toutes les boutiques partenaires pour l'Admin (Superadmin uniquement).
    """
    from orders.models import VenteBoutique, VersementBoutique
    from django.db.models import Sum

    boutiques = Boutique.objects.filter(statut='actif')
    res = []
    for b in boutiques:
        ca_brut = VenteBoutique.objects.filter(boutique=b, statut='valide').aggregate(s=Sum('montant_brut'))['s'] or Decimal('0.00')
        comm_admin = VenteBoutique.objects.filter(boutique=b, statut='valide').aggregate(s=Sum('montant_commission_admin'))['s'] or Decimal('0.00')
        net_b = VenteBoutique.objects.filter(boutique=b, statut='valide').aggregate(s=Sum('montant_net_boutique'))['s'] or Decimal('0.00')

        res.append({
            "id": b.id,
            "nom": b.nom,
            "proprietaire": b.proprietaire_nom,
            "taux_commission": str(b.taux_commission),
            "solde_disponible": str(b.solde_disponible),
            "solde_total_recu": str(b.solde_total_recu),
            "chiffre_affaires_brut": str(ca_brut),
            "commissions_admin_perdues": str(comm_admin),
            "net_boutique_cumule": str(net_b),
            "telephone_paiement": b.telephone_paiement,
            "mode_paiement_prefere": b.mode_paiement_prefere,
        })

    return Response(res)


@api_view(['POST'])
@permission_classes([IsSuperadmin])
def admin_boutique_effectuer_versement(request, pk):
    """
    POST: L'Admin enregistre un versement (Payout) à une boutique et déduit son solde_disponible.
    La clé d'idempotence ('idempotency_key', 'reference_transaction' ou header 'X-Idempotency-Key') est OBLIGATOIRE.
    """
    boutique = get_object_or_404(Boutique, pk=pk)
    montant = Decimal(str(request.data.get('montant', 0)))
    mode_paiement = request.data.get('mode_paiement', boutique.mode_paiement_prefere or 'OM')
    telephone = request.data.get('telephone_destination', boutique.telephone_paiement or boutique.telephone)
    note_admin = request.data.get('note_admin', '')

    idempotency_key = request.data.get('idempotency_key') or request.data.get('reference_transaction') or request.META.get('HTTP_X_IDEMPOTENCY_KEY')

    if not idempotency_key or not str(idempotency_key).strip():
        return Response({
            "detail": "La clé d'idempotence ('idempotency_key' ou 'reference_transaction') est obligatoire pour effectuer un versement."
        }, status=status.HTTP_400_BAD_REQUEST)

    idempotency_key = str(idempotency_key).strip()

    from orders.models import VersementBoutique
    existing_versement = VersementBoutique.objects.filter(reference_transaction=idempotency_key).first()
    if existing_versement:
        return Response({
            "detail": f"Ce versement a déjà été enregistré (Traitement idempotent).",
            "idempotent": True,
            "versement": VersementBoutiqueSerializer(existing_versement).data,
            "nouveau_solde_disponible": str(existing_versement.boutique.solde_disponible)
        }, status=status.HTTP_200_OK)

    if montant <= 0:
        return Response({"detail": "Le montant du versement doit être supérieur à 0."}, status=status.HTTP_400_BAD_REQUEST)

    # transaction.atomic() + select_for_update() pour éviter les race conditions sur le solde_disponible
    # (deux admins qui versent simultanément ne peuvent pas dépasser le solde réel)
    from django.db import transaction as db_transaction
    try:
        with db_transaction.atomic():
            boutique_locked = Boutique.objects.select_for_update().get(pk=pk)

            if montant > boutique_locked.solde_disponible:
                return Response({
                    "detail": f"Le montant ({montant} FCFA) dépasse le solde disponible de la boutique ({boutique_locked.solde_disponible} FCFA)."
                }, status=status.HTTP_400_BAD_REQUEST)

            ref = idempotency_key

            versement = VersementBoutique.objects.create(
                boutique=boutique_locked,
                montant=montant,
                reference_transaction=ref,
                mode_paiement=mode_paiement,
                telephone_destination=telephone,
                note_admin=note_admin,
                effectue_par=request.user
            )

            boutique_locked.solde_disponible -= montant
            boutique_locked.solde_total_recu += montant
            boutique_locked.save(update_fields=['solde_disponible', 'solde_total_recu'])

    except Boutique.DoesNotExist:
        return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)

    Notification.objects.create(
        recipient=boutique_locked.user,
        type='versement_boutique',
        title="Versement reçu !",
        message=f"Un versement de {montant} FCFA a été effectué sur votre compte ({ref}).",
        url="/me/boutique/portefeuille/",
        metadata={'versement_id': versement.id, 'montant': str(montant), 'reference': ref}
    )

    return Response({
        "detail": f"Versement de {montant} FCFA enregistré avec succès pour {boutique_locked.nom}.",
        "versement": VersementBoutiqueSerializer(versement).data,
        "nouveau_solde_disponible": str(boutique_locked.solde_disponible)
    }, status=status.HTTP_201_CREATED)



@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def list_prestataire_requests(request):
    """
    Liste toutes les demandes en attente (Réservé à l'Admin).
    """
    requests = Prestataire.objects.filter(statut='en_attente')
    serializer = PrestataireSerializer(requests, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def detail_prestataire_request(request, pk):
    """Récupère les informations détaillées d'une demande prestataire."""
    prestataire = get_object_or_404(Prestataire, pk=pk)
    serializer = PrestataireSerializer(prestataire)
    return Response(serializer.data)

@api_view(['GET', 'POST', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_notifications(request):
    """
    GET : Liste des notifications destinées à l'utilisateur connecté (et globales pour admin/serveuse).
    POST / PATCH : Marque toutes les notifications personnelles de l'utilisateur connecté comme lues.
    DELETE : Supprime une, plusieurs ou toutes les notifications de l'utilisateur connecté de la base de données.
    """
    user = request.user
    from utilisateur.permissions import is_active_serveuse
    
    if request.method == 'GET':
        # Si l'utilisateur est admin ou serveuse, il voit aussi les notifications globales
        if user.is_superuser or is_active_serveuse(user) or user.is_staff:
            notifications = Notification.objects.filter(
                Q(recipient=user) | Q(is_global_admin=True)
            ).order_by('-created_at')
        else:
            notifications = Notification.objects.filter(recipient=user).order_by('-created_at')
            
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)
        
    elif request.method in ['POST', 'PATCH']:
        # On marque comme lues les notifications accessibles à l'utilisateur
        if user.is_superuser or is_active_serveuse(user) or user.is_staff:
            updated = Notification.objects.filter((Q(recipient=user) | Q(is_global_admin=True)), is_read=False).update(is_read=True)
        else:
            updated = Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
        return Response({
            "detail": "Toutes vos notifications ont été marquées comme lues.",
            "updated": updated
        }, status=status.HTTP_200_OK)

    elif request.method == 'DELETE':
        data = request.data if hasattr(request, 'data') and isinstance(request.data, dict) else {}
        query = request.query_params

        notif_id = (
            query.get('id') or query.get('notification_id') or query.get('notif_id') or
            data.get('id') or data.get('notification_id') or data.get('notif_id')
        )

        notif_ids = data.get('notification_ids') or data.get('ids') or data.get('notif_ids') or query.get('ids')
        if isinstance(notif_ids, str):
            notif_ids = [i.strip() for i in notif_ids.split(',') if i.strip().isdigit()]

        if user.is_superuser or is_active_serveuse(user) or user.is_staff:
            scope_qs = Notification.objects.filter(Q(recipient=user) | Q(is_global_admin=True))
        else:
            scope_qs = Notification.objects.filter(recipient=user)

        if notif_id:
            deleted_count, _ = scope_qs.filter(pk=notif_id).delete()
            if deleted_count > 0:
                return Response({
                    "detail": f"Notification #{notif_id} supprimée de la base de données.",
                    "deleted": deleted_count
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "detail": f"Notification #{notif_id} introuvable.",
                    "deleted": 0
                }, status=status.HTTP_404_NOT_FOUND)

        elif notif_ids and isinstance(notif_ids, list):
            deleted_count, _ = scope_qs.filter(pk__in=notif_ids).delete()
            return Response({
                "detail": f"{deleted_count} notification(s) supprimée(s) de la base de données.",
                "deleted": deleted_count
            }, status=status.HTTP_200_OK)

        else:
            deleted_count, _ = scope_qs.delete()
            if deleted_count > 0:
                return Response({
                    "detail": "Toutes vos notifications ont été supprimées de la base de données.",
                    "deleted": deleted_count
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "detail": "Aucune notification à supprimer.",
                    "deleted": 0
                }, status=status.HTTP_200_OK)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_notification_detail(request, pk):
    """
    GET : Détail d'une notification.
    PATCH : Marque la notification comme lue.
    DELETE : Supprime définitivement la notification de la base de données.
    """
    user = request.user
    from utilisateur.permissions import is_active_serveuse

    if user.is_superuser or is_active_serveuse(user) or user.is_staff:
        notif = get_object_or_404(Notification, Q(pk=pk) & (Q(recipient=user) | Q(is_global_admin=True)))
    else:
        notif = get_object_or_404(Notification, pk=pk, recipient=user)

    if request.method == 'GET':
        serializer = NotificationSerializer(notif)
        return Response(serializer.data)

    elif request.method == 'PATCH':
        notif.is_read = True
        notif.save()
        return Response(NotificationSerializer(notif).data)

    elif request.method == 'DELETE':
        notif.delete()
        return Response({
            "detail": f"Notification #{pk} supprimée avec succès de la base de données."
        }, status=status.HTTP_200_OK)

from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

@api_view(['PATCH'])
@permission_classes([IsSuperadmin])
def validate_prestataire(request, pk):
    """
    Endpoint pour valider un prestataire (Réservé à l'Admin).
    L'admin doit fournir le taux_commission.
    """
    prestataire = get_object_or_404(Prestataire, pk=pk)
    
    if prestataire.statut != 'en_attente':
        return Response({"detail": "Ce prestataire a déjà été traité."}, status=status.HTTP_400_BAD_REQUEST)
        
    serializer = PrestataireValidationSerializer(prestataire, data=request.data)
    if serializer.is_valid():
        # Génération du code promo et activation
        promo_code = generate_promo_code()
        prestataire = serializer.save(statut='actif', code_promo=promo_code)
        
        # EMAIL HTML : Félicitations et envoi des conditions
        user = prestataire.client.user
        subject = "Bienvenue parmi nos partenaires exclusifs !"
        from_email = settings.DEFAULT_FROM_EMAIL
        to = [user.email]
        
        context = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'taux_commission': prestataire.taux_commission,
            'reduction_client_pourcentage': prestataire.reduction_client_pourcentage,
            'code_promo': promo_code
        }
        
        html_content = render_to_string('emails/prestataire_valide.html', context)
        text_content = strip_tags(html_content) # Version texte de secours
        
        msg = EmailMultiAlternatives(subject, text_content, from_email, to)
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=True)
        
        return Response({
            "detail": "Prestataire validé avec succès.",
            "code_promo": promo_code,
            "taux_commission": prestataire.taux_commission,
            "reduction_client_pourcentage": prestataire.reduction_client_pourcentage
        }, status=status.HTTP_200_OK)
        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from rest_framework.exceptions import ValidationError, PermissionDenied
from .serializers import (
    UserSerializer, PrestataireSerializer, PrestataireApplicationSerializer, 
    PrestataireValidationSerializer, PrestataireDashboardSerializer,
    CommissionLogSerializer
)

def get_prestataire_for_request(request):
    """
    Helper pour récupérer le prestataire ciblé par la requête.
    - Si l'utilisateur est admin, il peut passer 'prestataire_id' dans les paramètres de requête.
    - Sinon, on récupère le profil prestataire de l'utilisateur connecté s'il est actif.
    """
    user = request.user
    if user.is_superuser:
        prestataire_id = request.query_params.get('prestataire_id')
        if not prestataire_id:
            # Fallback si l'admin a son propre profil prestataire
            try:
                return user.client.prestataire
            except (AttributeError, Prestataire.DoesNotExist):
                raise ValidationError("Le paramètre 'prestataire_id' est requis pour les administrateurs.")
        return get_object_or_404(Prestataire, pk=prestataire_id)
    
    try:
        prestataire = user.client.prestataire
    except (AttributeError, Prestataire.DoesNotExist):
        raise PermissionDenied("Accès réservé aux prestataires.")
        
    if prestataire.statut != 'actif':
        raise PermissionDenied("Votre compte prestataire n'est pas encore actif.")
        
    return prestataire


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def prestataire_dashboard(request):
    """
    Dashboard pour le prestataire connecté (ou pour l'admin via ?prestataire_id=ID).
    Si l'admin fait la requête sans prestataire_id, il accède aux infos de tous les prestataires confondus.
    Affiche le solde, le code promo, les stats et l'historique récent.
    """
    user = request.user
    if user.is_superuser and not request.query_params.get('prestataire_id'):
        from decimal import Decimal
        from django.db.models import Sum
        
        solde_commission = Prestataire.objects.aggregate(Sum('solde_commission'))['solde_commission__sum'] or Decimal('0.00')
        total_gains = CommissionLog.objects.filter(montant__gt=0).aggregate(Sum('montant'))['montant__sum'] or Decimal('0.00')
        total_retraits = CommissionLog.objects.filter(montant__lt=0).aggregate(Sum('montant'))['montant__sum'] or Decimal('0.00')
        solde_bloque = PayoutTransaction.objects.filter(statut='en_cours').aggregate(Sum('montant'))['montant__sum'] or Decimal('0.00')
        
        payouts_recents_qs = PayoutTransaction.objects.all()[:5]
        payouts_recents = PayoutTransactionSerializer(payouts_recents_qs, many=True).data
        
        historique_recent_qs = CommissionLog.objects.all()[:10]
        historique_recent = CommissionLogSerializer(historique_recent_qs, many=True).data
        
        data = {
            'id': None,
            'solde_commission': f"{solde_commission:.2f}",
            'taux_commission': None,
            'reduction_client_pourcentage': None,
            'code_promo': None,
            'statut': 'actif',
            'total_gains': f"{total_gains:.2f}",
            'total_retraits': f"{abs(total_retraits):.2f}",
            'solde_bloque': f"{solde_bloque:.2f}",
            'payouts_recents': payouts_recents,
            'historique_recent': historique_recent
        }
        return Response(data)

    prestataire = get_prestataire_for_request(request)
    serializer = PrestataireDashboardSerializer(prestataire)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def prestataire_finance_history(request):
    """
    Historique financier complet (crédits/débits) pour le prestataire connecté
    (ou pour l'admin via ?prestataire_id=ID).
    Si l'admin fait la requête sans prestataire_id, il accède à l'historique de tous les prestataires.
    Supporte la pagination et le filtrage par type_operation.
    """
    user = request.user
    if user.is_superuser and not request.query_params.get('prestataire_id'):
        logs = CommissionLog.objects.all().order_by('-date_operation')
    else:
        prestataire = get_prestataire_for_request(request)
        logs = CommissionLog.objects.filter(prestataire=prestataire).order_by('-date_operation')
    
    # Filtrage par type
    type_op = request.query_params.get('type_operation')
    if type_op:
        logs = logs.filter(type_operation=type_op)
        
    paginator = PrestatairePagination()
    page = paginator.paginate_queryset(logs, request)
    if page is not None:
        serializer = CommissionLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = CommissionLogSerializer(logs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def prestataire_payouts_list(request):
    """
    Liste de toutes les demandes de virement initiées pour le prestataire connecté
    (ou pour l'admin via ?prestataire_id=ID).
    Si l'admin fait la requête sans prestataire_id, il accède aux virements de tous les prestataires.
    Supporte la pagination.
    """
    user = request.user
    if user.is_superuser and not request.query_params.get('prestataire_id'):
        payouts = PayoutTransaction.objects.all().order_by('-date_creation')
    else:
        prestataire = get_prestataire_for_request(request)
        payouts = PayoutTransaction.objects.filter(prestataire=prestataire).order_by('-date_creation')
    
    statut = request.query_params.get('statut')
    if statut:
        payouts = payouts.filter(statut=statut)
        
    paginator = PrestatairePagination()
    page = paginator.paginate_queryset(payouts, request)
    if page is not None:
        serializer = PayoutTransactionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = PayoutTransactionSerializer(payouts, many=True)
    return Response(serializer.data)


from .serializers import AdminUserSerializer, AdminPrestataireUpdateSerializer, User, CommissionLog

# ============================================================
# ADMINISTRATION (GESTION GLOBALE)
# ============================================================

@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def admin_users_list(request):
    """Liste paginée et recherchable de tous les utilisateurs"""
    search_query = request.query_params.get('search', '')
    users = User.objects.all().order_by('-date_joined')
    
    if search_query:
        users = users.filter(
            Q(email__icontains=search_query) | 
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query) |
            Q(telephone__icontains=search_query)
        )
    
    paginator = AdminPagination()
    page = paginator.paginate_queryset(users, request)
    serializer = AdminUserSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)

@api_view(['PATCH'])
@permission_classes([IsSuperadmin])
def admin_user_toggle_status(request, pk):
    """Bloquer ou débloquer un utilisateur (is_active)"""
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser:
        return Response({"detail": "Impossible de modifier un super-administrateur."}, status=status.HTTP_400_BAD_REQUEST)
    
    user.is_active = not user.is_active
    user.save()
    status_str = "activé" if user.is_active else "bloqué"
    return Response({"detail": f"Utilisateur {status_str} avec succès.", "is_active": user.is_active})

@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def admin_prestataires_list(request):
    """Liste de tous les prestataires avec filtrage par statut"""
    statut = request.query_params.get('statut')
    prestataires = Prestataire.objects.all().order_by('-date_creation')
    
    if statut:
        prestataires = prestataires.filter(statut=statut)
    
    serializer = PrestataireSerializer(prestataires, many=True)
    return Response(serializer.data)

@api_view(['PATCH'])
@permission_classes([IsSuperadmin])
def admin_prestataire_update(request, pk):
    """Modifier le taux de commission ou le statut d'un prestataire actif"""
    prestataire = get_object_or_404(Prestataire, pk=pk)
    serializer = AdminPrestataireUpdateSerializer(prestataire, data=request.data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsSuperadmin])
def admin_delete_prestataire(request, pk):
    """
    Supprime un profil ou une demande de prestataire (admin only).
    """
    prestataire = get_object_or_404(Prestataire, pk=pk)
    prestataire.delete()
    return Response({"detail": "Prestataire supprimé avec succès."}, status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@permission_classes([IsSuperadmin])
def admin_global_stats(request):
    """Statistiques financières pour le dashboard admin"""
    from django.db.models import Sum
    total_users = User.objects.count()
    total_prestataires = Prestataire.objects.filter(statut='actif').count()
    solde_total_dus = Prestataire.objects.aggregate(Sum('solde_commission'))['solde_commission__sum'] or 0
    
    return Response({
        "total_users": total_users,
        "total_prestataires_actifs": total_prestataires,
        "solde_total_commission_dus": solde_total_dus
    })


#==============================Campay Payouts=====================
import re
from . import campay as campay_adapter
import hmac
import hashlib


def _is_valid_campay_webhook_signature(request):
    """
    Vérifie la signature HMAC-SHA256 du webhook Campay.
    FAIL-CLOSED : si le secret n'est pas configuré, toutes les requêtes sont rejetées
    (sauf en mode DEBUG où l'absence de secret autorise les requêtes — usage dev uniquement).
    """
    secret = getattr(settings, 'CAMPAY_WEBHOOK_SECRET', '')
    if not secret:
        # En production, sans secret, on rejette systématiquement (fail-closed)
        if not getattr(settings, 'DEBUG', False):
            return False
        # En dev uniquement, on laisse passer pour faciliter les tests locaux
        return True

    if request.method != 'POST':
        return False

    header_name = getattr(settings, 'CAMPAY_WEBHOOK_SIGNATURE_HEADER', 'X-Campay-Signature')
    signature = request.headers.get(header_name) or request.META.get(f'HTTP_{header_name.upper().replace("-", "_")}')
    if not signature:
        return False

    if signature.startswith('sha256='):
        signature = signature.split('=', 1)[1]

    expected = hmac.new(secret.encode('utf-8'), request.body or b'', hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def clean_cameroon_phone(phone):
    """
    Nettoie et valide un numéro de téléphone pour Campay (Cameroun).
    Retourne le format international sans '+', ex: '2376XXXXXXXX'.
    """
    if not phone:
        return None
    cleaned = re.sub(r'\D', '', str(phone))
    if cleaned.startswith('237'):
        return cleaned if len(cleaned) >= 11 else None
    if len(cleaned) == 9:
        return f"237{cleaned}"
    return None


@api_view(['POST'])
@permission_classes([IsSuperadminOrActiveServeuse])
def admin_prestataire_payout(request, pk):
    """
    Initiation d'un virement mobile money vers un prestataire via Campay.
    Utilise le numéro fourni dans le body (`telephone`) si présent, sinon le numéro du profil prestataire.
    """
    prestataire = get_object_or_404(Prestataire, pk=pk)

    # 1. Validation du montant (et téléphone optionnel)
    serializer = PayoutRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    montant = serializer.validated_data['montant']
    override_phone = serializer.validated_data.get('telephone')
    external_reference = serializer.validated_data.get('external_reference')
    if external_reference:
        external_reference = str(external_reference).strip() or None

    if external_reference:
        existing_tx = PayoutTransaction.objects.filter(reference_unique=external_reference).first()
        if existing_tx:
            return Response(PayoutTransactionSerializer(existing_tx).data, status=status.HTTP_200_OK)

    # 2. Récupérer et nettoyer le numéro
    raw_phone = override_phone or (prestataire.client.user.telephone if prestataire.client and prestataire.client.user else None)
    cleaned_phone = clean_cameroon_phone(raw_phone)
    if not cleaned_phone:
        return Response(
            {"detail": f"Le numéro de téléphone du prestataire ({raw_phone}) n'est pas valide pour un virement Campay (Cameroun)."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 3. Opération atomique pour vérifier le solde et débiter
    try:
        with transaction.atomic():
            prestataire = Prestataire.objects.select_for_update().get(pk=prestataire.pk)
            if prestataire.solde_commission < montant:
                return Response(
                    {"detail": f"Solde insuffisant. Solde disponible : {prestataire.solde_commission}€, demandé : {montant}€."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            prestataire.solde_commission -= montant
            prestataire.save()

            ref_unique = external_reference or str(uuid.uuid4())
            payout_tx = PayoutTransaction.objects.create(
                prestataire=prestataire,
                montant=montant,
                telephone_destination=cleaned_phone,
                reference_unique=ref_unique,
                statut='en_cours'
            )
    except Exception as e:
        return Response({"detail": f"Erreur lors de l'initiation en base de données : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 4. Appel à Campay
    amount_xaf = int(montant)
    success, campay_data, error = campay_adapter.payout_to_phone(
        cleaned_phone, amount_xaf,
        description=f"Payout prestataire {prestataire.pk}",
        external_reference=ref_unique
    )

    if success:
        # Stocker le processing_number de Campay pour retrouver la transaction dans le webhook
        campay_pn = (campay_data or {}).get('processing_number') or (campay_data or {}).get('reference')
        if campay_pn:
            payout_tx.campay_processing_number = campay_pn

        # Vérifier si Campay a déjà donné un statut final dans la réponse initiale
        # (cas fréquent avec les numéros de test)
        campay_status = (campay_data or {}).get('status', '').upper()
        if campay_status == 'SUCCESSFUL':
            payout_tx.statut = 'succes'
            payout_tx.date_finalisation = timezone.now()
            payout_tx.save()
            CommissionLog.objects.create(
                prestataire=payout_tx.prestataire,
                type_operation='retrait',
                montant=-payout_tx.montant,
                description=f"Retrait réussi vers {payout_tx.telephone_destination} (Ref: {ref_unique})."
            )
        elif campay_status in ('FAILED', 'CANCELLED'):
            payout_tx.statut = 'echec'
            payout_tx.motif_echec = (campay_data or {}).get('message') or 'Rejeté par Campay'
            payout_tx.date_finalisation = timezone.now()
            payout_tx.save()
            # Restituer le solde
            with transaction.atomic():
                prest = Prestataire.objects.select_for_update().get(pk=prestataire.pk)
                prest.solde_commission += montant
                prest.save()
        else:
            # Statut PENDING ou inconnu : en attente du webhook
            payout_tx.save()

        return Response(PayoutTransactionSerializer(payout_tx).data, status=status.HTTP_201_CREATED)
    else:
        # Échec : restituer le solde et marquer en échec
        with transaction.atomic():
            prest = Prestataire.objects.select_for_update().get(pk=prestataire.pk)
            prest.solde_commission += montant
            prest.save()

            payout_tx.statut = 'echec'
            payout_tx.motif_echec = error or 'Rejet par Campay'
            payout_tx.date_finalisation = timezone.now()
            payout_tx.save()

        return Response({"detail": f"Campay a rejeté l'opération : {error}. Le solde du prestataire a été restitué."}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
def campay_payout_webhook(request):
    """
    Webhook public appelé par Campay pour notifier du statut final d'un virement.
    Campay envoie : processing_number (son ID interne), external_reference (notre UUID), status.
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info("[Campay Webhook] Received webhook call. Method: %s. Headers: %s", request.method, dict(request.headers))

    if getattr(settings, 'CAMPAY_WEBHOOK_SECRET', ''):
        if request.method != 'POST':
            logger.warning("[Campay Webhook] Webhook secret configured, but request is not POST.")
            return Response({"detail": "Webhook Campay signé doit être envoyé en POST."}, status=status.HTTP_403_FORBIDDEN)
        if not _is_valid_campay_webhook_signature(request):
            logger.error("[Campay Webhook] Invalid signature verification. Expected HMAC matching signature header.")
            return Response({"detail": "Signature webhook invalide."}, status=status.HTTP_403_FORBIDDEN)

    data = request.data if request.method == 'POST' else request.query_params
    logger.info("[Campay Webhook] Payload data: %s", data)

    # Campay envoie : processing_number (ID Campay interne) + external_reference (notre UUID)
    campay_pn     = data.get('processing_number') or data.get('payment_ref')
    external_ref  = data.get('external_reference') or data.get('reference')
    status_val    = (data.get('status') or '').upper()   # SUCCESSFUL / FAILED / PENDING
    message       = data.get('message') or data.get('reason') or data.get('detail')

    logger.info("[Campay Webhook] Parsed parameters: campay_pn=%s, external_ref=%s, status_val=%s, message=%s",
                campay_pn, external_ref, status_val, message)

    if not campay_pn and not external_ref:
        logger.warning("[Campay Webhook] Missing both processing_number and external_reference.")
        return Response({"detail": "processing_number ou external_reference manquant"}, status=status.HTTP_400_BAD_REQUEST)

    # Chercher la transaction :
    # 1) par campay_processing_number (le plus fiable)
    # 2) par notre UUID (external_reference / reference_unique)
    payout_tx = None
    if campay_pn:
        payout_tx = PayoutTransaction.objects.filter(campay_processing_number=campay_pn).first()
    if payout_tx is None and external_ref:
        payout_tx = PayoutTransaction.objects.filter(reference_unique=external_ref).first()
    if payout_tx is None and campay_pn:
        # Dernier recours : certaines intégrations stockent le PN comme reference_unique
        payout_tx = PayoutTransaction.objects.filter(reference_unique=campay_pn).first()
    if payout_tx is None:
        logger.warning("[Campay Webhook] Transaction not found for campay_pn=%s or external_ref=%s", campay_pn, external_ref)
        return Response({"detail": "Transaction non trouvée"}, status=status.HTTP_404_NOT_FOUND)

    if payout_tx.statut != 'en_cours':
        logger.info("[Campay Webhook] Transaction already finalized: ID=%s, status=%s", payout_tx.id, payout_tx.statut)
        return Response({"detail": f"Transaction déjà finalisée : {payout_tx.statut}"}, status=status.HTTP_200_OK)

    try:
        with transaction.atomic():
            payout_tx = PayoutTransaction.objects.select_for_update().get(pk=payout_tx.pk)

            if payout_tx.statut != 'en_cours':
                logger.info("[Campay Webhook] Transaction already processed inside lock: ID=%s", payout_tx.id)
                return Response({"detail": "Transaction déjà traitée"}, status=status.HTTP_200_OK)

            # Mettre à jour le processing_number si on ne l'avait pas encore
            if campay_pn and not payout_tx.campay_processing_number:
                payout_tx.campay_processing_number = campay_pn

            if status_val in ('SUCCESSFUL', 'SUCCESS'):
                payout_tx.statut = 'succes'
                payout_tx.date_finalisation = timezone.now()
                payout_tx.save()
                CommissionLog.objects.create(
                    prestataire=payout_tx.prestataire,
                    type_operation='retrait',
                    montant=-payout_tx.montant,
                    description=f"Retrait réussi vers {payout_tx.telephone_destination} (Ref: {payout_tx.reference_unique})."
                )
                logger.info("[Campay Webhook] Transaction updated to SUCCESS. ID=%s, Amount=%s", payout_tx.id, payout_tx.montant)
            elif status_val in ('FAILED', 'CANCELLED', 'REJECTED'):
                payout_tx.statut = 'echec'
                payout_tx.motif_echec = message or f"Échec notifié par Campay (status={status_val})"
                payout_tx.date_finalisation = timezone.now()
                payout_tx.save()
                prestataire = Prestataire.objects.select_for_update().get(pk=payout_tx.prestataire.pk)
                prestataire.solde_commission += payout_tx.montant
                prestataire.save()
                logger.info("[Campay Webhook] Transaction updated to FAILED. ID=%s, Balance refunded.", payout_tx.id)
            else:
                # PENDING ou autre statut intermédiaire : ne rien faire
                if campay_pn and not payout_tx.campay_processing_number:
                    payout_tx.save()  # Juste sauvegarder le processing_number
                logger.info("[Campay Webhook] Transaction received intermediate status: %s. No change.", status_val)
                return Response({"detail": f"Statut intermédiaire ignoré : {status_val}"}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("[Campay Webhook] Exception occurred while processing webhook transaction update.")
        return Response({"detail": f"Erreur interne : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"detail": "Webhook traité avec succès"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsSuperadmin])
def admin_poll_campay_payout(request, pk):
    """
    Endpoint pour interroger manuellement Campay sur une transaction spécifique.
    """
    payout_tx = get_object_or_404(PayoutTransaction, pk=pk)
    if not payout_tx.campay_processing_number:
        return Response({"detail": "Aucun processing_number Campay associé."}, status=status.HTTP_400_BAD_REQUEST)
        
    success, campay_data, error = campay_adapter.get_transaction_status(payout_tx.campay_processing_number)
    
    if not success:
        return Response({"detail": f"Erreur lors de l'interrogation : {error}"}, status=status.HTTP_400_BAD_REQUEST)
        
    # Appeler la logique de traitement en interne (via le même flow que le webhook)
    # Pour simplifier, on peut réutiliser une fonction partagée ou dupliquer un peu la logique
    # Ici, nous mettons simplement à jour le statut en fonction du résultat
    status_val = (campay_data or {}).get('status', '').upper()
    message = (campay_data or {}).get('message') or (campay_data or {}).get('reason')
    
    if status_val in ('SUCCESSFUL', 'SUCCESS') and payout_tx.statut == 'en_cours':
        with transaction.atomic():
            payout_tx.statut = 'succes'
            payout_tx.date_finalisation = timezone.now()
            payout_tx.save()
            CommissionLog.objects.create(
                prestataire=payout_tx.prestataire,
                type_operation='retrait',
                montant=-payout_tx.montant,
                description=f"Retrait via polling réussi vers {payout_tx.telephone_destination}."
            )
            
    elif status_val in ('FAILED', 'CANCELLED', 'REJECTED') and payout_tx.statut == 'en_cours':
        with transaction.atomic():
            payout_tx.statut = 'echec'
            payout_tx.motif_echec = message or "Échec notifié par Campay"
            payout_tx.date_finalisation = timezone.now()
            payout_tx.save()
            prest = Prestataire.objects.select_for_update().get(pk=payout_tx.prestataire.pk)
            prest.solde_commission += payout_tx.montant
            prest.save()
            
    return Response({"status": payout_tx.statut, "campay_status": status_val, "detail": message})


@api_view(['GET'])
@permission_classes([IsSuperadminOrActiveServeuse])
def admin_payouts_list(request):
    """
    Liste de tous les virements (payouts) initiés par l'admin avec pagination
    """
    payouts = PayoutTransaction.objects.all().order_by('-date_creation')
    
    statut = request.query_params.get('statut')
    if statut:
        payouts = payouts.filter(statut=statut)
        
    prestataire_id = request.query_params.get('prestataire')
    if prestataire_id:
        payouts = payouts.filter(prestataire_id=prestataire_id)
        
    paginator = AdminPagination()
    page = paginator.paginate_queryset(payouts, request)
    if page is not None:
        serializer = PayoutTransactionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = PayoutTransactionSerializer(payouts, many=True)
    return Response(serializer.data)


#==============================social===============================

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import RegisterView, ResendEmailVerificationView, SocialLoginView, VerifyEmailView


class ThrottledRegisterView(RegisterView):
    throttle_classes = [RegisterIPThrottle, RegisterEmailThrottle]


class ThrottledVerifyEmailView(VerifyEmailView):
    throttle_classes = [ResendEmailShortThrottle]


class ThrottledResendEmailVerificationView(ResendEmailVerificationView):
    throttle_classes = [ResendEmailShortThrottle, ResendEmailDailyThrottle]


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.FRONTEND_URL # Doit correspondre EXACTEMENT à l'URI de redirection configurée chez Google
    throttle_classes = [LoginIPThrottle]

    def post(self, request, *args, **kwargs):
        # Support Google One Tap (id_token / credential / token)
        id_token_input = (
            request.data.get('id_token') or 
            request.data.get('credential') or 
            request.data.get('token')
        ) if isinstance(request.data, dict) else None

        has_oauth_code = bool(
            isinstance(request.data, dict) and 
            (request.data.get('code') or request.data.get('access_token'))
        )

        if id_token_input and not has_oauth_code:
            return self._handle_one_tap(request, id_token_input)

        return super().post(request, *args, **kwargs)

    def _handle_one_tap(self, request, token_str):
        import requests as http_requests
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        from rest_framework_simplejwt.tokens import RefreshToken
        from dj_rest_auth.jwt_auth import set_jwt_cookies
        from allauth.socialaccount.models import SocialAccount
        from utilisateur.models import User
        from utilisateur.serializers import UserSerializer

        # Client ID Google : obligatoire pour valider que le token est bien destiné à notre app
        google_client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
        if not google_client_id and not getattr(settings, 'DEBUG', False):
            return Response(
                {"detail": "Authentification Google One Tap non configurée (GOOGLE_CLIENT_ID manquant)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        id_info = None
        # 1. Vérification via la bibliothèque google-auth avec validation de l'audience
        try:
            verify_kwargs = {
                'clock_skew_in_seconds': 10,
            }
            if google_client_id:
                id_info = google_id_token.verify_oauth2_token(
                    token_str,
                    google_requests.Request(),
                    audience=google_client_id,
                    **verify_kwargs
                )
            else:
                # Dev uniquement — sans audience, on accepte tout token Google valide
                id_info = google_id_token.verify_oauth2_token(
                    token_str,
                    google_requests.Request(),
                    **verify_kwargs
                )
        except Exception:
            # 2. Fallback via l'endpoint API google tokeninfo
            try:
                resp = http_requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token_str}", timeout=10)
                if resp.status_code == 200:
                    fallback_info = resp.json()
                    # Valider l'audience si on dispose du client_id
                    if google_client_id:
                        aud = fallback_info.get('aud', '')
                        azp = fallback_info.get('azp', '')
                        if aud != google_client_id and azp != google_client_id:
                            # Token valide mais émis pour une autre application
                            id_info = None
                        else:
                            id_info = fallback_info
                    else:
                        id_info = fallback_info
            except Exception:
                id_info = None

        if not id_info or not isinstance(id_info, dict) or not id_info.get('email'):
            return Response(
                {"detail": "Jeton Google One Tap (id_token) invalide ou expiré."},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = id_info.get('email').strip().lower()
        sub = id_info.get('sub') or id_info.get('user_id') or email
        first_name = id_info.get('given_name') or id_info.get('name', '').split(' ')[0]
        last_name = id_info.get('family_name') or ''

        # Récupération ou création du compte utilisateur
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            username = email.split('@')[0]
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1

            user = User.objects.create_user(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            user.set_unusable_password()
            user.save()
        else:
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])

        try:
            from allauth.account.models import EmailAddress
            EmailAddress.objects.get_or_create(
                user=user,
                email=user.email,
                defaults={'verified': True, 'primary': True}
            )
        except Exception:
            pass

        # Enregistrement de la fiche SocialAccount
        SocialAccount.objects.get_or_create(
            user=user,
            provider='google',
            defaults={
                'uid': str(sub),
                'extra_data': id_info
            }
        )

        # Génération des jetons JWT et cookies HttpOnly
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        serializer = UserSerializer(user, context={'request': request})
        data = {
            'access': access_token,
            'refresh': refresh_token,
            'user': serializer.data,
            'roles': serializer.data.get('roles', [])
        }

        response = Response(data, status=status.HTTP_200_OK)
        set_jwt_cookies(response, access_token, refresh_token)
        return response

    def get_response(self):
        response = super().get_response()
        if response.status_code == 200:
            # Positionnement strict des cookies JWT HttpOnly (access-token et refresh-token)
            from dj_rest_auth.jwt_auth import set_jwt_cookies
            if hasattr(self, 'access_token') and hasattr(self, 'refresh_token'):
                set_jwt_cookies(response, self.access_token, self.refresh_token)

            if dj_rest_auth_settings.USE_JWT and hasattr(self, 'refresh_token') and self.refresh_token:
                response.data['refresh'] = str(self.refresh_token)
            if hasattr(self, 'user') and self.user:
                from utilisateur.serializers import UserSerializer
                serializer = UserSerializer(self.user, context={'request': self.request})
                response.data['user'] = serializer.data
                response.data['roles'] = serializer.data.get('roles', [])
        return response

# ============================================================
# GESTION DES LIVREURS
# ============================================================

def get_livreur_for_request(request):
    """
    Helper pour récupérer le livreur connecté et vérifier s'il est actif.
    """
    user = request.user
    try:
        livreur = user.client.livreur
    except (AttributeError, Livreur.DoesNotExist):
        raise PermissionDenied("Accès réservé aux livreurs.")
        
    if livreur.statut in ['inactif', 'suspendu']:
        raise PermissionDenied("Votre compte livreur n'est pas actif.")
        
    return livreur


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def livreur_dashboard(request):
    """
    Dashboard pour le livreur connecté et actif.
    Affiche son statut, son nombre de livraisons et ses livraisons actives.
    """
    livreur = get_livreur_for_request(request)
    
    # Livraisons actives (statut_livraison est 'assignée')
    actives = Commande.objects.filter(livreur=livreur, statut_livraison='assignée').order_by('-date_creation')
    actives_data = LivreurCommandeSerializer(actives, many=True).data
    
    data = {
        "id": livreur.id,
        "statut": livreur.statut,
        "nombre_livraisons": livreur.nombre_livraisons,
        "livraisons_actives": actives_data
    }
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def livreur_commandes_list(request):
    """
    Liste paginée de toutes les livraisons assignées au livreur connecté.
    """
    livreur = get_livreur_for_request(request)
    commandes = Commande.objects.filter(livreur=livreur).order_by('-date_creation')
    
    statut = request.query_params.get('statut_livraison')
    if statut:
        commandes = commandes.filter(statut_livraison=statut)
        
    paginator = PrestatairePagination()
    page = paginator.paginate_queryset(commandes, request)
    if page is not None:
        serializer = LivreurCommandeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = LivreurCommandeSerializer(commandes, many=True)
    return Response(serializer.data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def livreur_update_delivery_status(request, pk):
    """
    Mise à jour du statut d'une livraison attribuée au livreur connecté.
    Actions autorisées : 'livrer', 'echouer'.
    """
    livreur = get_livreur_for_request(request)
    commande = get_object_or_404(Commande, pk=pk, livreur=livreur)
    
    if commande.statut_livraison not in ['assignée']:
        return Response({"detail": "Cette commande ne peut plus être modifiée."}, status=status.HTTP_400_BAD_REQUEST)
        
    action = request.data.get('action')
    if action == 'livrer':
        with transaction.atomic():
            commande.statut_livraison = 'livrée'
            commande.statut = 'livrée'
            commande.date_livraison_reelle = timezone.now()
            
            # Valider automatiquement le paiement si le livreur livre
            commande.statut_paiement = 'payé'
                
            commande.save()
            
            # Incrémenter le compteur du livreur
            livreur.nombre_livraisons += 1
            livreur.save()
            
        return Response({"detail": "Livraison validée avec succès.", "statut_livraison": commande.statut_livraison})
        
    elif action == 'echouer':
        motif = request.data.get('motif')
        if not motif:
            return Response({"detail": "Le motif d'échec est requis."}, status=status.HTTP_400_BAD_REQUEST)
            
        commande.statut_livraison = 'échouée'
        commande.motif_echec_livraison = motif
        commande.save()
        return Response({"detail": "Échec de livraison enregistré.", "statut_livraison": commande.statut_livraison})
        
    else:
        return Response({"detail": "Action invalide. Choix possibles : 'livrer', 'echouer'."}, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# ADMINISTRATION (GESTION DES LIVRAISONS & LIVREURS)
# ============================================================

@api_view(['GET'])
@permission_classes([IsSuperadminOrServeuseReadOnly])
def admin_livreurs_list(request):
    """
    Liste complète de tous les livreurs (pour affectation ou gestion admin).
    """
    livreurs = Livreur.objects.all().order_by('-date_creation')
    
    statut = request.query_params.get('statut')
    if statut:
        livreurs = livreurs.filter(statut=statut)
        
    paginator = AdminPagination()
    page = paginator.paginate_queryset(livreurs, request)
    if page is not None:
        serializer = LivreurSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = LivreurSerializer(livreurs, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsSuperadmin])
def admin_promote_to_livreur(request):
    """
    Crée un profil Livreur à partir d'un Client existant (via user_id) ou à partir de zéro.
    """
    user_id = request.data.get('user_id')
    photo = request.data.get('photo', '')
    date_embauche = request.data.get('date_embauche')
    
    if user_id:
        # Promotion d'un client existant
        user = get_object_or_404(User, pk=user_id)
        try:
            client = user.client
        except AttributeError:
            return Response({"detail": "Cet utilisateur n'a pas de profil Client associé."}, status=status.HTTP_400_BAD_REQUEST)
            
        if hasattr(client, 'livreur'):
            return Response({"detail": "Cet utilisateur est déjà enregistré comme livreur."}, status=status.HTTP_400_BAD_REQUEST)
            
        livreur = Livreur.objects.create(client=client, statut='disponible', photo=photo, date_embauche=date_embauche)
    else:
        # Création à partir de zéro
        email = request.data.get('email')
        telephone = request.data.get('telephone')
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        genre = request.data.get('genre', '')
        
        if not email or not telephone or not password:
            return Response(
                {"detail": "Veuillez fournir un user_id pour un client existant, ou l'email, le téléphone et le mot de passe pour le créer de zéro."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if User.objects.filter(email=email).exists():
            return Response({"detail": "Un utilisateur avec cet email existe déjà."}, status=status.HTTP_400_BAD_REQUEST)
            
        if User.objects.filter(telephone=telephone).exists():
            return Response({"detail": "Un utilisateur avec ce numéro de téléphone existe déjà."}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.create_user(
            email=email,
            username=email.split('@')[0],
            telephone=telephone,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        client = user.client
        if genre:
            client.genre = genre
            client.save()
            
        # On lie maintenant le livreur au client existant
        livreur = Livreur.objects.create(client=client, statut='disponible', photo=photo, date_embauche=date_embauche)        
    serializer = LivreurSerializer(livreur)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
@permission_classes([IsSuperadmin])
def admin_update_livreur(request, pk):
    """
    Modifie le profil ou le statut d'un livreur.
    """
    livreur = get_object_or_404(Livreur, pk=pk)
    serializer = LivreurUpdateSerializer(livreur, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsSuperadminOrActiveServeuse])
def admin_assign_delivery(request, pk):
    """
    Assigne une commande à un livreur actif.
    """
    commande = get_object_or_404(Commande, pk=pk)
    
    # Vérification que la commande est au statut validé
    if commande.statut == 'en_attente':
        return Response(
            {"detail": "Veuillez d'abord mettre la commande au statut 'validé' avant de pouvoir modifier son statut de livraison ou l'assigner à un livreur."},
            status=status.HTTP_400_BAD_REQUEST
        )
    elif commande.statut == 'annulée':
        return Response(
            {"detail": "Cette commande est annulée et ne peut plus être assignée à un livreur."},
            status=status.HTTP_400_BAD_REQUEST
        )

    livreur_id = request.data.get('livreur_id')
    if not livreur_id:
        return Response({"detail": "Le paramètre livreur_id est requis."}, status=status.HTTP_400_BAD_REQUEST)
        
    livreur = get_object_or_404(Livreur, pk=livreur_id)
    
    # Vérification si le livreur est actif
    if livreur.statut in ['inactif', 'suspendu']:
        return Response({"detail": "Impossible d'assigner une commande à un livreur inactif ou suspendu."}, status=status.HTTP_400_BAD_REQUEST)
        
    commande.livreur = livreur
    commande.statut_livraison = 'assignée'
    commande.save()
    
    return Response({
        "detail": f"Commande assignée avec succès au livreur {livreur.nom} {livreur.prenom}.",
        "statut_livraison": commande.statut_livraison
    })


@api_view(['GET'])
@permission_classes([IsSuperadminOrActiveServeuse])
def admin_deliveries_monitor(request):
    """
    Suivi global de toutes les livraisons pour l'administrateur.
    """
    commandes = Commande.objects.filter(statut_livraison__isnull=False).order_by('-date_creation')
    
    statut = request.query_params.get('statut_livraison')
    if statut:
        commandes = commandes.filter(statut_livraison=statut)
        
    livreur_id = request.query_params.get('livreur_id')
    if livreur_id:
        commandes = commandes.filter(livreur_id=livreur_id)
        
    paginator = AdminPagination()
    page = paginator.paginate_queryset(commandes, request)
    if page is not None:
        serializer = LivreurCommandeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = LivreurCommandeSerializer(commandes, many=True)
    return Response(serializer.data)


# ============================================================
# GESTION DES SERVEUSES (Admin Only)
# ============================================================

@api_view(['GET'])
@permission_classes([IsSuperadmin])
def admin_serveuses_list(request):
    """
    Liste complète de toutes les serveuses avec filtrage par statut (admin only).
    """
    serveuses = Serveuse.objects.all().order_by('-date_creation')
    
    statut = request.query_params.get('statut')
    if statut:
        serveuses = serveuses.filter(statut=statut)
        
    paginator = AdminPagination()
    page = paginator.paginate_queryset(serveuses, request)
    if page is not None:
        serializer = ServeusesSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
        
    serializer = ServeusesSerializer(serveuses, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsSuperadmin])
def admin_promote_to_serveuse(request):
    """
    Crée un profil Serveuse à partir d'un Client existant (via user_id) ou à partir de zéro.
    """
    user_id = request.data.get('user_id')
    date_embauche = request.data.get('date_embauche')
    
    if user_id:
        # Promotion d'un client existant
        user = get_object_or_404(User, pk=user_id)
        try:
            client = user.client
        except AttributeError:
            return Response({"detail": "Cet utilisateur n'a pas de profil Client associé."}, status=status.HTTP_400_BAD_REQUEST)
            
        if hasattr(client, 'serveuse'):
            return Response({"detail": "Cet utilisateur est déjà enregistré comme serveuse."}, status=status.HTTP_400_BAD_REQUEST)
            
        serveuse = Serveuse.objects.create(client=client, actif=True, date_embauche=date_embauche)
    else:
        # Création à partir de zéro
        email = request.data.get('email')
        telephone = request.data.get('telephone')
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        genre = request.data.get('genre', '')
        
        if not email or not telephone or not password:
            return Response(
                {"detail": "Veuillez fournir un user_id pour un client existant, ou l'email, le téléphone et le mot de passe pour le créer de zéro."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if User.objects.filter(email=email).exists():
            return Response({"detail": "Un utilisateur avec cet email existe déjà."}, status=status.HTTP_400_BAD_REQUEST)
            
        if User.objects.filter(telephone=telephone).exists():
            return Response({"detail": "Un utilisateur avec ce numéro de téléphone existe déjà."}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.create_user(
            email=email,
            username=email.split('@')[0],
            telephone=telephone,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        client = user.client
        if genre:
            client.genre = genre
            client.save()
        serveuse = Serveuse.objects.create(client=client, actif=True, date_embauche=date_embauche)
        
    serializer = ServeusesSerializer(serveuse)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
@permission_classes([IsSuperadmin])
def admin_update_serveuse(request, pk):
    """
    Modifie le profil ou le statut d'une serveuse (admin only).
    """
    serveuse = get_object_or_404(Serveuse, pk=pk)
    serializer = ServeusesUpdateSerializer(serveuse, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsSuperadmin])
def admin_delete_serveuse(request, pk):
    """
    Supprime une serveuse (admin only).
    """
    serveuse = get_object_or_404(Serveuse, pk=pk)
    serveuse_nom = f"{serveuse.nom} {serveuse.prenom}"
    serveuse.delete()
    return Response({"detail": f"Serveuse {serveuse_nom} supprimée avec succès."}, status=status.HTTP_204_NO_CONTENT)


# ============================================================
# GESTION DES LIVREURS - ENDPOINT DELETE
# ============================================================

@api_view(['DELETE'])
@permission_classes([IsSuperadmin])
def admin_delete_livreur(request, pk):
    """
    Supprime un livreur (admin only).
    """
    livreur = get_object_or_404(Livreur, pk=pk)
    livreur_nom = f"{livreur.nom} {livreur.prenom}"
    livreur.delete()
    return Response({"detail": f"Livreur {livreur_nom} supprimé avec succès."}, status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
#  Dépenses – CRUD admin & serveuse
# ---------------------------------------------------------------------------
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend


class DepenseViewSet(viewsets.ModelViewSet):
    """
    Dépenses boutique :
    - POST : serveuse active (cree_par auto).
    - GET : serveuse → ses dépenses ; superadmin → toutes.
    - PUT/PATCH : serveuse active, uniquement ses dépenses.
    - DELETE : superadmin uniquement.
    """
    serializer_class = DepenseSerializer
    permission_classes = [DepensePermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['date_depense']
    search_fields = ['titre', 'description']
    ordering_fields = ['date_depense', 'montant', 'date_creation']
    ordering = ['-date_depense']

    def get_queryset(self):
        qs = Depense.objects.select_related('cree_par').all()
        user = self.request.user
        if user.is_superuser:
            return qs
        if is_active_serveuse(user):
            return qs.filter(cree_par=user)
        return Depense.objects.none()

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

from django.db.models import Count, Sum, Q, Value, F
from django.db.models.functions import Coalesce

@api_view(['GET'])
@permission_classes([IsSuperadminOrActiveServeuse])
def admin_best_clients(request):
    """
    Retourne la liste des meilleurs clients, filtrés selon les critères de l'administrateur.
    Query params:
    - filter_by:
        'points'  : classement par points de fidélité décroissants (1 point / 25 000 FCFA).
        'spent'   : classement par montant total dépensé (payé) décroissant. (défaut)
        'orders'  : classement par nombre de commandes payées décroissant.
    - limit: Le nombre de clients à retourner. Si non précisé, retourne tout avec pagination de 100.
    """
    filter_by = request.GET.get('filter_by', 'spent')
    limit_param = request.GET.get('limit', None)

    clients = Client.objects.annotate(
        total_paid_orders=Coalesce(Count('commandes', filter=Q(commandes__statut_paiement='payé')), Value(0)),
        total_spent=Coalesce(Sum('commandes__total_ttc', filter=Q(commandes__statut_paiement='payé')), Value(Decimal('0')))
    )

    if filter_by == 'orders':
        clients = clients.order_by(F('total_paid_orders').desc(nulls_last=True), F('total_spent').desc(nulls_last=True), '-id')
    elif filter_by == 'points':
        clients = clients.order_by('-points_fidelite', F('total_spent').desc(nulls_last=True), '-id')
    else:
        # Défaut : classement par montant dépensé
        clients = clients.order_by(F('total_spent').desc(nulls_last=True), F('total_paid_orders').desc(nulls_last=True), '-id')

    if limit_param and limit_param.isdigit():
        clients = clients[:int(limit_param)]
        serializer = ClientSerializer(clients, many=True)
        return Response(serializer.data)

    # Pagination par défaut si pas de limit
    paginator = PageNumberPagination()
    paginator.page_size = 100
    paginated_clients = paginator.paginate_queryset(clients, request)
    serializer = ClientSerializer(paginated_clients, many=True)
    return paginator.get_paginated_response(serializer.data)

@api_view(['GET'])
@permission_classes([IsSuperadminOrActiveServeuse])
def admin_best_prestataires(request):
    """
    Retourne la liste des meilleurs prestataires, filtrés selon les critères de l'administrateur.
    Query params:
    - filter_by: 'orders' (le plus de commandes payées) ou 'gains' (plus grand montant de commission). Par défaut 'gains'.
    - limit: Le nombre de prestataires à retourner. Si non précisé, retourne tout avec pagination de 100.
    """
    filter_by = request.GET.get('filter_by', 'gains')
    limit_param = request.GET.get('limit', None)
    
    prestataires = Prestataire.objects.annotate(
        total_paid_orders=Coalesce(Count('commandes', filter=Q(commandes__statut_paiement='payé')), Value(0)),
        total_gains=Coalesce(Sum('commandes__commission_montant', filter=Q(commandes__statut_paiement='payé')), Value(Decimal('0')))
    )
    
    if filter_by == 'orders':
        prestataires = prestataires.order_by(F('total_paid_orders').desc(nulls_last=True), F('total_gains').desc(nulls_last=True), '-id')
    else:
        # Trier par gains (montant total des commissions)
        prestataires = prestataires.order_by(F('total_gains').desc(nulls_last=True), F('total_paid_orders').desc(nulls_last=True), '-id')
        
    if limit_param and limit_param.isdigit():
        prestataires = prestataires[:int(limit_param)]
        # Sérialisation directe sans pagination si limit est spécifié
        serializer = PrestataireSerializer(prestataires, many=True)
        return Response(serializer.data)
        
    # Pagination par défaut si pas de limit
    paginator = PageNumberPagination()
    paginator.page_size = 100
    paginated_prestataires = paginator.paginate_queryset(prestataires, request)
    serializer = PrestataireSerializer(paginated_prestataires, many=True)
    return paginator.get_paginated_response(serializer.data)



# ============================================================
# GESTION DES TOKENS FCM (Firebase Cloud Messaging)
# ============================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_fcm_device(request):
    """
    Enregistre ou met à jour le token FCM de l'appareil connecté.

    À appeler côté frontend après chaque connexion réussie, dès que
    Firebase SDK a fourni un token d'enregistrement.

    Body JSON attendu :
      {
        "registration_token": "<token FCM>",
        "platform": "web" | "android" | "ios"
      }
    """
    from utilisateur.serializers import FCMDeviceSerializer
    serializer = FCMDeviceSerializer(data=request.data)
    if serializer.is_valid():
        device = serializer.save(user=request.user)
        return Response(
            {
                "detail": "Token FCM enregistré avec succès.",
                "platform": device.platform,
                "active": device.active,
            },
            status=status.HTTP_200_OK,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unregister_fcm_device(request):
    """
    Désactive le token FCM de l'appareil lors de la déconnexion.

    Le token n'est pas supprimé mais marqué inactif, ce qui stoppe les pushs
    sans perdre l'historique. Il sera réactivé lors de la prochaine connexion.

    Body JSON attendu :
      {
        "registration_token": "<token FCM>"
      }
    """
    from utilisateur.models import FCMDevice
    token = request.data.get('registration_token')
    if not token:
        return Response(
            {"detail": "Le champ 'registration_token' est requis."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    updated = FCMDevice.objects.filter(
        registration_token=token,
        user=request.user,
    ).update(active=False)

    if updated:
        return Response({"detail": "Token FCM désactivé avec succès."}, status=status.HTTP_200_OK)
    return Response({"detail": "Token introuvable."}, status=status.HTTP_404_NOT_FOUND)
