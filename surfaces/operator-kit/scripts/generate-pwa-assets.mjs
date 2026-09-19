import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const require = createRequire(import.meta.url);
const collections = {
  lucide: require("@iconify-json/lucide/icons.json"),
  tabler: require("@iconify-json/tabler/icons.json"),
};

function argument(name, fallback = "") {
  const prefix = `--${name}=`;
  return process.argv.find((value) => value.startsWith(prefix))?.slice(prefix.length) || fallback;
}

// Símbolo e cor saíam da linha de comando de cada `package.json`, e a mesma cor estava
// escrita de novo no `nuxt.config` e no gate de PWA — três cópias para manter a página, o
// ícone e a barra de título iguais. Agora o gerador recebe só a CHAVE do app e pergunta
// à identidade canônica, a mesma que o manifesto lê.
const identityPath = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app-identity.json");
const identity = JSON.parse(await readFile(identityPath, "utf8"));
const app = argument("app");

if (!argument("out") || !app) {
  throw new Error("uso: --app=<hub|pos|kds|orders|production|marketing|purchase|bi> --out=<public/pwa>");
}
if (!identity.apps[app]) {
  throw new Error(`app de operador desconhecido: ${app} (ver ${identityPath})`);
}

const output = resolve(argument("out"));
// O favicon da aba mora na raiz do `public/` (o navegador pede `/favicon.ico` sozinho,
// até em página sem `<head>`), um nível acima dos PNGs PWA.
const faviconOutput = dirname(output);
const background = identity.apps[app].color;
const foreground = identity.foreground;
const iconReference = identity.apps[app].symbol;

const [collectionName, iconName, ...extra] = iconReference.split(":");
const collection = collections[collectionName];
const icon = collection?.icons?.[iconName];
if (!collection || !icon || extra.length > 0) {
  throw new Error(`ícone PWA desconhecido: ${iconReference}`);
}

const iconWidth = icon.width || collection.width || 24;
const iconHeight = icon.height || collection.height || 24;
const iconBody = icon.body.replaceAll("currentColor", foreground);

// Raio do canto do ícone `purpose: any`, em fração do lado — o padrão de ícone de app
// (squircle do iOS ≈ 22,37%). Windows, macOS e Linux desktop mostram o ícone `any` COMO
// ESTÁ, sem máscara: um quadrado cheio vira um azulejo de quinas vivas no menu Iniciar e
// na barra de tarefas. Só o launcher Android recorta, e ele usa o `maskable`.
const ICON_CORNER_RATIO = 0.225;

/** Engrossa o traço do desenho (Lucide/Tabler declaram `stroke-width` explícito). */
function strokedBody(strokeScale) {
  if (strokeScale === 1) return iconBody;
  return iconBody.replace(/stroke-width="([\d.]+)"/g, (_, width) => `stroke-width="${Number(width) * strokeScale}"`);
}

/**
 * `shape: "rounded"` → fundo num retângulo arredondado, transparente fora dele (ícone
 * `any`). `shape: "full"` → quadrado opaco de ponta a ponta: o `maskable` (o launcher
 * recorta, a arte fica na zona segura de 80%) e o `apple-touch-icon` (o iOS arredonda
 * sozinho e pinta de preto o que for transparente).
 */
function iconSvg(size, symbolRatio, shape, strokeScale = 1) {
  const symbolWidth = size * symbolRatio;
  const symbolHeight = symbolWidth * (iconHeight / iconWidth);
  const scale = symbolWidth / iconWidth;
  const left = (size - symbolWidth) / 2;
  const top = (size - symbolHeight) / 2;
  const radius = shape === "rounded" ? size * ICON_CORNER_RATIO : 0;
  return Buffer.from(`
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <rect width="${size}" height="${size}" rx="${radius}" ry="${radius}" fill="${background}"/>
      <g transform="translate(${left} ${top}) scale(${scale})">${strokedBody(strokeScale)}</g>
    </svg>
  `);
}

async function renderIcon(name, size, symbolRatio, shape) {
  await sharp(iconSvg(size, symbolRatio, shape))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(resolve(output, name));
}

// Favicon da aba: a MESMA arte do ícone `any` (fundo arredondado, canto transparente),
// com símbolo maior e traço mais grosso quanto menor o pixel. Em 16 px a proporção do
// PWA (56%, traço 2) vira um borrão de 0,75 px de linha; 78% com traço 3 é o maior que
// cabe sem o desenho encostar na curva do canto. Medido renderizando as oito famílias
// lado a lado em 16/32 px (17/09/2026), não suposto.
const FAVICON_ART = {
  16: { symbolRatio: 0.78, strokeScale: 1.5 },
  32: { symbolRatio: 0.7, strokeScale: 1.25 },
  48: { symbolRatio: 0.66, strokeScale: 1.125 },
};
// O SVG é o que Chrome/Firefox/Safari usam na aba, e a aba é sempre 16 px CSS (32 px de
// tela em HiDPI): leva a arte de 16, que em 32 ainda fica limpa, só mais encorpada.
const FAVICON_SVG_ART = FAVICON_ART[16];
const FAVICON_SVG_SIZE = 48;

function faviconPng(size) {
  const { symbolRatio, strokeScale } = FAVICON_ART[size];
  return sharp(iconSvg(size, symbolRatio, "rounded", strokeScale))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toBuffer();
}

/** ICO com PNG embutido (aceito por todo navegador atual), um quadro por tamanho. */
function icoFromPngs(entries) {
  const header = Buffer.alloc(6 + entries.length * 16);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entries.length, 4);
  let offset = header.length;
  entries.forEach(({ size, png }, index) => {
    const entry = 6 + index * 16;
    header.writeUInt8(size >= 256 ? 0 : size, entry);
    header.writeUInt8(size >= 256 ? 0 : size, entry + 1);
    header.writeUInt8(0, entry + 2);
    header.writeUInt8(0, entry + 3);
    header.writeUInt16LE(1, entry + 4);
    header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(png.length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += png.length;
  });
  return Buffer.concat([header, ...entries.map(({ png }) => png)]);
}

async function renderFavicons() {
  const sizes = [16, 32, 48];
  const pngs = await Promise.all(sizes.map((size) => faviconPng(size)));
  await writeFile(
    resolve(faviconOutput, "favicon.ico"),
    icoFromPngs(sizes.map((size, index) => ({ size, png: pngs[index] }))),
  );
  const svg = iconSvg(FAVICON_SVG_SIZE, FAVICON_SVG_ART.symbolRatio, "rounded", FAVICON_SVG_ART.strokeScale)
    .toString()
    .replace(/\n\s*/g, "")
    .replace(/\d+\.\d{5,}/g, (number) => String(Number(Number(number).toFixed(4))))
    .replace(` width="${FAVICON_SVG_SIZE}" height="${FAVICON_SVG_SIZE}"`, "");
  await writeFile(resolve(faviconOutput, "favicon.svg"), `${svg}\n`);
}

await mkdir(output, { recursive: true });
await Promise.all([
  renderIcon("pwa-64x64.png", 64, 0.56, "rounded"),
  renderIcon("pwa-192x192.png", 192, 0.56, "rounded"),
  renderIcon("pwa-512x512.png", 512, 0.56, "rounded"),
  renderIcon("maskable-512x512.png", 512, 0.48, "full"),
  renderIcon("apple-touch-icon-180x180.png", 180, 0.56, "full"),
  renderFavicons(),
]);

process.stdout.write(`assets PWA ${iconReference} gerados em ${output} (favicon em ${faviconOutput})\n`);
