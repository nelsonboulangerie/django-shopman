import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";

import { flushPromises, mount } from "@vue/test-utils";

import CustomerMergeDialog from "../../app/components/CustomerMergeDialog.vue";
import type { CustomerDetailProjection, MergePreviewProjection } from "../../app/generated/ordersContract";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("watchDebounced", (source: unknown, cb: (value: string) => void) => watch(source as never, cb as never));
vi.stubGlobal("httpErrorMessage", (_error: unknown, fallback: string) => fallback);

const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  Icon: true,
  UiDialog: passthrough,
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
};

const ifood: CustomerDetailProjection = {
  ref: "IF-AAAA0001", name: "Maria Souza", is_active: true, merged_into_ref: "",
  phone_display: "", email: "", document_display: "", birthday_display: "",
  source_label: "iFood", is_ifood: true, created_display: "", notes: "",
  orders_label: "1 pedido", total_spent_display: "", last_order_display: "",
  identifiers: [], addresses: [], recent_orders: [], candidates: [], actions: [],
};
const balcao = { ref: "CLI-MARIA", name: "Maria Souza", phone_display: "(43) 99999-0000", source_label: "Balcão" };

function previewFor(source: string, target: string): MergePreviewProjection {
  return {
    source: { ref: source, name: "Maria", phone_display: "", document_display: "", source_label: "", orders_label: "" },
    target: { ref: target, name: "Maria", phone_display: "", document_display: "", source_label: "", orders_label: "" },
    moves: [{ ref: "orders", count: 1, label: "1 pedido" }],
    fills: [],
    loyalty_label: "",
    summary: `${source} deixa de existir; tudo passa para ${target}.`,
    undo_notice: "Dá para desfazer por 24 horas.",
    actions: [],
  };
}

let fetchMergePreview: ReturnType<typeof vi.fn>;
let postMerge: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMergePreview = vi.fn(async (source: string, target: string) => ({ preview: previewFor(source, target) }));
  postMerge = vi.fn(async (source: string, target: string) => ({ ok: true, source_ref: source, target_ref: target, audit_id: "a1" }));
  vi.stubGlobal("fetchMergePreview", fetchMergePreview);
  vi.stubGlobal("postMerge", postMerge);
  vi.stubGlobal("searchCustomers", vi.fn(async () => []));
});

afterEach(() => { vi.clearAllMocks(); });

function mountDialog() {
  return mount(CustomerMergeDialog, {
    props: { open: true, current: ifood, initialOther: balcao },
    global: { stubs },
  });
}

describe("CustomerMergeDialog", () => {
  it("sugere que fique o cadastro com telefone e mostra a prévia desse par", async () => {
    const wrapper = mountDialog();
    await flushPromises();

    expect(fetchMergePreview).toHaveBeenLastCalledWith("IF-AAAA0001", "CLI-MARIA");
    expect(wrapper.find("[data-merge-side='target']").text()).toContain("CLI-MARIA");
    expect(wrapper.find("[data-merge-side='source']").text()).toContain("IF-AAAA0001");
    expect(wrapper.find("[data-merge-moves]").text()).toContain("1 pedido");
  });

  it("trocar quem fica refaz a prévia com o par invertido", async () => {
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.find("[data-merge-swap]").trigger("click");
    await flushPromises();

    expect(fetchMergePreview).toHaveBeenLastCalledWith("CLI-MARIA", "IF-AAAA0001");
    expect(wrapper.find("[data-merge-side='target']").text()).toContain("IF-AAAA0001");
  });

  it("unificar manda o par da prévia e avisa quem ficou", async () => {
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.find("[data-merge-confirm]").trigger("click");
    await flushPromises();

    expect(postMerge).toHaveBeenCalledWith("IF-AAAA0001", "CLI-MARIA");
    expect(wrapper.emitted("merged")?.[0]).toEqual([{ targetRef: "CLI-MARIA", sourceRef: "IF-AAAA0001" }]);
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("sem prévia não há como unificar", async () => {
    fetchMergePreview.mockRejectedValueOnce(new Error("boom"));
    const wrapper = mountDialog();
    await flushPromises();

    expect(wrapper.text()).toContain("Não foi possível calcular o que muda.");
    expect(wrapper.find("[data-merge-confirm]").attributes("disabled")).toBeDefined();
  });

  it("recusa do servidor fica na caixa, sem fechar", async () => {
    postMerge.mockRejectedValueOnce(new Error("422"));
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.find("[data-merge-confirm]").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Não foi possível unificar os cadastros.");
    expect(wrapper.emitted("merged")).toBeUndefined();
  });
});
