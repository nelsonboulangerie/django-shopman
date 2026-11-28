import assert from 'node:assert/strict'
import { test } from 'node:test'
import { startBackend, startNuxt } from './harness.mjs'

test('SSR real: concorrência, sessão, falha transitória e indisponibilidade honesta', async (t) => {
  const backend = await startBackend()
  let nuxt
  t.after(async () => { await nuxt?.close(); await backend.close() })
  nuxt = await startNuxt(backend.url)
  // Compilação/importação inicial não é a régua destes asserts de ordem.
  await (await fetch(nuxt.url + '/menu')).text()
  await (await fetch(nuxt.url + '/produto/FENDU')).text()

  await t.test('a leitura anônima começa antes de o shell terminar, sem GET duplicado', async () => {
    backend.control({ delays: { site: 200, shell: 200, primary: 100 } })
    const response = await fetch(nuxt.url + '/menu', { headers: { 'x-forwarded-for': '192.0.2.1' } }); await response.text()
    assert.equal(response.status, 200)
    assert.match(response.headers.get('server-timing'), /ssr;dur=.*ssr_primary;dur=/)
    assert.match(response.headers.get('x-storefront-request-id'), /^[a-f\d-]{36}$/)
    const reads = backend.reads(); const primary = reads.filter(r => r.kind === 'primary')
    assert.equal(primary.length, 1)
    assert.ok(primary[0].path.includes('/public/catalog/'))
    assert.ok(primary[0].startedAt < reads.find(r => r.kind === 'shell').finishedAt)
    assert.ok(reads.every(r => r.forwardedIpPresent))
  })

  await t.test('com sessão, conserva o caminho privado e a ordem dos snapshots', async () => {
    backend.control({ delays: { site: 80, shell: 100, primary: 20 } })
    const response = await fetch(nuxt.url + '/produto/FENDU', { headers: { cookie: 'sessionid=local-fixture' } }); await response.text()
    assert.equal(response.status, 200)
    const reads = backend.reads(); const primary = reads.filter(r => r.kind === 'primary')
    assert.equal(primary.length, 1)
    assert.equal(primary[0].path, '/api/v1/storefront/products/FENDU/')
    assert.ok(primary[0].startedAt >= Math.max(...reads.filter(r => r.kind !== 'primary').map(r => r.finishedAt)))
    assert.equal(reads.find(r => r.kind === 'site').cookiePresent, false)
    assert.equal(reads.find(r => r.kind === 'shell').cookiePresent, true)
  })

  await t.test('duas visitas não compartilham promessa nem identificador', async () => {
    backend.control()
    const responses = await Promise.all([fetch(nuxt.url + '/produto/FENDU'), fetch(nuxt.url + '/produto/FENDU')])
    await Promise.all(responses.map(response => response.text()))
    assert.ok(responses.every(r => r.status === 200))
    assert.notEqual(responses[0].headers.get('x-storefront-request-id'), responses[1].headers.get('x-storefront-request-id'))
    assert.equal(backend.reads().filter(r => r.kind === 'primary').length, 2)
  })

  await t.test('o intervalo de 200 ms permite recuperar uma rajada de 503 de 150 ms', async () => {
    backend.control({ mode: 'transient-503' })
    const response = await fetch(nuxt.url + '/produto/FENDU'); const body = await response.text()
    assert.equal(response.status, 200)
    assert.match(body, /Produto teste SSR/)
    const reads = backend.reads().filter(r => r.kind === 'primary')
    assert.deepEqual(reads.map(r => r.status), [503, 200])
    assert.ok(reads[1].startedAt - reads[0].startedAt >= 180)
  })

  await t.test('falha persistente continua 503 e fica diagnosticada, nunca 200 vazio', async () => {
    backend.control({ mode: 'persistent-503' })
    const response = await fetch(nuxt.url + '/produto/FENDU'); await response.text()
    assert.equal(response.status, 503)
    assert.equal(response.headers.get('retry-after'), '120')
    assert.equal(backend.reads().filter(r => r.kind === 'primary').length, 2)
    assert.match(response.headers.get('server-timing'), /ssr;dur=/)
    const observations = nuxt.logs().split('\n').filter(line => line.startsWith('{"category":"storefront_ssr_observation"')).map(line => JSON.parse(line))
    assert.ok(observations.some(row => row.status === 503 && row.reads.some(read => read.kind === 'primary' && read.statuses.every(status => status === 503))))
    assert.ok(!observations.some(row => JSON.stringify(row).includes('local-fixture')))
  })

  await t.test('um reset transitório do backend é recuperado e tem status intermediário registrado', async () => {
    backend.control({ mode: 'transient-reset' })
    const response = await fetch(nuxt.url + '/produto/FENDU'); await response.text()
    assert.equal(response.status, 200)
    const reads = backend.reads().filter(r => r.kind === 'primary')
    assert.ok(reads.some(read => read.reset))
    assert.equal(reads.at(-1).status, 200)
    const observations = nuxt.logs().split('\n').filter(line => line.startsWith('{"category":"storefront_ssr_observation"')).map(line => JSON.parse(line))
    assert.ok(observations.some(row => row.status === 200 && row.reads.some(read => read.kind === 'primary' && read.statuses.includes(502) && read.statuses.at(-1) === 200 && read.network_codes?.includes('UND_ERR_SOCKET'))))
  })

  await t.test('não repete 429 nem contraria Retry-After de 503', async () => {
    for (const mode of ['persistent-429', 'persistent-503']) {
      backend.control({ mode, retryAfter: '120' })
      const response = await fetch(nuxt.url + '/produto/FENDU'); await response.text()
      assert.equal(response.status, 503)
      assert.equal(backend.reads().filter(r => r.kind === 'primary').length, 1)
    }
  })
})
