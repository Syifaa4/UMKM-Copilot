from django.db.models import Q
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from apps.katalog.models import Produk
from apps.katalog.serializers import ProdukSerializer
from apps.umkm.permissions import HasUMKMMembership, get_umkm_ids_for_user


class ProdukPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ProdukViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API read-only untuk katalog produk.

    Queryset dibatasi ke UMKM yang menjadi keanggotaan aktif user terautentikasi.
    UMKM_ID dari query parameter atau body tidak pernah digunakan untuk otorisasi.

    Filter yang tersedia:
      ?kategori=Kaos          — filter by kategori (case-sensitive sesuai data)
      ?aktif=true|false       — filter by status aktif (default: hanya aktif)
      ?search=kata            — pencarian nama_produk atau sku (case-insensitive)

    Pagination:
      ?page=2&page_size=10    — navigasi halaman, max 100 per halaman
    """

    serializer_class = ProdukSerializer
    permission_classes = [HasUMKMMembership]
    pagination_class = ProdukPagination

    def get_queryset(self):
        umkm_ids = get_umkm_ids_for_user(self.request.user)
        # Jika user tidak punya keanggotaan aktif, kembalikan queryset kosong.
        # HasUMKMMembership seharusnya sudah mencegah ini, tapi defense-in-depth.
        if not umkm_ids:
            return Produk.objects.none()

        qs = Produk.objects.filter(umkm_id__in=umkm_ids)

        # Filter aktif — default hanya produk aktif
        aktif_param = self.request.query_params.get("aktif", "true").strip().lower()
        if aktif_param == "false":
            qs = qs.filter(aktif=False)
        else:
            qs = qs.filter(aktif=True)

        # Filter kategori
        kategori = self.request.query_params.get("kategori", "").strip()
        if kategori:
            qs = qs.filter(kategori=kategori)

        # Pencarian nama_produk atau SKU — satu filter Q agar scope UMKM tidak pecah
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(nama_produk__icontains=search) | Q(sku__icontains=search)
            )

        return qs.order_by("umkm_id", "sku")
