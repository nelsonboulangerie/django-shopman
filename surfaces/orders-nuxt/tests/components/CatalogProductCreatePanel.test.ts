import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref, toValue, watch } from "vue";

import CatalogProductCreatePanel from "../../app/components/CatalogProductCreatePanel.vue";
import OperatorConfirmDialog from "../../../operator-kit/app/components/OperatorConfirmDialog.vue";
import { answerConfirm } from "../../../operator-kit/app/composables/useConfirm";

// O cadastro de produto do Gestor consumindo o casco canônico do kit: as seções
// (intenção, GTIN, rascunho, campos), o estado sujo, a barra de ação na base e a
// pergunta antes de descartar.

vi.stubGlobal("computed", computed);
vi.stubGlobal("reactive", reactive);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("toValue", toValue);

const scanner = {
  open: ref(false),
  video: ref<HTMLVideoElement | null>(null),
  hint: ref(""),
  error: ref(""),
  start: vi.fn(),
  stop: vi.fn(),
};
vi.stubGlobal("useBarcodeScanner", () => scanner);

let dialog: ReturnType<typeof mount> | null = null;

afterEach(() => {
  answerConfirm(false);
  dialog?.unmount();
  dialog = null;
});

function panel(extra: Record<string, unknown> = {}) {
  return mount(CatalogProductCreatePanel, {
    props: {
      open: true,
      mode: "create",
      source: null,
      suggestedSku: "",
      suggestedName: "",
      busy: false,
      error: "",
      draft: null,
      draftBusy: false,
      draftError: "",
      enhance: vi.fn(),
      upload: vi.fn(),
      adminBaseUrl: "",
      ...extra,
    },
  });
}

async function showConfirm() {
  dialog = mount(OperatorConfirmDialog, { attachTo: document.body });
  await flushPromises();
  return dialog;
}

describe("cadastro de produto no casco do kit", () => {
  it("abre na intenção; escolher conduz ao campo de código de barras e aos dados", async () => {
    const w = panel();
    expect(w.text()).toContain("O que você vai cadastrar?");
    expect(w.find('[data-focus-target="intent"]').exists()).toBe(true);

    await w.get('[data-intent="revenda"]').trigger("click");
    expect(w.find('[data-focus-target="gtin"]').exists()).toBe(true);
    expect(w.find('[data-focus-target="fields"]').exists()).toBe(true);
    expect(w.text()).toContain("Dados do produto");
    expect(w.find("[data-testid='create-sku']").attributes("data-focus-control")).toBeDefined();
  });

  it("sem mexer em nada, descartar fecha direto", async () => {
    const w = panel();
    await w.get("[data-testid='create-discard']").trigger("click");
    await flushPromises();
    expect(w.emitted("update:open")).toEqual([[false]]);
    expect(w.emitted("discard")).toBeUndefined();
  });

  it("com alteração, o descarte pergunta na caixa da casa e continuar protege o que foi digitado", async () => {
    const w = panel();
    await w.get('[data-intent="revenda"]').trigger("click");
    await w.get("[data-testid='create-sku']").setValue("PAO-01");
    expect(w.get("[data-form-shell]").attributes("data-form-dirty")).toBe("true");

    await showConfirm();
    await w.get("[data-testid='create-discard']").trigger("click");
    await flushPromises();
    expect(document.body.textContent).toContain("Descartar o que você preencheu?");
    await dialog!.get("[data-operator-confirm-keep]").trigger("click");
    await flushPromises();
    expect(w.emitted("update:open")).toBeUndefined();

    await w.get("[data-testid='create-discard']").trigger("click");
    await flushPromises();
    await dialog!.get("[data-operator-confirm-act]").trigger("click");
    await flushPromises();
    expect(w.emitted("update:open")).toEqual([[false]]);
  });

  it("salva o que foi preenchido, com o preço em centavos", async () => {
    const w = panel();
    await w.get('[data-intent="revenda"]').trigger("click");
    await w.get("[data-testid='create-sku']").setValue("PAO-01");
    await w.get("[data-testid='create-name']").setValue("Pão de campanha");
    await w.get("[data-testid='create-price']").setValue("15,00");
    await w.get("[data-testid='create-submit']").trigger("click");
    expect(w.emitted("save")).toEqual([
      [
        expect.objectContaining({
          sku: "PAO-01",
          name: "Pão de campanha",
          base_price_q: 1500,
          intent: "revenda",
        }),
      ],
    ]);
  });

  it("insumo não cria produto: a ação conduz ao Compras", async () => {
    const w = panel();
    await w.get('[data-intent="insumo"]').trigger("click");
    expect(w.text()).toContain("Abrir o Compras");
    await w.get("[data-testid='create-go-purchase']").trigger("click");
    expect(w.emitted("go-purchase")).toHaveLength(1);
    expect(w.emitted("save")).toBeUndefined();
  });

  it("duplicar traz o conteúdo e não pede preço", async () => {
    const w = panel({
      mode: "duplicate",
      source: { sku: "ORIGEM", name: "Original" },
      suggestedSku: "ORIGEM-2",
      suggestedName: "Original (cópia)",
    });
    expect(w.find("[data-testid='create-price']").exists()).toBe(false);
    expect(w.get("[data-testid='create-sku']").element).toHaveProperty("value", "ORIGEM-2");
    await w.get("[data-testid='create-submit']").trigger("click");
    expect(w.emitted("save")).toEqual([
      [expect.objectContaining({ sku: "ORIGEM-2", name: "Original (cópia)" })],
    ]);
  });

  it("o código de barras pede a leitura à página", async () => {
    const w = panel();
    await w.get('[data-intent="revenda"]').trigger("click");
    await w.get("[data-testid='create-gtin']").setValue("7891000053508");
    await w.get("[data-testid='create-lookup']").trigger("click");
    expect(w.emitted("lookup")).toEqual([["7891000053508"]]);
  });
});
