import assert from 'node:assert/strict'
import { test } from 'node:test'
import { startBackend, startNuxt } from './harness.mjs'
import { continuumSsrValidatedAtMs } from './semantics.mjs'

test('SSR real com Continuum habilitado', async (t) => {
  const backend = await startBackend()
  let nuxt
  t.after(async () => { await nuxt?.close(); await backend.close() })
  nuxt = await startNuxt(backend.url, '.output', { continuumEnabled: true })
  await (await fetch(nuxt.url + '/menu')).text()

  await t.test('antecipa somente o snapshot público, com ETag, sem ler preços no SSR', async () => {
    backend.control({ delays: { site: 300, shell: 300, primary: 30 } })
    const response = await fetch(nuxt.url + '/menu'); const body = await response.text()
    assert.equal(response.status, 200)
    assert.ok(body.includes('Produto teste SSR'), 'O quadro estrutural perdeu o produto')
    assert.match(response.headers.get('server-timing'), /ssr_primary;dur=/)
    const reads = backend.reads()
    const primary = reads.filter(r => r.kind === 'primary')
    assert.equal(primary.length, 1)
    assert.equal(primary[0].path, '/api/v1/storefront/continuum/v0.2/catalog-structure/')
    assert.ok(primary[0].startedAt < reads.find(r => r.kind === 'shell').finishedAt)
    assert.equal(primary[0].cookiePresent, false)
    assert.ok(!reads.some(r => r.path.endsWith('/catalog/')))
    const validatedAt = continuumSsrValidatedAtMs(body)
    assert.ok(Number.isFinite(validatedAt), 'O snapshot perdeu a âncora de validade')
    assert.ok(validatedAt < reads.find(r => r.kind === 'shell').finishedWallMs - 40,
      'Consumir o snapshot depois do shell não pode renovar sua validade')
  })

  await t.test('não encaminha a sessão ao snapshot e conserva a sacola privada', async () => {
    backend.control()
    const response = await fetch(nuxt.url + '/menu', { headers: { cookie: 'sessionid=local-fixture', authorization: 'Bearer local-fixture' } })
    await response.text(); assert.equal(response.status, 200)
    const reads = backend.reads()
    assert.equal(reads.find(r => r.path.endsWith('/catalog-structure/')).cookiePresent, false)
    assert.equal(reads.find(r => r.kind === 'shell').cookiePresent, true)
    assert.ok(!reads.some(r => r.path.endsWith('/catalog/')))
  })

  await t.test('a falha do snapshot conserva o fallback canônico e relata ambas as leituras', async () => {
    backend.control({ mode: 'persistent-503', faultOnly: 'snapshot' })
    const response = await fetch(nuxt.url + '/menu'); await response.text()
    assert.equal(response.status, 200)
    const reads = backend.reads()
    assert.equal(reads.filter(r => r.path.endsWith('/catalog-structure/')).length, 1)
    assert.equal(reads.filter(r => r.path.endsWith('/public/catalog/')).length, 1)
    assert.match(response.headers.get('server-timing'), /ssr_fallback;dur=/)
    const logs = nuxt.logs().split('\n').filter(line => line.startsWith('{"category":"storefront_ssr_observation"')).map(line => JSON.parse(line))
    assert.ok(logs.some(row => row.status === 200 && row.reads.every(r => r.completed) && row.reads.some(r => r.kind === 'primary' && r.statuses.includes(503)) && row.reads.some(r => r.kind === 'fallback' && r.statuses.includes(200))))
  })

  await t.test('registra a causa nativa do socket interrompido e conserva o fallback', async () => {
    backend.control({ mode: 'persistent-reset', faultOnly: 'snapshot' })
    const response = await fetch(nuxt.url + '/menu'); await response.text()
    assert.equal(response.status, 200)
    const logs = nuxt.logs().split('\n').filter(line => line.startsWith('{"category":"storefront_ssr_observation"')).map(line => JSON.parse(line))
    assert.ok(logs.some(row => row.status === 200 && row.reads.every(r => r.completed) && row.reads.some(r => r.kind === 'primary' && r.network_codes?.includes('UND_ERR_SOCKET')) && row.reads.some(r => r.kind === 'fallback' && r.statuses.includes(200))))
  })

  await t.test('falha persistente das duas fontes continua 503 com diagnóstico do HTML', async () => {
    backend.control({ mode: 'persistent-503' })
    const response = await fetch(nuxt.url + '/menu'); await response.text()
    assert.equal(response.status, 503)
    assert.match(response.headers.get('x-storefront-request-id'), /^[a-f\d-]{36}$/)
    const logs = nuxt.logs().split('\n').filter(line => line.startsWith('{"category":"storefront_ssr_observation"')).map(line => JSON.parse(line))
    assert.ok(logs.some(row => row.status === 503 && row.reads.some(r => r.kind === 'fallback' && r.statuses.includes(503))))
  })
})
