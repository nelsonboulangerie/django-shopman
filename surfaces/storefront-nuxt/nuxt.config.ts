import tailwindcss from "@tailwindcss/vite";

const appleStartupImages = [
  [2048, 2732, 2, 'portrait'], [2732, 2048, 2, 'landscape'],
  [1668, 2388, 2, 'portrait'], [2388, 1668, 2, 'landscape'],
  [1536, 2048, 2, 'portrait'], [2048, 1536, 2, 'landscape'],
  [1640, 2360, 2, 'portrait'], [2360, 1640, 2, 'landscape'],
  [1668, 2224, 2, 'portrait'], [2224, 1668, 2, 'landscape'],
  [1620, 2160, 2, 'portrait'], [2160, 1620, 2, 'landscape'],
  [1488, 2266, 2, 'portrait'], [2266, 1488, 2, 'landscape'],
  [1320, 2868, 3, 'portrait'], [2868, 1320, 3, 'landscape'],
  [1206, 2622, 3, 'portrait'], [2622, 1206, 3, 'landscape'],
  [1260, 2736, 3, 'portrait'], [2736, 1260, 3, 'landscape'],
  [1290, 2796, 3, 'portrait'], [2796, 1290, 3, 'landscape'],
  [1179, 2556, 3, 'portrait'], [2556, 1179, 3, 'landscape'],
  [1170, 2532, 3, 'portrait'], [2532, 1170, 3, 'landscape'],
  [1284, 2778, 3, 'portrait'], [2778, 1284, 3, 'landscape'],
  [1125, 2436, 3, 'portrait'], [2436, 1125, 3, 'landscape'],
  [1242, 2688, 3, 'portrait'], [2688, 1242, 3, 'landscape'],
  [828, 1792, 2, 'portrait'], [1792, 828, 2, 'landscape'],
  [1242, 2208, 3, 'portrait'], [2208, 1242, 3, 'landscape'],
  [750, 1334, 2, 'portrait'], [1334, 750, 2, 'landscape'],
  [640, 1136, 2, 'portrait'], [1136, 640, 2, 'landscape']
] as const

