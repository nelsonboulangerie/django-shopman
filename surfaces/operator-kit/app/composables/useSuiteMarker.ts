// O opt-in do kit pelo marcador da suíte: os sete apps ainda não migrados ao cânone
// Nuxt UI vestem `data-suite="v3"` no próprio shell; o Gestor (o molde) não veste.
// Peça compartilhada que precisa do comportamento antigo SÓ nesses apps (o alvo de
// toque de 44 px da FilterBar, por exemplo) pergunta aqui, a partir do próprio
// elemento, depois de montar. No servidor e no Gestor a resposta é sempre `false`.
// O PR 0.2 da onda 0 (WP-OPERADOR-NUXTUI-ONDAS) troca isto pelo modo declarado no
// `app.config` do app; até lá, o marcador é a fonte.
import { onMounted, ref, type Ref } from "vue";

export const SUITE_MARKER_SELECTOR = '[data-suite="v3"]';

export function useSuiteMarker(element: Ref<HTMLElement | null>): Ref<boolean> {
  const marked = ref(false);
  onMounted(() => {
    marked.value = Boolean(element.value?.closest(SUITE_MARKER_SELECTOR));
  });
  return marked;
}
