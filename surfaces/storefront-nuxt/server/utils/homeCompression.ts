import { promisify } from 'node:util'
import { gzip as gzipCallback } from 'node:zlib'

const gzip = promisify(gzipCallback)

type Compressor = (body: Uint8Array) => Promise<Uint8Array>

interface EncodingPreference {
  gzip: number
  identity: number
}

type HeaderValue = string | string[] | number | undefined
export type RenderHeaders = Record<string, HeaderValue>

export type PreparedHomeRepresentation =
  | { kind: 'gzip', body: Buffer, error?: never }
  | { kind: 'identity', body: unknown, error?: Error }
  | { kind: 'not-acceptable', error?: Error }

export function headerValue (headers: RenderHeaders | undefined, name: string): HeaderValue {
  if (!headers) return undefined
  return Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1]
}

export function setHeaderValue (headers: RenderHeaders, name: string, value: string): void {
  removeHeaderValue(headers, name)
  headers[name] = value
}

export function removeHeaderValue (headers: RenderHeaders | undefined, name: string): void {
  for (const key of Object.keys(headers || {})) {
    if (key.toLowerCase() === name.toLowerCase()) delete headers?.[key]
  }
}

export function mergeVary (sources: HeaderValue[], value: string): string {
  const values = sources
    .flatMap(source => Array.isArray(source) ? source : [source])
    .flatMap(item => String(item || '').split(','))
    .map(item => item.trim())
    .filter(Boolean)

  if (values.includes('*')) return '*'
  if (!values.some(item => item.toLowerCase() === value.toLowerCase())) values.push(value)
  return values.filter((item, index) => (
    values.findIndex(candidate => candidate.toLowerCase() === item.toLowerCase()) === index
  )).join(', ')
}

function parseAcceptEncoding (header: string | undefined): Map<string, number> {
  const preferences = new Map<string, number>()
  if (!header) return preferences

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
    preferences.set(name, quality)
  }

  return preferences
}

export function encodingPreference (header: string | undefined): EncodingPreference {
  const preferences = parseAcceptEncoding(header)
  const wildcard = preferences.get('*')
  const gzipQuality = preferences.get('gzip') ?? wildcard ?? 0
  const identityQuality = preferences.get('identity')
    ?? (wildcard === 0 ? 0 : 1)

  return { gzip: gzipQuality, identity: identityQuality }
}

function asError (error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error))
}

export async function prepareHomeRepresentation (
  body: unknown,
  acceptEncoding: string | undefined,
  compressor: Compressor = gzip
): Promise<PreparedHomeRepresentation> {
  const preference = encodingPreference(acceptEncoding)
  if (preference.gzip <= 0 && preference.identity <= 0) return { kind: 'not-acceptable' }
  if (preference.gzip <= 0 || preference.identity > preference.gzip) return { kind: 'identity', body }

  try {
    const bytes = Buffer.from(await new Response(body as BodyInit | null | undefined).arrayBuffer())
    const compressed = Buffer.from(await compressor(bytes))
    return { kind: 'gzip', body: compressed }
  } catch (error) {
    const normalizedError = asError(error)
    if (preference.identity > 0) return { kind: 'identity', body, error: normalizedError }
    return { kind: 'not-acceptable', error: normalizedError }
  }
}
