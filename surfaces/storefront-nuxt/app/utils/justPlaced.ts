// Momento yoin: quem sabe que o pedido ACABOU de ser fechado é este navegador,
// não o servidor. O checkout marca; o acompanhamento consome UMA vez, quando o
// servidor diz que o pedido já pode ser comemorado (`placement_secured`: não
// deve pagamento e não morreu). Fica na aba (sessionStorage): sobrevive à ida
// ao Stripe e à volta, não vai na URL (link compartilhado não comemora o pedido
// de outra pessoa) e não repete no refresh.
const STORAGE_KEY = 'shopman-just-placed'

export function markJustPlaced (orderRef: string): void {
  if (!orderRef) return
  try { window.sessionStorage.setItem(STORAGE_KEY, orderRef) } catch { /* storage negado: sem confete */ }
}

export function takeJustPlaced (orderRef: string): boolean {
  if (!orderRef) return false
  try {
    if (window.sessionStorage.getItem(STORAGE_KEY) !== orderRef) return false
    window.sessionStorage.removeItem(STORAGE_KEY)
    return true
  } catch {
    return false
  }
}
