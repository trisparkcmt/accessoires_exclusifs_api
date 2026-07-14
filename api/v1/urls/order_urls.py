from django.urls import path, include
from rest_framework.routers import DefaultRouter
from orders.views import (
    PanierDetailView,
    AjouterParfumView,
    AjouterAccessoireView,
    AjouterProduitFiniEssenceView,
    AjouterEssencePersonnaliseeView,
    AjouterParfumPersoLabView,
    PanierLigneDetailView,
    AppliquerCodePromoView,
    RetirerCodePromoView,
    CommandeListView,
    CommandeDetailView,
    PasserCommandeView,
    FactureDownloadView,
    AdminFactureListView,
    AdminFactureRenvoyerView,
    AdminCodePromoViewSet,
    CommanderCompositionDirecteView,
    AdminStatistiquesBeneficesView,
    # FUTURE_UPDATE_DIFFUSEUR: AjouterDiffuseurParfumView,
)

router = DefaultRouter()
router.register(r'admin/codes-promo', AdminCodePromoViewSet, basename='admin-codes-promo')

urlpatterns = [
    # Panier
    path('panier/', PanierDetailView.as_view(), name='panier-detail'),
    path('panier/ajouter/parfum/', AjouterParfumView.as_view(), name='panier-ajouter-parfum'),
    path('panier/ajouter/accessoire/', AjouterAccessoireView.as_view(), name='panier-ajouter-accessoire'),
    path('panier/ajouter/produit-fini-essence/', AjouterProduitFiniEssenceView.as_view(), name='panier-ajouter-produit-fini-essence'),
    path('panier/ajouter/essence-personnalisee/', AjouterEssencePersonnaliseeView.as_view(), name='panier-ajouter-essence-personnalisee'),
    path('panier/ajouter/composition-directe/', CommanderCompositionDirecteView.as_view(), name='panier-ajouter-composition-directe'),
    path('panier/ajouter/parfum-personnalise-labo/', AjouterParfumPersoLabView.as_view(), name='panier-ajouter-parfum-perso-labo'),
    path('panier/ligne/<str:type_ligne>/<int:ligne_id>/', PanierLigneDetailView.as_view(), name='panier-ligne-detail'),
    path('panier/appliquer-promo/', AppliquerCodePromoView.as_view(), name='panier-appliquer-promo'),
    path('panier/retirer-promo/', RetirerCodePromoView.as_view(), name='panier-retirer-promo'),
    # FUTURE_UPDATE_DIFFUSEUR: path('panier/ajouter/diffuseur-parfum/', AjouterDiffuseurParfumView.as_view(), name='panier-ajouter-diffuseur'),

    # Commandes
    path('commandes/', CommandeListView.as_view(), name='commandes-list'),
    path('commandes/passer/', PasserCommandeView.as_view(), name='commande-passer'),
    path('commandes/<str:numero>/', CommandeDetailView.as_view(), name='commande-detail'),

    # Factures
    path('commandes/<str:numero>/facture/', FactureDownloadView.as_view(), name='commande-facture-download'),
    path('admin/factures/', AdminFactureListView.as_view(), name='admin-factures-list'),
    path('admin/factures/<str:numero_facture>/renvoyer/', AdminFactureRenvoyerView.as_view(), name='admin-facture-renvoyer'),

    # Statistiques financières (admin only)
    path('commandes/statistiques-benefices/', AdminStatistiquesBeneficesView.as_view(), name='admin-statistiques-benefices'),

    # Routeur Admin
    path('', include(router.urls)),
]

