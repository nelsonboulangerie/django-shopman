// O chip de contagem da suíte, a parte PURA (dono, 09/10/2026, PR `kit-chip-contagem`).
//
// UM chip para toda contagem: item da barra lateral (aberta e compactada), barra
// inferior do celular, botões e abas/recortes com contagem. Círculo preenchido de
// 16 px (o `4xl` do kit no `chip` do app.config), número de 12 px com contraste AA
// sobre a cor (`text-inverted` do tema: branco sobre o âmbar queimado no claro,
// marrom-quase-preto sobre o âmbar claro no escuro), anel de 2 px (o traço dos ícones)
// na cor do fundo do pai. Vira pílula só quando o número não cabe ("99+"), com as
// pontas inteiramente redondas.
//
// Duas posições, um desenho:
// - no fluxo (`OperatorCountChip`): na ponta direita da linha, no centro vertical;
//   botão, aba, recorte, item da barra lateral aberta;
// - no canto do ícone (`countChipProps` no `chip` de um item do NavigationMenu): barra
//   lateral compactada e barra inferior, `inset: false`, centrado no canto.
//
// Contador em retângulo arredondado (`NuxtBadge` com número, `rounded-md` num número)
// não existe mais: a trava é `tests/guardrails.countChip.test.ts`.

export type CountChipColor = "success" | "warning" | "error";

/** A cor da referência (barra lateral da Cozinha): o âmbar da casa. */
export const COUNT_CHIP_COLOR: CountChipColor = "warning";

/** O tamanho do chip numerado: o `4xl` do kit (16 px), porque o `3xl` não lê dois dígitos. */
export const COUNT_CHIP_SIZE = "4xl" as const;

/** Acima de 99 o chip escreve "99+" (decisão de 08/10/2026, PR #1539). */
export function countChipText(count: number): string {
  return count > 99 ? "99+" : String(count);
}

/**
 * Há o que contar? Só número inteiro maior que zero vira chip. Zero não é sinal: um
 * círculo âmbar com "0" chama atenção para o nada ("zero como código secreto").
 */
export function hasCount(count: number | null | undefined): count is number {
  return typeof count === "number" && Number.isFinite(count) && count > 0;
}

/** As props do Chip no CANTO do ícone (barra compactada, barra inferior). */
export function countChipProps(
  count: number,
  color: CountChipColor = COUNT_CHIP_COLOR,
): { color: CountChipColor; text: string; size: typeof COUNT_CHIP_SIZE; inset: false } {
  return { color, text: countChipText(count), size: COUNT_CHIP_SIZE, inset: false };
}
