import { addPlugin, addServerHandler, createResolver, defineNuxtModule, installModule } from "@nuxt/kit";
import type { NuxtConfig } from "@nuxt/schema";
import VitePwaModule from "@vite-pwa/nuxt";
import type { ModuleOptions as VitePwaModuleOptions } from "@vite-pwa/nuxt";
import { OPERATOR_APP_NAME_ROUTE } from "./app/presentation/windowTitle";

export interface OperatorPwaIcon {
  src: string;
  sizes: string;
  type?: string;
  purpose?: "any" | "maskable" | "monochrome";
}

export interface OperatorPwaShortcut {
  name: string;
  shortName?: string;
  url: string;
  icon?: string;
}

export interface OperatorPwaManifestOptions {
  /**
   * Rótulo do app ("PDV"), e só ele. O nome instalado é `"<casa> · <rótulo>"`, com a
   * casa (`Shop.short_name`) lida do Django em runtime — ver
   * `server/utils/operatorTenant.ts`. Sem hífen e sem prefixo de marca aqui.
   */
  label: string;
  description: string;
  themeColor: string;
  backgroundColor: string;
  icons: OperatorPwaIcon[];
  shortcuts?: OperatorPwaShortcut[];
  orientation?: "any" | "natural" | "landscape" | "portrait";
}

export interface OperatorPwaCapabilityOptions {
  app: string;
  display: "standalone" | "fullscreen";
  manifest: OperatorPwaManifestOptions;
  wakeLock?: boolean;
  kiosk?: boolean;
  /**
   * Rotas em que o app pode RECARREGAR SOZINHO para entrar na versão nova, quando
   * ninguém toca nele e a tela não publicou nenhuma razão de espera
   * (`useOperatorReloadHold`). Lista vazia = só o aviso ao operador.
   *
   * `"*"` libera tudo (KDS: nenhuma tela dele tem rascunho); `"/board"` libera o
   * painel e o que está sob ele, e preserva os editores de receita; `"/"` libera
   * SÓ a raiz. Kiosk exige a lista: um painel de parede que ninguém fecha nunca
   * trocaria de versão sem ela.
   */
  idleReloadPaths?: string[];
  push?: {
    surfaceRef: "hub" | "orders" | "pos" | "production" | "marketing" | "purchase" | "bi";
    categories: Array<"campaign" | "production" | "order" | "purchase" | "report" | "sign_in" | "system">;
  };
}

/** Suba junto com a forma/desenho do favicon: a aba guarda o ícone pela URL. */
export const FAVICON_VERSION = "?v=1";

/**
 * Links de `<head>` que a capability PWA assume em todo app de operador. Os ícones
 * saem de `pwa:assets` (PWA_ICONS.md). O favicon `.ico` (16/32/48) declara tamanho em
 * vez de `sizes="any"`: com `any` o Chrome prefere o `.ico` ao SVG.
 */
export const OPERATOR_HEAD_LINKS = [
  { rel: "manifest", href: "/manifest.webmanifest" },
  { rel: "apple-touch-icon", href: "/pwa/apple-touch-icon-180x180.png?v=3" },
  { rel: "icon", type: "image/svg+xml", href: `/favicon.svg${FAVICON_VERSION}` },
  { rel: "icon", sizes: "48x48", href: `/favicon.ico${FAVICON_VERSION}` },
] as const;

function namesImport(entry: unknown, name: string): boolean {
  if (typeof entry === "string") return entry === name;
  if (Array.isArray(entry)) return entry[0] === name || entry[1] === name;
  if (!entry || typeof entry !== "object") return false;
  const candidate = entry as { name?: unknown; as?: unknown };
  return candidate.name === name || candidate.as === name;
}

