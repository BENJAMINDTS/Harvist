/**
 * Configuración de Vite para el frontend de Harvist.
 *
 * Proxy /api y /ws hacia el backend FastAPI en desarrollo para evitar CORS.
 * En producción el proxy lo maneja el servidor inverso (nginx / caddy).
 *
 * @author BenjaminDTS | Carlos Vico
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
