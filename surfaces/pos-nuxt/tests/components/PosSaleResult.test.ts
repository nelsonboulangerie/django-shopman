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
    hasProof: true,
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
      props: props({ result: result({ fiscalExpected: true }) }),
    });
    const buttons = wrapper.findAll("button");
    await buttons.find((b) => b.text().includes("Imprimir recibo"))!.trigger("click");
    await buttons.find((b) => b.text().includes("DANFE"))!.trigger("click");
    await buttons.find((b) => b.text().includes("Cancelar venda"))!.trigger("click");
    expect(wrapper.emitted("printReceipt")).toHaveLength(1);
    expect(wrapper.emitted("printDanfe")).toHaveLength(1);
    expect(wrapper.emitted("cancelSale")).toHaveLength(1);
    expect(wrapper.find(`a[href="http://gestor.test/PDV-042"]`).exists()).toBe(true);
  });
});
