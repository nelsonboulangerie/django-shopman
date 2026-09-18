import { defineEventHandler, setResponseHeaders } from 'h3'

// Liveness do BFF da loja: prova só que o processo Nitro atende. É o health check
// da plataforma, que roda a cada poucos segundos — antes ele batia em `/`, e cada
// chamada renderizava a home SSR e pedia a projeção da home ao Django sem trazer
// informação nova. Aqui não há Django, sessão, banco nem renderização.
//
// A prontidão do Django se pergunta ao próprio `api.` (`/health/ready/`), no smoke;
// o health check não deve tirar a loja do ar por uma queda que reiniciar o Nitro
// não cura. Sem limitador: a resposta é constante e custa menos que contá-la.
export default defineEventHandler((event) => {
  setResponseHeaders(event, {
    'cache-control': 'no-store',
    'content-type': 'application/json; charset=utf-8',
    'x-content-type-options': 'nosniff',
    'x-robots-tag': 'noindex'
  })
  return { status: 'ok', checks: { bff: 'ok' } }
})
