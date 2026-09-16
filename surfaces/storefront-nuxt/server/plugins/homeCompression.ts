import {
  getRequestHeader,
  getRequestURL,
  getResponseHeader,
  removeResponseHeader,
  setResponseHeader
} from 'h3'

function qualityForEncoding (header: string | undefined, encoding: string): number {
  if (!header) return 0

  let wildcardQuality = 0
  for (const entry of header.split(',')) {
    const [rawName, ...parameters] = entry.trim().split(';')
    const name = rawName?.trim().toLowerCase()
    if (!name) continue

    let quality = 1
    for (const parameter of parameters) {
      const [rawKey, rawValue] = parameter.trim().split('=', 2)
      if (rawKey?.toLowerCase() !== 'q') continue
      const parsed = Number(rawValue)
      quality = Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : 0
    }

    if (name === encoding) return quality
    if (name === '*') wildcardQuality = quality
  }

  return wildcardQuality
}

function mergeVary (current: string | string[] | number | undefined, value: string): string {
  const values = (Array.isArray(current) ? current : [current])
    .flatMap(item => String(item || '').split(','))
    .map(item => item.trim())
    .filter(Boolean)

  if (values.includes('*')) return '*'
  if (!values.some(item => item.toLowerCase() === value.toLowerCase())) values.push(value)
  return values.join(', ')
}

function responseHeader (headers: Record<string, string> | undefined, name: string): string | undefined {
  if (!headers) return undefined
  const entry = Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase())
  return entry?.[1]
}

export default defineNitroPlugin((nitro) => {
  nitro.hooks.hook('render:response', async (response, { event }) => {
    if (!['GET', 'HEAD'].includes(event.method)) return
    if (getRequestURL(event).pathname !== '/') return
    if ((response.statusCode || 200) !== 200) return
    if (!responseHeader(response.headers, 'content-type')?.startsWith('text/html')) return

    const vary = mergeVary(responseHeader(response.headers, 'vary') || getResponseHeader(event, 'vary'), 'Accept-Encoding')
    response.headers = { ...response.headers, vary }
    setResponseHeader(event, 'Vary', vary)

    if (qualityForEncoding(getRequestHeader(event, 'accept-encoding'), 'gzip') <= 0) return
    if (responseHeader(response.headers, 'content-encoding') || getResponseHeader(event, 'content-encoding')) return

    const originalBody = response.body
    try {
      const source = new Response(originalBody).body
      if (!source) return

      response.body = source.pipeThrough(new CompressionStream('gzip'))
      setResponseHeader(event, 'Content-Encoding', 'gzip')
    } catch (error) {
      // Compression is an optimization. Preserve the canonical SSR response if
      // encoder setup fails instead of turning the home into a 500.
      response.body = originalBody
      removeResponseHeader(event, 'Content-Encoding')
      nitro.captureError(error as Error, { event, tags: ['storefront-home-compression'] })
    }
  })
})
