import tailwindcss from "@tailwindcss/vite";
import { definePwaCapability } from "../operator-kit/pwa.config";
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // Central de Apps: 5º cliente do kit compartilhado (BFF/resiliência/telemetria/DS).
  // É o launcher pós-login — não hospeda CRUD; deep-linka pro Unfold quando preciso.
  extends: ["../operator-kit"],

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
      // A Central é a casa: o rail começa colapsado (o operador abre se quiser).
      railDefaultState: "collapsed",
    },
  },

  modules: [
    definePwaCapability({
      app: "hub",
      display: "standalone",
      wakeLock: false,
      kiosk: false,
      push: {
        surfaceRef: "hub",
        categories: ["campaign", "production", "order", "purchase", "report", "sign_in", "system"],
      },
      shortcuts: [
        { name: "Pedidos", shortName: "Pedidos", url: "/shortcuts/orders" },
        { name: "Caixa", shortName: "Caixa", url: "/shortcuts/pos" },
        { name: "Produção", shortName: "Produção", url: "/shortcuts/production" },
      ],
    }),
    "@nuxtjs/color-mode",
    "motion-v/nuxt",
    "@vueuse/nuxt",
    "@nuxt/icon",
    "@nuxt/fonts",
    "@nuxt/eslint",
    "vue-sonner/nuxt",
  ],

  // Instrument Sans self-hospedada com os PESOS da escala do operador (body=500,
  // title=600, display/figure=700 — ver ESCALA DE DESIGN no tailwind.css). Sem esta
  // declaração o @nuxt/fonts baixa só o 400 e o navegador sintetiza os demais (faux
  // bold). Mesma família da vitrine (design system unificado).
  fonts: {
    families: [
      { name: 'Instrument Sans', provider: 'google', weights: [400, 500, 600, 700], styles: ['normal'] }
    ]
  },

  imports: {
    imports: [
      { from: "tailwind-variants", name: "tv" },
      { from: "tailwind-variants", name: "VariantProps", type: true },
      { from: "vue-sonner", name: "toast", as: "useSonner" },
    ],
  },

  colorMode: {
    // LIGHT-first — a Central é a casa dos apps de escritório e balcão, todos claros;
    // só a Cozinha é escura. Sem a declaração ela seguia o tema do SISTEMA e abria de
    // um jeito no Mac e de outro no tablet. O escuro segue no toggle do rail.
    preference: "light",
    fallback: "light",
    storageKey: "hub-nuxt-color-mode",
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
      // `title` e `theme-color` saem da capability PWA (surfaces/operator-kit/
      // app-identity.json): o rótulo do app e a cor do ícone, iguais em manifesto,
      // barra de título e aba.
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()],
  },
});
