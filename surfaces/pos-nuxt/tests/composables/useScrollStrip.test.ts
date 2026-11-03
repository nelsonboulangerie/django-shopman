import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import { useScrollStrip } from "~/composables/useScrollStrip";

// As coleções da Venda rolam para o lado com a barra escondida. No mouse a faixa
// era um beco (dono, 03/11/2026): sem seta e com a roda rolando para baixo, as
// últimas coleções ficavam fora de alcance.
function fakeStrip(el: HTMLElement, { width, content }: { width: number; content: number }) {
  Object.defineProperty(el, "clientWidth", { value: width, configurable: true });
  Object.defineProperty(el, "scrollWidth", { value: content, configurable: true });
  let left = 0;
  Object.defineProperty(el, "scrollLeft", {
    get: () => left,
    set: (v: number) => { left = Math.max(0, Math.min(v, content - width)); el.dispatchEvent(new Event("scroll")); },
    configurable: true,
  });
  el.scrollBy = ((opts: ScrollToOptions) => { el.scrollLeft = left + (opts.left ?? 0); }) as typeof el.scrollBy;
}

async function mountStrip(width: number, content: number) {
  let api!: ReturnType<typeof useScrollStrip>;
  const Host = defineComponent({
    setup() {
      const strip = ref<HTMLElement | null>(null);
      api = useScrollStrip(strip);
      return () => h("div", { ref: (el) => {
        if (el && !strip.value) { fakeStrip(el as HTMLElement, { width, content }); strip.value = el as HTMLElement; }
      } });
    },
  });
  const wrapper = await mountSuspended(Host);
  await nextTick();
  api.measure();
  return { wrapper, api, el: wrapper.element as HTMLElement };
}

describe("useScrollStrip: a faixa das coleções", () => {
  it("cabe tudo: nenhuma seta", async () => {
    const { api } = await mountStrip(400, 400);
    expect(api.canBack.value).toBe(false);
    expect(api.canForward.value).toBe(false);
  });

  it("passa da largura: seta para frente; andou, aparece a de voltar; no fim, some a da frente", async () => {
    const { api, el } = await mountStrip(400, 1000);
    expect(api.canBack.value).toBe(false);
    expect(api.canForward.value).toBe(true);
    api.step(1);
    expect(el.scrollLeft).toBe(320);
    expect(api.canBack.value).toBe(true);
    api.step(1);
    expect(el.scrollLeft).toBe(600);
    expect(api.canForward.value).toBe(false);
  });

  it("a roda do mouse (vertical) rola a faixa para o lado", async () => {
    const { el } = await mountStrip(400, 1000);
    const wheel = new WheelEvent("wheel", { deltaY: 120, cancelable: true });
    el.dispatchEvent(wheel);
    expect(el.scrollLeft).toBe(120);
    expect(wheel.defaultPrevented).toBe(true);
  });

  it("no fim da faixa a roda volta a rolar a página", async () => {
    const { el } = await mountStrip(400, 1000);
    el.scrollLeft = 600;
    const wheel = new WheelEvent("wheel", { deltaY: 120, cancelable: true });
    el.dispatchEvent(wheel);
    expect(wheel.defaultPrevented).toBe(false);
  });
});
