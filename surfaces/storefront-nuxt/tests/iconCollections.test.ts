import { readdirSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Todo ícone da loja sai do BUNDLE do cliente, nunca da rede no meio do gesto.
//
// O `@nuxt/icon` (`clientBundle.scan`) só embute no bundle os ícones de coleções
// INSTALADAS (`@iconify-json/<prefixo>`). Ícone de coleção ausente é buscado em
// `/api/_nuxt_icon/<prefixo>.json` na hora em que aparece pela primeira vez. O
// spinner do botão (`line-md:loading-loop`) era assim: o toque em "Atualizar" do
// aviso de versão nova disparava, no mesmo instante, a mensagem SKIP_WAITING e a
// busca do spinner. Quando essa busca chegava ao worker antigo enquanto o Chromium o
// desligava para ativar o novo, ele religava o worker antigo e a ativação esperava
// o worker ficar ocioso (30 s sem requisição): o botão girava sem fim e a versão nova
// não entrava (check "PWA — storefront", e2e `tests/e2e/pwa.spec.ts`). Sem rede, o
// mesmo ícone simplesmente não aparecia.

const root = fileURLToPath(new URL('..', import.meta.url))
const require = createRequire(import.meta.url)
const iconifyPrefixes = new Set(Object.keys(require('@iconify/collections/collections.json')))
const packageJson = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
const installed = new Set(
  Object.keys({ ...packageJson.dependencies, ...packageJson.devDependencies })
    .filter(name => name.startsWith('@iconify-json/'))
    .map(name => name.slice('@iconify-json/'.length))
)

function sourceFiles (dir: string): string[] {
  return readdirSync(join(root, dir), { withFileTypes: true }).flatMap((entry) => {
    const path = `${dir}/${entry.name}`
    if (entry.isDirectory()) return sourceFiles(path)
    return /\.(vue|ts)$/.test(entry.name) ? [path] : []
  })
}

function iconNames (): Map<string, string[]> {
  const byPrefix = new Map<string, string[]>()
  for (const file of sourceFiles('app')) {
    const source = readFileSync(join(root, file), 'utf8')
    for (const [, prefix, name] of source.matchAll(/["'`]([a-z0-9]+(?:-[a-z0-9]+)*):([a-z0-9]+(?:-[a-z0-9]+)*)["'`]/g)) {
      if (!prefix || !iconifyPrefixes.has(prefix)) continue
      const list = byPrefix.get(prefix) ?? []
      list.push(`${prefix}:${name} (${file})`)
      byPrefix.set(prefix, list)
    }
  }
  return byPrefix
}

describe('coleções de ícones', () => {
  it('acha os ícones da loja (a varredura não está cega)', () => {
    const found = iconNames()
    expect(found.get('lucide')?.length).toBeGreaterThan(50)
    expect(found.get('line-md')?.some(icon => icon.startsWith('line-md:loading-loop'))).toBe(true)
  })

  it('todo prefixo usado tem a coleção instalada, para o ícone vir do bundle e não da rede', () => {
    const missing = [...iconNames()]
      .filter(([prefix]) => !installed.has(prefix))
      .map(([prefix, icons]) => `@iconify-json/${prefix}: ${icons.slice(0, 3).join(', ')}`)
    expect(missing).toEqual([])
  })
})
