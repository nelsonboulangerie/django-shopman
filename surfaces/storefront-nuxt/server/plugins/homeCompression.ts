import {
  getRequestHeader,
  getRequestURL,
  getResponseHeader,
  removeResponseHeader,
  setResponseHeader,
  setResponseStatus
} from 'h3'
import {
  headerValue,
  mergeVary,
  prepareHomeRepresentation,
  removeHeaderValue,
  setHeaderValue,
  type RenderHeaders
} from '../utils/homeCompression'

function setRenderedHeader (
  response: { headers?: RenderHeaders },
  event: Parameters<typeof setResponseHeader>[0],
  name: string,
  value: string
): void {
  response.headers ||= {}
  setHeaderValue(response.headers, name, value)
  setResponseHeader(event, name, value)
}

function removeRenderedHeader (
  response: { headers?: RenderHeaders },
  event: Parameters<typeof removeResponseHeader>[0],
  name: string
): void {
  removeHeaderValue(response.headers, name)
  removeResponseHeader(event, name)
}

function renderNotAcceptable (
  response: { body?: unknown, headers?: RenderHeaders, statusCode?: number, statusMessage?: string },
  event: Parameters<typeof setResponseStatus>[0]
): void {
  const body = 'Not Acceptable'
  response.statusCode = 406
  response.statusMessage = body
  response.body = body
  setResponseStatus(event, 406, body)
  removeRenderedHeader(response, event, 'Content-Encoding')
  removeRenderedHeader(response, event, 'ETag')
  setRenderedHeader(response, event, 'Content-Type', 'text/plain; charset=utf-8')
  setRenderedHeader(response, event, 'Content-Length', String(Buffer.byteLength(body)))
}

export default defineNitroPlugin((nitro) => {
  nitro.hooks.hook('render:response', async (response, { event }) => {
    if (!['GET', 'HEAD'].includes(event.method)) return
    if (getRequestURL(event).pathname !== '/') return
    if ((response.statusCode || 200) !== 200) return
    if (!String(headerValue(response.headers, 'content-type') || '').startsWith('text/html')) return

    const vary = mergeVary([
      headerValue(response.headers, 'vary'),
      getResponseHeader(event, 'vary')
    ], 'Accept-Encoding')
    setRenderedHeader(response, event, 'Vary', vary)
    if (headerValue(response.headers, 'content-encoding') || getResponseHeader(event, 'content-encoding')) return

    const representation = await prepareHomeRepresentation(
      response.body,
      getRequestHeader(event, 'accept-encoding')
    )
    if (representation.error) {
      nitro.captureError(representation.error, { event, tags: ['storefront-home-compression'] })
    }
    if (representation.kind === 'identity') return
    if (representation.kind === 'not-acceptable') {
      renderNotAcceptable(response, event)
      return
    }

    response.body = representation.body
    removeRenderedHeader(response, event, 'ETag')
    setRenderedHeader(response, event, 'Content-Encoding', 'gzip')
    setRenderedHeader(response, event, 'Content-Length', String(representation.body.byteLength))
  })
})
