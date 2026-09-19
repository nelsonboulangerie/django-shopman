import { robotsTxt } from '../utils/indexingPolicy'

// robots.txt domain-aware: o host vem do request (funciona em dev e em qualquer
// domínio de produção sem hardcode). Rotas privadas NÃO entram aqui — elas se
// declaram `noindex` no cabeçalho; ver `indexingPolicy`.
export default defineEventHandler((event) => {
  setHeader(event, 'content-type', 'text/plain; charset=utf-8')
  return robotsTxt(getRequestURL(event).origin)
})
