import type { Action, CartOpenElsewhere, CartProjection } from '~/types/shopman'

// A sacola entre a loja e a conversa com a Nice (OC-16, #3515, #3517). Transforms
// puros: a tela só mostra o que o servidor disse que é possível (X1). Nenhuma regra
// de passagem mora aqui; o serviço decide e a projeção diz.

export interface OpenElsewhereNotice {
  channel: string
  // "Você tem outra sacola no WhatsApp: 3 itens (R$ 2,70)."
  text: string
  // O que acontece ao trazer, dito antes do toque (só com a ação ligada).
  consequence: string
  bring: Action | null
}

export function openElsewhereNotices (cart: Pick<CartProjection, 'open_elsewhere'>): OpenElsewhereNotice[] {
  return (cart.open_elsewhere || []).map((entry: CartOpenElsewhere) => {
    const bring = entry.bring?.enabled ? entry.bring : null
    return {
      channel: entry.channel,
      text: `Você tem outra sacola no ${entry.channel_label}: ${entry.items_phrase} (${entry.subtotal_display}).`,
      consequence: bring
        ? `Ao trazer, ela sai do ${entry.channel_label}.`
        : 'Ela fica lá, separada desta.',
      bring
    }
  })
}

// "Continuar pelo WhatsApp" só com a ação ligada pelo servidor.
export function continueInConversationAction (cart: Pick<CartProjection, 'continue_in_conversation' | 'is_empty'>): Action | null {
  if (cart.is_empty) return null
  const action = cart.continue_in_conversation
  return action && action.enabled ? action : null
}

export const CONTINUE_IN_CONVERSATION_HINT = 'Ao enviar a mensagem pronta, a sacola passa para a conversa com a Nice.'
export const CONTINUE_IN_CONVERSATION_SENT = 'Envie a mensagem no WhatsApp. Até lá, a sacola fica aqui.'
export const PASSAGE_FALLBACK_ERROR = 'Não foi possível agora. Suas sacolas continuam como estavam.'

// A frase da recusa que o servidor mandou, ou a genérica que não promete nada.
export function passageErrorMessage (error: unknown): string {
  const data = (error as { data?: { detail?: unknown } } | null)?.data
  const detail = typeof data?.detail === 'string' ? data.detail.trim() : ''
  return detail || PASSAGE_FALLBACK_ERROR
}
