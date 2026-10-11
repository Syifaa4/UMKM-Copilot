"""
Utilities untuk scope query dan permission berbasis keanggotaan UMKM.

Semua view yang mengakses data tenant HARUS menggunakan get_umkm_ids_for_user()
untuk membatasi queryset. UMKM_ID dari frontend tidak boleh dipercaya sebagai
bukti otorisasi.
"""

from rest_framework.permissions import BasePermission

from apps.umkm.models import KeanggotaanPengguna


def get_umkm_ids_for_user(user):
    """
    Mengembalikan set UMKM ID yang boleh diakses user yang terautentikasi,
    berdasarkan keanggotaan aktif.

    Mengembalikan set kosong jika user tidak punya keanggotaan aktif apapun.
    Tidak pernah raise exception — pemanggil yang memutuskan respons jika kosong.
    """
    if not user or not user.is_authenticated:
        return set()
    return set(
        KeanggotaanPengguna.objects.filter(user=user, aktif=True)
        .values_list("umkm_id", flat=True)
    )


class HasUMKMMembership(BasePermission):
    """
    Mengizinkan akses hanya jika user terautentikasi dan memiliki
    setidaknya satu keanggotaan UMKM yang aktif.

    Digunakan sebagai permission class di ViewSet yang mengakses data tenant.
    View tetap harus memfilter queryset dengan get_umkm_ids_for_user().
    """

    message = "Anda tidak terdaftar sebagai anggota UMKM manapun."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return KeanggotaanPengguna.objects.filter(
            user=request.user, aktif=True
        ).exists()
