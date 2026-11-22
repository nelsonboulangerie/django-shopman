// Toque antes da hidratação: guardado e repetido, nunca perdido (D1, opção 3).
//
// O HTML do servidor chega antes do JavaScript. Em celular lento há segundos em que
// o botão "Adicionar" já está na tela e ainda não tem ouvinte: o toque some sem
// rastro e só o segundo funciona. Desabilitar o botão até hidratar era pior: ele
// nascia esmaecido, com a mesma cara de "Indisponível", e o cardápio inteiro parecia
// fora de venda.
//
// O contrato agora:
//
// 1. O botão nasce ATIVO e marcado com `data-early-tap="<chave>"` enquanto o
//    componente não montou (produto indisponível não ganha a marca: segue com o
//    `disabled` dele).
// 2. `EARLY_TAP_SCRIPT` roda inline no <head>, antes de o corpo existir. Ele ouve
//    cliques na fase de captura do document e, se o alvo é um elemento marcado,
//    guarda a chave numa fila (sem repetir: dois toques viram um pedido) e marca o
//    botão com `data-early-tap-pending`, que o CSS desenha como girando. O toque
//    tem resposta visual no mesmo quadro, sem esperar o app.
// 3. Ao montar, o componente chama `claimEarlyTap(chave)`: se a chave está na fila,
//    ela sai (uma vez só, mesmo que o produto apareça em duas vitrines) e a ação
//    real é executada. A marca de pendente sai junto; a partir daí quem diz
//    "em andamento" é o próprio componente.
// 4. Montado, o componente tira o `data-early-tap` do botão, e o script inline passa
//    a ignorá-lo: o clique segue para o ouvinte do Vue normalmente.
// 5. A fila também vai para o `sessionStorage` da aba (#3171, F-18). Em memória, ela
//    morria com a página: a cliente tocava em Adicionar antes de a página hidratar e
//    abria a Sacola (um `<a>` comum até o app montar) ou recarregava. A página nova
//    nascia sem a fila, e o item sumia. Agora o toque sobrevive à troca de página na
//    mesma aba: o botão que monta o reclama (`claimEarlyTap`, memória OU aba), e o que
//    nenhum botão reclamou o app executa ao montar (`plugins/earlyTapReplay.client.ts`,
//    via `takeOrphanEarlyTaps`). Uma vez só: quem pega o toque o tira dos dois lugares.
//
// A CSP da loja aceita script inline (`script-src 'unsafe-inline'`, ver
// server/utils/storefrontSecurity.ts); este é o mesmo caminho do JSON-LD e do tema.
// Nada aqui afrouxa a política.

export const EARLY_TAP_ATTR = 'data-early-tap'
export const EARLY_TAP_PENDING_ATTR = 'data-early-tap-pending'
export const EARLY_TAP_QUEUE = '__shopmanEarlyTaps'
/** O nome do produto, para o app repetir o toque fora da página do botão. */
export const EARLY_TAP_NAME_ATTR = 'data-early-tap-name'
/** A fila na aba: `[{k: chave, n: nome}]`. */
export const EARLY_TAP_STORE = 'shopman:early-taps'

// ES5 de propósito: roda antes de qualquer polyfill e em navegador velho. Não usa
// nada do bundle. Testado executando o próprio texto (tests/earlyTap.test.ts).
export const EARLY_TAP_SCRIPT = [
  '(function(w,d){',
  `if(w.${EARLY_TAP_QUEUE})return;`,
  `var q=w.${EARLY_TAP_QUEUE}=[];`,
  'd.addEventListener("click",function(e){',
  'var t=e.target;',
  `var el=t&&t.closest?t.closest("[${EARLY_TAP_ATTR}]"):null;`,
  'if(!el||el.disabled)return;',
  'e.preventDefault();e.stopPropagation();',
  `var k=el.getAttribute("${EARLY_TAP_ATTR}");`,
  'if(k&&q.indexOf(k)<0)q.push(k);',
  // Na aba também, para sobreviver à troca de página. Armazenamento bloqueado só tira
  // essa garantia; o toque na mesma página segue valendo.
  `try{var s=w.sessionStorage,a=JSON.parse(s.getItem("${EARLY_TAP_STORE}")||"[]"),i,f=false;`,
  'for(i=0;i<a.length;i++){if(a[i]&&a[i].k===k)f=true;}',
  `if(k&&!f){a.push({k:k,n:el.getAttribute("${EARLY_TAP_NAME_ATTR}")||""});s.setItem("${EARLY_TAP_STORE}",JSON.stringify(a));}`,
  '}catch(x){}',
  `el.setAttribute("${EARLY_TAP_PENDING_ATTR}","true");`,
  'el.setAttribute("aria-busy","true");',
  '},true);',
  '})(window,document);'
].join('')

