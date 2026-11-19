import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import OrderDetailPending from "../../app/components/OrderDetailPending.vue";
import type {
  CancelledMoneyProjection,
  OrderPendingProjection,
} from "../../app/generated/ordersContract";

// WP-G05: a faixa "O que falta neste pedido". Quem decide o que falta, em que tom e com
// qual gesto é o servidor; estes testes prendem o que a faixa faz com a lista: cada
// linha com o fato, o motivo e o botão ao lado, e o toque subindo para a página.

const stubs = {
  Icon: { props: ["name"], template: "<i :data-icon='name' />" },
  OperatorCountChip: { props: ["count"], template: "<span data-count>{{ count }}</span>" },
};

const action = (ref: string, label: string, over: Record<string, unknown> = {}) => ({
  ref, label, enabled: true, reason: "", href: "", ...over,
});
const pending = (over: Partial<OrderPendingProjection> = {}): OrderPendingProjection => ({
  key: "nfce", tone: "error", label: "NFC-e não autorizada", reason: "", actions: [], failure: "", ...over,
});
const money = (over: Partial<CancelledMoneyProjection> = {}): CancelledMoneyProjection => ({
  state: "refunded", label: "Estornado", amount_display: "R$ 18,70",
  customer_line: "Devolvemos os R$ 18,70 do seu Pix para a mesma conta.", settled: true, ...over,
});

function faixa(props: Record<string, unknown>) {
  return mount(OrderDetailPending, { props, global: { stubs } });
}

