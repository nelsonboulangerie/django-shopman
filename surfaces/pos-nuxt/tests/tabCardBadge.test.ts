import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { tabCardAccessibleName, tabCardBadge, tabCardView } from "~/presentation/tabBoard";
import type { POSTabProjection } from "~/types/pos";

function tab(overrides: Partial<POSTabProjection> & { ref: string }): POSTabProjection {
  return {
    display_ref: overrides.ref, session_key: "", state: "empty", status_label: "", status_class: "",
    customer_name: "", customer_phone: "", item_count: 0, line_count: 0, total_display: "",
    last_touched_display: "", items_preview: "", ...overrides,
  };
}

describe("presentation/tabBoard — o selo de estado do cartão de comanda", () => {
  const cases = {
    ready: tab({ ref: "1", state: "in_use", item_count: 1, fired: true, kitchen_ready: true }),
    unpaid: tab({ ref: "2", state: "in_use", item_count: 1, fired: true }),
    pending: tab({ ref: "3", state: "in_use", item_count: 1 }),
    free: tab({ ref: "4", status_label: "Livre" }),
    emptyInUse: tab({ ref: "5", state: "in_use", status_label: "Em uso" }),
  };
  const badges = Object.fromEntries(Object.entries(cases).map(([k, t]) => [k, tabCardBadge(tabCardView(t))]));

  it("um selo por estado, na ordem do que o balcão faz primeiro, na cor do selo da suíte", () => {
    expect(badges.ready).toMatchObject({ kind: "ready", label: "Tudo pronto", color: "success" });
    expect(badges.unpaid).toMatchObject({ kind: "unpaid", label: "Não pago", color: "warning" });
    expect(badges.pending).toMatchObject({ kind: "pending", label: "A enviar", color: "neutral" });
    // Livre é neutro e discreto.
    expect(badges.free).toMatchObject({ kind: "status", label: "Livre", color: "neutral", title: "Livre: comanda disponível" });
    expect(badges.emptyInUse).toMatchObject({ kind: "status", label: "Em uso", color: "neutral" });
  });

  it("todo selo tem ícone (o que fica no cartão estreito) e a dica começa pelo nome; sem travessão", () => {
    for (const badge of Object.values(badges)) {
      expect(badge.icon).toMatch(/^lucide:/);
      expect(badge.title.startsWith(`${badge.label}: `)).toBe(true);
      expect(badge.title).not.toMatch(/[—–]/);
    }
  });

  it("os ícones dos selos vão no pacote do cliente (são dado num .ts; o scan do @nuxt/icon não os vê)", () => {
    const config = readFileSync(new URL("../nuxt.config.ts", import.meta.url), "utf8");
    for (const badge of Object.values(badges)) expect(config).toContain(`"${badge.icon}"`);
  });
});

describe("presentation/tabBoard — o cartão diz o que é (beta test de 05/11/2026)", () => {
  it("PDV2-22: o cartão tem nome acessível com número, estado e conteúdo", () => {
    const free = tabCardView(tab({ ref: "1009", status_label: "Livre" }));
    expect(tabCardAccessibleName(free, tabCardBadge(free), "#1009")).toBe("Comanda #1009, Livre");
    const busy = tabCardView(tab({ ref: "7", state: "in_use", item_count: 2, customer_name: "Maria", total_display: "R$ 10,00" }));
    expect(tabCardAccessibleName(busy, tabCardBadge(busy), "Mesa 7")).toBe("Comanda Mesa 7, A enviar, Maria, 2 itens · R$ 10,00");
  });

  it("PDV-19: a comanda Em uso sem item diz desde quando está aberta", () => {
    const view = tabCardView(tab({ ref: "1008", state: "in_use", status_label: "Em uso", opened_at_display: "14:32" }));
    expect(view.identity).toBe("Aberta às 14:32");
    const withCustomer = tabCardView(tab({ ref: "1008", state: "in_use", customer_name: "Ana", opened_at_display: "14:32" }));
    expect(withCustomer.identity).toBe("Ana");
  });
});
