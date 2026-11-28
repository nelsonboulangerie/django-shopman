// Comparação A/B supervisionada (OC-23, plano da Etapa II omnicanal §9.6): a parte PURA.
//
// O navegador mede (axe e tests/journeys/support/typographyAudit.mjs, a mesma medida do X9
// da fila); este módulo, em Node, resume, compara o shell de A e B (X13) e escreve o
// relatório, com teste (tests/experienceCompare.test.ts) e igual nas duas versões. As
// jornadas (tests/e2e/journeys/support/audit.ts) e o relatório
// (scripts/experience-compare-report.mjs) importam daqui.

/** As larguras do §9.5 e do X9/X11: os três celulares e o computador. */
export const VIEWPORTS = [
  { name: '320', width: 320, height: 720 },
  { name: '375', width: 375, height: 812 },
  { name: '390', width: 390, height: 844 },
  { name: 'desktop', width: 1366, height: 768 }
]

/** WCAG 2.2 AA (X10): as regras do axe com estas marcas. */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

// ── X9 e X11: o resumo da MESMA medida da fila ───────────────────────────────────────
//
// A medida de tamanho, contraste e fonte a 200 % é uma só no repositório:
// tests/journeys/support/typographyAudit.mjs (OC-30), que roda dentro da página e devolve
// `{ findings, measured, exceptions }`. Aqui só se resume o que ela achou, para o relatório
// pôr A e B lado a lado.

/**
 * X9 de uma tela (fonte normal). Sem nenhum `data-decisive` medido, a varredura não tem o
 * que medir e diz isso ("sem-marcacao"), em vez de passar em branco.
 */
export function summarizeX9 (audit) {
  const marked = (audit?.measured || []).filter(m => m.kind !== 'reading').length
  const failures = audit?.findings || []
  const exceptions = audit?.exceptions || []
  const status = failures.length ? 'falha' : marked ? 'ok' : 'sem-marcacao'
  return { status, marked, failures, exceptions }
}

/**
 * X11 de uma tela, com a fonte raiz a 200 %: os achados de corte, sumiço, saída da tela,
 * rolagem lateral e o que ficou embaixo de barra ou cartão fixo (`obscured`). Os achados de
 * tamanho e contraste a 200 % são do X9 e ficam de fora daqui.
 */
export function summarizeX11 (audit) {
  const failures = (audit?.findings || []).filter(f => f.kind === 'cta' || f.kind === 'page' || f.kind === 'dock')
  const exceptions = (audit?.exceptions || []).filter(e => e.kind === 'dock')
  return { status: failures.length ? 'falha' : 'ok', failures, exceptions }
}

/** A issue de uma exceção declarada (`<nome>-<issue>`, como `cartao-do-produto-3590`). */
export function exceptionIssue (exception) {
  const m = /-(\d+)$/.exec(exception || '')
  return m ? Number(m[1]) : null
}

/**
 * Defeitos que já têm issue: o relatório os mostra (nunca esconde), com o número, para o
 * revisor separar o achado novo do conhecido. Quem conserta fecha a issue e tira a linha.
 */
