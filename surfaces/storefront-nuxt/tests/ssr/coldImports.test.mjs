import assert from 'node:assert/strict'
import { test } from 'node:test'
import { startBackend, startNuxt } from './harness.mjs'

test('primeiro SSR não carrega o índice externo inteiro de Reka UI', async (t) => {
  const backend = await startBackend()
  let server
  t.after(async () => { await server?.close(); await backend.close() })
  const previous = process.env.NODE_DEBUG
  try {
    process.env.NODE_DEBUG = 'esm'
    server = await startNuxt(backend.url, '.output', { continuumEnabled: true })
  } finally {
    if (previous === undefined) delete process.env.NODE_DEBUG
    else process.env.NODE_DEBUG = previous
  }
  // O health continua independente do Django; não aquecemos páginas com GETs.
  assert.equal(backend.reads().length, 0)
  for (const route of ['/menu', '/produto/FENDU']) {
    const response = await fetch(server.url + route); const body = await response.text()
    assert.equal(response.status, 200)
    assert.ok(body.includes('Produto teste SSR'))
    const logs = server.logs()
    assert.match(logs, /ESM\s+\d+:/, 'O diagnóstico de imports precisa estar ativo')
    const external = [...new Set([...logs.matchAll(/file:\/\/\/[^\s)'"\]]+/g)]
      .map(match => match[0]).filter(path => path.includes('/node_modules/reka-ui/')))]
    assert.equal(external.length, 0, `O SSR voltou a importar o pacote inteiro: ${external.slice(0, 3)}`)
  }
})
