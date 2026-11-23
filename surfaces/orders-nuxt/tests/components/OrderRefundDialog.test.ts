// Estornar UM pedido (#2727, item 5): o diálogo lê a prévia DESTA cobrança a cada
// abertura, vem com o disponível inteiro, e só confirma com a segunda marca.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import OrderRefundDialog from "../../app/components/OrderRefundDialog.vue";
import type { OrderRefundPreview } from "../../app/presentation/orderRefund";

const env = installNuxtGlobals();
vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn(), info: vi.fn() });

const action = {
  ref: "refund",
  kind: "mutation",
  label: "Estornar",
  priority: "danger",
  enabled: true,
  reason: "",
  href: "",
  method: "POST",
  payload_schema: { base_revision: "preview-base", expected_actor_id: 1 },
  idempotency: "required",
  confirmation: { required: true },
};

function preview(over: Partial<OrderRefundPreview> = {}): OrderRefundPreview {
  return {
    order_ref: "WEB-1",
    method_label: "Pix",
    paid_q: 3000,
    paid_display: "R$ 30,00",
    returned_q: 0,
    returned_display: "",
    available_q: 3000,
    available_display: "R$ 30,00",
    partial_allowed: true,
    blocked: false,
    block_reason: "",
    action,
    ...over,
  } as OrderRefundPreview;
}

// Os campos do Nuxt UI viram elementos nativos: o teste digita e marca de verdade.
const input = defineComponent({
  name: "NuxtInput",
  inheritAttrs: false,
  props: { modelValue: { type: String, default: "" } },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("input", {
        ...attrs,
        value: props.modelValue,
        onInput: (event: Event) => emit("update:modelValue", (event.target as HTMLInputElement).value),
      });
  },
});
const checkbox = defineComponent({
  name: "NuxtCheckbox",
  inheritAttrs: false,
  props: { modelValue: Boolean, label: { type: String, default: "" } },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("input", {
        ...attrs,
        type: "checkbox",
        checked: props.modelValue,
        onChange: (event: Event) => emit("update:modelValue", (event.target as HTMLInputElement).checked),
      });
  },
});
const button = defineComponent({
  name: "NuxtButton",
  inheritAttrs: false,
  props: { label: { type: String, default: "" }, disabled: Boolean, loading: Boolean },
  emits: ["click"],
  setup(props, { attrs, emit }) {
    return () => h("button", { ...attrs, disabled: props.disabled, onClick: () => emit("click") }, props.label);
  },
});
const modal = { template: "<div><slot name='body' /><slot name='footer' /></div>" };
// O grupo de rádio vira botões: o teste escolhe a cobrança de verdade.
const radios = defineComponent({
  name: "NuxtRadioGroup",
  inheritAttrs: false,
  props: { modelValue: { type: String, default: "" }, items: { type: Array, default: () => [] } },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h(
        "div",
        attrs,
        (props.items as Array<{ value: string; label: string; description: string }>).map((item) =>
          h("button", { "data-charge": item.value, onClick: () => emit("update:modelValue", item.value) }, `${item.label} ${item.description}`),
        ),
      );
  },
});
const stubs = {
  Icon: true,
  OperatorScreenState: true,
  NuxtModal: modal,
  NuxtFormField: { template: "<div><slot /></div>" },
  NuxtInput: input,
  NuxtCheckbox: checkbox,
  NuxtButton: button,
  NuxtRadioGroup: radios,
};

async function opened(read: OrderRefundPreview) {
  env.fetchMock.mockResolvedValueOnce(read);
  const w = mount(OrderRefundDialog, { props: { open: true, orderRef: "WEB-1", busy: false }, global: { stubs } });
  await flushPromises();
  return w;
}

beforeEach(() => env.reset());

describe("OrderRefundDialog", () => {
  it("lê a prévia deste pedido e abre com o disponível inteiro", async () => {
    const w = await opened(preview());

    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/orders/WEB-1/refund/preview/");
    expect(w.get("[data-refund-paid]").text()).toBe("Pago neste pedido: R$ 30,00 (Pix)");
    expect(w.get("[data-refund-available]").text()).toBe("Disponível para estorno: R$ 30,00");
    expect(w.find("[data-refund-returned]").exists()).toBe(false);
    expect((w.get("[aria-label='Valor a estornar']").element as HTMLInputElement).value).toBe("30,00");
  });

  it("só confirma com a segunda marca, e leva o valor digitado e a ação da prévia", async () => {
    const w = await opened(preview());
    const confirm = w.get("[data-refund-confirm]");
    expect(confirm.attributes("disabled")).toBeDefined();

    await w.get("[aria-label='Valor a estornar']").setValue("12,50");
    await w.get("[data-refund-confirm-check]").setValue(true);
    expect(confirm.text()).toBe("Estornar R$ 12,50");
    expect(confirm.attributes("disabled")).toBeUndefined();
    await confirm.trigger("click");

    expect(w.emitted("confirm")).toEqual([[{ contract: action, amountQ: 1250 }]]);
  });

  it("bloqueado pelo servidor: só o motivo, sem botão de estornar", async () => {
    const reason = "O valor desta cobrança já voltou inteiro ao cliente.";
    const w = await opened(preview({ blocked: true, block_reason: reason }));

    expect(w.get("[data-refund-block]").text()).toBe(reason);
    expect(w.find("[data-refund-confirm]").exists()).toBe(false);
    expect(w.find("[data-refund-values]").exists()).toBe(false);
  });

  it("mais de uma cobrança: escolher relê a prévia dela e confirma com ela, sem total (#3134)", async () => {
    const charges = [
      { intent_ref: "INT-1", method_label: "Pix", paid_display: "R$ 30,00", available_q: 3000, available_display: "R$ 30,00" },
      { intent_ref: "INT-2", method_label: "Pix", paid_display: "R$ 8,00", available_q: 800, available_display: "R$ 8,00" },
    ];
    const w = await opened(
      preview({ choose: true, choose_reason: "Este pedido tem mais de uma cobrança. Escolha qual estornar.", charges, intent_ref: "" }),
    );
    expect(w.get("[data-refund-choose]").text()).toBe("Este pedido tem mais de uma cobrança. Escolha qual estornar.");
    expect(w.find("[data-refund-values]").exists()).toBe(false);
    expect(w.find("[data-refund-confirm]").attributes("disabled")).toBeDefined();
    expect(w.text()).not.toContain("38,00");

    env.fetchMock.mockResolvedValueOnce(
      preview({ charges, intent_ref: "INT-2", paid_display: "R$ 8,00", available_q: 800, available_display: "R$ 8,00" }),
    );
    await w.get("[data-charge='INT-2']").trigger("click");
    await flushPromises();

    expect(env.fetchMock).toHaveBeenLastCalledWith("/api/v1/backstage/orders/WEB-1/refund/preview/", { query: { intent: "INT-2" } });
    expect(w.get("[data-refund-paid]").text()).toBe("Pago nesta cobrança: R$ 8,00 (Pix)");
    expect(w.text()).not.toContain("38,00");
    await w.get("[data-refund-confirm-check]").setValue(true);
    await w.get("[data-refund-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ contract: action, amountQ: 800, intentRef: "INT-2" }]]);
  });
});
