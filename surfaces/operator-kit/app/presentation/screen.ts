// A régua de tela da suíte (uma só, a do CSS). As larguras são as do Tailwind: quem lê
// `screen.belowSm` no script e quem escreve `max-sm:` no template falam da MESMA borda.
//
// Antes, cada tela declarava a própria (`useMediaQuery("(max-width: 639.98px)")` em nove
// telas do Gestor, 1279 px na fila com o mesmo nome) e decidia `v-if` com ela. O servidor
// não sabe a largura e desenhava a mesa; o celular hidratava outra árvore. Ver o
// `useScreen` (o composable) e a seção "Régua de tela" do README.

export const SCREEN_BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280 } as const;

export type ScreenBreakpoint = keyof typeof SCREEN_BREAKPOINTS;

/** A consulta de "abaixo de `bp`", a mesma borda do `max-<bp>:` do Tailwind. */
export function belowQuery(bp: ScreenBreakpoint): string {
  return `(max-width: ${SCREEN_BREAKPOINTS[bp] - 0.02}px)`;
}
