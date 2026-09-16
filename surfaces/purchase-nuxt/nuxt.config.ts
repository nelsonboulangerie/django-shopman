import tailwindcss from "@tailwindcss/vite";
import { definePwaCapability } from "../operator-kit/pwa.config";

export default defineNuxtConfig({
  extends: ["../operator-kit"],
  ssr: false,

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {
      // O NOME da chave é o contrato com a env: o Nuxt deriva
      // public.djangoBaseUrl <- NUXT_PUBLIC_DJANGO_BASE_URL. Com outro nome
      // (era djangoPublicBaseUrl) a env do App Platform é ignorada em runtime
      // e o bundle serve o fallback 127.0.0.1 — links quebrados no ar, 28/08.
      djangoBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    },
  },

  modules: [
    definePwaCapability({
      app: "purchase",
      display: "standalone",
      wakeLock: false,
      kiosk: false,
      push: { surfaceRef: "purchase", categories: ["purchase"] },
      manifest: {
        name: "Compras",
        shortName: "Compras",
        description: "Compras e recebimento de insumos.",
        themeColor: "#FFFFFF",
        backgroundColor: "#FAFAF9",
        orientation: "any",
        icons: [
          { src: "/pwa/pwa-192x192.png?v=2", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/pwa/pwa-512x512.png?v=2", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/pwa/maskable-512x512.png?v=2", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
        shortcuts: [
          { name: "Recebimento", shortName: "Receber", url: "/?view=receive", icon: "/pwa/pwa-192x192.png?v=2" },
        ],
      },
    }),
    "@nuxtjs/color-mode",
    "motion-v/nuxt",
    "@vueuse/nuxt",
    "@nuxt/icon",
    "@nuxt/fonts",
    "@nuxt/eslint",
    "vue-sonner/nuxt",
  ],

  fonts: {
    families: [
      { name: "Instrument Sans", provider: "google", weights: [400, 500, 600, 700], styles: ["normal"] },
    ],
  },

  imports: {
    imports: [
      { from: "tailwind-variants", name: "tv" },
      { from: "tailwind-variants", name: "VariantProps", type: true },
      { from: "vue-sonner", name: "toast", as: "useSonner" },
    ],
  },

  colorMode: {
    preference: "light",
    fallback: "light",
    storageKey: "purchase-nuxt-color-mode",
    classSuffix: "",
  },

  icon: {
    clientBundle: { scan: true, sizeLimitKb: 0 },
    mode: "svg",
    class: "shrink-0",
    fetchTimeout: 2000,
    serverBundle: "local",
  },

  css: ["~/assets/css/tailwind.css"],

  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Compras",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "theme-color", content: "#ffffff" },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: [".ngrok-free.app", ".trycloudflare.com"],
    },
  },
});
