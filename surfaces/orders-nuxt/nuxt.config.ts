import tailwindcss from "@tailwindcss/vite";
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
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

  // 301 da rota pt-br antiga → inglês (vocabulário do domínio: Feed).
  // Tablets do gestor têm bookmark da antiga.
  routeRules: {
  },

  modules: [
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
    // LIGHT-first — the Gestor is a counter/office surface (well-lit, manager-
    // facing), like the POS and unlike the KDS (dark, back-of-house). Dark stays
    // available via the toggle.
    preference: 'light',
    fallback: 'light',
    storageKey: 'orders-nuxt-color-mode',
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
    // Served at the subdomain root (gestor.…) → baseURL "/". Internal operator
    // surface; the public host lives only in the deploy spec, never hardcoded here.
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Gestor de Pedidos",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "theme-color", content: "#ffffff" },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()],
    // Dev-only: permite acesso via túnel cloudflared (host-check do Vite 7). Targeted
    // a *.trycloudflare.com; NÃO commitar — é conveniência de preview local.
    server: {
      allowedHosts: [".trycloudflare.com"]
    }
  }
})
