from rest_framework import serializers

from apps.memori.models import Memori


class MemoriSerializer(serializers.ModelSerializer):
    """
    Serializer read-only untuk Memori berstatus DISETUJUI.
    Field status disertakan untuk konfirmasi di sisi client;
    view sudah memastikan hanya DISETUJUI yang dikembalikan.
    """

    class Meta:
        model = Memori
        fields = [
            "id",
            "umkm_id",
            "id_memori",
            "istilah",
            "makna",
            "sumber",
            "status",
            "versi",
            "makna_sebelumnya",
            "dibuat_pada",
            "disetujui_oleh",
            "catatan",
        ]
        read_only_fields = fields
