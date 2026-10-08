import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";

import OperatorReadingCard from "../../app/components/OperatorReadingCard.vue";
import OperatorReadingChart from "../../app/components/OperatorReadingChart.vue";
import OperatorReadingPageMenu from "../../app/components/OperatorReadingPageMenu.vue";
import type { ReadingChartPoint, ReadingChartSeries } from "../../app/presentation/readingChart";

// O desenho (Unovis) não roda no happy-dom: mede SVG que não existe. O dublê guarda as
// props que recebeu e deixa o teste disparar o que o Crosshair do Unovis dispararia.
const plotProps: Array<Record<string, unknown>> = [];
const PlotStub = defineComponent({
  name: "OperatorReadingChartPlot",
  props: {
    kind: { type: String, default: undefined },
    series: { type: Array, default: undefined },
    points: { type: Array, default: undefined },
    format: { type: Function, default: undefined },
    diverging: { type: Object, default: undefined },
    height: { type: Number, default: undefined },
    forcedIndex: { type: Number, default: null },
    maxTicks: { type: Number, default: undefined },
  },
  emits: ["point", "leave"],
  setup(props, { emit }) {
    return () => {
      plotProps.push({ ...props });
      return h("div", { "data-plot-stub": "", "data-active": String(props.forcedIndex) }, [
        h("button", { "data-stub-point": "", onClick: () => emit("point", 3) }),
        h("button", { "data-stub-leave": "", onClick: () => emit("leave") }),
      ]);
    };
  },
});

const series: ReadingChartSeries[] = [{ key: "orders", label: "Pedidos confirmados" }];
const points: ReadingChartPoint[] = ["09h", "10h", "11h", "12h"].map((label, index) => ({
  label,
  values: { orders: [12, 18, 25, 31][index] },
}));

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  plotProps.length = 0;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

async function mountChart(props: Record<string, unknown> = {}) {
  mounted = await mountSuspended(OperatorReadingChart, {
    attachTo: document.body,
    props: { title: "Pedidos confirmados por hora", axisLabel: "Hora", series, points, ...props },
    global: { stubs: { OperatorReadingChartPlot: PlotStub } },
  });
  await nextTick();
  return mounted;
}

const area = () => document.querySelector<HTMLElement>("[data-operator-reading-area]")!;
const readout = () => document.querySelector("[data-operator-reading-readout]")!.textContent!.trim();
const announcement = () => document.querySelector("[data-operator-reading-announcement]")!.textContent!.trim();

async function press(key: string) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  area().dispatchEvent(event);
  await nextTick();
  return event;
}

describe("OperatorReadingChart: o ponto em leitura pelo teclado", () => {
  it("a área do gráfico é uma parada de tabulação com nome e descrição", async () => {
    await mountChart();
    expect(area().getAttribute("tabindex")).toBe("0");
    expect(area().getAttribute("role")).toBe("group");
    expect(area().getAttribute("aria-label")).toBe("Pedidos confirmados por hora");
    const described = document.getElementById(area().getAttribute("aria-describedby")!);
    expect(described?.hasAttribute("data-operator-reading-readout")).toBe(true);
    expect(readout()).toBe("Toque no gráfico, passe o mouse ou use as setas para ler cada ponto.");
  });

  it("setas leem cada ponto, o leitor de tela ouve, e o traço vertical acompanha", async () => {
    await mountChart();
    area().focus();
    const first = await press("ArrowRight");
    expect(first.defaultPrevented).toBe(true);
    expect(readout()).toBe("09h: Pedidos confirmados 12");
    expect(announcement()).toBe("09h: Pedidos confirmados 12");
    expect(document.querySelector("[data-plot-stub]")!.getAttribute("data-active")).toBe("0");
    await press("End");
    expect(readout()).toBe("12h: Pedidos confirmados 31");
    await press("ArrowLeft");
    expect(announcement()).toBe("11h: Pedidos confirmados 25");
  });

  it("Escape solta a leitura; Tab segue para o navegador", async () => {
    await mountChart();
    await press("Home");
    await press("Escape");
    expect(readout()).toContain("use as setas");
    const tab = await press("Tab");
    expect(tab.defaultPrevented).toBe(false);
  });

  it("perder o foco solta o ponto que o teclado escolheu", async () => {
    await mountChart();
    area().focus();
    await press("Home");
    area().dispatchEvent(new FocusEvent("blur"));
    await nextTick();
    expect(readout()).toContain("use as setas");
  });
});

describe("OperatorReadingChart: o ponto em leitura pelo ponteiro (mouse e toque)", () => {
  it("o ponto do ponteiro mostra a frase sem falar ao leitor de tela, e some ao sair", async () => {
    await mountChart();
    (document.querySelector("[data-stub-point]") as HTMLElement).click();
    await nextTick();
    expect(readout()).toBe("12h: Pedidos confirmados 31");
    expect(announcement()).toBe("");
    // O ponto do ponteiro não é forçado no desenho: forçar travava o traço no primeiro
    // ponto tocado, e o mouse não saía mais dele.
    expect(document.querySelector("[data-plot-stub]")!.getAttribute("data-active")).toBe("null");
    (document.querySelector("[data-stub-leave]") as HTMLElement).click();
    await nextTick();
    expect(readout()).toContain("use as setas");
  });
});

