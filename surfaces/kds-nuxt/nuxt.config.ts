import tailwindcss from "@tailwindcss/vite";
import { definePwaCapability } from "../operator-kit/pwa.config";
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
  extends: ["../operator-kit"],

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
  },

  // 301 das rotas antigas → enxutas: estação direta em /<ref> (era /estacao/<ref>);
  // board do cliente em /pickup (era /cliente, depois /retirada) — cada rota antiga
  // aponta DIRETO ao destino final, sem cadeia de redirects. Splat preservado pelo Nitro.
  routeRules: {
    "/estacao/**": { redirect: { to: "/**", statusCode: 301 } },
    "/cliente": { redirect: { to: "/pickup", statusCode: 301 } },
    "/retirada": { redirect: { to: "/pickup", statusCode: 301 } },
  },

  modules: [
    definePwaCapability({
      app: "kds",
      display: "fullscreen",
      wakeLock: true,
      kiosk: true,
      idleReloadPaths: ["*"],
    }),
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/fonts',
    '@nuxt/eslint',
    "vue-sonner/nuxt"
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
    imports: [{
      from: 'tailwind-variants',
      name: 'tv'
    }, {
      from: 'tailwind-variants',
      name: 'VariantProps',
      type: true
    }, {
      from: "vue-sonner",
      name: "toast",
      as: "useSonner"
    }]
  },

  colorMode: {
    // DARK-first — KDS best practice (back-of-house: low light, less eye strain,
    // the time semaphore pops on dark). Diverges from the POS (light, counter-
    // facing) on purpose; light stays available via the toggle.
    preference: 'dark',
    fallback: 'dark',
    storageKey: 'kds-nuxt-color-mode',
    classSuffix: ''
  },

  icon: {
    clientBundle: {
      scan: true,
      sizeLimitKb: 0
    },

    mode: 'svg',
    class: 'shrink-0',
    fetchTimeout: 2000,
    serverBundle: 'local'
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
    plugins: [tailwindcss()]
  }
})
