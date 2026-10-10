import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import OperatorTable from "../../app/components/OperatorTable.vue";
import OperatorTableView from "../../app/components/OperatorTableView.vue";
import {
  appendClass,
  hideableColumns,
  operatorTableViewCookie,
  parseTableView,
  reconcileHidden,
  sortLabel,
  sortButtonClass,
  tableDensityUi,
  toggleHidden,
  visibilityFromHidden,
} from "../../app/presentation/operatorTable";

interface Order {
  ref: string;
  customer: string;
  channel: string;
  total_q: number;
}

const orders: Order[] = [
  { ref: "H58", customer: "Ana Souza de Albuquerque Figueiredo", channel: "iFood", total_q: 4870 },
  { ref: "H59", customer: "Bruno Lima", channel: "Loja", total_q: 1290 },
  { ref: "H60", customer: "Carla Dias", channel: "Balcão", total_q: 9320 },
];

const columns = [
  { accessorKey: "ref", header: "Pedido", enableHiding: false, enableSorting: true },
  { accessorKey: "customer", header: "Cliente", enableSorting: true },
  { accessorKey: "channel", header: "Canal", meta: { supporting: true } },
  { accessorKey: "total_q", header: "Total", enableSorting: true },
];

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0]!.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
});

const table = () => document.querySelector<HTMLElement>("[data-operator-table]")!;
const bodyRows = () => [...table().querySelectorAll("tbody tr")] as HTMLElement[];
const firstCells = () => bodyRows().map((row) => row.querySelectorAll("td")[0]?.textContent?.trim());

describe("as decisões puras da tabela", () => {
  it("compacta é o padrão; cookie estranho volta ao padrão", () => {
    expect(parseTableView(null)).toEqual({ density: "compact", hidden: [] });
    expect(parseTableView({ density: "gigante", hidden: "x" })).toEqual({ density: "compact", hidden: [] });
    expect(parseTableView({ density: "comfortable", hidden: ["a", "a", 3, ""] })).toEqual({
      density: "comfortable",
      hidden: ["a"],
    });
  });

  it("guarda as OCULTAS: coluna nova nasce visível", () => {
    expect(visibilityFromHidden(["canal"])).toEqual({ canal: false });
    expect(toggleHidden([], "canal", false)).toEqual(["canal"]);
    expect(toggleHidden(["canal"], "canal", true)).toEqual([]);
    expect(reconcileHidden(["canal", "sumiu"], ["canal", "total"])).toEqual(["canal"]);
  });

  it("a célula quebra nas duas densidades (texto da casa nunca cortado)", () => {
    expect(tableDensityUi("compact").td).toContain("whitespace-normal");
    expect(tableDensityUi("comfortable").td).toContain("whitespace-normal");
    expect(tableDensityUi("compact").td).not.toContain("truncate");
  });

  it("o foco da linha e do botão de ordenar fica DENTRO da tabela (o recorte do cartão não corta)", () => {
    expect(tableDensityUi("compact").tr).toContain("focus-visible:-outline-offset-2");
    expect(tableDensityUi("comfortable").tr).toContain("focus-visible:-outline-offset-2");
    expect(sortButtonClass("compact")).toBe("-ms-2 focus-visible:-outline-offset-3");
    expect(sortButtonClass("comfortable")).toBe("-ms-2.5 focus-visible:-outline-offset-3");
  });

  it("o Exibir lista o que pode sumir, com o nome do cabeçalho", () => {
    expect(hideableColumns(columns)).toEqual([
      { id: "customer", label: "Cliente" },
      { id: "channel", label: "Canal" },
      { id: "total_q", label: "Total" },
    ]);
    expect(appendClass(undefined, "max-sm:hidden")).toBe("max-sm:hidden");
    expect((appendClass(() => "a", "b") as (x: unknown) => string)(null)).toBe("a b");
    expect(operatorTableViewCookie("orders/history")).toBe("op-table-orders-history");
    expect(sortLabel("Total", false)).toBe("Ordenar por total");
    expect(sortLabel("Total", "asc")).not.toMatch(/[—–]/);
  });
});

