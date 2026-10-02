from django.urls import path, include
from utilisateur.views import (
    manage_me, change_email, upload_photo_profil, GoogleLogin, apply_prestataire, supprimer_compte, 
    cancel_prestataire_application, list_prestataire_requests, validate_prestataire,
    prestataire_dashboard, prestataire_finance_history, prestataire_payouts_list,
    apply_boutique, cancel_boutique_application, me_boutique, me_boutique_produits, admin_boutiques_list, admin_boutique_detail, admin_boutique_produits, validate_boutique,
    me_boutique_ventes, me_boutique_portefeuille, admin_boutiques_financier, admin_boutique_effectuer_versement,
    # Admin views
    admin_users_list, admin_user_toggle_status,
    admin_prestataires_list, admin_prestataire_update, admin_delete_prestataire,
    admin_global_stats,
    # Payouts
    admin_prestataire_payout, admin_payouts_list, campay_payout_webhook, admin_poll_campay_payout,
    # Livreur & Admin Delivery views
    livreur_dashboard, livreur_commandes_list, livreur_update_delivery_status,
    admin_livreurs_list, admin_promote_to_livreur, admin_update_livreur,
    admin_assign_delivery, admin_deliveries_monitor, admin_delete_livreur,
    # Serveuse & Admin Serveuse views
    admin_serveuses_list, admin_promote_to_serveuse, admin_update_serveuse, admin_delete_serveuse,
    # Connexion personnalisée
    WebLoginView, MobileLoginView, DeprecatedLoginView, HybridTokenRefreshView,
    ThrottledPasswordResetView, ThrottledRegisterView,
    ThrottledVerifyEmailView, ThrottledResendEmailVerificationView,
    CustomLogoutView,
    # Firebase Cloud Messaging (FCM)
    register_fcm_device, unregister_fcm_device
)

