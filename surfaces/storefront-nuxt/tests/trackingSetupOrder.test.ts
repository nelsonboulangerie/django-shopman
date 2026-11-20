import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Uma observação `immediate` roda na hora em que é declarada. Se ela lê um valor
// calculado que depende de uma `const` declarada MAIS ABAIXO no mesmo `setup`, a
// página inteira cai com "Cannot access 'x' before initialization". No acompanhamento
// isso só aparece quando o dado já está pronto na montagem (carga inteira pelo
// servidor, como na volta do pagamento com cartão), e passa despercebido em quem
// chega navegando pela loja. Medido em 19/11/2026 (WP-L05): a volta do pagamento
// com cartão respondia 500.

type Declaration = { name: string, start: number, body: string }

function topLevelStatements (script: string): { start: number, text: string }[] {
  const statements: { start: number, text: string }[] = []
  let offset = 0
  let current: { start: number, text: string } | null = null
  for (const line of script.split('\n')) {
    const opensStatement = /^[A-Za-z]/.test(line)
    if (opensStatement) {
      if (current) statements.push(current)
      current = { start: offset, text: line }
    } else if (current) {
      current.text += `\n${line}`
    }
    offset += line.length + 1
  }
  if (current) statements.push(current)
  return statements
}

export function immediateWatchesReadingLaterConsts (script: string): string[] {
  const statements = topLevelStatements(script)
  const declarations = new Map<string, Declaration>()
  for (const statement of statements) {
    const match = statement.text.match(/^const (\w+) = /)
    if (match?.[1]) declarations.set(match[1], { name: match[1], start: statement.start, body: statement.text })
  }

  const offenders: string[] = []
  for (const statement of statements) {
    const watched = statement.text.match(/^watch\((\w+),/)
    if (!watched?.[1] || !/immediate:\s*true/.test(statement.text)) continue
    const seen = new Set<string>()
    const queue = [watched[1]]
    while (queue.length) {
      const name = queue.shift()!
      if (seen.has(name)) continue
      seen.add(name)
      const declaration = declarations.get(name)
      if (!declaration) continue
      if (declaration.start > statement.start) offenders.push(`watch(${watched[1]}) lê ${name}, declarada depois`)
      // Só valores calculados são lidos na hora; o corpo de uma função comum não.
      if (!/^const \w+ = computed\(/.test(declaration.body)) continue
      for (const other of declarations.keys()) {
        if (other !== name && new RegExp(`\\b${other}\\b`).test(declaration.body)) queue.push(other)
      }
    }
  }
  return offenders
}

function scriptOf (path: string) {
  const source = readFileSync(join(process.cwd(), path), 'utf8')
  return source.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)?.[1] || ''
}

describe('ordem das declarações no setup', () => {
  it('o detector acusa a observação imediata que lê um valor declarado depois', () => {
    const broken = [
      'const first = computed(() => second.value)',
      'watch(first, () => {}, { immediate: true })',
      'const second = computed(() => 1)',
    ].join('\n')
    expect(immediateWatchesReadingLaterConsts(broken)).toEqual(['watch(first) lê second, declarada depois'])

    const fine = [
      'const second = computed(() => 1)',
      'const first = computed(() => second.value)',
      'watch(first, () => {}, { immediate: true })',
    ].join('\n')
    expect(immediateWatchesReadingLaterConsts(fine)).toEqual([])
  })

  it.each([
    'app/pages/pedido/[ref]/index.vue',
    'app/pages/finalizar.vue',
    'app/pages/sacola.vue',
  ])('%s não observa na hora um valor que ainda não existe', (path) => {
    const script = scriptOf(path)
    expect(script.length).toBeGreaterThan(0)
    expect(immediateWatchesReadingLaterConsts(script)).toEqual([])
  })
})
