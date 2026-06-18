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
        Intercepte l'envoi d'email pour garder le reset password cote backend
        tout en conservant FRONTEND_URL pour les liens generaux.
        """
        if 'password_reset_url' in context and 'uid' in context and 'token' in context:
            path = reverse("password_reset_confirm", args=[context['uid'], context['token']])
            site = Site.objects.get_current()
            context['password_reset_url'] = f"https://{site.domain}{path}"

        # Ajout de FRONTEND_URL à tous les contextes d'email pour le bouton général/footer
        context['frontend_url'] = settings.FRONTEND_URL

        super().send_mail(template_prefix, email, context)
