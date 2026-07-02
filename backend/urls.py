from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.http import JsonResponse
from django.views.generic import RedirectView
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from utilisateur.views import confirm_email_direct, password_reset_confirm_page


def health_check(request):
    """Endpoint de santé pour Render — répond 200 OK en permanence."""
    return JsonResponse({"status": "ok", "service": "Accessoires Exclusifs API"})


urlpatterns = [
    # ------------------------------------------------------------------ #
    #  Santé & Accueil                                                     #
    # ------------------------------------------------------------------ #
    path('', RedirectView.as_view(url='/api/docs/', permanent=False)),  # / → Swagger
    path('health/', health_check, name='health-check'),                 # Render health check

    # ------------------------------------------------------------------ #
    #  Admin & API                                                         #
    # ------------------------------------------------------------------ #
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),

    # ------------------------------------------------------------------ #
    #  Authentification (allauth / email confirm / reset)                  #
    # ------------------------------------------------------------------ #
    path(
        'accounts/confirm-email/<str:key>/',
        confirm_email_direct,
        name='account_confirm_email'
    ),
    path(
        'accounts/password/reset/confirm/<str:uid>/<str:token>/',
        password_reset_confirm_page,
        name='password_reset_confirm'
    ),
    path('accounts/', include('allauth.urls')),

    # ------------------------------------------------------------------ #
    #  Documentation                                                       #
    # ------------------------------------------------------------------ #
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ------------------------------------------------------------------ #
    #  Fichiers MEDIA — servis par Django (dev & prod)                     #
    #  Utilise django.views.static.serve directement pour contourner la   #
    #  restriction DEBUG=True imposée par le helper static().              #
    #  NOTE : En production réelle (Cloudinary/S3), supprimer cette       #
    #  route : les fichiers seront hébergés sur un CDN externe.           #
    # ------------------------------------------------------------------ #
    re_path(
        r'^media/(?P<path>.*)$',
        serve,
        {'document_root': settings.MEDIA_ROOT, 'show_indexes': False},
    ),
]
