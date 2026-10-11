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
import csv
import io
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
    Bangun CSV katalog aktif milik UMKM.
    UMKM_ID disertakan agar komponen Langflow dapat
    memfilter produk berdasarkan pemiliknya.
    """
    produk_qs = (
        Produk.objects
        .filter(umkm_id=umkm_id, aktif=True)
        .order_by("sku")
    )

    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow([
        "UMKM_ID",
        "SKU",
        "Nama_Produk",
        "Kategori",
        "Warna",
        "Ukuran",
        "Harga",
        "Stok",
        "Aktif",
        "Kunci_Produk",
    ])

    for p in produk_qs:
        bagian_kunci = [p.nama_produk]

        if p.warna:
            bagian_kunci.append(p.warna)
        if p.ukuran:
            bagian_kunci.append(p.ukuran)

        writer.writerow([
            str(umkm_id),
            p.sku,
            p.nama_produk,
            p.kategori,
            p.warna or "",
            p.ukuran or "",
            p.harga,
            p.stok,
            "TRUE",
            " | ".join(bagian_kunci),
        ])

    return output.getvalue()

def build_memori_csv(umkm_id: str) -> str:
    """
    Bangun CSV memori berstatus DISETUJUI milik UMKM.
    CSV ditulis menggunakan csv.writer agar koma dan
    karakter khusus dalam isi memori tidak merusak kolom.
    """
    memori_qs = (
        Memori.objects
        .filter(
            umkm_id=umkm_id,
            status=Memori.STATUS_DISETUJUI,
        )
        .order_by("istilah")
    )

    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow([
        "UMKM_ID",
        "ID_Memori",
        "Istilah",
        "Makna",
        "Sumber",
        "Status",
        "Versi",
        "Makna_Sebelumnya",
        "Dibuat_Pada",
        "Disetujui_Oleh",
        "Tindakan",
        "Catatan",
    ])

    for m in memori_qs:
        writer.writerow([
            str(umkm_id),
            m.id_memori,
            m.istilah,
            m.makna,
            m.sumber,
            m.status,
            m.versi,
            m.makna_sebelumnya or "",
            m.dibuat_pada or "",
            m.disetujui_oleh or "",
            m.tindakan or "",
            m.catatan or "",
        ])

    return output.getvalue()

# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

# Pola untuk mengekstrak blok ```json ... ``` dari field text

_POLA_JSON_FENCE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)

STATUS_ITEM_VALID = {
    "DITEMUKAN",
    "AMBIGU",
    "TIDAK_DITEMUKAN",
}


def _ambil_json(teks: str) -> dict:
    """Mengambil objek JSON dari teks respons Langflow."""
    teks = teks.strip()

    # 1. Coba ambil JSON dari code fence Markdown.
    cocok = _POLA_JSON_FENCE.search(teks)
    if cocok:
        teks = cocok.group(1).strip()

    # 2. Coba jika seluruh teks merupakan JSON.
    try:
        data = json.loads(teks)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 3. Coba temukan objek JSON jika ada teks tambahan.
    decoder = json.JSONDecoder()

    for posisi, karakter in enumerate(teks):
        if karakter != "{":
            continue

        try:
            data, _ = decoder.raw_decode(teks[posisi:])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    raise LangflowResponsInvalidError(
        "Respons Langflow tidak berisi objek JSON yang valid."
    )


def parse_respons_langflow(raw: dict) -> HasilLangflow:
    """Parse respons Langflow dan normalisasi format JSON."""
    try:
        teks = (
            raw["outputs"][0]["outputs"][0]
            ["results"]["message"]["data"]["text"]
        )
        logger.warning(
            "DEBUG LANGFLOW - RAW RESPONSE: %s",
            json.dumps(raw, ensure_ascii=False, default=str)[:12000],
        )

        logger.warning(
            "DEBUG LANGFLOW - TEKS OUTPUT: %r",
            teks,
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise LangflowResponsInvalidError(
            "Struktur respons Langflow tidak sesuai."
        ) from exc

    if not isinstance(teks, str) or not teks.strip():
        raise LangflowResponsInvalidError(
            "Teks respons Langflow kosong atau tidak valid."
        )

    data = _ambil_json(teks)

    status_flow = str(
        data.get("status", "TIDAK_DIKETAHUI")
    )

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

        # Mendukung format baru dan format lama.
        nama = str(
            item.get("nama_ditafsirkan")
            or item.get("produk")
            or ""
        ).strip()

        teks_asli = str(
            item.get("teks_asli") or nama
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
            kuantitas = 1

        status_item_raw = item.get("status_item")

        if status_item_raw:
            status_item = str(status_item_raw).strip().upper()
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
                sku=(
                    str(item["sku"])
                    if item.get("sku")
                    else None
                ),
                kuantitas=kuantitas,
                status_item=status_item,
                catatan=str(item.get("catatan", "")),
            )
        )

    return HasilLangflow(
        status_flow=status_flow,
        items=items,
        masalah=(
            [str(m) for m in masalah_raw]
            if isinstance(masalah_raw, list)
            else []
        ),
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

    def jalankan(
        self,
        input_value: str,
        session_id: str,
        umkm_id: str,
        catalog_csv: str,
        memory_csv: str,
    ) -> HasilLangflow:
        """
        Panggil flow Langflow dengan chat pelanggan, katalog,
        dan memori bisnis sebagai input terpisah.

        Raises:
            LangflowTimeoutError: jika request timeout.
            LangflowError: untuk HTTP error atau koneksi gagal.
            LangflowResponsInvalidError: jika respons tidak valid.
        """
        payload = {
            "input_value": input_value,
            "input_type": "chat",
            "output_type": "chat",
            "session_id": str(session_id),
            "tweaks": {
                "UMKMOrderCopilot-zOnHU": {
                    "chat": input_value,
                    "default_umkm": str(umkm_id),
                    "catalog_csv": catalog_csv,
                    "memory_csv": memory_csv,
                }
            },
        }

        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-api-key": self._api_key,
        }

        logger.info(
            "Memanggil Langflow: session_id=%s, input_length=%d",
            session_id,
            len(input_value),
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
                f"Langflow tidak merespons dalam "
                f"{self.TIMEOUT_DETIK} detik."
            ) from exc
        except httpx.RequestError as exc:
            raise LangflowError(
                f"Koneksi ke Langflow gagal: {type(exc).__name__}"
            ) from exc

        if resp.status_code != 200:
            logger.error(
                "Langflow mengembalikan HTTP %d untuk session_id=%s",
                resp.status_code,
                session_id,
            )
            raise LangflowError(
                f"Langflow mengembalikan status HTTP "
                f"{resp.status_code}."
            )

        try:
            raw = resp.json()
        except Exception as exc:
            raise LangflowResponsInvalidError(
                "Respons Langflow bukan JSON yang valid."
            ) from exc

        return parse_respons_langflow(raw)
