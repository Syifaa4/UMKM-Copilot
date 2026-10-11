from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.umkm import services
from apps.umkm.serializers import DaftarSerializer


class DaftarThrottle(AnonRateThrottle):
    scope = "daftar"
    rate = "10/hour"


class DaftarView(APIView):
    """POST /api/auth/daftar/ — daftar akun + UMKM baru (publik)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [DaftarThrottle]

    def post(self, request):
        serializer = DaftarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user, umkm, token, jumlah = services.daftar_umkm_baru(
                **serializer.validated_data
            )
        except IntegrityError:
            # Dua pendaftaran dengan username sama pada saat bersamaan
            return Response(
                {"username": ["Username sudah dipakai."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "token": token,
                "username": user.username,
                "umkm": {"id": umkm.id, "nama": umkm.nama},
                "katalog_contoh": jumlah,
            },
            status=status.HTTP_201_CREATED,
        )