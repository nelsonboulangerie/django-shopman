import { defineEventHandler, setResponseHeaders } from 'h3'

// Qual build a loja está servindo (WP-RELEASE-01 R1, docs/reference/release-contract.md).
// Mesmo contrato do `/health/release` dos apps de operador (operator-kit, que a
// loja não estende): os valores vêm da imagem (ENV da última camada do
// Dockerfile.surface, passados pelo deploy-images.yml), nunca de uma API em hora
// de pedido, e não são segredo. Valor fora do contrato vira vazio: a sonda do
// Watchman reprova "sem identidade", e não teria como reprovar um número inventado.
const SHA = /^[0-9a-f]{40}$/
const RELEASE_ID = /^\d{8}-\d{4}-[0-9a-f]{7}$/
const COMPONENT = /^[a-z0-9][a-z0-9-]{0,62}$/

function clean(value: string | undefined, pattern: RegExp): string {
  const text = (value ?? '').trim().toLowerCase()
  return pattern.test(text) ? text : ''
}

export default defineEventHandler((event) => {
  setResponseHeaders(event, {
    'cache-control': 'no-store',
    'content-type': 'application/json; charset=utf-8',
    'x-content-type-options': 'nosniff',
    'x-robots-tag': 'noindex'
  })
  return {
    schema_version: 1,
    component: clean(process.env.SHOPMAN_RELEASE_COMPONENT, COMPONENT) || 'storefront-nuxt',
    app: 'storefront',
    release_id: clean(process.env.SHOPMAN_RELEASE_ID, RELEASE_ID),
    build_sha: clean(process.env.SHOPMAN_BUILD_SHA, SHA)
  }
})
