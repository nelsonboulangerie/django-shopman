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

// Folga entre o CHEVRON e o que flutua na base (card de ação, barra).
//
// ⚠️ A folga é do chevron, NÃO do degradê. Enquanto ela morou aqui, no
// posicionamento da dica inteira, o degradê parava 12px acima do card e sobrava
// uma faixa de conteúdo cru entre os dois — a lavagem prometia dissolver e
// largava o texto legível justo na borda. O degradê encosta no obstáculo; o
// chevron recua por dentro. Por isso `hintOffset` não soma mais nada: quem
// aplica a folga é o recuo interno do desenho.
export const HINT_GAP = 12;

// Onde a base da dica se apoia: exatamente no topo do que flutua embaixo.
export function hintOffset(obstructedBottom: number): number {
  return Math.max(0, obstructedBottom);
}

// Quem pediu menos movimento recebe a dica PARADA, não a ausência dela: a
// informação é a mesma, só o movimento sai. É por isso que ela precisa ser
// grande o bastante para ser vista sem animar.
export function hintMotionClass(reducedMotion: boolean): string {
  return reducedMotion ? "" : "animate-bounce [animation-duration:1.6s]";
}

// Quem pediu menos movimento também não quer a página deslizando sob o olho:
// o toque na dica leva ao fim do mesmo jeito, só que de uma vez.
export function hintScrollBehavior(reducedMotion: boolean): ScrollBehavior {
  return reducedMotion ? "auto" : "smooth";
}

// A dica existe enquanto o FIM do conteúdo não apareceu. Nada de calcular
// posição de rolagem: quem responde é um sentinela no fim, observado.
export function shouldHint(endReached: boolean, enabled = true): boolean {
  return enabled && !endReached;
}
