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

/**
 * O chip contrasta com o pai (coordenação, 09/10/2026): círculo × fundo do pai ≥ 3:1 e
 * número × círculo AA (4,5:1), nos dois temas. O âmbar serve sobre a página, o cartão,
 * o recorte `soft` e a barra lateral escura. Sobre pai PREENCHIDO de cor próxima, o
 * chip INVERTE: o círculo toma a cor do texto do pai e o número a cor do fundo do pai,
 * mesmo tamanho e forma (o anel continua na cor do fundo do pai). Os pais que invertem
 * são estes, e o teste de contraste (`tests/countChipContrast.test.ts`) mede cada um:
 *
 *   tabActive  aba ativa preenchida (`NuxtTabs` `pill`: o dourado/latão do `primary`)
 *              nos dois temas: o âmbar some no dourado.
 *   pressed    botão ligado (`aria-pressed="true"`): o ativo da suíte é `solid`
 *              primário (`QUICK_ACTIVE`), o mesmo dourado da aba ativa.
 *   rail       barra lateral clara (latão), linha comum e linha ativa. No escuro a
 *              barra é bronze escuro e o âmbar contrasta: não inverte.
 *
 * A inversão é derivada do pai pelo próprio CSS (o pai ativo é o ancestral, não uma
 * prop da tela): `data-slot=trigger` + `data-state=active` é a aba ativa do Nuxt UI;
 * `aria-pressed=true` é o botão ligado;
 * `.bg-rail` é o escopo da barra lateral (o `RAIL_SCOPE` do app.config), aberta,
 * compactada ou em gaveta. Vale para o chip no fluxo e para o do canto do ícone.
 */
export const COUNT_CHIP_INVERTED_ON = {
  tabActive: { themes: ["light", "dark"], parentBg: "primary", parentText: "primary-foreground" },
  pressed: { themes: ["light", "dark"], parentBg: "primary", parentText: "primary-foreground" },
  rail: { themes: ["light"], parentBg: "rail", parentText: "rail-foreground" },
  railActive: { themes: ["light"], parentBg: "rail", parentText: "rail-foreground" },
} as const;

/**
 * As classes da inversão, no `base` do Chip (uma vez no kit, nunca por tela). Escritas
 * por extenso: o Tailwind lê o texto do arquivo, e classe montada por interpolação não
 * gera CSS.
 */
export const COUNT_CHIP_INVERT_CLASSES = [
  "in-[[data-slot=trigger][data-state=active]]:bg-(--ui-text-inverted)",
  "in-[[data-slot=trigger][data-state=active]]:text-(--ui-primary)",
  "in-[[aria-pressed=true]]:bg-(--ui-text-inverted)",
  "in-[[aria-pressed=true]]:text-(--ui-primary)",
  "[:root:not(.dark)_.bg-rail_&]:bg-(--ui-text)",
  "[:root:not(.dark)_.bg-rail_&]:text-(--ui-bg)",
].join(" ");

/** As props do Chip no CANTO do ícone (barra compactada, barra inferior). */
export function countChipProps(
  count: number,
  color: CountChipColor = COUNT_CHIP_COLOR,
): { color: CountChipColor; text: string; size: typeof COUNT_CHIP_SIZE; inset: false; ui: { base: string } } {
  return { color, text: countChipText(count), size: COUNT_CHIP_SIZE, inset: false, ui: { base: COUNT_CHIP_INVERT_CLASSES } };
}

/** O ponto de estado no canto do ícone: a mesma inversão do número. */
export function countChipDotProps(color: CountChipColor = COUNT_CHIP_COLOR): { color: CountChipColor; ui: { base: string } } {
  return { color, ui: { base: COUNT_CHIP_INVERT_CLASSES } };
}
