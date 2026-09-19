// Tela de resultado — o palco do troco e o CTA "Nova venda". O comportamento
// decidido em presentation (auto-avanço, Enter) tem prova própria; aqui se
// prova o que a TELA faz com ele: herói do troco, contagem visível/cancelável
// e a saída explícita com PIX pendente.
import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosSaleResult from "~/components/PosSaleResult.vue";
import type { PaymentProofView } from "~/presentation/payment";
import type { PosSaleResultSnapshot } from "~/presentation/saleResult";
import { formatBRL } from "~/utils/posIntent";

function result(overrides: Partial<PosSaleResultSnapshot> = {}): PosSaleResultSnapshot {
  return {
    salesMode: "counter",
    orderRef: "PDV-042",
    nextUrl: "http://gestor.test/PDV-042",
    payment: null,
    receipt: {
      orderRef: "PDV-042",
      tabDisplay: "1007",
      customerName: "",
      items: [],
      totalDisplay: "R$ 10,00",
      payments: [],
      fulfillmentLabel: "Retirada",
      printedAtMs: 0,
    },
    fiscalExpected: false,
    fiscalState: "not_expected",
    changeQ: 0,
    ...overrides,
  };
}

function pixProof(): PaymentProofView {
  return {
    method: "pix",
    icon: "lucide:qr-code",
    amountDisplay: "R$ 10,00",
    status: "pending",
    tone: "info",
    message: "",
    qrCodeSrc: "data:image/png;base64,abc",
    copyPaste: "000201...",
    checkoutUrl: "",
    isPix: true,
    isCard: false,
    isLink: false,
    hasProof: true,
    expiresDisplay: "",
  };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    result: result(),
    pixStatus: "idle" as const,
    canCancel: true,
    danfeScreenUrl: "",
    printingReceipt: false,
    printingDanfe: false,
    ...overrides,
  };
}

describe("PosSaleResult — o palco pós-venda", () => {
  it("com troco: herói gigante com aria-live e SEM contagem de auto-avanço", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ changeQ: 3370 }) }),
    });
    const text = wrapper.text();
    expect(text).toContain("Troco");
    expect(text).toContain(formatBRL(3370));
    expect(wrapper.find('[aria-live="polite"]').exists()).toBe(true);
    expect(text).not.toContain("Nova venda em"); // a tela nunca some sozinha
  });

  it("com cliente vinculado, o título agradece pelo primeiro nome", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ receipt: { ...result().receipt, customerName: "Maria da Silva" } }) }),
    });
    expect(wrapper.text()).toContain("Venda concluída. Obrigado, Maria!");
  });

  it("pagamento exato: contagem visível e cancelável por qualquer toque", async () => {
    const wrapper = await mountSuspended(PosSaleResult, { props: props() });
    expect(wrapper.text()).toContain("Nova venda em 5s");
    await wrapper.find("[data-sale-result]").trigger("pointerdown");
    expect(wrapper.text()).not.toContain("Nova venda em");
  });

  it("encomenda permanece para conferência e impressão, mesmo paga", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ salesMode: "order" }) }),
    });
    expect(wrapper.text()).toContain("Encomenda registrada");
    expect(wrapper.text()).not.toContain("Venda concluída");
    expect(wrapper.text()).not.toContain("Nova venda em");
    expect(wrapper.find(`a[href="http://gestor.test/PDV-042"]`).exists()).toBe(true);
  });

  it("encomenda lê de volta como e quando; balcão não", async () => {
    const order = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ salesMode: "order", fulfillmentLabel: "Entrega · Centro", scheduleLabel: "sáb, 20/09, 10:00 às 10:30" }) }),
    });
    const readback = order.find("[data-order-readback]");
    expect(readback.exists()).toBe(true);
    expect(readback.text()).toContain("Confirme com o cliente");
    expect(readback.text()).toContain("Entrega · Centro");
    expect(readback.text()).toContain("sáb, 20/09, 10:00 às 10:30");
    order.unmount();

    const counter = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ salesMode: "counter", fulfillmentLabel: "Retirada", scheduleLabel: "Hoje" }) }),
    });
    expect(counter.find("[data-order-readback]").exists()).toBe(false);
    counter.unmount();
  });

  it("a ficha do pedido fica na fileira de saídas de papel, só na encomenda", async () => {
    const order = await mountSuspended(PosSaleResult, { props: props({ result: result({ salesMode: "order" }), printingTicket: false }) });
    const button = order.findAll("button").find((b) => b.text().includes("Imprimir ficha do pedido"));
    expect(button).toBeDefined();
    await button!.trigger("click");
    expect(order.emitted("printTicket")).toHaveLength(1);
    await order.setProps({ printingTicket: true });
    expect(order.text()).toContain("Imprimindo…");
    order.unmount();

    const counter = await mountSuspended(PosSaleResult, { props: props({ result: result({ salesMode: "counter" }) }) });
    expect(counter.text()).not.toContain("ficha do pedido");
    counter.unmount();
  });

  // COBRANÇA NA ENTREGA/RETIRADA: o dinheiro ainda não entrou. A tela anunciava
  // "TROCO R$ 58 · Confira o troco" e travava Enter e auto-avanço por um
  // dinheiro que só o entregador vai ver.
  it("cobrança na entrega: 'Troco a separar' discreto, sem herói e sem travar", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ changeQ: 0, courierChangeQ: 5800 }) }),
    });
    const text = wrapper.text();
    expect(wrapper.find("[data-courier-change]").text()).toBe(`Troco a separar: ${formatBRL(5800)}`);
    expect(text).not.toContain("Confira o troco");
    expect(wrapper.find('[aria-live="polite"]').exists()).toBe(false);
    // auto-avanço e Enter seguem vivos: não há dinheiro na gaveta a conferir
    expect(text).toContain("Nova venda em 5s");
  });

  it("encomenda: Enter não dispensa a leitura de volta", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ salesMode: "order", fulfillmentLabel: "Retirada", scheduleLabel: "Hoje, a partir das 9h" }) }),
    });
    expect(wrapper.text()).not.toContain("Enter também avança.");
  });

  it("o CTA emite newSale", async () => {
    const wrapper = await mountSuspended(PosSaleResult, { props: props() });
    const cta = wrapper.findAll("button").find((b) => b.text().includes("Nova venda"));
    await cta!.trigger("click");
    expect(wrapper.emitted("newSale")).toHaveLength(1);
  });

  it("PIX aguardando: sem contagem, saída nomeada como gesto deliberado", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ payment: pixProof() }), pixStatus: "polling" }),
    });
    const text = wrapper.text();
    expect(text).not.toContain("Nova venda em");
    expect(text).toContain("Nova venda mesmo assim");
    expect(text).toContain("vira um aviso no topo");
  });

  it("verbos secundários emitem os handlers de sempre", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ fiscalExpected: true, fiscalState: "authorized" }) }),
    });
    const buttons = wrapper.findAll("button");
    await buttons.find((b) => b.text().includes("Imprimir recibo"))!.trigger("click");
    await buttons.find((b) => b.text().includes("DANFE"))!.trigger("click");
    await buttons.find((b) => b.text().includes("Cancelar venda"))!.trigger("click");
    expect(wrapper.emitted("printReceipt")).toHaveLength(1);
    expect(wrapper.emitted("printDanfe")).toHaveLength(1);
    expect(wrapper.emitted("cancelSale")).toHaveLength(1);
    expect(wrapper.find(`a[href="http://gestor.test/PDV-042"]`).exists()).toBe(false);
  });
});

