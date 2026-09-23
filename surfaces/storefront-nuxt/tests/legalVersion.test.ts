import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// A trava do RELÓGIO das páginas legais, e a do armazenamento no navegador.
//
// ## Por que ela existe
//
// A política de privacidade prometia, com estas palavras: *"Quando esta política mudar,
// a data no topo muda junto"*. Não mudava — a data era uma string cravada no `.vue`. O
// `terms.vue` foi editado em 28/08/2026 e em 22/09/2026 e continuou anunciando
// "20 de agosto de 2026".
//
// Prometer o que o código não faz é a forma mais cara de mentir, porque **parece
// cuidado**: quem lê a data confia nela exatamente por ela existir.
//
// Agora a data vem da versão do documento (`shopman/storefront/presentation/legal.py`),
// e esta trava fecha o único buraco que sobra — mudar o texto e não mudar a versão.
//
// ## Como consertar quando ela reprovar
//
// Ela vai reprovar toda vez que você editar o texto de uma das páginas. É de propósito:
// 1. troque `LEGAL_VERSION` e `LEGAL_UPDATED_AT` em `shopman/storefront/presentation/legal.py`;
// 2. grave aqui o resumo novo que a mensagem de falha imprime.
// Dois gestos conscientes, que é o que faltava.

const raiz = resolve(__dirname, '..')
const paginas = ['app/pages/privacy.vue', 'app/pages/terms.vue'] as const

/** Só o TEXTO que o cliente lê. Comentário e script mudam sem mudar o documento. */
function textoDaPagina (caminho: string): string {
  const fonte = readFileSync(resolve(raiz, caminho), 'utf8')
  const template = fonte.slice(fonte.indexOf('<template>'))
  return template
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function resumo (): string {
  const hash = createHash('sha256')
  for (const pagina of paginas) hash.update(textoDaPagina(pagina))
  return hash.digest('hex').slice(0, 16)
}

/** Resumo do texto publicado na versão abaixo. Muda junto com ela, nunca sozinho. */
const RESUMO_PUBLICADO = '0583a03ebccfa5b2'
const VERSAO_PUBLICADA = '2026-09-23'

describe('páginas legais — o relógio', () => {
  it('a versão declarada no servidor é a mesma que esta trava conhece', () => {
    const legalPy = readFileSync(
      resolve(raiz, '../../shopman/storefront/presentation/legal.py'),
      'utf8'
    )
    const encontrada = /LEGAL_VERSION = "([^"]+)"/.exec(legalPy)?.[1]
    expect(
      encontrada,
      'LEGAL_VERSION sumiu de shopman/storefront/presentation/legal.py'
    ).toBeTruthy()
    expect(
      encontrada,
      `A versão do documento mudou para ${encontrada} e esta trava ainda conhece ` +
      `${VERSAO_PUBLICADA}. Atualize VERSAO_PUBLICADA e RESUMO_PUBLICADO aqui.`
    ).toBe(VERSAO_PUBLICADA)
  })

  it('o texto publicado é o texto desta versão', () => {
    expect(
      resumo(),
      'O texto de /privacy ou /terms mudou sem a versão mudar junto.\n' +
      '1) troque LEGAL_VERSION e LEGAL_UPDATED_AT em shopman/storefront/presentation/legal.py;\n' +
      `2) grave aqui RESUMO_PUBLICADO = '${resumo()}'.`
    ).toBe(RESUMO_PUBLICADO)
  })
})

// ── A segunda metade: o que a loja deixa no navegador do cliente ────────────────
//
// A seção "Cookies" descrevia só cookie, e o checkout guardava nome, telefone, endereço
// e recado no `localStorage` por seis horas. Não era má-fé: a seção foi escrita quando
// o rascunho não existia, e ninguém tinha como saber que aquele parágrafo dependia dele.
//
// Esta trava obriga a conversa: chave nova no navegador reprova até alguém dizer se ela
// guarda dado do cliente — e, se guardar, a política precisa descrevê-la.

const CHAVES_DECLARADAS: Record<string, string> = {
  'shopman-checkout-draft': 'RASCUNHO DO CHECKOUT — guarda PII; descrito na política',
  'storefront-pwa-install-dismissed-until': 'só a data em que o convite foi dispensado',
  'shopman-intention:': 'chave de idempotência de uma ação; não guarda dado pessoal',
  'shop-marketing-prompt': 'marca de convite já visto; não guarda dado pessoal'
}

function arquivosDoApp (dir: string): string[] {
  const encontrados: string[] = []
  for (const entrada of readdirSync(dir, { withFileTypes: true })) {
    const caminho = resolve(dir, entrada.name)
    if (entrada.isDirectory()) encontrados.push(...arquivosDoApp(caminho))
    else if (/\.(ts|vue)$/.test(entrada.name)) encontrados.push(caminho)
  }
  return encontrados
}

const GRAVA_NO_NAVEGADOR = /(?:localStorage|sessionStorage)\.setItem\(\s*[`'"]([^`'"]+)/g

function chavesNoNavegador (): string[] {
  const chaves = new Set<string>()
  for (const arquivo of arquivosDoApp(resolve(raiz, 'app'))) {
    const fonte = readFileSync(arquivo, 'utf8')
    for (const achado of fonte.matchAll(GRAVA_NO_NAVEGADOR)) chaves.add(achado[1]!)
  }
  return [...chaves]
}

describe('páginas legais — o que fica no navegador', () => {
  it('toda chave gravada no navegador está declarada', () => {
    const declaradas = Object.keys(CHAVES_DECLARADAS)
    const novas = chavesNoNavegador().filter(
      chave => !declaradas.some(declarada => chave.startsWith(declarada))
    )
    expect(
      novas,
      'Estas chaves são gravadas no navegador do cliente e ninguém declarou o que elas ' +
      'guardam. Se guardam dado pessoal, a política de privacidade precisa descrevê-las ' +
      '— a seção "Cookies" já mentiu uma vez por causa disso.'
    ).toEqual([])
  })
})
