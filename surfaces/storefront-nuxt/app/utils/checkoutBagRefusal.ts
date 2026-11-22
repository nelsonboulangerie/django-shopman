// Recusa do envio que fala da SACOLA, não do formulário (#3267).
//
// Entre a revisão e o envio a sacola pode ter saído (outra aba a enviou primeiro)
// ou sumido (outro aparelho enviou um pedido e a encerrou, a limpeza a apagou, a
// última linha foi tirada). A API responde 409 com `error_code` e a ação que
// resolve (`actions[0]`, link); a tela não adivinha caminho, segue o que veio.
// Antes, a frase do Core caía no toast genérico, sem saída.
import { safeInternalPath } from '~/utils/safeNavigation'

export type CheckoutBagRefusalKind = 'order_already_sent' | 'cart_empty'

export interface CheckoutBagRefusal {
  kind: CheckoutBagRefusalKind
  message: string
  /** Para onde a ação leva: o pedido que já saiu, ou o cardápio. */
  href: string
  actionLabel: string
}

const FALLBACK: Record<CheckoutBagRefusalKind, { message: string, href: string, actionLabel: string }> = {
  order_already_sent: { message: 'Este pedido já foi enviado.', href: '/conta/pedidos', actionLabel: 'Ver meus pedidos' },
  cart_empty: { message: 'Sua sacola ficou vazia antes do envio.', href: '/menu', actionLabel: 'Ver o cardápio' }
}

function firstLink (actions: unknown): { href: string, label: string } | null {
  if (!Array.isArray(actions)) return null
  for (const action of actions) {
    if (!action || typeof action !== 'object') continue
    const { kind, href, label } = action as Record<string, unknown>
    if (kind === 'link' && typeof href === 'string' && typeof label === 'string' && label.trim()) {
      return { href, label: label.trim() }
    }
  }
  return null
}

export function checkoutBagRefusal (data: unknown): CheckoutBagRefusal | null {
  if (!data || typeof data !== 'object') return null
  const body = data as Record<string, unknown>
  const kind = body.error_code
  if (kind !== 'order_already_sent' && kind !== 'cart_empty') return null
  const fallback = FALLBACK[kind]
  const message = typeof body.detail === 'string' && body.detail.trim() ? body.detail.trim() : fallback.message
  const link = firstLink(body.actions)
  const linkHref = link ? safeInternalPath(link.href, '') : ''
  if (link && linkHref) return { kind, message, href: linkHref, actionLabel: link.label }
  const nextUrl = kind === 'order_already_sent' ? safeInternalPath(body.next_url, '') : ''
  if (nextUrl) return { kind, message, href: nextUrl, actionLabel: 'Ver o pedido' }
  return { kind, message, href: fallback.href, actionLabel: fallback.actionLabel }
}
