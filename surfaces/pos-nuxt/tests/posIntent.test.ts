import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { buildAdminLoginUrl, isOperatorAccessError, statusCodeFromError } from "../app/utils/operatorAccess";
import {
  POS_SALE_INTENT_VERSION,
  actionHref,
  buildPosSaleIntent,
  cartTotalQ,
  concreteActionHref,
  newLineId,
  resolvePayment,
} from "../app/utils/posIntent";
import {
  draftAssociationTargetStates,
  requiresOpenTabForCart,
  requiresTabBeforeSave,
  tabRefMaxLength,
  tabRefPlaceholder,
} from "../app/utils/posTabLifecycle";

describe("POS sale intent", () => {
  it("serializes cart state into the canonical POS intent contract", () => {
    const payload = buildPosSaleIntent({
      tabRef: "00001007",
      tabSessionKey: "session-1",
      customerName: "Ana",
      customerRef: "CUST-1",
      customerPhone: "(43) 99999-0000",
      customerTaxId: "123.456.789-01",
      invoiceTaxId: "529.982.247-25",
      customerEmail: "ana@example.com",
      customerMemoryAction: "",
      fulfillmentType: "delivery",
      deliveryAddress: "Rua A, 10 - Centro",
      deliveryAddressStructured: {
        formatted_address: "Rua A, 10 - Centro",
        route: "Rua A",
        street_number: "10",
        neighborhood: "Centro",
        city: "Londrina",
        state_code: "PR",
        postal_code: "86000-000",
        latitude: -23.3,
        longitude: -51.1,
        place_id: "ChIJ-pos",
        reference: "",
      },
      deliveryComplement: "Sala 2",
      deliveryInstructions: "Portaria",
      deliveryDate: "2026-05-16",
      deliveryTimeSlot: "14:00-14:30",
      deliveryFeeOverrideQ: 300,
      orderNotes: "Portaria",
      paymentMethod: "cash",
      paymentCollection: "on_delivery",
      paymentTenders: [],
      tenderedQ: null,
      changeForQ: 0,
      receiptChannels: ["email"],
      receiptEmail: "ana@example.com",
      manualDiscount: null,
      managerApproval: null,
      clientRequestId: "pos:test-1",
      items: [
        { line_id: "L-abc12345", sku: "PAO", name: "Pao", price_q: 1200, qty: 2, notes: "" },
      ],
    });

    expect(payload).toMatchObject({
      intent_version: POS_SALE_INTENT_VERSION,
      tab_ref: "00001007",
      tab_session_key: "session-1",
      fulfillment_type: "delivery",
      customer_ref: "CUST-1",
      delivery_address: "Rua A, 10 - Centro",
      delivery_address_structured: {
        formatted_address: "Rua A, 10 - Centro",
        route: "Rua A",
        street_number: "10",
        neighborhood: "Centro",
        city: "Londrina",
        state_code: "PR",
        postal_code: "86000-000",
        latitude: -23.3,
        longitude: -51.1,
        place_id: "ChIJ-pos",
        complement: "Sala 2",
        delivery_instructions: "Portaria",
        reference: "",
      },
      delivery_date: "2026-05-16",
      delivery_time_slot: "14:00-14:30",
      delivery_fee_override_q: 300,
      order_notes: "Portaria",
      payment_method: "cash",
      payment_collection: "on_delivery",
      customer_phone: "43999990000",
      customer_tax_id: "12345678901",
      receipt_channels: ["email"],
      receipt_email: "ana@example.com",
    });
    // A IDENTIDADE da linha viaja com ela: sem `line_id` no payload o servidor
    // gerava um id novo a cada save e perdia o vínculo com o ticket já disparado.
    expect(payload.items).toEqual([
      { line_id: "L-abc12345", sku: "PAO", name: "Pao", qty: 2, unit_price_q: 1200, notes: "" },
    ]);
    expect(payload.items[0]).not.toHaveProperty("price_q");
  });

  it("uses projection actions instead of hardcoding mutation paths in state builders", () => {
    const actions = [
      {
        ref: "open_tab",
        kind: "mutation",
        label: "Abrir",
        priority: "secondary",
        enabled: true,
        reason: "",
        href: "/api/v1/backstage/pos/tabs/{tab_ref}/open/",
        method: "POST",
        payload_schema: {},
        idempotency: "none",
        confirmation: {},
      },
    ];

    expect(actionHref(actions, "missing", "/fallback/")).toBe("/fallback/");
    expect(concreteActionHref(actions, "open_tab", "/fallback/", { tab_ref: "00001007" })).toBe(
      "/api/v1/backstage/pos/tabs/00001007/open/",
    );
  });

  it("only computes local display totals from projected line prices", () => {
    expect(cartTotalQ([
      { sku: "A", name: "A", price_q: 500, qty: 2, notes: "" },
      { sku: "B", name: "B", price_q: 300, qty: 1, notes: "" },
    ])).toBe(1300);
  });

  it("does not replay saved tender lines unless split payment is explicit", () => {
    const staleTender = { method: "cash", amount_q: 1000, collection: "terminal" as const };
    const simple = buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentTenders: [staleTender],
      tenderedQ: null,
    }));

    expect(simple).not.toHaveProperty("payment_tenders");

    const mixed = buildPosSaleIntent(baseIntentState({
      paymentMethod: "mixed",
      paymentTenders: [staleTender],
      tenderedQ: null,
    }));

    expect(mixed.payment_tenders).toEqual([staleTender]);
  });

  it("sends cash received amount only for terminal cash payments", () => {
    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "pix",
      paymentCollection: "terminal",
      tenderedQ: 2000,
    }))).not.toHaveProperty("tendered_q");

    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentCollection: "on_delivery",
      tenderedQ: 2000,
    }))).not.toHaveProperty("tendered_q");

    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentCollection: "terminal",
      tenderedQ: 2000,
    }))).toMatchObject({ tendered_q: 2000 });
  });

  it("envia o troco-para só no dinheiro NA ENTREGA (COD)", () => {
    // Entrega + receber na entrega + valor → viaja na chave canônica.
    expect(buildPosSaleIntent(baseIntentState({
      fulfillmentType: "delivery",
      deliveryAddress: "Rua A, 10",
      paymentMethod: "cash",
      paymentCollection: "on_delivery",
      changeForQ: 5000,
    }))).toMatchObject({ change_for_q: 5000 });

    // Recebimento no terminal: o troco é tendered/change; change_for não viaja.
    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentCollection: "terminal",
      changeForQ: 5000,
    }))).not.toHaveProperty("change_for_q");

    // Campo opcional: zero não viaja.
    expect(buildPosSaleIntent(baseIntentState({
      fulfillmentType: "delivery",
      deliveryAddress: "Rua A, 10",
      paymentMethod: "cash",
      paymentCollection: "on_delivery",
      changeForQ: 0,
    }))).not.toHaveProperty("change_for_q");
  });

  it("serializes manual discount as a canonical intent for backend review", () => {
    expect(buildPosSaleIntent(baseIntentState({
      manualDiscount: { type: "percent", value: "10", reason: "fidelidade" },
      managerApproval: { username: "gerente", password: "secret" },
    }))).toMatchObject({
      manual_discount: { type: "percent", value: "10", reason: "fidelidade" },
      manager_approval: { username: "gerente", password: "secret" },
    });
  });
});

