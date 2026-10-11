"""Logika pendaftaran UMKM baru."""

import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from apps.katalog.models import KomponenHPP, Produk
from apps.umkm.models import UMKM, KeanggotaanPengguna


def _buat_id_umkm() -> str:
    """ID acak 'U' + 8 hex (9 karakter, batas model 10)."""
    for _ in range(10):
        kandidat = "U" + secrets.token_hex(4).upper()
        if not UMKM.objects.filter(pk=kandidat).exists():
            return kandidat
    raise RuntimeError("Gagal membuat ID UMKM unik.")


def salin_katalog_contoh(umkm: UMKM) -> int:
    """
    Salin produk aktif (dan komponen HPP-nya) dari UMKM templat ke umkm baru.
    Templat diambil dari settings.UMKM_TEMPLATE_ID (default 'U001').
    Jika templat tidak ada atau kosong, tidak ada yang disalin.
    Mengembalikan jumlah produk yang disalin.
    """
    id_templat = getattr(settings, "UMKM_TEMPLATE_ID", "U001")
    produk_templat = list(Produk.objects.filter(umkm_id=id_templat, aktif=True))
    if not produk_templat:
        return 0

    produk_baru = Produk.objects.bulk_create(
        [
            Produk(
                umkm=umkm,
                sku=p.sku,
                nama_produk=p.nama_produk,
                kategori=p.kategori,
                warna=p.warna,
                ukuran=p.ukuran,
                harga=p.harga,
                stok=p.stok,
                aktif=True,
            )
            for p in produk_templat
        ]
    )
    # Petakan SKU -> produk baru lewat query ulang (aman untuk semua database)
    peta_sku = {p.sku: p for p in Produk.objects.filter(umkm=umkm)}

    komponen_baru = []
    for lama in produk_templat:
        for k in KomponenHPP.objects.filter(produk=lama):
            komponen_baru.append(
                KomponenHPP(
                    produk=peta_sku[lama.sku],
                    nama_komponen=k.nama_komponen,
                    biaya=k.biaya,
                    satuan=k.satuan,
                    catatan=k.catatan,
                )
            )
    KomponenHPP.objects.bulk_create(komponen_baru)
    return len(produk_baru)


@transaction.atomic
def daftar_umkm_baru(*, username, password, nama_umkm, email=""):
    """
    Buat akun + UMKM + keanggotaan (pemilik) + token + katalog contoh
    dalam satu transaksi. Jika ada yang gagal, semuanya dibatalkan.
    Mengembalikan (user, umkm, token_key, jumlah_produk_contoh).
    """
    user = User.objects.create_user(username=username, password=password, email=email)
    umkm = UMKM.objects.create(id=_buat_id_umkm(), nama=nama_umkm.strip())
    KeanggotaanPengguna.objects.create(
        user=user, umkm=umkm, peran="pemilik", aktif=True
    )
    token, _ = Token.objects.get_or_create(user=user)
    jumlah = salin_katalog_contoh(umkm)
    return user, umkm, token.key, jumlah