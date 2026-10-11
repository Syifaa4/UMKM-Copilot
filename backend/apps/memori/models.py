from django.db import models
from django.db.models import Q, UniqueConstraint

from apps.umkm.models import UMKM


class Memori(models.Model):
    """
    Alias atau istilah bisnis yang dipahami Langflow untuk satu UMKM.

    Aturan penggunaan:
    - Langflow hanya boleh menggunakan baris dengan status='DISETUJUI'.
    - Hanya boleh ada satu memori berstatus DISETUJUI per (umkm, istilah),
      dijaga melalui UniqueConstraint parsial di level database.
    - Saat memperbarui makna: set baris lama ke DIGANTIKAN dulu, baru insert
      atau update baris baru ke DISETUJUI — keduanya dalam satu transaction.atomic().
    - Versi bertambah setiap pergantian; Makna_Sebelumnya mencatat makna versi lama.
    """

    STATUS_DISETUJUI = "DISETUJUI"
    STATUS_DIGANTIKAN = "DIGANTIKAN"
    STATUS_PENDING = "PENDING"

    STATUS_CHOICES = [
        (STATUS_DISETUJUI, "Disetujui"),
        (STATUS_DIGANTIKAN, "Digantikan"),
        (STATUS_PENDING, "Pending"),
    ]

    umkm = models.ForeignKey(
        UMKM,
        on_delete=models.CASCADE,
        related_name="memori",
    )
    id_memori = models.CharField(
        max_length=20,
        help_text="Identifier dari CSV, contoh: MEM001.",
    )
    istilah = models.CharField(
        max_length=100,
        help_text="Kata/frasa yang digunakan pelanggan, contoh: 'premium'.",
    )
    makna = models.CharField(
        max_length=200,
        help_text="Nama produk atau deskripsi yang dimaksud istilah ini.",
    )
    sumber = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    versi = models.PositiveIntegerField(default=1)
    makna_sebelumnya = models.CharField(
        max_length=200,
        blank=True,
        help_text="Makna dari versi sebelumnya yang digantikan.",
    )
    dibuat_pada = models.DateField()
    disetujui_oleh = models.CharField(max_length=100, blank=True)
    tindakan = models.CharField(
        max_length=50,
        blank=True,
        help_text="Contoh: 'aktif', 'digantikan'.",
    )
    catatan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Memori"
        verbose_name_plural = "Memori"
        ordering = ["umkm", "istilah", "-versi"]
        constraints = [
            UniqueConstraint(
                fields=["umkm", "id_memori"],
                name="unique_id_memori_per_umkm",
            ),
            UniqueConstraint(
                fields=["umkm", "istilah"],
                condition=Q(status="DISETUJUI"),
                name="unique_istilah_disetujui_per_umkm",
            ),
        ]

    def __str__(self):
        return f"[{self.umkm_id}] '{self.istilah}' → {self.makna} (v{self.versi}, {self.status})"
