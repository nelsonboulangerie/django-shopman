import tailwindcss from "@tailwindcss/vite";
import { definePwaCapability } from "../operator-kit/pwa.config";
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // A matriz visual usa o mesmo relógio e o mesmo primeiro render do browser.
  // O app normal e o build de produção continuam SSR.
  ssr: process.env.POS_VISUAL_CLIENT_ONLY !== "1",
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
    operatorSecurityHeaders: true,
    // Exceções da CSP do kit, uma por função real (SEC-SURF-001). Decisão do dono em
    // 29/09/2026: o PDV carrega o Google Maps; foto de produto e agente do balcão
    // repetem a regra já aprovada para o Pedidos.
    operatorCspAllow: {
      // Autocompletar de endereço da entrega (`usePosGoogleMaps`): o bootstrap da
      // Maps JS API e os pedaços que ele carrega (`maps-api-v3/…`, biblioteca Places)
      // vêm todos deste host. Host explícito, sem curinga.
      "script-src": ["https://maps.googleapis.com"],
      // - maps.googleapis.com: a Maps JS API fala com a própria origem (autenticação
      //   da chave e telemetria da biblioteca);
      // - places.googleapis.com: as sugestões e os detalhes do endereço (Places API
      //   New, `fetchAutocompleteSuggestions` e `fetchFields` em
      //   `PosAddressAutocomplete`);
      // - viacep.com.br: a busca do endereço pelo CEP no mesmo campo;
      // - loopback: a gaveta e a impressora saem pelo agente do dispositivo, que vive
      //   no próprio balcão (`useCounterAgent`, DEFAULT_AGENT_URL
      //   http://127.0.0.1:47811). Quem chama é o navegador; nada fica aberto para
      //   fora da máquina.
      "connect-src": [
        "https://maps.googleapis.com",
        "https://places.googleapis.com",
        "https://viacep.com.br",
        "http://127.0.0.1:*",
        "http://localhost:*",
      ],
      // A foto do produto no tile e na pesagem vem de host externo (o gestor pode
      // colar a URL de qualquer site); a mesma regra cobre o QR do Pix quando a
      // cobrança o devolve por URL e as imagens da Maps JS API (maps.gstatic.com).
      "img-src": ["https:"],
    },
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

  // 301 das rotas antigas → a tela única das Encomendas (redesenho de 28/09/2026).
  // Hoje, Semana e "Via Pedido – painel" eram páginas; viraram modos e filtros da
  // mesma tela, e o estado vai na query. "Fichas de pedido" (`/tickets`) e o painel
  // abrem a semana com "Falta imprimir" ligado — o kiosk do painel de parede tem
  // bookmark das duas. Mesmo mecanismo das rotas pt-br antigas (PR #68):
  // `routeRules` do Nitro, direto ao destino final (e o middleware de route rules
  // do Nuxt faz o mesmo na navegação do cliente).
  routeRules: {
    "/tickets": { redirect: { to: "/preorders?mode=week&print=pending", statusCode: 301 } },
    "/preorders/panel": { redirect: { to: "/preorders?mode=week&print=pending", statusCode: 301 } },
    "/preorders/today": { redirect: { to: "/preorders?mode=day", statusCode: 301 } },
    "/preorders/week": { redirect: { to: "/preorders?mode=week", statusCode: 301 } },
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
      // fechamento é digitada e não está salva; `/preorders`, porque a busca e os filtros
      // da tela das Encomendas são o lugar em que o operador está.
      //
      // ⚠️ `/display` fica de fora pelo motivo mais forte de todos: `skipWaiting` vale
      // para a ORIGEM inteira, e toda janela que viu o worker em espera recarrega
      // junto (o vite-plugin-pwa registra `controlling` → reload em cada uma). A tela
      // do cliente ninguém toca, então ela seria considerada ociosa SEMPRE — e quem
      // recarregaria no meio da venda seria o PDV, não ela.
      idleReloadPaths: ["/"],
      push: { surfaceRef: "pos", categories: ["order", "system"] },
      shortcuts: [
        { name: "Venda", shortName: "Venda", url: "/" },
        { name: "Caixa", shortName: "Caixa", url: "/session" },
      ],
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
    // LIGHT-first — o PDV é superfície de balcão, em ambiente claro e virada para o
    // cliente, como o Gestor e ao contrário do KDS (escuro, fundo de casa). Sem esta
    // declaração ele seguia o tema do SISTEMA: um Mac no escuro abria o caixa escuro,
    // e o comentário do KDS já descrevia o PDV como claro. O escuro segue no toggle.
    preference: 'light',
    fallback: 'light',
    storageKey: 'pos-nuxt-color-mode',
    classSuffix: ''
  },

  // Ícones que só aparecem como DADO num .ts (a seção "Fim do dia" do rail, o botão da
  // barra lateral do kit): o scan do @nuxt/icon lê só os templates, e o navegador ia
  // buscá-los na API do Iconify, que a CSP bloqueia (erro no console, 10/10/2026). O
  // gancho do módulo os põe no pacote sem tocar a identidade do app.
  hooks: {
    "icon:clientBundleIcons": (bundle: Set<string>) => {
      for (const name of ["lucide:clipboard-check", "lucide:panel-left-dashed"]) bundle.add(name);
    },
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
