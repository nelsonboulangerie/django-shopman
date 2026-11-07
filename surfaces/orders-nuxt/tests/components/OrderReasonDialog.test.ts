import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, mergeProps, ref, watch } from "vue";

import { mount } from "@vue/test-utils";

import OperatorReasonDialog from "../../../operator-kit/app/components/OperatorReasonDialog.vue";
import OrderReasonDialog from "../../app/components/OrderReasonDialog.vue";
import type { CancelReasonProjection, CancellationReason } from "../../app/types/orders";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);

// UiDialog e partes viram passthrough de slot — o miolo (seletor/textarea/botões) é o
// que interessa testar; o shell modal é território de e2e.
const passthrough = { template: "<div><slot /></div>" };
const nativeSelect = defineComponent({
  inheritAttrs: false,
  props: { modelValue: { default: undefined } },
  emits: ["update:modelValue", "change"],
  setup(props, { attrs, emit, slots }) {
    return () =>
      h(
        "select",
        mergeProps(attrs, {
          value: props.modelValue,
          onChange: (event: Event) => {
            emit(
              "update:modelValue",
              (event.target as HTMLSelectElement).value,
            );
            emit("change", event);
          },
        }),
        slots.default?.(),
      );
  },
});
// Botão e campo da casa viram o elemento nativo: o que se testa é o contrato do
// diálogo de motivo (o `OperatorReasonDialog` do operator-kit entra de verdade).
const button = defineComponent({
  inheritAttrs: false,
  props: { loading: Boolean, variant: { type: String, default: undefined } },
  setup(_props, { attrs, slots }) {
    return () => h("button", attrs, slots.default?.());
  },
});
const textarea = defineComponent({
  inheritAttrs: false,
  props: { modelValue: { type: String, default: "" } },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("textarea", mergeProps(attrs, {
        value: props.modelValue,
        onInput: (event: Event) => emit("update:modelValue", (event.target as HTMLTextAreaElement).value),
      }));
  },
});
const stubs = {
  UiButton: button,
  UiTextarea: textarea,
  UiDialog: passthrough,
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
  UiNativeSelect: nativeSelect,
};

function mountDialog(props: Partial<{
  open: boolean;
  mode: "reject" | "cancel";
  loading: boolean;
  reasons: CancellationReason[];
  cancelReasons: CancelReasonProjection[];
  busy: boolean;
  marketplace: boolean;
  error: string;
  initialKey: string;
}> = {}, options: { attachTo?: HTMLElement } = {}) {
  return mount(OrderReasonDialog, {
    props: { marketplace: Boolean(props.reasons?.length), open: true, mode: "reject", loading: false, reasons: [], cancelReasons: [], busy: false, ...props },
    global: { stubs, components: { OperatorReasonDialog } },
    ...options,
  });
}

const confirmBtn = (w: ReturnType<typeof mountDialog>, label: string) =>
  w.findAll("button").find((b) => b.text() === label)!;

describe("OrderReasonDialog — iFood (marketplace)", () => {
  const reasons: CancellationReason[] = [
    { code: "A", description: "Item em falta" },
    { code: "B", description: "Loja fechada" },
  ];

  it("mostra o seletor de códigos exigido, sem a lista da casa nem texto livre", () => {
    const w = mountDialog({ reasons, cancelReasons: [{ key: "other", label: "Outro motivo", customer_text: "x" }] });
    expect(w.find("select").exists()).toBe(true);
    expect(w.find("textarea").exists()).toBe(false);
    expect(w.text()).not.toContain("Outro motivo");
  });

  it("exige um código antes de confirmar e envia o código + descrição espelhada", async () => {
    const w = mountDialog({ mode: "reject", reasons });
    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("select").setValue("B");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Loja fechada", cancellationCode: "B", reasonKey: "" }]);
  });

  it("cancelar de iFood também usa o seletor obrigatório", async () => {
    const w = mountDialog({ mode: "cancel", reasons });
    const btn = confirmBtn(w, "Cancelar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("select").setValue("A");
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Item em falta", cancellationCode: "A", reasonKey: "" }]);
  });
});

describe("OrderReasonDialog — recusar em canal comum: a MESMA lista do cancelar (beta 06/11)", () => {
  const cancelReasons: CancelReasonProjection[] = [
    { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou e não conseguimos preparar o pedido completo." },
    { key: "customer_request", label: "O cliente pediu", customer_text: "Conforme sua solicitação." },
  ];

  it("recusar escolhe da lista única, mostra a frase do cliente e envia a chave", async () => {
    const w = mountDialog({ mode: "reject", cancelReasons }, { attachTo: document.body });
    expect(w.text()).toContain("O cliente recebe o aviso com a frase do motivo.");
    expect(w.text()).toContain("Observação interna (opcional)");
    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    const radios = w.findAll('[data-reason-keyed] [role="radio"]');
    expect(radios.map((r) => r.attributes("data-reason-key"))).toEqual(["out_of_stock", "customer_request"]);
    await radios[1]!.trigger("click");
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Conforme sua solicitação.");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "", cancellationCode: "", reasonKey: "customer_request" }]);
    w.unmount();
  });
});

describe("OrderReasonDialog — cancelar em canal comum (lista única, P1-10)", () => {
  const cancelReasons: CancelReasonProjection[] = [
    { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou e não conseguimos preparar o pedido completo." },
    { key: "other", label: "Outro motivo", customer_text: "Sentimos muito pelo imprevisto." },
  ];

  it("o motivo é obrigatório: Confirmar só acende com um da lista, nunca com texto", async () => {
    const w = mountDialog({ mode: "cancel", cancelReasons }, { attachTo: document.body });
    expect(w.text()).toContain("Observação interna (opcional)");
    const btn = confirmBtn(w, "Cancelar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("textarea").setValue("Faltou farinha");
    expect(btn.attributes("disabled")).toBeDefined();
    const radios = w.findAll('[data-reason-keyed] [role="radio"]');
    expect(radios.map((r) => r.attributes("data-reason-key"))).toEqual(["out_of_stock", "other"]);
    await radios[0]!.trigger("click");
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Um dos itens acabou");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Faltou farinha", cancellationCode: "", reasonKey: "out_of_stock" }]);
    w.unmount();
  });
});

describe("Pix vencido: o cancelar abre com o motivo marcado (beta 05/11: GES-05, GES-16)", () => {
  const cancelReasons: CancelReasonProjection[] = [
    { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." },
    { key: "payment_not_confirmed", label: "Pagamento não confirmado", customer_text: "Não recebemos a confirmação do pagamento a tempo." },
  ];

  it("o motivo chega marcado e Confirmar já acende; o operador ainda pode trocar", async () => {
    const w = mountDialog({ mode: "cancel", cancelReasons, open: false, initialKey: "payment_not_confirmed" }, { attachTo: document.body });
    await w.setProps({ open: true });
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Não recebemos a confirmação");
    const btn = confirmBtn(w, "Cancelar pedido");
    expect(btn.attributes("disabled")).toBeUndefined();
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "", cancellationCode: "", reasonKey: "payment_not_confirmed" }]);
    w.unmount();
  });
});

