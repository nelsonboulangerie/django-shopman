import { randomUUID } from 'node:crypto'
import { getRequestHeader, getRequestURL, getResponseHeader, setResponseHeader, type H3Event } from 'h3'
import { defineNitroPlugin, useRuntimeConfig } from 'nitropack/runtime'
import { createFetch, type $Fetch } from 'ofetch'
import type { StorefrontSsrRead } from '../../shared/types/ssrRead'
import { publicTwinPath } from '../utils/djangoProxy'
import { publicSsrReadOptions, ssrProjectionPath, ssrReadSnapshot, traceSsrFetch } from '../utils/ssrRead'

function emitObservation (event: H3Event, status: number, force = false) {
  const state = event.context.storefrontSsrRead as StorefrontSsrRead | undefined
  if (!state || state.reported || state.ownerRequest !== event.node.req) return
  const snapshot = ssrReadSnapshot(state)
  if (!event.node.res.headersSent) {
    const timing = [`ssr;dur=${snapshot.duration_ms.toFixed(2)}`]
    for (const kind of ['site', 'shell', 'primary', 'fallback'] as const) {
      const duration = snapshot.reads.filter(r => r.kind === kind).reduce((sum, r) => sum + r.duration_ms, 0)
      if (duration) timing.push(`ssr_${kind};dur=${duration.toFixed(2)}`)
    }
    const existing = getResponseHeader(event, 'server-timing')
    setResponseHeader(event, 'server-timing', [existing, ...timing].filter(Boolean).join(', '))
    setResponseHeader(event, 'x-storefront-request-id', state.id)
  }
  const failedRead = snapshot.reads.some(read => read.error_code || read.network_codes?.length || read.statuses.some(code => code >= 400))
  if (force || status >= 500 || snapshot.duration_ms >= 2000 || failedRead) {
    state.reported = true
    console.info(JSON.stringify({ ...snapshot, status }))
  }
}

export default defineNitroPlugin((nitro) => {
  nitro.hooks.hook('request', (event) => {
    if (!['GET', 'HEAD'].includes(event.method)) return
    const config = useRuntimeConfig(event)
    const baseURL = config.app.baseURL || '/'
    const projection = ssrProjectionPath(getRequestURL(event).pathname, baseURL, config.public.continuumCatalogEnabled)
    if (!projection) return
    const state: StorefrontSsrRead = {
      id: randomUUID(), route: projection.route, primaryPath: projection.path,
      startedAt: performance.now(), reads: [], ownerRequest: event.node.req,
      fallbackPath: 'fallbackPath' in projection ? projection.fallbackPath : undefined
    }
    event.context.storefrontSsrRead = state
    // O wrapper mantém argumentos, corpo e erro. A fronteira remove apenas a
    // inferência recursiva de rotas do Nitro durante a decoração do transporte.
    const original = event.$fetch
    // O fetch do evento é uma função simples no Nitro, sem método raw. O
    // transporte nativo vinculado ao evento fornece a resposta HTTP completa.
    const transport = Object.assign(original, { raw: createFetch({ fetch: (request, options) => event.fetch(request instanceof URL ? request.href : request, options) }).raw })
    const observed = traceSsrFetch(transport as unknown as $Fetch, state)
    event.$fetch = observed as unknown as typeof original
    const base = baseURL.replace(/\/+$/, '')
    const canonicalPath = base ? projection.path.slice(base.length) : projection.path
    // Uma sessão conserva a ordem antiga dos snapshots de sacola. Só a leitura
    // anônima, já admitida pela política pública do BFF, pode correr antes.
    if ('format' in projection && projection.format === 'snapshot') {
      // O quadro estrutural já é público para toda sessão. Cookie/Authorization
      // continuam barrados pelo proxy Continuum; preço e sacola não são antecipados.
      state.primaryRaw = observed.raw(projection.path, {
        ...publicSsrReadOptions(), credentials: 'omit', ignoreResponseError: true,
        headers: { accept: 'application/cloudevents+json; continuum=0.2; schema=1' }
      })
      void state.primaryRaw.catch(() => undefined) // silêncio-deliberado: página e trace conservam a rejeição original
    } else if (publicTwinPath('GET', canonicalPath, getRequestHeader(event, 'cookie'), false)
      && !getRequestHeader(event, 'authorization')) {
      state.primary = observed(projection.path, publicSsrReadOptions())
      // A página consome a promessa. Se o render abortar antes, não deixar uma
      // rejeição sem observador; o erro original continua chegando à página.
      void state.primary.catch(() => undefined) // silêncio-deliberado: só observa a rejeição; página e trace conservam o erro original
    }
    event.node.res.once('close', () => {
      if (event.node.res.writableFinished || state.reported) return
      state.reported = true
      console.warn(JSON.stringify({ ...ssrReadSnapshot(state), aborted: true }))
    })
  })

  nitro.hooks.hook('beforeResponse', (event) => {
    emitObservation(event, event.node.res.statusCode)
  })
  // O renderer de erro pode encerrar a resposta sem beforeResponse do H3.
  // Registrar aqui conserva a causa upstream do 503, antes de virar tela de erro.
  nitro.hooks.hook('error', (error, { event }) => {
    if (!event) return
    const status = (error as { statusCode?: number }).statusCode || 500
    emitObservation(event, status, true)
  })
})
