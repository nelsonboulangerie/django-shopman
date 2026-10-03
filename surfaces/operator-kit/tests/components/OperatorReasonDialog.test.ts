import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, mergeProps } from "vue";
import type { VueWrapper } from "vue";

import OperatorReasonDialog from "../../app/components/OperatorReasonDialog.vue";

// O diálogo de motivo do kit, testado na fonte. `UiDialog`, `UiButton` e
// `UiTextarea` são do app hospedeiro (o kit não registra módulo): aqui viram o
// elemento nativo, e o que se cobra é o contrato da peça.
const passthrough = { template: "<div><slot /></div>" };
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
  UiDialog: passthrough,
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
  UiButton: button,
  UiTextarea: textarea,
};

const mounted: VueWrapper[] = [];
async function mount(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorReasonDialog, {
    props: {
      open: true,
      title: "Cancelar a encomenda de Ana?",
      description: "O que já foi pago volta no mesmo meio.",
      confirmLabel: "Cancelar encomenda",
      ...props,
    },
    global: { stubs },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

const groups = [
  { label: "Produto", presets: ["Item indisponível no momento"] },
  { label: "", presets: ["Pedido em duplicidade"] },
];

describe("OperatorReasonDialog", () => {
  it("diz a consequência e confirma pelo rótulo de quem chama", async () => {
    const w = await mount();
    expect(w.text()).toContain("O que já foi pago volta no mesmo meio.");
    const confirm = w.get("[data-reason-confirm]");
    expect(confirm.text()).toBe("Cancelar encomenda");
    expect(confirm.attributes("disabled")).toBeUndefined();
    await w.get("[data-reason-input]").setValue("  Cliente desistiu  ");
    await confirm.trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Cliente desistiu", code: "" }]]);
  });

  it("motivo exigido: confirmar em branco não sai", async () => {
    const w = await mount({ required: true });
    expect(w.get("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await w.get("[data-reason-input]").setValue("Fora de área");
    expect(w.get("[data-reason-confirm]").attributes("disabled")).toBeUndefined();
  });

  it("motivos prontos: um toque escolhe; Outros exige texto e nunca vira o motivo", async () => {
    const w = await mount({ presets: groups });
    const chips = w.findAll("[data-reason-preset]");
    expect(chips.map((c) => c.text())).toEqual(["Item indisponível no momento", "Pedido em duplicidade"]);
    await chips[1]!.trigger("click");
    expect(chips[1]!.attributes("aria-pressed")).toBe("true");
    await w.get("[data-testid='reason-other']").trigger("click");
    expect(chips[1]!.attributes("aria-pressed")).toBe("false");
    expect(w.get("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await w.get("[data-reason-input]").setValue("Forno em manutenção hoje");
    await w.get("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Forno em manutenção hoje", code: "" }]]);
  });

  it("motivo codificado: escolhe da lista e espelha a descrição no motivo", async () => {
    const w = await mount({ coded: true, codedReasons: [{ code: "B", description: "Loja fechada" }], presets: groups });
    expect(w.find("[data-reason-input]").exists()).toBe(false);
    expect(w.find("[data-reason-preset]").exists()).toBe(false);
    expect(w.get("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await w.get("select").setValue("B");
    await w.get("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Loja fechada", code: "B" }]]);
  });

  it("fechar com texto digitado pergunta dentro do diálogo, sem window.confirm", async () => {
    const nativeConfirm = vi.fn(() => true);
    vi.stubGlobal("confirm", nativeConfirm);
    const w = await mount();
    await w.get("[data-reason-input]").setValue("Cliente desistiu");
    await w.get("[data-reason-back]").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.find("[data-reason-discard]").exists()).toBe(true);
    await w.get("[data-reason-keep]").trigger("click");
    expect((w.get("[data-reason-input]").element as HTMLTextAreaElement).value).toBe("Cliente desistiu");
    await w.get("[data-reason-back]").trigger("click");
    await w.get("[data-reason-discard-confirm]").trigger("click");
    expect(w.emitted("update:open")).toEqual([[false]]);
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("ocupado: não fecha nem confirma de novo", async () => {
    const w = await mount({ busy: true });
    await w.get("[data-reason-back]").trigger("click");
    await w.get("[data-reason-confirm]").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.emitted("confirm")).toBeUndefined();
  });

  it("erro ao ler os motivos: bloqueia e oferece consultar de novo", async () => {
    const w = await mount({ error: "Não foi possível consultar os motivos." });
    expect(w.get("[role='alert']").text()).toContain("Não foi possível consultar os motivos.");
    expect(w.get("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await w.findAll("button").find((b) => b.text() === "Consultar novamente")!.trigger("click");
    expect(w.emitted("retry")).toHaveLength(1);
  });
});
