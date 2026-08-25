import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Vite build configuration for the FCC Dashboard frontend.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})
