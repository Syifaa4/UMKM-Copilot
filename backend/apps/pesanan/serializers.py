from rest_framework import serializers

from apps.pesanan.models import ItemPesanan, Pesanan


class ItemPesananSerializer(serializers.ModelSerializer):
    """Serializer read-only untuk satu item pesanan."""

    class Meta:
        model = ItemPesanan
        fields = [
            "id",
            "produk",
            "teks_asli",
            "nama_ditafsirkan",
            "kuantitas",
            "harga_satuan",
            "subtotal",
            "hpp_snapshot",
            "status_item",
            "catatan_validasi",
        ]
        read_only_fields = fields


class PesananSerializer(serializers.ModelSerializer):
    """Serializer read-only untuk pesanan (digunakan di list dan detail)."""

    item_pesanan = ItemPesananSerializer(many=True, read_only=True)

    class Meta:
        model = Pesanan
        fields = [
            "id",
            "umkm_id",
            "nomor_pesanan",
            "nama_pelanggan",
            "teks_chat_asli",
            "status",
            "catatan",
            "item_pesanan",
            "dibuat_pada",
            "diperbarui_pada",
        ]
        read_only_fields = fields


class BuatPesananSerializer(serializers.Serializer):
    """Serializer untuk POST /pesanan/ — membuat pesanan baru."""

    nama_pelanggan = serializers.CharField(max_length=200)
    teks_chat_asli = serializers.CharField()
    catatan = serializers.CharField(required=False, allow_blank=True, default="")


class VerifikasiItemSerializer(serializers.Serializer):
    """
    Serializer untuk PATCH items/{id}/verifikasi/.
    Operator memilih produk yang benar untuk item ambigu.
    produk_id harus milik UMKM yang sama dengan pesanan —
    divalidasi di service layer.
    """

    produk_id = serializers.IntegerField()
    kuantitas = serializers.IntegerField(min_value=1)
