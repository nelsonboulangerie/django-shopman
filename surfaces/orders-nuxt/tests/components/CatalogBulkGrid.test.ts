import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import CatalogBulkGrid from "../../app/components/CatalogBulkGrid.vue";
import { useGridEdit } from "../../../operator-kit/app/composables/useGridEdit";
import OperatorConfirmDialog from "../../../operator-kit/app/components/OperatorConfirmDialog.vue";
import {
  answerConfirm,
  useConfirm,
} from "../../../operator-kit/app/composables/useConfirm";
import type {
  CatalogRowProjection,
  SurfaceProjection,
} from "../../app/types/catalog";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("useGridEdit", useGridEdit);
vi.stubGlobal("useConfirm", useConfirm);
let archiveDialog: ReturnType<typeof mount> | null = null;
afterEach(() => {
  answerConfirm(false);
  archiveDialog?.unmount();
  archiveDialog = null;
});

const OperatorTableStub = defineComponent({
  props: {
    data: { type: Array, default: () => [] },
    rowSelection: { type: Object, default: () => ({}) },
  },
  emits: ["update:rowSelection"],
  setup(props, { emit }) {
    return () =>
      h(
        "div",
        props.data.map((item: any) =>
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
        ),
      );
  },
});

const row = (sku: string, active = true) =>
  ({
    sku,
    name: `Produto ${sku}`,
    is_active: active,
    cells: [],
  }) as CatalogRowProjection;

const surface = {
  ref: "web",
  name: "Loja online",
  short_name: "Loja",
} as SurfaceProjection;

function grid(rows = [row("A"), row("B")]) {
  return mount(CatalogBulkGrid, {
    props: { open: true, rows, surfaces: [surface] },
    global: { stubs: { OperatorTable: OperatorTableStub } },
  });
}

describe("arquivamento no tabelão", () => {
  it("seleciona produtos e emite um único lote, sem campo is_active", async () => {
    const wrapper = grid();
    const boxes = wrapper.findAll("[data-operator-table-select]");
    await boxes[0]!.trigger("click");
    await boxes[1]!.trigger("click");

    const action = wrapper.get("[data-bulk-archive]");
    expect(action.text()).toContain("Arquivar");
    archiveDialog = mount(OperatorConfirmDialog, { attachTo: document.body });
    await action.trigger("click");
    await flushPromises();
    expect(document.body.textContent).toContain(
      "Os produtos saem do cardápio, dos canais e das listas.",
    );
    await archiveDialog.get("[data-operator-confirm-act]").trigger("click");
    await flushPromises();
    expect(wrapper.emitted("archive")).toEqual([
      [
        [
          { sku: "A", base_is_active: true },
          { sku: "B", base_is_active: true },
        ],
        false,
      ],
    ]);
    expect(wrapper.find('input[name="is_active"]').exists()).toBe(false);
  });

  it("mostra recibo por linha e oferece Desfazer cronometrado", async () => {
    const wrapper = grid();
    await wrapper.setProps({
      archiveReceipt: {
        ok: true,
        outcome: "applied",
        intention: "archive-1",
        applied: [
          {
            index: 0,
            sku: "A",
            name: "Produto A",
            before_is_active: true,
            is_active: false,
            changed: true,
          },
        ],
        conflicts: [],
        errors: [],
        server_now: new Date().toISOString(),
        undo_until: new Date(Date.now() + 10_000).toISOString(),
      },
    });

    expect(wrapper.get("[data-archive-receipt]").text()).toContain(
      "Produto A: arquivado",
    );
    const undo = wrapper.get("[data-bulk-archive-undo]");
    expect(undo.text()).toContain("Desfazer");
    await undo.trigger("click");
    expect(wrapper.emitted("archive")?.at(-1)).toEqual([
      [{ sku: "A", base_is_active: false }],
      true,
    ]);
  });
});
