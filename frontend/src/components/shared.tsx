import type { StatusItem, StatusPesanan } from '../types/api'

const LABEL_STATUS_PESANAN: Record<StatusPesanan, string> = {
  DRAFT: 'Draft',
  MENUNGGU_REVIEW: 'Menunggu Review',
  DIKONFIRMASI: 'Dikonfirmasi',
  SELESAI: 'Selesai',
  DIBATALKAN: 'Dibatalkan',
}

const WARNA_STATUS_PESANAN: Record<StatusPesanan, string> = {
  DRAFT: '#64748b',
  MENUNGGU_REVIEW: '#d97706',
  DIKONFIRMASI: '#2563eb',
  SELESAI: '#16a34a',
  DIBATALKAN: '#dc2626',
}

const LABEL_STATUS_ITEM: Record<StatusItem, string> = {
  DITEMUKAN: 'Ditemukan',
  AMBIGU: 'Ambigu',
  TIDAK_DITEMUKAN: 'Tidak Ditemukan',
  DIKONFIRMASI: 'Dikonfirmasi',
}

const WARNA_STATUS_ITEM: Record<StatusItem, string> = {
  DITEMUKAN: '#16a34a',
  AMBIGU: '#d97706',
  TIDAK_DITEMUKAN: '#dc2626',
  DIKONFIRMASI: '#2563eb',
}

interface BadgeStatusPesananProps {
  status: StatusPesanan
}

export function BadgeStatusPesanan({ status }: BadgeStatusPesananProps) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        background: WARNA_STATUS_PESANAN[status] + '1a',
        color: WARNA_STATUS_PESANAN[status],
        border: `1px solid ${WARNA_STATUS_PESANAN[status]}40`,
      }}
    >
      {LABEL_STATUS_PESANAN[status]}
    </span>
  )
}

interface BadgeStatusItemProps {
  status: StatusItem
}

export function BadgeStatusItem({ status }: BadgeStatusItemProps) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        background: WARNA_STATUS_ITEM[status] + '1a',
        color: WARNA_STATUS_ITEM[status],
        border: `1px solid ${WARNA_STATUS_ITEM[status]}40`,
      }}
    >
      {LABEL_STATUS_ITEM[status]}
    </span>
  )
}

/** Format string desimal dari API menjadi format Rupiah. */
export function formatRupiah(nilai: string | null | undefined): string {
  if (nilai == null || nilai === '') return '—'
  const angka = parseFloat(nilai)
  if (isNaN(angka)) return nilai
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
  }).format(angka)
}
