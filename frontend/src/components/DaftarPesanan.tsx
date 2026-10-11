import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPesanan, buatPesanan } from '../services/pesananService'
import { BadgeStatusPesanan } from './shared'
import type { BuatPesananPayload, StatusPesanan } from '../types/api'
import PesananDetail from './PesananDetail'

const STATUS_OPTIONS: Array<{ value: StatusPesanan | ''; label: string }> = [
  { value: '', label: 'Semua Status' },
  { value: 'DRAFT', label: 'Draft' },
  { value: 'MENUNGGU_REVIEW', label: 'Menunggu Review' },
  { value: 'DIKONFIRMASI', label: 'Dikonfirmasi' },
  { value: 'SELESAI', label: 'Selesai' },
  { value: 'DIBATALKAN', label: 'Dibatalkan' },
]

export default function DaftarPesanan() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusPesanan | ''>('')
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // Form buat pesanan baru
  const [showForm, setShowForm] = useState(false)
  const [namaPelanggan, setNamaPelanggan] = useState('')
  const [teksChat, setTeksChat] = useState('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['pesanan', statusFilter, page],
    queryFn: () => fetchPesanan({ status: statusFilter || undefined, page }),
  })

  const buatMutation = useMutation({
    mutationFn: (payload: BuatPesananPayload) => buatPesanan(payload),
    onSuccess: (pesanaBaru) => {
      queryClient.invalidateQueries({ queryKey: ['pesanan'] })
      setShowForm(false)
      setNamaPelanggan('')
      setTeksChat('')
      setSelectedId(pesanaBaru.id)
    },
  })

  if (selectedId !== null) {
    return (
      <PesananDetail
        id={selectedId}
        onBack={() => setSelectedId(null)}
      />
    )
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20 }}>Daftar Pesanan</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            padding: '8px 16px', fontSize: 14,
            background: '#2563eb', color: '#fff',
            border: 'none', borderRadius: 4, cursor: 'pointer',
          }}
        >
          {showForm ? 'Batal' : '+ Pesanan Baru'}
        </button>
      </div>

      {/* Form buat pesanan */}
      {showForm && (
        <div style={{
          background: '#f8fafc', border: '1px solid #e2e8f0',
          borderRadius: 8, padding: 20, marginBottom: 24,
        }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>Buat Pesanan Baru</h3>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
              Nama Pelanggan <span style={{ color: '#dc2626' }}>*</span>
            </label>
            <input
              value={namaPelanggan}
              onChange={(e) => setNamaPelanggan(e.target.value)}
              placeholder="Nama pelanggan"
              style={{ width: '100%', padding: '8px 10px', fontSize: 13, boxSizing: 'border-box' }}
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
              Teks Chat Pelanggan <span style={{ color: '#dc2626' }}>*</span>
            </label>
            <textarea
              value={teksChat}
              onChange={(e) => setTeksChat(e.target.value)}
              placeholder="Salin percakapan chat di sini..."
              rows={4}
              style={{ width: '100%', padding: '8px 10px', fontSize: 13, boxSizing: 'border-box', resize: 'vertical' }}
            />
          </div>
          {buatMutation.isError && (
            <p style={{ color: '#dc2626', fontSize: 13, margin: '0 0 12px' }}>
              Gagal membuat pesanan. Pastikan semua field terisi.
            </p>
          )}
          <button
            onClick={() => buatMutation.mutate({ nama_pelanggan: namaPelanggan, teks_chat_asli: teksChat })}
            disabled={buatMutation.isPending || !namaPelanggan.trim() || !teksChat.trim()}
            style={{
              padding: '8px 20px', fontSize: 13,
              background: buatMutation.isPending ? '#94a3b8' : '#2563eb',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: buatMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {buatMutation.isPending ? 'Menyimpan...' : 'Simpan'}
          </button>
        </div>
      )}

      {/* Filter status */}
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => { setStatusFilter(opt.value); setPage(1) }}
            style={{
              padding: '4px 12px', fontSize: 13, borderRadius: 4,
              border: '1px solid #cbd5e1',
              background: statusFilter === opt.value ? '#2563eb' : '#fff',
              color: statusFilter === opt.value ? '#fff' : '#374151',
              cursor: 'pointer',
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Daftar */}
      {isLoading && <p style={{ color: '#64748b' }}>Memuat...</p>}
      {isError && <p style={{ color: '#dc2626' }}>Gagal memuat data pesanan.</p>}

      {data && data.results.length === 0 && (
        <p style={{ color: '#64748b', textAlign: 'center', padding: '40px 0' }}>
          Belum ada pesanan.
        </p>
      )}

      {data && data.results.map((p) => (
        <div
          key={p.id}
          onClick={() => setSelectedId(p.id)}
          style={{
            background: '#fff', border: '1px solid #e2e8f0',
            borderRadius: 8, padding: 16, marginBottom: 10,
            cursor: 'pointer', transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#2563eb')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#e2e8f0')}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontWeight: 600, fontSize: 14 }}>{p.nomor_pesanan}</span>
              <span style={{ marginLeft: 12, color: '#64748b', fontSize: 13 }}>
                {p.nama_pelanggan}
              </span>
            </div>
            <BadgeStatusPesanan status={p.status} />
          </div>
          <p style={{
            margin: '8px 0 0', fontSize: 13, color: '#475569',
            overflow: 'hidden', textOverflow: 'ellipsis',
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
          }}>
            {p.teks_chat_asli}
          </p>
          <p style={{ margin: '6px 0 0', fontSize: 12, color: '#94a3b8' }}>
            {p.item_pesanan.length} item •{' '}
            {new Date(p.dibuat_pada).toLocaleString('id-ID')}
          </p>
        </div>
      ))}

      {/* Paginasi */}
      {data && (data.previous || data.next) && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!data.previous}
            style={{ padding: '6px 14px', fontSize: 13, cursor: 'pointer' }}
          >
            ← Sebelumnya
          </button>
          <span style={{ padding: '6px 12px', fontSize: 13, color: '#64748b' }}>
            Hal. {page} • {data.count} total
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!data.next}
            style={{ padding: '6px 14px', fontSize: 13, cursor: 'pointer' }}
          >
            Berikutnya →
          </button>
        </div>
      )}
    </div>
  )
}