describe("a identidade da linha nasce no cliente", () => {
  it("o formato é estável: `L-` + 8 caracteres", () => {
    // O formato é contrato com o servidor (que preserva o id que recebe) e com
    // o log — mudá-lo é mudar o payload da comanda.
    for (let i = 0; i < 50; i += 1) expect(newLineId()).toMatch(/^L-[0-9a-f]{8}$/);
  });

  it("duas linhas criadas em sequência nunca colidem", () => {
    // É disto que depende "mais um chá vira uma linha nova": dois ids iguais
    // fariam o servidor deduplicar as duas de volta numa só.
    const ids = new Set(Array.from({ length: 200 }, () => newLineId()));
    expect(ids.size).toBe(200);
  });
});

describe("surface architecture guardrails", () => {
  it("drives POS tab association UX from the canonical tab lifecycle capability", () => {
    const capabilities = {
      tab_lifecycle: {
        requires_open_tab_for_cart: true,
        requires_tab_before_save: true,
        allows_direct_checkout_without_tab: true,
        tab_ref_max_length: 64,
        tab_ref_placeholder: "Mesa, nome ou referência",
        draft_association_target_states: ["empty"],
      },
    };

    expect(requiresOpenTabForCart(capabilities)).toBe(true);
    expect(requiresTabBeforeSave(capabilities)).toBe(true);
    expect(tabRefMaxLength(capabilities)).toBe(64);
    expect(tabRefPlaceholder(capabilities)).toBe("Mesa, nome ou referência");
    expect(draftAssociationTargetStates(capabilities)).toEqual(["empty"]);
    expect(requiresOpenTabForCart({ tab_lifecycle: { requires_open_tab_for_cart: false } })).toBe(false);
  });

  it("does not reach around POS projections to catalog, stock, or checkout contracts", () => {
    // O fechamento do DIA (antesala) consome a projection de closing do
    // backstage, cujo contrato carrega `available_qty` (reconciliação) — não é
    // reach-around de estoque/catálogo, então fica fora deste scan.
    const sources = readSources(join(process.cwd(), "app"))
      .filter((entry) => !entry.path.includes(`${join("components", "Ui")}${"/"}`))
      .filter((entry) => !entry.path.includes("closing"));
    const joined = sources.map((entry) => entry.content).join("\n");

    expect(joined).not.toContain("/api/v1/catalog");
    expect(joined).not.toContain("/api/v1/storefront");
    expect(joined).not.toContain("base_price_q");
    expect(joined).not.toContain("available_qty");
    expect(joined).not.toContain("Order.Status");
  });
});

