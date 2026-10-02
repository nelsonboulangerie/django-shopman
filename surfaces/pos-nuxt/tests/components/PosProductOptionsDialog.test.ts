// O diálogo de escolhas no produto: regra legível, opção fora desabilitada,
// total ao vivo, [Lançar] só com os mínimos cumpridos, Enter lança.
import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosProductOptionsDialog from "~/components/PosProductOptionsDialog.vue";
import type { POSProductProjection } from "~/types/pos";

const frappe: POSProductProjection = {
  sku: "FRAPPE",
  name: "Frappé",
  price_q: 1800,
  price_display: "R$ 18,00",
  collection_ref: "bebidas",
  collection_color: "",
  collection_icon: "",
  image_url: "",
  option_groups: [
    {
      ref: "sabor",
      label: "Sabor",
      min: 1,
      max: 1,
      options: [
        { ref: "cafe", label: "Café", price_q: 0, available: true },
        { ref: "frutas", label: "Frutas vermelhas", price_q: 0, available: false },
      ],
    },
    {
      ref: "adicionais",
      label: "Adicionais",
      min: 0,
      max: 2,
      options: [{ ref: "chantilly", label: "Chantilly", price_q: 400, available: true }],
    },
  ],
};

const settle = () => new Promise((resolve) => setTimeout(resolve, 50));

async function render() {
  document.body.innerHTML = "";
  const wrapper = await mountSuspended(PosProductOptionsDialog, { props: { product: frappe }, attachTo: document.body });
  await settle();
  return wrapper;
}

function option(key: string): HTMLButtonElement {
  return document.querySelector<HTMLButtonElement>(`[data-option="${key}"]`)!;
}

function confirmButton(): HTMLButtonElement {
  return document.querySelector<HTMLButtonElement>('[data-role="confirm"]')!;
}

describe("PosProductOptionsDialog", () => {
  it("mostra a regra de cada grupo e a opção fora como Indisponível", async () => {
    const wrapper = await render();
    const text = document.body.textContent || "";
    expect(text).toContain("Escolha 1");
    expect(text).toContain("Opcional");
    expect(text).toContain("Indisponível");
    expect(text).toContain("+ R$ 4,00");
    expect(text).not.toMatch(/[—–]/);
    expect(option("sabor:frutas").disabled).toBe(true);
    wrapper.unmount();
  });

  it("Lançar só com o mínimo cumprido; total ao vivo; emite as escolhas", async () => {
    const wrapper = await render();
    expect(confirmButton().disabled).toBe(true);
    option("sabor:cafe").click();
    option("adicionais:chantilly").click();
    await settle();
    expect(confirmButton().disabled).toBe(false);
    expect(document.querySelector('[data-testid="product-options-total"]')!.textContent).toContain("22,00");
    confirmButton().click();
    const [[product, options]] = wrapper.emitted("confirm") as [[POSProductProjection, unknown[]]];
    expect(product.sku).toBe("FRAPPE");
    expect(options).toEqual([
      { group: "sabor", ref: "cafe", group_label: "Sabor", name: "Café", unit_price_q: 0 },
      { group: "adicionais", ref: "chantilly", group_label: "Adicionais", name: "Chantilly", unit_price_q: 400 },
    ]);
    wrapper.unmount();
  });

  it("Enter lança quando válido e não faz nada antes", async () => {
    const wrapper = await render();
    const dialog = document.querySelector('[data-testid="product-options-dialog"]')!;
    dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(wrapper.emitted("confirm")).toBeUndefined();
    option("sabor:cafe").click();
    await settle();
    dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(wrapper.emitted("confirm")).toHaveLength(1);
    wrapper.unmount();
  });

  it("o foco abre na primeira opção disponível", async () => {
    const wrapper = await render();
    await settle();
    expect(document.activeElement).toBe(option("sabor:cafe"));
    wrapper.unmount();
  });
});
