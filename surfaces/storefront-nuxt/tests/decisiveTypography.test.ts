import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// X9 (OC-30): o que decide a compra (preço, disponibilidade, total, estado, erro) nunca fica
// abaixo de 14 px e se marca com `data-decisive`, que é o que a varredura do navegador mede
// (tests/journeys/x9-tipografia-decisiva.spec.ts) e a comparação A/B do OC-23 lê. Este
// arquivo é a trava BARATA, que roda no PR: o sistema de tipos não volta a 12 px onde decide,
// e as telas essenciais não perdem a marcação. O tamanho e o contraste DESENHADOS só o
// navegador mede.

const root = fileURLToPath(new URL('..', import.meta.url))

function read (path: string): string {
  return readFileSync(join(root, path), 'utf8')
}

function vueFiles (dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(join(root, dir))) {
    const rel = relative(root, join(root, dir, entry))
    if (statSync(join(root, rel)).isDirectory()) out.push(...vueFiles(rel))
    else if (rel.endsWith('.vue')) out.push(rel)
  }
  return out
}

/** O bloco de regras de uma classe do tailwind.css (até a chave que fecha). */
function rule (css: string, selector: string): string {
  const start = css.indexOf(`${selector} {`)
  expect(start, `${selector} existe no tailwind.css`).toBeGreaterThan(-1)
  return css.slice(start, css.indexOf('}', start))
}

/** Cada tag de abertura que carrega `data-decisive` (a tag pode ocupar várias linhas). */
function decisiveTags (source: string): string[] {
  return [...source.matchAll(/<[A-Za-z][^<>]*?\bdata-decisive\b[^<>]*>/g)].map(m => m[0])
}

describe('tipografia decisiva (X9, OC-30)', () => {
  const css = read('app/assets/css/tailwind.css')

  it('a meta da loja é 14 px e o corpo de leitura, 16 px', () => {
    expect(rule(css, '.shop-meta')).toContain('text-sm')
    expect(rule(css, '.shop-meta')).not.toContain('text-xs')
    expect(rule(css, '.shop-reading')).toContain('text-base')
  })

  it('o selo nasce com 14 px, quebra linha em vez de vazar, e o âmbar passa o AA', () => {
    const badge = read('app/components/Ui/Badge.vue')
    expect(badge).toMatch(/defaultVariants:\s*\{[^}]*size:\s*"md"/)
    expect(badge).toMatch(/md:\s*"[^"]*text-sm/)
    const base = badge.match(/base:\s*"([^"]+)"/)?.[1] || ''
    expect(base).not.toContain('whitespace-nowrap')
    expect(base).toContain('max-w-full')
    // Letra branca sobre o âmbar cheio da marca dá 3,7:1.
    expect(badge).not.toMatch(/warning:\s*\n?\s*"bg-warning text-warning-foreground/)
  })

  it('o botão quebra o rótulo e cresce, nunca vaza com a fonte grande (X11)', () => {
    const button = read('app/components/Ui/Button.vue')
    const base = button.match(/base:\s*"([^"]+)"/)?.[1] || ''
    expect(base).not.toContain('whitespace-nowrap')
    expect(base).toContain('max-w-full')
    for (const size of ['sm', 'default', 'lg']) {
      expect(button).toMatch(new RegExp(`${size}:\\s*"min-h-`))
    }
  })

  it('aviso e erro de campo são decisivos por construção', () => {
    expect(read('app/components/Ui/Alert/Title.vue')).toContain('data-decisive="alert"')
    expect(read('app/components/Ui/Alert/Description.vue')).toContain('data-decisive="alert"')
    expect(read('app/components/Ui/Field/Error.vue')).toContain('data-decisive="error"')
  })

  it('as telas essenciais marcam preço, disponibilidade, total e estado', () => {
    const expected: Record<string, string[]> = {
      'app/components/ProductTile.vue': ['price', 'availability'],
      'app/components/ProductListItem.vue': ['price', 'availability'],
      'app/pages/produto/[sku].vue': ['price', 'availability'],
      'app/components/CartSummaryBreakdown.vue': ['price', 'total'],
      'app/components/CartLineTotal.vue': ['price'],
      'app/pages/sacola.vue': ['price', 'availability', 'total'],
      'app/pages/finalizar.vue': ['availability', 'total'],
      'app/pages/pedido/[ref]/index.vue': ['price', 'total', 'state'],
      'app/components/PaymentBlock.vue': ['state'],
      'app/components/ShopHeader.vue': ['state'],
      'app/pages/conta/index.vue': ['state']
    }
    for (const [file, kinds] of Object.entries(expected)) {
      const tags = decisiveTags(read(file))
      for (const kind of kinds) {
        expect(tags.some(tag => tag.includes(`data-decisive="${kind}"`)), `${file} marca data-decisive="${kind}"`).toBe(true)
      }
    }
  })

  it('nenhum decisivo nas telas da loja usa 12 px nem o eyebrow', () => {
    const offenders: string[] = []
    for (const file of [...vueFiles('app/pages'), ...vueFiles('app/components')]) {
      for (const tag of decisiveTags(read(file))) {
        if (/\btext-xs\b|\bshop-kicker\b|\btext-\[/.test(tag)) offenders.push(`${file}: ${tag.slice(0, 120)}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('o decisivo em cor de ação clareia no tema escuro (o burgundy da marca dá 3,1:1 no fundo escuro)', () => {
    const offenders: string[] = []
    for (const file of [...vueFiles('app/pages'), ...vueFiles('app/components')]) {
      for (const tag of decisiveTags(read(file))) {
        if (/\btext-primary\b/.test(tag) && !/\bdark:text-foreground\b/.test(tag)) offenders.push(`${file}: ${tag.slice(0, 120)}`)
      }
    }
    expect(offenders).toEqual([])
  })
})
