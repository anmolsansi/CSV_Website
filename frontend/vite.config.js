import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Disposable EXT-05 browser spike only: make /api behave like the
    // deployed Vercel same-origin rewrite without changing release hosting.
    ...(process.env.JOBGRID_LOCAL_API_PROXY === '1' ? {
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api(?=\/)/, ''),
        },
      },
    } : {}),
  },
})
