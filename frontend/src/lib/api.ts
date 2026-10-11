/**
 * Axios instance terpusat untuk semua request ke Django backend.
 *
 * - Base URL diambil dari VITE_API_BASE_URL (env) atau default ke /api
 * - Token disimpan di localStorage dengan key 'auth_token'
 * - Interceptor menyisipkan header Authorization secara otomatis
 * - 401 dari server: hapus token dan redirect ke /login
 *
 * JANGAN simpan secret lain (Langflow key, DB password, dsb.) di sini.
 * Token pengguna yang aktif login adalah satu-satunya secret di frontend.
 */

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Sisipkan token ke setiap request jika tersedia
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Token ${token}`
  }
  return config
})

// Tangani 401 global — hapus token, redirect ke login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
