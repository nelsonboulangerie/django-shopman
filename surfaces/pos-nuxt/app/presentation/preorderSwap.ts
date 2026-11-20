// Presentation — trocar o item que falta na encomenda (#2765).
//
// O "Trocar por <produto>" do diálogo "Resolver" do Gestor abre o detalhe da
// encomenda em `?swap=<sku em falta>` (repetido quando falta mais de um item).
// O endereço leva só a INTENÇÃO: nome, preço, quantidade e alternativas vêm do
// servidor (`GET pos/preorders/<ref>/swap/`). Aqui fica a régua pura: ler os
// SKUs do endereço, a chave do próximo foco de cada item, o endereço sem o item
// já trocado e as frases da tela.
import type { PreorderSwapItem, PreorderSwapOption, PreorderSwapResponse } from "~/types/preorders";

/** Quantos SKUs o endereço pode pedir de uma vez (o servidor corta no mesmo número). */
export const MAX_SWAP_SKUS = 10;

/** Os SKUs de `?swap=`, sem vazios nem repetidos, na ordem do endereço. Nada de válido: `[]`. */
export function swapSkusFromQuery(raw: unknown): string[] {
  const values = Array.isArray(raw) ? raw : [raw];
  const out: string[] = [];
  for (const value of values) {
    if (typeof value !== "string") continue;
    const sku = value.trim();
    if (!sku || sku.length > 64 || out.includes(sku)) continue;
    out.push(sku);
    if (out.length >= MAX_SWAP_SKUS) break;
  }
  return out;
}

/** A chave do bloco de um item no próximo foco (`data-focus-target`). */
export function swapFocusKey(sku: string): string {
  return `swap:${sku}`;
}

/** O foco do momento: o primeiro item a trocar, ou nenhum. */
export function swapFocus(swap: PreorderSwapResponse | null): string | null {
  const first = swap?.items[0];
  return first ? swapFocusKey(first.sku) : null;
}

/** O endereço sem o item já trocado: o bloco dele some, e recarregar não oferece de novo. */
export function queryWithoutSwap<Q extends Record<string, unknown>>(query: Q, sku: string): Record<string, unknown> {
  const rest = swapSkusFromQuery(query.swap).filter((value) => value !== sku);
  const { swap: _swap, ...others } = query;
  return rest.length ? { ...others, swap: rest } : others;
}

/** O título do bloco de um item: o que sai, na quantidade da linha. */
export function swapItemTitle(item: PreorderSwapItem): string {
  return `Trocar ${item.qty_label}`;
}

/** O aviso de quem não conseguiu procurar: nunca afirma que não há. */
export function swapUnsearchedTitle(items: PreorderSwapItem[]): string {
  const names = items.filter((item) => !item.searched).map((item) => item.name);
  if (names.length === 1) return `Não deu para procurar agora o que trocar por ${names[0]}.`;
  return "Não deu para procurar agora as alternativas da troca.";
}

export const SWAP_LOAD_FAILED = "Não deu para ler as alternativas da troca.";
export const SWAP_RETRY = "Procurar de novo";

/** A pergunta da caixa de conferência: o que sai e o que entra. */
export function swapConfirmTitle(item: PreorderSwapItem, option: PreorderSwapOption): string {
  return `Trocar ${item.name} por ${option.name}?`;
}

/** A frase do toast depois da troca: o que entrou no lugar de quê. */
export function swapDoneMessage(item: PreorderSwapItem, option: PreorderSwapOption): string {
  return `Trocado: ${option.qty_label} no lugar de ${item.qty_label}.`;
}
