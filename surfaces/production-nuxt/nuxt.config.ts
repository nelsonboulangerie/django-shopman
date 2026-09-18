import tailwindcss from "@tailwindcss/vite";
import { configuredDjangoBaseUrl } from "../operator-kit/server/utils/djangoBaseUrl";
import { definePwaCapability } from "../operator-kit/pwa.config";
// https://nuxt.com/docs/api/configuration/nuxt-config
const isProduction = process.env.NODE_ENV === "production";
const djangoBaseUrl = configuredDjangoBaseUrl();

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
  extends: ["../operator-kit"],

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    // Privado ao Nitro: browser fala somente com o BFF same-origin. Em build/boot
    // de produção a resolução falha sem uma URL HTTPS remota explícita.
    djangoBaseUrl,
    operatorSecurityHeaders: true,
    operatorUpstreamFailFast: true,
    public: {
      // A antessala da PRODUÇÃO, não a compartilhada — e isto é metade de uma
      // trava de servidor, não organização de rota.
      //
      // Uma estação autônoma (o painel de parede, sem ninguém para digitar PIN)
      // só tem a conta dela resolvida sob `/api/v1/backstage/production/`. O
      // cookie de estação é nomeado por terminal, mas vale em
      // `.boulangerie.com.br` inteiro: o mesmo aparelho, aberto no PDV, leva a
      // confiança junto. A antessala compartilhada fica de fora do corte de
      // propósito — se ela resolvesse o painel, o balcão com o mesmo cookie
      // leria "destravado" com o nome dele e a pessoa perderia a tela de PIN.
      // Ver `shopman/backstage/station_trust.PRODUCTION_API_PREFIX`.
      operatorSessionPath: "/api/v1/backstage/production/session/",
    },
  },

  // 301 das rotas pt-br antigas → inglês (vocabulário das lentes da grade: plan/
  // mise-en-place/expedite + board Solari). Kiosks/tablets têm bookmark das antigas.
  routeRules: {
    "/planejamento": { redirect: { to: "/plan", statusCode: 301 } },
    "/preparacao": { redirect: { to: "/mise-en-place", statusCode: 301 } },
    "/expedicao": { redirect: { to: "/expedite", statusCode: 301 } },
    "/painel": { redirect: { to: "/board", statusCode: 301 } },
  },

  modules: [
    definePwaCapability({
      app: "production",
      display: "fullscreen",
      wakeLock: true,
      kiosk: true,
      idleReloadPaths: ["/board"],
      push: { surfaceRef: "production", categories: ["production", "system"] },
      shortcuts: [
        { name: "Plano", shortName: "Plano", url: "/plan" },
        { name: "Fornadas", shortName: "Fornadas", url: "/board" },
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
      {
        name: "Instrument Sans",
        provider: "google",
        weights: [400, 500, 600, 700],
        styles: ["normal"],
      },
    ],
  },

  imports: {
    imports: [
      {
        from: "tailwind-variants",
        name: "tv",
      },
      {
        from: "tailwind-variants",
        name: "VariantProps",
        type: true,
      },
      {
        from: "vue-sonner",
        name: "toast",
        as: "useSonner",
      },
    ],
  },

  colorMode: {
    // LIGHT-first — the production app is touch-first but light (Pablo's call),
    // like the Gestor and unlike the KDS (dark, back-of-house). Dark stays
    // available via the toggle for the back-of-house bakery floor.
    preference: "light",
    fallback: "light",
    storageKey: "production-nuxt-color-mode",
    classSuffix: "",
  },

  icon: {
    clientBundle: {
      scan: true,
      sizeLimitKb: 0,
    },

    mode: "svg",
    class: "shrink-0",
    fetchTimeout: 2000,
    serverBundle: "local",
  },

  css: ["~/assets/css/tailwind.css"],

  app: {
    // Served at the subdomain root (prod.…) → baseURL "/". Internal operator
    // surface; the public host lives only in the deploy spec, never hardcoded here.
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      // `title` e `theme-color` saem da capability PWA (surfaces/operator-kit/
      // app-identity.json): o rótulo do app e a cor do ícone, iguais em manifesto,
      // barra de título e aba.
      meta: [
        {
          name: "viewport",
          content: "width=device-width, initial-scale=1, viewport-fit=cover",
        },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()],
    server: {
      // Dev-only: permite espiar o dev server por um quick tunnel do
      // Cloudflare (QA remoto antes de publicar). Produção não passa por
      // aqui (build Nitro, sem dev server).
      allowedHosts: isProduction ? [] : [".trycloudflare.com"],
    },
  },
});
