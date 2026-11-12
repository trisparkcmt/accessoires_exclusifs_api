from django.urls import path
from orders.pos_views import (
    POSProductSearchView,
    POSCommandeCreateView,
    POSRapportJournalierApercuView,
    POSRapportJournalierClotureView,
    POSRapportJournalierListView,
    POSRapportJournalierDetailView,
)

urlpatterns = [
    path('produits/recherche/', POSProductSearchView.as_view(), name='pos-produits-recherche'),
    path('commandes/creer/', POSCommandeCreateView.as_view(), name='pos-commandes-creer'),
    path('rapport-journalier/apercu/', POSRapportJournalierApercuView.as_view(), name='pos-rapport-apercu'),
    path('rapport-journalier/cloturer/', POSRapportJournalierClotureView.as_view(), name='pos-rapport-cloturer'),
    path('rapport-journalier/', POSRapportJournalierListView.as_view(), name='pos-rapport-list'),
    path('rapport-journalier/<int:pk>/', POSRapportJournalierDetailView.as_view(), name='pos-rapport-detail'),
]
