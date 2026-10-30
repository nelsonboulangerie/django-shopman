// Experimento pareado: mesmos snapshots anônimos em memória, mesmos atrasos,
// processos SSR novos. Nenhum corpo, cookie ou credencial é salvo no relatório.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { writeFile } from 'node:fs/promises'
import { htmlSemantics } from '../../../surfaces/storefront-nuxt/tests/ssr/semantics.mjs'
import { startBackend, startNuxt } from '../../../surfaces/storefront-nuxt/tests/ssr/harness.mjs'

const [before, after, output] = process.argv.slice(2)
assert.ok(before && after && output, 'Uso: node benchmark_ssr.mjs <build-anterior> <build-novo> <json> [--live-snapshots]')
const liveSnapshots = process.argv.includes('--live-snapshots')
const backend = await startBackend({ liveSnapshots })
const rows = []
const hash = value => createHash('sha256').update(value).digest('hex')
const normalize = value => value.replace(/http:\/\/127\.0\.0\.1:\d+/g, 'http://local.test')
function semantics (body) {
  const { text, schemas } = htmlSemantics(body)
  return { visible_text_sha256: hash(normalize(text)), json_ld_sha256: hash(normalize(JSON.stringify(schemas))) }
}
try {
  // Materializa os dados antes da régua; todos os casos seguintes recebem os
  // mesmos bytes e os mesmos atrasos. A origem, se usada, só recebe estes GETs.
  for (const path of ['site/', 'public/shell/', 'continuum/v0.2/catalog-structure/']) {
    const response = await fetch(backend.url + '/api/v1/storefront/' + path)
    assert.equal(response.status, 200); await response.arrayBuffer()
  }
  for (const route of ['/menu']) {
    for (let round = 0; round < 3; round++) {
      for (const variant of round % 2 ? ['after', 'before'] : ['before', 'after']) {
        backend.control({ delays: { site: 1000, shell: 900, primary: 1800 } })
        const server = await startNuxt(backend.url, variant === 'before' ? before : after, { continuumEnabled: true })
        try {
          const started = performance.now()
          const response = await fetch(server.url + route)
          const body = await response.text()
          assert.equal(response.status, 200)
          const reads = backend.reads()
          assert.equal(reads.filter(read => read.kind === 'primary').length, 1)
          rows.push({ variant, round, route, duration_ms: performance.now() - started, status: response.status,
            ...semantics(body), server_timing: response.headers.get('server-timing'),
            reads: reads.map(read => ({ kind: read.kind, path: read.path, start_ms: read.startedAt - started,
              finish_ms: read.finishedAt - started, body_sha256: read.bodySha256, status: read.status })) })
        } finally { await server.close() }
      }
    }
  }
  for (const route of ['/menu']) {
    const selected = rows.filter(row => row.route === route)
    assert.equal(new Set(selected.map(row => row.visible_text_sha256)).size, 1, 'Texto visível divergiu')
    assert.equal(new Set(selected.map(row => row.json_ld_sha256)).size, 1, 'Preço/disponibilidade/SEO divergiu')
  }
  const report = { method: 'Continuum enabled exactly as production; paired fresh SSR processes, immutable anonymous snapshots in memory, injected site=1000ms/shell=900ms/primary=1800ms; alternate order; not claimed as historical production spans',
    live_snapshots: liveSnapshots, rows, semantics_equal: true }
  await writeFile(output, JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(rows.map(({ variant, route, duration_ms }) => ({ variant, route, duration_ms }))))
} finally { await backend.close() }
