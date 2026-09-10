import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";
// https://nuxt.com/docs/api/configuration/nuxt-config

const immutableAssetHeaders = {
  "cache-control": "public, max-age=31536000, immutable",
  "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
  "cross-origin-opener-policy": "same-origin",
  "cross-origin-resource-policy": "same-origin",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
  "referrer-policy": "no-referrer",
  "strict-transport-security": "max-age=31536000; includeSubDomains",
  "x-content-type-options": "nosniff",
  "x-dns-prefetch-control": "off",
  "x-frame-options": "DENY",
};

export default defineNuxtConfig({
  // A matriz visual roda client-only para que o relógio fixado pelo navegador
  // seja também o relógio do primeiro render. O app normal e o build continuam SSR.
  ssr: process.env.MARKETING_VISUAL_CLIENT_ONLY !== "1",
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
    },
  },

  // A página sintética só entra no roteador hermético da matriz. O app normal não
  // publica uma rota capaz de fabricar erros.
  hooks: process.env.MARKETING_VISUAL_MATRIX === "1"
    ? {
        "pages:extend": (pages) => {
          pages.push({
            name: "visual-error",
            path: "/__visual_error/:status",
            file: fileURLToPath(
              new URL("./app/visual/VisualErrorPage.vue", import.meta.url),
            ),
          });
        },
      }
    : {},

  // A notificação acionável do backend aponta para /campaign/announcements/<pk>/
  // (``UserNotification.action_url``). Servido na raiz do subdomínio, o prefixo
  // sobra — este redirect faz o link do celular cair no card certo.
  routeRules: {
    "/campaign/announcements/**": { redirect: { to: "/announcements/**", statusCode: 302 } },
    "/_nuxt/**": { headers: immutableAssetHeaders },
    "/fonts/**": { headers: immutableAssetHeaders },
  },

  modules: [
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/eslint',
    "vue-sonner/nuxt"
  ],

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
    // LIGHT-first — o Marketing é superfície de escritório (gestor revisando texto e
    // foto, em ambiente claro), como o Gestor e o PDV; o escuro segue no toggle.
    preference: 'light',
    fallback: 'light',
    storageKey: 'marketing-nuxt-color-mode',
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
    // Servido na raiz do subdomínio (mkt.…) → baseURL "/". Superfície interna;
    // o host público vive só na spec de deploy, nunca hardcoded aqui.
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Marketing",
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
      // O Vite recusa Host que não conheça (proteção contra DNS rebinding). Ao expor
      // o dev server por túnel (ngrok), o Host que chega é o hostname aleatório do
      // túnel e o servidor responde 403. Libera o sufixo para o dev server aceitar
      // qualquer túnel ngrok sem reeditar config a cada execução.
      // Vale SÓ para `nuxt dev` — `vite.server` não entra no build de produção.
      allowedHosts: [".ngrok-free.app"],
    },
  }
})
