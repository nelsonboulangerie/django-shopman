#!/usr/bin/env node
// Relatório da comparação A/B supervisionada (OC-23): lê o que as duas rodadas gravaram
// (tests/e2e/journeys, uma rodada por versão) e escreve relatorio.html e relatorio.md
// ao lado, com as capturas lado a lado, o axe, X9, X11 e a diferença do shell (X13).
//
//   node scripts/experience-compare-report.mjs [pasta]   # padrão test-results/experience-compare
//
// A pasta fica sob test-results/, que o .gitignore da raiz ignora.
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { basename, join, resolve } from 'node:path'
import { renderHtml, renderMarkdown } from './experience-compare.mjs'

const out = resolve(process.argv[2] || 'test-results/experience-compare')

const readJson = path => (existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null)
const dirs = path => (existsSync(path) ? readdirSync(path).filter(name => statSync(join(path, name)).isDirectory()) : [])

/** Resultado de cada arquivo de jornada no relatório JSON do Playwright. */
function results (report) {
  const byFile = {}
  const walk = (suite) => {
    for (const spec of suite.specs || []) {
      const file = basename(spec.file || suite.file || '').replace(/\.(spec|setup)\.ts$/, '')
      const statuses = (spec.tests || []).flatMap(t => (t.results || []).map(r => r.status))
      const status = !statuses.length ? 'não rodou' : statuses.every(s => s === 'passed') ? 'passou' : statuses.includes('skipped') && statuses.every(s => s === 'skipped') ? 'pulou' : 'falhou'
      byFile[file] = status
    }
    for (const child of suite.suites || []) walk(child)
  }
  for (const suite of report?.suites || []) walk(suite)
  return byFile
}

function run (variant) {
  const root = join(out, variant)
  const meta = readJson(join(root, 'rodada.json'))
  if (!meta) return null
  const journeys = {}
  for (const journey of dirs(root).filter(name => /^\d\d-/.test(name))) {
    journeys[journey] = dirs(join(root, journey))
      .sort()
      .map(step => readJson(join(root, journey, step, 'audit.json')))
      .filter(Boolean)
  }
  return { meta, results: results(readJson(join(root, 'playwright.json'))), journeys }
}

const runs = { a: run('a'), b: run('b') }
if (!runs.a && !runs.b) {
  console.error(`Nenhuma rodada em ${out} (falta a/rodada.json e b/rodada.json).`)
  process.exit(1)
}
writeFileSync(join(out, 'relatorio.html'), renderHtml(runs))
writeFileSync(join(out, 'relatorio.md'), renderMarkdown(runs))
console.log(`Relatório: ${join(out, 'relatorio.html')}`)
console.log(`Sumário:   ${join(out, 'relatorio.md')}`)
