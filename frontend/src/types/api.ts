/**
 * Tipe data yang mencerminkan kontrak API backend Django.
 * Semua field diambil dari serializer dan model yang sudah diverifikasi.
 */

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface TokenResponse {
  token: string
}

// ---------------------------------------------------------------------------
// ItemPesanan
// ---------------------------------------------------------------------------

/** Status item setelah parsing AI atau verifikasi operator. */
export type StatusItem =
  | 'DITEMUKAN'
  | 'AMBIGU'
  | 'TIDAK_DITEMUKAN'
  | 'DIKONFIRMASI'

export interface ItemPesanan {
  id: number
  /** ID produk (angka) atau null. Nama produk diambil dari endpoint katalog. */
  produk: number | null
  teks_asli: string
  nama_ditafsirkan: string
  kuantitas: number
  /** String desimal, mis. "65000.00". Jangan dijumlah sebagai float. */
  harga_satuan: string | null
  subtotal: string | null
  hpp_snapshot: string | null
  status_item: StatusItem
  catatan_validasi: string
}

// ---------------------------------------------------------------------------
// Pesanan
// ---------------------------------------------------------------------------

export type StatusPesanan =
  | 'DRAFT'
  | 'MENUNGGU_REVIEW'
  | 'DIKONFIRMASI'
  | 'SELESAI'
  | 'DIBATALKAN'

export interface Pesanan {
  id: number
  umkm_id: string
  nomor_pesanan: string
  nama_pelanggan: string
  teks_chat_asli: string
  status: StatusPesanan
  catatan: string
  item_pesanan: ItemPesanan[]
  dibuat_pada: string
  diperbarui_pada: string
}

/** Response list pesanan dengan paginasi DRF PageNumberPagination. */
export interface PaginatedPesanan {
  count: number
  next: string | null
  previous: string | null
  results: Pesanan[]
}

/** Payload untuk membuat pesanan baru. */
export interface BuatPesananPayload {
  nama_pelanggan: string
  teks_chat_asli: string
  catatan?: string
}

/** Payload untuk verifikasi item. */
export interface VerifikasiItemPayload {
  produk_id: number
  kuantitas: number
}

// ---------------------------------------------------------------------------
// Katalog
// ---------------------------------------------------------------------------

export interface Produk {
  id: number
  umkm_id: string
  sku: string
  nama_produk: string
  kategori: string
  warna: string
  ukuran: string
  harga: string
  stok: number
  aktif: boolean
  diperbarui_pada: string
}

export interface PaginatedProduk {
  count: number
  next: string | null
  previous: string | null
  results: Produk[]
}

// ---------------------------------------------------------------------------
// Error DRF
// ---------------------------------------------------------------------------

/** Error bisnis dari backend: {"detail": "..."} */
export interface DetailError {
  detail: string
}

/** Error validasi serializer DRF: {"field_name": ["pesan"]} */
export type ValidationError = Record<string, string[]>
