import {
  createError,
  getQuery,
  getRequestHeader,
  setResponseHeader,
  setResponseStatus,
  type H3Event
} from 'h3'
import { resolveDjangoBaseUrl } from './djangoBaseUrl'

const FORWARDED_HEADERS = [
  'cache-control',
  'content-type',
  'etag',
  'server-timing',
  'vary',
  'continuum-stream',
  'continuum-epoch',
  'continuum-sequence',
  'continuum-state-token',
  'continuum-state-digest',
  'continuum-fresh-for-ms',
  'continuum-stale-if-error-ms',
  'continuum-age-ms'
] as const

export async function proxyPublicContinuumCatalog (event: H3Event) {
  const config = useRuntimeConfig(event)
  const enabled = config.public.continuumCatalogEnabled === true
    || String(config.public.continuumCatalogEnabled || '').toLowerCase() === 'true'
  if (!enabled) {
    throw createError({ statusCode: 404, statusMessage: 'Not Found' })
  }
  if (!['GET', 'HEAD'].includes(event.method || 'GET')) {
    throw createError({ statusCode: 405, statusMessage: 'Method Not Allowed' })
  }
  if (Object.keys(getQuery(event)).length) {
    throw createError({ statusCode: 400, statusMessage: 'Bad Request' })
  }

  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl)
  const headers: Record<string, string> = {
    accept: getRequestHeader(event, 'accept') || 'application/cloudevents+json; continuum=0.2; schema=1'
  }
  const ifNoneMatch = getRequestHeader(event, 'if-none-match')
  if (ifNoneMatch) headers['if-none-match'] = ifNoneMatch

  const response = await $fetch.raw<ArrayBuffer>(
    `${djangoBaseUrl}/api/v1/storefront/continuum/v0.2/catalog-structure/`,
    {
      method: event.method === 'HEAD' ? 'HEAD' : 'GET',
      headers,
      responseType: 'arrayBuffer',
      ignoreResponseError: true
    }
  )
  setResponseStatus(event, response.status)
  for (const name of FORWARDED_HEADERS) {
    const value = response.headers.get(name)
    if (value) setResponseHeader(event, name, value)
  }
  // Nunca repassa Cookie/Authorization ao Django nem Set-Cookie ao navegador.
  if (response.status === 304 || event.method === 'HEAD') return null
  if (!response._data) throw createError({ statusCode: 502, statusMessage: 'Bad Gateway' })
  return new Uint8Array(response._data)
}
