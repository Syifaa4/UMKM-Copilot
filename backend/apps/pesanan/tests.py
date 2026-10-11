"""
Test suite untuk API pesanan.

Cakupan:
- Autentikasi dan pengguna tanpa keanggotaan aktif
- Isolasi tenant (list, detail, semua endpoint tulis)
- Pembuatan pesanan dan keunikan nomor pesanan
- Transisi status valid dan tidak valid
- Verifikasi item dan validasi harga
- Konfirmasi: hpp_snapshot, transaksi penjualan, rollback jika gagal
- Pencegahan transaksi penjualan ganda
- Pembatalan sebelum dan sesudah konfirmasi
- Pencegahan koreksi pembatalan ganda
- Endpoint tidak menyediakan DELETE
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.umkm.models import UMKM, KeanggotaanPengguna
from apps.katalog.models import KomponenHPP, Produk
from apps.keuangan.models import Transaksi
from apps.pesanan.models import ItemPesanan, Pesanan

PESANAN_URL = "/api/pesanan/pesanan/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def buat_umkm(umkm_id="U001", nama="Toko Test"):
    return UMKM.objects.get_or_create(id=umkm_id, defaults={"nama": nama})[0]


def buat_user_dengan_keanggotaan(username, umkm, peran="operator"):
    user = User.objects.create_user(username=username, password="testpass123")
    KeanggotaanPengguna.objects.create(user=user, umkm=umkm, peran=peran, aktif=True)
    return user


def buat_produk(umkm, sku="SKU001", nama="Produk Test", harga=50000):
    return Produk.objects.create(
        umkm=umkm, sku=sku, nama_produk=nama, kategori="Kaos",
        harga=Decimal(str(harga)), stok=10, aktif=True,
    )


def buat_produk_dengan_hpp(umkm, sku="SKU-HPP", nama="Produk HPP",
                            harga=100000, hpp_per_unit=40000):
    produk = buat_produk(umkm, sku=sku, nama=nama, harga=harga)
    KomponenHPP.objects.create(
        produk=produk,
        nama_komponen="Bahan",
        biaya=Decimal(str(hpp_per_unit)),
    )
    return produk


def buat_pesanan_draft(umkm, nama_pelanggan="Budi", teks="2 kaos hitam M"):
    from apps.pesanan.services import buat_pesanan
    return buat_pesanan(umkm=umkm, nama_pelanggan=nama_pelanggan,
                        teks_chat_asli=teks)


def tambah_item(pesanan, teks="2 kaos hitam M",
                status_item=ItemPesanan.STATUS_TIDAK_DITEMUKAN,
                produk=None, harga_satuan=None, subtotal=None):
    return ItemPesanan.objects.create(
        pesanan=pesanan,
        teks_asli=teks,
        status_item=status_item,
        produk=produk,
        harga_satuan=harga_satuan,
        subtotal=subtotal,
        kuantitas=2,
    )


def pesanan_siap_konfirmasi(umkm, produk):
    """Buat pesanan MENUNGGU_REVIEW dengan satu item terverifikasi."""
    from apps.pesanan.services import ajukan_review
    p = buat_pesanan_draft(umkm)
    tambah_item(
        p, teks="2 kaos", status_item=ItemPesanan.STATUS_DIKONFIRMASI,
        produk=produk, harga_satuan=produk.harga,
        subtotal=produk.harga * 2,
    )
    ajukan_review(p)
    return p


# ---------------------------------------------------------------------------
# Autentikasi
# ---------------------------------------------------------------------------

class PesananAutentikasiTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("PA01")
        self.user = buat_user_dengan_keanggotaan("user_pa", self.umkm)

    def test_tanpa_token_ditolak(self):
        response = self.client.get(PESANAN_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_tanpa_keanggotaan_ditolak(self):
        user = User.objects.create_user(username="user_no_umkm_p", password="x")
        self.client.force_authenticate(user=user)
        response = self.client.get(PESANAN_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_keanggotaan_nonaktif_ditolak(self):
        user = User.objects.create_user(username="user_inactive_p", password="x")
        KeanggotaanPengguna.objects.create(
            user=user, umkm=self.umkm, peran="operator", aktif=False
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(PESANAN_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dengan_keanggotaan_aktif_berhasil(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(PESANAN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Isolasi Tenant
# ---------------------------------------------------------------------------

class PesananIsolasiTenantTest(APITestCase):

    def setUp(self):
        self.umkm_a = buat_umkm("IT-A1", "Toko A")
        self.umkm_b = buat_umkm("IT-B1", "Toko B")
        self.user_a = buat_user_dengan_keanggotaan("user_it_a", self.umkm_a)
        self.user_b = buat_user_dengan_keanggotaan("user_it_b", self.umkm_b)
        self.pesanan_a = buat_pesanan_draft(self.umkm_a, "Pelanggan A")
        self.pesanan_b = buat_pesanan_draft(self.umkm_b, "Pelanggan B")

    def test_list_hanya_pesanan_sendiri(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get(PESANAN_URL)
        ids = [p["id"] for p in resp.data["results"]]
        self.assertIn(self.pesanan_a.id, ids)
        self.assertNotIn(self.pesanan_b.id, ids)

    def test_detail_pesanan_umkm_lain_404(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get(f"{PESANAN_URL}{self.pesanan_b.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_ajukan_review_pesanan_umkm_lain_404(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.post(
            f"{PESANAN_URL}{self.pesanan_b.id}/ajukan-review/"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_konfirmasi_pesanan_umkm_lain_404(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.post(
            f"{PESANAN_URL}{self.pesanan_b.id}/konfirmasi/"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_batalkan_pesanan_umkm_lain_404(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.post(
            f"{PESANAN_URL}{self.pesanan_b.id}/batalkan/"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Pembuatan Pesanan
# ---------------------------------------------------------------------------

class PesananBuatTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("BP01")
        self.user = buat_user_dengan_keanggotaan("user_bp", self.umkm)
        self.client.force_authenticate(user=self.user)

    def test_buat_pesanan_berhasil(self):
        resp = self.client.post(PESANAN_URL, {
            "nama_pelanggan": "Andi",
            "teks_chat_asli": "2 kaos hitam M",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], Pesanan.STATUS_DRAFT)
        self.assertEqual(resp.data["nama_pelanggan"], "Andi")
        self.assertTrue(resp.data["nomor_pesanan"].startswith("ORD-BP01-"))

    def test_nomor_pesanan_unik_tiap_buat(self):
        resp1 = self.client.post(PESANAN_URL, {
            "nama_pelanggan": "X", "teks_chat_asli": "a",
        })
        resp2 = self.client.post(PESANAN_URL, {
            "nama_pelanggan": "Y", "teks_chat_asli": "b",
        })
        self.assertNotEqual(
            resp1.data["nomor_pesanan"], resp2.data["nomor_pesanan"]
        )

    def test_buat_tanpa_nama_pelanggan_ditolak(self):
        resp = self.client.post(PESANAN_URL, {"teks_chat_asli": "test"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buat_tanpa_teks_chat_ditolak(self):
        resp = self.client.post(PESANAN_URL, {"nama_pelanggan": "Budi"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nomor_pesanan_tidak_diterima_dari_user(self):
        """nomor_pesanan dari payload diabaikan — selalu di-generate server."""
        resp = self.client.post(PESANAN_URL, {
            "nama_pelanggan": "Cici",
            "teks_chat_asli": "test",
            "nomor_pesanan": "NOMOR-PALSU-999",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(resp.data["nomor_pesanan"], "NOMOR-PALSU-999")

    def test_delete_tidak_tersedia(self):
        p = buat_pesanan_draft(self.umkm)
        resp = self.client.delete(f"{PESANAN_URL}{p.id}/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# ---------------------------------------------------------------------------
# Transisi Status
# ---------------------------------------------------------------------------

class PesananTransisiTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("TR01")
        self.user = buat_user_dengan_keanggotaan("user_tr", self.umkm)
        self.produk = buat_produk(self.umkm, "SKU-TR-01")
        self.client.force_authenticate(user=self.user)

    def test_draft_ke_menunggu_review(self):
        p = buat_pesanan_draft(self.umkm)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/ajukan-review/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], Pesanan.STATUS_MENUNGGU_REVIEW)

    def test_transisi_tidak_valid_ditolak(self):
        """DRAFT tidak bisa langsung ke DIKONFIRMASI."""
        p = buat_pesanan_draft(self.umkm)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Transisi", resp.data["detail"])

    def test_selesai_tidak_valid_dari_draft(self):
        p = buat_pesanan_draft(self.umkm)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/selesai/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dibatalkan_tidak_bisa_diubah_lagi(self):
        p = buat_pesanan_draft(self.umkm)
        self.client.post(f"{PESANAN_URL}{p.id}/ajukan-review/")
        self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        resp = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Verifikasi Item
# ---------------------------------------------------------------------------

class VerifikasiItemTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("VI01")
        self.umkm_b = buat_umkm("VI-B1", "Toko Lain")
        self.user = buat_user_dengan_keanggotaan("user_vi", self.umkm)
        self.produk = buat_produk(self.umkm, "SKU-VI-01", harga=60000)
        self.produk_lain = buat_produk(self.umkm_b, "SKU-VI-OTH", harga=99000)
        self.client.force_authenticate(user=self.user)

    def _pesanan_dengan_item_ambigu(self):
        from apps.pesanan.services import ajukan_review
        p = buat_pesanan_draft(self.umkm)
        item = tambah_item(p, status_item=ItemPesanan.STATUS_AMBIGU)
        ajukan_review(p)
        return p, item

    def test_verifikasi_item_berhasil(self):
        p, item = self._pesanan_dengan_item_ambigu()
        resp = self.client.patch(
            f"{PESANAN_URL}{p.id}/items/{item.id}/verifikasi/",
            {"produk_id": self.produk.id, "kuantitas": 3},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.status_item, ItemPesanan.STATUS_DIKONFIRMASI)
        self.assertEqual(item.harga_satuan, Decimal("60000"))
        self.assertEqual(item.subtotal, Decimal("180000"))

    def test_verifikasi_item_produk_umkm_lain_404(self):
        """Produk dari UMKM lain tidak boleh digunakan."""
        p, item = self._pesanan_dengan_item_ambigu()
        resp = self.client.patch(
            f"{PESANAN_URL}{p.id}/items/{item.id}/verifikasi/",
            {"produk_id": self.produk_lain.id, "kuantitas": 1},
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_verifikasi_kuantitas_nol_ditolak(self):
        p, item = self._pesanan_dengan_item_ambigu()
        resp = self.client.patch(
            f"{PESANAN_URL}{p.id}/items/{item.id}/verifikasi/",
            {"produk_id": self.produk.id, "kuantitas": 0},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verifikasi_item_pesanan_draft_ditolak(self):
        """Verifikasi hanya boleh saat MENUNGGU_REVIEW."""
        p = buat_pesanan_draft(self.umkm)
        item = tambah_item(p, status_item=ItemPesanan.STATUS_AMBIGU)
        resp = self.client.patch(
            f"{PESANAN_URL}{p.id}/items/{item.id}/verifikasi/",
            {"produk_id": self.produk.id, "kuantitas": 1},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("MENUNGGU_REVIEW", resp.data["detail"])


# ---------------------------------------------------------------------------
# Konfirmasi dan HPP Snapshot
# ---------------------------------------------------------------------------

class KonfirmasiPesananTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("KP01")
        self.user = buat_user_dengan_keanggotaan("user_kp", self.umkm)
        self.produk = buat_produk_dengan_hpp(
            self.umkm, sku="SKU-KP-01", harga=100000, hpp_per_unit=40000
        )
        self.client.force_authenticate(user=self.user)

    def test_konfirmasi_berhasil(self):
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], Pesanan.STATUS_DIKONFIRMASI)

    def test_hpp_snapshot_diisi_saat_konfirmasi(self):
        """hpp_snapshot = SUM(komponen.biaya) × kuantitas = 40000 × 2 = 80000."""
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        item = p.item_pesanan.first()
        item.refresh_from_db()
        self.assertEqual(item.hpp_snapshot, Decimal("80000.00"))

    def test_hpp_snapshot_nol_jika_produk_tanpa_komponen(self):
        """Produk tanpa KomponenHPP → hpp_snapshot = 0.00, bukan error."""
        produk_tanpa_hpp = buat_produk(self.umkm, sku="SKU-NO-HPP", harga=50000)
        p = pesanan_siap_konfirmasi(self.umkm, produk_tanpa_hpp)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item = p.item_pesanan.first()
        item.refresh_from_db()
        self.assertEqual(item.hpp_snapshot, Decimal("0.00"))

    def test_transaksi_penjualan_dibuat_saat_konfirmasi(self):
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        transaksi = Transaksi.objects.filter(
            pesanan=p, kategori=Transaksi.KATEGORI_PENJUALAN
        )
        self.assertEqual(transaksi.count(), 1)
        # Jumlah = harga × kuantitas = 100000 × 2 = 200000
        self.assertEqual(transaksi.first().jumlah, Decimal("200000.00"))

    def test_konfirmasi_gagal_jika_ada_item_ambigu(self):
        from apps.pesanan.services import ajukan_review
        p = buat_pesanan_draft(self.umkm)
        tambah_item(p, status_item=ItemPesanan.STATUS_AMBIGU)
        ajukan_review(p)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("belum teridentifikasi", resp.data["detail"])

    def test_konfirmasi_gagal_jika_item_tanpa_harga(self):
        from apps.pesanan.services import ajukan_review
        p = buat_pesanan_draft(self.umkm)
        tambah_item(
            p, status_item=ItemPesanan.STATUS_DIKONFIRMASI,
            produk=self.produk,
            # harga_satuan dan subtotal sengaja None
        )
        ajukan_review(p)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("belum memiliki harga", resp.data["detail"])

    def test_konfirmasi_tanpa_item_ditolak(self):
        from apps.pesanan.services import ajukan_review
        p = buat_pesanan_draft(self.umkm)
        ajukan_review(p)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("item", resp.data["detail"])


# ---------------------------------------------------------------------------
# Pencegahan Transaksi Ganda
# ---------------------------------------------------------------------------

class TransaksiGandaTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("TG01")
        self.user = buat_user_dengan_keanggotaan("user_tg", self.umkm)
        self.produk = buat_produk(self.umkm, "SKU-TG-01", harga=50000)
        self.client.force_authenticate(user=self.user)

    def test_konfirmasi_kedua_kali_ditolak(self):
        """Mengkonfirmasi pesanan yang sudah DIKONFIRMASI harus ditolak."""
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        # Pesanan sekarang DIKONFIRMASI — konfirmasi lagi harus gagal (transisi)
        resp2 = self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transaksi_penjualan_hanya_satu(self):
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        count = Transaksi.objects.filter(
            pesanan=p, kategori=Transaksi.KATEGORI_PENJUALAN
        ).count()
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# Rollback Konfirmasi
# ---------------------------------------------------------------------------

class RollbackKonfirmasiTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("RB01")
        self.user = buat_user_dengan_keanggotaan("user_rb", self.umkm)
        self.client.force_authenticate(user=self.user)

    def test_konfirmasi_gagal_tidak_membuat_transaksi(self):
        """Jika konfirmasi gagal (item ambigu), tidak boleh ada transaksi."""
        from apps.pesanan.services import ajukan_review
        p = buat_pesanan_draft(self.umkm)
        tambah_item(p, status_item=ItemPesanan.STATUS_AMBIGU)
        ajukan_review(p)

        transaksi_sebelum = Transaksi.objects.filter(pesanan=p).count()
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        transaksi_sesudah = Transaksi.objects.filter(pesanan=p).count()

        self.assertEqual(transaksi_sebelum, transaksi_sesudah)
        p.refresh_from_db()
        self.assertEqual(p.status, Pesanan.STATUS_MENUNGGU_REVIEW)

    def test_konfirmasi_gagal_hpp_snapshot_tidak_tersimpan(self):
        """Jika konfirmasi gagal, hpp_snapshot item tidak berubah dari None."""
        from apps.pesanan.services import ajukan_review
        produk_valid = buat_produk_dengan_hpp(
            self.umkm, sku="SKU-RB-V", harga=100000, hpp_per_unit=30000
        )
        p = buat_pesanan_draft(self.umkm)
        # Item valid + item ambigu — konfirmasi harus gagal
        item_valid = tambah_item(
            p, teks="item valid",
            status_item=ItemPesanan.STATUS_DIKONFIRMASI,
            produk=produk_valid,
            harga_satuan=produk_valid.harga,
            subtotal=produk_valid.harga * 2,
        )
        tambah_item(p, teks="item ambigu", status_item=ItemPesanan.STATUS_AMBIGU)
        ajukan_review(p)

        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        item_valid.refresh_from_db()
        # hpp_snapshot tidak boleh terisi karena konfirmasi rollback
        self.assertIsNone(item_valid.hpp_snapshot)


# ---------------------------------------------------------------------------
# Pembatalan
# ---------------------------------------------------------------------------

class PembatalanTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("PB01")
        self.user = buat_user_dengan_keanggotaan("user_pb", self.umkm)
        self.produk = buat_produk(self.umkm, "SKU-PB-01", harga=75000)
        self.client.force_authenticate(user=self.user)

    def test_batalkan_dari_draft_berhasil_tanpa_transaksi(self):
        p = buat_pesanan_draft(self.umkm)
        resp = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], Pesanan.STATUS_DIBATALKAN)
        self.assertEqual(Transaksi.objects.filter(pesanan=p).count(), 0)

    def test_batalkan_dari_menunggu_review_tanpa_transaksi(self):
        p = buat_pesanan_draft(self.umkm)
        self.client.post(f"{PESANAN_URL}{p.id}/ajukan-review/")
        resp = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Transaksi.objects.filter(pesanan=p).count(), 0)

    def test_batalkan_dari_dikonfirmasi_membuat_koreksi(self):
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        resp = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        koreksi = Transaksi.objects.filter(
            pesanan=p, kategori=Transaksi.KATEGORI_KOREKSI_PEMBATALAN
        )
        self.assertEqual(koreksi.count(), 1)
        penjualan = Transaksi.objects.filter(
            pesanan=p, kategori=Transaksi.KATEGORI_PENJUALAN
        ).first()
        self.assertEqual(koreksi.first().jumlah, penjualan.jumlah)

    def test_batalkan_dari_selesai_membuat_koreksi(self):
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.client.post(f"{PESANAN_URL}{p.id}/selesai/")
        resp = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Transaksi.objects.filter(
                pesanan=p, kategori=Transaksi.KATEGORI_KOREKSI_PEMBATALAN
            ).count(), 1
        )

    def test_batalkan_dua_kali_ditolak(self):
        p = buat_pesanan_draft(self.umkm)
        self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        resp = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_koreksi_pembatalan_tidak_ganda(self):
        """Pembatalan ganda pada pesanan dikonfirmasi tidak membuat 2 koreksi."""
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        # Percobaan kedua harus ditolak di guard transisi (status sudah DIBATALKAN)
        resp2 = self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            Transaksi.objects.filter(
                pesanan=p, kategori=Transaksi.KATEGORI_KOREKSI_PEMBATALAN
            ).count(), 1
        )

    def test_transaksi_asli_tidak_dihapus_saat_batalkan(self):
        """Pembatalan tidak menghapus transaksi penjualan asli."""
        p = pesanan_siap_konfirmasi(self.umkm, self.produk)
        self.client.post(f"{PESANAN_URL}{p.id}/konfirmasi/")
        self.client.post(f"{PESANAN_URL}{p.id}/batalkan/")
        self.assertEqual(
            Transaksi.objects.filter(
                pesanan=p, kategori=Transaksi.KATEGORI_PENJUALAN
            ).count(), 1
        )


# ---------------------------------------------------------------------------
# Filter Status
# ---------------------------------------------------------------------------

class PesananFilterStatusTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("FS01")
        self.user = buat_user_dengan_keanggotaan("user_fs", self.umkm)
        self.p_draft = buat_pesanan_draft(self.umkm, "A")
        self.p_review = buat_pesanan_draft(self.umkm, "B")
        from apps.pesanan.services import ajukan_review
        ajukan_review(self.p_review)
        self.client.force_authenticate(user=self.user)

    def test_filter_status_draft(self):
        resp = self.client.get(PESANAN_URL, {"status": "DRAFT"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for p in resp.data["results"]:
            self.assertEqual(p["status"], Pesanan.STATUS_DRAFT)

    def test_filter_status_menunggu_review(self):
        resp = self.client.get(PESANAN_URL, {"status": "MENUNGGU_REVIEW"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in resp.data["results"]]
        self.assertIn(self.p_review.id, ids)
        self.assertNotIn(self.p_draft.id, ids)
