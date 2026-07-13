import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@app-root': resolve(
        __dirname,
        mode === 'console' ? 'src/apps/console/ConsoleApp.vue' : 'src/App.vue'
      )
    }
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/music': {
        target: 'http://localhost:9191',
        changeOrigin: true,
      },
      '/live': {
        target: 'http://localhost:9191',
        changeOrigin: true,
        ws: true,
      },
      '/agent': {
        target: 'http://localhost:9191',
        changeOrigin: true,
        ws: true,
      },
      '/health': {
        target: 'http://localhost:9191',
        changeOrigin: true,
      },
      '/ai': {
        target: 'http://localhost:9191',
        changeOrigin: true,
      },
      '/config': {
        target: 'http://localhost:9191',
        changeOrigin: true,
      },
      '/avatar': {
        target: 'http://localhost:9191',
        changeOrigin: true,
        ws: true,
      },
      '/stream': {
        target: 'http://localhost:9191',
        changeOrigin: true,
      },
      '/hls': {
        target: 'http://localhost:8088',
        changeOrigin: true,
      },
      '/test': {
        target: 'http://localhost:9191',
        changeOrigin: true,
        ws: true,
      },
    }
  },
  preview: {
    host: '127.0.0.1',
  },
  build: {
    outDir: mode === 'console' ? 'dist/console' : 'dist/live',
    assetsDir: 'assets',
    sourcemap: false
  }
}))
