// Conferência do pedido incerto (laudo 23/10, U6).
//
// Quando o envio do checkout fica sem resposta (rede caiu, 5xx, prazo do BFF), a
// tela não sabe se o pedido entrou. A tentativa (Idempotency-Key) é a mesma, então
// o `checkout/recover/` responde o pedido assim que o Django o tiver confirmado.
// Antes, a tela perguntava UMA vez e prometia "se resolve sozinha": se o Django
// ainda estava gravando, o cliente ficava num aviso que nunca mudava.
//
// Aqui a pergunta se repete com espera crescente até achar o pedido ou até o
// teto. No teto, a tela para de prometer e devolve a decisão ao cliente, com a
// verdade: o reenvio usa a mesma tentativa, e o mesmo pedido não entra duas vezes.

/** Esperas entre as conferências: ~1min30 no total, a maior parte no começo. */
export const CHECKOUT_RECOVERY_DELAYS_MS = [2_000, 4_000, 8_000, 15_000, 30_000, 30_000] as const

export interface CheckoutRecoveryLoop {
  /** Interrompe as conferências que faltam (o cliente reenviou, saiu da tela). */
  cancel(): void
  /** Resolve `true` quando achou o pedido; `false` no teto ou se cancelado. */
  done: Promise<boolean>
}

export function startCheckoutRecovery (
  attempt: () => Promise<boolean>,
  delays: readonly number[] = CHECKOUT_RECOVERY_DELAYS_MS,
  wait: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms))
): CheckoutRecoveryLoop {
  let cancelled = false
  const done = (async () => {
    for (const delay of delays) {
      await wait(delay)
      if (cancelled) return false
      let found: boolean
      try {
        found = await attempt()
      } catch {
        found = false
      }
      if (cancelled) return false
      if (found) return true
    }
    return false
  })()
  return {
    cancel () { cancelled = true },
    done
  }
}
