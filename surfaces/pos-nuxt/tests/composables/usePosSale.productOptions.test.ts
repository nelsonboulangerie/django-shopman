import { describe, expect, it, vi } from "vitest";

import type { POSCartItemOption, POSProductProjection } from "~/types/pos";
import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const croque: POSProductProjection = {
  sku: "CQMO",
  name: "Croque Monsieur",
  price_q: 2400,
  price_display: "R$ 24,00",
  collection_ref: "salgados",
  collection_color: "",
  collection_icon: "",
  image_url: "",
  option_groups: [
    {
      ref: "adicionais",
      label: "Adicionais",
      min: 0,
      max: 2,
      options: [
        { ref: "ovo", label: "Ovo frito", price_q: 400, available: true },
        { ref: "salada", label: "Salada", price_q: 300, available: true },
      ],
    },
  ],
};

const ovo: POSCartItemOption = { group: "adicionais", ref: "ovo", group_label: "Adicionais", name: "Ovo frito", unit_price_q: 400 };
const salada: POSCartItemOption = { group: "adicionais", ref: "salada", group_label: "Adicionais", name: "Salada", unit_price_q: 300 };

function saleWithCroque(actionCall?: ReturnType<typeof vi.fn>) {
  const base = makeProjection();
  const h = makeSale({
    actionCall,
    projection: makeProjection({
      products: [...base.products, croque],
      checkout: {
        intent_version: 1,
        capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
      } as ReturnType<typeof makeProjection>["checkout"],
    }),
  });
  // Comanda aberta: o save tem para onde ir.
  h.sale.cart.tabRef = "M1";
  h.sale.cart.tabDisplay = "M1";
  h.sale.cart.tabSessionKey = "sess-1";
  h.sale.cart.expectedRevision = "v1:initial";
  return h;
}

describe("usePosSale · escolhas no produto", () => {
  it("o toque no produto com grupo abre a escolha e não lança nada", () => {
    const h = saleWithCroque();
    h.sale.addProduct(croque);
    expect(h.sale.optionsPrompt.value?.sku).toBe("CQMO");
    expect(h.sale.cart.items).toHaveLength(0);
    h.sale.cancelOptionsPrompt();
    expect(h.sale.optionsPrompt.value).toBeNull();
    expect(h.sale.cart.items).toHaveLength(0);
    h.handles.dispose();
  });

  it("produto sem grupo continua somando direto", () => {
    const h = saleWithCroque();
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    expect(h.sale.optionsPrompt.value).toBeNull();
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.cart.items[0]).not.toHaveProperty("options");
    h.handles.dispose();
  });

  it("confirmar lança a linha com nome resumido, preço somado e options", () => {
    const h = saleWithCroque();
    h.sale.addProduct(croque);
    h.sale.addOptionsProduct(croque, [ovo]);
    expect(h.sale.optionsPrompt.value).toBeNull();
    const [line] = h.sale.cart.items;
    expect(line!.name).toBe("Croque Monsieur (+ Ovo frito)");
    expect(line!.price_q).toBe(2800);
    expect(line!.options).toEqual([ovo]);
    h.handles.dispose();
  });

  it("mesma assinatura soma qty; assinatura diferente é linha nova", () => {
    const h = saleWithCroque();
    h.sale.addOptionsProduct(croque, [ovo, salada]);
    h.sale.addOptionsProduct(croque, [salada, ovo]);
    h.sale.addOptionsProduct(croque, [ovo]);
    h.sale.addOptionsProduct(croque, []);
    h.sale.addOptionsProduct(croque, []);
    expect(h.sale.cart.items).toHaveLength(3);
    expect(h.sale.cart.items.map((item) => [item.name, item.qty, item.price_q])).toEqual([
      ["Croque Monsieur (+ Ovo frito · + Salada)", 2, 3100],
      ["Croque Monsieur (+ Ovo frito)", 1, 2800],
      ["Croque Monsieur", 2, 2400],
    ]);
    // O selo do grid continua sendo do PRODUTO: soma as três linhas.
    expect(h.sale.productQty("CQMO")).toBe(5);
    h.handles.dispose();
  });

  it("linha já enviada à cozinha não soma, mesmo com a mesma escolha", () => {
    const h = saleWithCroque();
    h.sale.addOptionsProduct(croque, [ovo]);
    h.sale.cart.items[0]!.fired = true;
    h.sale.addOptionsProduct(croque, [ovo]);
    expect(h.sale.cart.items).toHaveLength(2);
    h.handles.dispose();
  });

  it("o save da comanda leva options {group, ref} por item", async () => {
    const actionCall = vi.fn().mockResolvedValue({});
    const h = saleWithCroque(actionCall);
    h.sale.addOptionsProduct(croque, [ovo]);
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await h.sale.saveTab();
    const save = actionCall.mock.calls.find((call) => String(call[0]).includes("/tabs/save/"));
    const items = save![1].body.items as Array<Record<string, unknown>>;
    expect(items[0]!.options).toEqual([{ group: "adicionais", ref: "ovo" }]);
    expect(items[0]!.unit_price_q).toBe(2800);
    expect(items[1]).not.toHaveProperty("options");
    h.handles.dispose();
  });

  it("a comanda recarregada preserva as escolhas e as reenvia", async () => {
    const remote = { line_id: "L-abc12345", sku: "CQMO", name: "Croque Monsieur (+ Ovo frito)", price_q: 2800, qty: 1, notes: "", options: [ovo] };
    const actionCall = vi
      .fn()
      .mockRejectedValueOnce({ status: 409, data: { detail: "Outra estação alterou a comanda." } })
      .mockResolvedValueOnce(makeTabPayload({ revision: "v1:remote", items: [remote] }))
      .mockResolvedValue({ revision: "v1:merged" });
    const h = saleWithCroque(actionCall);
    h.sale.addOptionsProduct(croque, []);
    await h.sale.saveTab();
    await h.sale.reloadConflictingTab();
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.cart.items[0]!.options).toEqual([ovo]);
    // Mais um igual soma na mesma linha; sem ovo, linha nova.
    h.sale.addOptionsProduct(croque, [ovo]);
    h.sale.addOptionsProduct(croque, []);
    expect(h.sale.cart.items.map((item) => item.qty)).toEqual([2, 1]);
    await h.sale.saveTab();
    const lastSave = actionCall.mock.calls.filter((call) => String(call[0]).includes("/tabs/save/")).at(-1)!;
    const items = lastSave[1].body.items as Array<Record<string, unknown>>;
    expect(items[0]!.options).toEqual([{ group: "adicionais", ref: "ovo" }]);
    expect(items[1]).not.toHaveProperty("options");
    h.handles.dispose();
  });
});
