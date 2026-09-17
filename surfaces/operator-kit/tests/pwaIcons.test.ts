import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { describe, expect, it } from "vitest";
import { FAVICON_VERSION, OPERATOR_HEAD_LINKS } from "../pwa.config";

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
// sha256 do `public/favicon.ico` do template do Nuxt (o logo verde, 32×32). Os apps de
// operador nasceram com ele e a aba mostrava o Nuxt em vez do app até 17/09/2026.
const NUXT_DEFAULT_FAVICON_SHA256 = "1057b17aec08a7191d134000203947f195a8aa7c84c39f1164cee8d01279762a";
const FAVICON_SIZES = [16, 32, 48] as const;

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

/** Quadros PNG de um `.ico`, por lado em px (0 no cabeçalho = 256). */
function icoFrames(bytes: Buffer): Map<number, Buffer> {
  expect(bytes.readUInt16LE(0)).toBe(0);
  expect(bytes.readUInt16LE(2)).toBe(1);
  const frames = new Map<number, Buffer>();
  for (let index = 0; index < bytes.readUInt16LE(4); index += 1) {
    const entry = 6 + index * 16;
    const size = bytes.readUInt8(entry) || 256;
    const length = bytes.readUInt32LE(entry + 8);
    const offset = bytes.readUInt32LE(entry + 12);
    frames.set(size, bytes.subarray(offset, offset + length));
  }
  return frames;
}

async function rgbaAt(image: Buffer, x: (size: number) => number, y: (size: number) => number) {
  const { data, info } = await sharp(image).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const start = (y(info.height) * info.width + x(info.width)) * 4;
  return [...data.subarray(start, start + 4)];
}

function backgroundOf(app: string): number[] {
  const scripts = JSON.parse(readFileSync(resolve(surfacesDir, app, "package.json"), "utf8")).scripts;
  const hex = /--background=#([0-9A-Fa-f]{6})/.exec(scripts["pwa:assets"])?.[1];
  expect(hex, `${app} declara --background no pwa:assets`).toBeTruthy();
  return [0, 2, 4].map((start) => Number.parseInt(hex!.slice(start, start + 2), 16));
}

// A aba do navegador mostra a identidade do app (PWA_ICONS.md, "Favicon da aba"): a
// mesma arte arredondada do ícone `any`, gerada por `pwa:assets`, nunca o logo do Nuxt.
describe.each(OPERATOR_APPS)("favicon de %s", (app) => {
  const publicDir = resolve(surfacesDir, app, "public");

  it("favicon.ico existe e não é o logo padrão do Nuxt", () => {
    const path = resolve(publicDir, "favicon.ico");
    expect(existsSync(path)).toBe(true);
    const sha = createHash("sha256").update(readFileSync(path)).digest("hex");
    expect(sha).not.toBe(NUXT_DEFAULT_FAVICON_SHA256);
  });

  it("favicon.ico traz 16, 32 e 48 px de canto transparente, na cor do app", async () => {
    const frames = icoFrames(readFileSync(resolve(publicDir, "favicon.ico")));
    expect([...frames.keys()].sort((a, b) => a - b)).toEqual([...FAVICON_SIZES]);
    for (const size of FAVICON_SIZES) {
      const frame = frames.get(size)!;
      const { width, height } = await sharp(frame).metadata();
      expect([width, height]).toEqual([size, size]);
      expect((await rgbaAt(frame, () => 0, () => 0))[3]).toBe(0);
    }
    const frame48 = frames.get(48)!;
    expect((await rgbaAt(frame48, () => 2, () => 2))[3]).toBe(0);
    expect((await rgbaAt(frame48, (w) => w - 1, (h) => h - 1))[3]).toBe(0);
    expect(await rgbaAt(frame48, (w) => Math.floor(w / 2), () => 0)).toEqual([...backgroundOf(app), 255]);
  });

  it("favicon.svg é o retângulo arredondado com canto transparente", async () => {
    const svg = readFileSync(resolve(publicDir, "favicon.svg"));
    expect(svg.toString()).toMatch(/<rect [^>]*rx="10\.8"/);
    const image = await sharp(svg).resize(48, 48).png().toBuffer();
    expect((await rgbaAt(image, () => 0, () => 0))[3]).toBe(0);
    expect(await rgbaAt(image, (w) => Math.floor(w / 2), () => 0)).toEqual([...backgroundOf(app), 255]);
  });

  it("recebe os links de favicon da capability PWA, sem declarar outro", () => {
    const config = readFileSync(resolve(surfacesDir, app, "nuxt.config.ts"), "utf8");
    expect(config).toContain("definePwaCapability(");
    expect(config).not.toMatch(/rel:\s*["']icon["']/);
  });
});

describe("links de favicon no <head> dos apps de operador", () => {
  it(`declaram SVG e ICO com ${FAVICON_VERSION} (a aba guarda o ícone pela URL)`, () => {
    expect(OPERATOR_HEAD_LINKS).toEqual(expect.arrayContaining([
      { rel: "icon", type: "image/svg+xml", href: `/favicon.svg${FAVICON_VERSION}` },
      { rel: "icon", sizes: "48x48", href: `/favicon.ico${FAVICON_VERSION}` },
    ]));
  });
});
