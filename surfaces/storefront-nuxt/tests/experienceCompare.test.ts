import { describe, expect, it } from 'vitest'
import {
  classifyContractDiff,
  collectFindings,
  diffContracts,
  exceptionIssue,
  groupFindings,
  knownIssueOf,
  normalizeContract,
  pairSteps,
  renderHtml,
  renderMarkdown,
  summarizeX11,
  summarizeX9,
  variantFromShell
} from '../scripts/experience-compare.mjs'

// OC-23: o resumo da comparação A/B é puro e o mesmo nas duas versões. A medida de X9 e
// X11 é a da fila (tests/journeys/support/typographyAudit.mjs, OC-30); estes testes fixam
// o que cada resultado dela vira no relatório.

const decisive = (text: string, size = 16) => ({ kind: 'decisive', text, size, contrast: 7, overImage: false, disabled: false })

describe('X9: o resumo da medida da fila', () => {
  it('tela sem nenhum data-decisive diz "sem marcação", nunca passa em branco', () => {
    expect(summarizeX9({ findings: [], measured: [], exceptions: [] }).status).toBe('sem-marcacao')
    // Corpo de leitura medido não é decisivo.
    expect(summarizeX9({ findings: [], measured: [{ kind: 'reading', text: 'Sobre', size: 16 }], exceptions: [] }).status).toBe('sem-marcacao')
  })

  it('decisivos medidos e nenhum achado: ok, com a contagem', () => {
    expect(summarizeX9({ findings: [], measured: [decisive('R$ 13,00'), decisive('Total')], exceptions: [] }))
      .toEqual({ status: 'ok', marked: 2, failures: [], exceptions: [] })
  })

  it('qualquer achado da medida reprova a tela, e a exceção declarada aparece sem reprovar', () => {
    const small = { ...decisive('R$ 13,00', 12), rule: 'decisivo abaixo de 14 px' }
    const amber = { ...decisive('Novo'), contrast: 3.73, rule: 'decisivo sem contraste AA', exception: 'ambar-da-marca-3523' }
    expect(summarizeX9({ findings: [small], measured: [decisive('R$ 13,00', 12)], exceptions: [] })).toMatchObject({ status: 'falha', failures: [small] })
    expect(summarizeX9({ findings: [], measured: [decisive('Novo')], exceptions: [amber] })).toMatchObject({ status: 'ok', exceptions: [amber] })
  })
})

describe('X11: a fonte a 200 %', () => {
  it('ação cortada, sumida, fora da tela, encoberta, cartão da base ou rolagem lateral reprova a tela', () => {
    const covered = { kind: 'cta', text: 'Ir para o fim do conteúdo', rule: 'encoberto com fonte 200 %', by: 'svg', layer: 'header.shop-header-bar.sticky', where: 'a' }
    const dock = { kind: 'dock', text: 'Total do pedido', share: 0.3, rule: 'cartão fixo na base cobre a página com fonte 200 %' }
    const scroll = { kind: 'page', text: '', rule: 'rolagem lateral' }
    expect(summarizeX11({ findings: [covered, dock, scroll], measured: [], exceptions: [] })).toEqual({ status: 'falha', failures: [covered, dock, scroll], exceptions: [] })
  })

  it('tamanho e contraste a 200 % são do X9 e não contam no X11', () => {
    const contrast = { ...decisive('Total'), rule: 'decisivo sem contraste AA' }
    expect(summarizeX11({ findings: [contrast], measured: [], exceptions: [] })).toEqual({ status: 'ok', failures: [], exceptions: [] })
  })

  it('o cartão do produto declarado como exceção não reprova e leva a issue', () => {
    const product = { kind: 'dock', text: 'Croissant R$ 13,00', share: 0.2, rule: 'cartão fixo na base cobre a página com fonte 200 %', exception: 'cartao-do-produto-3590' }
    expect(summarizeX11({ findings: [], measured: [], exceptions: [product] })).toEqual({ status: 'ok', failures: [], exceptions: [product] })
    expect(exceptionIssue('cartao-do-produto-3590')).toBe(3590)
    expect(exceptionIssue('sem-numero')).toBeNull()
  })
})

