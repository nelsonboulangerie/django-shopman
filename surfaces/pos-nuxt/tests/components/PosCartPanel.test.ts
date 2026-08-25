import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x", ...overrides };
}

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { price_q: 500, qty: 1, notes: "", ...overrides };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [item({ sku: "PAO", name: "Pão" }), item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: affordance(),
    unfireAction: affordance({ ref: "unfire_tab", label: "Cancelar envio" }),
    firing: false,
    ...overrides,
  };
}

describe("PosCartPanel — render", () => {
  it("lista as linhas do carrinho com nome e total", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const text = wrapper.text();
    expect(text).toContain("Pão");
    expect(text).toContain("Café");
    // Total = 5,00 + 2×3,00 = R$ 11,00
    expect(text).toContain("11,00");
  });

  it("com comanda obrigatória e sem comanda aberta, mostra o gate 'Abra uma comanda'", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    expect(wrapper.text()).toContain("Abra uma comanda");
    expect(wrapper.text()).toContain("Escolher comanda");
  });

  it("carrinho vazio (com comanda) mostra o placeholder, não o gate", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [] }) });
    expect(wrapper.text()).not.toContain("Abra uma comanda");
  });
});

describe("PosCartPanel — interações emitem os comandos certos", () => {
  it("'Aumentar' emite increment com o sku da linha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.findAll('[aria-label="Aumentar"]')[0]!.trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["PAO"]);
  });

  it("'Diminuir' numa linha com qty>1 emite decrement (não abre remoção)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // CAFE é a 2ª linha, qty 2 → decrementa direto.
    await wrapper.findAll('[aria-label="Diminuir"]')[1]!.trigger("click");
    expect(wrapper.emitted("decrement")?.[0]).toEqual(["CAFE"]);
    expect(wrapper.emitted("remove")).toBeUndefined();
  });

  it("'Diminuir' na última unidade PERGUNTA antes de remover", async () => {
    // Já removeu direto (com Desfazer no toast) e o balcão discordou: o gesto
    // que mais remove é zerar a quantidade, e ali ninguém teve intenção de
    // excluir — o item sumia e o operador procurava um toast que já passou.
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.findAll('[aria-label="Diminuir"]')[0]!.trigger("click");

    expect(wrapper.emitted("decrement")).toBeUndefined();
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover item"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["PAO"]);
  });

  it("linha JÁ disparada à cozinha pede confirmação antes de remover", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "PAO", name: "Pão", fired: true, line_id: "l1" })] }),
    });
    await wrapper.find('[aria-label="Remover"]').trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover item"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["PAO"]);
  });

  it("'Remover' da barra de lote pede confirmação e remove a seleção inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Café"]').trigger("click");
    const batchRemove = wrapper.findAll("button").find((b) => b.text().trim() === "Remover");
    await batchRemove!.trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover itens"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.length).toBe(2);
  });

  it("'Pagamento' emite prepare", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const pay = wrapper.findAll("button").find((b) => b.text().includes("Pagamento"));
    await pay!.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
  });

  it("o gate 'Escolher comanda' emite requestTab", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    const btn = wrapper.findAll("button").find((b) => b.text().includes("Escolher comanda"));
    await btn!.trigger("click");
    expect(wrapper.emitted("requestTab")).toHaveLength(1);
  });

  it("selecionar uma linha arma a barra de lote (multi-select)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    // A barra de seleção aparece com o atalho de limpar seleção.
    expect(wrapper.find('[aria-label="Limpar seleção"]').exists()).toBe(true);
  });
});

describe("PosCartPanel — numpad global desliga sob overlay/diálogo", () => {
  function pressKey(key: string) {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
    );
  }

  it("digitar um número na janela edita a quantidade da linha ativa (baseline)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    pressKey("5");
    await wrapper.vm.$nextTick();
    // A linha ativa é a última adicionada (CAFE).
    expect(wrapper.emitted("setQty")?.[0]).toEqual(["CAFE", 5]);
  });

  it("com um diálogo aberto, o teclado NÃO reescreve o carrinho", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // Um diálogo qualquer aberto por cima (é assim que o reka-ui marca o DOM).
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("data-state", "open");
    document.body.appendChild(dialog);
    try {
      pressKey("5");
      pressKey("Backspace");
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted("setQty")).toBeUndefined();
    } finally {
      dialog.remove();
    }
  });

  it("com o terminal travado (overlay do kit), o crachá não vira quantidade", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const lock = document.createElement("div");
    lock.setAttribute("data-operator-lock", "");
    document.body.appendChild(lock);
    try {
      // O token do crachá tem dígitos: era ISTO que reescrevia a linha ativa.
      for (const char of "a1b2c3d4e5f6") pressKey(char);
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted("setQty")).toBeUndefined();
    } finally {
      lock.remove();
    }
  });
});
