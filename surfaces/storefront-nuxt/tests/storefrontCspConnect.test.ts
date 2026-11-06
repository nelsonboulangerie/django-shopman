import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { STOREFRONT_CONTENT_SECURITY_POLICY } from '../server/utils/storefrontSecurity'
import { cepSearchIssue } from '../app/presentation/address'

// Beta SMS-01: o AddressPicker chamava a ViaCEP pelo navegador e a CSP da própria
// Loja bloqueava. Toda origem que o app chama do navegador precisa estar no
// connect-src, senão a funcionalidade morre em silêncio só em produção.
function sourceFiles (dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(vue|ts)$/.test(name) ? [path] : []
  })
}

function connectSources (): string[] {
  const directive = STOREFRONT_CONTENT_SECURITY_POLICY.split(';').map(part => part.trim()).find(part => part.startsWith('connect-src')) || ''
  return directive.split(/\s+/).slice(1)
}

function allowed (origin: string): boolean {
  const host = new URL(origin).host
  return connectSources().some((source) => {
    if (!source.startsWith('https://')) return false
    const allowedHost = source.slice('https://'.length)
    if (allowedHost.startsWith('*.')) return host.endsWith(allowedHost.slice(1))
    return host === allowedHost
  })
}

describe('connect-src cobre o que o app chama do navegador', () => {
  const appDir = new URL('../app', import.meta.url).pathname
  const origins = new Set<string>()
  for (const file of sourceFiles(appDir)) {
    const text = readFileSync(file, 'utf8')
    for (const match of text.matchAll(/\$fetch(?:<[^>]*>)?\(\s*[`'"](https:\/\/[^/`'"$]+)/g)) {
      origins.add(match[1]!)
    }
  }

  it('encontra a ViaCEP entre as chamadas diretas', () => {
    expect([...origins]).toContain('https://viacep.com.br')
  })

  it.each([...origins])('%s está liberado', (origin) => {
    expect(allowed(origin)).toBe(true)
  })
})

describe('frase da busca por CEP', () => {
  it('separa CEP inexistente de consulta que falhou, sem travessão', () => {
    expect(cepSearchIssue(false)).toContain('Não achamos esse CEP')
    expect(cepSearchIssue(true)).not.toContain('Não achamos')
    expect(cepSearchIssue(true) + cepSearchIssue(false)).not.toMatch(/[—–]/)
  })
})