describe("OrderDetailPending", () => {
  it("sem nada pendente e sem dinheiro de cancelado, não desenha nada", () => {
    const w = faixa({ pending: [], money: null });
    expect(w.find("[data-order-pending]").exists()).toBe(false);
  });

  it("cada linha traz o fato, o motivo e o botão que resolve; o toque sobe com a ação", async () => {
    const w = faixa({
      pending: [
        pending({
          reason: "Resposta do emissor: Rejeição 778: NCM inexistente. Se reprocessar não resolver, chame o contador.",
          actions: [action("requeue-fiscal", "Reprocessar NFC-e")],
        }),
        pending({
          key: "danfe", tone: "warning", label: "DANFE não impressa",
          reason: "A impressora de Balcão recusou a DANFE. Confira o papel e imprima de novo.",
          actions: [action("print-danfe", "Imprimir DANFE")],
        }),
      ],
    });

    expect(w.get("h2").text()).toBe("O que falta neste pedido");
    expect(w.get("[data-count]").text()).toBe("2");
    const rows = w.findAll("[data-pending]");
    expect(rows.map((row) => row.attributes("data-pending"))).toEqual(["nfce", "danfe"]);
    expect(rows[0]!.text()).toContain("NFC-e não autorizada");
    expect(rows[0]!.get("[data-pending-reason]").text()).toContain("Rejeição 778: NCM inexistente");
    expect(rows[1]!.get("[data-pending-reason]").text()).toContain("recusou a DANFE");

    await w.get('[data-pending-action="requeue-fiscal"]').trigger("click");
    await w.get('[data-pending-action="print-danfe"]').trigger("click");
    expect(w.emitted("act")).toEqual([["requeue-fiscal"], ["print-danfe"]]);
  });

  it("um gesto principal na faixa: o da primeira linha que pede alguém; cancelar é vermelho", () => {
    const w = faixa({
      pending: [
        pending({
          key: "payment", label: "Pix expirado", reason: "Gerado às 21h55 · expirou às 22h25.",
          actions: [
            action("cancel", "Cancelar pedido (pede gerente)"),
            action("contact-customer", "Chamar no WhatsApp", { href: "https://wa.me/5543999990000" }),
          ],
        }),
        pending({ actions: [action("requeue-fiscal", "Reprocessar NFC-e")] }),
      ],
    });

    const cancel = w.get('[data-pending-action="cancel"]');
    expect(cancel.attributes("color")).toBe("error");
    expect(cancel.attributes("variant")).toBe("solid");
    const contact = w.get('[data-pending-action="contact-customer"]');
    expect(contact.attributes("variant")).toBe("outline");
    expect(contact.attributes("color")).toBe("neutral");
    // A conversa abre fora do Gestor: é link, não ação do pedido.
    expect(contact.attributes("href")).toBe("https://wa.me/5543999990000");
    expect(contact.attributes("target")).toBe("_blank");
    const requeue = w.get('[data-pending-action="requeue-fiscal"]');
    expect(requeue.attributes("variant")).toBe("outline");
  });

  it("espera saudável: tom de informação, ampulheta, nenhum botão principal (P2-26)", () => {
    const w = faixa({
      pending: [
        pending({
          key: "advance", tone: "info", label: "Aguardando o dia da encomenda",
          reason: "Combinado: Amanhã · 08h às 10h. O preparo abre nesse dia.",
        }),
        pending({
          key: "payment", tone: "info", label: "Aguardando pagamento", reason: "Link gerado às 14h02 · vence às 14h32.",
          actions: [action("resend-payment-link", "Reenviar link de pagamento")],
        }),
      ],
    });

    const row = w.get('[data-pending="advance"]');
    expect(row.attributes("data-pending-tone")).toBe("info");
    expect(row.get("i").attributes("data-icon")).toBe("lucide:hourglass");
    expect(row.get("i").classes()).not.toContain("text-error");
    expect(row.text()).toContain("Em espera: Aguardando o dia da encomenda");
    // Espera não ganha o botão cheio: o reenvio fica à mão, secundário.
    expect(w.get('[data-pending-action="resend-payment-link"]').attributes("variant")).toBe("outline");
    expect(w.html()).not.toContain("text-error");
  });

  it("ação que não pode agora fica no lugar, desligada, com o motivo ESCRITO", async () => {
    const w = faixa({
      pending: [pending({
        actions: [action("requeue-fiscal", "Reprocessar NFC-e", {
          enabled: false, reason: "Identifique uma pessoa com permissão para gerenciar pedidos.",
        })],
      })],
    });

    const button = w.get('[data-pending-action="requeue-fiscal"]');
    expect(button.attributes("disabled")).toBeDefined();
    expect(w.get("[data-pending-blocked]").text()).toBe("Identifique uma pessoa com permissão para gerenciar pedidos.");
    await button.trigger("click");
    expect(w.emitted("act")).toBeUndefined();
  });

  it("gravação em andamento trava os gestos do pedido; imprimindo trava só a DANFE", () => {
    const lines = [
      pending({ actions: [action("requeue-fiscal", "Reprocessar NFC-e")] }),
      pending({ key: "danfe", tone: "warning", label: "DANFE não impressa", actions: [action("print-danfe", "Imprimir DANFE")] }),
    ];
    const busy = faixa({ pending: lines, busy: true });
    expect(busy.get('[data-pending-action="requeue-fiscal"]').attributes("disabled")).toBeDefined();

    const printing = faixa({ pending: lines, danfePrinting: true });
    const print = printing.get('[data-pending-action="print-danfe"]');
    expect(print.attributes("disabled")).toBeDefined();
    expect(print.text()).toContain("Imprimindo…");
    expect(printing.get('[data-pending-action="requeue-fiscal"]').attributes("disabled")).toBeUndefined();
  });

  it("estorno pedido é linha da lista; estornado é a resposta do dinheiro, sem título de pendência (P1-15)", () => {
    const requested = faixa({
      pending: [pending({
        key: "refund", tone: "info", label: "Estorno pedido",
        reason: "A devolução de R$ 18,70 foi pedida e ainda não foi confirmada. O cliente lê na loja: “Estamos devolvendo os R$ 18,70 do seu Pix para a mesma conta.”",
      })],
      money: money({ state: "refund_requested", label: "Estorno pedido", settled: false }),
    });
    expect(requested.get('[data-pending="refund"]').text()).toContain("Estorno pedido");
    expect(requested.find("[data-order-money]").exists()).toBe(false);

    const refunded = faixa({ pending: [], money: money() });
    expect(refunded.find("h2").exists()).toBe(false);
    const line = refunded.get("[data-order-money]");
    expect(line.attributes("data-order-money-state")).toBe("refunded");
    expect(line.text()).toContain("Dinheiro do pedido cancelado: Estornado");
    expect(line.text()).toContain("O cliente lê na loja: “Devolvemos os R$ 18,70 do seu Pix para a mesma conta.”");
  });

  it("estorno que não saiu pede alguém, em vermelho, e não repete a frase da loja", () => {
    const w = faixa({
      pending: [pending({
        key: "refund", label: "Estorno não saiu",
        reason: "A devolução de R$ 18,70 não chegou ao cliente. O suporte já recebeu o aviso e conclui o estorno no Pix ou no cartão. Se o cliente perguntar, diga que o estorno está sendo feito.",
      })],
      money: money({ state: "refund_failed", label: "Estorno não saiu", customer_line: "", settled: false }),
    });
    const row = w.get('[data-pending="refund"]');
    expect(row.attributes("data-pending-tone")).toBe("error");
    expect(row.text()).toContain("Precisa de alguém: Estorno não saiu");
    expect(w.find("[data-order-money]").exists()).toBe(false);
    expect(w.text()).not.toContain("O cliente lê na loja");
  });

  // WP-G13: a linha "Estorno não saiu" ganha o gesto, e a falha fica escrita nela.
  describe("tentar o estorno de novo", () => {
    const failed = (over: Partial<OrderPendingProjection> = {}) => pending({
      key: "refund", label: "Estorno não saiu",
      reason: "A devolução de R$ 22,00 não chegou ao cliente. Tentar de novo pede esse estorno outra vez ao Pix do cliente, com a autorização de um gerente.",
      actions: [action("refund-retry", "Tentar o estorno de novo")],
      ...over,
    });
    const failedMoney = money({ state: "refund_failed", label: "Estorno não saiu", amount_display: "R$ 22,00", customer_line: "", settled: false });

    it("o botão mora na linha, é o gesto principal e o toque sobe com a ação", async () => {
      const w = faixa({ pending: [failed()], money: failedMoney });
      const row = w.get('[data-pending="refund"]');
      expect(row.attributes("data-pending-tone")).toBe("error");
      expect(row.text()).toContain("pede esse estorno outra vez ao Pix do cliente");
      expect(row.text()).not.toContain("suporte");
      expect(row.find("[data-pending-failure]").exists()).toBe(false);
      const button = w.get('[data-pending-action="refund-retry"]');
      expect(button.text()).toBe("Tentar o estorno de novo");
      expect(button.attributes("variant")).toBe("solid");
      expect(button.attributes("color")).toBe("primary");

      await button.trigger("click");
      expect(w.emitted("act")).toEqual([["refund-retry"]]);
    });

    it("enquanto o estorno vai ao meio de pagamento, o botão diz isso e não aceita outro toque", async () => {
      const w = faixa({ pending: [failed()], money: failedMoney, busy: true, refundRetrying: true });
      const button = w.get('[data-pending-action="refund-retry"]');
      expect(button.text()).toBe("Tentando o estorno…");
      expect(w.getComponent('[data-pending-action="refund-retry"]').props("loading")).toBe(true);
      expect(button.attributes("disabled")).toBeDefined();
      await button.trigger("click");
      expect(w.emitted("act")).toBeUndefined();
    });

    it("o que o meio de pagamento respondeu fica escrito na linha, em tom de erro", () => {
      const failure = "Última tentativa, em 18/11 às 14h32: O Pix não aceitou o estorno. Nada foi devolvido ao cliente. Chame o suporte.";
      const w = faixa({ pending: [failed({ failure })], money: failedMoney });
      const told = w.get('[data-pending="refund"] [data-pending-failure]');
      expect(told.text()).toBe(failure);
      expect(told.classes()).toContain("text-error");
      expect(told.attributes("role")).toBe("status");
      // O gesto continua de pé: uma tentativa nova é permitida.
      expect(w.get('[data-pending-action="refund-retry"]').attributes("disabled")).toBeUndefined();
      expect(w.text()).not.toMatch(/[—–]/);
    });

    it("quem não pode vê o botão desligado, com o motivo escrito", () => {
      const reason = "Identifique uma pessoa com permissão para gerenciar pedidos.";
      const w = faixa({
        pending: [failed({ actions: [action("refund-retry", "Tentar o estorno de novo", { enabled: false, reason })] })],
        money: failedMoney,
      });
      expect(w.get('[data-pending-action="refund-retry"]').attributes("disabled")).toBeDefined();
      expect(w.get("[data-pending-blocked]").text()).toBe(reason);
    });
  });

  it("nenhum texto da faixa usa travessão", () => {
    const w = faixa({ pending: [pending({ actions: [action("requeue-fiscal", "Reprocessar NFC-e")] })], money: money() });
    expect(w.text()).not.toMatch(/[—–]/);
  });
});
