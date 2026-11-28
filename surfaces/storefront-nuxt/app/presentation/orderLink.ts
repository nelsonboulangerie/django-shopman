// O link do aviso (DEV-2026-093): `/pedido/<ref>~<selo>`. O selo é a capacidade
// DESTE pedido, calculada pelo servidor (`shop/services/order_view_link.py`): a
// página troca o selo pelo acesso a este pedido ANTES de ler o acompanhamento, e
// tira o selo da barra de endereço. Não loga ninguém; quem decide o que a tela
// mostra e permite é a projection do servidor (`access_mode`, `login_invite`).

export const ORDER_LINK_SEPARATOR = '~'

export interface OrderLinkParam {
  ref: string
  capability: string
}

/** `"<ref>~<selo>"` → `{ ref, capability }`; sem selo, `capability` vazio. */
export function splitOrderLinkParam (param: string | null | undefined): OrderLinkParam {
  const value = String(param || '').trim()
  const at = value.lastIndexOf(ORDER_LINK_SEPARATOR)
  if (at < 0) return { ref: value, capability: '' }
  return { ref: value.slice(0, at), capability: value.slice(at + 1) }
}

/** O endereço limpo do pedido, sem o selo. */
export function cleanOrderPath (ref: string): string {
  return `/pedido/${encodeURIComponent(ref)}`
}

export interface OpenOrderLinkDeps {
  /** POST `/api/v1/tracking/<ref>/access/` `{ cap }`; rejeita quando o selo não vale. */
  exchange: (ref: string, capability: string) => Promise<unknown>
  /** Troca a URL da barra sem empilhar histórico (o `router.replace`). */
  replace: (path: string) => Promise<unknown> | unknown
}

export interface OpenOrderLinkResult {
  ref: string
  arrivedWithCapability: boolean
  exchanged: boolean
}

/**
 * Chegou pelo link do aviso: troca o selo e deixa a URL limpa.
 *
 * O selo some da barra mesmo quando a troca falha (selo vencido, revogado): ele não
 * serve mais, e ficar no histórico ou num print não ajuda ninguém. A leitura do
 * pedido vem depois, e é ela que diz se a tela abre (o cliente pode ter sessão).
 */
export async function openOrderLink (param: string, deps: OpenOrderLinkDeps): Promise<OpenOrderLinkResult> {
  const { ref, capability } = splitOrderLinkParam(param)
  if (!capability) return { ref, arrivedWithCapability: false, exchanged: false }
  const exchanged = await deps.exchange(ref, capability).then(() => true, () => false)
  await deps.replace(cleanOrderPath(ref))
  return { ref, arrivedWithCapability: true, exchanged }
}
