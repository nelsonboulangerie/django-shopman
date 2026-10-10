import type { Ref } from "vue";
import { PULL_COMMIT_PX, pullLabel } from "~/presentation/swipe";

/**
 * "Puxe para atualizar" (G17, prévia v3 `depois-gestor-celular` (a)): no topo da
 * lista, puxar para baixo além de `PULL_COMMIT_PX` e soltar refaz a leitura. Só no
 * toque e só quando `enabled` (o celular); o resto da rolagem segue do navegador.
 */
export function usePullToRefresh(
  el: Ref<HTMLElement | null>,
  onRefresh: () => Promise<unknown> | unknown,
  enabled: Ref<boolean>,
) {
  const pull = ref(0);
  const refreshing = ref(false);
  let y0: number | null = null;

  function start(event: TouchEvent) {
    if (!enabled.value || refreshing.value || (el.value?.scrollTop ?? 0) > 0)
      return;
    y0 = event.touches[0]?.clientY ?? null;
  }
  function move(event: TouchEvent) {
    if (y0 === null) return;
    const dy = (event.touches[0]?.clientY ?? y0) - y0;
    pull.value = dy > 0 ? Math.min(dy * 0.6, PULL_COMMIT_PX * 1.4) : 0;
  }
  async function end() {
    if (y0 === null) return;
    y0 = null;
    if (pull.value >= PULL_COMMIT_PX) {
      refreshing.value = true;
      try {
        await onRefresh();
      } finally {
        refreshing.value = false;
      }
    }
    pull.value = 0;
  }
  watch(
    el,
    (node, old) => {
      old?.removeEventListener("touchstart", start);
      old?.removeEventListener("touchmove", move);
      old?.removeEventListener("touchend", end);
      node?.addEventListener("touchstart", start, { passive: true });
      node?.addEventListener("touchmove", move, { passive: true });
      node?.addEventListener("touchend", end);
    },
    { immediate: true },
  );
  onBeforeUnmount(() => {
    el.value?.removeEventListener("touchstart", start);
    el.value?.removeEventListener("touchmove", move);
    el.value?.removeEventListener("touchend", end);
  });
  const label = computed(() => pullLabel(pull.value, refreshing.value));
  return { pull, refreshing, label };
}
