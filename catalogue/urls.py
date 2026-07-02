# catalogue/urls.py
from rest_framework.routers import DefaultRouter

from .views import EssenceLaboViewSet, IngredientViewSet, LotEssenceViewSet, ParfumViewSet, EssenceViewSet, AccessoireViewSet, FlaconViewSet, FavoriViewSet, ProduitFiniEssenceViewSet, PromotionViewSet, TagEssenceSelectViewSet, TagParfumSelectViewSet, TagViewSet, NotificationCatalogueViewSet, MouvementStockViewSet, BestsellerViewSet, HotsellerViewSet
from .views import CategorieParfumViewSet, TypeAccessoireViewSet, TypeFlaconViewSet

# ============================================================
# ROUTER SHOP — /api/shop/...
# Parfums, Accessoires, Flacons
# ============================================================
shop_router = DefaultRouter()
shop_router.register(r'parfums',     ParfumViewSet,     basename='parfum')
shop_router.register(r'accessoires', AccessoireViewSet, basename='accessoire')
shop_router.register(r'flacons',     FlaconViewSet,     basename='flacon')
shop_router.register(r'favoris', FavoriViewSet, basename='favori')
shop_router.register(r'tags', TagViewSet, basename='tag') 
shop_router.register(r'tags-parfum', TagParfumSelectViewSet, basename='tagparfum-select')
shop_router.register(r'tags-essence', TagEssenceSelectViewSet, basename='tagessence-select')
shop_router.register(r'categories-parfum', CategorieParfumViewSet, basename='categorieparfum')
shop_router.register(r'types-accessoire', TypeAccessoireViewSet, basename='typeaccessoire')
shop_router.register(r'types-flacon', TypeFlaconViewSet, basename='typeflacon')
shop_router.register(r'produits-essence', ProduitFiniEssenceViewSet, basename='produitessence')
shop_router.register(r'promotions', PromotionViewSet, basename='promotion')
shop_router.register(r'bestsellers', BestsellerViewSet, basename='bestsellers')
shop_router.register(r'hotsellers', HotsellerViewSet, basename='hotsellers')
shop_router.register(r'notifications', NotificationCatalogueViewSet, basename='notificationcatalogue')
shop_router.register(r'mouvements-stock', MouvementStockViewSet, basename='mouvementstock')
# ============================================================
# ROUTER LAB — /api/lab/...
# Essences
# ============================================================
lab_router = DefaultRouter()
lab_router.register(r'essences', EssenceViewSet, basename='essence')
lab_router.register(r'ingredients', IngredientViewSet, basename='ingredient')
lab_router.register(r'tags-essence', TagEssenceSelectViewSet, basename='tagessence-select-lab')

lab_router.register(r'lots-essence', LotEssenceViewSet, basename='lotessence')
lab_router.register(r'labo/essences', EssenceLaboViewSet, basename='essencelabo')


# Exportés et utilisés dans shop_urls.py et lab_urls.py
shop_urlpatterns = shop_router.urls
lab_urlpatterns  = lab_router.urls

# urlpatterns vide ici — chaque router est branché dans son fichier dédié
urlpatterns = []