export const KNOWN_FINDINGS = [
  {
    issue: 3497,
    check: 'axe',
    // O nome acessível do resumo e da Sacola no rodapé, e a lista do resumo sem itens: os
    // três achados do axe no /finalizar que o OC-32 registrou.
    step: /finalizar|fora-da-area|trocou-para-retirada/,
    rule: /^(label-content-name-mismatch|aria-required-children)$/,
    what: '/finalizar: nome acessível do resumo e da Sacola, e lista sem itens'
  },
  // Abertas pelo OC-23 na rodada de 25/11/2026, iguais em A e B (dívida da loja, uma por
  // defeito, com label ficou-de-fora).
  { issue: 3579, check: 'x11', step: /home|rodape/, rule: /^some com fonte 200/, what: 'home: o aviso do pedido em andamento espreme o estado' },
  { issue: 3607, check: 'x11', step: /produto/, rule: /^encoberto/, by: /(^| )img\./, what: 'produto, computador: "Foto anterior" por baixo da foto' },
  { issue: 3608, check: 'x11', step: /revisar/, rule: /^encoberto/, by: /sticky\.bottom-0/, what: 'revisão: o aviso de rolagem da folha cobre o preço' },
  { issue: 3609, check: 'x11', step: /finalizar-entrega|fora-da-area/, rule: /^sai da largura/, what: '/finalizar entrega: ações do endereço saem da tela' },
  { issue: 3610, check: 'axe', step: /sacola/, rule: /^label-content-name-mismatch$/, what: '/sacola: nome acessível sem o texto visível' },
  { issue: 3580, check: 'axe', step: /produto/, rule: /^(scrollable-region-focusable|target-size)$/, what: 'galeria do produto: teclado e alvo' },
  { issue: 3611, check: 'axe', step: /home|rodape/, rule: /^color-contrast$/, what: 'home: pílula "Acompanhar" sem AA' },
  { issue: 3612, check: 'axe', step: /conta/, rule: /^color-contrast$/, what: '/conta: casas vazias do cartão fidelidade sem AA' },
  { issue: 3613, check: 'axe', step: /finalizar|fora-da-area|trocou-para-retirada/, rule: /^color-contrast$/, what: '/finalizar: "Continuar" desbotado durante "Atualizando total…"' }
]

/** A issue que já descreve este achado, ou null. */
export function knownIssueOf (check, step, finding) {
  const hit = KNOWN_FINDINGS.find(k => k.check === check &&
    (!k.step || k.step.test(step || '')) &&
    k.rule.test(finding?.rule || '') &&
    (!k.by || k.by.test(`${finding?.by || ''} ${finding?.layer || ''}`)))
  return hit ? hit.issue : null
}

// ── Contrato do shell (X13) ──────────────────────────────────────────────────────────

const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/
// Valores que mudam com o relógio ou com a rodada, não com a versão: instantes e prazos,
// credenciais, e identificadores que o servidor gera a cada rodada (a linha da sacola,
// o rascunho do checkout, o código do pedido). Medido na primeira rodada: `line_id` e
// `draft_context` eram as diferenças do shell fora de `experience`, e o horário da
// reserva escrito para a cliente (`reserved_until_display`, "0h37" contra "0h42").
const VOLATILE_KEY = /(_at|_until|_since|_deadline|_ms|_seconds)(_display)?$|^(now|server_now|key|draft_context|order_ref)$|expires|deadline|countdown|token|csrf|nonce|idempotency|(^|_)id$/i

/**
 * O shell como contrato comparável: instantes e chaves voláteis viram marcadores, para a
 * diferença entre duas rodadas falar só do que a versão poderia mudar.
 */
export function normalizeContract (value, key = '') {
  if (Array.isArray(value)) return value.map(item => normalizeContract(item, key))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(k => [k, normalizeContract(value[k], k)]))
  }
  if (VOLATILE_KEY.test(key) && value !== null && value !== '') return '<volátil>'
  if (typeof value === 'string' && INSTANT.test(value)) return '<instante>'
  return value
}

/** As folhas que diferem entre dois contratos (`path` em notação de ponto). */
export function diffContracts (a, b, path = '') {
  if (a === b) return []
  const isObj = v => v && typeof v === 'object'
  if (!isObj(a) || !isObj(b) || Array.isArray(a) !== Array.isArray(b)) return [{ path: path || '(raiz)', a, b }]
  const keys = Array.isArray(a)
    ? [...Array(Math.max(a.length, b.length)).keys()].map(String)
    : [...new Set([...Object.keys(a), ...Object.keys(b)])].sort()
  return keys.flatMap(k => diffContracts(a[k], b[k], path ? `${path}.${k}` : k))
}

/**
 * Separa a diferença do shell entre A e B: `experience` é a única esperada (X13); o resto
 * é violação do X13, a ser lida pelo revisor.
 */
export function classifyContractDiff (diffs) {
  const expected = diffs.filter(d => /(^|\.)experience(\.|$)/.test(d.path))
  const violations = diffs.filter(d => !expected.includes(d))
  return { expected, violations }
}

