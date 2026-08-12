import tailwindcss from "@tailwindcss/vite";

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

  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || '/',
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      // titleTemplate vive no app.vue (useHead): lá é função com a marca dinâmica do
      // tenant — e nuxt.config só aceita string, então aqui ele não tem vez.
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#85786c' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'default' }
      ]
    }
  },

  modules: [
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/fonts',
    "@yuta-inoue-ph/nuxt-vcalendar",
    "vue-sonner/nuxt",
    '@nuxt/eslint',
    '@nuxt/test-utils/module'
  ],

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
