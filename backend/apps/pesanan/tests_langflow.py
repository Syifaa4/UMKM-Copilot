"""
Test suite untuk integrasi Langflow.

Cakupan:
- parse_respons_langflow: JSON biasa, JSON dalam code fence, respons tidak valid
- build_katalog_csv / build_memori_csv: output CSV dari database
- LangflowClient: timeout, HTTP error, koneksi gagal (semua via mock)
- services.proses_langflow: item valid, item ambigu, SKU tidak di katalog
- Harga selalu dari database — tidak dari AI
- Isolasi tenant: pesanan UMKM lain tidak dapat diproses
- Kegagalan Langflow tidak meninggalkan item tersimpan sebagian
- Guard status: hanya pesanan DRAFT yang dapat diproses
- Guard idempoten: pesanan yang sudah ada item tidak dapat diproses ulang
- Endpoint POST /api/pesanan/pesanan/{id}/proses-langflow/
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.katalog.models import Produk
from apps.keuangan.models import Transaksi
from apps.memori.models import Memori
from apps.pesanan.langflow_client import (
    HasilLangflow,
    ItemParsed,
    LangflowClient,
    LangflowError,
    LangflowResponsInvalidError,
    LangflowTimeoutError,
    build_katalog_csv,
    build_memori_csv,
    parse_respons_langflow,
)
from apps.pesanan.models import ItemPesanan, Pesanan
from apps.pesanan.services import proses_langflow
from apps.umkm.models import UMKM, KeanggotaanPengguna

PROSES_URL = "/api/pesanan/pesanan/{id}/proses-langflow/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def buat_umkm(umkm_id="LF01", nama="Toko Langflow Test"):
    return UMKM.objects.get_or_create(id=umkm_id, defaults={"nama": nama})[0]


def buat_user_dengan_keanggotaan(username, umkm, peran="operator"):
    user = User.objects.create_user(username=username, password="testpass123")
    KeanggotaanPengguna.objects.create(user=user, umkm=umkm, peran=peran, aktif=True)
    return user


def buat_produk(umkm, sku="SKU-LF-01", nama="Kaos Test", harga=65000, warna="Hitam", ukuran="M"):
    return Produk.objects.create(
        umkm=umkm, sku=sku, nama_produk=nama, kategori="Kaos",
        warna=warna, ukuran=ukuran,
        harga=Decimal(str(harga)), stok=10, aktif=True,
    )


def buat_pesanan_draft(umkm, teks="2 kaos hitam M"):
    from apps.pesanan.services import buat_pesanan
    return buat_pesanan(umkm=umkm, nama_pelanggan="Pelanggan Test",
                        teks_chat_asli=teks)


def buat_hasil_langflow(items=None, status_flow="SEBAGIAN_VALID"):
    """Helper: buat HasilLangflow mock dengan daftar ItemParsed."""
    return HasilLangflow(
        status_flow=status_flow,
        items=items or [],
        masalah=[],
        teks_mentah="",
    )


def respons_langflow_raw(teks_json: str) -> dict:
    """Bungkus string JSON menjadi struktur respons bersarang Langflow."""
    return {
        "session_id": "test-session",
        "outputs": [{
            "inputs": {"input_value": "test"},
            "outputs": [{
                "results": {
                    "message": {
                        "data": {
                            "text": teks_json,
                        }
                    }
                }
            }]
        }]
    }


# ---------------------------------------------------------------------------
# 1. Unit test: parse_respons_langflow
# ---------------------------------------------------------------------------

class ParseResponsLangflowTest(TestCase):

    def _json_dalam_fence(self, data: dict) -> str:
        """Bungkus dict dalam ```json ... ``` seperti output flow asli."""
        return f"Teks sebelumnya\n```json\n{json.dumps(data)}\n```\nTeks sesudahnya"

    def test_parse_json_langsung(self):
        """JSON ditulis langsung di field text (tanpa code fence)."""
        data = {
            "status": "BELUM_ADA_PESANAN",
            "items": [],
            "masalah": [],
        }
        raw = respons_langflow_raw(json.dumps(data))
        hasil = parse_respons_langflow(raw)
        self.assertEqual(hasil.status_flow, "BELUM_ADA_PESANAN")
        self.assertEqual(hasil.items, [])

    def test_parse_json_dalam_code_fence(self):
        """JSON dalam blok ```json``` — format utama yang digunakan flow."""
        data = {
            "status": "SEBAGIAN_VALID",
            "items": [
                {
                    "teks_asli": "2 kaos hitam M",
                    "nama_ditafsirkan": "Kaos Basic Cotton 24s",
                    "sku": "SKU001",
                    "kuantitas": 2,
                    "status_item": "DITEMUKAN",
                    "catatan": "",
                }
            ],
            "masalah": [],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        hasil = parse_respons_langflow(raw)
        self.assertEqual(hasil.status_flow, "SEBAGIAN_VALID")
        self.assertEqual(len(hasil.items), 1)
        item = hasil.items[0]
        self.assertEqual(item.teks_asli, "2 kaos hitam M")
        self.assertEqual(item.sku, "SKU001")
        self.assertEqual(item.kuantitas, 2)
        self.assertEqual(item.status_item, "DITEMUKAN")

    def test_parse_item_ambigu(self):
        data = {
            "status": "BUTUH_KLARIFIKASI",
            "items": [
                {
                    "teks_asli": "kaos premium",
                    "nama_ditafsirkan": "Kaos Premium (ambigu)",
                    "sku": None,
                    "kuantitas": 1,
                    "status_item": "AMBIGU",
                    "catatan": "Bisa Combed 24s atau Cotton 30s",
                }
            ],
            "masalah": ["Item ambigu membutuhkan klarifikasi"],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        hasil = parse_respons_langflow(raw)
        item = hasil.items[0]
        self.assertEqual(item.status_item, "AMBIGU")
        self.assertIsNone(item.sku)
        self.assertEqual(len(hasil.masalah), 1)

    def test_parse_item_tidak_ditemukan(self):
        data = {
            "status": "ADA_ITEM_TIDAK_VALID",
            "items": [
                {
                    "teks_asli": "sepatu boot ukuran 42",
                    "nama_ditafsirkan": "",
                    "sku": None,
                    "kuantitas": 1,
                    "status_item": "TIDAK_DITEMUKAN",
                    "catatan": "Produk tidak ada di katalog",
                }
            ],
            "masalah": [],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        hasil = parse_respons_langflow(raw)
        self.assertEqual(hasil.items[0].status_item, "TIDAK_DITEMUKAN")
        self.assertIsNone(hasil.items[0].sku)

    def test_status_item_tidak_dikenal_dinormalisasi(self):
        """Nilai status_item tidak dikenal dari AI dinormalisasi ke TIDAK_DITEMUKAN."""
        data = {
            "status": "OK",
            "items": [{
                "teks_asli": "produk x",
                "nama_ditafsirkan": "",
                "sku": None,
                "kuantitas": 1,
                "status_item": "NILAI_ANEH_DARI_AI",
                "catatan": "",
            }],
            "masalah": [],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        hasil = parse_respons_langflow(raw)
        self.assertEqual(hasil.items[0].status_item, "TIDAK_DITEMUKAN")

    def test_error_jika_struktur_bersarang_salah(self):
        """Respons tanpa struktur outputs bersarang → LangflowResponsInvalidError."""
        with self.assertRaises(LangflowResponsInvalidError):
            parse_respons_langflow({"session_id": "x", "outputs": []})

    def test_error_jika_json_tidak_valid(self):
        """Field text berisi bukan JSON → LangflowResponsInvalidError."""
        raw = respons_langflow_raw("ini bukan json sama sekali")
        with self.assertRaises(LangflowResponsInvalidError):
            parse_respons_langflow(raw)

    def test_error_jika_items_bukan_array(self):
        data = {"status": "OK", "items": "bukan array", "masalah": []}
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        with self.assertRaises(LangflowResponsInvalidError):
            parse_respons_langflow(raw)

    def test_error_jika_item_tidak_punya_teks_asli(self):
        data = {
            "status": "OK",
            "items": [{"kuantitas": 2, "status_item": "DITEMUKAN"}],
            "masalah": [],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        with self.assertRaises(LangflowResponsInvalidError):
            parse_respons_langflow(raw)

    def test_kuantitas_tidak_valid_dinormalisasi_ke_1(self):
        """Kuantitas string tidak valid dari AI → dinormalisasi ke 1."""
        data = {
            "status": "OK",
            "items": [{
                "teks_asli": "kaos",
                "nama_ditafsirkan": "Kaos",
                "sku": "SKU001",
                "kuantitas": "dua",   # tidak valid
                "status_item": "DITEMUKAN",
                "catatan": "",
            }],
            "masalah": [],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        hasil = parse_respons_langflow(raw)
        self.assertEqual(hasil.items[0].kuantitas, 1)

    def test_parse_multiple_items(self):
        """Beberapa item sekaligus terurai dengan benar."""
        data = {
            "status": "SEBAGIAN_VALID",
            "items": [
                {"teks_asli": "2 kaos hitam M", "nama_ditafsirkan": "Kaos",
                 "sku": "SKU001", "kuantitas": 2, "status_item": "DITEMUKAN", "catatan": ""},
                {"teks_asli": "1 hoodie abu", "nama_ditafsirkan": "Hoodie",
                 "sku": None, "kuantitas": 1, "status_item": "AMBIGU",
                 "catatan": "Ukuran tidak disebutkan"},
            ],
            "masalah": [],
        }
        raw = respons_langflow_raw(self._json_dalam_fence(data))
        hasil = parse_respons_langflow(raw)
        self.assertEqual(len(hasil.items), 2)
        self.assertEqual(hasil.items[0].status_item, "DITEMUKAN")
        self.assertEqual(hasil.items[1].status_item, "AMBIGU")


# ---------------------------------------------------------------------------
# 2. Unit test: build_katalog_csv dan build_memori_csv
# ---------------------------------------------------------------------------

class BuildCsvTest(TestCase):

    def setUp(self):
        self.umkm = buat_umkm("CSV01")
        self.produk1 = buat_produk(self.umkm, "SKU-A", "Kaos A", 50000, "Hitam", "M")
        self.produk2 = buat_produk(self.umkm, "SKU-B", "Kaos B", 65000, "Putih", "L")
        # Produk tidak aktif — tidak boleh muncul di CSV
        Produk.objects.create(
            umkm=self.umkm, sku="SKU-NONAKTIF", nama_produk="Nonaktif",
            kategori="Kaos", harga=Decimal("10000"), stok=0, aktif=False,
        )

    def test_katalog_csv_header(self):
        csv = build_katalog_csv(self.umkm.id)
        baris = csv.splitlines()
        self.assertEqual(
            baris[0],
            "SKU,Nama_Produk,Kategori,Warna,Ukuran,Harga,Stok,Aktif,Kunci_Produk"
        )

    def test_katalog_csv_hanya_produk_aktif(self):
        csv = build_katalog_csv(self.umkm.id)
        self.assertIn("SKU-A", csv)
        self.assertIn("SKU-B", csv)
        self.assertNotIn("SKU-NONAKTIF", csv)

    def test_katalog_csv_kunci_produk_digenerate(self):
        csv = build_katalog_csv(self.umkm.id)
        # Kunci_Produk = "Kaos A | Hitam | M"
        self.assertIn("Kaos A | Hitam | M", csv)

    def test_katalog_csv_kosong_jika_tidak_ada_produk_aktif(self):
        umkm_kosong = buat_umkm("CSV02", "Kosong")
        csv = build_katalog_csv(umkm_kosong.id)
        baris = csv.splitlines()
        self.assertEqual(len(baris), 1)   # hanya header

    def test_katalog_csv_umkm_lain_tidak_bocor(self):
        umkm2 = buat_umkm("CSV03", "Toko Lain")
        buat_produk(umkm2, "SKU-LAIN", "Produk Lain", 99000)
        csv = build_katalog_csv(self.umkm.id)
        self.assertNotIn("SKU-LAIN", csv)

    def test_memori_csv_header(self):
        Memori.objects.create(
            umkm=self.umkm, id_memori="MEM001", istilah="premium",
            makna="Kaos A", sumber="test", status=Memori.STATUS_DISETUJUI,
            versi=1, dibuat_pada="2026-10-01",
        )
        csv = build_memori_csv(self.umkm.id)
        self.assertTrue(csv.startswith("ID_Memori,Istilah,Makna"))

    def test_memori_csv_hanya_disetujui(self):
        Memori.objects.create(
            umkm=self.umkm, id_memori="MEM001", istilah="premium",
            makna="Kaos A", sumber="test", status=Memori.STATUS_DISETUJUI,
            versi=1, dibuat_pada="2026-10-01",
        )
        Memori.objects.create(
            umkm=self.umkm, id_memori="MEM002", istilah="premium lama",
            makna="Kaos B", sumber="test", status=Memori.STATUS_PENDING,
            versi=1, dibuat_pada="2026-10-01",
        )
        csv = build_memori_csv(self.umkm.id)
        self.assertIn("MEM001", csv)
        self.assertNotIn("MEM002", csv)


# ---------------------------------------------------------------------------
# 3. Unit test: LangflowClient (semua via mock httpx)
# ---------------------------------------------------------------------------

class LangflowClientTest(TestCase):

    def _buat_respons_sukses(self, teks_json: str):
        """Buat mock respons httpx dengan JSON valid."""
        data = {
            "status": "OK",
            "items": [],
            "masalah": [],
        }
        raw = respons_langflow_raw(f"```json\n{json.dumps(data)}\n```")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw
        return mock_resp

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_jalankan_berhasil(self, mock_post):
        mock_post.return_value = self._buat_respons_sukses("{}")
        client = LangflowClient()
        hasil = client.jalankan("test input", "session-001")
        self.assertIsInstance(hasil, HasilLangflow)
        # Pastikan API key tidak di-assert (tidak di-print) — hanya cek dipanggil
        mock_post.assert_called_once()

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_timeout_raise_langflow_timeout_error(self, mock_post):
        import httpx as httpx_real
        mock_post.side_effect = httpx_real.TimeoutException("timeout", request=None)
        client = LangflowClient()
        with self.assertRaises(LangflowTimeoutError):
            client.jalankan("test", "session-002")

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_http_500_raise_langflow_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp
        client = LangflowClient()
        with self.assertRaises(LangflowError):
            client.jalankan("test", "session-003")

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_http_403_raise_langflow_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_post.return_value = mock_resp
        client = LangflowClient()
        with self.assertRaises(LangflowError):
            client.jalankan("test", "session-004")

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_koneksi_gagal_raise_langflow_error(self, mock_post):
        import httpx as httpx_real
        mock_post.side_effect = httpx_real.ConnectError("refused", request=None)
        client = LangflowClient()
        with self.assertRaises(LangflowError):
            client.jalankan("test", "session-005")

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_respons_bukan_json_raise_invalid(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bukan json")
        mock_post.return_value = mock_resp
        client = LangflowClient()
        with self.assertRaises(LangflowResponsInvalidError):
            client.jalankan("test", "session-006")

    @patch("apps.pesanan.langflow_client.httpx.post")
    def test_api_key_tidak_ada_di_pesan_error(self, mock_post):
        """Pastikan pesan error tidak mengandung string yang mungkin adalah API key."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp
        client = LangflowClient()
        try:
            client.jalankan("test", "session-007")
        except LangflowError as exc:
            msg = str(exc)
            # Pesan error hanya mengandung status code — bukan key
            self.assertIn("401", msg)
            self.assertNotIn(client._api_key, msg)


