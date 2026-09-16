import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import sharp from "sharp";

function argument(name, fallback = "") {
  const prefix = `--${name}=`;
  return process.argv.find((value) => value.startsWith(prefix))?.slice(prefix.length) || fallback;
}

const source = resolve(argument("source"));
const output = resolve(argument("out"));
const background = argument("background", "#8B6B2E");
const ink = argument("ink", "#3B2A1E");
const paper = argument("paper", "#FCF6F1");
const badgeLabel = argument("badge", "");

if (!argument("source") || !argument("out")) {
  throw new Error("uso: --source=<nelson-mark.svg> --out=<public/pwa>");
}

const markSource = (await readFile(source, "utf8"))
  .replaceAll("#ffd25c", paper)
  .replaceAll("#FFD25C", paper)
  .replaceAll("#a37316", ink)
  .replaceAll("#A37316", ink);

function badgeSvg(size) {
  const escapedLabel = badgeLabel
    .slice(0, 3)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  if (escapedLabel) {
    const fontSize = escapedLabel.length > 2 ? 37 : escapedLabel.length > 1 ? 43 : 50;
    return Buffer.from(`
      <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="56" fill="${ink}" stroke="${paper}" stroke-width="6"/>
        <text x="60" y="64" fill="${paper}" font-family="Arial, Helvetica, sans-serif"
          font-size="${fontSize}" font-weight="700" text-anchor="middle" dominant-baseline="middle">${escapedLabel}</text>
      </svg>
    `);
  }
  return Buffer.from(`
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="56" fill="${ink}" stroke="${paper}" stroke-width="6"/>
      <g fill="none" stroke="${paper}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">
        <path d="M37 50h46l7 31H30l7-31Z"/>
        <path d="M43 35h34v15H43zM39 66h42M45 81v8M75 81v8"/>
        <path d="M48 59h2M60 59h2M72 59h2"/>
      </g>
    </svg>
  `);
}

async function renderIcon(name, size, safe = false) {
  const markSize = Math.round(size * (safe ? 0.61 : 0.72));
  const badgeSize = Math.round(size * (safe ? 0.21 : 0.23));
  const mark = await sharp(Buffer.from(markSource)).resize(markSize, markSize).png().toBuffer();
  const badge = await sharp(badgeSvg(badgeSize)).png().toBuffer();
  const badgeInset = Math.round(size * (safe ? 0.105 : 0.07));

  await sharp({
    create: { width: size, height: size, channels: 4, background },
  })
    .composite([
      { input: mark, left: Math.round((size - markSize) / 2), top: Math.round((size - markSize) / 2) },
      { input: badge, left: size - badgeSize - badgeInset, top: size - badgeSize - badgeInset },
    ])
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(resolve(output, name));
}

await mkdir(output, { recursive: true });
await Promise.all([
  renderIcon("pwa-64x64.png", 64),
  renderIcon("pwa-192x192.png", 192),
  renderIcon("pwa-512x512.png", 512),
  renderIcon("maskable-512x512.png", 512, true),
  renderIcon("apple-touch-icon-180x180.png", 180, true),
]);

process.stdout.write(`assets PWA gerados em ${output}\n`);
