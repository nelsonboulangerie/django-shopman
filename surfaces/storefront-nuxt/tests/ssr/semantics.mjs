import { Window } from 'happy-dom'

/** Apenas parseia o SSR para comparação; nunca executa scripts ou busca assets. */
export function htmlSemantics (body) {
  const window = new Window({ settings: {
    disableJavaScriptEvaluation: true,
    disableJavaScriptFileLoading: true,
    disableCSSFileLoading: true
  } })
  try {
    const document = new window.DOMParser().parseFromString(body, 'text/html')
    const schemas = [...document.querySelectorAll('script[type="application/ld+json"]')]
      .map(script => JSON.parse(script.textContent))
    for (const node of document.querySelectorAll('script, style')) node.remove()
    return { text: document.documentElement.textContent.replace(/\s+/g, ' ').trim(), schemas }
  } finally { window.happyDOM.abort() }
}

/** Lê a âncora de validade no payload SSR sem executar o HTML. */
export function continuumSsrValidatedAtMs (body) {
  const window = new Window({ settings: {
    disableJavaScriptEvaluation: true,
    disableJavaScriptFileLoading: true,
    disableCSSFileLoading: true
  } })
  try {
    const document = new window.DOMParser().parseFromString(body, 'text/html')
    const values = JSON.parse(document.querySelector('script#__NUXT_DATA__')?.textContent || '[]')
    const cache = values.find(value => value && typeof value === 'object' && 'validated_at_ms' in value && 'message' in value && 'etag' in value)
    return cache ? values[cache.validated_at_ms] : null
  } finally { window.happyDOM.abort() }
}
