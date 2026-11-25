// Clique nunca inerte: travas estáticas da loja.
//
// Irmã de `surfaces/operator-kit/tests/guardrails.pendingAction.test.ts`; a regra
// e o contrato estão na seção "Clique nunca inerte" do README do kit.
//
// 1. Botão com `@click` numa função `async` do próprio componente precisa declarar
//    o pendente no MESMO elemento (`:loading`, `:aria-busy` ou `:disabled`), ou a
//    ação passar por `usePendingAction` (que não é `async function`, então sai da
//    varredura). O que já existia sem isso está em `KNOWN_INERT`, que só encolhe:
//    consertou, tira da lista (o teste reprova a entrada que sobrou); entrada nova
//    reprova.
//    Desde DEV-2026-094 o `UiButton` gira e trava sozinho quando o clique DEVOLVE a
//    promessa (`@click="save"`, `@click="save(x)"`): sai da varredura. Ficam o
//    `<button>` nativo e o `UiButton` cujo handler joga a promessa fora
//    (`@click="a(); save()"`), que reprova sem lista.
// 2. D1 (opção 3): o "Adicionar" nunca nasce `disabled` por esperar hidratação, e o
//    toque precoce é guardado pelo script inline do <head>.
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '..')
const read = (file: string) => readFileSync(join(root, file), 'utf8')

function vueFiles (dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return vueFiles(path)
    return entry.name.endsWith('.vue') ? [path] : []
  })
}

// Abre cada tag do template respeitando aspas (handler com `=>` e classe com `>`).
function openingTags (template: string): string[] {
  const tags: string[] = []
  let i = 0
  while ((i = template.indexOf('<', i)) !== -1) {
    if (!/[A-Za-z]/.test(template[i + 1] ?? '')) { i += 1; continue }
    let quote = ''
    let j = i + 1
    for (; j < template.length; j++) {
      const ch = template[j]
      if (quote) { if (ch === quote) quote = '' } else if (ch === '"' || ch === '\'') quote = ch
      else if (ch === '>') break
    }
    tags.push(template.slice(i, j + 1))
    i = j + 1
  }
  return tags
}

// Separa os blocos <script> do resto do SFC por índice, sem regex de tag
// (o CodeQL trata regex de <script> como filtro de HTML; aqui só lemos fonte nossa).
function splitScripts (source: string): { script: string, template: string } {
  const lower = source.toLowerCase()
  const scripts: string[] = []
  let template = ''
  let at = 0
  while (true) {
    const open = lower.indexOf('<script', at)
    if (open === -1) break
    const bodyStart = lower.indexOf('>', open) + 1
    const close = lower.indexOf('</script', bodyStart)
    if (bodyStart === 0 || close === -1) break
    template += source.slice(at, open)
    scripts.push(source.slice(bodyStart, close))
    const end = lower.indexOf('>', close)
    at = end === -1 ? source.length : end + 1
  }
  template += source.slice(at)
  return { script: scripts.join('\n'), template }
}

// O botão da loja com o pendente automático (`app/components/ui/Button.vue`).
const AUTO_PENDING_TAGS = /^<UiButton\b/
// Handler que devolve o que a função devolveu: o nome solto ou UMA chamada.
const RETURNS_RESULT = /^(?:\w+|\w+\([^;]*\))$/

function asyncNamesOf (script: string): Set<string> {
  return new Set([
    ...[...script.matchAll(/async\s+function\s+(\w+)/g)].map(m => m[1]!),
    ...[...script.matchAll(/(?:const|let)\s+(\w+)\s*=\s*async\b/g)].map(m => m[1]!)
  ])
}

function inertAsyncClicks (source: string): string[] {
  const { script, template } = splitScripts(source)
  const asyncNames = asyncNamesOf(script)
  const inert = new Set<string>()
  for (const tag of openingTags(template)) {
    const click = tag.match(/@click(?:\.\w+)*="(void\s+)?(\w+)(?:\([^"]*\))?"/)
    if (!click || !asyncNames.has(click[2]!)) continue
    if (AUTO_PENDING_TAGS.test(tag) && !click[1]) continue
    if (/\s:(?:loading|aria-busy|disabled)=/.test(tag)) continue
    inert.add(click[2]!)
  }
  return [...inert].sort()
}

// `UiButton` cujo handler chama uma função async e joga a promessa fora: o pendente
// automático não a vê, e o botão fica mudo.
function discardedAsyncClicks (source: string): string[] {
  const { script, template } = splitScripts(source)
  const asyncNames = asyncNamesOf(script)
  const found = new Set<string>()
  for (const tag of openingTags(template)) {
    if (!AUTO_PENDING_TAGS.test(tag)) continue
    const click = tag.match(/@click(?:\.\w+)*="([^"]*)"/)
    if (!click) continue
    const handler = click[1]!.trim()
    if (RETURNS_RESULT.test(handler)) continue
    if (/\s:(?:loading|aria-busy)=/.test(tag)) continue
    for (const call of handler.matchAll(/\b(\w+)\s*\(/g)) {
      if (asyncNames.has(call[1]!)) found.add(call[1]!)
    }
  }
  return [...found].sort()
}

