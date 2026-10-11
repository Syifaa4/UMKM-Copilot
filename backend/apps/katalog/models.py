from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint

from apps.umkm.models import UMKM


class Produk(models.Model):
    """
    Satu SKU dalam katalog produk UMKM.
    SKU unik per UMKM. Warna dan ukuran boleh kosong untuk produk non-fashion.
    Harga dan stok dibatasi >= 0 melalui CheckConstraint di level database.
    """

    umkm = models.ForeignKey(
        UMKM,
        on_delete=models.PROTECT,
        related_name="produk",
    )
    sku = models.CharField(max_length=20)
    nama_produk = models.CharField(max_length=200)
    kategori = models.CharField(max_length=100)
    warna = models.CharField(max_length=50, blank=True)
    ukuran = models.CharField(max_length=20, blank=True)
    harga = models.DecimalField(max_digits=10, decimal_places=2)
    stok = models.IntegerField(default=0)
    aktif = models.BooleanField(default=True)
    diperbarui_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produk"
        verbose_name_plural = "Produk"
        ordering = ["umkm", "sku"]
        constraints = [
            UniqueConstraint(
                fields=["umkm", "sku"],
                name="unique_sku_per_umkm",
            ),
            CheckConstraint(
                condition=Q(harga__gte=0),
                name="produk_harga_nonneg",
            ),
            CheckConstraint(
                condition=Q(stok__gte=0),
                name="produk_stok_nonneg",
            ),
        ]

    def __str__(self):
        bagian = [self.nama_produk]
        if self.warna:
            bagian.append(self.warna)
        if self.ukuran:
            bagian.append(self.ukuran)
        return f"[{self.sku}] {' | '.join(bagian)}"


class KomponenHPP(models.Model):
    """
    Satu komponen biaya produksi per unit produk (HPP per unit).
    HPP total item pesanan = SUM(biaya) × kuantitas item, dihitung saat konfirmasi
    dan disimpan sebagai hpp_snapshot di ItemPesanan — tidak berubah setelahnya.
    """

    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name="komponen_hpp",
    )
    nama_komponen = models.CharField(max_length=200)
    biaya = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Biaya per unit produk.",
    )
    satuan = models.CharField(
        max_length=50,
        blank=True,
        help_text="Informatif, contoh: 'per pcs'.",
    )
    catatan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Komponen HPP"
        verbose_name_plural = "Komponen HPP"
        ordering = ["produk", "nama_komponen"]
        constraints = [
            CheckConstraint(
                condition=Q(biaya__gte=0),
                name="hpp_biaya_nonneg",
            ),
        ]

    def __str__(self):
        return f"{self.nama_komponen} — Rp {self.biaya} ({self.produk.sku})"
