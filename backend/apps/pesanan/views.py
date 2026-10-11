import logging

logger = logging.getLogger(__name__)

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.katalog.models import Produk
from apps.pesanan.models import ItemPesanan, Pesanan
from apps.pesanan.serializers import (
    BuatPesananSerializer,
    PesananSerializer,
    VerifikasiItemSerializer,
)
from apps.pesanan import services
from apps.pesanan.langflow_client import LangflowError, LangflowTimeoutError
from apps.umkm.models import KeanggotaanPengguna
from apps.umkm.permissions import HasUMKMMembership, get_umkm_ids_for_user


class PesananPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _get_umkm_tunggal(user):
    """
    Mengembalikan objek UMKM pertama aktif milik user.
    Digunakan saat user hanya memiliki satu keanggotaan aktif.
    Untuk user multi-UMKM, UMKM dipilih secara otomatis dari keanggotaan aktif pertama.
    Catatan: pada tahap ini tidak ada mekanisme context switching UMKM.
    """
    keanggotaan = (
        KeanggotaanPengguna.objects.filter(user=user, aktif=True)
        .select_related("umkm")
        .first()
    )
    if keanggotaan is None:
        return None
    return keanggotaan.umkm


class PesananViewSet(viewsets.GenericViewSet):
    """
    ViewSet untuk pesanan. Semua operasi dibatasi ke UMKM milik user aktif.

    Endpoints:
      GET    /api/pesanan/pesanan/                          — daftar pesanan
      GET    /api/pesanan/pesanan/{id}/                     — detail pesanan
      POST   /api/pesanan/pesanan/                          — buat pesanan baru
      PATCH  /api/pesanan/pesanan/{id}/items/{item_id}/verifikasi/
      POST   /api/pesanan/pesanan/{id}/ajukan-review/
      POST   /api/pesanan/pesanan/{id}/konfirmasi/
      POST   /api/pesanan/pesanan/{id}/selesai/
      POST   /api/pesanan/pesanan/{id}/batalkan/
      POST   /api/pesanan/pesanan/{id}/proses-langflow/
    """

    permission_classes = [HasUMKMMembership]
    pagination_class = PesananPagination
    serializer_class = PesananSerializer

    def get_queryset(self):
        umkm_ids = get_umkm_ids_for_user(self.request.user)
        if not umkm_ids:
            return Pesanan.objects.none()
        qs = Pesanan.objects.filter(umkm_id__in=umkm_ids).prefetch_related(
            "item_pesanan__produk"
        )
        status_filter = self.request.query_params.get("status", "").strip().upper()
        if status_filter and status_filter in Pesanan.STATUS_VALID:
            qs = qs.filter(status=status_filter)
        return qs.order_by("-dibuat_pada")

    def _get_pesanan_atau_404(self, pk):
        """Ambil pesanan yang scope-nya sudah dibatasi ke UMKM user."""
        umkm_ids = get_umkm_ids_for_user(self.request.user)
        return get_object_or_404(Pesanan, pk=pk, umkm_id__in=umkm_ids)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = PesananSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = PesananSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        pesanan = self._get_pesanan_atau_404(pk)
        return Response(PesananSerializer(pesanan).data)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, request):
        serializer = BuatPesananSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        umkm = _get_umkm_tunggal(request.user)
        if umkm is None:
            return Response(
                {"detail": "Tidak ada keanggotaan UMKM aktif."},
                status=status.HTTP_403_FORBIDDEN,
            )

        pesanan = services.buat_pesanan(
            umkm=umkm,
            nama_pelanggan=serializer.validated_data["nama_pelanggan"],
            teks_chat_asli=serializer.validated_data["teks_chat_asli"],
            catatan=serializer.validated_data.get("catatan", ""),
        )
        return Response(
            PesananSerializer(pesanan).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Verifikasi item
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"items/(?P<item_id>\d+)/verifikasi",
    )
    def verifikasi_item(self, request, pk=None, item_id=None):
        pesanan = self._get_pesanan_atau_404(pk)
        item = get_object_or_404(ItemPesanan, pk=item_id, pesanan=pesanan)

        serializer = VerifikasiItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        produk_id = serializer.validated_data["produk_id"]
        kuantitas = serializer.validated_data["kuantitas"]

        # Produk harus milik UMKM yang sama — divalidasi ulang di service
        umkm_ids = get_umkm_ids_for_user(request.user)
        produk = get_object_or_404(Produk, pk=produk_id, umkm_id__in=umkm_ids)

        try:
            item = services.verifikasi_item(pesanan, item, produk, kuantitas)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            PesananSerializer(
                Pesanan.objects.prefetch_related("item_pesanan__produk")
                .get(pk=pesanan.pk)
            ).data
        )

    # ------------------------------------------------------------------
    # Transisi status
    # ------------------------------------------------------------------

    def _aksi_transisi(self, request, pk, service_fn, nama_aksi):
        """Helper generik untuk endpoint transisi status."""
        pesanan = self._get_pesanan_atau_404(pk)
        try:
            pesanan = service_fn(pesanan)
        except (ValueError, RuntimeError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(PesananSerializer(pesanan).data)

    @action(detail=True, methods=["post"], url_path="ajukan-review")
    def ajukan_review(self, request, pk=None):
        return self._aksi_transisi(
            request, pk, services.ajukan_review, "ajukan-review"
        )

    @action(detail=True, methods=["post"], url_path="konfirmasi")
    def konfirmasi(self, request, pk=None):
        pesanan = self._get_pesanan_atau_404(pk)
        try:
            pesanan, _ = services.konfirmasi_pesanan(pesanan)
        except (ValueError, RuntimeError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(PesananSerializer(pesanan).data)

    @action(detail=True, methods=["post"], url_path="selesai")
    def selesai(self, request, pk=None):
        return self._aksi_transisi(
            request, pk, services.selesaikan_pesanan, "selesai"
        )

    @action(detail=True, methods=["post"], url_path="batalkan")
    def batalkan(self, request, pk=None):
        return self._aksi_transisi(
            request, pk, services.batalkan_pesanan, "batalkan"
        )

    @action(detail=True, methods=["post"], url_path="proses-langflow")
    def proses_langflow(self, request, pk=None):
        """
        Kirim teks_chat_asli pesanan ke Langflow, simpan hasilnya sebagai
        ItemPesanan, dan transisikan pesanan ke MENUNGGU_REVIEW.

        Hanya dapat dipanggil pada pesanan berstatus DRAFT.
        Harga diambil dari database — tidak dari output AI.
        """
        pesanan = self._get_pesanan_atau_404(pk)
        try:
            pesanan = services.proses_langflow(pesanan)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except LangflowTimeoutError:
            return Response(
                {"detail": "Langflow tidak merespons. Coba lagi beberapa saat."},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        
        except LangflowError as exc:
            logger.exception(
                "Integrasi Langflow gagal untuk pesanan ID=%s: %s",
                pk,
                exc,
            )
            return Response(
                {"detail": "Gagal menghubungi layanan AI. Coba lagi nanti."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(PesananSerializer(pesanan).data)
