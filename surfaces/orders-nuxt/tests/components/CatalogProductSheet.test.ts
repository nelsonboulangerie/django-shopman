import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import CatalogProductSheet from "../../app/components/CatalogProductSheet.vue";
import { useGridEdit } from "../../../operator-kit/app/composables/useGridEdit";
import OperatorConfirmDialog from "../../../operator-kit/app/components/OperatorConfirmDialog.vue";
import {
  answerConfirm,
  useConfirm,
} from "../../../operator-kit/app/composables/useConfirm";
import type {
  CatalogRowProjection,
  ProductSheet,
  ProductSheetRow,
} from "../../app/types/catalog";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useGridEdit", useGridEdit);
vi.stubGlobal("useConfirm", useConfirm);
let dialog: ReturnType<typeof mount> | null = null;
afterEach(() => {
  answerConfirm(false);
  dialog?.unmount();
  dialog = null;
});

const OperatorTableStub = defineComponent({
  props: {
    data: { type: Array, default: () => [] },
    rowSelection: { type: Object, default: () => ({}) },
  },
  emits: ["update:rowSelection"],
  setup(props, { emit, slots }) {
    return () =>
      h(
        "div",
        props.data.flatMap((item: any) => [
          h(
            "button",
            {
              "data-operator-table-select": item.sku,
              onClick: () =>
                emit("update:rowSelection", {
                  ...props.rowSelection,
                  [item.sku]: !props.rowSelection[item.sku],
                }),
            },
            item.sku,
          ),
          slots["product-cell"]?.({ row: { original: item } }),
          slots["name-cell"]?.({ row: { original: item } }),
          slots["price-cell"]?.({ row: { original: item } }),
        ]),
      );
  },
});

const sheetRow = (sku: string): ProductSheetRow => ({
  sku,
  is_active: true,
  name: `Produto ${sku}`,
  short_description: "",
  base_price_q: 500,
  unit: "un",
  fiscal: { profile: "", ncm: "", cest: "", origin: "0" },
  fiscal_warnings: [],
  revisions: { name: `r-${sku}`, short_description: `d-${sku}`, base_price_q: `p-${sku}` },
});

const sheet: ProductSheet = {
  rows: [sheetRow("B"), sheetRow("A"), sheetRow("FORA")],
  fiscal_profiles: [],
  fiscal_origins: [{ key: "0", name: "Nacional" }],
};

function mountSheet() {
  return mount(CatalogProductSheet, {
    props: {
      open: true,
      rows: [{ sku: "A" }, { sku: "B" }] as CatalogRowProjection[],
      sheet,
    },
    global: { stubs: { OperatorTable: OperatorTableStub } },
  });
}

describe("tabelão de produtos", () => {
  it("segue a página do catálogo e cola duas colunas de uma vez", async () => {
    const wrapper = mountSheet();
    const cells = wrapper.findAll("[data-sheet-cell$='|name']");
    expect(cells.map((cell) => cell.attributes("data-sheet-cell"))).toEqual([
      "A|name",
      "B|name",
    ]);
    await cells[0]!.trigger("paste", {
      clipboardData: { getData: () => "Pão A\tCrocante\t6,00\nPão B\tMacio\t7,00" },
    });
    await wrapper.get("[data-sheet-save]").trigger("click");
    expect(wrapper.emitted("save")).toEqual([
      [
        [
          {
            sku: "A",
            patch: { name: "Pão A", short_description: "Crocante", base_price_q: 600 },
            base_revisions: { name: "r-A", short_description: "d-A", base_price_q: "p-A" },
          },
          {
            sku: "B",
            patch: { name: "Pão B", short_description: "Macio", base_price_q: 700 },
            base_revisions: { name: "r-B", short_description: "d-B", base_price_q: "p-B" },
          },
        ],
      ],
    ]);
  });

  it("marca a célula com erro e não envia a linha", async () => {
    const wrapper = mountSheet();
    await wrapper.get("[data-sheet-cell='A|price'] input").setValue("abc");
    expect(wrapper.get("[data-cell-problem='A|price']").text()).toBe(
      "Preço inválido.",
    );
    await wrapper.get("[data-sheet-save]").trigger("click");
    expect(wrapper.emitted("save")).toBeUndefined();
    expect(wrapper.get("[data-row-error='A']").text()).toContain(
      "Corrija as células marcadas",
    );
  });

  it("desfaz a última edição", async () => {
    const wrapper = mountSheet();
    const input = wrapper.get("[data-sheet-cell='A|name'] input");
    await input.setValue("Outro nome");
    await wrapper.get("[data-sheet-undo]").trigger("click");
    expect(
      (wrapper.get("[data-sheet-cell='A|name'] input").element as HTMLInputElement).value,
    ).toBe("Produto A");
  });

  it("duplica os selecionados depois de confirmar", async () => {
    const wrapper = mountSheet();
    const boxes = wrapper.findAll("[data-operator-table-select]");
    await boxes[0]!.trigger("click");
    await boxes[1]!.trigger("click");
    dialog = mount(OperatorConfirmDialog, { attachTo: document.body });
    await wrapper.get("[data-sheet-duplicate]").trigger("click");
    await flushPromises();
    expect(document.body.textContent).toContain("Cada cópia nasce oculta e fora de venda");
    await dialog.get("[data-operator-confirm-act]").trigger("click");
    await flushPromises();
    expect(wrapper.emitted("duplicate")).toEqual([[["A", "B"]]]);
  });

  it("mostra o recibo por linha com o campo do conflito", async () => {
    const wrapper = mountSheet();
    await wrapper.setProps({
      receipt: {
        ok: true,
        outcome: "applied",
        applied: [],
        conflicts: [
          { index: 0, sku: "B", detail: "O produto mudou.", conflicting_fields: ["name"] },
        ],
        errors: [],
      },
    });
    expect(wrapper.get("[data-row-error='B']").text()).toBe("Nome: O produto mudou.");
  });
});
