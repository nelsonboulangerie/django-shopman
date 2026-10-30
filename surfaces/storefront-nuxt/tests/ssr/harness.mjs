import { createServer } from 'node:http'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const product = {
  sku: 'FENDU', slug: 'fendu', name: 'Produto teste SSR', short_description: 'Descrição de teste', long_description: '',
  image_url: null, gallery: [], quote: { qty: '1', listing_ref: null, list_unit_price_q: 1500, list_line_total_q: 1500, final_unit_price_q: 1500, final_line_total_q: 1500, adjustments: [] },
  availability: 'available', availability_label: 'Disponível', can_add_to_cart: true, available_qty: 10, max_qty: 10, qty_in_cart: 0,
  is_paused: false, is_notifiable: false, is_notify_subscribed: false, is_favorite: false, dietary_warnings: [], is_bundle: false,
  components: [], unit_weight_label: null, approx_dimensions_label: null, is_made_to_order: false, made_to_order_label: '',
  allergen: null, conservation: null, ingredients_text: null, trace_notice: '', nutrition: null, seo_description: '', seo_keywords: [],
  brand: '', gtin: '', mpn: '', item_condition: 'new', breadcrumb_category: null, category_color: null, category_icon: null, option_groups: []
}

export async function startBackend ({ liveSnapshots = false } = {}) {
  const snapshots = new Map()
  let config = {}; let reads = []; let firstFailure
  const server = createServer(async (req, res) => {
    const path = req.url.split('?')[0]
    if (!['GET', 'HEAD'].includes(req.method) || !path.startsWith('/api/v1/storefront/')) { res.writeHead(405); res.end(); return }
    const kind = path.includes('/products/FENDU/') || path.endsWith('/catalog/') ? 'primary' : path.endsWith('/shell/') ? 'shell' : 'site'
    const read = { path, kind, startedAt: performance.now(), cookiePresent: !!req.headers.cookie, forwardedIpPresent: !!req.headers['x-forwarded-for'] }
    reads.push(read)
    res.once('finish', () => { read.finishedAt = performance.now(); read.status = res.statusCode })
    if (config.delays?.[kind]) await sleep(config.delays[kind])
    let failing = false
    if (kind === 'primary' && config.mode && config.mode !== 'normal') {
      firstFailure ??= performance.now()
      failing = config.mode.startsWith('persistent') || performance.now() - firstFailure < 150
    }
    if (failing && config.mode.includes('reset')) { read.reset = true; req.socket.destroy(); return }
    if (failing) {
      const status = config.mode === 'persistent-429' ? 429 : 503
      res.writeHead(status, { 'content-type': 'application/json', 'x-api-version': '1', ...(config.retryAfter ? { 'retry-after': config.retryAfter } : {}) })
      res.end('{"detail":"controlled unavailable"}'); return
    }
    try {
      if (!snapshots.has(path)) snapshots.set(path, (async () => {
        if (liveSnapshots) {
          // Somente GET anônimo de URLs fixas do catálogo. Nenhum cookie ou
          // credencial sai do harness; o corpo fica apenas nesta memória.
          const response = await fetch('https://api.boulangerie.com.br' + path, { headers: { accept: 'application/json' } })
          if (response.status !== 200) throw new Error(`Snapshot unavailable: ${response.status}`)
          return Buffer.from(await response.arrayBuffer())
        }
        const body = kind === 'primary'
          ? path.includes('/products/') ? { product, ...(!path.includes('/public/') ? { cart: null } : {}) } : { catalog: { items: [], sections: [], favorite_category_ref: '' } }
          : {}
        return Buffer.from(JSON.stringify(body))
      })())
      const body = await snapshots.get(path)
      read.bodySha256 = createHash('sha256').update(body).digest('hex')
      res.writeHead(200, { 'content-type': 'application/json', 'x-api-version': '1', 'cache-control': 'private, no-store' })
      res.end(req.method === 'HEAD' ? undefined : body)
    } catch { res.writeHead(502); res.end() }
  })
  server.listen(0, '127.0.0.1'); await once(server, 'listening')
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    control: (next = {}) => { config = next; reads = []; firstFailure = undefined },
    reads: () => reads.map(read => ({ ...read })),
    close: () => new Promise(resolveClose => { server.closeAllConnections(); server.close(resolveClose) })
  }
}

export async function startNuxt (backendUrl, buildDirectory = '.output') {
  const reservation = createServer(); reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening')
  const port = reservation.address().port; await new Promise(done => reservation.close(done))
  const child = spawn(process.execPath, [resolve(buildDirectory, 'server/index.mjs')], {
    env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), NUXT_DJANGO_BASE_URL: backendUrl, NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED: 'false' },
    stdio: ['ignore', 'pipe', 'pipe']
  })
  let logs = ''
  child.stdout.on('data', chunk => { logs += chunk.toString() }); child.stderr.on('data', chunk => { logs += chunk.toString() })
  const url = `http://127.0.0.1:${port}`
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error(`Nuxt exited: ${logs}`)
    try { if ((await fetch(url + '/health/live')).status === 200) break } catch { /* O processo ainda pode estar iniciando. */ }
    await sleep(50)
    if (i === 99) { child.kill('SIGTERM'); throw new Error(`Nuxt did not become ready: ${logs}`) }
  }
  return {
    url,
    logs: () => logs,
    close: async () => { if (child.exitCode === null) { child.kill('SIGTERM'); await once(child, 'exit') } }
  }
}