const appleStartupLinks = appleStartupImages.map(([width, height, scale, orientation]) => ({
  rel: 'apple-touch-startup-image' as const,
  href: `/pwa/apple-splash-${width}-${height}.png`,
  media: `(device-width: ${width / scale}px) and (device-height: ${height / scale}px) and (-webkit-device-pixel-ratio: ${scale}) and (orientation: ${orientation})`
}))

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2026-05-16',
  devtools: { enabled: false },

  // O tsconfig gerado pelo Nuxt zera `types`; o namespace global `google` usado por
  // AddressPicker/useGoogleMaps vem de @types/google.maps e precisa ser registrado.
  typescript: {
    tsConfig: {
      compilerOptions: {
        types: ['google.maps']
      }
    }
  },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || 'http://127.0.0.1:8000'
  },

  // Foto de catálogo é imutável por convenção: trocar a foto = trocar o NOME do
  // arquivo (ct.v2.webp), nunca sobrescrever — é isso que torna o cache longo
  // seguro. Sem esta regra o Nitro serve public/ com cache curto e cada volta à
  // loja rebaixa o catálogo inteiro.
  routeRules: {
    '/img/products/**': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/sw.js': {
      headers: { 'cache-control': 'no-cache, no-store, must-revalidate' }
    }
  },

  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || '/',
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      // titleTemplate vive no app.vue (useHead): lá é função com a marca dinâmica do
      // tenant — e nuxt.config só aceita string, então aqui ele não tem vez.
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#7C3A40' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'default' }
      ],
      link: [
        { rel: 'manifest', href: '/manifest.webmanifest' },
        { rel: 'icon', href: '/pwa/favicon.svg', type: 'image/svg+xml' },
        { rel: 'icon', href: '/pwa/favicon.ico', sizes: 'any' },
        { rel: 'apple-touch-icon', href: '/pwa/apple-touch-icon-transparent-180x180.png' },
        ...appleStartupLinks
      ]
    }
  },

  modules: [
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/fonts',
    '@vite-pwa/nuxt',
    "@yuta-inoue-ph/nuxt-vcalendar",
    "vue-sonner/nuxt",
    '@nuxt/eslint',
    '@nuxt/test-utils/module'
  ],

  pwa: {
    manifest: false,
    strategies: 'generateSW',
    registerType: 'prompt',
    injectRegister: false,
    client: {
      registerPlugin: false,
      installPrompt: false,
      periodicSyncForUpdates: 0
    },
    workbox: {
      navigateFallback: null,
      navigationPreload: false,
      cleanupOutdatedCaches: true,
      clientsClaim: false,
      skipWaiting: false,
      globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
      globIgnores: ['pwa/screenshots/**'],
      manifestTransforms: [async entries => ({ manifest: entries, warnings: [] })],
      runtimeCaching: [
        {
          urlPattern: ({ request }) => request.mode === 'navigate',
          handler: 'NetworkOnly',
          options: {
            precacheFallback: { fallbackURL: '/offline.html' }
          }
        },
        {
          urlPattern: ({ url }) => url.origin === self.location.origin && url.pathname.startsWith('/img/products/'),
          handler: 'CacheFirst',
          options: {
            cacheName: 'storefront-product-images'
          }
        },
        {
          urlPattern: ({ url }) => url.origin === self.location.origin && url.pathname.startsWith('/fonts/'),
          handler: 'CacheFirst',
          options: {
            cacheName: 'storefront-fonts'
          }
        }
      ]
    },
    devOptions: {
      enabled: false
    }
  },

  // ESLint com o flat config gerado pelo Nuxt (stylistic OFF; Prettier cuida do estilo).
  eslint: {
    config: {
      stylistic: false
    }
  },

  // Tipografia canônica, servida do NOSSO repo (`public/fonts/`):
  //  · Instrument Sans → corpo (--font-sans canônica; o eixo wght cobre o 500 que as
  //    primitivas Ui usam). É a fonte oficial do tema, não um <link> de runtime da marca.
  //  · Fraunces (serif) → títulos (.shop-display/.shop-title). O arquivo é o VARIÁVEL com
  //    eixo opsz, que é o que faz `font-optical-sizing: auto` cortar diferente nos títulos
  //    grandes — uma instância estática perderia isso.
  //
  // ⚠️ Eram `provider: 'google'`, e o @nuxt/fonts baixava os woff2 DURANTE o build. Em
  // 2026-08-11 o deploy do staging morreu inteiro assim, sem uma linha de código mudada:
  //
  //     FetchError: [GET] "https://fonts.gstatic.com/s/fraunces/v38/…woff2": 404 Not Found
  //     ERROR: failed to build: exit status 1
  //
  // O Google rotacionou a URL de um arquivo e levou o build com ela. Fonte no repo tira
  // um terceiro do caminho do deploy — e o `src` explícito continua dando ao módulo o
  // arquivo para calcular a métrica de fallback (`fallbacks`), que é o que garante o zero
  // CLS (o CSS gerado sai com `size-adjust`/`ascent-override`, conferido no build).
  //
  // Os arquivos são o subset `latin` do Google: cobre ã/ç/é/õ, travessão, aspas curvas,
  // setas, € e ™. `latin-ext` custaria +70 KB em caracteres que uma loja pt-br não usa, e
  // caractere fora do subset cai no próximo da pilha por glifo (comportamento normal do
  // CSS), não em retângulo.
  fonts: {
    families: [
      {
        name: 'Instrument Sans',
        src: '/fonts/instrument-sans-latin.woff2',
        weight: [400, 700],  // arquivo variável: um só cobre 400/500/600
        style: 'normal',
        display: 'swap',
        fallbacks: ['Helvetica Neue', 'Arial']
      },
      {
        name: 'Fraunces',
        src: '/fonts/fraunces-latin.woff2',
        weight: [400, 700],
        style: 'normal',
        display: 'swap',
        fallbacks: ['Georgia', 'Times New Roman']
      }
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
      from: 'vue-sonner',
      name: 'toast',
      as: 'useSonner'
    }]
  },

  colorMode: {
    storageKey: 'storefront-nuxt-color-mode',
    storage: 'cookie',
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

  css: ['~/assets/css/tailwind.css'],

  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      include: ['reka-ui', 'tailwind-variants', 'v-calendar']
    }
  }
})