describe("OperatorReadingChart: tabela, legenda e vazio", () => {
  it("a tabela equivalente existe para o leitor de tela, com legenda e cabeçalhos", async () => {
    await mountChart();
    const table = document.querySelector("[data-operator-reading-table]")!;
    expect(table.classList.contains("sr-only")).toBe(true);
    // Dentro do recorte do sr-only a tabela não rola (axe: scrollable-region-focusable).
    const root = table.querySelector('[data-slot="root"]')!;
    expect(root.classList.contains("overflow-visible")).toBe(true);
    expect(root.classList.contains("overflow-auto")).toBe(false);
    expect(table.querySelector("caption")?.textContent).toContain("Pedidos confirmados por hora, em tabela");
    const headers = [...table.querySelectorAll("th")].map((cell) => cell.textContent?.trim());
    expect(headers).toEqual(["Hora", "Pedidos confirmados"]);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(4);
  });

  it("table-visible mostra a tabela a quem enxerga", async () => {
    await mountChart({ tableVisible: true, tableCaption: "Dados do gráfico de pedidos" });
    const table = document.querySelector("[data-operator-reading-table]")!;
    expect(table.classList.contains("sr-only")).toBe(false);
    expect(table.querySelector('[data-slot="root"]')!.classList.contains("overflow-visible")).toBe(false);
    expect(table.querySelector("caption")?.textContent).toContain("Dados do gráfico de pedidos");
  });

  it("o divergente tem legenda com os dois lados e a tabela fala a palavra do lado", async () => {
    await mountChart({
      kind: "diverging",
      axisLabel: "Produto",
      series: [{ key: "difference", label: "Sobra ou falta" }],
      points: [
        { label: "Croissant", values: { difference: 6 } },
        { label: "Brioche", values: { difference: -2 } },
      ],
      diverging: { positive: "Sobrou", negative: "Faltou" },
    });
    const legend = document.querySelector("[data-operator-reading-legend]")!;
    expect(legend.getAttribute("aria-hidden")).toBe("true");
    expect(legend.textContent).toContain("Sobrou");
    expect(legend.textContent).toContain("Faltou");
    const cells = [...document.querySelectorAll("[data-operator-reading-table] tbody td")].map((cell) =>
      cell.textContent?.trim(),
    );
    expect(cells).toEqual(["Croissant", "Sobrou 6", "Brioche", "Faltou 2"]);
  });

  it("sem pontos, o vazio é o NuxtEmpty, sem área de teclado", async () => {
    await mountChart({ points: [] });
    expect(document.querySelector("[data-operator-reading-area]")).toBeNull();
    expect(document.body.textContent).toContain("Sem dados para esta leitura");
  });

  it("entrega ao desenho a forma, as séries e o teto de rótulos", async () => {
    await mountChart({ kind: "comparison", maxTicks: 4 });
    const last = plotProps.at(-1)!;
    expect(last.kind).toBe("comparison");
    expect(last.maxTicks).toBe(4);
    expect(last.points).toEqual(points);
  });
});

describe("OperatorReadingCard: o quadro de leitura", () => {
  it("é NuxtCard com título em cabeçalho, descrição e região nomeada", async () => {
    mounted = await mountSuspended(OperatorReadingCard, {
      attachTo: document.body,
      props: { title: "Faturamento por dia", description: "Esta semana contra a anterior", headingLevel: 3 },
      slots: { default: () => h("p", { "data-test": "corpo" }, "conteúdo") },
    });
    const card = document.querySelector<HTMLElement>("[data-operator-reading-card]")!;
    expect(card.tagName).toBe("SECTION");
    const heading = card.querySelector("h3")!;
    expect(heading.textContent).toBe("Faturamento por dia");
    expect(card.getAttribute("aria-labelledby")).toBe(heading.id);
    expect(card.querySelector('[data-slot="title"]')).not.toBeNull();
    expect(card.querySelector('[data-slot="description"]')?.textContent?.trim()).toBe(
      "Esta semana contra a anterior",
    );
    expect(card.querySelector('[data-slot="body"] [data-test="corpo"]')).not.toBeNull();
    // Sem csv nem items, não há ⋯ vazio.
    expect(card.querySelector("[data-operator-reading-card-menu]")).toBeNull();
  });

  it("o ⋯ exporta o CSV deste quadro, com o nome do arquivo saído do título", async () => {
    const createObjectURL = vi.fn(() => "blob:quadro");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });

    mounted = await mountSuspended(OperatorReadingCard, {
      attachTo: document.body,
      props: { title: "Faturamento por dia", csv: { header: ["Dia", "Valor"], rows: [["Seg 05/10", 3180]] } },
    });
    const trigger = document.querySelector<HTMLElement>("[data-operator-reading-card-menu]")!;
    expect(trigger.getAttribute("aria-label")).toBe("Mais sobre Faturamento por dia");
    trigger.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
    trigger.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const item = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find((node) =>
      node.textContent?.includes("Exportar CSV deste quadro"),
    );
    expect(item).toBeDefined();
    item!.click();
    await nextTick();
    expect(clicks).toEqual(["faturamento-por-dia.csv"]);
    const blob = (createObjectURL.mock.calls[0] as unknown as [Blob])[0];
    expect(await blob.text()).toBe("\uFEFFDia;Valor\nSeg 05/10;3180");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:quadro");
    vi.unstubAllGlobals();
  });
});

describe("OperatorReadingPageMenu: o ⋯ da página de leitura", () => {
  it("o rótulo diz o que o menu tem", async () => {
    mounted = await mountSuspended(OperatorReadingPageMenu, { attachTo: document.body });
    expect(document.querySelector("[data-operator-reading-page-menu]")!.getAttribute("aria-label")).toBe(
      "Mais: copiar link desta leitura",
    );
    mounted.unmount();
    mounted = await mountSuspended(OperatorReadingPageMenu, {
      attachTo: document.body,
      props: { items: [{ label: "Como é calculado" }] },
    });
    expect(document.querySelector("[data-operator-reading-page-menu]")!.getAttribute("aria-label")).toBe(
      "Mais: copiar link e como é calculado",
    );
  });
});
