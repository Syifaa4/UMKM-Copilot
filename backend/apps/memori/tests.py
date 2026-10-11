from datetime import date

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.umkm.models import UMKM, KeanggotaanPengguna
from apps.memori.models import Memori

MEMORI_URL = "/api/memori/memori/"


def buat_umkm(umkm_id="U001", nama="Toko Test"):
    return UMKM.objects.get_or_create(id=umkm_id, defaults={"nama": nama})[0]


def buat_user_dengan_keanggotaan(username, umkm, peran="operator"):
    user = User.objects.create_user(username=username, password="testpass123")
    KeanggotaanPengguna.objects.create(user=user, umkm=umkm, peran=peran, aktif=True)
    return user


def buat_memori(umkm, id_memori, istilah, makna,
                status=Memori.STATUS_DISETUJUI, versi=1,
                makna_sebelumnya=""):
    return Memori.objects.create(
        umkm=umkm,
        id_memori=id_memori,
        istilah=istilah,
        makna=makna,
        sumber="test",
        status=status,
        versi=versi,
        makna_sebelumnya=makna_sebelumnya,
        dibuat_pada=date(2026, 10, 1),
        disetujui_oleh="Admin",
        tindakan="aktif",
        catatan="",
    )


class MemoriAutentikasiTest(APITestCase):
    """Endpoint memori wajib menggunakan token autentikasi."""

    def setUp(self):
        self.umkm = buat_umkm()
        self.user = buat_user_dengan_keanggotaan("user_mem_auth", self.umkm)
        buat_memori(self.umkm, "MEM-T01", "premium", "Kaos Premium")

    def test_tanpa_token_ditolak(self):
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dengan_token_berhasil(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_tanpa_keanggotaan_ditolak(self):
        user_tanpa_umkm = User.objects.create_user(
            username="user_mem_no_umkm", password="testpass123"
        )
        self.client.force_authenticate(user=user_tanpa_umkm)
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_keanggotaan_nonaktif_ditolak(self):
        user = User.objects.create_user(
            username="user_mem_inactive", password="testpass123"
        )
        KeanggotaanPengguna.objects.create(
            user=user, umkm=self.umkm, peran="operator", aktif=False
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MemoriFilterStatusTest(APITestCase):
    """Hanya memori DISETUJUI yang boleh dikembalikan."""

    def setUp(self):
        self.umkm = buat_umkm("U-MEM", "Toko Memori")
        self.user = buat_user_dengan_keanggotaan("user_mem_filter", self.umkm)
        # Satu DISETUJUI — harus muncul
        buat_memori(self.umkm, "MEM-F01", "premium",
                    "Kaos Premium Cotton", status=Memori.STATUS_DISETUJUI, versi=2)
        # Satu DIGANTIKAN — tidak boleh muncul
        buat_memori(self.umkm, "MEM-F02", "basic",
                    "Kaos Basic Lama", status=Memori.STATUS_DIGANTIKAN, versi=1)
        # Satu PENDING — tidak boleh muncul
        buat_memori(self.umkm, "MEM-F03", "oversize",
                    "Kaos Oversize", status=Memori.STATUS_PENDING, versi=1)
        self.client.force_authenticate(user=self.user)

    def test_hanya_disetujui_dikembalikan(self):
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hasil = response.data["results"]
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["status"], Memori.STATUS_DISETUJUI)
        self.assertEqual(hasil[0]["id_memori"], "MEM-F01")

    def test_status_digantikan_tidak_muncul(self):
        response = self.client.get(MEMORI_URL)
        id_memori_list = [m["id_memori"] for m in response.data["results"]]
        self.assertNotIn("MEM-F02", id_memori_list)

    def test_status_pending_tidak_muncul(self):
        response = self.client.get(MEMORI_URL)
        id_memori_list = [m["id_memori"] for m in response.data["results"]]
        self.assertNotIn("MEM-F03", id_memori_list)

    def test_filter_status_dari_query_param_diabaikan(self):
        """Query param ?status= tidak boleh mengubah filter DISETUJUI."""
        response = self.client.get(MEMORI_URL, {"status": "DIGANTIKAN"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Tetap hanya mengembalikan DISETUJUI
        for m in response.data["results"]:
            self.assertEqual(m["status"], Memori.STATUS_DISETUJUI)


class MemoriIsolasiTenantTest(APITestCase):
    """Memori UMKM lain tidak boleh terlihat."""

    def setUp(self):
        self.umkm_a = buat_umkm("MA01", "Toko Mem A")
        self.umkm_b = buat_umkm("MB01", "Toko Mem B")
        self.user_a = buat_user_dengan_keanggotaan("user_mem_a", self.umkm_a)
        self.user_b = buat_user_dengan_keanggotaan("user_mem_b", self.umkm_b)
        self.mem_a = buat_memori(self.umkm_a, "MEM-A01", "premium", "Produk A")
        self.mem_b = buat_memori(self.umkm_b, "MEM-B01", "spesial", "Produk B")

    def test_user_a_hanya_lihat_memori_umkm_a(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id_memori"] for m in response.data["results"]]
        self.assertIn("MEM-A01", ids)
        self.assertNotIn("MEM-B01", ids)

    def test_detail_memori_umkm_lain_tidak_ditemukan(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"{MEMORI_URL}{self.mem_b.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MemoriFilterIstilahTest(APITestCase):
    """Filter ?istilah= bekerja dengan benar."""

    def setUp(self):
        self.umkm = buat_umkm("U-IST", "Toko Istilah")
        self.user = buat_user_dengan_keanggotaan("user_istilah", self.umkm)
        buat_memori(self.umkm, "MEM-I01", "premium", "Kaos Premium")
        buat_memori(self.umkm, "MEM-I02", "basic", "Kaos Basic")
        self.client.force_authenticate(user=self.user)

    def test_filter_istilah(self):
        response = self.client.get(MEMORI_URL, {"istilah": "premium"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hasil = response.data["results"]
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["istilah"], "premium")

    def test_filter_istilah_case_insensitive(self):
        response = self.client.get(MEMORI_URL, {"istilah": "PREMIUM"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_filter_istilah_tidak_ditemukan(self):
        response = self.client.get(MEMORI_URL, {"istilah": "tidakada"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


class MemoriMultiKeanggotaanTest(APITestCase):
    """User yang anggota dua UMKM melihat keduanya, tapi bukan UMKM ketiga."""

    def setUp(self):
        self.umkm_x = buat_umkm("MM-X1", "Toko Mem X")
        self.umkm_y = buat_umkm("MM-Y1", "Toko Mem Y")
        self.umkm_z = buat_umkm("MM-Z1", "Toko Mem Z")
        self.user_xy = User.objects.create_user(
            username="user_mem_xy", password="testpass123"
        )
        KeanggotaanPengguna.objects.create(
            user=self.user_xy, umkm=self.umkm_x, peran="operator", aktif=True
        )
        KeanggotaanPengguna.objects.create(
            user=self.user_xy, umkm=self.umkm_y, peran="operator", aktif=True
        )
        self.mem_x = buat_memori(self.umkm_x, "MEM-MX01", "premium", "Produk X")
        self.mem_y = buat_memori(self.umkm_y, "MEM-MY01", "spesial", "Produk Y")
        self.mem_z = buat_memori(self.umkm_z, "MEM-MZ01", "eksklusif", "Produk Z")
        self.client.force_authenticate(user=self.user_xy)

    def test_user_melihat_memori_kedua_umkm(self):
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id_memori"] for m in response.data["results"]]
        self.assertIn("MEM-MX01", ids)
        self.assertIn("MEM-MY01", ids)

    def test_user_tidak_melihat_umkm_ketiga(self):
        response = self.client.get(MEMORI_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id_memori"] for m in response.data["results"]]
        self.assertNotIn("MEM-MZ01", ids)

    def test_detail_memori_umkm_ketiga_tidak_ditemukan(self):
        response = self.client.get(f"{MEMORI_URL}{self.mem_z.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MemoriBypassUmkmIdTest(APITestCase):
    """Parameter ?umkm_id= tidak dapat digunakan untuk membaca data UMKM lain."""

    def setUp(self):
        self.umkm_milik = buat_umkm("MB-OWN", "Toko Mem Sendiri")
        self.umkm_lain = buat_umkm("MB-OTH", "Toko Mem Lain")
        self.user = buat_user_dengan_keanggotaan("user_mem_bypass", self.umkm_milik)
        buat_memori(self.umkm_milik, "MEM-MB-OWN", "lokal", "Produk Sendiri")
        buat_memori(self.umkm_lain, "MEM-MB-OTH", "asing", "Produk Lain")
        self.client.force_authenticate(user=self.user)

    def test_umkm_id_param_tidak_memperluas_akses(self):
        """?umkm_id=<umkm_lain> tidak membocorkan memori UMKM lain."""
        response = self.client.get(MEMORI_URL, {"umkm_id": self.umkm_lain.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id_memori"] for m in response.data["results"]]
        self.assertNotIn("MEM-MB-OTH", ids)

    def test_umkm_id_param_tidak_menyembunyikan_akses_sendiri(self):
        """?umkm_id= tidak mempengaruhi memori UMKM milik sendiri."""
        response = self.client.get(MEMORI_URL, {"umkm_id": self.umkm_lain.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [m["id_memori"] for m in response.data["results"]]
        self.assertIn("MEM-MB-OWN", ids)
