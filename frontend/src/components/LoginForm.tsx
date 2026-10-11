import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'

interface Props {
  onSuccess?: () => void
  onSwitchToRegister: () => void
}

export default function LoginForm({ onSuccess, onSwitchToRegister }: Props) {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await login(username.trim(), password)
      onSuccess?.()
    } catch {
      setError('Tidak dapat masuk. Periksa username, password, dan koneksi server.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-brand">
        <div className="brand-topline">
          <span className="brand-mark">OC</span>
          <span className="brand-name">UMKM ORDER COPILOT</span>
        </div>

        <div className="brand-intro">
          <span className="brand-pill"><span className="brand-pill-dot" /> WORKSPACE UNTUK UMKM</span>
          <h1>Kelola pesanan <span>lebih mudah.</span></h1>
          <p className="brand-description">
            Ubah percakapan pelanggan menjadi pesanan terstruktur. Hemat waktu,
            kurangi kesalahan, dan tetap pegang kendali atas setiap transaksi.
          </p>
        </div>

        <div className="brand-features">
          <article className="brand-feature">
            <span className="feature-icon feature-indigo">↗</span>
            <div>
              <strong>Catat pesanan dari chat</strong>
              <p>Kurangi pencatatan manual dari percakapan pelanggan.</p>
            </div>
          </article>
          <article className="brand-feature">
            <span className="feature-icon feature-violet">✓</span>
            <div>
              <strong>Periksa hasil AI</strong>
              <p>Validasi produk dan jumlah sebelum pesanan dikonfirmasi.</p>
            </div>
          </article>
          <article className="brand-feature">
            <span className="feature-icon feature-pink">▦</span>
            <div>
              <strong>Pantau dalam satu tempat</strong>
              <p>Lihat status pesanan dengan alur kerja yang lebih rapi.</p>
            </div>
          </article>
        </div>

        <p className="brand-footer">Dibuat untuk membantu operasional usaha sehari-hari.</p>
      </section>

      <section className="auth-panel">
        <div className="auth-form-container">
          <div className="mobile-brand">
            <span className="brand-mark">OC</span>
            <span className="brand-name">UMKM ORDER COPILOT</span>
          </div>

          <span className="auth-eyebrow">SELAMAT DATANG KEMBALI</span>
          <h2>Masuk ke akunmu</h2>
          <p className="auth-subtitle">
            Masuk untuk melanjutkan pengelolaan pesanan usahamu.
          </p>

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="form-field">
              <label htmlFor="login_username">Username</label>
              <input
                id="login_username"
                type="text"
                placeholder="Masukkan username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
                disabled={loading}
              />
            </div>

            <div className="form-field">
              <label htmlFor="login_password">Password</label>
              <div className="password-input-wrap">
                <input
                  id="login_password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Masukkan password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
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
            </div>

            {error && <div className="auth-error" role="alert">{error}</div>}

            <button className="auth-submit" type="submit" disabled={loading}>
              {loading ? 'Memproses...' : 'Masuk'}
              {!loading && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <p className="auth-switch">
            Belum punya akun?{' '}
            <button type="button" className="auth-link" onClick={onSwitchToRegister} disabled={loading}>
              Daftar UMKM
            </button>
          </p>
          <p className="auth-legal">Akses ruang kerja usahamu dengan aman dan teratur.</p>
        </div>
      </section>
    </main>
  )
}
