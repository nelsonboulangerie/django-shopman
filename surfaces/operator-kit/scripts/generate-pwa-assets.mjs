import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
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

const output = resolve(argument("out"));
const background = argument("background", "#34373B");
const foreground = argument("foreground", "#FCF7EE");
const iconReference = argument("icon");

if (!argument("out") || !iconReference) {
  throw new Error("uso: --icon=<lucide|tabler>:<name> --out=<public/pwa> [--background=#RRGGBB] [--foreground=#RRGGBB]");
}

const [collectionName, iconName, ...extra] = iconReference.split(":");
const collection = collections[collectionName];
const icon = collection?.icons?.[iconName];
if (!collection || !icon || extra.length > 0) {
  throw new Error(`ícone PWA desconhecido: ${iconReference}`);
}

const iconWidth = icon.width || collection.width || 24;
const iconHeight = icon.height || collection.height || 24;
const iconBody = icon.body.replaceAll("currentColor", foreground);

function iconSvg(size, symbolRatio) {
  const symbolWidth = size * symbolRatio;
  const symbolHeight = symbolWidth * (iconHeight / iconWidth);
  const scale = symbolWidth / iconWidth;
  const left = (size - symbolWidth) / 2;
  const top = (size - symbolHeight) / 2;
  return Buffer.from(`
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <rect width="${size}" height="${size}" fill="${background}"/>
      <g transform="translate(${left} ${top}) scale(${scale})">${iconBody}</g>
    </svg>
  `);
}

async function renderIcon(name, size, symbolRatio) {
  await sharp(iconSvg(size, symbolRatio))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(resolve(output, name));
}

await mkdir(output, { recursive: true });
await Promise.all([
  renderIcon("pwa-64x64.png", 64, 0.56),
  renderIcon("pwa-192x192.png", 192, 0.56),
  renderIcon("pwa-512x512.png", 512, 0.56),
  renderIcon("maskable-512x512.png", 512, 0.48),
  renderIcon("apple-touch-icon-180x180.png", 180, 0.56),
]);

process.stdout.write(`assets PWA ${iconReference} gerados em ${output}\n`);
