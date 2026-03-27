import { defineConfig } from 'astro/config'
import react from '@astrojs/react'
import tailwindcss from '@tailwindcss/vite'

const base = process.env.BASE_PATH || ''

export default defineConfig({
  output: 'static',
  site: 'https://iponweb.github.io',
  base,
  trailingSlash: 'always',
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
})