/** A versão que o shell traz para um experimento (padrão "a" quando não vem). */
export function variantFromShell (response, ref) {
  const list = response?.shell?.experience || []
  return list.find(item => item?.ref === ref)?.variant || 'a'
}

// ── Relatório ────────────────────────────────────────────────────────────────────────

const escape = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

function axeCount (step, viewport) {
  const v = step?.viewports?.[viewport]?.axe
  if (!v) return '-'
  return String(v.length)
}

/** O status de X9 ou X11 numa largura; a falha só de defeito conhecido diz a issue. */
function statusOf (step, viewport, check) {
  const summary = step?.viewports?.[viewport]?.[check]
  if (!summary) return '-'
  const excIssues = [...new Set((summary.exceptions || []).map(e => exceptionIssue(e.exception)).filter(Boolean))]
  if (summary.status !== 'falha') return excIssues.length ? `${summary.status} (exceção ${excIssues.map(i => `#${i}`).join(', ')})` : summary.status
  const issues = [...new Set(summary.failures.map(f => knownIssueOf(check, step.step, f)))]
  if (issues.every(Boolean)) return `conhecido (${issues.map(i => `#${i}`).join(', ')})`
  return issues.some(Boolean) ? `falha (+${issues.filter(Boolean).map(i => `#${i}`).join(', ')})` : 'falha'
}

/** O nome do(s) experimento(s) da rodada. */
function refsOf (runs) {
  const meta = runs.a?.meta || runs.b?.meta || {}
  const refs = meta.refs || (meta.ref ? [meta.ref] : [])
  return refs.length ? refs : ['?']
}

/**
 * Todos os achados das duas rodadas numa lista só (X9, X11, axe), com a issue quando o
 * defeito já é conhecido: é o que o revisor lê primeiro.
 */
export function collectFindings (runs) {
  const out = []
  for (const variant of ['a', 'b']) {
    for (const [journey, steps] of Object.entries(runs[variant]?.journeys || {})) {
      for (const step of steps) {
        for (const [viewport, vp] of Object.entries(step.viewports || {})) {
          for (const check of ['x9', 'x11']) {
            for (const f of vp[check]?.failures || []) {
              out.push({ variant, journey, step: step.step, viewport, check, rule: f.rule, text: f.text, issue: knownIssueOf(check, step.step, f) })
            }
            // Exceção declarada não reprova, mas aparece com a issue que a tira.
            for (const e of vp[check]?.exceptions || []) {
              out.push({ variant, journey, step: step.step, viewport, check, rule: `${e.rule} (exceção ${e.exception})`, text: e.text, issue: exceptionIssue(e.exception) })
            }
          }
          for (const v of vp.axe || []) {
            out.push({ variant, journey, step: step.step, viewport, check: 'axe', rule: v.id, text: v.help, issue: knownIssueOf('axe', step.step, { rule: v.id }) })
          }
        }
      }
    }
  }
  return out
}

/**
 * Junta as duas rodadas por jornada e passo. `runs` é `{ a: Run, b: Run }`, cada `Run`
 * com `{ meta, results: { [arquivo]: 'passed'|'failed'|... }, journeys: { [jornada]: Step[] } }`.
 */
export function pairSteps (runs) {
  const journeys = [...new Set([...Object.keys(runs.a?.journeys || {}), ...Object.keys(runs.b?.journeys || {})])].sort()
  return journeys.map((journey) => {
    const a = runs.a?.journeys?.[journey] || []
    const b = runs.b?.journeys?.[journey] || []
    const names = [...new Set([...a.map(s => s.step), ...b.map(s => s.step)])].sort()
    return {
      journey,
      steps: names.map((step) => {
        const sa = a.find(s => s.step === step) || null
        const sb = b.find(s => s.step === step) || null
        const diffs = sa?.shell && sb?.shell
          ? classifyContractDiff(diffContracts(normalizeContract(sa.shell), normalizeContract(sb.shell)))
          : null
        return { step, a: sa, b: sb, contract: diffs }
      })
    }
  })
}