describe("operator access", () => {
  it("recognizes Django/DRF auth failures as operator access states", () => {
    expect(statusCodeFromError({ statusCode: 403 })).toBe(403);
    expect(statusCodeFromError({ response: { status: 401 } })).toBe(401);
    expect(isOperatorAccessError({ statusCode: 403 })).toBe(true);
    expect(isOperatorAccessError({ response: { status: 401 } })).toBe(true);
    expect(isOperatorAccessError({ statusCode: 500 })).toBe(false);
  });

  it("builds an admin login URL without taking ownership of credentials", () => {
    expect(buildAdminLoginUrl({
      djangoBaseUrl: "https://shop.example.com/",
      nextPath: "/pos/",
    })).toBe("https://shop.example.com/admin/login/?next=%2Fpos%2F");

    expect(buildAdminLoginUrl({
      djangoBaseUrl: "http://127.0.0.1:8000",
      nextPath: "pos/",
    })).toBe("http://127.0.0.1:8000/admin/login/?next=%2Fpos%2F");

    expect(buildAdminLoginUrl({
      djangoBaseUrl: "http://127.0.0.1:8000",
      nextPath: "/admin/",
    })).toBe("http://127.0.0.1:8000/admin/login/?next=%2Fadmin%2F");
  });
});

function readSources(dir: string): Array<{ path: string; content: string }> {
  const entries: Array<{ path: string; content: string }> = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      entries.push(...readSources(path));
      continue;
    }
    if (/\.(ts|vue)$/.test(path)) {
      entries.push({ path, content: readFileSync(path, "utf8") });
    }
  }
  return entries;
}

