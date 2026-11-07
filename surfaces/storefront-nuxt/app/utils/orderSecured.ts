// "Este navegador já fechou um pedido de verdade." É o que libera o convite de
// instalar o app: oferecer instalação antes de a pessoa conhecer a loja é pedir
// compromisso a quem ainda está olhando a vitrine (beta 05/11). O padrão de
// mercado é convidar depois do primeiro pedido concluído.
//
// "Concluído" é o mesmo instante do momento yoin: o servidor diz que o pedido já
// pode ser comemorado (`placement_secured`: não deve pagamento e não morreu), e
// quem consome a marca do checkout é o acompanhamento (`takeJustPlaced`). Fica no
// localStorage porque vale para as próximas visitas, não só para esta aba.
const STORAGE_KEY = 'shopman-order-secured'

export function rememberOrderSecured (): void {
  try { window.localStorage.setItem(STORAGE_KEY, '1') } catch { /* storage negado: o convite espera a próxima visita */ }
}

export function hasSecuredOrder (): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}
