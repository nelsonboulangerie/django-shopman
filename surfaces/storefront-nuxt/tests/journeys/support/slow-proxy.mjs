// Proxy lento da pilha de jornadas (J9, #2573). Fica ENTRE a loja compilada (o BFF) e o
// Django, só na pilha de teste: a loja aponta `NUXT_DJANGO_BASE_URL` para ele, e ele
// repassa tudo ao Django como veio. A jornada pede, pela porta de controle, que a próxima
// resposta de uma rota demore mais que o prazo do BFF; o Django faz o trabalho, a resposta
// chega tarde e o BFF desiste. Nada disso existe no código da loja nem no do Django.
//
//   SLOW_PROXY_PORT=8076 SLOW_PROXY_TARGET=http://127.0.0.1:8090 node slow-proxy.mjs
//
// Controle (só na própria porta):
//   POST /__slow-proxy/delay  {"method":"PUT","path":"^/api/v1/cart/skus/","ms":30000,"times":1}
//   POST /__slow-proxy/reset
import http from 'node:http'

const port = Number(process.env.SLOW_PROXY_PORT || 8076)
const target = new URL(process.env.SLOW_PROXY_TARGET || 'http://127.0.0.1:8090')

/** @type {Array<{ method: string, pattern: RegExp, ms: number, left: number }>} */
let rules = []

function takeDelay (method, path) {
  const rule = rules.find(r => r.left > 0 && r.method === method && r.pattern.test(path))
  if (!rule) return 0
  rule.left -= 1
  return rule.ms
}

function control (req, res) {
  let body = ''
  req.on('data', (chunk) => { body += chunk })
  req.on('end', () => {
    if (req.url === '/__slow-proxy/reset') {
      rules = []
    } else if (req.url === '/__slow-proxy/delay') {
      const { method = 'GET', path = '.*', ms = 0, times = 1 } = JSON.parse(body || '{}')
      rules.push({ method: String(method).toUpperCase(), pattern: new RegExp(path), ms: Number(ms), left: Number(times) })
    } else {
      res.writeHead(404).end()
      return
    }
    res.writeHead(204).end()
  })
}

const server = http.createServer((req, res) => {
  if (req.url?.startsWith('/__slow-proxy/')) return control(req, res)
  const delay = takeDelay(req.method || 'GET', (req.url || '/').split('?')[0])
  const upstream = http.request({
    hostname: target.hostname,
    port: target.port,
    method: req.method,
    path: req.url,
    headers: req.headers
  }, (answer) => {
    // O Django já respondeu (e já gravou): a resposta é que chega tarde ao BFF.
    setTimeout(() => {
      res.writeHead(answer.statusCode || 502, answer.headers)
      answer.pipe(res)
    }, delay)
  })
  upstream.on('error', () => { if (!res.headersSent) res.writeHead(502).end() })
  req.pipe(upstream)
})

server.listen(port, '127.0.0.1', () => {
  console.log(`slow-proxy :${port} -> ${target.origin}`)
})
