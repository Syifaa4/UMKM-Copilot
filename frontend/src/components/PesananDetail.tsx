import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchPesananDetail,
  prosesLangflow,
  verifikasiItem,
  ajukanReview,
  konfirmasiPesanan,
  selesaikanPesanan,
  batalkanPesanan,
  fetchProduk,
} from '../services/pesananService'
import { BadgeStatusPesanan, BadgeStatusItem, formatRupiah } from './shared'
import type { Pesanan, VerifikasiItemPayload } from '../types/api'
import axios from 'axios'

interface Props {
  id: number
  onBack: () => void
}

// ---------------------------------------------------------------------------
// Sub-komponen: panel verifikasi item
// ---------------------------------------------------------------------------

interface VerifikasiPanelProps {
  pesananId: number
  itemId: number
  teksAsli: string
  umkmId: string
  onDone: () => void
}

function VerifikasiPanel({ pesananId, itemId, teksAsli, umkmId, onDone }: VerifikasiPanelProps) {
  const queryClient = useQueryClient()
  const [produkId, setProdukId] = useState('')
  const [kuantitas, setKuantitas] = useState('1')
  const [error, setError] = useState<string | null>(null)

  const { data: katalogData } = useQuery({
    queryKey: ['katalog', umkmId],
    queryFn: () => fetchProduk({ aktif: 'true', page_size: 100 }),
  })

  const mutation = useMutation({
    mutationFn: (payload: VerifikasiItemPayload) =>
      verifikasiItem(pesananId, itemId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pesanan-detail', pesananId] })
      onDone()
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail ?? 'Gagal memverifikasi item.')
      }
    },
  })

  return (
    <div style={{
      background: '#fefce8', border: '1px solid #fde68a',
      borderRadius: 6, padding: 12, marginTop: 8,
    }}>
      <p style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600 }}>
        Verifikasi: &ldquo;{teksAsli}&rdquo;
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 3 }}>Produk</label>
          <select
            value={produkId}
            onChange={(e) => setProdukId(e.target.value)}
            style={{ padding: '6px 8px', fontSize: 13, minWidth: 200 }}
          >
            <option value="">-- Pilih produk --</option>
            {katalogData?.results.map((p) => (
              <option key={p.id} value={p.id}>
                [{p.sku}] {p.nama_produk} {p.warna} {p.ukuran} — {formatRupiah(p.harga)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 3 }}>Kuantitas</label>
          <input
            type="number"
            value={kuantitas}
            min={1}
            onChange={(e) => setKuantitas(e.target.value)}
            style={{ padding: '6px 8px', fontSize: 13, width: 70 }}
          />
        </div>
        <button
          onClick={() => {
            setError(null)
            mutation.mutate({ produk_id: Number(produkId), kuantitas: Number(kuantitas) })
          }}
          disabled={!produkId || Number(kuantitas) < 1 || mutation.isPending}
          style={{
            padding: '6px 14px', fontSize: 13, background: '#16a34a',
            color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer',
          }}
        >
          {mutation.isPending ? 'Menyimpan...' : 'Simpan'}
        </button>
        <button
          onClick={onDone}
          style={{
            padding: '6px 14px', fontSize: 13, background: '#e2e8f0',
            border: 'none', borderRadius: 4, cursor: 'pointer',
          }}
        >
          Batal
        </button>
      </div>
      {error && <p style={{ color: '#dc2626', fontSize: 12, margin: '6px 0 0' }}>{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Komponen utama: detail pesanan
// ---------------------------------------------------------------------------

export default function PesananDetail({ id, onBack }: Props) {
  const queryClient = useQueryClient()
  const [verifikasiItemId, setVerifikasiItemId] = useState<number | null>(null)
  const [aksiError, setAksiError] = useState<string | null>(null)

  const { data: pesanan, isLoading, isError } = useQuery<Pesanan>({
    queryKey: ['pesanan-detail', id],
    queryFn: () => fetchPesananDetail(id),
  })

  function onMutationSuccess() {
    queryClient.invalidateQueries({ queryKey: ['pesanan-detail', id] })
    queryClient.invalidateQueries({ queryKey: ['pesanan'] })
    setAksiError(null)
  }

  function onMutationError(err: unknown, label: string) {
    if (axios.isAxiosError(err)) {
      setAksiError(err.response?.data?.detail ?? `Gagal: ${label}`)
    }
  }

  const mutProses = useMutation({
    mutationFn: () => prosesLangflow(id),
    onSuccess: onMutationSuccess,
    onError: (err) => onMutationError(err, 'proses AI'),
  })

  const mutAjukan = useMutation({
    mutationFn: () => ajukanReview(id),
    onSuccess: onMutationSuccess,
    onError: (err) => onMutationError(err, 'ajukan review'),
  })

  const mutKonfirmasi = useMutation({
    mutationFn: () => konfirmasiPesanan(id),
    onSuccess: onMutationSuccess,
    onError: (err) => onMutationError(err, 'konfirmasi'),
  })

  const mutSelesai = useMutation({
    mutationFn: () => selesaikanPesanan(id),
    onSuccess: onMutationSuccess,
    onError: (err) => onMutationError(err, 'selesai'),
  })

  const mutBatalkan = useMutation({
    mutationFn: () => batalkanPesanan(id),
    onSuccess: onMutationSuccess,
    onError: (err) => onMutationError(err, 'batalkan'),
  })

  const anyPending =
    mutProses.isPending || mutAjukan.isPending || mutKonfirmasi.isPending ||
    mutSelesai.isPending || mutBatalkan.isPending

  if (isLoading) return <div style={{ padding: 32, color: '#64748b' }}>Memuat...</div>
  if (isError || !pesanan) return <div style={{ padding: 32, color: '#dc2626' }}>Gagal memuat pesanan.</div>

  const adaItemBelumValid = pesanan.item_pesanan.some(
    (i) => i.status_item === 'AMBIGU' || i.status_item === 'TIDAK_DITEMUKAN'
  )

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      {/* Navigasi kembali */}
      <button
        onClick={onBack}
        style={{
          background: 'none', border: 'none', color: '#2563eb',
          cursor: 'pointer', fontSize: 14, padding: '0 0 16px', display: 'block',
        }}
      >
        ← Kembali ke daftar
      </button>

      {/* Header pesanan */}
      <div style={{
        background: '#fff', border: '1px solid #e2e8f0',
        borderRadius: 8, padding: 20, marginBottom: 20,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h2 style={{ margin: '0 0 4px', fontSize: 18 }}>{pesanan.nomor_pesanan}</h2>
            <p style={{ margin: 0, color: '#64748b', fontSize: 14 }}>
              Pelanggan: <strong>{pesanan.nama_pelanggan}</strong>
            </p>
          </div>
          <BadgeStatusPesanan status={pesanan.status} />
        </div>

        <div style={{
          background: '#f8fafc', borderRadius: 6, padding: '10px 12px',
          marginTop: 14, fontSize: 13, color: '#475569', whiteSpace: 'pre-wrap',
        }}>
          <strong style={{ display: 'block', marginBottom: 4, color: '#374151' }}>
            Teks Chat Asli:
          </strong>
          {pesanan.teks_chat_asli}
        </div>

        {pesanan.catatan && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: '#64748b' }}>
            <strong>Catatan:</strong> {pesanan.catatan}
          </p>
        )}
      </div>

      {/* Aksi */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {/* Proses AI — hanya untuk DRAFT tanpa item */}
        {pesanan.status === 'DRAFT' && pesanan.item_pesanan.length === 0 && (
          <button
            onClick={() => { setAksiError(null); mutProses.mutate() }}
            disabled={anyPending}
            style={{
              padding: '8px 16px', fontSize: 14, background: '#7c3aed',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: anyPending ? 'not-allowed' : 'pointer', opacity: anyPending ? 0.7 : 1,
            }}
          >
            {mutProses.isPending ? '⏳ Memproses AI... (hingga 60 detik)' : '🤖 Proses dengan AI'}
          </button>
        )}

        {/* Ajukan review — DRAFT dengan item */}
        {pesanan.status === 'DRAFT' && pesanan.item_pesanan.length > 0 && (
          <button
            onClick={() => { setAksiError(null); mutAjukan.mutate() }}
            disabled={anyPending}
            style={{
              padding: '8px 16px', fontSize: 14, background: '#0891b2',
              color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer',
            }}
          >
            Ajukan Review
          </button>
        )}

        {/* Konfirmasi — hanya aktif jika MENUNGGU_REVIEW dan tidak ada item belum valid */}
        {pesanan.status === 'MENUNGGU_REVIEW' && (
          <button
            onClick={() => { setAksiError(null); mutKonfirmasi.mutate() }}
            disabled={anyPending || adaItemBelumValid}
            title={adaItemBelumValid ? 'Selesaikan semua item AMBIGU/TIDAK_DITEMUKAN dahulu' : ''}
            style={{
              padding: '8px 16px', fontSize: 14, background: '#16a34a',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: (anyPending || adaItemBelumValid) ? 'not-allowed' : 'pointer',
              opacity: adaItemBelumValid ? 0.5 : 1,
            }}
          >
            ✓ Konfirmasi Pesanan
          </button>
        )}

        {/* Selesai */}
        {pesanan.status === 'DIKONFIRMASI' && (
          <button
            onClick={() => { setAksiError(null); mutSelesai.mutate() }}
            disabled={anyPending}
            style={{
              padding: '8px 16px', fontSize: 14, background: '#2563eb',
              color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer',
            }}
          >
            Tandai Selesai
          </button>
        )}

        {/* Batalkan — semua status kecuali DIBATALKAN */}
        {pesanan.status !== 'DIBATALKAN' && (
          <button
            onClick={() => {
              if (confirm('Batalkan pesanan ini?')) {
                setAksiError(null)
                mutBatalkan.mutate()
              }
            }}
            disabled={anyPending}
            style={{
              padding: '8px 16px', fontSize: 14, background: '#fff',
              color: '#dc2626', border: '1px solid #fca5a5',
              borderRadius: 4, cursor: 'pointer',
            }}
          >
            Batalkan
          </button>
        )}
      </div>

      {/* Error aksi */}
      {aksiError && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fca5a5',
          borderRadius: 6, padding: '10px 14px', marginBottom: 16, fontSize: 13, color: '#dc2626',
        }}>
          {aksiError}
        </div>
      )}

      {/* Peringatan item belum valid */}
      {pesanan.status === 'MENUNGGU_REVIEW' && adaItemBelumValid && (
        <div style={{
          background: '#fffbeb', border: '1px solid #fde68a',
          borderRadius: 6, padding: '10px 14px', marginBottom: 16, fontSize: 13, color: '#92400e',
        }}>
          ⚠️ Ada item <strong>AMBIGU</strong> atau <strong>TIDAK DITEMUKAN</strong>.
          Verifikasi semua item sebelum konfirmasi.
        </div>
      )}

      {/* Daftar item */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', borderBottom: '1px solid #e2e8f0', fontWeight: 600, fontSize: 14 }}>
          Item Pesanan ({pesanan.item_pesanan.length})
        </div>

        {pesanan.item_pesanan.length === 0 && (
          <p style={{ padding: 20, color: '#94a3b8', fontSize: 13, margin: 0 }}>
            Belum ada item. Gunakan tombol &ldquo;Proses dengan AI&rdquo; untuk mengekstrak item dari teks chat.
          </p>
        )}

        {pesanan.item_pesanan.map((item) => {
          const perluVerifikasi =
            (item.status_item === 'AMBIGU' || item.status_item === 'TIDAK_DITEMUKAN') &&
            pesanan.status === 'MENUNGGU_REVIEW'

          return (
            <div
              key={item.id}
              style={{
                padding: '14px 16px',
                borderBottom: '1px solid #f1f5f9',
                background: perluVerifikasi ? '#fffbeb' : '#fff',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{item.teks_asli}</span>
                  {item.nama_ditafsirkan && (
                    <span style={{ marginLeft: 8, fontSize: 12, color: '#64748b' }}>
                      → {item.nama_ditafsirkan}
                    </span>
                  )}
                </div>
                <BadgeStatusItem status={item.status_item} />
              </div>

              <div style={{ display: 'flex', gap: 16, marginTop: 6, fontSize: 13, color: '#475569', flexWrap: 'wrap' }}>
                <span>Qty: <strong>{item.kuantitas}</strong></span>
                <span>Harga: <strong>{formatRupiah(item.harga_satuan)}</strong></span>
                <span>Subtotal: <strong>{formatRupiah(item.subtotal)}</strong></span>
              </div>

              {item.catatan_validasi && (
                <p style={{ margin: '6px 0 0', fontSize: 12, color: '#92400e' }}>
                  ⚠ {item.catatan_validasi}
                </p>
              )}

              {/* Tombol verifikasi */}
              {perluVerifikasi && verifikasiItemId !== item.id && (
                <button
                  onClick={() => setVerifikasiItemId(item.id)}
                  style={{
                    marginTop: 8, padding: '5px 12px', fontSize: 12,
                    background: '#d97706', color: '#fff',
                    border: 'none', borderRadius: 4, cursor: 'pointer',
                  }}
                >
                  Verifikasi Item
                </button>
              )}

              {/* Panel verifikasi */}
              {verifikasiItemId === item.id && (
                <VerifikasiPanel
                  pesananId={id}
                  itemId={item.id}
                  teksAsli={item.teks_asli}
                  umkmId={pesanan.umkm_id}
                  onDone={() => setVerifikasiItemId(null)}
                />
              )}
            </div>
          )
        })}
      </div>

      <p style={{ marginTop: 12, fontSize: 12, color: '#94a3b8' }}>
        Dibuat: {new Date(pesanan.dibuat_pada).toLocaleString('id-ID')} •{' '}
        Diperbarui: {new Date(pesanan.diperbarui_pada).toLocaleString('id-ID')}
      </p>
    </div>
  )
}
