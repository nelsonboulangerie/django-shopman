// O detalhe do pedido é o MESMO no Gestor e no PDV (decisão do dono, 28/09/2026).
// A presentation é a parte pura dele: tom, linhas que juntam fatos, ícone e a
// leitura das ações que o servidor ofereceu. Testada aqui, na fonte, e não por um
// dos dois consumidores.
import { describe, expect, it } from "vitest";

import {
  canComment,
  customerAdminUrl,
  detailAction,
  fiscalHref,
  hasCustomerContact,
  joinFacts,
  lucideIcon,
  profileHabits,
  profileHistory,
  relayExpiresLabel,
  statusTone,
  toneBadge,
} from "../app/presentation/orderDetail";
import type { OperatorOrderDetail, OrderDetailCustomerProfile } from "../app/types/orderDetail";

function profile(overrides: Partial<OrderDetailCustomerProfile> = {}): OrderDetailCustomerProfile {
  return {
    orders_label: "",
    last_order_display: "",
    average_ticket_display: "",
    favorite_product: "",
    segment_label: "",
    segment_tone: "",
    notes: "",
    dietary_restrictions: "",
    birthday_display: "",
    is_birthday_today: false,
    ...overrides,
  };
}

function contact(overrides: Partial<OperatorOrderDetail> = {}): OperatorOrderDetail {
  return {
    customer_phone_uri: "",
    customer_relay_phone: "",
    customer_whatsapp_url: "",
    customer_email: "",
    ...overrides,
  } as OperatorOrderDetail;
}

describe("orderDetail · tom", () => {
  it("cada status do ciclo tem um tom; o desconhecido fica neutro", () => {
    expect(statusTone("ready")).toBe("success");
    expect(statusTone("preparing")).toBe("warning");
    expect(statusTone("cancelled")).toBe("danger");
    expect(statusTone("status_que_nao_existe")).toBe("neutral");
  });

  it("o selo neutro não carrega cor saturada", () => {
    expect(toneBadge("neutral")).toContain("bg-muted");
    expect(toneBadge("danger")).toContain("text-red-700");
    expect(toneBadge("")).toBe(toneBadge("neutral"));
  });
});

describe("orderDetail · linhas", () => {
  it("junta fatos sem separador órfão", () => {
    expect(joinFacts("a", "", null, undefined, "  ", "b")).toBe("a · b");
    expect(joinFacts("", null)).toBe("");
  });

  it("histórico e hábitos do cliente só com o que o servidor sabe", () => {
    expect(profileHistory(null)).toBe("");
    expect(profileHabits(null)).toBe("");
    expect(profileHistory(profile({ orders_label: "12 pedidos", last_order_display: "há 12 dias" }))).toBe(
      "12 pedidos · última compra há 12 dias",
    );
    expect(profileHistory(profile({ orders_label: "Primeiro pedido" }))).toBe("Primeiro pedido");
    expect(profileHabits(profile({ average_ticket_display: "R$ 42,00", favorite_product: "Pão francês" }))).toBe(
      "ticket médio R$ 42,00 · costuma levar Pão francês",
    );
    expect(profileHabits(profile({ favorite_product: "Croissant" }))).toBe("costuma levar Croissant");
  });

  it("o prazo do código do iFood só aparece quando é legível", () => {
    expect(relayExpiresLabel("")).toBe("");
    expect(relayExpiresLabel("não é data")).toBe("");
    expect(relayExpiresLabel("2026-09-28T14:32:00")).toMatch(/^Vale até \d{2}:\d{2}$/);
  });
});

describe("orderDetail · ícones e links", () => {
  it("traduz a ligadura do Material para lucide, e nunca devolve vazio", () => {
    expect(lucideIcon("local_shipping")).toBe("bike");
    expect(lucideIcon("store")).toBe("store");
    expect(lucideIcon("package")).toBe("package");
    expect(lucideIcon("")).toBe("circle");
  });

  it("o cadastro no Admin precisa do cliente E do endereço do Admin", () => {
    expect(customerAdminUrl("", "CLI-1")).toBe("");
    expect(customerAdminUrl("https://admin.exemplo", "")).toBe("");
    expect(customerAdminUrl("https://admin.exemplo", "CLI 1")).toBe(
      "https://admin.exemplo/admin/guestman/customer/?q=CLI%201",
    );
  });

  it("sem nenhum caminho até a pessoa, o bloco de contato não existe", () => {
    expect(hasCustomerContact(contact(), "")).toBe(false);
    expect(hasCustomerContact(contact(), "https://admin.exemplo/x")).toBe(true);
    expect(hasCustomerContact(contact({ customer_relay_phone: "0800" }), "")).toBe(true);
    expect(hasCustomerContact(contact({ customer_email: "a@b.c" }), "")).toBe(true);
  });

  it("o link fiscal aceita href e o url legado", () => {
    expect(fiscalHref({ href: "/danfe" })).toBe("/danfe");
    expect(fiscalHref({ url: "/xml" })).toBe("/xml");
    expect(fiscalHref({})).toBe("#");
  });
});

describe("orderDetail · ações (a régua é do servidor)", () => {
  const comment = { ref: "comment", label: "Comentar", enabled: true, reason: "", payload_schema: {} };

  it("acha a ação oferecida, e nada quando não veio", () => {
    expect(detailAction({ actions: [comment] }, "comment")).toEqual(comment);
    expect(detailAction({ actions: [comment] }, "cancel")).toBeUndefined();
    expect(detailAction(null, "comment")).toBeUndefined();
  });

  it("comentar só quando o servidor oferece E deixa", () => {
    expect(canComment({ actions: [comment] })).toBe(true);
    expect(canComment({ actions: [{ ...comment, enabled: false, reason: "Sem permissão" }] })).toBe(false);
    expect(canComment({ actions: [] })).toBe(false);
    expect(canComment(undefined)).toBe(false);
  });
});
