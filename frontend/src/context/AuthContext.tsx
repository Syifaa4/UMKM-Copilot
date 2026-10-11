/**
 * AuthContext — mengelola autentikasi pengguna.
 * Token disimpan di localStorage agar sesi login tetap tersedia
 * ketika halaman dimuat ulang.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'

import {
  login as apiLogin,
  daftarAkun,
} from '../services/pesananService'

import type {
  DaftarPayload,
  DaftarResponse,
} from '../services/pesananService'

interface AuthContextValue {
  token: string | null
  isLoggedIn: boolean
  login: (username: string, password: string) => Promise<void>
  register: (payload: DaftarPayload) => Promise<DaftarResponse>
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

  const register = useCallback(async (payload: DaftarPayload) => {
    const result = await daftarAkun(payload)

    localStorage.setItem('auth_token', result.token)
    setToken(result.token)

    return result
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token')
    setToken(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        token,
        isLoggedIn: !!token,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)

  if (!ctx) {
    throw new Error('useAuth harus digunakan di dalam AuthProvider')
  }

  return ctx
}
