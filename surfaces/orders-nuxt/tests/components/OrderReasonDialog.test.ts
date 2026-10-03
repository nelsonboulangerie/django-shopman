import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, mergeProps, ref, watch } from "vue";

import { mount } from "@vue/test-utils";

import OperatorReasonDialog from "../../../operator-kit/app/components/OperatorReasonDialog.vue";
import OrderReasonDialog from "../../app/components/OrderReasonDialog.vue";
import type { CancellationPresetGroupProjection, CancellationReason } from "../../app/types/orders";

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
  presets: CancellationPresetGroupProjection[];
  busy: boolean;
  marketplace: boolean;
  error: string;
}> = {}, options: { attachTo?: HTMLElement } = {}) {
  return mount(OrderReasonDialog, {
    props: { marketplace: Boolean(props.reasons?.length), open: true, mode: "reject", loading: false, reasons: [], presets: [], busy: false, ...props },
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

  it("mostra o seletor de códigos exigido, sem presets nem texto livre", () => {
    const w = mountDialog({ reasons, presets: [{ label: "", presets: ["Preset ignorado"] }] });
    expect(w.find("select").exists()).toBe(true);
    expect(w.find("textarea").exists()).toBe(false);
    expect(w.text()).not.toContain("Preset ignorado");
  });

  it("exige um código antes de confirmar e envia o código + descrição espelhada", async () => {
    const w = mountDialog({ mode: "reject", reasons });
    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("select").setValue("B");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Loja fechada", cancellationCode: "B" }]);
  });

  it("cancelar de iFood também usa o seletor obrigatório", async () => {
    const w = mountDialog({ mode: "cancel", reasons });
    const btn = confirmBtn(w, "Confirmar");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("select").setValue("A");
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Item em falta", cancellationCode: "A" }]);
  });
});

describe("OrderReasonDialog — canais comuns (presets + texto livre)", () => {
  it("recusar: presets + textarea; motivo é obrigatório; envia código vazio", async () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: [{ label: "", presets: ["Sem estoque", "Fora de área"] }] });
    expect(w.find("select").exists()).toBe(false);
    const pills = w.findAll("button").filter((b) => ["Sem estoque", "Fora de área"].includes(b.text()));
    expect(pills).toHaveLength(2);

    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await pills[0]!.trigger("click");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Sem estoque", cancellationCode: "" }]);
  });

  it("cancelar: motivo é opcional — confirma mesmo em branco", async () => {
    const w = mountDialog({ mode: "cancel", reasons: [], presets: [] });
    const btn = confirmBtn(w, "Confirmar");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "", cancellationCode: "" }]);
  });
});

describe("OrderReasonDialog — grupos e Outros", () => {
  const groups: CancellationPresetGroupProjection[] = [
    { label: "Produto", presets: ["Item indisponível no momento", "Sem um dos ingredientes hoje"] },
    { label: "Pagamento", presets: ["Pagamento não aprovado"] },
    { label: "", presets: ["Pedido em duplicidade"] },
  ];

  it("mostra cada grupo com o seu cabeçalho, na ordem recebida, e Outros por último", () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: groups });
    const rendered = w.findAll("[data-testid='reason-preset-group']");
    expect(rendered).toHaveLength(3);
    expect(rendered[0]!.find("p").text()).toBe("Produto");
    expect(rendered[0]!.findAll("button").map((b) => b.text())).toEqual([
      "Item indisponível no momento",
      "Sem um dos ingredientes hoje",
    ]);
    expect(rendered[1]!.find("p").text()).toBe("Pagamento");
    // Grupo sem rótulo: chips sem cabeçalho.
    expect(rendered[2]!.find("p").exists()).toBe(false);
    const chipTexts = w.find("[data-testid='reason-presets']").findAll("button").map((b) => b.text());
    expect(chipTexts.at(-1)).toBe("Outros");
  });

  it("Outros limpa o preset, foca o texto e nunca vira o motivo enviado", async () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: groups }, { attachTo: document.body });
    const chip = w.findAll("button").find((b) => b.text() === "Pagamento não aprovado")!;
    await chip.trigger("click");
    await w.find("[data-testid='reason-other']").trigger("click");
    await w.vm.$nextTick();
    const textarea = w.find("textarea");
    expect((textarea.element as HTMLTextAreaElement).value).toBe("");
    expect(document.activeElement).toBe(textarea.element);
    expect(chip.attributes("aria-pressed")).toBe("false");
    expect(w.find("[data-testid='reason-other']").attributes("aria-pressed")).toBe("true");

    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")).toBeUndefined();

    await textarea.setValue("Forno em manutenção hoje");
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Forno em manutenção hoje", cancellationCode: "" }]);
    w.unmount();
  });

  it("cancelar com Outros e texto vazio é bloqueado; sem Outros, vazio segue permitido", async () => {
    const w = mountDialog({ mode: "cancel", reasons: [], presets: groups });
    const btn = confirmBtn(w, "Confirmar");
    expect(btn.attributes("disabled")).toBeUndefined();
    await w.find("[data-testid='reason-other']").trigger("click");
    expect(btn.attributes("disabled")).toBeDefined();
    expect(w.find("[data-testid='reason-other-hint']").exists()).toBe(true);
    await btn.trigger("click");
    expect(w.emitted("confirm")).toBeUndefined();
    // Voltar a um preset devolve o cancelamento ao fluxo normal.
    await w.findAll("button").find((b) => b.text() === "Pedido em duplicidade")!.trigger("click");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Pedido em duplicidade", cancellationCode: "" }]);
  });

  it("reabrir desfaz o Outros", async () => {
    const w = mountDialog({ mode: "cancel", reasons: [], presets: groups });
    await w.find("[data-testid='reason-other']").trigger("click");
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    expect(w.find("[data-testid='reason-other']").attributes("aria-pressed")).toBe("false");
    expect(confirmBtn(w, "Confirmar").attributes("disabled")).toBeUndefined();
  });

  it("sem motivos configurados não há chips, nem Outros", () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: [] });
    expect(w.find("[data-testid='reason-other']").exists()).toBe(false);
    expect(w.find("textarea").exists()).toBe(true);
  });
});

describe("OrderReasonDialog — estados", () => {
  it("carregando: mostra aviso e esconde seletor/texto", () => {
    const w = mountDialog({ loading: true, reasons: [{ code: "A", description: "x" }] });
    expect(w.text()).toContain("Carregando motivos do iFood");
    expect(w.find("select").exists()).toBe(false);
    expect(w.find("textarea").exists()).toBe(false);
  });

  it("Voltar emite update:open=false", async () => {
    const w = mountDialog();
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")![0]).toEqual([false]);
  });

  it("reabrir limpa a seleção anterior", async () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: [{ label: "", presets: ["P"] }] });
    await w.findAll("button").find((b) => b.text() === "P")!.trigger("click");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeUndefined();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
  });
});


describe("motivos indisponíveis", () => {
  it("bloqueia cancelar durante leitura e não converte vazio iFood em texto livre", () => {
    const loading = mountDialog({ mode: "cancel", loading: true });
    expect(confirmBtn(loading, "Confirmar").attributes("disabled")).toBeDefined();
    const empty = mountDialog({ mode: "cancel", marketplace: true, reasons: [] });
    expect(empty.find("textarea").exists()).toBe(false);
    expect(empty.text()).toContain("não oferece motivos");
    expect(confirmBtn(empty, "Confirmar").attributes("disabled")).toBeDefined();
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
