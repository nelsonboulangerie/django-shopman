import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import OperatorCountChip from "../../app/components/OperatorCountChip.vue";
import { countChipProps, countChipText, hasCount } from "../../app/presentation/countChip";
import { railSignalChip } from "../../app/presentation/suiteChrome";

// O chip de contagem da suíte (dono, 09/10/2026): um desenho para toda contagem.

const mounted: VueWrapper[] = [];

async function mount(props: Record<string, unknown>) {
  const wrapper = await mountSuspended(OperatorCountChip, { props });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("countChip (puro)", () => {
  it("escreve 99+ acima de 99 e só conta inteiro maior que zero", () => {
    expect(countChipText(7)).toBe("7");
    expect(countChipText(99)).toBe("99");
    expect(countChipText(100)).toBe("99+");
    expect(hasCount(0)).toBe(false);
    expect(hasCount(null)).toBe(false);
    expect(hasCount(Number.NaN)).toBe(false);
    expect(hasCount(3)).toBe(true);
  });

  it("no canto do ícone: o mesmo chip, inset false, e a barra lateral usa este", () => {
    expect(countChipProps(7)).toMatchObject({ color: "warning", text: "7", size: "4xl", inset: false });
    expect(railSignalChip({ color: "error", count: 120 })).toEqual(countChipProps(120, "error"));
  });
});

describe("OperatorCountChip (no fluxo)", () => {
  it("é o círculo âmbar 4xl com o número, no fluxo da linha e com anel na cor do pai", async () => {
    const wrapper = await mount({ count: 7 });
    const base = wrapper.get("[data-slot=base]");
    expect(base.text()).toBe("7");
    expect(base.classes()).toEqual(expect.arrayContaining(["bg-warning", "rounded-full", "h-4", "min-w-4", "ring-2", "ring-transparent"]));
    expect(base.classes()).not.toContain("absolute");
    expect(wrapper.get("[data-count-chip]").text()).toBe("7");
  });

  it("vira pílula de pontas redondas com 99+", async () => {
    const wrapper = await mount({ count: 250 });
    const base = wrapper.get("[data-slot=base]");
    expect(base.text()).toBe("99+");
    expect(base.classes()).toContain("rounded-full");
  });

  it("os atributos vão no número; a classe, na raiz", async () => {
    const wrapper = await mountSuspended(OperatorCountChip, {
      props: { count: 2 },
      attrs: { class: "ms-auto", "data-page-header-filters-count": "" },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    expect(wrapper.get("[data-slot=root]").classes()).toContain("ms-auto");
    expect(wrapper.get("[data-page-header-filters-count]").text()).toBe("2");
  });

  it("zero e ausente não aparecem; o ponto de estado não tem número", async () => {
    expect((await mount({ count: 0 })).find("[data-count-chip]").exists()).toBe(false);
    expect((await mount({})).find("[data-count-chip]").exists()).toBe(false);
    const dot = await mount({ dot: true, color: "error" });
    const base = dot.get("[data-slot=base]");
    expect(base.text()).toBe("");
    expect(base.classes()).toContain("bg-error");
  });
});
