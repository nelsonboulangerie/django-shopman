// A barra de seleção da suíte (`OperatorBulkBar`, WP-FASE2-UX-OPERADOR K2).
//
// Decisão do dono (09/10/2026): na mesa ela OCUPA O LUGAR DA TOOLBAR enquanto houver
// marcados e diz em que recorte a seleção foi feita (mudar o recorte com marcados fora
// da vista seria agir no que não se vê); no celular ela é a ação na base. As ações são
// dados: pares de gestos opostos (Pausar/Ativar, Ocultar/Exibir) vão num grupo só, com o
// MESMO peso visual (dono, 09/10/2026, Catálogo do Gestor).
//
// Funções puras: o componente só desenha o que elas decidem.

export interface OperatorBulkAction {
  /** Verbo e, quando couber, quantos: "Pausar", "Aceitar 3". */
  label: string;
  icon?: string;
  disabled?: boolean;
  /** Por que não pode (com `disabled`): vira a dica e o nome acessível. */
  reason?: string;
  loading?: boolean;
  /** A ação principal da barra (uma só): `primary` `solid`. As outras, `outline`. */
  primary?: boolean;
  onSelect?: (event: Event) => void;
  /**
   * A ação abre um painel em vez de agir (o "Preço…" do Catálogo): o nome do slot com
   * o conteúdo. O painel é o `NuxtPopover` da barra, com `open` controlado pela tela.
   */
  panel?: string;
  open?: boolean;
  onUpdateOpen?: (open: boolean) => void;
  /** Atributo `data-*` para teste e captura. */
  testId?: string;
}

/** Uma ação sozinha, ou um par (ou trio) de gestos opostos num grupo de botões. */
export type OperatorBulkItem = OperatorBulkAction | OperatorBulkAction[];

/** "1 selecionado", "3 selecionados". */
export function bulkCountLabel(count: number): string {
  return count === 1 ? "1 selecionado" : `${count} selecionados`;
}

/**
 * A frase da barra: quantos, e em que recorte ("3 selecionados em Rústicos"). Sem
 * marcados (o modo de seleção ligado, ainda vazio), a instrução da tela.
 */
export function bulkSelectionLabel(count: number, scope = "", empty = ""): string {
  if (count <= 0) return empty || "Nenhum selecionado";
  const where = scope.trim();
  return where ? `${bulkCountLabel(count)} em ${where}` : bulkCountLabel(count);
}

/** O nome acessível de uma ação que não pode: o rótulo e o motivo. */
export function bulkActionTitle(action: OperatorBulkAction): string | undefined {
  return action.disabled && action.reason ? `${action.label}: ${action.reason}` : undefined;
}

/** Normaliza para grupos: a ação sozinha vira um grupo de um. */
export function bulkGroups(items: readonly OperatorBulkItem[]): OperatorBulkAction[][] {
  return items
    .map((item) => (Array.isArray(item) ? item : [item]))
    .filter((group) => group.length > 0);
}

export const BULK_CLEAR_LABEL = "Limpar seleção";
