// A ação na base no celular (`OperatorActionBar`, WP-FASE2-UX-OPERADOR K3).
//
// A ação é declarada como dados, no mesmo espírito do ⋯ único: rótulo com verbo e alvo
// ("Pronto para retirar", "Despachar M09"), nunca um "Confirmar" solto, e o motivo
// quando não pode.

export interface OperatorActionBarAction {
  /** Verbo e alvo: "Iniciar preparo", "Conferir o próximo". */
  label: string;
  icon?: string;
  to?: string;
  loading?: boolean;
  disabled?: boolean;
  /** Por que não pode agora (com `disabled`): aparece escrito sob a ação. */
  reason?: string;
  onSelect?: (event: Event) => void;
}