urlpatterns = [
    # Authentification classique séparée
    path('login/', DeprecatedLoginView.as_view(), name='rest_login'),
    path('web/login/', WebLoginView.as_view(), name='web_login'),
    path('mobile/login/', MobileLoginView.as_view(), name='mobile_login'),
    path('token/refresh/', HybridTokenRefreshView.as_view(), name='token_refresh'),
    path('password/reset/', ThrottledPasswordResetView.as_view(), name='rest_password_reset'),
    path('logout/', CustomLogoutView.as_view(), name='rest_logout'),
    path('', include('dj_rest_auth.urls')),

    # Firebase Cloud Messaging (Push Notifications)
    path('fcm/register/', register_fcm_device, name='fcm-register'),
    path('fcm/unregister/', unregister_fcm_device, name='fcm-unregister'),

    # Inscription avec limitation anti-abus, mêmes URLs que dj-rest-auth
    path('registration/', ThrottledRegisterView.as_view(), name='rest_register'),
    path('registration/verify-email/', ThrottledVerifyEmailView.as_view(), name='rest_verify_email'),
    path('registration/resend-email/', ThrottledResendEmailVerificationView.as_view(), name='rest_resend_email'),

    # Authentification Google
    path('google/', GoogleLogin.as_view(), name='google_login'),

    # Profil utilisateur personnalisé
    path('me/', manage_me, name='me'),
    path('me', manage_me),
    path('me/change-email/', change_email, name='me-change-email'),
    path('me/photo/', upload_photo_profil, name='me-upload-photo'),
    path('me/boutique/', me_boutique, name='me-boutique'),
    path('me/supprimer-compte/', supprimer_compte, name='me-supprimer-compte'),

    # Workflow Prestataire (Côté Client)
    path('prestataire/apply/', apply_prestataire, name='prestataire-apply'),
    path('prestataire/cancel/', cancel_prestataire_application, name='prestataire-cancel'),
    path('prestataire/dashboard/', prestataire_dashboard, name='prestataire-dashboard'),
    path('prestataire/historique/', prestataire_finance_history, name='prestataire-historique'),
    path('prestataire/payouts/', prestataire_payouts_list, name='prestataire-payouts'),

    # Workflow Boutique (Côté Client)
    path('boutique/apply/', apply_boutique, name='boutique-apply'),
    path('boutique/cancel/', cancel_boutique_application, name='boutique-cancel'),
    path('boutique/produits/', me_boutique_produits, name='boutique-produits'),
    path('me/boutique/produits/', me_boutique_produits, name='me-boutique-produits'),
    path('boutique/ventes/', me_boutique_ventes, name='boutique-ventes'),
    path('boutique/portefeuille/', me_boutique_portefeuille, name='boutique-portefeuille'),

    # Webhook public pour Campay Payouts
    path('payout/webhook/', campay_payout_webhook, name='campay-payout-webhook'),

    # Livreur Endpoints
    path('livreur/dashboard/', livreur_dashboard, name='livreur-dashboard'),
    path('livreur/livraisons/', livreur_commandes_list, name='livreur-commandes-list'),
    path('livreur/livraisons/<int:pk>/statut/', livreur_update_delivery_status, name='livreur-update-delivery-status'),

    # ADMINISTRATION (Routes réservées aux Admin)
    path('admin/users/', admin_users_list, name='admin-users-list'),
    path('admin/users/<int:pk>/toggle-status/', admin_user_toggle_status, name='admin-user-toggle-status'),
    path('admin/prestataires/', admin_prestataires_list, name='admin-prestataires-list'),
    path('admin/prestataires/validate/<int:pk>/', validate_prestataire, name='admin-prestataire-validate'),
    path('admin/prestataires/<int:pk>/update/', admin_prestataire_update, name='admin-prestataire-update'),
    path('admin/prestataires/<int:pk>/delete/', admin_delete_prestataire, name='admin-prestataire-delete'),
    path('admin/prestataires/<int:pk>/payout/', admin_prestataire_payout, name='admin-prestataire-payout'),
    path('admin/payouts/', admin_payouts_list, name='admin-payouts-list'),
    path('admin/payouts/<int:pk>/verifier/', admin_poll_campay_payout, name='admin-payout-check-status'),
    path('admin/stats/global/', admin_global_stats, name='admin-global-stats'),
    
    # Admin Boutique Endpoints
    path('admin/boutiques/', admin_boutiques_list, name='admin-boutiques-list'),
    path('admin/boutiques/financier/', admin_boutiques_financier, name='admin-boutiques-financier'),
    path('admin/boutiques/validate/<int:pk>/', validate_boutique, name='admin-boutique-validate'),
    path('admin/boutiques/<int:pk>/', admin_boutique_detail, name='admin-boutique-detail'),
    path('admin/boutiques/<int:pk>/produits/', admin_boutique_produits, name='admin-boutique-produits'),
    path('admin/boutiques/<int:pk>/effectuer-versement/', admin_boutique_effectuer_versement, name='admin-boutique-effectuer-versement'),

    # Admin Delivery Endpoints
    path('admin/livreurs/', admin_livreurs_list, name='admin-livreurs-list'),
    path('admin/livreurs/promote/', admin_promote_to_livreur, name='admin-promote-to-livreur'),
    path('admin/livreurs/<int:pk>/', admin_update_livreur, name='admin-update-livreur'),
    path('admin/livreurs/<int:pk>/delete/', admin_delete_livreur, name='admin-delete-livreur'),
    path('admin/commandes/<int:pk>/affecter-livreur/', admin_assign_delivery, name='admin-assign-delivery'),
    path('admin/livraisons/', admin_deliveries_monitor, name='admin-deliveries-monitor'),
    
    # Admin Serveuse Endpoints
    path('admin/serveuses/', admin_serveuses_list, name='admin-serveuses-list'),
    path('admin/serveuses/promote/', admin_promote_to_serveuse, name='admin-promote-to-serveuse'),
    path('admin/serveuses/<int:pk>/', admin_update_serveuse, name='admin-update-serveuse'),
    path('admin/serveuses/<int:pk>/delete/', admin_delete_serveuse, name='admin-delete-serveuse'),
]