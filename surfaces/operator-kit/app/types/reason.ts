/** Motivos prontos da casa, cadastrados no Admin e agrupados pelo cabeçalho da casa. */
export interface ReasonPresetGroup {
  label: string;
  presets: string[];
}

/** Motivo codificado de um marketplace (o iFood exige um dos códigos dele). */
export interface CodedReason {
  code: string;
  description: string;
}

/**
 * Motivo da lista única do backend (cancelar pedido): a chave estável que volta ao
 * servidor, o rótulo que o operador escolhe e a frase revisada que o cliente lê.
 */
export interface KeyedReason {
  key: string;
  label: string;
  customer_text: string;
}

/**
 * O que o `OperatorReasonDialog` entrega. Com motivos da lista (`keyedReasons`),
 * `key` é a chave escolhida e `reason` é a observação interna (nunca vai ao
 * cliente). Nas outras formas, `reason` é o texto que o cliente lê, `code` o
 * código do marketplace e `key` sai vazio.
 */
export interface ReasonChoice {
  reason: string;
  code: string;
  key: string;
}
