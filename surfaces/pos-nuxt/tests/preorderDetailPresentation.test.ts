// A volta do detalhe da encomenda: o recorte da lista vai no link (`?back=`), e
// só caminho da própria seção vale (o parâmetro nunca vira redirecionamento aberto).
import { describe, expect, it, vi } from "vitest";

import { PROMISE_ALERT_TITLE, preorderBackTarget, preorderDetailPath, promiseAlert } from "../app/presentation/preorderDetail";
import type { PreorderPromise } from "../app/types/preorders";

describe("preorderDetailPath — o link leva a volta junto", () => {
  it("o recorte da lista vai em ?back=", () => {
    expect(preorderDetailPath("NB-7", "/preorders?mode=day&date=2026-10-02&print=pending"))
      .toBe("/preorders/NB-7?back=%2Fpreorders%3Fmode%3Dday%26date%3D2026-10-02%26print%3Dpending");
  });

  it("a casa da seção não vai na URL: a volta sem back já cai nela", () => {
    expect(preorderDetailPath("NB-7", "/preorders")).toBe("/preorders/NB-7");
    expect(preorderDetailPath("NB-7")).toBe("/preorders/NB-7");
  });

  it("recorte de fora da seção é ignorado", () => {
    expect(preorderDetailPath("NB-7", "https://example.com/preorders")).toBe("/preorders/NB-7");
    expect(preorderDetailPath("NB-7", "/preordersX")).toBe("/preorders/NB-7");
  });

  it("o ref é escapado", () => {
    expect(preorderDetailPath("A/B 1")).toBe("/preorders/A%2FB%201");
  });

  it("o que o link manda, a volta aceita (ida e volta)", () => {
    const from = "/preorders?mode=week&fulfillment=delivery&q=Ana";
    const link = new URL(preorderDetailPath("NB-7", from), "http://pdv.test");
    expect(preorderBackTarget(link.searchParams.get("back"))).toBe(from);
  });
});

// #2721 item 3: a promessa em risco no topo do detalhe, com o "Resolver" do Gestor.
function promise(over: Partial<PreorderPromise> = {}): PreorderPromise {
  return {
    state: "at_risk",
    label: "Promessa em risco",
    items: [
      { sku: "CRO", at_risk: true, label: "Falta 1x Croissant", detail: "O lote de amanhã foi cancelado." },
      { sku: "CHA", at_risk: false, label: "Chá", detail: "" },
    ],
    actions: [{ ref: "resolve", label: "Resolver no Gestor", href: "https://gestor.example/NB-1#resolve", enabled: true, reason: "" }],
    ...over,
  };
}

describe("promiseAlert — a promessa em risco no topo", () => {
  it("o fato do Gestor, item a item, e o botão que abre o Resolver de lá", () => {
    const open = vi.fn();
    const alert = promiseAlert(promise(), open)!;
    expect(alert.title).toBe(PROMISE_ALERT_TITLE);
    expect(alert.description).toBe("Falta 1x Croissant. O lote de amanhã foi cancelado.");
    expect(alert.color).toBe("error");
    expect(alert.action?.label).toBe("Resolver no Gestor");
    alert.action?.onSelect?.(new Event("click"));
    expect(open).toHaveBeenCalledWith("https://gestor.example/NB-1#resolve");
  });

  it("travada, a saída some e o motivo entra no texto", () => {
    const alert = promiseAlert(
      promise({ actions: [{ ref: "resolve", label: "Resolver no Gestor", href: "", enabled: false, reason: "O endereço do Gestor não está configurado." }] }),
      vi.fn(),
    )!;
    expect(alert.action).toBeUndefined();
    expect(alert.description).toBe("Falta 1x Croissant. O lote de amanhã foi cancelado. O endereço do Gestor não está configurado.");
  });

  it("sem promessa em risco, não há aviso", () => {
    expect(promiseAlert(null, vi.fn())).toBeNull();
    expect(promiseAlert(undefined, vi.fn())).toBeNull();
    expect(promiseAlert(promise({ state: "waiting_batch" }), vi.fn())).toBeNull();
  });
});
