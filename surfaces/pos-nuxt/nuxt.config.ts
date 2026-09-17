import tailwindcss from "@tailwindcss/vite";
import { definePwaCapability } from "../operator-kit/pwa.config";
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
  extends: ["../operator-kit"],

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },
  // O Playwright injeta diretórios por execução para duas suítes no mesmo
  // checkout nunca disputarem `.nuxt`/`.output`. Sem env, produção e dev
  // preservam exatamente os caminhos canônicos do Nuxt.
  buildDir: process.env.NUXT_BUILD_DIR || ".nuxt",
  nitro: {
    output: {
      dir: process.env.NITRO_OUTPUT_DIR || ".output",
    },
  },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {
      // O NOME da chave é o contrato com a env: o Nuxt deriva
      // public.djangoBaseUrl <- NUXT_PUBLIC_DJANGO_BASE_URL. Com outro nome
      // (era djangoPublicBaseUrl) a env do App Platform é ignorada em runtime
      // e o bundle serve o fallback 127.0.0.1 — links quebrados no ar, 28/08.
      djangoBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
      // A porta HUMANA do Admin tem host próprio (admin.<zona>), canonizado em
      // 15/08. O api.<zona>/admin segue vivo porque o BFF pega CSRF nele, mas isso
      // é mecanismo: link em que o operador CLICA vai para a porta humana. Sem a
      // env (dev), cai na base do Django, onde os dois são o mesmo 127.0.0.1:8000.
      adminBaseUrl:
        process.env.NUXT_PUBLIC_ADMIN_BASE_URL ||
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL ||
        process.env.NUXT_DJANGO_BASE_URL ||
        "http://127.0.0.1:8000",
    },
  },

  modules: [
    definePwaCapability({
      app: "pos",
      display: "standalone",
      wakeLock: true,
      kiosk: false,
      // SÓ a tela de venda, e mesmo nela só com o balcão vazio: as razões de espera
      // (`useOperatorReloadHold` em `pages/index.vue`) barram carrinho, comanda,
      // pagamento e resultado na tela. `/session` fica de fora porque a contagem de
      // fechamento é digitada e não está salva; `/display` fica de fora porque a tela
      // do cliente nunca é tocada — seria sempre "ociosa" e recarregaria no meio da
      // venda de outra estação; `/tickets` fica de fora porque a seleção de fichas
      // para impressão é rascunho.
      idleReloadPaths: ["/"],
      push: { surfaceRef: "pos", categories: ["order", "system"] },
      manifest: {
        label: "PDV",
        description: "Ponto de venda da Nelson Boulangerie.",
        themeColor: "#FCF6F1",
        backgroundColor: "#FCF6F1",
        orientation: "any",
        icons: [
          { src: "/pwa/pwa-192x192.png?v=3", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/pwa/pwa-512x512.png?v=3", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/pwa/maskable-512x512.png?v=3", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
        shortcuts: [
          { name: "Venda", shortName: "Venda", url: "/", icon: "/pwa/pwa-192x192.png?v=3" },
          { name: "Caixa", shortName: "Caixa", url: "/session", icon: "/pwa/pwa-192x192.png?v=3" },
        ],
      },
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
    storageKey: 'pos-nuxt-color-mode',
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
      title: "PDV",
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
