// Balcão: "Consumir aqui" e "Para levar" (#3193, opção A do dono). O chip do balcão
// era a porta da encomenda, e quem queria levar caía nela. Agora são dois chips, o
// F8 troca entre eles, e a encomenda fica no seletor de modo.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import PosTabHeader from "~/components/PosTabHeader.vue";
import { buildPosSaleIntent } from "~/utils/posIntent";
import { TAB_DRAFT_FIELDS } from "~/utils/tabDraft";

const base = {
  salesMode: "counter", tabDisplay: "M1", hasOpenTab: true, canRename: false,
  customerName: "", customerPhone: "", customerTaxId: "", customerEmail: "", customerLookup: null,
  lookupBusy: false, searchResults: [], searchBusy: false, fulfillmentType: "pickup",
  fulfillmentLabel: "Retirada", scheduleLabel: "Para hoje", scheduled: false, loading: false,
} as const;

async function header(props: Record<string, unknown> = {}) {
  return mountSuspended(PosTabHeader, {
    props: { ...base, ...props },
    global: { stubs: { PosCustomerModal: true } },
  });
}

function chip(w: Awaited<ReturnType<typeof header>>, label: string) {
  return w.find('[data-context-entry="service"]').findAll("button")
    .find((b) => b.find(".sr-only").text() === label)!;
}

describe("PosTabHeader: comer aqui ou levar, no balcão", () => {
  it("o balcão mostra os dois chips, e Consumir aqui é o ligado por padrão", async () => {
    const w = await header();
    expect(chip(w, "Consumir aqui").attributes("aria-pressed")).toBe("true");
    expect(chip(w, "Para levar").attributes("aria-pressed")).toBe("false");
    // O chip de recebimento da encomenda não aparece no balcão.
    expect(w.find('[data-context-entry="fulfillment"]').exists()).toBe(false);
    w.unmount();
  });

  it("tocar em Para levar pede a troca, e o ligado acompanha a escolha", async () => {
    const w = await header();
    await chip(w, "Para levar").trigger("click");
    expect(w.emitted("counterServiceChange")).toEqual([["to_go"]]);
    // O toque não abre mais a porta da encomenda.
    expect(w.emitted("openFulfillment")).toBeUndefined();
    await w.setProps({ counterService: "to_go" });
    expect(chip(w, "Para levar").attributes("aria-pressed")).toBe("true");
    expect(chip(w, "Consumir aqui").attributes("aria-pressed")).toBe("false");
    w.unmount();
  });

  it("na encomenda os dois chips saem e volta o recebimento", async () => {
    const w = await header({ salesMode: "order" });
    expect(w.find('[data-context-entry="service"]').exists()).toBe(false);
    expect(w.find('[data-context-entry="fulfillment"]').text()).toContain("Retirada");
    w.unmount();
  });
});

describe("a escolha viaja com a venda", () => {
  const state = {
    tabRef: "7", tabSessionKey: "s-7", items: [], customerName: "", customerRef: "", customerPhone: "",
    customerTaxId: "", invoiceTaxId: "", customerEmail: "", customerMemoryAction: "",
    fulfillmentType: "pickup", deliveryAddress: "", deliveryAddressStructured: {}, deliveryComplement: "",
    deliveryInstructions: "", deliveryDate: "", deliveryTimeSlot: "", deliveryFeeOverrideQ: null,
    orderNotes: "", paymentMethod: "", paymentCollection: "terminal", paymentTenders: [], tenderedQ: null,
    changeForQ: 0, receiptChannels: [], receiptEmail: "",
  } as unknown as Parameters<typeof buildPosSaleIntent>[0];

  it("no balcão sobe counter_service; na encomenda não", () => {
    const counter = buildPosSaleIntent({ ...state, salesMode: "counter", counterService: "to_go" });
    expect(counter.counter_service).toBe("to_go");
    const order = buildPosSaleIntent({ ...state, salesMode: "order", counterService: "to_go" });
    expect(order.counter_service).toBeUndefined();
  });

  it("a escolha volta junto com o que não chegou ao servidor (rascunho da comanda)", () => {
    expect(TAB_DRAFT_FIELDS).toContain("counterService");
  });
});
