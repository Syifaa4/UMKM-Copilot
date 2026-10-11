from rest_framework import serializers

from apps.katalog.models import Produk


class ProdukSerializer(serializers.ModelSerializer):
    """
    Serializer read-only untuk Produk.
    Field umkm_id disertakan eksplisit sebagai informasi konteks;
    tidak digunakan untuk otorisasi di sisi client.
    """

    class Meta:
        model = Produk
        fields = [
            "id",
            "umkm_id",
            "sku",
            "nama_produk",
            "kategori",
            "warna",
            "ukuran",
            "harga",
            "stok",
            "aktif",
            "diperbarui_pada",
        ]
        read_only_fields = fields