/** O sumário em Markdown (para colar no PR ou no registro da sessão supervisionada). */
export function renderMarkdown (runs) {
  const paired = pairSteps(runs)
  const lines = [
    '# Comparação A/B supervisionada (OC-23)',
    '',
    `Experimento(s): ${refsOf(runs).map(r => `\`${r}\``).join(', ')} · cliente da jornada: ${runs.a?.meta?.customer || runs.b?.meta?.customer || '?'}`,
    `Rodada A: ${runs.a?.meta?.startedAt || 'não rodou'} · rodada B: ${runs.b?.meta?.startedAt || 'não rodou'}`,
    '',
    'X9 e X11 por largura (320 / 375 / 390 / desktop). axe = nº de regras WCAG violadas.',
    '',
    '## Achados (A e B)',
    '',
    '| verificação | jornada / passo | achado | A | B | issue |',
    '|---|---|---|---|---|---|',
    ...groupFindings(collectFindings(runs)).map(f => `| ${f.check.toUpperCase()} | ${f.journey} / ${f.step} | ${String(f.rule).replace(/\|/g, '/')} | ${f.a.join(', ') || '-'} | ${f.b.join(', ') || '-'} | ${f.issue ? `#${f.issue}` : 'novo'} |`),
    ''
  ]
  for (const { journey, steps } of paired) {
    const ra = runs.a?.results?.[journey] || '-'
    const rb = runs.b?.results?.[journey] || '-'
    lines.push(`## ${journey} (A: ${ra} · B: ${rb})`, '')
    lines.push('| passo | axe A | axe B | X9 A | X9 B | X11 A | X11 B | shell A×B |', '|---|---|---|---|---|---|---|---|')
    for (const s of steps) {
      const vps = VIEWPORTS.map(v => v.name)
      const join = (step, fn) => vps.map(v => fn(step, v)).join(' / ')
      const contract = !s.contract ? 'sem par' : s.contract.violations.length ? `**${s.contract.violations.length} diferença(s) fora de experience**` : 'igual (exceto experience)'
      lines.push(`| ${s.step} | ${join(s.a, axeCount)} | ${join(s.b, axeCount)} | ${join(s.a, (st, v) => statusOf(st, v, 'x9'))} | ${join(s.b, (st, v) => statusOf(st, v, 'x9'))} | ${join(s.a, (st, v) => statusOf(st, v, 'x11'))} | ${join(s.b, (st, v) => statusOf(st, v, 'x11'))} | ${contract} |`)
    }
    lines.push('')
  }
  return lines.join('\n')
}

/** Agrupa os achados por verificação, passo e regra, com as larguras de A e de B. */
export function groupFindings (findings) {
  const groups = new Map()
  for (const f of findings) {
    const key = [f.check, f.journey, f.step, f.rule, f.text].join('|')
    if (!groups.has(key)) groups.set(key, { check: f.check, journey: f.journey, step: f.step, rule: f.rule, text: f.text, issue: f.issue, a: [], b: [] })
    const g = groups.get(key)
    if (!g[f.variant].includes(f.viewport)) g[f.variant].push(f.viewport)
  }
  return [...groups.values()].sort((x, y) => Number(Boolean(x.issue)) - Number(Boolean(y.issue)) || `${x.journey}${x.step}`.localeCompare(`${y.journey}${y.step}`))
}

function axeList (violations) {
  if (!violations?.length) return '<p class="ok">axe: nenhuma violação</p>'
  return `<ul class="axe">${violations.map(v => `<li><b>${escape(v.id)}</b> (${escape(v.impact)}, ${v.nodes} nó${v.nodes === 1 ? '' : 's'}): ${escape(v.help)}</li>`).join('')}</ul>`
}

function issueTag (check, step, finding) {
  const issue = knownIssueOf(check, step, finding)
  return issue ? ` <b class="known">achado conhecido #${issue}</b>` : ''
}

function findingText (f) {
  const detail = [f.size ? `${f.size}px` : '', f.contrast ? `${f.contrast}:1` : '', f.layer ? `camada por cima: ${f.layer}` : f.by ? `por cima: ${f.by}` : ''].filter(Boolean).join(', ')
  return `${escape(f.rule)}: "${escape(f.text)}"${detail ? ` (${escape(detail)})` : ''}`
}

