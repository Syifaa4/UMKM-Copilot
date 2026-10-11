import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy API ke Django selama development — menghindari masalah CORS
      // saat membuka langsung via browser tanpa header Authorization.
      // Tetap kirim header Authorization dari frontend — proxy hanya meneruskan.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
