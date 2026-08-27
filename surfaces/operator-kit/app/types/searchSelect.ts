// Contrato do campo de busca com seleção (SearchSelect) — genérico, sem domínio.
// O app hospedeiro traduz o que ele tem (insumo, operador, canal) para esta forma
// e recebe de volta o `value` escolhido.
//
// Chaves em inglês (value/label/hint), textos em pt-BR — convenção do projeto.

export interface SearchSelectOption {
  /** Identidade que volta no `update:modelValue` — SKU, ref, id. */
  value: string;
  /** Texto principal: o que o operador lê na lista e o que ele busca. */
  label: string;
  /**
   * Texto secundário, mostrado sob o rótulo e TAMBÉM buscável. É onde vive o
   * identificador que o operador conhece de cor (o SKU do insumo, por exemplo):
   * quem digita o código acha tão rápido quanto quem digita o nome.
   */
  hint?: string;
}
