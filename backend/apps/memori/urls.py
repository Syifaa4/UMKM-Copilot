from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.memori.views import MemoriViewSet

router = DefaultRouter()
router.register(r"memori", MemoriViewSet, basename="memori")

urlpatterns = [
    path("", include(router.urls)),
]
