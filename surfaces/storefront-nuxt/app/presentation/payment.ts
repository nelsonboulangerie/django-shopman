// Lógica pura do bloco de pagamento inline. Depois da fusão
// PAYMENT-TRACKING-MERGE a tela de pagamento deixou de existir: o Pix/cartão
// viraram um degrau do próprio acompanhamento, então o estado, o poll e o
// countdown vivem na página de acompanhamento (o promise carrega tudo). O que
// sobra aqui é o rótulo acolhedor do método.

// Rótulo acolhedor do método (omotenashi) em vez do enum cru "pix"/"card".
export function paymentMethodLabel (method: string | null | undefined): string {
  if (method === 'pix') return 'Pix'
  if (method === 'card') return 'Cartão de crédito'
  return 'Pagamento'
}
