// O backend controlado existe só em loopback. Prova a distinção entre status
// HTTP e erro de recepção curl, sem provocar falhas no ambiente vivo.
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { writeFile } from 'node:fs/promises'
import { startBackend, startNuxt } from '../../../surfaces/storefront-nuxt/tests/ssr/harness.mjs'

const run = promisify(execFile)
const [before, after, output] = process.argv.slice(2)
assert.ok(before && after && output)
const backend = await startBackend()
const rows = []
try {
  for (const [variant, build] of [['before', before], ['after', after]]) {
    const server = await startNuxt(backend.url, build)
    try {
      backend.control()
      await (await fetch(server.url + '/produto/FENDU')).text()
      for (const mode of ['transient-503', 'transient-reset', 'persistent-503', 'persistent-429']) {
        backend.control({ mode, ...(mode === 'persistent-429' ? { retryAfter: '120' } : {}) })
        let stdout
        try {
          stdout = (await run('curl', ['--silent', '--show-error', '--fail', '--max-time', '10', '--write-out', '%{json}', '--output', '/dev/null', server.url + '/produto/FENDU'])).stdout
        } catch (error) { stdout = error.stdout }
        const raw = JSON.parse(stdout)
        rows.push({ variant, mode, http_code: raw.http_code, curl_exitcode: raw.exitcode, curl_error: raw.errormsg,
          duration_ms: raw.time_total * 1000, reads: backend.reads().filter(read => read.kind === 'primary') })
      }
    } finally { await server.close() }
  }
  for (const mode of ['transient-503', 'transient-reset']) {
    assert.equal(rows.find(row => row.variant === 'before' && row.mode === mode).http_code, 503)
    assert.equal(rows.find(row => row.variant === 'after' && row.mode === mode).http_code, 200)
  }
  assert.ok(rows.filter(row => row.mode.startsWith('persistent')).every(row => row.http_code === 503))
  assert.ok(rows.every(row => row.curl_exitcode !== 56), 'Não confundir erro HTTP reproduzido com o curl 56 histórico')
  await writeFile(output, JSON.stringify({ method: 'Controlled loopback backend; 150ms failure burst starts at first primary read; no production faults; warmed SSR processes; actual curl exit codes', rows }, null, 2) + '\n')
  console.log(JSON.stringify(rows.map(({ variant, mode, http_code, curl_exitcode, duration_ms, reads }) => ({ variant, mode, http_code, curl_exitcode, duration_ms, attempts: reads.length }))))
} finally { await backend.close() }
