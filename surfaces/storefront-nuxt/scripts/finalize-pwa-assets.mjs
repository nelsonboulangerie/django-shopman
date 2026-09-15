import {
  copyFile,
  readFile,
  writeFile
} from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const root = new URL('../', import.meta.url)
const sourceMark = new URL('brand/nelson-mark.svg', root)
const sourceLogo = new URL('brand/nelson-logo.svg', root)
const splashScreensSource = new URL('pwa-splash-screens.json', root)
const output = new URL('public/pwa/', root)

const source = await readFile(sourceMark, 'utf8')
const monochrome = source
  .replace(/\s*<path class="st0" d="M639,320[^>]+\/>/, '')
  .replace(/fill:\s*#[0-9a-f]{6};/gi, 'fill: #000000;')

const paperTexture = (width, height) => Buffer.from(`
  <svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <pattern id="grain" width="47" height="53" patternUnits="userSpaceOnUse">
        <circle cx="8" cy="11" r="1.1" fill="#fff4da" opacity=".12"/>
        <circle cx="34" cy="29" r=".9" fill="#4c2f1d" opacity=".08"/>
        <circle cx="19" cy="45" r=".7" fill="#fff4da" opacity=".08"/>
        <path d="M-4 18L51 24M-8 42L44 47" stroke="#4c2f1d" stroke-width=".7" opacity=".035"/>
        <path d="M12-5L15 58M39-7L41 56" stroke="#fff4da" stroke-width=".6" opacity=".03"/>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#grain)"/>
  </svg>
`)

const splashScreens = JSON.parse(await readFile(splashScreensSource, 'utf8'))
const logo = await readFile(sourceLogo)

function splashLogoBounds (width, height) {
  // Equivalente ao padding CSS anteriormente renderizado pelo Chromium:
  // calc(50vh - min(17vw, 20vh)) calc(50vw - min(37vw, 43vh)).
  return {
    width: Math.round(2 * Math.min(0.37 * width, 0.43 * height)),
    height: Math.round(2 * Math.min(0.17 * width, 0.20 * height))
  }
}

for (const [width, height] of splashScreens) {
  const bounds = splashLogoBounds(width, height)
  const resizedLogo = await sharp(logo)
    .resize(bounds.width, bounds.height, {
      fit: 'contain',
      background: { r: 0, g: 0, b: 0, alpha: 0 }
    })
    .png()
    .toBuffer()
  const metadata = await sharp(resizedLogo).metadata()

  await sharp({
    create: {
      width,
      height,
      channels: 4,
      background: '#D0A66E'
    }
  })
    .composite([
      {
        input: resizedLogo,
        left: Math.floor((width - metadata.width) / 2),
        top: Math.floor((height - metadata.height) / 2)
      },
      { input: paperTexture(width, height) }
    ])
    .png({ compressionLevel: 9 })
    .toFile(fileURLToPath(new URL(`apple-splash-${width}-${height}.png`, output)))
}

await sharp(Buffer.from(monochrome))
  .resize(512, 512, { fit: 'contain' })
  .png({ compressionLevel: 9 })
  .toFile(fileURLToPath(new URL('monochrome-512x512.png', output)))

await Promise.all([
  writeFile(new URL('favicon.svg', output), source),
  copyFile(sourceLogo, new URL('nelson-logo.svg', output))
])