function x9Block (x9, step) {
  if (!x9) return ''
  if (x9.status === 'sem-marcacao') return '<p class="warn">X9: sem marcação <code>data-decisive</code> nesta tela</p>'
  const bad = x9.failures.map(f => `<li>${findingText(f)}${issueTag('x9', step, f)}</li>`).join('')
  const exc = (x9.exceptions || []).map(e => `<li>exceção declarada <code>${escape(e.exception)}</code>: "${escape(e.text)}" ${e.contrast}:1</li>`).join('')
  return `<p class="${x9.status === 'ok' ? 'ok' : 'bad'}">X9: ${x9.marked} decisivo(s) medido(s), ${x9.failures.length} achado(s)</p>${bad || exc ? `<ul>${bad}${exc}</ul>` : ''}`
}

function x11Block (x11, step) {
  if (!x11) return ''
  const bad = x11.failures.slice(0, 12).map(f => `<li>${findingText(f)}${issueTag('x11', step, f)}</li>`).join('')
  const more = x11.failures.length > 12 ? `<li>e mais ${x11.failures.length - 12}</li>` : ''
  const exc = (x11.exceptions || []).map(e => `<li>exceção declarada <code>${escape(e.exception)}</code>: ${findingText(e)} <b class="known">#${exceptionIssue(e.exception) ?? '?'}</b></li>`).join('')
  return `<p class="${x11.status === 'ok' ? 'ok' : 'bad'}">X11 (fonte 200 %): ${x11.failures.length} achado(s)${exc ? `, ${x11.exceptions.length} exceção(ões) declarada(s)` : ''}</p>${bad || exc ? `<ul>${bad}${more}${exc}</ul>` : ''}`
}

function cell (step, variant, viewport) {
  if (!step) return '<td class="missing">não chegou a este passo</td>'
  const vp = step.viewports?.[viewport]
  if (!vp) return '<td class="missing">sem auditoria nesta largura</td>'
  const img = (file, alt) => file ? `<a href="${escape(`${variant}/${file}`)}"><img loading="lazy" src="${escape(`${variant}/${file}`)}" alt="${escape(alt)}"></a>` : ''
  return `<td>${img(vp.capture, `${variant} ${viewport}`)}${img(vp.captureFont200, `${variant} ${viewport} fonte 200 %`)}${axeList(vp.axe)}${x9Block(vp.x9, step.step)}${x11Block(vp.x11, step.step)}</td>`
}

function contractBlock (contract) {
  if (!contract) return '<p class="warn">Shell: sem par para comparar (uma das versões não chegou a este passo).</p>'
  const rows = [...contract.violations, ...contract.expected]
    .map(d => `<tr class="${contract.expected.includes(d) ? 'expected' : 'violation'}"><td><code>${escape(d.path)}</code></td><td><code>${escape(JSON.stringify(d.a))}</code></td><td><code>${escape(JSON.stringify(d.b))}</code></td></tr>`)
    .join('')
  const head = contract.violations.length
    ? `<p class="bad">Shell (X13): ${contract.violations.length} diferença(s) além de <code>experience</code></p>`
    : '<p class="ok">Shell (X13): igual entre A e B, exceto <code>experience</code></p>'
  return `${head}${rows ? `<table class="diff"><tr><th>caminho</th><th>A</th><th>B</th></tr>${rows}</table>` : ''}`
}

