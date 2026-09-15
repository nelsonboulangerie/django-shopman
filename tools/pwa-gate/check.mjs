import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { readFile, stat } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

function check (condition, message) {
  if (!condition) throw new Error(message)
  process.stdout.write(`✓ ${message}\n`)
}

async function freePort () {
  const server = createServer()
  await new Promise((resolve, reject) => server.once('error', reject).listen(0, '127.0.0.1', resolve))
  const address = server.address()
  check(typeof address === 'object' && address !== null, 'porta local resolvida')
  const port = address.port
  await new Promise(resolve => server.close(resolve))
  return port
}

async function waitForServer (url, child) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`preview Nitro encerrou com código ${child.exitCode}`)
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // O socket ainda não abriu; a próxima tentativa mantém o teto explícito.
    }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('preview Nitro não respondeu em 30 segundos')
}

async function pngSize (path) {
  const bytes = await readFile(path)
  check(bytes.subarray(1, 4).toString() === 'PNG', `${path} é PNG`)
  return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)]
}

const requestedApp = process.argv.find(value => value.startsWith('--app='))?.split('=', 2)[1]
check(requestedApp === 'storefront', 'app=storefront é a surface suportada')
check(process.versions.node.startsWith('22.'), `Node 22 em uso (${process.version})`)

const repository = dirname(dirname(dirname(fileURLToPath(import.meta.url))))
const surface = join(repository, 'surfaces/storefront-nuxt')
const output = join(surface, '.output')
const packageJson = JSON.parse(await readFile(join(surface, 'package.json'), 'utf8'))
check(packageJson.dependencies['@vite-pwa/nuxt'] === '1.1.1', '@vite-pwa/nuxt usa versão fixa 1.1.1')

const swPath = join(output, 'public/sw.js')
await stat(swPath)
const sw = await readFile(swPath, 'utf8')
const precache = [...sw.matchAll(/url:"([^"]+)"/g)].map(match => match[1])
const forbidden = precache.filter(url => /^(?:\/)?(?:api|events|admin)(?:\/|$)/.test(url))
const html = precache.filter(url => url.endsWith('.html'))
check(precache.includes('offline.html'), 'offline.html está no precache')
check(forbidden.length === 0, 'precache não contém /api/, /events/ nem /admin/')
check(html.length === 1 && html[0] === 'offline.html', 'nenhuma navegação/HTML entra no precache além do casco offline')
check(sw.includes('=>"navigate"===') && sw.includes('NetworkOnly') && sw.includes('PrecacheFallbackPlugin'), 'navegação usa NetworkOnly com fallback offline')
check((sw.match(/\.CacheFirst\(/g) || []).length === 2, 'existem exatamente dois caches CacheFirst')
check(sw.includes('startsWith("/img/products/")') && sw.includes('startsWith("/fonts/")'), 'cache de runtime cobre somente produtos e fontes')
check(!sw.includes('startsWith("/api/') && !sw.includes('startsWith("/events/') && !sw.includes('startsWith("/admin/'), 'service worker não registra rotas proibidas')
check(/"SKIP_WAITING"===\w+\.data\.type&&self\.skipWaiting\(\)/.test(sw), 'skipWaiting depende de mensagem explícita')

const requiredAssets = [
  ['pwa-64x64.png', 64, 64],
  ['pwa-192x192.png', 192, 192],
  ['pwa-512x512.png', 512, 512],
  ['maskable-512x512.png', 512, 512],
  ['apple-touch-icon-180x180.png', 180, 180],
  ['monochrome-512x512.png', 512, 512],
  ['screenshots/home-narrow.png', 1080, 1920],
  ['screenshots/menu-narrow.png', 1080, 1920],
  ['screenshots/home-wide.png', 1280, 720]
]
for (const [name, width, height] of requiredAssets) {
  const actual = await pngSize(join(surface, 'public/pwa', name))
  check(actual[0] === width && actual[1] === height, `${name} mede ${width}x${height}`)
}
await Promise.all(['favicon.ico', 'favicon.svg', 'nelson-logo.svg'].map(name => stat(join(surface, 'public/pwa', name))))
const splashFiles = precache.filter(url => url.startsWith('pwa/apple-splash-') && url.endsWith('.png'))
check(splashFiles.length === 40, '40 splash screens iOS estão no precache')

const port = await freePort()
const baseUrl = `http://127.0.0.1:${port}`
let logs = ''
const preview = spawn(process.execPath, [join(output, 'server/index.mjs')], {
  cwd: surface,
  env: {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(port),
    NUXT_DJANGO_BASE_URL: 'http://127.0.0.1:1'
  },
  stdio: ['ignore', 'pipe', 'pipe']
})
preview.stdout.on('data', chunk => { logs += chunk })
preview.stderr.on('data', chunk => { logs += chunk })

try {
  await waitForServer(`${baseUrl}/offline.html`, preview)
  const manifestResponse = await fetch(`${baseUrl}/manifest.webmanifest`)
  check(manifestResponse.ok, 'manifesto responde 200 mesmo sem Django')
  check(manifestResponse.headers.get('content-type')?.startsWith('application/manifest+json'), 'manifesto usa application/manifest+json')
  check(manifestResponse.headers.get('cache-control') === 'public, max-age=3600', 'manifesto usa cache público de uma hora')
  const manifest = await manifestResponse.json()
  for (const field of ['id', 'name', 'short_name', 'description', 'lang', 'dir', 'start_url', 'scope', 'display', 'display_override', 'orientation', 'theme_color', 'background_color', 'icons', 'shortcuts', 'categories', 'screenshots']) {
    check(field in manifest, `manifesto contém ${field}`)
  }
  check(manifest.icons.some(icon => icon.purpose === 'maskable'), 'manifesto declara ícone maskable')
  check(manifest.icons.some(icon => icon.purpose === 'monochrome'), 'manifesto declara ícone monochrome')
  check(manifest.screenshots.filter(item => item.form_factor === 'narrow').length === 2, 'manifesto declara duas screenshots narrow')
  check(manifest.screenshots.filter(item => item.form_factor === 'wide').length === 1, 'manifesto declara uma screenshot wide')

  const swResponse = await fetch(`${baseUrl}/sw.js`, { method: 'HEAD' })
  check(swResponse.ok, 'service worker responde 200')
  check(swResponse.headers.get('cache-control') === 'no-cache, no-store, must-revalidate', 'service worker nunca fica imutável')

  const documentResponse = await fetch(`${baseUrl}/`, { headers: { 'x-forwarded-proto': 'https' } })
  const document = await documentResponse.text()
  const csp = documentResponse.headers.get('content-security-policy') || ''
  check(csp.includes("worker-src 'self' blob:") && csp.includes("manifest-src 'self'"), 'CSP existente libera worker e manifesto locais')
  check(document.includes('rel="manifest"') && document.includes('name="theme-color"'), 'HTML contém manifesto e theme-color')
  check(document.includes('apple-mobile-web-app-capable') && document.includes('apple-mobile-web-app-status-bar-style'), 'HTML contém metas iOS')
  check((document.match(/rel="apple-touch-startup-image"/g) || []).length === 40, 'HTML contém 40 links apple-touch-startup-image')
} catch (error) {
  process.stderr.write(logs)
  throw error
} finally {
  preview.kill('SIGTERM')
}

process.stdout.write('✓ Gate PWA estrutural concluído\n')
