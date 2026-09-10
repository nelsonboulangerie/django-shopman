// Lógica pura do bloco de pagamento inline. Depois da fusão
// PAYMENT-TRACKING-MERGE a tela de pagamento deixou de existir: o Pix/cartão
// viraram um degrau do próprio acompanhamento, então o estado, o poll e o
// countdown vivem na página de acompanhamento (o promise carrega tudo).
//
// O rótulo do método NÃO mora mais aqui: o de-para vivia duplicado no cliente e
// o operador que renomeasse "Cartão" no Admin via o checkout obedecer e o
// acompanhamento não — dois nomes para o mesmo pedido. Agora vem pronto em
// `promise.payment_method_label`.

// Sessão HOSPEDADA: o cliente abre a URL do gateway e paga lá. O cartão da loja
// online e o link do balcão (pedido remoto anotado no PDV) são a mesma coisa
// para esta tela — muda o rótulo, não o botão. Enquanto só `card` contava, o
// pedido de link chegava com `checkout_url` e a página não desenhava nada.
export function isHostedCheckout (method: string | null | undefined): boolean {
  return method === 'card' || method === 'link'
}

// O que o bloco de pagamento precisa saber para decidir o que desenhar.
// Recorte mínimo do tracking — as funções abaixo são puras e testáveis.
export interface PaymentBlockState {
  payment_method: string | null | undefined
  pix_qr_code?: string | null
  pix_copy_paste?: string | null
  checkout_url?: string | null
  // Decidido pelo backend por PEDIDO (ambiente de teste + intent capturável),
  // não só "estamos em DEBUG".
  mock_payment_enabled?: boolean
}

function hasPixCode (s: PaymentBlockState): boolean {
  return Boolean(s.pix_qr_code || s.pix_copy_paste)
}

// Dá para pagar DE VERDADE agora? Pix com código na mão, ou o link do gateway
// do cartão. É isto que decide os botões que o cliente usa em produção.
export function canPayForReal (s: PaymentBlockState): boolean {
  if (s.payment_method === 'pix') return hasPixCode(s)
  if (isHostedCheckout(s.payment_method)) return Boolean(s.checkout_url)
  return false
}

// A captura simulada substitui o passo EXTERNO: no Pix, o app do banco; no
// cartão, a página do gateway. Quem decide se ela cabe NESTE pedido é o
// backend — `mock_payment_enabled` já exige ambiente de teste, intent vivo e
// status ainda capturável. A tela só obedece; recalcular aqui seria um
// segundo dono da mesma pergunta.
export function canSimulatePayment (s: PaymentBlockState): boolean {
  return Boolean(s.mock_payment_enabled)
}

// O bloco inteiro aparece? Uma pergunta, um dono — a página e o componente
// leem daqui. Enquanto cada um tinha a sua fórmula, o cartão sem link do
// gateway caía fora do bloco na página E fora da caixa de teste no componente.
export function showsPaymentBlock (s: PaymentBlockState): boolean {
  if (s.payment_method === 'pix') return true
  if (!isHostedCheckout(s.payment_method)) return false
  // Sessão hospedada: a URL real do gateway, ou a captura simulada. Com o
  // `payment_mock` não existe checkout_url — sem o segundo braço o testador
  // não via nada.
  return Boolean(s.checkout_url) || canSimulatePayment(s)
}