describe('achados conhecidos', () => {
  it('os achados do axe no /finalizar são a #3497 e a #3613; na home o contraste é outro', () => {
    expect(knownIssueOf('axe', '06-finalizar-pagamento', { rule: 'label-content-name-mismatch' })).toBe(3497)
    expect(knownIssueOf('axe', '04-finalizar-recebimento', { rule: 'aria-required-children' })).toBe(3497)
    expect(knownIssueOf('axe', '04-finalizar-recebimento', { rule: 'color-contrast' })).toBe(3613)
    expect(knownIssueOf('axe', '01-home', { rule: 'color-contrast' })).toBe(3611)
    expect(knownIssueOf('axe', '03-perguntas', { rule: 'color-contrast' })).toBeNull()
  })

  it('X9 e X11 sem issue cadastrada são achado novo', () => {
    expect(knownIssueOf('x11', '03-sacola', { rule: 'encoberto com fonte 200 %' })).toBeNull()
  })

  it('a dívida medida igual em A e B cita a issue do defeito, pela tela e pelo que cobre', () => {
    expect(knownIssueOf('x11', '01-home', { rule: 'some com fonte 200 %' })).toBe(3579)
    expect(knownIssueOf('x11', '02-produto', { rule: 'encoberto com fonte 200 %', by: 'img.size-full.snap-center[672] < div' })).toBe(3607)
    // No produto, encoberto por outra coisa que não a foto continua novo.
    expect(knownIssueOf('x11', '02-produto', { rule: 'encoberto com fonte 200 %', by: 'header.sticky' })).toBeNull()
    expect(knownIssueOf('x11', '07-revisar', { rule: 'encoberto com fonte 200 %', by: 'button', layer: 'div.pointer-events-none.sticky.bottom-0.z-10[309]' })).toBe(3608)
    expect(knownIssueOf('axe', '03-sacola', { rule: 'label-content-name-mismatch' })).toBe(3610)
    expect(knownIssueOf('axe', '04-conta', { rule: 'color-contrast' })).toBe(3612)
  })
})

describe('contrato do shell entre A e B (X13)', () => {
  const shell = (variant: string, extra: Record<string, unknown> = {}) => ({
    shell: { experience: [{ ref: 'prova-e2e', variant }], omotenashi: { greeting: 'Boa noite' }, ...extra },
    cart: { items: [], expires_at: '2026-11-24T02:30:30.492Z' }
  })

  it('a versão vem do shell, e "a" quando o experimento não vem', () => {
    expect(variantFromShell(shell('b'), 'prova-e2e')).toBe('b')
    expect(variantFromShell(shell('b'), 'outro')).toBe('a')
    expect(variantFromShell({}, 'prova-e2e')).toBe('a')
  })

  it('instantes e chaves voláteis não contam como diferença', () => {
    const a = normalizeContract({ cart: { expires_at: '2026-11-24T02:30:30Z', server_now: 1 }, when: '2026-11-24T02:31:00-03:00' })
    const b = normalizeContract({ cart: { expires_at: '2026-11-24T02:40:00Z', server_now: 2 }, when: '2026-11-24T02:41:00-03:00' })
    expect(diffContracts(a, b)).toEqual([])
  })

  it('identificadores gerados a cada rodada (linha da sacola, rascunho) não contam', () => {
    const a = normalizeContract({ cart: { draft_context: '3da5', items: [{ line_id: 'L-9E5', sku: 'CRO', qty: 1 }] } })
    const b = normalizeContract({ cart: { draft_context: '3980', items: [{ line_id: 'L-ZRG', sku: 'CRO', qty: 1 }] } })
    expect(diffContracts(a, b)).toEqual([])
    // O que a cliente vê continua contando: outro produto ou outra quantidade é diferença.
    const c = normalizeContract({ cart: { draft_context: '3980', items: [{ line_id: 'L-ZRG', sku: 'CRO', qty: 2 }] } })
    expect(diffContracts(a, c)).toEqual([{ path: 'cart.items.0.qty', a: 1, b: 2 }])
  })

  it('o prazo escrito para a cliente é relógio, não versão', () => {
    expect(normalizeContract({ reserved_until_display: '0h37' })).toEqual({ reserved_until_display: '<volátil>' })
  })

  it('chave que só contém "_at" no meio não é instante', () => {
    expect(normalizeContract({ is_at_capacity: true })).toEqual({ is_at_capacity: true })
  })

  it('só experience difere: nenhuma violação', () => {
    const diff = classifyContractDiff(diffContracts(normalizeContract(shell('a')), normalizeContract(shell('b'))))
    expect(diff.expected.map(d => d.path)).toEqual(['shell.experience.0.variant'])
    expect(diff.violations).toEqual([])
  })

  it('qualquer outra diferença é violação do X13', () => {
    const diff = classifyContractDiff(diffContracts(
      normalizeContract(shell('a', { price_hint: 'R$ 13,00' })),
      normalizeContract(shell('b', { price_hint: 'R$ 12,00' }))
    ))
    expect(diff.violations).toEqual([{ path: 'shell.price_hint', a: 'R$ 13,00', b: 'R$ 12,00' }])
  })
})