# ---------------------------------------------------------------------------
# 4. Integrasi service: proses_langflow (semua via mock client)
# ---------------------------------------------------------------------------

class ProsesLangflowServiceTest(TestCase):

    def setUp(self):
        self.umkm = buat_umkm("SV01")
        self.produk = buat_produk(self.umkm, "SKU-SV-01", "Kaos SV", 65000, "Hitam", "M")
        self.pesanan = buat_pesanan_draft(self.umkm, "2 kaos hitam M")

    def _mock_client(self, hasil: HasilLangflow):
        """Patch LangflowClient.jalankan agar mengembalikan hasil tertentu."""
        return patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(jalankan=MagicMock(return_value=hasil))
        )

    def test_item_ditemukan_disimpan_dengan_harga_dari_db(self):
        """Harga diambil dari DB — harga dari AI diabaikan."""
        hasil = buat_hasil_langflow([
            ItemParsed(
                teks_asli="2 kaos hitam M",
                nama_ditafsirkan="Kaos SV",
                sku="SKU-SV-01",
                kuantitas=2,
                status_item="DITEMUKAN",
            )
        ])
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)

        self.assertEqual(pesanan.status, Pesanan.STATUS_MENUNGGU_REVIEW)
        items = list(pesanan.item_pesanan.all())
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.status_item, "DITEMUKAN")
        self.assertEqual(item.kuantitas, 2)
        # Harga dari DB (65000), bukan dari AI
        self.assertEqual(item.harga_satuan, Decimal("65000"))
        self.assertEqual(item.subtotal, Decimal("130000"))
        self.assertEqual(item.produk, self.produk)

    def test_item_ambigu_tidak_punya_harga(self):
        """Item AMBIGU: produk/harga/subtotal harus None."""
        hasil = buat_hasil_langflow([
            ItemParsed(
                teks_asli="kaos premium",
                nama_ditafsirkan="Kaos (ambigu)",
                sku=None,
                kuantitas=1,
                status_item="AMBIGU",
                catatan="Bisa beberapa produk",
            )
        ])
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)

        item = pesanan.item_pesanan.first()
        self.assertEqual(item.status_item, "AMBIGU")
        self.assertIsNone(item.produk)
        self.assertIsNone(item.harga_satuan)
        self.assertIsNone(item.subtotal)

    def test_item_tidak_ditemukan(self):
        """Item TIDAK_DITEMUKAN: tidak ada produk, harga None."""
        hasil = buat_hasil_langflow([
            ItemParsed(
                teks_asli="sepatu boots",
                nama_ditafsirkan="",
                sku=None,
                kuantitas=1,
                status_item="TIDAK_DITEMUKAN",
            )
        ])
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)

        item = pesanan.item_pesanan.first()
        self.assertEqual(item.status_item, "TIDAK_DITEMUKAN")
        self.assertIsNone(item.harga_satuan)

    def test_sku_tidak_ada_di_katalog_diturunkan_ke_tidak_ditemukan(self):
        """SKU dari AI yang tidak ada di katalog UMKM → TIDAK_DITEMUKAN."""
        hasil = buat_hasil_langflow([
            ItemParsed(
                teks_asli="produk x",
                nama_ditafsirkan="Produk X",
                sku="SKU-TIDAK-ADA",  # tidak ada di DB
                kuantitas=1,
                status_item="DITEMUKAN",
            )
        ])
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)

        item = pesanan.item_pesanan.first()
        self.assertEqual(item.status_item, "TIDAK_DITEMUKAN")
        self.assertIsNone(item.produk)
        self.assertIsNone(item.harga_satuan)

    def test_kuantitas_nol_dari_ai_dinormalisasi_ke_1(self):
        hasil = buat_hasil_langflow([
            ItemParsed(
                teks_asli="kaos",
                nama_ditafsirkan="Kaos",
                sku="SKU-SV-01",
                kuantitas=0,   # tidak valid
                status_item="DITEMUKAN",
            )
        ])
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)

        item = pesanan.item_pesanan.first()
        self.assertEqual(item.kuantitas, 1)

    def test_pesanan_status_menunggu_review_setelah_proses(self):
        hasil = buat_hasil_langflow([])   # tidak ada item — tetap transisi status
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)
        self.assertEqual(pesanan.status, Pesanan.STATUS_MENUNGGU_REVIEW)

    def test_pesanan_bukan_draft_ditolak(self):
        """proses_langflow hanya valid dari status DRAFT."""
        from apps.pesanan.services import ajukan_review
        ajukan_review(self.pesanan)  # DRAFT → MENUNGGU_REVIEW
        with self.assertRaises(ValueError) as ctx:
            proses_langflow(self.pesanan)
        self.assertIn("DRAFT", str(ctx.exception))

    def test_pesanan_sudah_ada_item_ditolak(self):
        """proses_langflow idempoten — tidak bisa dijalankan ulang."""
        ItemPesanan.objects.create(
            pesanan=self.pesanan,
            teks_asli="item sudah ada",
            kuantitas=1,
            status_item=ItemPesanan.STATUS_TIDAK_DITEMUKAN,
        )
        with self.assertRaises(ValueError) as ctx:
            proses_langflow(self.pesanan)
        self.assertIn("sudah memiliki item", str(ctx.exception))

    def test_kegagalan_langflow_tidak_menyimpan_item(self):
        """Jika Langflow gagal, tidak boleh ada item tersimpan."""
        with patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(jalankan=MagicMock(side_effect=LangflowError("gagal")))
        ):
            with self.assertRaises(LangflowError):
                proses_langflow(self.pesanan)

        self.assertEqual(ItemPesanan.objects.filter(pesanan=self.pesanan).count(), 0)
        # Status pesanan tidak berubah
        self.pesanan.refresh_from_db()
        self.assertEqual(self.pesanan.status, Pesanan.STATUS_DRAFT)

    def test_kegagalan_di_tengah_bulk_create_rollback_semua_item(self):
        """Simulasi IntegrityError di bulk_create → tidak ada item tersimpan."""
        hasil = buat_hasil_langflow([
            ItemParsed("item 1", "Item 1", "SKU-SV-01", 1, "DITEMUKAN"),
            ItemParsed("item 2", "Item 2", None, 1, "AMBIGU"),
        ])
        with patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(jalankan=MagicMock(return_value=hasil))
        ):
            with patch(
                "apps.pesanan.services.ItemPesanan.objects.bulk_create",
                side_effect=Exception("simulasi error DB")
            ):
                with self.assertRaises(Exception):
                    proses_langflow(self.pesanan)

        # Rollback — tidak ada item
        self.assertEqual(ItemPesanan.objects.filter(pesanan=self.pesanan).count(), 0)
        self.pesanan.refresh_from_db()
        self.assertEqual(self.pesanan.status, Pesanan.STATUS_DRAFT)

    def test_sku_dari_umkm_lain_tidak_bocor(self):
        """Produk dari UMKM lain tidak boleh digunakan meski SKU sama."""
        umkm2 = buat_umkm("SV02", "Toko Lain")
        # Buat produk di umkm2 dengan SKU yang sama
        Produk.objects.create(
            umkm=umkm2, sku="SKU-SV-01", nama_produk="Produk Lain",
            kategori="Kaos", harga=Decimal("999999"), stok=10, aktif=True,
        )
        hasil = buat_hasil_langflow([
            ItemParsed(
                teks_asli="2 kaos hitam M",
                nama_ditafsirkan="Kaos SV",
                sku="SKU-SV-01",
                kuantitas=2,
                status_item="DITEMUKAN",
            )
        ])
        with self._mock_client(hasil):
            pesanan = proses_langflow(self.pesanan)

        item = pesanan.item_pesanan.first()
        # Harga harus dari UMKM pesanan (65000), bukan dari UMKM lain (999999)
        self.assertEqual(item.harga_satuan, Decimal("65000"))
        self.assertEqual(item.produk.umkm_id, self.umkm.id)


