/*
 * vite.config.ts
 * Vite build configuration for the FCC Dashboard frontend.
 * https://vite.dev/config/
 *
 * Also carries the dev-server proxy (forwards backend routes to
 * http://localhost:8000 unchanged, no changeOrigin/header rewriting, so the
 * browser's Sec-Fetch-Site header stays same-origin for the backend's
 * same-site check on /control/start and /control/stop) and the Vitest
 * config (test key, enabled by the triple-slash types reference below).
 */

/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/status': 'http://localhost:8000',
      '/requests': 'http://localhost:8000',
      '/stats': 'http://localhost:8000',
      '/pricing': 'http://localhost:8000',
      '/control': 'http://localhost:8000',
      '/db': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
