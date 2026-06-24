from django.urls import path
from orders.pos_views import POSProductSearchView, POSCommandeCreateView

urlpatterns = [
    path('produits/recherche/', POSProductSearchView.as_view(), name='pos-produits-recherche'),
    path('commandes/creer/', POSCommandeCreateView.as_view(), name='pos-commandes-creer'),
]