# ---------------------------------------------------------------------------
# 5. Integrasi endpoint: POST /api/pesanan/pesanan/{id}/proses-langflow/
# ---------------------------------------------------------------------------

class ProsesLangflowEndpointTest(APITestCase):

    def setUp(self):
        self.umkm = buat_umkm("EP01")
        self.user = buat_user_dengan_keanggotaan("user_ep", self.umkm)
        self.produk = buat_produk(self.umkm, "SKU-EP-01", "Kaos EP", 70000)
        self.pesanan = buat_pesanan_draft(self.umkm, "mau beli 1 kaos EP")
        self.client.force_authenticate(user=self.user)

    def _mock_client_sukses(self, items=None):
        hasil = buat_hasil_langflow(items or [])
        return patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(jalankan=MagicMock(return_value=hasil))
        )

    def test_endpoint_berhasil_200(self):
        with self._mock_client_sukses():
            resp = self.client.post(
                PROSES_URL.format(id=self.pesanan.id)
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], Pesanan.STATUS_MENUNGGU_REVIEW)

    def test_endpoint_dengan_item_ditemukan(self):
        items = [ItemParsed(
            teks_asli="1 kaos EP",
            nama_ditafsirkan="Kaos EP",
            sku="SKU-EP-01",
            kuantitas=1,
            status_item="DITEMUKAN",
        )]
        with self._mock_client_sukses(items):
            resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item_data = resp.data["item_pesanan"]
        self.assertEqual(len(item_data), 1)
        self.assertEqual(item_data[0]["status_item"], "DITEMUKAN")
        # Harga dari DB — 70000
        self.assertEqual(Decimal(item_data[0]["harga_satuan"]), Decimal("70000"))
        self.assertEqual(Decimal(item_data[0]["subtotal"]), Decimal("70000"))

    def test_endpoint_pesanan_bukan_draft_400(self):
        """Pesanan non-DRAFT → 400."""
        from apps.pesanan.services import ajukan_review
        ajukan_review(self.pesanan)
        resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endpoint_langflow_timeout_504(self):
        with patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(
                jalankan=MagicMock(side_effect=LangflowTimeoutError("timeout"))
            )
        ):
            resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))
        self.assertEqual(resp.status_code, status.HTTP_504_GATEWAY_TIMEOUT)

    def test_endpoint_langflow_error_502(self):
        with patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(
                jalankan=MagicMock(side_effect=LangflowError("koneksi gagal"))
            )
        ):
            resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_endpoint_tanpa_autentikasi_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_endpoint_user_tanpa_keanggotaan_403(self):
        user_asing = User.objects.create_user("asing_ep", password="pass123")
        self.client.force_authenticate(user=user_asing)
        resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_endpoint_pesanan_umkm_lain_404(self):
        """User tidak bisa memproses pesanan UMKM lain."""
        umkm2 = buat_umkm("EP02", "Toko Lain")
        user2 = buat_user_dengan_keanggotaan("user_ep2", umkm2)
        pesanan2 = buat_pesanan_draft(umkm2, "order toko lain")
        # user1 mencoba memproses pesanan milik umkm2
        resp = self.client.post(PROSES_URL.format(id=pesanan2.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_endpoint_tidak_mengembalikan_api_key(self):
        """Detail error tidak boleh bocorkan API key."""
        with patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(
                jalankan=MagicMock(side_effect=LangflowError("error"))
            )
        ):
            resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))
        # Respons tidak mengandung kata 'api_key' atau 'key'
        self.assertNotIn("api_key", str(resp.data).lower())

    def test_endpoint_item_tidak_mengandalkan_harga_dari_ai(self):
        """Harga di response harus dari DB meski AI mengirim harga berbeda."""
        # AI mengklaim harga 999999 (harga jahat), tapi DB = 70000
        data_ai = {
            "status": "OK",
            "items": [{
                "teks_asli": "1 kaos EP",
                "nama_ditafsirkan": "Kaos EP",
                "sku": "SKU-EP-01",
                "kuantitas": 1,
                "status_item": "DITEMUKAN",
                "harga_satuan": 999999,   # <- ini harus diabaikan
                "catatan": "",
            }],
            "masalah": [],
        }
        raw = respons_langflow_raw(
            f"```json\n{json.dumps(data_ai)}\n```"
        )
        mock_hasil = parse_respons_langflow(raw)
        with patch(
            "apps.pesanan.services.LangflowClient",
            return_value=MagicMock(jalankan=MagicMock(return_value=mock_hasil))
        ):
            resp = self.client.post(PROSES_URL.format(id=self.pesanan.id))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item = resp.data["item_pesanan"][0]
        # Harga yang tersimpan harus dari DB (70000), bukan dari AI (999999)
        self.assertEqual(Decimal(item["harga_satuan"]), Decimal("70000"))
