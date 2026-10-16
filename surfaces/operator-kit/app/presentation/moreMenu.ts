// O ⋯ "Mais ações", um só para a suíte (WP-FASE2-UX-OPERADOR, A14 e D9).
//
// Antes dele, a mesma atividade tinha uma peça por lugar: o ⋯ do cabeçalho, o da fila
// (`outline`), o do catálogo (`outline`), o da linha da tabela (`ellipsis-vertical`), o do
// quadro de leitura, cada um com o seu botão e o seu menu. Agora a tela declara as ações
// como DADOS e a peça (`OperatorMoreMenu`) desenha o mesmo ⋯ no celular e na mesa.
//
// O formato é o do item do `NuxtDropdownMenu` (grupos são listas de listas; o rótulo de um
// grupo é um item `type: "label"`), com uma coisa a mais: `reason`, o motivo de uma ação
// desabilitada. Ele aparece escrito embaixo do rótulo, porque no toque não há dica de
// ponteiro: ação apagada sem motivo é pergunta sem resposta.
//
// Funções puras: o componente só desenha o que elas decidem, e os testes travam a regra
// sem montar nada.
import type { DropdownMenuItem } from "@nuxt/ui";

/** Um item do ⋯. O formato do `NuxtDropdownMenu`, mais o motivo de quando não pode. */
export interface OperatorMoreMenuItem extends DropdownMenuItem {
  /**
   * Por que a ação não pode agora. Só vale com `disabled`: aparece escrito sob o rótulo
   * (o toque não tem dica de ponteiro). Ação desabilitada por regra do negócio leva
   * motivo; a desabilitada só enquanto um pedido anda (`busy`) dispensa.
   */
  reason?: string;
}

/** Lista simples ou lista de grupos, como no `NuxtDropdownMenu`. */
export type OperatorMoreMenuItems =
  | readonly OperatorMoreMenuItem[]
  | readonly (readonly OperatorMoreMenuItem[])[];

/** Chaves que são do kit e não chegam ao item do `NuxtDropdownMenu`. */
const KIT_KEYS = ["reason", "priority", "search"] as const;

function isGrouped(
  items: OperatorMoreMenuItems,
): items is readonly (readonly OperatorMoreMenuItem[])[] {
  return items.length > 0 && items.every((entry) => Array.isArray(entry));
}

/** Um item pronto para o `NuxtDropdownMenu`: o motivo vira a descrição do item. */
export function moreMenuItem(item: OperatorMoreMenuItem): DropdownMenuItem {
  const out: Record<string, unknown> = { ...item };
  for (const key of KIT_KEYS) delete out[key];
  if (item.disabled && item.reason && !item.description) out.description = item.reason;
  return out as DropdownMenuItem;
}

/** O item mostra alguma coisa: uma ação, ou um rótulo desenhado por slot (a leitura da fila). */
function showsSomething(item: DropdownMenuItem): boolean {
  if (item.type === "separator") return false;
  if (item.type === "label") return Boolean(item.slot);
  return true;
}

/**
 * Os grupos do ⋯, prontos para o `NuxtDropdownMenu`: sempre lista de listas, sem grupo
 * vazio (nem grupo que só tem o rótulo), e o motivo escrito em cada ação que não pode.
 */
export function moreMenuGroups(items: OperatorMoreMenuItems): DropdownMenuItem[][] {
  const groups = isGrouped(items) ? items : [items as readonly OperatorMoreMenuItem[]];
  return groups.map((group) => group.map(moreMenuItem)).filter((group) => group.some(showsSomething));
}

/** Quantas ações o ⋯ guarda (rótulos de grupo e separadores não contam). */
export function moreMenuActionCount(items: OperatorMoreMenuItems): number {
  return moreMenuGroups(items).reduce(
    (total, group) =>
      total + group.filter((item) => item.type !== "label" && item.type !== "separator").length,
    0,
  );
}
