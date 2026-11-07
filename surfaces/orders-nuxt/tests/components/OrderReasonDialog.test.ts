import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, mergeProps, ref, watch } from "vue";

import { mount } from "@vue/test-utils";

import OperatorReasonDialog from "../../../operator-kit/app/components/OperatorReasonDialog.vue";
import OrderReasonDialog from "../../app/components/OrderReasonDialog.vue";
import type { CancelReasonProjection } from "../../app/types/orders";

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
  cancelReasons: CancelReasonProjection[];
  busy: boolean;
  marketplace: boolean;
  initialKey: string;
}> = {}, options: { attachTo?: HTMLElement } = {}) {
  return mount(OrderReasonDialog, {
    props: { marketplace: false, open: true, mode: "reject", cancelReasons: LIST, busy: false, ...props },
    global: { stubs, components: { OperatorReasonDialog } },
    attachTo: document.body,
    ...options,
  });
}

const confirmBtn = (w: ReturnType<typeof mountDialog>, label: string) =>
  w.findAll("button").find((b) => b.text() === label)!;
const radioKeys = (w: ReturnType<typeof mountDialog>) =>
  w.findAll('[data-reason-keyed] [role="radio"]').map((r) => r.attributes("data-reason-key"));

// A lista única de motivos (dono, 07/11/2026): a mesma para recusar e cancelar.
const LIST: CancelReasonProjection[] = [
  { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou e não conseguimos preparar o pedido completo.", offered_on_ifood: true },
  { key: "high_demand", label: "Muitos pedidos agora", customer_text: "Estamos com muitos pedidos agora e não conseguiríamos preparar o seu no horário.", offered_on_ifood: true },
  { key: "customer_request", label: "O cliente pediu", customer_text: "Conforme sua solicitação.", offered_on_ifood: false },
  { key: "payment_not_confirmed", label: "Pagamento não confirmado", customer_text: "Não recebemos a confirmação do pagamento a tempo.", offered_on_ifood: false },
  { key: "other", label: "Outro motivo", customer_text: "Sentimos muito pelo imprevisto.", offered_on_ifood: true },
];

describe("OrderReasonDialog — uma lista para recusar e cancelar", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it.each(["reject", "cancel"] as const)("%s: escolhe da lista, mostra a frase do cliente e envia a chave e a nota interna", async (mode) => {
    const w = mountDialog({ mode });
    const label = mode === "reject" ? "Recusar pedido" : "Cancelar pedido";
    expect(w.text()).toContain("O cliente recebe o aviso com a frase do motivo.");
    expect(w.text()).toContain("Observação interna (opcional)");
    expect(radioKeys(w)).toEqual(["out_of_stock", "high_demand", "customer_request", "payment_not_confirmed", "other"]);
    const btn = confirmBtn(w, label);
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("textarea").setValue("Faltou farinha");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.findAll('[data-reason-keyed] [role="radio"]')[0]!.trigger("click");
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Um dos itens acabou");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reasonKey: "out_of_stock", internalNote: "Faltou farinha" }]);
    w.unmount();
  });

  it("no iFood esconde o que o iFood não oferece e avisa que o iFood recebe o motivo", () => {
    const w = mountDialog({ marketplace: true });
    expect(radioKeys(w)).toEqual(["out_of_stock", "high_demand", "other"]);
    expect(w.text()).toContain("O iFood e o cliente recebem o aviso com ele.");
    w.unmount();
  });

  it("Pix vencido: o cancelar abre com o motivo marcado e Confirmar já acende", async () => {
    const w = mountDialog({ mode: "cancel", open: false, initialKey: "payment_not_confirmed" });
    await w.setProps({ open: true });
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Não recebemos a confirmação");
    const btn = confirmBtn(w, "Cancelar pedido");
    expect(btn.attributes("disabled")).toBeUndefined();
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reasonKey: "payment_not_confirmed", internalNote: "" }]);
    w.unmount();
  });

  it("reabrir limpa a seleção anterior", async () => {
    const w = mountDialog();
    await w.find('[data-reason-keyed] [role="radio"]').trigger("click");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeUndefined();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
    w.unmount();
  });

  it("Voltar sem rascunho fecha; com nota digitada pergunta dentro do diálogo", async () => {
    window.confirm = vi.fn();
    const w = mountDialog();
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")![0]).toEqual([false]);
    await w.find("textarea").setValue("Contexto importante");
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.find("[data-reason-discard]").exists()).toBe(true);
    await confirmBtn(w, "Continuar escrevendo").trigger("click");
    expect((w.find("textarea").element as HTMLTextAreaElement).value).toBe("Contexto importante");
    expect(window.confirm).not.toHaveBeenCalled();
    w.unmount();
  });

  it("não dispensa o editor enquanto a operação está pendente", async () => {
    const w = mountDialog({ busy: true });
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    w.unmount();
  });
});
