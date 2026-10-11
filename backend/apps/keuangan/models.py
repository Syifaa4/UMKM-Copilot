from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint

from apps.umkm.models import UMKM
from apps.pesanan.models import Pesanan


# Mapping valid antara kategori dan jenis transaksi.
# Digunakan oleh CheckConstraint DB, clean(), dan service layer.
KATEGORI_JENIS_VALID = {
    "PENJUALAN": "PEMASUKAN",
    "PEMASUKAN_LAIN": "PEMASUKAN",
    "KOREKSI_PEMBATALAN": "PENGELUARAN",
    "BAHAN_BAKU": "PENGELUARAN",
    "OPERASIONAL": "PENGELUARAN",
    "LAINNYA": "PENGELUARAN",
}


class Transaksi(models.Model):
    """
    Buku kas UMKM — satu-satunya sumber kebenaran untuk laporan keuangan.

    Aturan pembuatan transaksi penjualan:
    - Dibuat oleh service konfirmasi_pesanan() dalam blok transaction.atomic()
      bersamaan dengan pengisian hpp_snapshot di ItemPesanan.
    - Hanya boleh ada satu transaksi PENJUALAN per pesanan (UniqueConstraint parsial).
    - Hanya boleh ada satu transaksi KOREKSI_PEMBATALAN per pesanan (UniqueConstraint parsial).
    - Transaksi yang sudah ada tidak boleh diubah atau dihapus — audit trail permanen.
    - Konsistensi UMKM antara transaksi dan pesanan dijaga di service layer dan clean().

    Definisi laporan (semua dari tabel ini):
      Omzet kotor     = SUM(jumlah) WHERE kategori=PENJUALAN
      Koreksi         = SUM(jumlah) WHERE kategori=KOREKSI_PEMBATALAN
      Omzet bersih    = Omzet kotor − Koreksi
      Pengeluaran ops = SUM(jumlah) WHERE kategori IN (BAHAN_BAKU, OPERASIONAL, LAINNYA)
      Pemasukan lain  = SUM(jumlah) WHERE kategori=PEMASUKAN_LAIN

    HPP dihitung terpisah dari ItemPesanan.hpp_snapshot untuk pesanan yang
    tidak memiliki KOREKSI_PEMBATALAN (pesanan yang tidak dibatalkan).
    """

    JENIS_PEMASUKAN = "PEMASUKAN"
    JENIS_PENGELUARAN = "PENGELUARAN"

    JENIS_CHOICES = [
        (JENIS_PEMASUKAN, "Pemasukan"),
        (JENIS_PENGELUARAN, "Pengeluaran"),
    ]

    KATEGORI_PENJUALAN = "PENJUALAN"
    KATEGORI_PEMASUKAN_LAIN = "PEMASUKAN_LAIN"
    KATEGORI_KOREKSI_PEMBATALAN = "KOREKSI_PEMBATALAN"
    KATEGORI_BAHAN_BAKU = "BAHAN_BAKU"
    KATEGORI_OPERASIONAL = "OPERASIONAL"
    KATEGORI_LAINNYA = "LAINNYA"

    KATEGORI_CHOICES = [
        (KATEGORI_PENJUALAN, "Penjualan"),
        (KATEGORI_PEMASUKAN_LAIN, "Pemasukan Lain"),
        (KATEGORI_KOREKSI_PEMBATALAN, "Koreksi Pembatalan"),
        (KATEGORI_BAHAN_BAKU, "Bahan Baku"),
        (KATEGORI_OPERASIONAL, "Operasional"),
        (KATEGORI_LAINNYA, "Lainnya"),
    ]

    umkm = models.ForeignKey(
        UMKM,
        on_delete=models.PROTECT,
        related_name="transaksi",
    )
    pesanan = models.ForeignKey(
        Pesanan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transaksi",
        help_text=(
            "Pesanan yang menghasilkan transaksi ini. "
            "Null untuk transaksi manual (pengeluaran operasional, dsb). "
            "PROTECT mencegah penghapusan pesanan yang sudah punya transaksi."
        ),
    )
    jenis = models.CharField(max_length=20, choices=JENIS_CHOICES)
    kategori = models.CharField(max_length=30, choices=KATEGORI_CHOICES)
    jumlah = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Selalu positif. Arah arus kas ditentukan oleh field 'jenis'.",
    )
    keterangan = models.TextField(blank=True)
    tanggal = models.DateField(
        help_text="Tanggal ekonomis transaksi (bukan waktu pencatatan).",
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transaksi"
        verbose_name_plural = "Transaksi"
        ordering = ["-tanggal", "-dibuat_pada"]
        constraints = [
            # Jumlah harus positif
            CheckConstraint(
                condition=Q(jumlah__gt=0),
                name="transaksi_jumlah_positif",
            ),
            # Kombinasi jenis+kategori harus valid
            CheckConstraint(
                condition=(
                    Q(kategori="PENJUALAN",          jenis="PEMASUKAN")
                    | Q(kategori="PEMASUKAN_LAIN",     jenis="PEMASUKAN")
                    | Q(kategori="KOREKSI_PEMBATALAN", jenis="PENGELUARAN")
                    | Q(kategori="BAHAN_BAKU",         jenis="PENGELUARAN")
                    | Q(kategori="OPERASIONAL",        jenis="PENGELUARAN")
                    | Q(kategori="LAINNYA",            jenis="PENGELUARAN")
                ),
                name="transaksi_jenis_kategori_valid",
            ),
            # Hanya satu transaksi PENJUALAN per pesanan
            UniqueConstraint(
                fields=["pesanan"],
                condition=Q(kategori="PENJUALAN"),
                name="unique_penjualan_per_pesanan",
            ),
            # Hanya satu transaksi KOREKSI_PEMBATALAN per pesanan
            UniqueConstraint(
                fields=["pesanan"],
                condition=Q(kategori="KOREKSI_PEMBATALAN"),
                name="unique_koreksi_per_pesanan",
            ),
            # Transaksi PENJUALAN dan KOREKSI_PEMBATALAN wajib terkait pesanan
            CheckConstraint(
                condition=(
                    ~Q(kategori__in=["PENJUALAN", "KOREKSI_PEMBATALAN"])
                    | Q(pesanan__isnull=False)
                ),
                name="transaksi_penjualan_wajib_pesanan",
            ),
        ]

    def clean(self):
        """
        Validasi fallback untuk jalur yang memanggil full_clean() (mis. Django Admin).
        Validasi utama (termasuk konsistensi UMKM) ditegakkan di service layer.
        """
        # Validasi kombinasi jenis + kategori
        jenis_valid = KATEGORI_JENIS_VALID.get(self.kategori)
        if jenis_valid and self.jenis != jenis_valid:
            raise ValidationError(
                f"Kategori '{self.kategori}' hanya valid untuk jenis '{jenis_valid}', "
                f"bukan '{self.jenis}'."
            )

        # Validasi konsistensi UMKM antara transaksi dan pesanan
        if self.pesanan_id is not None:
            # Akses pesanan.umkm_id secara langsung untuk menghindari query tambahan
            # jika pesanan sudah di-cache; jika belum, query satu baris saja.
            pesanan_umkm_id = (
                self.pesanan.umkm_id
                if hasattr(self, "_pesanan_cache")
                else Pesanan.objects.filter(pk=self.pesanan_id).values_list(
                    "umkm_id", flat=True
                ).first()
            )
            if pesanan_umkm_id is not None and pesanan_umkm_id != self.umkm_id:
                raise ValidationError(
                    "UMKM transaksi dan UMKM pesanan harus sama. "
                    f"Transaksi: '{self.umkm_id}', Pesanan: '{pesanan_umkm_id}'."
                )

    def __str__(self):
        ref = f" (Pesanan: {self.pesanan_id})" if self.pesanan_id else ""
        return (
            f"[{self.umkm_id}] {self.get_kategori_display()} "
            f"Rp {self.jumlah:,.0f} — {self.tanggal}{ref}"
        )