describe('relatório', () => {
  const step = (variant: string) => ({
    step: '03-sacola',
    url: '/',
    viewports: {
      375: {
        capture: `01-informacao/03-sacola/375.png`,
        captureFont200: `01-informacao/03-sacola/375-fonte200.png`,
        axe: [{ id: 'target-size', impact: 'serious', help: 'Alvo pequeno', nodes: 2, targets: [] }],
        x9: summarizeX9({ findings: [], measured: [], exceptions: [] }),
        x11: summarizeX11({ findings: [], measured: [], exceptions: variant === 'b' ? [{ kind: 'dock', text: 'Croissant', share: 0.2, rule: 'cartão fixo na base cobre a página com fonte 200 %', exception: 'cartao-do-produto-3590' }] : [] })
      }
    },
    shell: { shell: { experience: [{ ref: 'prova-e2e', variant }] } }
  })
  const runs = {
    a: { meta: { ref: 'prova-e2e', customer: 'CLI-003', startedAt: '2026-11-24T03:00:00Z', serverVariant: 'a' }, results: { '01-informacao': 'passou' }, journeys: { '01-informacao': [step('a')] } },
    b: { meta: { ref: 'prova-e2e', customer: 'CLI-003', startedAt: '2026-11-24T03:20:00Z', serverVariant: 'b' }, results: { '01-informacao': 'passou' }, journeys: { '01-informacao': [step('b')] } }
  }

  it('junta A e B por jornada e passo, com a diferença do shell', () => {
    const [journey] = pairSteps(runs)
    expect(journey!.journey).toBe('01-informacao')
    expect(journey!.steps[0]!.contract!.violations).toEqual([])
    expect(journey!.steps[0]!.contract!.expected).toHaveLength(1)
  })

  it('o HTML põe as capturas de A e B lado a lado e diz "sem marcação" do X9', () => {
    const html = renderHtml(runs)
    expect(html).toContain('src="a/01-informacao/03-sacola/375.png"')
    expect(html).toContain('src="b/01-informacao/03-sacola/375.png"')
    expect(html).toContain('X9: sem marcação')
    expect(html).toContain('igual entre A e B, exceto <code>experience</code>')
    expect(html).not.toContain('—')
  })

  it('a exceção declarada aparece no relatório com a issue, nunca escondida', () => {
    const grouped = groupFindings(collectFindings(runs))
    expect(grouped.find(f => f.check === 'x11')).toMatchObject({ step: '03-sacola', issue: 3590, a: [], b: ['375'] })
    // O axe também entra na lista, nas duas versões.
    expect(grouped.find(f => f.check === 'axe')).toMatchObject({ rule: 'target-size', a: ['375'], b: ['375'], issue: null })
    const html = renderHtml(runs)
    expect(html).toContain('exceção declarada <code>cartao-do-produto-3590</code>')
    expect(html).toContain('<td>#3590</td>')
  })

  it('o Markdown resume a jornada nas duas versões', () => {
    const md = renderMarkdown(runs)
    expect(md).toContain('## 01-informacao (A: passou · B: passou)')
    expect(md).toContain('igual (exceto experience)')
    expect(md).toContain('ok (exceção #3590)')
    expect(md).not.toContain('—')
  })
})
