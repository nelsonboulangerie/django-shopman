import { readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = join(process.cwd(), 'app')

function read (path: string) {
  return readFileSync(join(process.cwd(), path), 'utf8')
}

function vueFiles (directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return vueFiles(path)
    return entry.isFile() && entry.name.endsWith('.vue') ? [path] : []
  })
}

describe('régua do foco inteligente no Storefront', () => {
  it('alinha qualquer data-focus-target exatamente em 4rem + 6px', () => {
    const css = read('app/assets/css/tailwind.css')

    expect(css).toMatch(
      /\.shop-focus-ruler,\s*\[data-focus-target\]\s*\{\s*scroll-margin-top:\s*calc\(4rem \+ 6px\);\s*\}/
    )
  })

  it('não deixa um alvo sobrescrever a régua canônica com scroll-mt-* local', () => {
    const offenders = vueFiles(root).flatMap(path => {
      const source = readFileSync(path, 'utf8')
      const targetTags = source.match(/<[^>]*data-focus-target[^>]*>/gs) || []
      return targetTags.some(tag => /scroll-mt-/.test(tag))
        ? [relative(process.cwd(), path)]
        : []
    })

    expect(offenders).toEqual([])
  })

  it('mantém a busca overlay fora da régua porque ela substitui o chrome inteiro', () => {
    const overlay = read('app/components/SearchOverlay.vue')
    const searchState = read('app/composables/useSearchOverlay.ts')

    expect(overlay).toContain('fixed inset-0 z-50')
    expect(searchState).toContain('inputEl?.focus()')
    expect(overlay).not.toContain('data-focus-target')
  })
})
