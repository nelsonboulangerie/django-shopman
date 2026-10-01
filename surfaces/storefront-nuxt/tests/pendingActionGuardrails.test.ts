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

function inertAsyncClicks (source: string): string[] {
  const script = (source.match(/<script[^>]*>[\s\S]*?<\/script>/g) || []).join('\n')
  const asyncNames = new Set([
    ...[...script.matchAll(/async\s+function\s+(\w+)/g)].map(m => m[1]!),
    ...[...script.matchAll(/(?:const|let)\s+(\w+)\s*=\s*async\b/g)].map(m => m[1]!)
  ])
  const template = source.replace(/<script[\s\S]*?<\/script>/g, '')
  const inert = new Set<string>()
  for (const tag of openingTags(template)) {
    const click = tag.match(/@click(?:\.\w+)*="(?:void\s+)?(\w+)(?:\([^"]*\))?"/)
    if (!click || !asyncNames.has(click[1]!)) continue
    if (/\s:(?:loading|aria-busy|disabled)=/.test(tag)) continue
    inert.add(click[1]!)
  }
  return [...inert].sort()
}

// O que já existia sem pendente declarado em 01/10/2026. Só encolhe.
const KNOWN_INERT: Record<string, string[]> = {
  'app/components/AddressPicker.vue': ['acceptSuggestion', 'openMapAdjust', 'startManualEntry'],
  'app/components/PaymentBlock.vue': ['copyPix'],
  'app/components/PwaInstallInvite.vue': ['installNow'],
  'app/components/SearchOverlay.vue': ['loadMenu'],
  'app/components/WhatsappVerifyPanel.vue': ['copyMessage'],
  'app/pages/conta/seguranca.vue': ['removePasskey'],
  'app/pages/entrar.vue': ['revealSms', 'skipWelcome'],
  'app/pages/finalizar.vue': ['goToAuthRoute', 'startEditName'],
  'app/pages/menu.vue': ['refresh'],
  'app/pages/pedido/[ref]/index.vue': ['compartilhar', 'postAction']
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
    const mute = '<script setup>async function save () {}</script><template><UiButton @click="save">Salvar</UiButton></template>'
    const declared = '<script setup>async function save () {}</script><template><UiButton :loading="saving" @click="save">Salvar</UiButton></template>'
    const viaCapability = '<script setup>const { run: save, pending } = usePendingAction(() => $fetch("/x"))</script><template><UiButton @click="save" :loading="pending" /></template>'
    expect(inertAsyncClicks(mute)).toEqual(['save'])
    expect(inertAsyncClicks(declared)).toEqual([])
    expect(inertAsyncClicks(viaCapability)).toEqual([])
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
