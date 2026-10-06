import { fileURLToPath } from "node:url";

// Nuxt layer compartilhado das superfícies de operador.
//
// Os apps (pos/orders/kds/production-nuxt + Central) fazem
// `extends: ['../operator-kit']` no seu nuxt.config. Este layer contribui:
//   - app/components  → auto-importados (ex.: OfflineBanner)
//   - app/composables → auto-importados (ex.: useConnectivity)
//   - app/utils       → auto-importados (ex.: retryWithBackoff, httpError, tw, translucent)
//   - app/plugins     → registrados (ex.: errorReporter.client)
//   - server/utils    → auto-importados pelo Nitro (djangoProxy, eventStream, apiVersion)
//
// Deliberadamente MÍNIMO: não impõe módulos, color-mode nem css ao app hospedeiro
// (cada app decide sua orientação — KDS dark-first, demais light-first — e importa o
// tailwind.css próprio). O que é genuinamente invariante e sem colisão de nome vive
// aqui; a família operator-lock canônica (types/presentation/composable/overlay) vive
// neste layer (o POS mantém a própria variante, usePosOperatorLock). O storefront fica
// de fora (superfície de cliente, branded, proxy e harness próprios).
export default defineNuxtConfig({
  devtools: { enabled: false },
  // Layer segue a convenção Nuxt 4 (srcDir `app/`) igual aos apps hospedeiros, para
  // que components/composables/utils/plugins em `app/` sejam auto-importados via extends.
  future: { compatibilityVersion: 4 },

  // Nuxt UI é a camada estrutural e visual de alto nível da suíte. O tema
  // canônico permanece ligado; operator-theme.css traduz os tokens semânticos
  // oficiais para a marca Shopman. Wrappers só ajustam o que o caso de uso
  // operacional comprovar necessário, sem reconstruir a anatomia do componente.
  modules: [
    [
      "@nuxt/ui",
      {
        prefix: "Nuxt",
        fonts: false,
        colorMode: false,
        theme: {
          unstyled: false,
          transitions: true,
        },
        experimental: {
          componentDetection: true,
        },
      },
    ],
  ],

  // Imports usados pelos próprios componentes do layer. O toast continua sob
  // responsabilidade dos apps hospedeiros; o catálogo o declara somente no
  // harness para poder compilar o layer isoladamente sem mudar essa fronteira.
  imports: {
    imports: [
      { from: "tailwind-variants", name: "tv" },
      { from: "tailwind-variants", name: "VariantProps", type: true },
      { from: "@vueuse/core", name: "reactiveOmit" },
      { from: "@vueuse/core", name: "useEventListener" },
      ...(process.env.OPERATOR_KIT_CATALOG === "1"
        ? [{ from: "vue-sonner", name: "toast", as: "useSonner" }]
        : []),
    ],
  },

  hooks: {
    // Os oito apps já instalam @nuxtjs/color-mode e esse é o dono canônico do
    // composable. O Nuxt UI também exporta um fallback homônimo mesmo quando seu
    // módulo de color mode está desligado; removê-lo evita warning de import
    // duplicado e, sobretudo, duas fontes possíveis para o mesmo estado.
    "imports:extend": (imports) => {
      const duplicate = imports.findIndex(
        (entry) =>
          entry.name === "useColorMode" &&
          String(entry.from).includes("@nuxt/ui"),
      );
      if (duplicate >= 0) imports.splice(duplicate, 1);
    },
    // Catálogo vivo somente no harness explícito. Nenhum consumer publica esta
    // rota em produção, mesmo que estenda a layer inteira.
    ...(process.env.OPERATOR_KIT_CATALOG === "1"
      ? {
          "pages:extend": (pages) => {
            pages.push({
              name: "operator-kit-catalog",
              path: "/__operator_kit_catalog",
              file: fileURLToPath(new URL("./catalog/OperatorKitCatalogPage.vue", import.meta.url)),
            });
          },
        }
      : {}),
  },

  // Uma instância de cada runtime com estado global no bundle do app. Sem isto, o
  // componente do kit resolve `operator-kit/node_modules` e o app resolve a própria
  // cópia: duas pilhas de DismissableLayer e dois stores de toast independentes.
  // Nesse segundo caso o comando é aceito por uma cópia de vue-sonner, enquanto o
  // OperatorSonner observa a outra, e a mensagem nunca aparece.
  vite: {
    resolve: { dedupe: ["reka-ui", "vue-sonner"] },
  },

  runtimeConfig: {
    // Segredo que prova ao Django que a chamada veio deste BFF, para ele ler o IP
    // do operador um salto mais fundo no X-Forwarded-For (server/utils/djangoProxy.ts).
    // Só no servidor — NUNCA em `public`. Declarado aqui para todo app que estende
    // a layer poder recebê-lo por NUXT_DJANGO_PROXY_SECRET; cada componente liga
    // pela env, com o MESMO valor do SHOPMAN_BFF_PROXY_SECRET do Django. Vazio = desligado.
    djangoProxySecret: "",
    // Nome do SERVIÇO no aviso de capacidade (server/utils/capacityReport.ts). Com
    // vários apps no mesmo contêiner, o deploy declara NUXT_OPERATOR_SERVICE_NAME
    // (`operator-floor`, `operator-office`) e todos reportam como um serviço só.
    // Vazio = a identidade do app (`operatorPwa.app`), certo com um app por contêiner.
    operatorServiceName: "",
    public: {
      // URL da Central (a home) — o ícone do app no topo do OperatorRail leva
      // pra cá (padrão Odoo). Dev: hub-nuxt em :3001; prod: central.<zona> via env.
      operatorHubUrl: process.env.NUXT_PUBLIC_OPERATOR_HUB_URL || "http://127.0.0.1:3001/",
      // Estado inicial do rail (só quando não há cookie ainda). Padrão compacto em todos,
      // a Central inclusive desde a camada da suíte (o rail dela tem "Início" e Avisos).
      railDefaultState: process.env.NUXT_PUBLIC_RAIL_DEFAULT_STATE || "compact",
      // URL do Gestor de Pedidos (orders-nuxt) — links cross-app "abrir no gestor"
      // apontam pra cá. Dev: orders-nuxt em :3004; prod: gestor.<zona> via env.
      ordersUrl: process.env.NUXT_PUBLIC_ORDERS_URL || "http://127.0.0.1:3004/",
      // URL do PDV — usada pela Central para o atalho instalável same-origin que
      // então redireciona ao app dedicado. O destino continua dado de deploy.
      posUrl: process.env.NUXT_PUBLIC_POS_URL || "http://127.0.0.1:3002/",
      // URL do Produção (production-nuxt) — links cross-app "resolver na produção"
      // (ex.: fechamento do dia com ordens abertas). Dev: :3005; prod: prod.<zona>.
      productionUrl: process.env.NUXT_PUBLIC_PRODUCTION_URL || "http://127.0.0.1:3005/",
      // A antessala deste app ("estou travado? quem está operando?"). O padrão é a
      // compartilhada, e ele serve a todo app de operador ATENDIDO.
      //
      // ⚠️ NÃO é env, e não é preferência: é o outro lado de uma trava de servidor.
      // Uma estação AUTÔNOMA (painel de parede da Produção, sem ninguém para digitar
      // PIN) só tem a conta dela resolvida sob `/api/v1/backstage/production/` — o
      // cookie de estação vale no domínio inteiro, e essa é a única barreira que
      // impede a conta do painel de virar operador no PDV da aba ao lado (ver
      // `shopman/backstage/station_trust.py`). Por isso a Produção aponta esta
      // chave para a antessala DELA; um app que não é a Produção não tem por que
      // mexer aqui, e mexer não lhe dá nada — quem decide é o servidor.
      operatorSessionPath: "/api/v1/backstage/operator/session/",
    },
  },
});
