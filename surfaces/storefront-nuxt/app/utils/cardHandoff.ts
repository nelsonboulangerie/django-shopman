// Cartão em um toque (plano EXCELENCIA-STOREFRONT, P2-09).
//
// Quem pagou com cartão tocava em "Enviar pedido", caía no acompanhamento e só ali
// achava "Pagar com cartão": dois toques para uma decisão que ela já tinha tomado na
// revisão. O checkout marca o pedido recém-enviado com cartão; o acompanhamento consome
// a marca UMA vez, quando o link de pagamento chega, e leva a cliente direto ao ambiente
// seguro. A volta do pagamento cai no mesmo acompanhamento, já sem a marca.
//
// Fica na aba (sessionStorage) e vence em poucos minutos: link compartilhado, recarga
// tardia ou outra aba nunca redirecionam ninguém sozinhos.
const STORAGE_KEY = 'shopman-card-handoff'
const MAX_AGE_MS = 3 * 60_000

export function markCardHandoff (orderRef: string, now: number = Date.now()): void {
  if (!orderRef) return
  try { window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ref: orderRef, at: now })) } catch { /* storage negado: fica o botão */ }
}

export function takeCardHandoff (orderRef: string, now: number = Date.now()): boolean {
  if (!orderRef) return false
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return false
    const mark = JSON.parse(raw) as { ref?: unknown, at?: unknown }
    if (mark.ref !== orderRef) return false
    window.sessionStorage.removeItem(STORAGE_KEY)
    return typeof mark.at === 'number' && now - mark.at >= 0 && now - mark.at <= MAX_AGE_MS
  } catch {
    return false
  }
}
