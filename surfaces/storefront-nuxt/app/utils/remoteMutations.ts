export function newRemoteMutationKey (prefix: string): string {
  const randomId = import.meta.client && window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${randomId}`
}

const HTTP_METHODS = ['GET', 'HEAD', 'PATCH', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE'] as const
export type HttpRequestMethod = typeof HTTP_METHODS[number]

/**
 * Normaliza o `method` (string livre vinda das Actions do backend) para o verbo HTTP
 * que o `$fetch` aceita. Default `POST` (a maioria das mutations) e fallback seguro
 * quando o backend mandar algo fora do conjunto conhecido.
 */
export function remoteMethod (method: string | null | undefined): HttpRequestMethod {
  const normalized = (method || 'POST').toUpperCase()
  return (HTTP_METHODS as readonly string[]).includes(normalized)
    ? normalized as HttpRequestMethod
    : 'POST'
}


// Correlation only, never a credential or an instruction to resubmit on reconnect.
export function retainedRemoteMutationKey (resource: string, prefix: string): string {
  let key = ''
  if (import.meta.client) {
    try { key = sessionStorage.getItem(`shopman-intention:${resource}`) || '' } catch { /* storage denied */ }
  }
  if (!key || key.length > 128) key = newRemoteMutationKey(prefix)
  if (import.meta.client) {
    try { sessionStorage.setItem(`shopman-intention:${resource}`, key) } catch { /* caller retains it in memory */ }
  }
  return key
}

export function forgetRemoteMutationKey (resource: string) {
  if (import.meta.client) {
    try { sessionStorage.removeItem(`shopman-intention:${resource}`) } catch { /* storage denied */ }
  }
}
