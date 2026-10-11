/**
 * Semua fungsi pemanggilan API ke backend.
 * Gunakan fungsi-fungsi ini dari React Query hooks — jangan panggil langsung dari komponen.
 */

import { api } from '../lib/api'
import type {
  BuatPesananPayload,
  PaginatedPesanan,
  PaginatedProduk,
  Pesanan,
  TokenResponse,
  VerifikasiItemPayload,
} from '../types/api'

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function login(username: string, password: string): Promise<string> {
  const resp = await api.post<TokenResponse>('/auth/token/', { username, password })
  return resp.data.token
}

// ---------------------------------------------------------------------------
// Pesanan
// ---------------------------------------------------------------------------

export async function fetchPesanan(params?: {
  status?: string
  page?: number
  page_size?: number
}): Promise<PaginatedPesanan> {
  const resp = await api.get<PaginatedPesanan>('/pesanan/pesanan/', { params })
  return resp.data
}

export async function fetchPesananDetail(id: number): Promise<Pesanan> {
  const resp = await api.get<Pesanan>(`/pesanan/pesanan/${id}/`)
  return resp.data
}

export async function buatPesanan(payload: BuatPesananPayload): Promise<Pesanan> {
  const resp = await api.post<Pesanan>('/pesanan/pesanan/', payload)
  return resp.data
}

export async function prosesLangflow(id: number): Promise<Pesanan> {
  const resp = await api.post<Pesanan>(`/pesanan/pesanan/${id}/proses-langflow/`)
  return resp.data
}

export async function verifikasiItem(
  pesananId: number,
  itemId: number,
  payload: VerifikasiItemPayload
): Promise<Pesanan> {
  const resp = await api.patch<Pesanan>(
    `/pesanan/pesanan/${pesananId}/items/${itemId}/verifikasi/`,
    payload
  )
  return resp.data
}

export async function ajukanReview(id: number): Promise<Pesanan> {
  const resp = await api.post<Pesanan>(`/pesanan/pesanan/${id}/ajukan-review/`)
  return resp.data
}

export async function konfirmasiPesanan(id: number): Promise<Pesanan> {
  const resp = await api.post<Pesanan>(`/pesanan/pesanan/${id}/konfirmasi/`)
  return resp.data
}

export async function selesaikanPesanan(id: number): Promise<Pesanan> {
  const resp = await api.post<Pesanan>(`/pesanan/pesanan/${id}/selesai/`)
  return resp.data
}

export async function batalkanPesanan(id: number): Promise<Pesanan> {
  const resp = await api.post<Pesanan>(`/pesanan/pesanan/${id}/batalkan/`)
  return resp.data
}

// ---------------------------------------------------------------------------
// Katalog
// ---------------------------------------------------------------------------

export async function fetchProduk(params?: {
  search?: string
  kategori?: string
  aktif?: string
  page?: number
  page_size?: number
}): Promise<PaginatedProduk> {
  const resp = await api.get<PaginatedProduk>('/katalog/produk/', { params })
  return resp.data
}
