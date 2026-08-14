import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BarSeries from "~/components/chart/BarSeries.vue";
import DivergingBars from "~/components/chart/DivergingBars.vue";
import HBarList from "~/components/chart/HBarList.vue";

describe("chart/BarSeries", () => {
  const points = [
    { label: "12/08", value: 10 },
    { label: "13/08", value: 40, detail: "pico" },
    { label: "14/08", value: 0 },
  ];

  it("renderiza uma barra por ponto, escalada pelo máximo", () => {
    const wrapper = mount(BarSeries, { props: { points } });
    const bars = wrapper.findAll(".rounded-t-sm");
    expect(bars).toHaveLength(3);
    expect(bars[1]!.attributes("style")).toContain("height: 100%");
    expect(bars[2]!.attributes("style")).toContain("height: 0%");
  });

  it("rótulo direto só no pico (seletivo, não em todo ponto)", () => {
    const wrapper = mount(BarSeries, {
      props: { points, format: (v: number) => `#${v}` },
    });
    // O tooltip (oculto por CSS) existe para todo ponto; o rótulo DIRETO
    // (span -top-4) só no pico.
    const direct = wrapper.findAll(".-top-4");
    expect(direct).toHaveLength(1);
    expect(direct[0]!.text()).toBe("#40");
  });

  it("tooltip carrega rótulo, valor e detalhe", () => {
    const wrapper = mount(BarSeries, { props: { points } });
    expect(wrapper.text()).toContain("pico");
  });

  it("período anterior vira traço, entra no máximo e no tooltip", () => {
    const wrapper = mount(BarSeries, {
      props: {
        // anterior (80) maior que o atual (40): o máximo tem que considerá-lo.
        points: [{ label: "14/08", value: 40, previous: 80 }],
        format: (v: number) => `#${v}`,
      },
    });
    const bar = wrapper.find(".rounded-t-sm");
    expect(bar.attributes("style")).toContain("height: 50%");
    const dash = wrapper.find(".h-0\\.5");
    expect(dash.exists()).toBe(true);
    expect(dash.attributes("style")).toContain("bottom: 100%");
    expect(wrapper.text()).toContain("anterior #80");
  });
});

describe("chart/DivergingBars", () => {
  it("separa positivo (tinta) de negativo (destructive)", () => {
    const wrapper = mount(DivergingBars, {
      props: {
        points: [
          { label: "12/08", value: 500 },
          { label: "13/08", value: -300 },
        ],
      },
    });
    expect(wrapper.findAll(".bg-foreground\\/60")).toHaveLength(1);
    expect(wrapper.findAll(".bg-destructive\\/70")).toHaveLength(1);
  });
});

describe("chart/HBarList", () => {
  it("mostra rótulo, valor formatado e barra proporcional", () => {
    const wrapper = mount(HBarList, {
      props: {
        rows: [
          { label: "web", value: 4000, display: "R$ 40,00" },
          { label: "pdv", value: 2000, display: "R$ 20,00", hint: "2 pedidos" },
        ],
      },
    });
    expect(wrapper.text()).toContain("R$ 40,00");
    expect(wrapper.text()).toContain("2 pedidos");
    const fills = wrapper.findAll(".bg-foreground\\/60");
    expect(fills[1]!.attributes("style")).toContain("width: 50%");
  });
});
