import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// dev only: the API (uvicorn on :8000) serves the built app in production
const api = { target: 'http://localhost:8000', changeOrigin: false }
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': api, '/auth': api } },
})
