"""
URL configuration for config project.

API endpoints:
  /api/katalog/produk/                              — daftar produk (GET, paginated)
  /api/katalog/produk/{id}/                         — detail produk (GET)
  /api/memori/memori/                               — daftar memori DISETUJUI (GET)
  /api/memori/memori/{id}/                          — detail memori (GET)
  /api/pesanan/pesanan/                             — daftar & buat pesanan
  /api/pesanan/pesanan/{id}/                        — detail pesanan
  /api/pesanan/pesanan/{id}/items/{iid}/verifikasi/ — verifikasi item
  /api/pesanan/pesanan/{id}/ajukan-review/          — DRAFT → MENUNGGU_REVIEW
  /api/pesanan/pesanan/{id}/konfirmasi/             — MENUNGGU_REVIEW → DIKONFIRMASI
  /api/pesanan/pesanan/{id}/selesai/                — DIKONFIRMASI → SELESAI
  /api/pesanan/pesanan/{id}/batalkan/               — * → DIBATALKAN
  /api/auth/token/                                  — obtain auth token
  /admin/                                           — Django Admin
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", obtain_auth_token, name="api-token-auth"),
    path("api/katalog/", include("apps.katalog.urls")),
    path("api/memori/", include("apps.memori.urls")),
    path("api/pesanan/", include("apps.pesanan.urls")),
]