// O que já existia sem pendente declarado em 01/10/2026. Só encolhe.
// 25/11/2026 (DEV-2026-094): o pendente automático do `UiButton` tirou 14 dos 16 itens.
// Os dois que sobram são `UiAlertDialogAction` (o diálogo fecha no toque e a ação corre
// depois, sem sinal) e moram em fluxos com dono próprio nesta data (checkout e
// acompanhamento do pedido): saem na issue de seguimento.
const KNOWN_INERT: Record<string, string[]> = {
  'app/pages/finalizar.vue': ['goToAuthRoute'],
  'app/pages/pedido/[ref]/index.vue': ['postAction']
}

describe('clique nunca inerte (loja)', () => {
  it('botão com ação async declara o pendente; a lista do que falta só encolhe', () => {
    const found: Record<string, string[]> = {}
    for (const file of vueFiles(join(root, 'app'))) {
      const inert = inertAsyncClicks(readFileSync(file, 'utf8'))
      if (inert.length) found[relative(root, file)] = inert
    }
    expect(found).toEqual(KNOWN_INERT)
  })

  it('a varredura reconhece o botão mudo e o que declara pendente', () => {
    const mute = '<script setup>async function save () {}</script><template><button @click="save">Salvar</button></template>'
    const auto = '<script setup>async function save () {}</script><template><UiButton @click="save(1)">Salvar</UiButton></template>'
    const declared = '<script setup>async function save () {}</script><template><UiButton :loading="saving" @click="save">Salvar</UiButton></template>'
    const viaCapability = '<script setup>const { run: save, pending } = usePendingAction(() => $fetch("/x"))</script><template><UiButton @click="save" :loading="pending" /></template>'
    expect(inertAsyncClicks(mute)).toEqual(['save'])
    expect(inertAsyncClicks(auto)).toEqual([])
    expect(inertAsyncClicks(declared)).toEqual([])
    expect(inertAsyncClicks(viaCapability)).toEqual([])
  })

  it('UiButton nunca joga fora a promessa da ação (o automático não a veria)', () => {
    const found: Record<string, string[]> = {}
    for (const file of vueFiles(join(root, 'app'))) {
      const discarded = discardedAsyncClicks(readFileSync(file, 'utf8'))
      if (discarded.length) found[relative(root, file)] = discarded
    }
    expect(found).toEqual({})
    const script = '<script setup>async function save () {}\nconst open = ref(false)</script>'
    expect(discardedAsyncClicks(`${script}<template><UiButton @click="open = false; save()" /></template>`)).toEqual(['save'])
    expect(discardedAsyncClicks(`${script}<template><UiButton @click="() => { save() }" /></template>`)).toEqual(['save'])
    expect(discardedAsyncClicks(`${script}<template><UiButton @click="save({ a: 1 })" /></template>`)).toEqual([])
  })

  it('a raiz está ligada: UiButton pendente por padrão, barra de rota, link marcado e quadro antes da troca', () => {
    const button = read('app/components/ui/Button.vue')
    expect(button).toContain('autoPending.value = true')
    expect(button).toMatch(/:aria-busy="busy \|\| undefined"/)
    expect(read('app/app.vue')).toContain('<NavigationFeedback />')
    const feedback = read('app/components/NavigationFeedback.vue')
    expect(feedback).toContain('markLink(link)')
    // A barra anda só por `transform` (o compositor a mantém viva em tarefa longa).
    expect(feedback).toContain('data-navigation-route-bar')
    expect(feedback).toMatch(/@keyframes navigation-route-bar \{\s*from \{ transform/)
    expect(read('app/plugins/navigationPaintsFirst.client.ts')).toContain('await nextPaint()')
    expect(read('app/assets/css/tailwind.css')).toContain('a[data-navigation-pending]')
  })

  it('as telas migradas passam pela capability', () => {
    for (const file of ['app/components/CartQuantityAction.vue', 'app/pages/sacola.vue', 'app/pages/finalizar.vue']) {
      expect(read(file), file).toContain('usePendingAction(')
    }
  })

  it('"Adicionar" nasce ativo e o toque antes da hidratação é guardado (D1)', () => {
    const action = read('app/components/CartQuantityAction.vue')
    // Nenhum `:disabled` do botão pode depender de hidratação.
    for (const binding of action.matchAll(/:disabled="([^"]*)"/g)) {
      expect(binding[1]).not.toMatch(/hydrated/)
    }
    expect(action).toContain(':data-early-tap="earlyTap"')
    expect(action).toContain('claimEarlyTap(earlyTapKey.value)')
    // O script vai inline no <head>, pelo nuxt.config (vale para toda página).
    const config = read('nuxt.config.ts')
    expect(config).toContain("import { EARLY_TAP_SCRIPT } from './app/utils/earlyTap'")
    expect(config).toMatch(/innerHTML: EARLY_TAP_SCRIPT, tagPosition: 'head'/)
  })
})
