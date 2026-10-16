import tailwindcss from "@tailwindcss/vite";

export default defineNuxtConfig({
  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },
  ssr: true,

  routeRules: {
    "/": { prerender: true },
    "/_nuxt/**": { headers: { "cache-control": "public, max-age=31536000, immutable" } },
    "/status.snapshot.json": { headers: { "cache-control": "public, max-age=60" } },
    "/manifest.webmanifest": { headers: { "cache-control": "public, max-age=3600" } },
    "/sw.js": { headers: { "cache-control": "no-cache, no-store, must-revalidate" } },
  },

  app: {
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Status — Nelson Boulangerie",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "description", content: "Disponibilidade dos serviços digitais da Nelson Boulangerie." },
        { name: "theme-color", content: "#ffffff" },
        { name: "apple-mobile-web-app-capable", content: "yes" },
        { name: "apple-mobile-web-app-status-bar-style", content: "default" },
        { name: "robots", content: "index, follow" },
      ],
      link: [
        { rel: "manifest", href: "/manifest.webmanifest?v=1" },
        { rel: "icon", href: "/pwa/favicon.svg?v=1", type: "image/svg+xml" },
        { rel: "apple-touch-icon", href: "/pwa/apple-touch-icon-180x180.png?v=1" },
      ],
    },
  },

  modules: ["@nuxt/icon", "@vueuse/nuxt", "@vite-pwa/nuxt", "@nuxt/eslint"],
  css: ["~/assets/css/main.css"],

  icon: {
    clientBundle: { scan: true, sizeLimitKb: 0 },
    mode: "svg",
    serverBundle: "local",
  },

  pwa: {
    manifest: false,
    strategies: "generateSW",
    registerType: "prompt",
    injectRegister: false,
    client: { registerPlugin: false, installPrompt: false, periodicSyncForUpdates: 0 },
    workbox: {
      navigateFallback: null,
      navigationPreload: false,
      cleanupOutdatedCaches: true,
      clientsClaim: false,
      skipWaiting: false,
      globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
      globIgnores: ["index.html"],
      // Mantém o nome exato do casco offline; a transformação padrão do Nuxt
      // remove a extensão e quebraria o fallback explícito abaixo.
      manifestTransforms: [async entries => ({ manifest: entries, warnings: [] })],
      runtimeCaching: [
        {
          urlPattern: ({ request }: { request: Request }) => request.mode === "navigate",
          handler: "NetworkOnly",
          options: { precacheFallback: { fallbackURL: "/offline.html" } },
        },
        {
          urlPattern: ({ url }: { url: URL }) => url.origin === self.location.origin && url.pathname.startsWith("/fonts/"),
          handler: "CacheFirst",
          options: { cacheName: "status-fonts" },
        },
        {
          urlPattern: ({ url }: { url: URL }) => url.origin === self.location.origin && url.pathname === "/nelson-logo.svg",
          handler: "CacheFirst",
          options: { cacheName: "status-brand" },
        },
      ],
    },
    devOptions: { enabled: false },
  },

  vite: {
    plugins: [tailwindcss()],
    server: { allowedHosts: [".trycloudflare.com"] },
  },
});
