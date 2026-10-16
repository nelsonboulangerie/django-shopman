// O gesto de deslizar uma linha no toque (OperatorSwipeRow). Puro: testado em
// `tests/swipe.test.ts`.
//
// Duas direções, dois sentidos, e nenhum deles é o único caminho:
//   - para a ESQUERDA revela ações (uma gaveta que fica aberta depois da metade);
//   - para a DIREITA faz o gesto principal da linha, só quando passa do ponto de
//     compromisso. Soltar antes devolve a linha, e nada acontece.
// O mesmo ato existe sempre num botão visível (o do cartão, o do polegar): o deslize
// é o atalho do dedo, nunca a única porta.

/** Quanto o dedo precisa andar para a direita para o gesto valer. */
export const SWIPE_COMMIT_PX = 96;
/** Largura máxima das ações que o deslize para a esquerda revela. */
export const SWIPE_REVEAL_PX = 176;
/** A partir de quanto a faixa descoberta tem largura para o verbo escrito (antes, só o ícone). */
export const SWIPE_LABEL_MIN_PX = 64;
/** O quanto o dedo anda antes de o gesto escolher o eixo (rolar ou deslizar). */
export const SWIPE_AXIS_PX = 10;

/** O deslocamento visível: só na direção do gesto, com resistência depois do limite. */
export function swipeOffset(
  dx: number,
  direction: "left" | "right",
  limit = SWIPE_REVEAL_PX,
): number {
  const signed = direction === "right" ? dx : -dx;
  if (signed <= 0) return 0;
  const eased = signed <= limit ? signed : limit + (signed - limit) * 0.25;
  return direction === "right" ? eased : -eased;
}

/** Soltou para a esquerda: a gaveta das ações fica aberta (passou da metade) ou volta. */
export function revealSettles(dx: number, width = SWIPE_REVEAL_PX): boolean {
  return -dx >= width / 2;
}

/** Soltou para a direita: o gesto principal vale só depois do ponto de compromisso. */
export function commitReached(dx: number, threshold = SWIPE_COMMIT_PX): boolean {
  return dx >= threshold;
}

/**
 * O eixo do gesto, decidido no começo: rolagem vertical nunca vira deslize. Vazio
 * enquanto o dedo não andou o bastante para dizer.
 */
export function swipeAxis(dx: number, dy: number): "x" | "y" | "" {
  if (Math.abs(dx) > SWIPE_AXIS_PX && Math.abs(dx) >= Math.abs(dy)) return "x";
  if (Math.abs(dy) > SWIPE_AXIS_PX) return "y";
  return "";
}

/**
 * Para onde a linha pode ir agora. Com a gaveta aberta, só volta (direita até zero);
 * fechada, cada lado só existe se tiver o que fazer.
 */
export function swipeDirection(
  dx: number,
  options: { hasActions: boolean; hasCommit: boolean; open: boolean },
): "left" | "right" | "" {
  if (options.open) return "left";
  if (dx > 0) return options.hasCommit ? "right" : "";
  if (dx < 0) return options.hasActions ? "left" : "";
  return "";
}
