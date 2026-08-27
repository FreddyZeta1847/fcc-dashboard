/*
 * vite.config.ts
 * Vite build configuration for the FCC Dashboard frontend.
 * https://vite.dev/config/
 *
 * Also carries the dev-server proxy (forwards backend routes to the backend
 * unchanged, no changeOrigin/header rewriting, so the browser's Sec-Fetch-Site
 * header stays same-origin for the backend's same-site check on /control/start
 * and /control/stop) and the Vitest config (test key, enabled by the
 * triple-slash types reference below).
 *
 * The backend prefers port 8000 but steps to the next free one when something
 * already holds it, so the target is overridable: set FCC_DASHBOARD_PORT to
 * the port the backend actually reported before running `npm run dev`.
 */

/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = `http://localhost:${process.env.FCC_DASHBOARD_PORT ?? 8000}`

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/status': backend,
      '/requests': backend,
      '/stats': backend,
      '/pricing': backend,
      '/control': backend,
      '/db': backend,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