// A DANFE por EXISTÊNCIA da nota, não por previsão: o botão aparecia por
// `fiscalExpected` e o endpoint respondia 409 até a SEFAZ autorizar — no Pix,
// durante toda a espera.
describe("PosSaleResult — a DANFE obedece ao estado da nota", () => {
  const danfeButton = (w: Awaited<ReturnType<typeof mountSuspended>>) => w.find("[data-danfe-action]");

  it("authorized: 'Imprimir DANFE' vivo, e 'Ver a nota' para quem tem acesso", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ fiscalExpected: true, fiscalState: "authorized" }), danfeScreenUrl: "http://api.test/fiscal/danfe/PDV-042/" }),
    });
    const button = danfeButton(wrapper);
    expect(button.text()).toContain("Imprimir DANFE");
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("printDanfe")).toHaveLength(1);
    expect(wrapper.text()).toContain("Ver a nota");
  });

  it("queued: botão desabilitado 'NFC-e na fila…', sem 'Ver a nota'", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ fiscalExpected: true, fiscalState: "queued" }), danfeScreenUrl: "http://api.test/fiscal/danfe/PDV-042/" }),
    });
    const button = danfeButton(wrapper);
    expect(button.text()).toContain("NFC-e na fila…");
    expect(button.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).not.toContain("Ver a nota");
    // e a promoção (o 409 virou 200) troca o botão sem remontar
    await wrapper.setProps({ result: result({ fiscalExpected: true, fiscalState: "authorized" }) });
    expect(danfeButton(wrapper).text()).toContain("Imprimir DANFE");
    expect(danfeButton(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("awaiting_payment: a frase diz o quando, sem botão", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ fiscalExpected: true, fiscalState: "awaiting_payment" }) }),
    });
    expect(danfeButton(wrapper).exists()).toBe(false);
    expect(wrapper.find("[data-danfe-awaiting]").text()).toContain("NFC-e sai quando o pagamento confirmar");
  });

  it("failed: alerta apontando as Últimas vendas, sem botão", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ fiscalExpected: true, fiscalState: "failed" }) }),
    });
    expect(danfeButton(wrapper).exists()).toBe(false);
    const alert = wrapper.find("[data-fiscal-failed]");
    expect(alert.attributes("role")).toBe("alert");
    expect(alert.text()).toContain("NFC-e falhou — veja Últimas vendas");
  });

  it("not_expected: nada sobre a DANFE, mesmo com URL da nota", async () => {
    const wrapper = await mountSuspended(PosSaleResult, {
      props: props({ result: result({ fiscalExpected: false, fiscalState: "not_expected" }), danfeScreenUrl: "http://api.test/fiscal/danfe/PDV-042/" }),
    });
    expect(danfeButton(wrapper).exists()).toBe(false);
    expect(wrapper.text()).not.toContain("DANFE");
    expect(wrapper.text()).not.toContain("NFC-e");
    expect(wrapper.text()).not.toContain("Ver a nota");
  });
});
