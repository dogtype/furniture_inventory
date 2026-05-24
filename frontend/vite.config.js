import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/furniture_inventory/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Julias Interior Store',
        short_name: 'Interior Store',
        description: 'Möbel & Einrichtung verwalten',
        theme_color: '#aa3bff',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: '/furniture_inventory/',
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
})
