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

/** O que o `OperatorReasonDialog` entrega: o texto que o cliente lê e o código, se houver. */
export interface ReasonChoice {
  reason: string;
  code: string;
}