describe("OrderReasonDialog — estados", () => {
  it("carregando: mostra aviso e esconde seletor/texto", () => {
    const w = mountDialog({ loading: true, reasons: [{ code: "A", description: "x" }] });
    expect(w.text()).toContain("Carregando motivos do iFood");
    expect(w.find("select").exists()).toBe(false);
    expect(w.find("textarea").exists()).toBe(false);
  });

  it("fora do iFood o carregando não fala do iFood (beta 05/11: GES-06)", () => {
    const w = mountDialog({ mode: "cancel", loading: true, marketplace: false });
    expect(w.text()).toContain("Carregando motivos…");
    expect(w.text()).not.toContain("iFood");
  });

  it("Voltar emite update:open=false", async () => {
    const w = mountDialog();
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")![0]).toEqual([false]);
  });

  it("reabrir limpa a seleção anterior", async () => {
    const w = mountDialog({ mode: "reject", cancelReasons: [{ key: "other", label: "Outro motivo", customer_text: "Sentimos muito." }] });
    await w.find('[data-reason-keyed] [role="radio"]').trigger("click");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeUndefined();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
  });
});


describe("motivos indisponíveis", () => {
  it("bloqueia cancelar durante leitura e não converte vazio iFood em texto livre", () => {
    const loading = mountDialog({ mode: "cancel", loading: true });
    expect(confirmBtn(loading, "Cancelar pedido").attributes("disabled")).toBeDefined();
    const empty = mountDialog({ mode: "cancel", marketplace: true, reasons: [] });
    expect(empty.find("textarea").exists()).toBe(false);
    expect(empty.text()).toContain("não oferece motivos");
    expect(confirmBtn(empty, "Cancelar pedido").attributes("disabled")).toBeDefined();
  });
  it("mantém seleção no erro e permite consultar novamente sem reabrir", async () => {
    const w = mountDialog({ marketplace: true, reasons: [{ code: "A", description: "Motivo" }] });
    await w.find("select").setValue("A");
    await w.setProps({ error: "Consulta indisponível" });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
    await w.findAll("button").find(b => b.text() === "Consultar novamente")!.trigger("click");
    expect(w.emitted("retry")).toHaveLength(1);
    await w.setProps({ error: "", reasons: [{ code: "A", description: "Motivo" }] });
    expect((w.find("select").element as HTMLSelectElement).value).toBe("A");
    await w.setProps({ reasons: [{ code: "B", description: "Novo" }] });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
  });
});


describe("descarte explícito do motivo", () => {
  // A confirmação mora DENTRO do diálogo (contrato de modal da casa): nada de
  // `window.confirm`, que o navegador desenha fora da tela do operador.
  beforeEach(() => { window.confirm = vi.fn(); });
  afterEach(() => vi.restoreAllMocks());
  it("preserva texto quando a pessoa recusa descartar", async () => {
    const w = mountDialog();
    await w.find("textarea").setValue("Contexto importante");
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.find("[data-reason-discard]").exists()).toBe(true);
    await confirmBtn(w, "Continuar escrevendo").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.find("[data-reason-discard]").exists()).toBe(false);
    expect(w.find("textarea").element.value).toBe("Contexto importante");
    expect(window.confirm).not.toHaveBeenCalled();
  });
  it("permite descartar explicitamente e informa o estado do draft", async () => {
    const w = mountDialog();
    await w.find("textarea").setValue("Contexto importante");
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([true]);
    await confirmBtn(w, "Voltar").trigger("click");
    await confirmBtn(w, "Descartar").trigger("click");
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(window.confirm).not.toHaveBeenCalled();
    await w.setProps({ open: false });
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
    await w.setProps({ open: true });
    expect(w.find("textarea").element.value).toBe("");
    expect(w.find("[data-reason-discard]").exists()).toBe(false);
  });
  it("fecha draft vazio sem confirmação redundante", async () => {
    const w = mountDialog();
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(w.find("[data-reason-discard]").exists()).toBe(false);
  });
  it("não dispensa o editor enquanto a operação está pendente", async () => {
    const w = mountDialog({ busy: true });
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
  });
});
