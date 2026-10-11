from django.contrib.auth.models import User
from django.db import models
from django.db.models import UniqueConstraint


class UMKM(models.Model):
    """
    Entitas utama UMKM. ID ditetapkan manual sesuai konvensi CSV (mis. 'U001').
    Semua data katalog, memori, pesanan, dan keuangan ber-scope ke UMKM ini.
    """

    id = models.CharField(max_length=10, primary_key=True)
    nama = models.CharField(max_length=100)
    deskripsi = models.TextField(blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "UMKM"
        verbose_name_plural = "UMKM"
        ordering = ["id"]

    def __str__(self):
        return f"{self.id} — {self.nama}"


class KeanggotaanPengguna(models.Model):
    """
    Relasi many-to-many antara User dan UMKM dengan atribut tambahan.
    Satu user boleh terdaftar di lebih dari satu UMKM; pasangan user+umkm unik.
    Scope query API: KeanggotaanPengguna.objects.filter(user=request.user, aktif=True)
    """

    PERAN_CHOICES = [
        ("pemilik", "Pemilik"),
        ("operator", "Operator"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="keanggotaan",
    )
    umkm = models.ForeignKey(
        UMKM,
        on_delete=models.CASCADE,
        related_name="anggota",
    )
    peran = models.CharField(max_length=20, choices=PERAN_CHOICES, default="operator")
    aktif = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Keanggotaan Pengguna"
        verbose_name_plural = "Keanggotaan Pengguna"
        constraints = [
            UniqueConstraint(
                fields=["user", "umkm"],
                name="unique_user_umkm",
            ),
        ]
        ordering = ["umkm", "user"]

    def __str__(self):
        return f"{self.user.username} @ {self.umkm_id} ({self.peran})"
