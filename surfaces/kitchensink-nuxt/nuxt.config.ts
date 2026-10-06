import tailwindcss from "@tailwindcss/vite";
import { definePwaCapability } from "../operator-kit/pwa.config";

export default defineNuxtConfig({
  extends: ["../operator-kit"],
  ssr: true,

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    operatorSecurityHeaders: true,
    operatorUpstreamFailFast: true,
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {
      // Harness hermético somente no dev server da matriz. Produção nunca pode
      // transformar uma env em bypass do gate de permissão.
      kitchenSinkHarness:
        process.env.NODE_ENV !== "production" && process.env.KITCHENSINK_VISUAL_MATRIX === "1",
      // O NOME da chave é o contrato com a env: o Nuxt deriva
      // public.djangoBaseUrl <- NUXT_PUBLIC_DJANGO_BASE_URL.
      djangoBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    },
  },

  modules: [
    definePwaCapability({
      app: "kitchensink",
      display: "standalone",
      wakeLock: false,
      kiosk: false,
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
    storageKey: "kitchensink-nuxt-color-mode",
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
      // `title` e `theme-color` saem da capability PWA (surfaces/operator-kit/app-identity.json).
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
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
