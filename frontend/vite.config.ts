/*
 * vite.config.ts
 * Vite build configuration for the FCC Dashboard frontend.
 * https://vite.dev/config/
 */

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
export default defineConfig({
  plugins: [react()],
})
