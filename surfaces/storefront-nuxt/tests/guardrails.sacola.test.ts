// A loja diz "sacola", nunca "carrinho" (voz da loja; a mesma regra que a recusa do
// checkout já segue no servidor). No código o objeto é `cart`, em inglês: fora dos
// comentários, "carrinho" só pode estar num texto que a cliente lê. Medido em 20/11/2026:
// quatro textos de tela diziam "carrinho" (o aviso de "Repetir pedido", a falha ao
// atualizar a sacola e as telas de erro da sacola e da finalização).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const APP = join(__dirname, '..', 'app')

function sourceFiles (dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(vue|ts)$/.test(name) ? [path] : []
  })
}

function withoutComments (source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
}

describe('voz da loja: sacola, nunca carrinho', () => {
  it('nenhum texto da loja diz "carrinho"', () => {
    const offenders = sourceFiles(APP).flatMap((path) => {
      const lines = withoutComments(readFileSync(path, 'utf8')).split('\n')
      return lines
        .map((line, index) => ({ line: line.trim(), number: index + 1 }))
        .filter(({ line }) => /carrinho/i.test(line))
        .map(({ line, number }) => `${relative(APP, path)}:${number}: ${line}`)
    })
    expect(offenders).toEqual([])
  })
})
