import { describe, expect, it } from "vitest";

import { makeProjection, makeSale } from "./_posSaleHarness";

// Uma comanda salva com `slot-09` para HOJE mostrava o ref cru no chip e na
// leitura de volta: a grade do dia só existe depois que alguém abre a agenda.
// Os slots canônicos do terminal (`pos.delivery_slots_canonical`) trazem o
// rótulo real; a humanização fica de rede quando eles ainda não chegaram.
function projectionWith(overrides: Record<string, unknown>) {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
    ...overrides,
  });
}

describe("usePosSale — o rótulo da janela resolve pelos slots canônicos", () => {
  const CANONICOS = [
    { ref: "slot-09", label: "Manhã (a partir das 9h)", starts_at: "2026-09-16T09:00:00-03:00" },
    { ref: "slot-12", label: "A partir das 12h", starts_at: "2026-09-16T12:00:00-03:00" },
  ];

  it("comanda de HOJE com `slot-09` e grade não buscada: o rótulo é o do servidor", () => {
    const h = makeSale({ projection: projectionWith({ delivery_today: "2026-09-16", delivery_slots_canonical: CANONICOS }) });
    h.sale.cart.deliveryTimeSlot = "slot-09";
    expect(h.sale.deliverySlots.value).toEqual([]);
    expect(h.sale.deliveryWindowLabel.value).toBe("Manhã (a partir das 9h)");
    h.handles.dispose();
  });

  it("sem canônicos, o ref é humanizado — nunca cru", () => {
    const h = makeSale({ projection: projectionWith({ delivery_today: "2026-09-16" }) });
    h.sale.cart.deliveryTimeSlot = "slot-09";
    expect(h.sale.deliveryWindowLabel.value).toBe("a partir das 9h");
    expect(h.sale.deliveryWindowLabel.value).not.toContain("slot-");
    h.handles.dispose();
  });
});
