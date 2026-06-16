from django.urls import path
from orders.views import (
    PanierDetailView,
    AjouterParfumView,
    AjouterAccessoireView,
    AjouterProduitFiniEssenceView,
    AjouterParfumPersonnaliseView,
    AjouterEssencePersonnaliseeView,
    PanierLigneDetailView,
    AppliquerCodePromoView,
    RetirerCodePromoView,
    CommandeListView,
    CommandeDetailView,
    PasserCommandeView
)

urlpatterns = [
    # Panier
    path('panier/', PanierDetailView.as_view(), name='panier-detail'),
    path('panier/ajouter/parfum/', AjouterParfumView.as_view(), name='panier-ajouter-parfum'),
    path('panier/ajouter/accessoire/', AjouterAccessoireView.as_view(), name='panier-ajouter-accessoire'),
    path('panier/ajouter/produit-fini-essence/', AjouterProduitFiniEssenceView.as_view(), name='panier-ajouter-produit-fini-essence'),
    path('panier/ajouter/parfum-personnalise/', AjouterParfumPersonnaliseView.as_view(), name='panier-ajouter-parfum-personnalise'),
    path('panier/ajouter/essence-personnalisee/', AjouterEssencePersonnaliseeView.as_view(), name='panier-ajouter-essence-personnalisee'),
    path('panier/ligne/<str:type_ligne>/<int:ligne_id>/', PanierLigneDetailView.as_view(), name='panier-ligne-detail'),
    path('panier/appliquer-promo/', AppliquerCodePromoView.as_view(), name='panier-appliquer-promo'),
    path('panier/retirer-promo/', RetirerCodePromoView.as_view(), name='panier-retirer-promo'),

    # Commandes
    path('commandes/', CommandeListView.as_view(), name='commandes-list'),
    path('commandes/passer/', PasserCommandeView.as_view(), name='commande-passer'),
    path('commandes/<str:numero>/', CommandeDetailView.as_view(), name='commande-detail'),
]

