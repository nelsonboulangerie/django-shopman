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
//
// A CSP da loja aceita script inline (`script-src 'unsafe-inline'`, ver
// server/utils/storefrontSecurity.ts); este é o mesmo caminho do JSON-LD e do tema.
// Nada aqui afrouxa a política.

export const EARLY_TAP_ATTR = 'data-early-tap'
export const EARLY_TAP_PENDING_ATTR = 'data-early-tap-pending'
export const EARLY_TAP_QUEUE = '__shopmanEarlyTaps'

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
  for (const el of document.querySelectorAll<HTMLElement>(`[${EARLY_TAP_PENDING_ATTR}]`)) {
    if (el.getAttribute(EARLY_TAP_ATTR) !== key) continue
    el.removeAttribute(EARLY_TAP_PENDING_ATTR)
    el.removeAttribute('aria-busy')
  }
  return index >= 0
}
