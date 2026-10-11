from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from apps.memori.models import Memori
from apps.memori.serializers import MemoriSerializer
from apps.umkm.permissions import HasUMKMMembership, get_umkm_ids_for_user


class MemoriPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class MemoriViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API read-only untuk memori alias produk.

    Hanya mengembalikan memori berstatus DISETUJUI.
    Status DIGANTIKAN dan PENDING tidak pernah dikembalikan melalui endpoint ini,
    tanpa pengecualian — filter ini di-hardcode dan tidak dapat diubah via query param.

    Queryset dibatasi ke UMKM keanggotaan aktif user terautentikasi.

    Filter yang tersedia:
      ?istilah=premium        — filter by istilah (case-insensitive)
    """

    serializer_class = MemoriSerializer
    permission_classes = [HasUMKMMembership]
    pagination_class = MemoriPagination

    def get_queryset(self):
        umkm_ids = get_umkm_ids_for_user(self.request.user)
        if not umkm_ids:
            return Memori.objects.none()

        # status=DISETUJUI di-hardcode — tidak dapat di-override via query param
        qs = Memori.objects.filter(
            umkm_id__in=umkm_ids,
            status=Memori.STATUS_DISETUJUI,
        )

        # Filter opsional by istilah
        istilah = self.request.query_params.get("istilah", "").strip()
        if istilah:
            qs = qs.filter(istilah__icontains=istilah)

        return qs.order_by("umkm_id", "istilah")
