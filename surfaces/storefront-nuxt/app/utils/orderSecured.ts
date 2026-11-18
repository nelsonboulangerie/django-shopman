// "Nesta visita, um pedido já foi enviado e pode ser comemorado." É o que libera os
// convites da loja (instalar o app e avisos pelo WhatsApp). Decisão do dono de
// 16/11/2026 (excelência da loja, decisão 3): convite só depois do pedido enviado.
// A cliente que volta percorre produto, sacola e checkout sem convite nenhum; o
// primeiro convite possível vem depois do pedido.
//
// "Enviado" é o mesmo instante do momento yoin: o servidor diz que o pedido já pode
// ser comemorado (`placement_secured`: não deve pagamento e não morreu), e quem
// consome a marca do checkout é o acompanhamento (`takeJustPlaced`). Fica no
// sessionStorage porque vale para esta visita, não para as próximas: o pedido da
// semana passada não abre convite hoje.
const STORAGE_KEY = 'shopman-order-secured'

export function rememberOrderSecured (): void {
  try { window.sessionStorage.setItem(STORAGE_KEY, '1') } catch { /* storage negado: sem convite nesta visita */ }
}

export function orderSecuredThisVisit (): boolean {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}
