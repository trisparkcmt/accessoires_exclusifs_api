from django.urls import path
from .views import (
    user_notifications, detail_prestataire_request, list_prestataire_requests,
    admin_best_clients, admin_best_prestataires,
    register_fcm_device, unregister_fcm_device,
)

urlpatterns = [
    path('notifications/', user_notifications, name='user-notifications'),
    path('admin/meilleurs-clients/', admin_best_clients, name='admin-best-clients'),
    path('admin/meilleurs-prestataires/', admin_best_prestataires, name='admin-best-prestataires'),
    path('prestataire-requests/', list_prestataire_requests, name='prestataire-requests'),
    path('prestataire-requests/<int:pk>/', detail_prestataire_request, name='prestataire-request-detail'),
    # FCM Push Notifications
    path('devices/register/', register_fcm_device, name='fcm-device-register'),
    path('devices/unregister/', unregister_fcm_device, name='fcm-device-unregister'),
]