type EarlyTapWindow = Window & { [EARLY_TAP_QUEUE]?: string[] }

/**
 * Retira `key` da fila de toques precoces. Devolve `true` uma vez só por toque
 * guardado: quem recebe `true` executa a ação. Limpa a marca visual de pendente
 * de todo botão com a mesma chave.
 */
export function claimEarlyTap (key: string): boolean {
  if (!import.meta.client) return false
  const win = window as EarlyTapWindow
  const queue = win[EARLY_TAP_QUEUE]
  const index = queue ? queue.indexOf(key) : -1
  if (queue && index >= 0) queue.splice(index, 1)
  // O toque guardado na aba, de uma página anterior (recarregar com o mesmo botão).
  const stored = storedTaps()
  const inStore = stored.some(tap => tap.key === key)
  if (inStore) saveStoredTaps(stored.filter(tap => tap.key !== key))
  clearPendingMark(key)
  return index >= 0 || inStore
}

export interface EarlyTap {
  key: string
  name: string
}

/**
 * O Adicionar do app hidratado também passa pela aba enquanto a escrita está em voo
 * (#3171): a cliente que toca e sai da página no mesmo instante (recarrega, ou o link
 * da Sacola numa troca dura) cancela a requisição no navegador, e a página nova executa
 * o que ficou. `forgetEarlyTap` quando a escrita termina, com sucesso ou erro: o erro
 * já tem aviso próprio, e repetir não o resolveria.
 */
export function rememberEarlyTap (key: string, name: string): void {
  if (!import.meta.client) return
  const taps = storedTaps().filter(tap => tap.key !== key)
  saveStoredTaps([...taps, { key, name }])
}

export function forgetEarlyTap (key: string): void {
  if (!import.meta.client) return
  const taps = storedTaps()
  if (taps.some(tap => tap.key === key)) saveStoredTaps(taps.filter(tap => tap.key !== key))
}

/**
 * Os toques que nenhum botão reclamou: os da aba (de uma página que a cliente deixou
 * antes de hidratar) e os da memória sem botão montado. Saem dos dois lugares; quem
 * recebe executa. O app chama depois de montar, quando cada botão já reclamou o seu.
 */
export function takeOrphanEarlyTaps (): EarlyTap[] {
  if (!import.meta.client) return []
  const queue = (window as EarlyTapWindow)[EARLY_TAP_QUEUE]
  const taps = storedTaps()
  for (const key of queue ?? []) {
    if (!taps.some(tap => tap.key === key)) taps.push({ key, name: '' })
  }
  if (queue) queue.length = 0
  saveStoredTaps([])
  for (const tap of taps) clearPendingMark(tap.key)
  return taps
}

/** `cart-add:<sku>:<qtd>`, a chave do Adicionar (CartQuantityAction). */
export function parseCartAddKey (key: string): { sku: string, qty: number } | null {
  const match = /^cart-add:(.+):(\d+)$/.exec(key)
  if (!match) return null
  const qty = Number(match[2])
  return qty > 0 ? { sku: match[1]!, qty } : null
}

function clearPendingMark (key: string): void {
  for (const el of document.querySelectorAll<HTMLElement>(`[${EARLY_TAP_PENDING_ATTR}]`)) {
    if (el.getAttribute(EARLY_TAP_ATTR) !== key) continue
    el.removeAttribute(EARLY_TAP_PENDING_ATTR)
    el.removeAttribute('aria-busy')
  }
}

function storedTaps (): EarlyTap[] {
  try {
    const raw = JSON.parse(window.sessionStorage.getItem(EARLY_TAP_STORE) || '[]') as unknown
    if (!Array.isArray(raw)) return []
    return raw
      .filter((tap): tap is { k: string, n?: unknown } => !!tap && typeof (tap as { k?: unknown }).k === 'string')
      .map(tap => ({ key: tap.k, name: typeof tap.n === 'string' ? tap.n : '' }))
  } catch {
    return []
  }
}

function saveStoredTaps (taps: EarlyTap[]): void {
  try {
    if (taps.length) window.sessionStorage.setItem(EARLY_TAP_STORE, JSON.stringify(taps.map(tap => ({ k: tap.key, n: tap.name }))))
    else window.sessionStorage.removeItem(EARLY_TAP_STORE)
  } catch {
    // Armazenamento bloqueado: a garantia entre páginas some, a da página fica.
  }
}
