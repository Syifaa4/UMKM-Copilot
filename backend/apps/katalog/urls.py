from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.katalog.views import ProdukViewSet

router = DefaultRouter()
router.register(r"produk", ProdukViewSet, basename="produk")

urlpatterns = [
    path("", include(router.urls)),
]
