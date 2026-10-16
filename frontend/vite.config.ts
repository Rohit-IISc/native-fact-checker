import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// GitHub Codespaces serves the dev server through https://{name}-5173.{domain}; Vite must accept
// that host and point the HMR websocket at the forwarded https port.
const codespace = process.env.CODESPACES === 'true' && process.env.CODESPACE_NAME
const forwardDomain = process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN || 'app.github.dev'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectRegister: false,
      // public/manifest.webmanifest carries the share_target; the plugin must not generate another.
      manifest: false,
      injectManifest: { globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}'] },
      devOptions: { enabled: true, type: 'module' },
    }),
  ],
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: codespace ? [`.${forwardDomain}`] : undefined,
    hmr: codespace ? { host: `${codespace}-5173.${forwardDomain}`, protocol: 'wss', clientPort: 443 } : undefined,
    // API_PROXY_TARGET lets a second local stack run beside `make dev` (e.g. offline screenshots on :8090).
    proxy: { '/api': { target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8080', changeOrigin: true } },
  },
})
