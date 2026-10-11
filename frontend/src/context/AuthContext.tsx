/**
 * AuthContext — menyimpan token dan state login di seluruh aplikasi.
 *
 * Token disimpan di localStorage. Komponen yang butuh token
 * cukup panggil useAuth().
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import { login as apiLogin } from '../services/pesananService'

interface AuthContextValue {
  token: string | null
  isLoggedIn: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem('auth_token')
  )

  const login = useCallback(async (username: string, password: string) => {
    const tok = await apiLogin(username, password)
    localStorage.setItem('auth_token', tok)
    setToken(tok)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token')
    setToken(null)
  }, [])

  return (
    <AuthContext.Provider value={{ token, isLoggedIn: !!token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth harus digunakan di dalam AuthProvider')
  return ctx
}
