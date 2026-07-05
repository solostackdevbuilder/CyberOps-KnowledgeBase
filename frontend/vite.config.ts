/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.BACKEND_PORT || '17000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: parseInt(process.env.PORT || '17001', 10),
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})

