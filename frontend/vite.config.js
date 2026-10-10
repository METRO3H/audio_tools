import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

const r = (p) => fileURLToPath(new URL(p, import.meta.url))

export default defineConfig({
  plugins: [
    tailwindcss(),
    svelte(),
  ],
  resolve: {
    alias: {
      '@app': r('./src/app'),
      '@shared': r('./src/shared'),
      '@home': r('./src/features/home'),
      '@merge': r('./src/features/merge'),
      '@diverge': r('./src/features/diverge'),
      '@audio-to-video': r('./src/features/audio-to-video'),
      '@transcribe': r('./src/features/transcribe'),
      '@translate': r('./src/features/translate'),
    },
  },
  build: {
    outDir: '../dist_ui',
    emptyOutDir: true,
  },
})