describe("OperatorTable", () => {
  it("nasce COMPACTA, ordena pelo cabeçalho e some com a coluna de apoio no celular", async () => {
    mounted = await mountSuspended(OperatorTable as never, {
      attachTo: document.body,
      props: {
        data: orders,
        columns,
        rowKey: (row: Order) => row.ref,
        caption: "Pedidos da semana",
      },
    });
    expect(table().getAttribute("data-density")).toBe("compact");
    expect(table().querySelector("td")!.className).toContain("py-1.5");
    const channelTh = [...table().querySelectorAll("th")].find((th) => th.textContent?.includes("Canal"))!;
    expect(channelTh.className).toContain("max-sm:hidden");
    expect(table().querySelector("[data-operator-table-sort='channel']")).toBeNull();

    const sortTotal = table().querySelector<HTMLButtonElement>("[data-operator-table-sort='total_q']")!;
    expect(sortTotal.getAttribute("aria-label")).toBe("Ordenar por total");
    sortTotal.click();
    await nextTick();
    expect(firstCells()).toEqual(["H59", "H58", "H60"]);
    sortTotal.click();
    await nextTick();
    expect(firstCells()).toEqual(["H60", "H58", "H59"]);
  });

  it("seleção múltipla com o nome da linha; marcar não abre a linha", async () => {
    const opened: string[] = [];
    const selection = ref<Record<string, boolean>>({});
    const Host = defineComponent({
      setup: () => () =>
        h(OperatorTable as never, {
          data: orders,
          columns,
          rowKey: (row: Order) => row.ref,
          rowLabel: (row: Order) => `o pedido ${row.ref}`,
          caption: "Pedidos",
          selectable: true,
          rowSelection: selection.value,
          "onUpdate:rowSelection": (next: Record<string, boolean>) => (selection.value = next),
          onSelect: (row: Order) => opened.push(row.ref),
        }),
    });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    const box = document.querySelector<HTMLElement>("[data-operator-table-select][aria-label='Selecionar o pedido H59']")!;
    expect(box).not.toBeNull();
    box.click();
    await nextTick();
    expect(selection.value).toEqual({ H59: true });
    expect(opened).toEqual([]);

    document.querySelector<HTMLElement>("[data-operator-table-select-all]")!.click();
    await nextTick();
    expect(Object.keys(selection.value).sort()).toEqual(["H58", "H59", "H60"]);

    bodyRows()[0]!.querySelectorAll("td")[2]!.click();
    expect(opened).toEqual(["H58"]);
  });

  it("a linha aberta NÃO compacta: o conteúdo ganha o respiro da confortável", async () => {
    mounted = await mountSuspended(OperatorTable as never, {
      attachTo: document.body,
      props: { data: orders, columns, rowKey: (row: Order) => row.ref, caption: "Pedidos" },
      slots: { expanded: ({ row }: { row: { original: Order } }) => h("p", `Itens de ${row.original.ref}`) },
    });
    document.querySelector<HTMLElement>("[data-operator-table-expand]")!.click();
    await nextTick();
    const open = document.querySelector<HTMLElement>("[data-operator-table-expanded]")!;
    expect(open.textContent).toContain("Itens de H58");
    expect(open.className).toContain("px-2");
    expect(open.className).toContain("py-1.5");
  });

  it("a coluna fixada cabe no celular e a tela não escreve :ui", async () => {
    mounted = await mountSuspended(OperatorTable as never, {
      attachTo: document.body,
      props: { data: orders, columns, rowKey: (row: Order) => row.ref, caption: "Pedidos", pinned: "ref", selectable: true },
    });
    const pinned = [...table().querySelectorAll<HTMLElement>("tbody tr:first-child td[data-pinned='left']")];
    expect(pinned).toHaveLength(2);
    // A caixa de marcar tem largura declarada: a coluna fixada para logo depois dela
    // (sem os 150 px que o TanStack supõe para quem não diz).
    expect(pinned[0]!.style.width).toBe("32px");
    expect(pinned[1]!.style.left).toBe("32px");
    expect(pinned[1]!.className).toContain("max-sm:max-w-40");
  });

  it("estados: carregando, vazio e erro pela peça do estado", async () => {
    mounted = await mountSuspended(OperatorTable as never, {
      attachTo: document.body,
      props: { data: [], columns, rowKey: (row: Order) => row.ref, caption: "Pedidos", loading: true, what: "o histórico" },
    });
    expect(document.querySelector("[data-operator-screen-state='loading']")?.textContent).toContain(
      "Carregando o histórico",
    );
    await mounted.setProps({ loading: false, emptyTitle: "Nenhum pedido neste recorte." });
    expect(document.querySelector("[data-operator-screen-state='empty']")?.textContent).toContain(
      "Nenhum pedido neste recorte.",
    );
    await mounted.setProps({ error: true });
    expect(document.querySelector("[data-operator-screen-state='error']")?.textContent).toContain(
      "Não foi possível carregar o histórico",
    );
    expect(document.querySelector("[data-operator-screen-state='empty']")).toBeNull();
    await mounted.setProps({ data: orders });
    expect(document.querySelector("[data-operator-screen-state='error']")).not.toBeNull();
    expect(table()).not.toBeNull();
  });

  it("dentro de outro cartão: o da tabela é soft e o vazio perde a moldura", async () => {
    mounted = await mountSuspended(OperatorTable as never, {
      attachTo: document.body,
      props: { data: orders, columns, rowKey: (row: Order) => row.ref, caption: "Pedidos", inCard: true },
    });
    const card = table().closest("[data-operator-table-root] > *") as HTMLElement;
    expect(card.className).not.toContain("bg-card");
    expect(card.className).toContain("bg-elevated");
    await mounted.setProps({ data: [], emptyTitle: "Nenhum pedido neste recorte." });
    const empty = document.querySelector<HTMLElement>("[data-operator-screen-state='empty']")!;
    expect(empty.className).not.toMatch(/\bring\b|bg-card/);
  });

  it("Exibir: Confortável e colunas ocultas valem para a tabela com a mesma chave", async () => {
    const Host = defineComponent({
      setup: () => () =>
        h("div", [
          h(OperatorTableView, { tableKey: "teste-pedidos" }),
          h(OperatorTable as never, {
            data: orders,
            columns,
            rowKey: (row: Order) => row.ref,
            caption: "Pedidos",
            viewKey: "teste-pedidos",
          }),
        ]),
    });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    const { useOperatorTableView } = await import("../../app/composables/useOperatorTableView");
    const view = useOperatorTableView("teste-pedidos");
    await nextTick();
    expect(view.columns.value.map((column) => column.id)).toEqual(["customer", "channel", "total_q"]);
    view.setDensity("comfortable");
    view.setVisible("channel", false);
    await nextTick();
    expect(table().getAttribute("data-density")).toBe("comfortable");
    expect([...table().querySelectorAll("th")].some((th) => th.textContent?.includes("Canal"))).toBe(false);
    const button = document.querySelector<HTMLElement>("[data-operator-table-view]")!;
    expect(button.getAttribute("aria-label")).toBe("Exibir: linhas e colunas (1 coluna oculta)");
    expect(button.className).toContain("max-sm:hidden");
  });
});
