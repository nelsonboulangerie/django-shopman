import {
  copyFile,
  readFile,
  readdir,
  rename,
  writeFile
} from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const root = new URL('../', import.meta.url)
const sourceMark = new URL('brand/nelson-mark.svg', root)
const sourceLogo = new URL('brand/nelson-logo.svg', root)
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

await sharp(Buffer.from(monochrome))
  .resize(512, 512, { fit: 'contain' })
  .png({ compressionLevel: 9 })
  .toFile(fileURLToPath(new URL('monochrome-512x512.png', output)))

await Promise.all([
  writeFile(new URL('favicon.svg', output), source),
  copyFile(sourceLogo, new URL('nelson-logo.svg', output))
])

const splashNames = (await readdir(output)).filter(name => /^apple-splash-.*\.png$/.test(name))
await Promise.all(splashNames.map(async (name) => {
  const input = new URL(name, output)
  const temporary = new URL(`.paper-${name}`, output)
  const { width, height } = await sharp(fileURLToPath(input)).metadata()

  await sharp(fileURLToPath(input))
    .composite([{ input: paperTexture(width, height) }])
    .png({ compressionLevel: 9 })
    .toFile(fileURLToPath(temporary))
  await rename(temporary, input)
}))
