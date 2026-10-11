import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginForm from './components/LoginForm'
import DaftarPesanan from './components/DaftarPesanan'

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

  if (!isLoggedIn) {
    return <LoginForm />
  }

  return (
    <div>
      {/* Navbar sederhana */}
      <nav style={{
        background: '#1e293b', color: '#f1f5f9',
        padding: '0 20px', display: 'flex',
        justifyContent: 'space-between', alignItems: 'center',
        height: 48,
      }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>UMKM Order Copilot</span>
        <button
          onClick={logout}
          style={{
            background: 'none', border: '1px solid #475569',
            color: '#cbd5e1', padding: '4px 12px', fontSize: 13,
            borderRadius: 4, cursor: 'pointer',
          }}
        >
          Keluar
        </button>
      </nav>

      <DaftarPesanan />
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
