"""
Client dan parser untuk integrasi Langflow.

Tanggung jawab modul ini:
- Mengirim request HTTP ke Langflow (LangflowClient).
- Mengekstrak JSON terstruktur dari respons bersarang Langflow (parse_respons_langflow).
- Membangun payload CSV katalog dan memori dari objek Django (build_katalog_csv,
  build_memori_csv).

Yang TIDAK dilakukan modul ini:
- Tidak menyimpan apapun ke database.
- Tidak memvalidasi item terhadap katalog.
- Tidak menghitung harga atau subtotal.

Keamanan:
- API key tidak pernah di-log atau dimasukkan ke pesan error.
- Timeout eksplisit untuk semua request.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import httpx
from django.conf import settings

from apps.katalog.models import Produk
from apps.memori.models import Memori

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LangflowError(Exception):
    """Error generik saat memanggil Langflow."""


class LangflowTimeoutError(LangflowError):
    """Langflow tidak merespons dalam batas waktu."""


class LangflowResponsInvalidError(LangflowError):
    """Respons Langflow tidak sesuai kontrak yang diharapkan."""


# ---------------------------------------------------------------------------
# Data class untuk output terstruktur
# ---------------------------------------------------------------------------

@dataclass
class ItemParsed:
    """
    Satu item hasil parsing respons Langflow.

    teks_asli       : teks mentah dari chat pelanggan
    nama_ditafsirkan: nama produk yang ditafsirkan AI (bisa kosong)
    sku             : SKU produk yang ditemukan AI (None jika tidak ditemukan)
    kuantitas       : jumlah yang dipesan (belum divalidasi backend)
    status_item     : 'DITEMUKAN', 'AMBIGU', atau 'TIDAK_DITEMUKAN'
    catatan         : pesan AI mengenai item ini (ambiguitas, dll.)
    """
    teks_asli: str
    nama_ditafsirkan: str
    sku: str | None
    kuantitas: int
    status_item: str
    catatan: str = ""


@dataclass
class HasilLangflow:
    """
    Seluruh output parsing satu sesi Langflow.

    status_flow   : status global dari AI (misal SEBAGIAN_VALID, BELUM_ADA_PESANAN)
    items         : daftar ItemParsed
    masalah       : daftar pesan masalah global dari AI
    teks_mentah   : field 'text' asli dari respons, untuk keperluan debug
    """
    status_flow: str
    items: list[ItemParsed] = field(default_factory=list)
    masalah: list[str] = field(default_factory=list)
    teks_mentah: str = ""


# ---------------------------------------------------------------------------
# CSV builder
# ---------------------------------------------------------------------------

def build_katalog_csv(umkm_id: str) -> str:
    """
    Bangun string CSV katalog aktif milik umkm_id dari database.

    Kolom disamakan dengan format yang digunakan flow Langflow:
    SKU, Nama_Produk, Kategori, Warna, Ukuran, Harga, Stok, Aktif, Kunci_Produk

    Kolom 'Bahan' tidak ada di model saat ini — dikosongkan agar header tetap
    kompatibel dengan flow. Ini adalah keterbatasan yang sudah didokumentasikan.
    Kolom 'Kunci_Produk' digenerate on-the-fly: "Nama | Warna | Ukuran".
    """
    produk_qs = Produk.objects.filter(umkm_id=umkm_id, aktif=True).order_by("sku")
    baris = ["SKU,Nama_Produk,Kategori,Warna,Ukuran,Harga,Stok,Aktif,Kunci_Produk"]
    for p in produk_qs:
        bagian_kunci = [p.nama_produk]
        if p.warna:
            bagian_kunci.append(p.warna)
        if p.ukuran:
            bagian_kunci.append(p.ukuran)
        kunci = " | ".join(bagian_kunci)
        baris.append(
            f"{p.sku},{p.nama_produk},{p.kategori},{p.warna},{p.ukuran},"
            f"{p.harga},{p.stok},TRUE,{kunci}"
        )
    return "\n".join(baris)


def build_memori_csv(umkm_id: str) -> str:
    """
    Bangun string CSV memori berstatus DISETUJUI milik umkm_id dari database.
    Hanya baris DISETUJUI yang dikirim ke Langflow — sesuai aturan model Memori.
    """
    memori_qs = (
        Memori.objects
        .filter(umkm_id=umkm_id, status=Memori.STATUS_DISETUJUI)
        .order_by("istilah")
    )
    baris = [
        "ID_Memori,Istilah,Makna,Sumber,Status,Versi,"
        "Makna_Sebelumnya,Dibuat_Pada,Disetujui_Oleh,Tindakan,Catatan"
    ]
    for m in memori_qs:
        baris.append(
            f"{m.id_memori},{m.istilah},{m.makna},{m.sumber},{m.status},"
            f"{m.versi},{m.makna_sebelumnya},{m.dibuat_pada},"
            f"{m.disetujui_oleh},{m.tindakan},{m.catatan}"
        )
    return "\n".join(baris)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

# Pola untuk mengekstrak blok ```json ... ``` dari field text
_POLA_JSON_FENCE = re.compile(r"```json\s*([\s\S]+?)\s*```", re.IGNORECASE)

# Status item yang valid dari flow — harus cocok dengan konstanta ItemPesanan
STATUS_ITEM_VALID = {"DITEMUKAN", "AMBIGU", "TIDAK_DITEMUKAN"}



def parse_respons_langflow(raw: dict) -> HasilLangflow:
    """Parse respons Langflow dan normalisasi dua format JSON yang didukung."""
    try:
        teks = (
            raw["outputs"][0]["outputs"][0]
            ["results"]["message"]["data"]["text"]
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise LangflowResponsInvalidError(
            "Struktur respons Langflow tidak sesuai."
        ) from exc

    cocok = _POLA_JSON_FENCE.search(teks)
    json_str = cocok.group(1) if cocok else teks.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise LangflowResponsInvalidError(
            "JSON dari respons Langflow tidak valid."
        ) from exc

    if not isinstance(data, dict):
        raise LangflowResponsInvalidError(
            "JSON dari Langflow bukan objek."
        )

    status_flow = str(data.get("status", "TIDAK_DIKETAHUI"))
    masalah_raw = data.get("masalah", [])
    raw_items = data.get("items", [])

    if not isinstance(raw_items, list):
        raise LangflowResponsInvalidError(
            "Field 'items' bukan array."
        )

    items = []

    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise LangflowResponsInvalidError(
                f"Item ke-{i} bukan objek."
            )

        # Format flow saat ini: produk, jumlah, valid.
        # Format lama: teks_asli, nama_ditafsirkan, kuantitas, status_item.
        nama = str(
            item.get("nama_ditafsirkan")
            or item.get("produk")
            or ""
        ).strip()

        teks_asli = str(
            item.get("teks_asli")
            or nama
        ).strip()

        if not teks_asli:
            raise LangflowResponsInvalidError(
                f"Item ke-{i} tidak memiliki nama atau teks asli."
            )

        try:
            kuantitas = int(
                item.get("kuantitas", item.get("jumlah", 1))
            )
        except (TypeError, ValueError):
            kuantitas = 1
        

        if kuantitas < 1:
            raise LangflowResponsInvalidError(
                f"Kuantitas item ke-{i} harus minimal 1."
            )

        status_item_raw = item.get("status_item")

        if status_item_raw:
            status_item = str(status_item_raw).upper()
        elif item.get("valid") is True:
            status_item = "DITEMUKAN"
        elif item.get("valid") is False:
            status_item = "TIDAK_DITEMUKAN"
        else:
            status_item = "AMBIGU"

        if status_item not in STATUS_ITEM_VALID:
            status_item = "TIDAK_DITEMUKAN"

        items.append(
            ItemParsed(
                teks_asli=teks_asli,
                nama_ditafsirkan=nama,
                sku=str(item["sku"]) if item.get("sku") else None,
                kuantitas=kuantitas,
                status_item=status_item,
                catatan=str(item.get("catatan", "")),
            )
        )

    return HasilLangflow(
        status_flow=status_flow,
        items=items,
        masalah=[
            str(m) for m in masalah_raw
        ] if isinstance(masalah_raw, list) else [],
        teks_mentah=teks,
    )



# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

class LangflowClient:
    """
    Client HTTP untuk memanggil Langflow run endpoint.
    Konfigurasi diambil dari Django settings (yang dibaca dari .env).
    """

    TIMEOUT_DETIK = 60

    def __init__(self):
        self._api_url: str = getattr(settings, "LANGFLOW_API_URL", "")
        self._api_key: str = getattr(settings, "LANGFLOW_API_KEY", "")
        if not self._api_url:
            raise LangflowError(
                "LANGFLOW_API_URL belum dikonfigurasi di settings."
            )
        if not self._api_key:
            raise LangflowError(
                "LANGFLOW_API_KEY belum dikonfigurasi di settings."
            )

    def jalankan(self, input_value: str, session_id: str) -> HasilLangflow:
        """
        Panggil flow Langflow dengan input_value dan session_id.

        Raises:
            LangflowTimeoutError    : jika request timeout.
            LangflowError           : untuk HTTP error atau koneksi gagal.
            LangflowResponsInvalidError: jika respons tidak sesuai kontrak.
        """
        payload = {
            "input_value": input_value,
            "input_type": "chat",
            "output_type": "chat",
            "session_id": session_id,
        }
        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-api-key": self._api_key,
        }

        logger.info(
            "Memanggil Langflow: session_id=%s, input_length=%d",
            session_id, len(input_value),
        )

        try:
            resp = httpx.post(
                self._api_url,
                json=payload,
                headers=headers,
                timeout=self.TIMEOUT_DETIK,
            )
        except httpx.TimeoutException as exc:
            raise LangflowTimeoutError(
                f"Langflow tidak merespons dalam {self.TIMEOUT_DETIK} detik."
            ) from exc
        except httpx.RequestError as exc:
            raise LangflowError(
                f"Koneksi ke Langflow gagal: {type(exc).__name__}"
            ) from exc

        if resp.status_code != 200:
            # Log status code saja — jangan log body yang mungkin memuat info internal
            logger.error(
                "Langflow mengembalikan HTTP %d untuk session_id=%s",
                resp.status_code, session_id,
            )
            raise LangflowError(
                f"Langflow mengembalikan status HTTP {resp.status_code}."
            )

        try:
            raw = resp.json()
        except Exception as exc:
            raise LangflowResponsInvalidError(
                "Respons Langflow bukan JSON yang valid."
            ) from exc

        return parse_respons_langflow(raw)
