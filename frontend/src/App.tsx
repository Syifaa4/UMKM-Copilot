import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginForm from './components/LoginForm'
import DaftarUMKMForm from './components/DaftarUMKMForm'
import DaftarPesanan from './components/DaftarPesanan'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

function AppShell() {
  const { isLoggedIn, logout } = useAuth()
  const [showRegister, setShowRegister] = useState(false)

  if (!isLoggedIn) {
    return showRegister ? (
      <DaftarUMKMForm onSwitchToLogin={() => setShowRegister(false)} />
    ) : (
      <LoginForm onSwitchToRegister={() => setShowRegister(true)} />
    )
  }

  return (
    <div className="app-shell">
      <header className="app-navbar">
        <a className="app-brand" href="/" aria-label="UMKM Order Copilot">
          <span className="app-brand-mark">OC</span>
          <span className="app-brand-text">
            <strong>Order Copilot</strong>
            <small>UMKM WORKSPACE</small>
          </span>
        </a>
        <button className="logout-button" onClick={logout}>
          Keluar <span aria-hidden="true">↗</span>
        </button>
      </header>
      <main className="app-main">
        <DaftarPesanan />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </QueryClientProvider>
  )
}
