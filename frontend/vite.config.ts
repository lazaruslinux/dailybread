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
      manifest: {
        name: 'dailybread',
        short_name: 'dailybread',
        description: 'A self-hosted family life planner.',
        theme_color: '#0b1220',
        background_color: '#0b1220',
        display: 'standalone',
        // Placeholder icon for now: the scaffold's SVG favicon. Replace with
        // real 192px/512px PNG icons before shipping the PWA.
        icons: [
          {
            src: 'favicon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      // In dev the frontend calls /api/* and Vite forwards it to the FastAPI
      // backend, stripping the /api prefix. This keeps the browser same-origin
      // (no CORS) and mirrors how the LAN-only Caddy proxy will route /api on
      // the home server. Nothing here is public-facing.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
