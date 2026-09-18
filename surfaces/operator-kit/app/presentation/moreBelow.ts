// Tem mais abaixo — a regra pura da dica de rolagem.
//
// Irmã do próximo foco, e a outra metade do mesmo contrato com a área visível:
// um responde "onde eu devo estar agora", esta responde "ainda há coisa que
// você não viu". As duas convivem, e devem: com a ação fixa num card e sem a
// dica, dá para avançar sem nunca ver as opções que ficaram abaixo.
//
// Esta camada não toca o DOM — só decide. A observação e o desenho vivem em
// `composables/useMoreBelow` e `components/MoreBelow.vue`.
// Espelhado em `storefront-nuxt/app/presentation/moreBelow.ts`.

// Folga entre a dica e o que estiver flutuando na base (card de ação, barra).
// Encostada nele a dica vira parte do card; longe demais ela boia no meio do
// conteúdo e perde o sentido de "continua para baixo".
export const HINT_GAP = 12;

export function hintOffset(obstructedBottom: number, gap = HINT_GAP): number {
  return Math.max(0, obstructedBottom) + gap;
}

// Quem pediu menos movimento recebe a dica PARADA, não a ausência dela: a
// informação é a mesma, só o movimento sai. É por isso que ela precisa ser
// grande o bastante para ser vista sem animar.
export function hintMotionClass(reducedMotion: boolean): string {
  return reducedMotion ? "" : "animate-bounce [animation-duration:1.6s]";
}

// A dica existe enquanto o FIM do conteúdo não apareceu. Nada de calcular
// posição de rolagem: quem responde é um sentinela no fim, observado.
export function shouldHint(endReached: boolean, enabled = true): boolean {
  return enabled && !endReached;
}
