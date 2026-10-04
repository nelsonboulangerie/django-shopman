// O gesto de deslizar do celular (G16/G17, prévias v3 `depois-gestor-celular` e v4
// `cozinha-celular`): a linha acompanha o dedo, presa à direção do gesto e a um limite,
// e só vale quando passa do ponto de compromisso. Puro: testado em `tests/swipe.test.ts`.

/** Quanto o dedo precisa andar para o gesto valer (soltar antes devolve a linha). */
export const SWIPE_COMMIT_PX = 96;
/** Largura das ações que o deslize para a esquerda revela (Atender · Recusar). */
export const SWIPE_REVEAL_PX = 176;
/** Puxar para atualizar: o quanto puxar no topo da lista. */
export const PULL_COMMIT_PX = 72;

/** O deslocamento visível: só na direção do gesto, com resistência depois do limite. */
export function swipeOffset(dx: number, direction: "left" | "right", limit = SWIPE_REVEAL_PX): number {
  const signed = direction === "right" ? dx : -dx;
  if (signed <= 0) return 0;
  const eased = signed <= limit ? signed : limit + (signed - limit) * 0.25;
  return direction === "right" ? eased : -eased;
}

/** Soltou: a gaveta das ações fica aberta (passou da metade) ou volta. */
export function revealSettles(dx: number, width = SWIPE_REVEAL_PX): boolean {
  return -dx >= width / 2;
}

/** A frase do puxar para atualizar, pelo quanto já se puxou. */
export function pullLabel(dy: number, refreshing: boolean): string {
  if (refreshing) return "Atualizando…";
  return dy >= PULL_COMMIT_PX ? "Solte para atualizar" : "Puxe para atualizar";
}
