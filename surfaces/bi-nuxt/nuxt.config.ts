import tailwindcss from "@tailwindcss/vite";

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
  extends: ["../operator-kit"],

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {
      djangoPublicBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    },
  },

  modules: [
    "@nuxtjs/color-mode",
    "motion-v/nuxt",
    "@vueuse/nuxt",
    "@nuxt/icon",
    "@nuxt/fonts",
    "@nuxt/eslint",
    "vue-sonner/nuxt",
  ],

  // Instrument Sans self-hospedada com os PESOS da escala do operador (body=500,
  // title=600, display/figure=700 — ver ESCALA DE DESIGN no tailwind.css).
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
    // LIGHT-first — o B.I. é superfície de escritório (gestor lendo números em
    // ambiente claro), como o Marketing e o Gestor; o escuro segue no toggle.
    preference: "light",
    fallback: "light",
    storageKey: "bi-nuxt-color-mode",
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
    // Servido na raiz do subdomínio (bi.…) → baseURL "/". Superfície interna;
    // o host público vive só na spec de deploy, nunca hardcoded aqui.
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "B.I.",
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
      // Túnel de dev (ngrok) — mesmo racional do marketing-nuxt.
      allowedHosts: [".ngrok-free.app"],
    },
  },
});
