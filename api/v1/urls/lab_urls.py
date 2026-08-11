from django.urls import path, include
from rest_framework.routers import DefaultRouter
from laboratoire.views import (
    ParfumPersonnaliseViewSet,
    EssencePersonnaliseeViewSet,
    ia_recommandation,
    ia_conversations,
    vider_resume,
)
from catalogue.views import EssenceViewSet
from catalogue.urls import lab_urlpatterns

router = DefaultRouter()
router.register(r'parfums-perso', ParfumPersonnaliseViewSet, basename='parfumpersonnalise')
router.register(r'essences-perso', EssencePersonnaliseeViewSet, basename='essencepersonnalisee')

urlpatterns = [
    path('ia-recommandation/', ia_recommandation, name='ia-recommandation'),
    path('ia-conversations/', ia_conversations, name='ia-conversations'),
    path('ia-conversations/resume/', vider_resume, name='vider-resume'),
    path('essences/<slug:slug>/modifier/', EssenceViewSet.as_view({'patch': 'partial_update', 'put': 'update'}), name='essence-modifier'),
    path('', include(router.urls)),
    path('', include(lab_urlpatterns)),
]

