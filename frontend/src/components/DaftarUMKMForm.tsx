import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import type { DaftarPayload } from '../services/pesananService'

interface Props {
  onSwitchToLogin: () => void
}

export default function DaftarUMKMForm({ onSwitchToLogin }: Props) {
  const { register } = useAuth()

  const [form, setForm] = useState<DaftarPayload>({
    username: '',
    password: '',
    nama_umkm: '',
    email: '',
  })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  function updateField(
    field: keyof DaftarPayload,
    value: string
  ) {
    setForm((previous) => ({
      ...previous,
      [field]: value,
    }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      await register({
        ...form,
        username: form.username.trim(),
        nama_umkm: form.nama_umkm.trim(),
        email: form.email?.trim() ?? '',
      })
    } catch (err: unknown) {
      const errorData = (
        err as {
          response?: {
            data?: Record<string, string | string[]>
          }
        }
      ).response?.data

      if (errorData) {
        const messages = Object.entries(errorData)
          .map(([field, value]) => {
            const message = Array.isArray(value)
              ? value.join(' ')
              : value

            const labels: Record<string, string> = {
              username: 'Username',
              password: 'Password',
              nama_umkm: 'Nama UMKM',
              email: 'Email',
              non_field_errors: 'Pendaftaran',
              detail: 'Pendaftaran',
            }

            return `${labels[field] ?? field}: ${message}`
          })

        setError(messages.join('\n'))
      } else {
        setError('Pendaftaran gagal. Periksa koneksi dan coba lagi.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-brand">
        <div className="brand-mark">OC</div>
        <p className="brand-eyebrow">UMKM ORDER COPILOT</p>
        <h1>Kelola pesanan lebih mudah.</h1>
        <p className="brand-description">
          Ubah percakapan pelanggan menjadi pesanan yang
          terstruktur. Kamu tetap memegang kendali atas
          setiap transaksi.
        </p>

        <div className="brand-feature">
          <span>01</span>
          <div>
            <strong>Catat pesanan</strong>
            <p>Mulai dari chat pelanggan.</p>
          </div>
        </div>

        <div className="brand-feature">
          <span>02</span>
          <div>
            <strong>Periksa hasil AI</strong>
            <p>Validasi produk dan jumlah sebelum konfirmasi.</p>
          </div>
        </div>

        <div className="brand-feature">
          <span>03</span>
          <div>
            <strong>Kelola lebih teratur</strong>
            <p>Awasi status pesanan dalam satu dashboard.</p>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-form-container">
          <p className="auth-eyebrow">MULAI BERSAMA KAMI</p>
          <h2>Buat akun UMKM</h2>
          <p className="auth-subtitle">
            Daftarkan usaha kamu untuk mulai mengelola pesanan.
          </p>

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="form-field">
              <label htmlFor="nama_umkm">Nama usaha</label>
              <input
                id="nama_umkm"
                type="text"
                placeholder="Contoh: Toko Berkah"
                value={form.nama_umkm}
                onChange={(event) =>
                  updateField('nama_umkm', event.target.value)
                }
                maxLength={100}
                autoComplete="organization"
                required
                disabled={loading}
              />
            </div>

            <div className="form-field">
              <label htmlFor="register_username">Username</label>
              <input
                id="register_username"
                type="text"
                placeholder="Buat username"
                value={form.username}
                onChange={(event) =>
                  updateField('username', event.target.value)
                }
                maxLength={150}
                autoComplete="username"
                required
                disabled={loading}
              />
            </div>

            <div className="form-field">
              <label htmlFor="register_email">
                Email <span className="optional-label">Opsional</span>
              </label>
              <input
                id="register_email"
                type="email"
                placeholder="nama@email.com"
                value={form.email}
                onChange={(event) =>
                  updateField('email', event.target.value)
                }
                autoComplete="email"
                disabled={loading}
              />
            </div>

            <div className="form-field">
              <label htmlFor="register_password">Password</label>
              <div className="password-input-wrap">
                <input
                  id="register_password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Buat password yang kuat"
                  value={form.password}
                  onChange={(event) =>
                    updateField('password', event.target.value)
                  }
                  autoComplete="new-password"
                  maxLength={128}
                  required
                  disabled={loading}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword((previous) => !previous)}
                  disabled={loading}
                  aria-label={showPassword ? 'Sembunyikan password' : 'Lihat password'}
                >
                  {showPassword ? 'Sembunyikan' : 'Lihat'}
                </button>
              </div>
              <p className="field-hint">
                Gunakan password yang kuat dan tidak mudah ditebak.
              </p>
            </div>

            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}

            <button
              className="auth-submit"
              type="submit"
              disabled={loading}
            >
              {loading ? 'Mendaftarkan akun...' : 'Daftar sekarang'}
              {!loading && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <p className="auth-switch">
            Sudah punya akun?{' '}
            <button
              type="button"
              className="auth-link"
              onClick={onSwitchToLogin}
              disabled={loading}
            >
              Masuk
            </button>
          </p>

          <p className="auth-legal">
            Dengan mendaftar, kamu membuat akun dan ruang usaha
            baru di UMKM Order Copilot.
          </p>
        </div>
      </section>
    </main>
  )
}
