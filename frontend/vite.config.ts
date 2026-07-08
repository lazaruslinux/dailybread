import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Generates the web app manifest + service worker so the app is
    // installable to a phone/desktop home screen ("Add to Home Screen").
    VitePWA({
      registerType: 'autoUpdate',
      // Static files that must be precached alongside the manifest icons.
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      workbox: {
        // Web Push handlers ride inside the generated service worker.
        importScripts: ['push-sw.js'],
      },
      manifest: {
        name: 'dailybread',
        short_name: 'dailybread',
        description: 'A self-hosted family life planner.',
        theme_color: '#0b1220',
        background_color: '#0b1220',
        display: 'standalone',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
          // Android crops "maskable" icons into whatever shape the launcher
          // uses (circle, squircle), so this variant keeps the loaf inside
          // the safe zone instead of getting its corners chopped off.
          { src: 'maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      // In dev the frontend calls /api/* and Vite forwards it to the FastAPI
      // backend, stripping the /api prefix. This keeps the browser same-origin
      // (no CORS) and mirrors how a production reverse proxy routes /api to the
      // backend. Nothing here is public-facing.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    // `vite preview` serves the built app (with its real service worker, which
    // the dev server doesn't run) - used to exercise PWA/push flows locally.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
