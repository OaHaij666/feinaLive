import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/music': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/bilibili': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ai': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/config': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/avatar': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/hls': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
      },
      '/test': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false
  }
})
