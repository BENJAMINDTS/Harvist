/**
 * Configuración de Vitest para el frontend de Harvist.
 *
 * Usa jsdom como entorno DOM, alias @/ igual que vite.config.ts,
 * y carga el setup de @testing-library/jest-dom antes de cada suite.
 *
 * @author BenjaminDTS | Carlos Vico
 */
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/api/**', 'src/hooks/**'],
    },
  },
})
