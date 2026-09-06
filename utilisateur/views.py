from decimal import Decimal
from allauth.account.forms import AddEmailForm
from allauth.account.forms import default_token_generator
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from allauth.account.utils import url_str_to_user_pk
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
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
    ServeusesSerializer, ServeusesUpdateSerializer, DepenseSerializer, ClientSerializer
)
from .models import Prestataire, User, Notification, PayoutTransaction, CommissionLog, Livreur, Serveuse, Client, Depense
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
    """
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

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')

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
                'client__parfums_personnalises__flacon',
                'client__parfums_personnalises__lignes__essence__essence',
                'client__parfums_personnalises__lignes__essence_personnalisee',
                'client__commandes__lignes_parfums__parfum',
                'client__commandes__lignes_parfums_perso__parfum_personnalise',
                'client__commandes__lignes_accessoires__accessoire',
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
def apply_prestataire(request):
    """
    Endpoint pour qu'un utilisateur postule en tant que prestataire.
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
        # On ne marque comme lu que les notifications de l'utilisateur connecté
        updated = Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
        return Response({
            "detail": "Toutes vos notifications ont été marquées comme lues.",
            "updated": updated
        }, status=status.HTTP_200_OK)

    elif request.method == 'DELETE':
        notif_id = request.query_params.get('id') or (request.data.get('notification_id') if hasattr(request, 'data') and isinstance(request.data, dict) else None)
        notif_ids = request.data.get('notification_ids') if hasattr(request, 'data') and isinstance(request.data, dict) else None

        if notif_id:
            deleted_count, _ = Notification.objects.filter(pk=notif_id, recipient=user).delete()
            if deleted_count == 0 and (user.is_superuser or user.is_staff):
                deleted_count, _ = Notification.objects.filter(pk=notif_id, is_global_admin=True).delete()
            return Response({
                "detail": f"Notification #{notif_id} supprimée de la base de données." if deleted_count > 0 else "Notification introuvable.",
                "deleted": deleted_count
            }, status=status.HTTP_200_OK if deleted_count > 0 else status.HTTP_404_NOT_FOUND)

        elif notif_ids and isinstance(notif_ids, list):
            deleted_count, _ = Notification.objects.filter(pk__in=notif_ids, recipient=user).delete()
            return Response({
                "detail": f"{deleted_count} notification(s) supprimée(s) de la base de données.",
                "deleted": deleted_count
            }, status=status.HTTP_200_OK)

        else:
            deleted_count, _ = Notification.objects.filter(recipient=user).delete()
            return Response({
                "detail": "Toutes vos notifications ont été supprimées de la base de données.",
                "deleted": deleted_count
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
    secret = getattr(settings, 'CAMPAY_WEBHOOK_SECRET', '')
    if not secret:
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
    elif commande.statut in ('annulée', 'remboursée'):
        return Response(
            {"detail": f"Cette commande est '{commande.statut}' et ne peut plus être assignée à un livreur."},
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
