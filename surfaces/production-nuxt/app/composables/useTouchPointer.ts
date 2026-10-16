import { useMediaQuery } from "@vueuse/core";

/**
 * Ponteiro de toque (`pointer: coarse`), a única régua da Produção que não é de largura
 * (a de largura é o `useScreen()` do kit). Serve a comportamento, nunca à árvore do
 * primeiro desenho: a busca do `NuxtSelectMenu` só ganha o foco ao abrir onde há
 * teclado físico, e o painel encaixado do tablet de toque. Responde `false` no servidor.
 */
export function useTouchPointer() {
  return useMediaQuery("(pointer: coarse)");
}
