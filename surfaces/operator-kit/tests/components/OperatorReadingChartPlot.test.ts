import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";

import OperatorReadingChartPlot from "../../app/components/OperatorReadingChartPlot.client.vue";
import {
  READING_POINT_SIZE,
  READING_TONE_COLOR,
  defaultReadingFormat,
  type ReadingChartPoint,
  type ReadingChartSeries,
} from "../../app/presentation/readingChart";

// O Unovis não desenha no happy-dom (mede SVG que não existe). Cada peça vira um dublê
// que guarda as props com que o gráfico a montou: o contrato aqui é O QUE o gráfico
// pede ao Unovis, e o desenho de verdade se confere no Kitchen Sink.
const mountedProps = vi.hoisted(() => [] as Array<{ name: string; props: Record<string, unknown> }>);

vi.mock("@unovis/vue", async () => {
  const { defineComponent: define, h: render } = await import("vue");
  const stub = (name: string) =>
    define({
      name,
      inheritAttrs: false,
      setup(_, { attrs, slots }) {
        return () => {
          mountedProps.push({ name, props: { ...attrs } });
          return render("div", { "data-stub": name }, slots.default?.());
        };
      },
    });
  return Object.fromEntries(
    ["VisArea", "VisAxis", "VisCrosshair", "VisGroupedBar", "VisLine", "VisScatter", "VisStackedBar", "VisXYContainer"].map(
      (name) => [name, stub(name)],
    ),
  );
});

const series: ReadingChartSeries[] = [{ key: "orders", label: "Pedidos confirmados" }];
const pointsOf = (values: Array<number | null>): ReadingChartPoint[] =>
  values.map((value, index) => ({ label: `${9 + index}h`, values: { orders: value } }));

afterEach(() => {
  mountedProps.length = 0;
});

async function mountPlot(values: Array<number | null>, kind: "line" | "bars" = "line") {
  const points = pointsOf(values);
  await mountSuspended(
    defineComponent({
      render: () =>
        h(OperatorReadingChartPlot, {
          kind,
          series,
          points,
          axisFormat: defaultReadingFormat,
          height: 240,
          forcedIndex: null,
          maxTicks: 6,
        }),
    }),
  );
  return points;
}

const last = (name: string) => mountedProps.filter((entry) => entry.name === name);

describe("OperatorReadingChartPlot: o ponto isolado", () => {
  it("ponto entre dois buracos sai como marcador no tom da série, no tamanho do ponto em leitura", async () => {
    // 11h e 14h não ligam com ninguém: a linha os desenharia com comprimento zero.
    const points = await mountPlot([12, 18, null, 31, null, 16]);
    const scatter = last("VisScatter").at(-1);
    expect(scatter).toBeDefined();
    expect(scatter!.props.color).toBe(READING_TONE_COLOR.primary);
    expect(scatter!.props.size).toBe(READING_POINT_SIZE);
    const y = scatter!.props.y as (row: { index: number; point: ReadingChartPoint }) => number | undefined;
    expect(points.map((point, index) => y({ index, point }))).toEqual([undefined, undefined, undefined, 31, undefined, 16]);
    // O círculo do ponto em leitura tem o mesmo tamanho do marcador.
    expect(last("VisCrosshair").at(-1)!.props.circleRadius).toBe(READING_POINT_SIZE / 2);
  });

  it("sem ponto isolado, nenhum marcador: o resto do gráfico fica como era", async () => {
    await mountPlot([12, 18, null, 31, 25, 16]);
    expect(last("VisScatter")).toEqual([]);
    expect(last("VisLine")).toHaveLength(1);
  });

  it("nas barras o ponto isolado já é uma barra: sem marcador", async () => {
    await mountPlot([12, null, 31, null, 16], "bars");
    expect(last("VisScatter")).toEqual([]);
  });
});
