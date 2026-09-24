// Contrato das escolhas do operador — o que é comum a `UiRadioGroup` e a `UiSelect`.
//
// Chaves em inglês, rótulo em pt-BR: a convenção do projeto. O `value` aceita
// boolean porque escolha exclusiva de duas pontas existe de verdade no Marketing
// (`useSaved` do disparo: o público salvo ou a escolha avulsa), e forçar aquilo a
// virar string só para caber num tipo seria o app se contorcendo para o primitivo.

/** Valor de uma escolha. Comparado por identidade (`===`), nunca por conteúdo. */
export type ChoiceValue = string | number | boolean | null;

export interface ChoiceOption<T extends ChoiceValue = ChoiceValue> {
  value: T;
  /** Rótulo visível, em pt-BR. */
  label: string;
  /** Segunda linha — o detalhe que desempata duas opções parecidas. */
  hint?: string;
  /**
   * Texto extra que a BUSCA considera mas a tela não mostra. Serve para o que o
   * operador digita e o rótulo não contém: o `ref` do modelo aprovado, o nome
   * antigo de uma coleção, a sigla do canal.
   */
  keywords?: string;
  disabled?: boolean;
}
