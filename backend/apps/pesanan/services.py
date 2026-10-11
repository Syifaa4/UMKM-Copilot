"""
Service layer untuk operasi bisnis Pesanan.

Semua operasi yang mengubah status pesanan, item, atau keuangan wajib
melalui fungsi di modul ini — bukan langsung dari view atau serializer.

Aturan umum:
- Setiap fungsi yang menulis ke DB menggunakan transaction.atomic().
- UMKM selalu diambil dari keanggotaan user — tidak pernah dari payload.
- Nomor pesanan di-generate di sini dengan mekanisme yang aman terhadap
  concurrent request (loop retry dengan UUID suffix jika terjadi konflik).
"""

import logging
import uuid
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.keuangan.models import Transaksi
from apps.katalog.models import Produk
from apps.pesanan.models import ItemPesanan, Pesanan
from apps.pesanan.langflow_client import (
    HasilLangflow,
    ItemParsed,
    LangflowClient,
    LangflowError,
    build_katalog_csv,
    build_memori_csv,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_nomor_pesanan(umkm_id: str) -> str:
    """
    Hasilkan nomor pesanan unik dengan format ORD-{UMKM}-{YYYYMMDD}-{suffix}.
    Suffix adalah 8 karakter hex dari UUID4 — aman terhadap concurrent request
    tanpa memerlukan penguncian baris counter.
    Probabilitas tabrakan per UMKM per hari: ~1 dalam 4 miliar.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    today = date.today().strftime("%Y%m%d")
    return f"ORD-{umkm_id}-{today}-{suffix}"


def _hitung_hpp_item(item: ItemPesanan) -> Decimal:
    """
    Hitung total HPP untuk satu item berdasarkan KomponenHPP produk saat ini.
    Mengembalikan Decimal('0.00') jika produk tidak punya komponen HPP.

    Nilai nol ini valid dan didokumentasikan — produk tanpa komponen HPP
    dianggap HPP-nya nol, bukan error.

    Raises ValueError jika item tidak punya produk (produk=None).
    """
    if item.produk_id is None:
        raise ValueError(
            f"Item '{item.teks_asli}' tidak memiliki produk — "
            "hpp_snapshot tidak dapat dihitung."
        )
    total_hpp_per_unit = sum(
        k.biaya for k in item.produk.komponen_hpp.all()
    )
    return Decimal(str(total_hpp_per_unit)) * item.kuantitas


# ---------------------------------------------------------------------------
# Transisi status dan operasi bisnis
# ---------------------------------------------------------------------------

TRANSISI_VALID = {
    Pesanan.STATUS_DRAFT: {Pesanan.STATUS_MENUNGGU_REVIEW, Pesanan.STATUS_DIBATALKAN},
    Pesanan.STATUS_MENUNGGU_REVIEW: {
        Pesanan.STATUS_DIKONFIRMASI,
        Pesanan.STATUS_DIBATALKAN,
    },
    Pesanan.STATUS_DIKONFIRMASI: {
        Pesanan.STATUS_SELESAI,
        Pesanan.STATUS_DIBATALKAN,
    },
    Pesanan.STATUS_SELESAI: {Pesanan.STATUS_DIBATALKAN},
    Pesanan.STATUS_DIBATALKAN: set(),
}


def _validasi_transisi(pesanan: Pesanan, status_baru: str) -> None:
    """Raise ValueError jika transisi status tidak diizinkan."""
    diizinkan = TRANSISI_VALID.get(pesanan.status, set())
    if status_baru not in diizinkan:
        raise ValueError(
            f"Transisi dari '{pesanan.status}' ke '{status_baru}' tidak diizinkan."
        )


def buat_pesanan(umkm, nama_pelanggan: str, teks_chat_asli: str,
                 catatan: str = "") -> Pesanan:
    """
    Buat pesanan baru dengan status DRAFT.
    Nomor pesanan di-generate otomatis dengan retry jika terjadi konflik.
    UMKM berasal dari keanggotaan pengguna, bukan dari payload.
    """
    for attempt in range(5):
        nomor = _generate_nomor_pesanan(umkm.id)
        try:
            with transaction.atomic():
                pesanan = Pesanan.objects.create(
                    umkm=umkm,
                    nomor_pesanan=nomor,
                    nama_pelanggan=nama_pelanggan,
                    teks_chat_asli=teks_chat_asli,
                    catatan=catatan,
                    status=Pesanan.STATUS_DRAFT,
                )
            return pesanan
        except IntegrityError:
            if attempt == 4:
                raise RuntimeError(
                    "Gagal membuat nomor pesanan unik setelah 5 percobaan."
                )
            continue


def ajukan_review(pesanan: Pesanan) -> Pesanan:
    """
    Transisi DRAFT → MENUNGGU_REVIEW.
    Hanya memvalidasi transisi; tidak memvalidasi isi item
    (item diisi oleh integrasi Langflow yang akan datang).
    """
    _validasi_transisi(pesanan, Pesanan.STATUS_MENUNGGU_REVIEW)
    with transaction.atomic():
        pesanan.status = Pesanan.STATUS_MENUNGGU_REVIEW
        pesanan.save(update_fields=["status", "diperbarui_pada"])
    return pesanan


def verifikasi_item(pesanan: Pesanan, item: ItemPesanan,
                    produk: Produk, kuantitas: int) -> ItemPesanan:
    """
    Operator memilih produk yang tepat untuk item AMBIGU atau TIDAK_DITEMUKAN.
    Mengisi harga_satuan, subtotal, dan mengubah status_item ke DIKONFIRMASI.
    Pesanan harus berada di MENUNGGU_REVIEW.

    Raises:
        ValueError: jika pesanan tidak di MENUNGGU_REVIEW, kuantitas < 1,
                    atau produk bukan milik UMKM yang sama dengan pesanan.
    """
    if pesanan.status != Pesanan.STATUS_MENUNGGU_REVIEW:
        raise ValueError(
            f"Verifikasi item hanya diizinkan saat pesanan berstatus "
            f"MENUNGGU_REVIEW. Status saat ini: '{pesanan.status}'."
        )
    if produk.umkm_id != pesanan.umkm_id:
        raise ValueError(
            "Produk tidak berasal dari UMKM yang sama dengan pesanan."
        )
    if kuantitas < 1:
        raise ValueError("Kuantitas minimal 1.")

    harga = produk.harga
    subtotal = harga * kuantitas

    with transaction.atomic():
        item.produk = produk
        item.kuantitas = kuantitas
        item.harga_satuan = harga
        item.subtotal = subtotal
        item.status_item = ItemPesanan.STATUS_DIKONFIRMASI
        item.nama_ditafsirkan = str(produk)
        item.save(update_fields=[
            "produk", "kuantitas", "harga_satuan", "subtotal",
            "status_item", "nama_ditafsirkan",
        ])
    return item


def konfirmasi_pesanan(pesanan: Pesanan) -> tuple[Pesanan, Transaksi]:
    """
    Transisi MENUNGGU_REVIEW → DIKONFIRMASI.

    Dalam satu blok atomic:
    1. Kunci baris pesanan dengan select_for_update().
    2. Guard: status harus MENUNGGU_REVIEW.
    3. Guard: tidak ada item AMBIGU atau TIDAK_DITEMUKAN.
    4. Guard: semua item DITEMUKAN/DIKONFIRMASI punya harga_satuan dan subtotal.
    5. Guard: minimal satu item terverifikasi.
    6. Guard: belum ada Transaksi PENJUALAN untuk pesanan ini (idempoten).
    7. Hitung hpp_snapshot untuk setiap item terverifikasi.
       - Jika produk tidak punya KomponenHPP → hpp_snapshot = 0.00 (valid).
       - Jika item tidak punya produk → raise ValueError, batalkan seluruh operasi.
    8. Buat Transaksi PENJUALAN.
    9. Update status pesanan.

    Raises:
        ValueError: untuk semua pelanggaran guard bisnis.
        RuntimeError: jika constraint DB unique_penjualan_per_pesanan dilanggar
                      (seharusnya tidak terjadi jika guard #6 bekerja).
    """
    with transaction.atomic():
        pesanan = Pesanan.objects.select_for_update().get(pk=pesanan.pk)
        _validasi_transisi(pesanan, Pesanan.STATUS_DIKONFIRMASI)

        items = list(
            pesanan.item_pesanan.select_related("produk").prefetch_related(
                "produk__komponen_hpp"
            ).all()
        )

        # Guard: minimal satu item
        if not items:
            raise ValueError("Pesanan tidak memiliki item.")

        # Guard: tidak ada item yang belum terselesaikan
        belum_valid = [
            i for i in items
            if i.status_item in (
                ItemPesanan.STATUS_AMBIGU,
                ItemPesanan.STATUS_TIDAK_DITEMUKAN,
            )
        ]
        if belum_valid:
            teks = ", ".join(f"'{i.teks_asli}'" for i in belum_valid)
            raise ValueError(
                f"Pesanan masih memiliki item yang belum teridentifikasi: {teks}."
            )

        # Guard: semua item terverifikasi harus punya harga
        item_tanpa_harga = [
            i for i in items
            if i.status_item in ItemPesanan.STATUS_TERVERIFIKASI
            and (i.harga_satuan is None or i.subtotal is None)
        ]
        if item_tanpa_harga:
            teks = ", ".join(f"'{i.teks_asli}'" for i in item_tanpa_harga)
            raise ValueError(
                f"Item berikut belum memiliki harga terverifikasi: {teks}."
            )

        item_valid = [
            i for i in items
            if i.status_item in ItemPesanan.STATUS_TERVERIFIKASI
        ]

        # Guard: idempoten — cegah transaksi penjualan ganda
        if pesanan.transaksi.filter(
            kategori=Transaksi.KATEGORI_PENJUALAN
        ).exists():
            raise ValueError(
                "Transaksi penjualan untuk pesanan ini sudah ada."
            )

        # Hitung hpp_snapshot dan total penjualan
        total_penjualan = Decimal("0.00")
        for item in item_valid:
            hpp = _hitung_hpp_item(item)  # raise jika produk None
            item.hpp_snapshot = hpp
            total_penjualan += item.subtotal

        # Simpan hpp_snapshot semua item dalam batch
        ItemPesanan.objects.bulk_update(item_valid, ["hpp_snapshot"])

        # Buat transaksi penjualan
        try:
            transaksi = Transaksi.objects.create(
                umkm=pesanan.umkm,
                pesanan=pesanan,
                jenis=Transaksi.JENIS_PEMASUKAN,
                kategori=Transaksi.KATEGORI_PENJUALAN,
                jumlah=total_penjualan,
                tanggal=date.today(),
                keterangan=f"Penjualan dari pesanan {pesanan.nomor_pesanan}",
            )
        except IntegrityError as exc:
            raise RuntimeError(
                "Transaksi penjualan duplikat terdeteksi oleh constraint database."
            ) from exc

        pesanan.status = Pesanan.STATUS_DIKONFIRMASI
        pesanan.save(update_fields=["status", "diperbarui_pada"])

    return pesanan, transaksi


def selesaikan_pesanan(pesanan: Pesanan) -> Pesanan:
    """Transisi DIKONFIRMASI → SELESAI."""
    _validasi_transisi(pesanan, Pesanan.STATUS_SELESAI)
    with transaction.atomic():
        pesanan = Pesanan.objects.select_for_update().get(pk=pesanan.pk)
        _validasi_transisi(pesanan, Pesanan.STATUS_SELESAI)
        pesanan.status = Pesanan.STATUS_SELESAI
        pesanan.save(update_fields=["status", "diperbarui_pada"])
    return pesanan


def batalkan_pesanan(pesanan: Pesanan) -> Pesanan:
    """
    Batalkan pesanan dari status apapun kecuali DIBATALKAN.

    - Jika pesanan belum dikonfirmasi: ubah status saja, tidak ada transaksi.
    - Jika pesanan DIKONFIRMASI atau SELESAI: buat Transaksi KOREKSI_PEMBATALAN
      sebesar jumlah transaksi penjualan asli, dalam satu blok atomic.
    - Guard idempoten: jika KOREKSI_PEMBATALAN sudah ada, tolak dengan error.
    """
    _validasi_transisi(pesanan, Pesanan.STATUS_DIBATALKAN)

    status_sudah_dikonfirmasi = pesanan.status in (
        Pesanan.STATUS_DIKONFIRMASI,
        Pesanan.STATUS_SELESAI,
    )

    with transaction.atomic():
        pesanan = Pesanan.objects.select_for_update().get(pk=pesanan.pk)
        _validasi_transisi(pesanan, Pesanan.STATUS_DIBATALKAN)

        if status_sudah_dikonfirmasi:
            # Guard idempoten
            if pesanan.transaksi.filter(
                kategori=Transaksi.KATEGORI_KOREKSI_PEMBATALAN
            ).exists():
                raise ValueError(
                    "Transaksi koreksi pembatalan untuk pesanan ini sudah ada."
                )

            transaksi_penjualan = pesanan.transaksi.filter(
                kategori=Transaksi.KATEGORI_PENJUALAN
            ).first()
            if transaksi_penjualan is None:
                raise ValueError(
                    "Tidak ditemukan transaksi penjualan untuk pesanan ini. "
                    "Tidak dapat membuat koreksi pembatalan."
                )

            try:
                Transaksi.objects.create(
                    umkm=pesanan.umkm,
                    pesanan=pesanan,
                    jenis=Transaksi.JENIS_PENGELUARAN,
                    kategori=Transaksi.KATEGORI_KOREKSI_PEMBATALAN,
                    jumlah=transaksi_penjualan.jumlah,
                    tanggal=date.today(),
                    keterangan=(
                        f"Koreksi pembatalan pesanan {pesanan.nomor_pesanan}"
                    ),
                )
            except IntegrityError as exc:
                raise RuntimeError(
                    "Transaksi koreksi pembatalan duplikat terdeteksi "
                    "oleh constraint database."
                ) from exc

        pesanan.status = Pesanan.STATUS_DIBATALKAN
        pesanan.save(update_fields=["status", "diperbarui_pada"])

    return pesanan


# ---------------------------------------------------------------------------
# Integrasi Langflow
# ---------------------------------------------------------------------------

def _bangun_input_langflow(pesanan: "Pesanan") -> str:
    """
    Sertakan identitas UMKM agar Langflow tidak menebak konteks UMKM.
    """
    return (
        f"UMKM_ID: {pesanan.umkm_id}\n"
        f"{pesanan.teks_chat_asli}"
    )


def _buat_item_dari_parsed(
    pesanan: "Pesanan",
    item_parsed: "ItemParsed",
    produk_map: dict,
) -> "ItemPesanan":
    """
    Buat instance ItemPesanan (belum disimpan) dari satu ItemParsed.

    Aturan:
    - Harga selalu diambil dari objek Produk di database — bukan dari AI.
    - Subtotal dihitung backend: harga_db × kuantitas.
    - Kuantitas minimum 1 — nilai AI yang tidak valid dinormalisasi ke 1.
    - Item AMBIGU/TIDAK_DITEMUKAN: produk/harga/subtotal tetap None.
    - produk_map: dict {sku: Produk} yang sudah di-filter ke UMKM pesanan.
    """
    kuantitas = max(1, item_parsed.kuantitas)
    status_item = item_parsed.status_item

    produk = None
    harga_satuan = None
    subtotal = None

    if status_item == "DITEMUKAN" and item_parsed.sku:
        produk = produk_map.get(item_parsed.sku)
        if produk is None:
            # SKU tidak ada di katalog UMKM ini — turunkan ke TIDAK_DITEMUKAN
            logger.warning(
                "SKU '%s' dari Langflow tidak ditemukan di katalog UMKM '%s' — "
                "item diturunkan ke TIDAK_DITEMUKAN.",
                item_parsed.sku, pesanan.umkm_id,
            )
            status_item = "TIDAK_DITEMUKAN"
        else:
            harga_satuan = produk.harga          # harga dari DB, bukan dari AI
            subtotal = harga_satuan * kuantitas  # dihitung backend

    return ItemPesanan(
        pesanan=pesanan,
        produk=produk,
        teks_asli=item_parsed.teks_asli[:500],
        nama_ditafsirkan=item_parsed.nama_ditafsirkan[:200],
        kuantitas=kuantitas,
        harga_satuan=harga_satuan,
        subtotal=subtotal,
        status_item=status_item,
        catatan_validasi=item_parsed.catatan[:500] if item_parsed.catatan else "",
    )


def proses_langflow(pesanan: "Pesanan") -> "Pesanan":
    """
    Panggil Langflow untuk mem-parsing teks_chat_asli pesanan, lalu simpan
    hasilnya sebagai ItemPesanan dan transisikan pesanan ke MENUNGGU_REVIEW.

    Alur:
    1. Guard: pesanan harus berstatus DRAFT.
    2. Guard: pesanan tidak boleh sudah memiliki item (idempoten).
    3. Panggil Langflow (operasi di luar transaksi DB — tidak boleh dalam atomic).
    4. Dalam satu transaction.atomic():
       a. Ambil katalog UMKM dari DB → buat produk_map {sku: Produk}.
       b. Konversi setiap ItemParsed → ItemPesanan (harga dari DB).
       c. Bulk-create semua item.
       d. Transisi pesanan DRAFT → MENUNGGU_REVIEW.

    Raises:
        ValueError       : guard bisnis dilanggar (bukan status DRAFT, sudah ada item).
        LangflowError    : kegagalan koneksi atau HTTP Langflow.
        LangflowResponsInvalidError: respons Langflow tidak sesuai kontrak.

    Catatan keamanan:
    - UMKM diambil dari objek pesanan yang sudah ada di DB (sudah ter-scope ke user).
    - Harga tidak pernah diambil dari output AI.
    - Kegagalan di langkah 4 akan di-rollback seluruhnya — tidak ada item tersimpan
      sebagian.
    """
    if pesanan.status != Pesanan.STATUS_DRAFT:
        raise ValueError(
            f"proses_langflow hanya dapat dipanggil pada pesanan DRAFT. "
            f"Status saat ini: '{pesanan.status}'."
        )

    if pesanan.item_pesanan.exists():
        raise ValueError(
            "Pesanan ini sudah memiliki item. "
            "proses_langflow tidak dapat dijalankan ulang."
        )

    # --- Panggil Langflow (di luar transaksi DB) ---
    input_value = _bangun_input_langflow(pesanan)
    client = LangflowClient()
    hasil: HasilLangflow = client.jalankan(
        input_value=input_value,
        session_id=pesanan.nomor_pesanan,
    )

    logger.info(
        "Langflow selesai: pesanan=%s, status_flow=%s, jumlah_item=%d",
        pesanan.nomor_pesanan, hasil.status_flow, len(hasil.items),
    )

    # --- Simpan ke DB dalam satu atomic block ---
    with transaction.atomic():
        # Ambil ulang pesanan dengan lock untuk mencegah race condition
        pesanan = Pesanan.objects.select_for_update().get(pk=pesanan.pk)

        # Guard ulang di dalam atomic (status bisa berubah sejak pengecekan awal)
        if pesanan.status != Pesanan.STATUS_DRAFT:
            raise ValueError(
                f"Status pesanan berubah sebelum item dapat disimpan: '{pesanan.status}'."
            )
        if pesanan.item_pesanan.exists():
            raise ValueError(
                "Item sudah ada saat hendak disimpan — kemungkinan race condition."
            )

        # Bangun lookup table produk aktif milik UMKM ini
        produk_qs = Produk.objects.filter(
            umkm_id=pesanan.umkm_id, aktif=True
        )
        produk_map: dict = {p.sku: p for p in produk_qs}

        # Konversi hasil Langflow ke daftar ItemPesanan (belum disimpan)
        item_list = [
            _buat_item_dari_parsed(pesanan, ip, produk_map)
            for ip in hasil.items
        ]

        # Simpan semua item sekaligus — rollback otomatis jika ada error
        if item_list:
            ItemPesanan.objects.bulk_create(item_list)

        # Transisi status DRAFT → MENUNGGU_REVIEW
        pesanan.status = Pesanan.STATUS_MENUNGGU_REVIEW
        pesanan.save(update_fields=["status", "diperbarui_pada"])

    return pesanan
