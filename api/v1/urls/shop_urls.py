# api/v1/urls/shop_urls.py
from django.urls import include
from catalogue.urls import shop_urlpatterns

urlpatterns = [
    *shop_urlpatterns,
    # FUTURE_UPDATE_DIFFUSEUR: Les diffuseurs sont déjà inclus via shop_urlpatterns puisqu'ils sont enregistrés sur shop_router dans catalogue/urls.py
]