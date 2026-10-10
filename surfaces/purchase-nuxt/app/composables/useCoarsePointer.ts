import { useMediaQuery } from "@vueuse/core";

/**
 * Toque (ponteiro grosso), para a busca da lista longa (`NuxtSelectMenu`) receber o foco
 * ao abrir só onde há teclado físico: no toque, o teclado virtual sobe quando a pessoa
 * toca na busca (README do kit, "Escolha numa lista"). Não é régua de largura: a largura
 * da tela é do `useScreen()`.
 */
export function useCoarsePointer() {
  return useMediaQuery("(pointer: coarse)");
}
