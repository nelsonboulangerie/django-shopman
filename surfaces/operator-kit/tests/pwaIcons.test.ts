import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { describe, expect, it } from "vitest";

// Varredura da FORMA dos ícones instalados das oito superfícies de operador
// (PWA_ICONS.md, "Forma: quem arredonda o canto"). Windows/macOS/Linux desktop mostram
// o ícone `any` sem máscara: um quadrado cheio aparecia de quinas vivas no menu Iniciar
// (PDV no Windows, 17/09/2026). O launcher Android recorta o `maskable` e o iOS
// arredonda o `apple-touch-icon` — esses dois ficam cheios e opacos.
//
// Varredura, não amostra: um app regerado com o gerador antigo (ou PNG trocado à mão)
// reprova aqui, e o manifesto apontando para `?v=` velho também.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = [
  "hub-nuxt", "pos-nuxt", "kds-nuxt", "orders-nuxt",
  "production-nuxt", "marketing-nuxt", "purchase-nuxt", "bi-nuxt",
] as const;
const ROUNDED = ["pwa-64x64.png", "pwa-192x192.png", "pwa-512x512.png"] as const;
const FULL_BLEED = ["maskable-512x512.png", "apple-touch-icon-180x180.png"] as const;
const ICON_VERSION = "?v=3";

async function alphaAt(app: string, file: string, x: (size: number) => number, y: (size: number) => number) {
  const { data, info } = await sharp(resolve(surfacesDir, app, "public/pwa", file))
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  return data[(y(info.height) * info.width + x(info.width)) * 4 + 3];
}

describe.each(OPERATOR_APPS)("ícones PWA de %s", (app) => {
  it.each(ROUNDED)("%s (purpose any) tem canto transparente e borda cheia", async (file) => {
    expect(await alphaAt(app, file, () => 0, () => 0)).toBe(0);
    expect(await alphaAt(app, file, (w) => Math.floor(w * 0.04), (h) => Math.floor(h * 0.04))).toBe(0);
    expect(await alphaAt(app, file, (w) => Math.floor(w / 2), () => 0)).toBe(255);
    expect(await alphaAt(app, file, () => 0, (h) => Math.floor(h / 2))).toBe(255);
  });

  it.each(FULL_BLEED)("%s continua cheio e opaco (o SO recorta)", async (file) => {
    expect(await alphaAt(app, file, () => 0, () => 0)).toBe(255);
  });

  it(`manifesto aponta os ícones com ${ICON_VERSION} (o SO só relê ícone com URL nova)`, () => {
    const config = readFileSync(resolve(surfacesDir, app, "nuxt.config.ts"), "utf8");
    const iconUrls = config.match(/\/pwa\/[\w-]+\.png\?v=\d+/g) || [];
    expect(iconUrls.length).toBeGreaterThan(0);
    for (const url of iconUrls) expect(url).toContain(ICON_VERSION);
  });
});
