import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Запросы /api уходят на FastAPI, поэтому CORS не нужен
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
