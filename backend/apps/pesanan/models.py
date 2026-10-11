from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint

from apps.umkm.models import UMKM
from apps.katalog.models import Produk


class Pesanan(models.Model):
    """
    Header pesanan dari satu percakapan chat pelanggan.

    Alur status:
        DRAFT → MENUNGGU_REVIEW → DIKONFIRMASI → SELESAI
                               ↘ DIBATALKAN

    Aturan laporan:
    - Hanya pesanan DIKONFIRMASI dan SELESAI yang menghasilkan Transaksi penjualan.
    - Pembatalan setelah konfirmasi dicatat sebagai Transaksi KOREKSI_PEMBATALAN
      terpisah; status pesanan berubah ke DIBATALKAN.
    - Laporan keuangan tidak memfilter berdasarkan status pesanan — semua kalkulasi
      diambil dari tabel Transaksi saja.
    """

    STATUS_DRAFT = "DRAFT"
    STATUS_MENUNGGU_REVIEW = "MENUNGGU_REVIEW"
    STATUS_DIKONFIRMASI = "DIKONFIRMASI"
    STATUS_SELESAI = "SELESAI"
    STATUS_DIBATALKAN = "DIBATALKAN"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_MENUNGGU_REVIEW, "Menunggu Review"),
        (STATUS_DIKONFIRMASI, "Dikonfirmasi"),
        (STATUS_SELESAI, "Selesai"),
        (STATUS_DIBATALKAN, "Dibatalkan"),
    ]

    STATUS_VALID = {
        STATUS_DRAFT,
        STATUS_MENUNGGU_REVIEW,
        STATUS_DIKONFIRMASI,
        STATUS_SELESAI,
        STATUS_DIBATALKAN,
    }

    umkm = models.ForeignKey(
        UMKM,
        on_delete=models.PROTECT,
        related_name="pesanan",
    )
    nomor_pesanan = models.CharField(
        max_length=50,
        unique=True,
        help_text="Auto-generate, contoh: ORD-U001-20261001-0001.",
    )
    nama_pelanggan = models.CharField(max_length=200)
    teks_chat_asli = models.TextField(
        help_text="Teks mentah percakapan chat dari pelanggan.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    catatan = models.TextField(blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diperbarui_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pesanan"
        verbose_name_plural = "Pesanan"
        ordering = ["-dibuat_pada"]
        constraints = [
            CheckConstraint(
                condition=Q(status__in=[
                    "DRAFT",
                    "MENUNGGU_REVIEW",
                    "DIKONFIRMASI",
                    "SELESAI",
                    "DIBATALKAN",
                ]),
                name="pesanan_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.nomor_pesanan} — {self.nama_pelanggan} [{self.status}]"


class ItemPesanan(models.Model):
    """
    Satu baris produk dalam pesanan, hasil tafsir Langflow dari teks chat.

    Aturan integritas harga/subtotal:
    - harga_satuan dan subtotal hanya boleh diisi oleh service konfirmasi_item()
      setelah operator memverifikasi produk yang cocok.
    - Item dengan status_item AMBIGU atau TIDAK_DITEMUKAN tidak boleh memiliki
      harga_satuan atau subtotal — dijaga di service dan serializer, bukan hanya clean().
    - hpp_snapshot diisi sekali saat konfirmasi pesanan dalam blok transaction.atomic();
      setelah itu tidak boleh diubah melalui endpoint apapun.

    Batasan MVP:
    - Stok produk tidak dikelola otomatis saat konfirmasi atau pembatalan pesanan.
      Pembaruan stok dilakukan manual oleh operator melalui endpoint update produk.
    """

    STATUS_DITEMUKAN = "DITEMUKAN"
    STATUS_AMBIGU = "AMBIGU"
    STATUS_TIDAK_DITEMUKAN = "TIDAK_DITEMUKAN"
    STATUS_DIKONFIRMASI = "DIKONFIRMASI"

    STATUS_ITEM_CHOICES = [
        (STATUS_DITEMUKAN, "Ditemukan"),
        (STATUS_AMBIGU, "Ambigu"),
        (STATUS_TIDAK_DITEMUKAN, "Tidak Ditemukan"),
        (STATUS_DIKONFIRMASI, "Dikonfirmasi"),
    ]

    STATUS_TERVERIFIKASI = {STATUS_DITEMUKAN, STATUS_DIKONFIRMASI}

    pesanan = models.ForeignKey(
        Pesanan,
        on_delete=models.CASCADE,
        related_name="item_pesanan",
    )
    produk = models.ForeignKey(
        Produk,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="item_pesanan",
    )
    teks_asli = models.CharField(
        max_length=500,
        help_text="Teks mentah dari chat, contoh: '2 kaos premium hitam M'.",
    )
    nama_ditafsirkan = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nama produk hasil tafsir Langflow.",
    )
    kuantitas = models.PositiveIntegerField(default=1)
    harga_satuan = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diisi hanya jika produk terverifikasi (DITEMUKAN atau DIKONFIRMASI).",
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diisi hanya jika produk terverifikasi. Null jika masih ambigu.",
    )
    hpp_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Total HPP untuk seluruh kuantitas item ini, "
            "diisi sekali saat pesanan dikonfirmasi dan tidak boleh diubah setelahnya. "
            "Nilai 0.00 berarti produk tidak memiliki data KomponenHPP."
        ),
    )
    status_item = models.CharField(
        max_length=20,
        choices=STATUS_ITEM_CHOICES,
        default=STATUS_TIDAK_DITEMUKAN,
    )
    catatan_validasi = models.TextField(
        blank=True,
        help_text="Pesan validasi dari Langflow atau catatan operator.",
    )

    class Meta:
        verbose_name = "Item Pesanan"
        verbose_name_plural = "Item Pesanan"
        ordering = ["pesanan", "id"]
        constraints = [
            CheckConstraint(
                condition=Q(kuantitas__gte=1),
                name="item_kuantitas_min1",
            ),
            CheckConstraint(
                condition=Q(harga_satuan__isnull=True) | Q(harga_satuan__gte=0),
                name="item_harga_nonneg",
            ),
            CheckConstraint(
                condition=Q(subtotal__isnull=True) | Q(subtotal__gte=0),
                name="item_subtotal_nonneg",
            ),
            CheckConstraint(
                condition=Q(hpp_snapshot__isnull=True) | Q(hpp_snapshot__gte=0),
                name="item_hpp_nonneg",
            ),
        ]

    def clean(self):
        """
        Validasi fallback untuk jalur yang memanggil full_clean() (mis. Django Admin).
        Validasi utama ditegakkan di service layer, bukan hanya di sini.
        """
        item_belum_terverifikasi = self.status_item not in (
            self.STATUS_DITEMUKAN,
            self.STATUS_DIKONFIRMASI,
        )
        if item_belum_terverifikasi:
            if self.harga_satuan is not None:
                raise ValidationError(
                    "harga_satuan tidak boleh diisi untuk item yang belum terverifikasi."
                )
            if self.subtotal is not None:
                raise ValidationError(
                    "subtotal tidak boleh diisi untuk item yang belum terverifikasi."
                )

    def __str__(self):
        return (
            f"[{self.pesanan.nomor_pesanan}] {self.teks_asli!r} "
            f"× {self.kuantitas} [{self.status_item}]"
        )