function baseIntentState(overrides: Record<string, unknown> = {}) {
  return {
    tabRef: "00001007",
    tabSessionKey: "session-1",
    customerName: "",
    customerRef: "",
    customerPhone: "",
    customerTaxId: "",
    invoiceTaxId: "",
    customerEmail: "",
    customerMemoryAction: "",
    fulfillmentType: "pickup",
    deliveryAddress: "",
    deliveryAddressStructured: {},
    deliveryComplement: "",
    deliveryInstructions: "",
    deliveryDate: "",
    deliveryTimeSlot: "",
    deliveryFeeOverrideQ: null,
    orderNotes: "",
    paymentMethod: "cash",
    paymentCollection: "terminal",
    paymentTenders: [],
    tenderedQ: null,
    changeForQ: 0,
    receiptChannels: [],
    receiptEmail: "",
    manualDiscount: null,
    managerApproval: null,
    clientRequestId: "pos:test-base",
    items: [
      { line_id: "L-base0001", sku: "PAO", name: "Pao", price_q: 1200, qty: 1, notes: "" },
    ],
    ...overrides,
  };
}

describe("o QUANDO viaja na retirada também", () => {
  it("retirada agendada leva data e janela no intent", () => {
    // Estas duas linhas moravam dentro do bloco `if (fulfillmentType ===
    // "delivery")`, e era o terceiro portão do mesmo mal-entendido (os outros
    // dois eram do servidor). O operador combinava quinta às 10h para retirar, a
    // barra mostrava "Amanhã, 10:00 às 10:30" — e o intent subia SEM data. O
    // pedido nascia para hoje, calado, e nada na tela dizia isso.
    const payload = buildPosSaleIntent(baseIntentState({
      fulfillmentType: "pickup",
      deliveryDate: "2026-09-10",
      deliveryTimeSlot: "10:00-10:30",
    }) as Parameters<typeof buildPosSaleIntent>[0]);

    expect(payload.delivery_date).toBe("2026-09-10");
    expect(payload.delivery_time_slot).toBe("10:00-10:30");
  });

  it("mas a retirada continua sem ENDEREÇO e sem TAXA", () => {
    // *Onde* e *quanto* seguem sendo fatos da entrega. Só *quando* mudou de lado.
    const payload = buildPosSaleIntent(baseIntentState({
      fulfillmentType: "pickup",
      deliveryDate: "2026-09-10",
      deliveryAddress: "Rua A, 10",
      deliveryFeeOverrideQ: 500,
    }) as Parameters<typeof buildPosSaleIntent>[0]);

    expect(payload.delivery_address).toBeUndefined();
    expect(payload.delivery_fee_override_q).toBeUndefined();
    expect(payload.delivery_date).toBe("2026-09-10");
  });

  it("sem agendamento, nenhuma das duas chaves sobe", () => {
    const payload = buildPosSaleIntent(baseIntentState() as Parameters<typeof buildPosSaleIntent>[0]);

    expect(payload.delivery_date).toBeUndefined();
    expect(payload.delivery_time_slot).toBeUndefined();
  });
});

describe("resolvePayment (injeção de tenders → contrato)", () => {
  const t = (method: string, amount_q: number) => ({ method, amount_q, collection: "terminal" as const });

  it("dinheiro único com troco vai pelo caminho de caixa (sem tenders)", () => {
    const r = resolvePayment([t("cash", 5000)], 4300);
    expect(r.paymentMethod).toBe("cash");
    expect(r.paymentTenders).toEqual([]);
    expect(r.tenderedQ).toBe(5000);
  });

  it("dinheiro único exato também usa o caminho de caixa", () => {
    const r = resolvePayment([t("cash", 4300)], 4300);
    expect(r.tenderedQ).toBe(4300);
    expect(r.paymentTenders).toEqual([]);
  });

  it("um cartão: só o método (backend constrói o tender), sem replay", () => {
    const r = resolvePayment([t("card", 4300)], 4300);
    expect(r.paymentMethod).toBe("card");
    expect(r.paymentTenders).toEqual([]);
    expect(r.tenderedQ).toBeNull();
  });

  it("split deriva 'mixed' e envia as linhas", () => {
    const r = resolvePayment([t("card", 3000), t("cash", 1300)], 4300);
    expect(r.paymentMethod).toBe("mixed");
    expect(r.paymentTenders).toHaveLength(2);
    expect(r.tenderedQ).toBeNull();
  });

  it("sem tenders não resolve método", () => {
    expect(resolvePayment([], 4300).paymentMethod).toBe("");
  });
});
