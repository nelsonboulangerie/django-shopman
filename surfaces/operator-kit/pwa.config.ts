import { addPlugin, addServerHandler, createResolver, defineNuxtModule, installModule } from "@nuxt/kit";
import type { NuxtConfig } from "@nuxt/schema";
import VitePwaModule from "@vite-pwa/nuxt";
import type { ModuleOptions as VitePwaModuleOptions } from "@vite-pwa/nuxt";

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
  name: string;
  shortName: string;
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
  idleReloadPaths?: string[];
}

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
      name: "",
      shortName: "",
      description: "",
      themeColor: "#F5F5F4",
      backgroundColor: "#FAFAF9",
      icons: [],
      orientation: "any",
    },
    wakeLock: false,
    kiosk: false,
    idleReloadPaths: [],
  },
  async setup(options, nuxt) {
    if (!options.app.trim()) throw new TypeError("operator PWA exige app");
    if (!options.manifest.name.trim() || !options.manifest.shortName.trim()) {
      throw new TypeError("operator PWA exige name e shortName");
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
    if (!options.kiosk && options.idleReloadPaths?.length) {
      throw new TypeError("operator PWA sem kiosk não aceita recarga ociosa");
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
    const managedLinks = new Set(["manifest", "apple-touch-icon"]);
    head.meta = [
      ...(head.meta || []).filter((entry) => !managedMeta.has(String(entry.name || ""))),
      { name: "theme-color", content: options.manifest.themeColor },
      { name: "apple-mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-status-bar-style", content: "default" },
      { name: "apple-mobile-web-app-title", content: options.manifest.shortName },
    ];
    head.link = [
      ...(head.link || []).filter((entry) => !managedLinks.has(String(entry.rel || ""))),
      { rel: "manifest", href: "/manifest.webmanifest" },
      { rel: "apple-touch-icon", href: "/pwa/apple-touch-icon-180x180.png" },
    ];

    addServerHandler({
      route: "/manifest.webmanifest",
      handler: resolver.resolve("./runtime/server/manifest"),
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
