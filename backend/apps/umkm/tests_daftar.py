from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.katalog.models import KomponenHPP, Produk
from apps.umkm import services
from apps.umkm.models import UMKM, KeanggotaanPengguna

URL = "/api/auth/daftar/"
PASSWORD_KUAT = "Kopi-Susu-Gula-2026!"


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    UMKM_TEMPLATE_ID="TPL01",
)
class DaftarUMKMTest(APITestCase):
    def setUp(self):
        cache.clear()  # reset penghitung throttle antar tes

    def _payload(self, **ubah):
        data = {
            "username": "budi",
            "password": PASSWORD_KUAT,
            "nama_umkm": "Toko Budi",
        }
        data.update(ubah)
        return data

    def _buat_templat(self):
        tpl = UMKM.objects.create(id="TPL01", nama="Templat")
        p1 = Produk.objects.create(
            umkm=tpl, sku="K-001", nama_produk="Kaos Polos", kategori="Atasan",
            warna="Hitam", ukuran="M", harga=70000, stok=10,
        )
        Produk.objects.create(
            umkm=tpl, sku="K-002", nama_produk="Kaos Polos", kategori="Atasan",
            warna="Putih", ukuran="L", harga=70000, stok=5,
        )
        Produk.objects.create(
            umkm=tpl, sku="K-003", nama_produk="Produk Nonaktif",
            kategori="Atasan", harga=1000, stok=1, aktif=False,
        )
        KomponenHPP.objects.create(produk=p1, nama_komponen="Kain", biaya=30000)

    def test_sukses_membuat_akun_umkm_dan_keanggotaan(self):
        self._buat_templat()
        resp = self.client.post(URL, self._payload(), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("token", resp.data)
        self.assertNotIn("password", resp.data)
        user = User.objects.get(username="budi")
        k = KeanggotaanPengguna.objects.get(user=user)
        self.assertEqual(k.peran, "pemilik")
        self.assertTrue(k.aktif)
        self.assertEqual(k.umkm_id, resp.data["umkm"]["id"])
        self.assertEqual(k.umkm.nama, "Toko Budi")

    def test_katalog_contoh_disalin_hanya_produk_aktif(self):
        self._buat_templat()
        resp = self.client.post(URL, self._payload(), format="json")
        baru = resp.data["umkm"]["id"]
        self.assertEqual(resp.data["katalog_contoh"], 2)
        self.assertEqual(Produk.objects.filter(umkm_id=baru).count(), 2)
        self.assertEqual(
            KomponenHPP.objects.filter(produk__umkm_id=baru).count(), 1
        )
        # templat tidak berubah
        self.assertEqual(Produk.objects.filter(umkm_id="TPL01").count(), 3)

    def test_tanpa_templat_tetap_berhasil(self):
        resp = self.client.post(URL, self._payload(), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["katalog_contoh"], 0)

    def test_token_hasil_daftar_bisa_dipakai_dan_data_terisolasi(self):
        self._buat_templat()
        resp = self.client.post(URL, self._payload(), format="json")
        self.client.credentials(HTTP_AUTHORIZATION="Token " + resp.data["token"])
        daftar = self.client.get("/api/pesanan/pesanan/")
        self.assertEqual(daftar.status_code, 200)
        self.assertEqual(daftar.data["count"], 0)

    def test_username_duplikat_tanpa_beda_huruf_besar_kecil(self):
        User.objects.create_user(username="budi", password=PASSWORD_KUAT)
        resp = self.client.post(URL, self._payload(username="BUDI"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("username", resp.data)
        self.assertEqual(User.objects.count(), 1)

    def test_password_lemah_ditolak(self):
        resp = self.client.post(URL, self._payload(password="12345678"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.data)
        self.assertEqual(User.objects.count(), 0)

    def test_nama_umkm_wajib(self):
        resp = self.client.post(URL, self._payload(nama_umkm=""), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("nama_umkm", resp.data)

    def test_id_umkm_unik_dan_maksimal_10_karakter(self):
        a = self.client.post(URL, self._payload(username="a1"), format="json")
        b = self.client.post(URL, self._payload(username="b1"), format="json")
        self.assertNotEqual(a.data["umkm"]["id"], b.data["umkm"]["id"])
        self.assertLessEqual(len(a.data["umkm"]["id"]), 10)

    def test_gagal_di_tengah_membatalkan_semuanya(self):
        with mock.patch(
            "apps.umkm.services.salin_katalog_contoh",
            side_effect=RuntimeError("gagal"),
        ):
            with self.assertRaises(RuntimeError):
                services.daftar_umkm_baru(
                    username="sari", password=PASSWORD_KUAT, nama_umkm="Toko Sari"
                )
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(UMKM.objects.count(), 0)
        self.assertEqual(KeanggotaanPengguna.objects.count(), 0)

    def test_throttle_membatasi_10_pendaftaran_per_jam(self):
        for i in range(10):
            resp = self.client.post(
                URL, self._payload(username=f"user{i}"), format="json"
            )
            self.assertEqual(resp.status_code, 201)
        resp = self.client.post(URL, self._payload(username="user99"), format="json")
        self.assertEqual(resp.status_code, 429)