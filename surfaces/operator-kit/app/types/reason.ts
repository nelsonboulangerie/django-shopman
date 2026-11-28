/**
 * Motivo da lista única do backend (recusar e cancelar pedido): a chave estável que
 * volta ao servidor, o rótulo que o operador escolhe e a frase revisada que o cliente lê.
 */
export interface KeyedReason {
  key: string;
  label: string;
  customer_text: string;
}

/**
 * O que o `OperatorReasonDialog` entrega. Com motivos da lista (`keyedReasons`),
 * `key` é a chave escolhida e `reason` é a observação interna (nunca vai ao
 * cliente). Sem lista, `reason` é o texto escrito e `key` sai vazio.
 */
export interface ReasonChoice {
  reason: string;
  key: string;
}