const pwaCapabilityModule = defineNuxtModule<OperatorPwaCapabilityOptions>({
  meta: {
    name: "@shopman/operator-pwa",
    configKey: "operatorPwa",
  },
  defaults: {
    app: "",
    display: "standalone",
    manifest: {
      label: "",
      description: "",
      themeColor: "#F5F5F4",
      backgroundColor: "#FAFAF9",
      icons: [],
      orientation: "any",
    },
    wakeLock: false,
    kiosk: false,
    idleReloadPaths: [],
    push: undefined,
  },
  async setup(options, nuxt) {
    if (!options.app.trim()) throw new TypeError("operator PWA exige app");
    if (!options.manifest.label.trim()) {
      throw new TypeError("operator PWA exige label");
    }
    if (/\s[-–—|·]\s|^Shopman\b/i.test(options.manifest.label)) {
      throw new TypeError("operator PWA: label é só o app; a casa vem do Shop.short_name");
    }
    if (!options.manifest.icons.some((icon) => icon.sizes === "192x192")) {
      throw new TypeError("operator PWA exige ícone 192x192");
    }
    if (!options.manifest.icons.some((icon) => icon.sizes === "512x512")) {
      throw new TypeError("operator PWA exige ícone 512x512");
    }
    if (options.kiosk && !options.idleReloadPaths?.length) {
      throw new TypeError("operator PWA kiosk exige rotas explícitas para recarga ociosa");
    }
    if (options.push && (!options.push.categories.length || new Set(options.push.categories).size !== options.push.categories.length)) {
      throw new TypeError("operator PWA push exige categorias explícitas e sem repetição");
    }

    const resolver = createResolver(import.meta.url);
    nuxt.hook("modules:done", () => {
      nuxt.hook("imports:sources", (sources) => {
        // @vueuse/nuxt também exporta um useWakeLock, mas o contrato Shopman
        // inclui reaquisição e falha silenciosa próprias. Remover só esse símbolo
        // da fonte depois de todos os módulos evita ambiguidade sem desligar VueUse.
        for (const source of sources) {
          if (!("from" in source) || source.from !== "@vueuse/core" || !Array.isArray(source.imports)) continue;
          source.imports = source.imports.filter((entry) => !namesImport(entry, "useWakeLock"));
        }
      });
    });
    const publicConfig = nuxt.options.runtimeConfig.public as Record<string, unknown>;
    publicConfig.operatorPwa = JSON.parse(JSON.stringify(options));
    publicConfig.vapidPublicKey = process.env.NUXT_PUBLIC_VAPID_PUBLIC_KEY || "";
    publicConfig.appVersion = process.env.NUXT_PUBLIC_APP_VERSION || process.env.SOURCE_VERSION || "local";

    // O `sw.js` é o ÚNICO arquivo que não pode ser servido de cache: ele é a porta
    // pela qual toda versão nova entra. `no-cache` obriga revalidação a cada sonda
    // de `registration.update()` — sem isso, a sonda periódica perguntaria ao disco
    // do navegador e responderia "nada novo" para sempre.
    const routeRules = nuxt.options.routeRules ||= {};
    routeRules["/sw.js"] = {
      ...routeRules["/sw.js"],
      headers: {
        ...routeRules["/sw.js"]?.headers,
        "cache-control": "no-cache, no-store, must-revalidate",
      },
    };

    const head = nuxt.options.app.head;
    const managedMeta = new Set([
      "theme-color",
      "apple-mobile-web-app-capable",
      "apple-mobile-web-app-status-bar-style",
      "apple-mobile-web-app-title",
    ]);
    const managedLinks = new Set<string>(OPERATOR_HEAD_LINKS.map((link) => link.rel));
    head.meta = [
      ...(head.meta || []).filter((entry) => !managedMeta.has(String(entry.name || ""))),
      { name: "theme-color", content: options.manifest.themeColor },
      { name: "apple-mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-status-bar-style", content: "default" },
      // Valor inicial; o plugin `operatorAppName` troca pelo nome com a casa em runtime.
      { name: "apple-mobile-web-app-title", content: options.manifest.label },
    ];
    head.link = [
      ...(head.link || []).filter((entry) => !managedLinks.has(String(entry.rel || ""))),
      ...OPERATOR_HEAD_LINKS.map((link) => ({ ...link })),
    ];

    addServerHandler({
      route: "/manifest.webmanifest",
      handler: resolver.resolve("./runtime/server/manifest"),
    });
    addServerHandler({
      route: OPERATOR_APP_NAME_ROUTE,
      handler: resolver.resolve("./runtime/server/appName"),
    });
    if (options.push) {
      addServerHandler({
        route: "/operator-push-sw.js",
        handler: resolver.resolve("./runtime/server/push-worker"),
      });
    }
    addPlugin({
      src: resolver.resolve("./runtime/plugins/operatorAppName"),
    });
    addPlugin({
      src: resolver.resolve("./runtime/plugins/pwaRegistration.client"),
      mode: "client",
    });

    const vitePwaOptions: VitePwaModuleOptions = {
      manifest: false,
      strategies: "generateSW",
      registerType: "prompt",
      injectRegister: false,
      client: {
        registerPlugin: false,
        installPrompt: false,
        periodicSyncForUpdates: 0,
      },
      workbox: {
        navigateFallback: null,
        navigationPreload: false,
        cleanupOutdatedCaches: true,
        clientsClaim: false,
        skipWaiting: false,
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        // Preserve the real public filenames. Nuxt's default transform turns
        // `offline.html` into `offline`, while the navigation fallback must
        // address the committed static shell by its exact URL.
        manifestTransforms: [async entries => ({ manifest: entries, warnings: [] })],
        importScripts: options.push ? ["/operator-push-sw.js"] : undefined,
        runtimeCaching: [
          {
            urlPattern: ({ request }: { request: Request }) => request.mode === "navigate",
            handler: "NetworkOnly",
            options: { precacheFallback: { fallbackURL: "/offline.html" } },
          },
          {
            urlPattern: ({ url }: { url: URL }) => url.origin === self.location.origin
              && url.pathname.startsWith("/img/products/"),
            handler: "CacheFirst",
            options: { cacheName: `${options.app}-product-images` },
          },
          {
            urlPattern: ({ url }: { url: URL }) => url.origin === self.location.origin
              && url.pathname.startsWith("/fonts/"),
            handler: "CacheFirst",
            options: { cacheName: `${options.app}-fonts` },
          },
        ],
      },
      devOptions: { enabled: false },
    };
    await installModule(VitePwaModule, vitePwaOptions);
  },
});

/** Capability explícita: somente apps que a colocam em `modules` ganham PWA. */
export function definePwaCapability(
  options: OperatorPwaCapabilityOptions,
): NonNullable<NuxtConfig["modules"]>[number] {
  return [pwaCapabilityModule, options] as unknown as NonNullable<NuxtConfig["modules"]>[number];
}
