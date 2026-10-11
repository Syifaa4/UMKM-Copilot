from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.pesanan.views import PesananViewSet

router = DefaultRouter()
router.register(r"pesanan", PesananViewSet, basename="pesanan")

urlpatterns = [
    path("", include(router.urls)),
]