/** O relatório completo, em HTML de arquivo único (as capturas ficam em a/ e b/). */
export function renderHtml (runs) {
  const paired = pairSteps(runs)
  const decided = r => r.meta?.serverVariants
    ? Object.entries(r.meta.serverVariants).map(([ref, v]) => `${escape(ref)} = <b>${escape(v)}</b>`).join(', ')
    : `<b>${escape(r.meta?.serverVariant)}</b>`
  const meta = (r, v) => r ? `<li>Versão ${v.toUpperCase()}: rodou em ${escape(r.meta?.startedAt)}; o servidor decidiu ${decided(r)}</li>` : `<li>Versão ${v.toUpperCase()}: não rodou</li>`
  const findings = groupFindings(collectFindings(runs))
  const findingsBlock = findings.length
    ? `<table class="findings"><tr><th>verificação</th><th>jornada e passo</th><th>achado</th><th>A</th><th>B</th><th>issue</th></tr>${findings.map(f => `<tr class="${f.issue ? 'known' : 'violation'}"><td>${escape(f.check.toUpperCase())}</td><td>${escape(f.journey)} / ${escape(f.step)}</td><td><b>${escape(f.rule)}</b> ${escape(f.text)}</td><td>${escape(f.a.join(', ') || '-')}</td><td>${escape(f.b.join(', ') || '-')}</td><td>${f.issue ? `#${f.issue}` : 'novo'}</td></tr>`).join('')}</table>`
    : '<p class="ok">Nenhum achado de axe, X9 ou X11 nas duas versões.</p>'
  const body = paired.map(({ journey, steps }) => `
<section>
  <h2>${escape(journey)}</h2>
  <p>A: ${escape(runs.a?.results?.[journey] || '-')} · B: ${escape(runs.b?.results?.[journey] || '-')}</p>
  ${steps.map(s => `
  <details open>
    <summary>${escape(s.step)} <small>${escape(s.a?.url || s.b?.url || '')}</small></summary>
    ${contractBlock(s.contract)}
    <table class="pair">
      <tr><th>largura</th><th>A</th><th>B</th></tr>
      ${VIEWPORTS.map(v => `<tr><th>${v.name}</th>${cell(s.a, 'a', v.name)}${cell(s.b, 'b', v.name)}</tr>`).join('')}
    </table>
  </details>`).join('')}
</section>`).join('')
  return `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparação A/B</title>
<style>
:root { --bg: #fff; --fg: #1b1b1b; --muted: #5c5c5c; --line: #ddd; --ok: #1f6f3a; --bad: #a3261b; --warn: #7a5300; }
@media (prefers-color-scheme: dark) { :root { --bg: #141414; --fg: #eee; --muted: #aaa; --line: #333; --ok: #6fd08f; --bad: #ff8a7a; --warn: #e8c06a; } }
body { background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; margin: 0 auto; padding: 16px; max-width: 1600px; }
small, .missing { color: var(--muted); }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid var(--line); padding: 6px; vertical-align: top; text-align: left; }
table.pair td { width: 50%; }
img { max-width: 48%; margin: 2px; border: 1px solid var(--line); vertical-align: top; }
.ok { color: var(--ok); } .bad { color: var(--bad); } .warn { color: var(--warn); }
tr.violation td { color: var(--bad); }
tr.known td, .known { color: var(--warn); }
table.findings { margin-bottom: 24px; }
code { overflow-wrap: anywhere; }
summary { font-weight: 600; cursor: pointer; margin: 12px 0 4px; }
</style></head><body>
<h1>Comparação A/B supervisionada (OC-23)</h1>
<p>Experimento(s) ${refsOf(runs).map(r => `<code>${escape(r)}</code>`).join(', ')}, cliente da jornada ${escape(runs.a?.meta?.customer || runs.b?.meta?.customer || '?')}. Mesmo seed, versão decidida pelo servidor (coorte na RuleConfig).</p>
<ul>${meta(runs.a, 'a')}${meta(runs.b, 'b')}</ul>
<p><small>Em cada largura: a captura normal e a captura com a fonte raiz a 200 % (X11); axe com as regras WCAG 2.2 AA (X10); X9 nos elementos <code>data-decisive</code>. O relógio do servidor não é fixável sem tocar código de produção: a loja fica aberta 24 h pelo seed e A e B rodam em sequência, então horários de janela podem diferir entre as rodadas (#3574). Na diferença do shell, instantes, prazos (inclusive o horário escrito, como <code>reserved_until_display</code>) e identificadores que o servidor gera a cada rodada (<code>line_id</code>, <code>draft_context</code>) não contam.</small></p>
<h2>Achados</h2>
<p><small>Cada linha é um achado, com as larguras em que apareceu em cada versão. "Achado conhecido" já tem issue e está à vista, não escondido.</small></p>
${findingsBlock}
${body}
</body></html>
`
}
