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

// Raio do canto do ícone `purpose: any`, em fração do lado — o padrão de ícone de app
// (squircle do iOS ≈ 22,37%). Windows, macOS e Linux desktop mostram o ícone `any` COMO
// ESTÁ, sem máscara: um quadrado cheio vira um azulejo de quinas vivas no menu Iniciar e
// na barra de tarefas. Só o launcher Android recorta, e ele usa o `maskable`.
const ICON_CORNER_RATIO = 0.225;

/**
 * `shape: "rounded"` → fundo num retângulo arredondado, transparente fora dele (ícone
 * `any`). `shape: "full"` → quadrado opaco de ponta a ponta: o `maskable` (o launcher
 * recorta, a arte fica na zona segura de 80%) e o `apple-touch-icon` (o iOS arredonda
 * sozinho e pinta de preto o que for transparente).
 */
function iconSvg(size, symbolRatio, shape) {
  const symbolWidth = size * symbolRatio;
  const symbolHeight = symbolWidth * (iconHeight / iconWidth);
  const scale = symbolWidth / iconWidth;
  const left = (size - symbolWidth) / 2;
  const top = (size - symbolHeight) / 2;
  const radius = shape === "rounded" ? size * ICON_CORNER_RATIO : 0;
  return Buffer.from(`
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <rect width="${size}" height="${size}" rx="${radius}" ry="${radius}" fill="${background}"/>
      <g transform="translate(${left} ${top}) scale(${scale})">${iconBody}</g>
    </svg>
  `);
}

async function renderIcon(name, size, symbolRatio, shape) {
  await sharp(iconSvg(size, symbolRatio, shape))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(resolve(output, name));
}

await mkdir(output, { recursive: true });
await Promise.all([
  renderIcon("pwa-64x64.png", 64, 0.56, "rounded"),
  renderIcon("pwa-192x192.png", 192, 0.56, "rounded"),
  renderIcon("pwa-512x512.png", 512, 0.56, "rounded"),
  renderIcon("maskable-512x512.png", 512, 0.48, "full"),
  renderIcon("apple-touch-icon-180x180.png", 180, 0.56, "full"),
]);

process.stdout.write(`assets PWA ${iconReference} gerados em ${output}\n`);
