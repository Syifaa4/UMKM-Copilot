from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.umkm.models import UMKM, KeanggotaanPengguna
from apps.katalog.models import Produk

PRODUK_URL = "/api/katalog/produk/"


def buat_umkm(umkm_id="U001", nama="Toko Test"):
    return UMKM.objects.get_or_create(id=umkm_id, defaults={"nama": nama})[0]


def buat_user_dengan_keanggotaan(username, umkm, peran="operator"):
    user = User.objects.create_user(username=username, password="testpass123")
    KeanggotaanPengguna.objects.create(user=user, umkm=umkm, peran=peran, aktif=True)
    return user


def buat_produk(umkm, sku, nama="Kaos Test", kategori="Kaos",
                harga=50000, stok=10, aktif=True, warna="Hitam", ukuran="M"):
    return Produk.objects.create(
        umkm=umkm, sku=sku, nama_produk=nama, kategori=kategori,
        harga=Decimal(str(harga)), stok=stok, aktif=aktif,
        warna=warna, ukuran=ukuran,
    )


class KatalogAutentikasiTest(APITestCase):
    """Endpoint katalog wajib menggunakan token autentikasi."""

    def setUp(self):
        self.umkm = buat_umkm()
        self.user = buat_user_dengan_keanggotaan("user_auth", self.umkm)
        buat_produk(self.umkm, "SKU-AUTH-01")

    def test_tanpa_token_ditolak(self):
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dengan_token_berhasil(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_tanpa_keanggotaan_ditolak(self):
        user_tanpa_umkm = User.objects.create_user(
            username="user_no_umkm", password="testpass123"
        )
        self.client.force_authenticate(user=user_tanpa_umkm)
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_keanggotaan_nonaktif_ditolak(self):
        user = User.objects.create_user(username="user_inactive", password="testpass123")
        KeanggotaanPengguna.objects.create(
            user=user, umkm=self.umkm, peran="operator", aktif=False
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class KatalogIsolasiTenantTest(APITestCase):
    """Produk UMKM lain tidak boleh terlihat oleh user yang bukan anggotanya."""

    def setUp(self):
        self.umkm_a = buat_umkm("TA01", "Toko A")
        self.umkm_b = buat_umkm("TB01", "Toko B")
        self.user_a = buat_user_dengan_keanggotaan("user_a", self.umkm_a)
        self.user_b = buat_user_dengan_keanggotaan("user_b", self.umkm_b)
        self.produk_a = buat_produk(self.umkm_a, "SKU-A-01", nama="Produk Toko A")
        self.produk_b = buat_produk(self.umkm_b, "SKU-B-01", nama="Produk Toko B")

    def test_user_a_hanya_lihat_produk_umkm_a(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = [p["sku"] for p in response.data["results"]]
        self.assertIn("SKU-A-01", skus)
        self.assertNotIn("SKU-B-01", skus)

    def test_user_b_hanya_lihat_produk_umkm_b(self):
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = [p["sku"] for p in response.data["results"]]
        self.assertIn("SKU-B-01", skus)
        self.assertNotIn("SKU-A-01", skus)

    def test_detail_produk_umkm_lain_tidak_ditemukan(self):
        """User A tidak boleh mengakses detail produk UMKM B via ID langsung."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"{PRODUK_URL}{self.produk_b.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class KatalogPencarianTest(APITestCase):
    """Pencarian nama_produk dan SKU bekerja dengan benar."""

    def setUp(self):
        self.umkm = buat_umkm("U-CARI", "Toko Cari")
        self.user = buat_user_dengan_keanggotaan("user_cari", self.umkm)
        buat_produk(self.umkm, "SKU-K001", nama="Kaos Basic Cotton")
        buat_produk(self.umkm, "SKU-K002", nama="Kaos Premium Combed")
        buat_produk(self.umkm, "SKU-H001", nama="Hoodie Fleece", kategori="Hoodie")
        self.client.force_authenticate(user=self.user)

    def test_cari_nama_produk(self):
        response = self.client.get(PRODUK_URL, {"search": "kaos"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hasil = response.data["results"]
        self.assertEqual(len(hasil), 2)
        for p in hasil:
            self.assertIn("Kaos", p["nama_produk"])

    def test_cari_sku(self):
        response = self.client.get(PRODUK_URL, {"search": "SKU-H"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hasil = response.data["results"]
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["sku"], "SKU-H001")

    def test_cari_tidak_ditemukan(self):
        response = self.client.get(PRODUK_URL, {"search": "xyznotexist"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_filter_kategori(self):
        response = self.client.get(PRODUK_URL, {"kategori": "Hoodie"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hasil = response.data["results"]
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["kategori"], "Hoodie")

    def test_filter_aktif_false(self):
        buat_produk(self.umkm, "SKU-NONAKTIF", nama="Produk Nonaktif", aktif=False)
        response = self.client.get(PRODUK_URL, {"aktif": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        hasil = response.data["results"]
        self.assertEqual(len(hasil), 1)
        self.assertFalse(hasil[0]["aktif"])

    def test_default_hanya_produk_aktif(self):
        buat_produk(self.umkm, "SKU-NONAKTIF2", nama="Produk Nonaktif 2", aktif=False)
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for p in response.data["results"]:
            self.assertTrue(p["aktif"])


class KatalogPaginasiTest(APITestCase):
    """Respons katalog terpaginasi dengan benar."""

    def setUp(self):
        self.umkm = buat_umkm("U-PAGE", "Toko Paginasi")
        self.user = buat_user_dengan_keanggotaan("user_page", self.umkm)
        for i in range(25):
            buat_produk(self.umkm, f"SKU-PG-{i:03}", nama=f"Produk {i}")
        self.client.force_authenticate(user=self.user)

    def test_respons_terpaginasi(self):
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 20)

    def test_page_size_custom(self):
        response = self.client.get(PRODUK_URL, {"page_size": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)

    def test_total_count_benar(self):
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.data["count"], 25)


class KatalogMultiKeanggotaanTest(APITestCase):
    """User yang anggota dua UMKM melihat keduanya, tapi bukan UMKM ketiga."""

    def setUp(self):
        self.umkm_x = buat_umkm("MK-X1", "Toko X")
        self.umkm_y = buat_umkm("MK-Y1", "Toko Y")
        self.umkm_z = buat_umkm("MK-Z1", "Toko Z")
        # user_xy adalah anggota aktif UMKM X dan Y, bukan Z
        self.user_xy = User.objects.create_user(
            username="user_xy", password="testpass123"
        )
        KeanggotaanPengguna.objects.create(
            user=self.user_xy, umkm=self.umkm_x, peran="operator", aktif=True
        )
        KeanggotaanPengguna.objects.create(
            user=self.user_xy, umkm=self.umkm_y, peran="operator", aktif=True
        )
        self.produk_x = buat_produk(self.umkm_x, "SKU-MKX-01", nama="Produk X")
        self.produk_y = buat_produk(self.umkm_y, "SKU-MKY-01", nama="Produk Y")
        self.produk_z = buat_produk(self.umkm_z, "SKU-MKZ-01", nama="Produk Z")
        self.client.force_authenticate(user=self.user_xy)

    def test_user_melihat_produk_kedua_umkm(self):
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = [p["sku"] for p in response.data["results"]]
        self.assertIn("SKU-MKX-01", skus)
        self.assertIn("SKU-MKY-01", skus)

    def test_user_tidak_melihat_umkm_ketiga(self):
        response = self.client.get(PRODUK_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = [p["sku"] for p in response.data["results"]]
        self.assertNotIn("SKU-MKZ-01", skus)

    def test_detail_produk_umkm_ketiga_tidak_ditemukan(self):
        self.client.force_authenticate(user=self.user_xy)
        response = self.client.get(f"{PRODUK_URL}{self.produk_z.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class KatalogBypassUmkmIdTest(APITestCase):
    """Parameter ?umkm_id= tidak dapat digunakan untuk membaca data UMKM lain."""

    def setUp(self):
        self.umkm_milik = buat_umkm("BP-OWN", "Toko Sendiri")
        self.umkm_lain = buat_umkm("BP-OTH", "Toko Lain")
        self.user = buat_user_dengan_keanggotaan("user_bypass", self.umkm_milik)
        buat_produk(self.umkm_milik, "SKU-BP-OWN", nama="Produk Sendiri")
        buat_produk(self.umkm_lain, "SKU-BP-OTH", nama="Produk Lain")
        self.client.force_authenticate(user=self.user)

    def test_umkm_id_param_tidak_memperluas_akses(self):
        """?umkm_id=<umkm_lain> tidak membocorkan produk UMKM lain."""
        response = self.client.get(PRODUK_URL, {"umkm_id": self.umkm_lain.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = [p["sku"] for p in response.data["results"]]
        self.assertNotIn("SKU-BP-OTH", skus)

    def test_umkm_id_param_tidak_menyembunyikan_akses_sendiri(self):
        """?umkm_id= tidak mempengaruhi data UMKM milik sendiri."""
        response = self.client.get(PRODUK_URL, {"umkm_id": self.umkm_lain.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = [p["sku"] for p in response.data["results"]]
        self.assertIn("SKU-BP-OWN", skus)
