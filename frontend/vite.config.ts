import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // During development the FastAPI backend runs on port 8000; /api goes there.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
