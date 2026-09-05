from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.urls import reverse
from django.contrib.sites.models import Site

class CustomAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        """
        Force l'utilisateur à être inactif (is_active=False) lors de son inscription,
        jusqu'à ce qu'il confirme son adresse email.
        """
        from django.conf import settings

        # On ne désactive le compte QUE pour les inscriptions classiques par email.
        # Pour Google (social), l'email est déjà considéré comme vérifié par le fournisseur.
        is_social = hasattr(request, 'sociallogin') or getattr(request, '_sociallogin_signup', False)
        if getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional') == 'mandatory' and not is_social:
            user.is_active = False
        return super().save_user(request, user, form, commit=commit)

    def pre_login(self, request, user, **kwargs):
        """
        Contourne la vérification de l'état inactif lors de l'inscription (signup=True)
        afin que l'étape EmailVerificationStage puisse s'exécuter et envoyer l'email de confirmation.
        """
        if kwargs.get('signup', False):
            return None
        return super().pre_login(request, user, **kwargs)

    def get_email_confirmation_url(self, request, emailconfirmation):
        """
        Génère l'URL de confirmation d'email qui sera envoyée à l'utilisateur.
        Détermine dynamiquement le protocole et le domaine à partir de la requête.
        Force HTTP pour les hôtes locaux (127.0.0.1 / localhost) pour éviter les erreurs SSL.
        """
        url = reverse("account_confirm_email", args=[emailconfirmation.key])
        if request:
            host = request.get_host()
            if any(local in host for local in ['127.0.0.1', 'localhost', '172.20.10.5']):
                scheme = 'http'
            else:
                scheme = 'https'
            return f"{scheme}://{host}{url}"
        else:
            site = Site.objects.get_current()
            domain = site.domain
            scheme = 'http' if any(local in domain for local in ['127.0.0.1', 'localhost', '172.20.10.5']) else 'https'
            return f"{scheme}://{domain}{url}"

    def send_mail(self, template_prefix, email, context):
        """
        Intercepte l'envoi d'email pour forcer le lien de reinitialisation
        de mot de passe vers la page HTML servie par le backend Django (100% backend).
        """
        import re

        # Cas 1 : uid et token sont dans le contexte (allauth standard)
        if 'password_reset_url' in context and context.get('uid') and context.get('token'):
            uid = context['uid']
            token = context['token']
            path = reverse("password_reset_confirm", args=[uid, token])
            scheme = 'http' if settings.DEBUG else 'https'
            host = settings.BACKEND_URL.rstrip('/')
            context['password_reset_url'] = f"{host}{path}"

        # Cas 2 : l'URL est déjà construite par dj_rest_auth mais pointe vers le frontend
        # → on extrait uid/token depuis l'URL et on reconstruit vers le backend
        elif 'password_reset_url' in context:
            url = context['password_reset_url']
            # Tente d'extraire uid et token depuis un pattern commun
            match = re.search(r'/([A-Za-z0-9\-_]+)/([A-Za-z0-9\-_]+)/?$', url)
            if match:
                uid = match.group(1)
                token = match.group(2)
                path = reverse("password_reset_confirm", args=[uid, token])
                host = settings.BACKEND_URL.rstrip('/')
                context['password_reset_url'] = f"{host}{path}"

        # Ajout de FRONTEND_URL à tous les contextes d'email pour le bouton général/footer
        context['frontend_url'] = settings.FRONTEND_URL

        super().send_mail(template_prefix, email, context)
