// Uma faixa que rola para o lado (as coleções da Venda) e se deixa rolar com qualquer
// ponteiro. A barra de rolagem fica escondida para não roubar altura do balcão; sem ela,
// no mouse a faixa era um beco: a roda rola para baixo, e as coleções do fim ficavam
// fora de alcance (dono, 03/11/2026). Daqui saem:
//   - `canBack` / `canForward`: há mais daquele lado (as setas aparecem só então);
//   - `step(dir)`: rola quase uma largura da faixa, com a borda anterior à vista;
//   - a roda vertical do mouse vira rolagem lateral enquanto a faixa tiver para onde ir;
//   - `reveal(el)`: leva um item (a coleção escolhida) para dentro da faixa.
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";

export function useScrollStrip(strip: Ref<HTMLElement | null>) {
  const canBack = ref(false);
  const canForward = ref(false);

  function measure() {
    const el = strip.value;
    if (!el) return;
    canBack.value = el.scrollLeft > 1;
    canForward.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
  }

  function step(direction: -1 | 1) {
    const el = strip.value;
    if (!el) return;
    el.scrollBy({ left: direction * Math.max(el.clientWidth * 0.8, 120), behavior: "smooth" });
  }

  function onWheel(event: WheelEvent) {
    const el = strip.value;
    if (!el || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
    const room = event.deltaY > 0 ? el.scrollWidth - el.clientWidth - el.scrollLeft : el.scrollLeft;
    if (room <= 0) return;
    event.preventDefault();
    el.scrollLeft += event.deltaY;
  }

  function reveal(item: Element | null | undefined) {
    item?.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }

  let observer: ResizeObserver | null = null;
  function bind(el: HTMLElement | null, old?: HTMLElement | null) {
    old?.removeEventListener("scroll", measure);
    old?.removeEventListener("wheel", onWheel);
    observer?.disconnect();
    if (!el) return;
    el.addEventListener("scroll", measure, { passive: true });
    el.addEventListener("wheel", onWheel, { passive: false });
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(measure);
      observer.observe(el);
      for (const child of Array.from(el.children)) observer.observe(child);
    }
    measure();
  }

  onMounted(() => {
    watch(strip, (el, old) => bind(el, old), { immediate: true });
  });
  onBeforeUnmount(() => bind(null, strip.value));

  return { canBack, canForward, step, reveal, measure };
}
