import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { formatClock, formatClockRange, formatDateClock } from '../app/utils/clock'

// Guardrail de HORA, a metade da loja: a hora que o cliente LÊ é "12h45" ("9h05",
// "9h"). Decisão do dono em 16/11/2026, para a suíte inteira; a regra está em
// `docs/reference/suite-vocabulary.md`, seção "Hora". A trava reprova o FORMATADOR
// antigo: hora lida por gente passa por `app/utils/clock.ts`, e mais nada formata
// hora. Formato de máquina se declara na linha (ou na de cima) com
// `// hora-ok: <motivo>`.
//
// A loja não estende o operator-kit e builda sozinha, então o formatador é um
// módulo GÊMEO do de `operator-kit/app/presentation/clock.ts`, byte a byte, e a
// trava do kit (`guardrails.clock.test.ts`) não varre esta pasta. Esta varre.

const root = fileURLToPath(new URL('..', import.meta.url))
const here = join(root, 'app/utils/clock.ts')
const twin = fileURLToPath(new URL('../../operator-kit/app/presentation/clock.ts', import.meta.url))

const OLD_FORMS: ReadonlyArray<readonly [string, RegExp]> = [
  ['toLocaleTimeString', /toLocaleTimeString\(/],
  ['Intl com hora', /\bhour:\s*["'](?:2-digit|numeric)["']/],
  ['Intl com timeStyle', /\btimeStyle\b/],
  ['hora montada à mão com dois-pontos', /padStart\(2,\s*["']0["']\)\}:/],
  ['hora montada à mão com "h"', /getHours\(\)\}h/]
]
const MARKER = /hora-ok:\s*\S/
const SKIP_DIRS = new Set(['node_modules', '.nuxt', '.output', 'dist', 'generated'])

function sourceFiles (dir: string, found: string[] = []): string[] {
  let entries: string[]
  try {
    entries = readdirSync(dir)
  } catch {
    return found
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) sourceFiles(full, found)
    else if (full.endsWith('.ts') || full.endsWith('.vue')) found.push(full)
  }
  return found
}

const SOURCES = [...sourceFiles(join(root, 'app')), ...sourceFiles(join(root, 'server'))].filter(
  file => file !== here
)

function clockOffenders (text: string): string[] {
  const lines = text.split('\n')
  return lines.flatMap((line, index) => {
    if (MARKER.test(line) || MARKER.test(lines[index - 1] ?? '')) return []
    const hit = OLD_FORMS.find(([, pattern]) => pattern.test(line))
    return hit ? [`${index + 1} (${hit[0]}): ${line.trim()}`] : []
  })
}

describe('a hora na loja é 12h45', () => {
  it('nada na loja formata hora fora do formatador da casa', () => {
    const leaks = SOURCES.flatMap(file =>
      clockOffenders(readFileSync(file, 'utf8')).map(offender => `${relative(root, file)}:${offender}`)
    )
    expect(leaks, 'Use formatClock / formatDateClock de ~/utils/clock. Formato de máquina: "// hora-ok: <motivo>".').toEqual([])
  })

  it('a trava reprova cada forma antiga', () => {
    const old = [
      "new Date(parsed).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })",
      "new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })",
      "const hhmm = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`"
    ]
    for (const line of old) expect(clockOffenders(line), line).not.toEqual([])
    expect(clockOffenders("hour: '2-digit', // hora-ok: cálculo, não exibição")).toEqual([])
    expect(clockOffenders("hour: '2-digit', // hora-ok:")).not.toEqual([])
  })

  it('a varredura lê a loja de verdade', () => {
    expect(SOURCES.length).toBeGreaterThan(150)
  })
})

describe('o formatador da loja', () => {
  it('é byte a byte igual ao do operator-kit', () => {
    expect(readFileSync(here, 'utf8'), `mude os gêmeos: ${twin}`).toBe(readFileSync(twin, 'utf8'))
  })

  it('escreve a hora como a casa escreve', () => {
    const TZ = 'America/Sao_Paulo'
    expect(formatClock('2026-11-16T15:45:00Z', TZ)).toBe('12h45')
    expect(formatClock('2026-11-16T12:00:00Z', TZ)).toBe('9h')
    expect(formatClock('07:30')).toBe('7h30')
    expect(formatClock('lixo')).toBe('')
    expect(formatClockRange('12:00', '14:30')).toBe('12h às 14h30')
    expect(formatDateClock('2026-11-16T15:45:00Z', { day: '2-digit', month: '2-digit' }, { timeZone: TZ })).toBe('16/11, 12h45')
  })
})
