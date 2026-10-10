import { describe, expect, it } from "vitest";

import {
  cashCloseBlockedByQueue,
  classifyOfflineSend,
  offlineQueueAlert,
  offlineSaleBlockers,
  offlineSaleLabel,
  offlineSaleReview,
} from "~/presentation/offlineSales";
import { createOfflineSaleQueue } from "~/utils/offlineSaleQueue";
import { memoryOfflineSaleStore } from "~/utils/offlineSaleStore";
import type { OfflineSale } from "~/presentation/offlineSales";
import type { POSCartItem } from "~/types/pos";

const item = (over: Partial<POSCartItem> = {}): POSCartItem => ({
  line_id: "L-1",
  sku: "PAO",
  name: "Pão",
  qty: 2,
  price_q: 600,
  notes: "",
  ...over,
} as POSCartItem);

const counterSale = {
  salesMode: "counter",
  fulfillmentType: "pickup",
  items: [item()],
  orderDiscountValue: "",
  tenderMethods: ["cash"],
  paymentCollection: "terminal",
};

describe("offlineSaleBlockers", () => {
  it("venda de balcão em dinheiro segue sem conexão", () => {
    expect(offlineSaleBlockers(counterSale)).toEqual([]);
  });

  it("maquininha (crédito, débito, externo) segue sem conexão", () => {
    expect(offlineSaleBlockers({ ...counterSale, tenderMethods: ["credit", "debit", "external"] })).toEqual([]);
  });

  it("encomenda, entrega, desconto e Pix esperam a conexão, cada um com o motivo", () => {
    expect(offlineSaleBlockers({ ...counterSale, salesMode: "order" })[0]).toMatch(/Encomenda/);
    expect(offlineSaleBlockers({ ...counterSale, fulfillmentType: "delivery" })[0]).toMatch(/Entrega/);
    expect(offlineSaleBlockers({ ...counterSale, items: [item({ discount: { type: "percent", value: 10, reason: "" } } as Partial<POSCartItem>)] })[0])
      .toMatch(/Desconto precisa de conexão/);
    expect(offlineSaleBlockers({ ...counterSale, orderDiscountValue: "5" })[0]).toMatch(/Desconto/);
    expect(offlineSaleBlockers({ ...counterSale, tenderMethods: ["pix"] })[0]).toBe("Pix precisa de conexão. Receba em dinheiro ou na maquininha.");
    expect(offlineSaleBlockers({ ...counterSale, paymentCollection: "on_delivery" })[0]).toMatch(/Receber depois/);
  });
});

describe("offlineSaleReview", () => {
  it("soma pela última leitura e diz de quando são os preços", () => {
    const review = offlineSaleReview({
      items: [item(), item({ line_id: "L-2", sku: "CAFE", qty: 1, price_q: 800 })],
      tenders: [{ method: "cash", amount_q: 5000 }],
      intentVersion: "pos.sale-intent.v1",
      pricesAt: "2026-10-10T17:05:00.000Z",
    });
    expect(review.total_q).toBe(2000);
    expect(review.change_q).toBe(3000);
    expect(review.offline?.prices_at).toBe("2026-10-10T17:05:00.000Z");
    expect(review.warnings[0]?.code).toBe("offline_prices");
    expect(review.warnings[0]?.message).toMatch(/^Sem conexão: total pelos preços das \d\d:\d\d\./);
    expect(review.requires_manager_approval).toBe(false);
  });
});

describe("classifyOfflineSend", () => {
  it("pedido devolvido = enviada", () => {
    expect(classifyOfflineSend({ response: { ok: true, order_ref: "NB-1" } })).toEqual({ kind: "sent", orderRef: "NB-1" });
    expect(classifyOfflineSend({ response: { ok: true, order_ref: "NB-1", offline_note: "" } }))
      .toEqual({ kind: "sent", orderRef: "NB-1" });
  });

  it("comanda mudada em outro dispositivo: a venda entra e traz a frase do balcão", () => {
    const note = "Itens lançados em outro dispositivo seguem abertos na comanda 12.";
    expect(classifyOfflineSend({ response: { ok: true, order_ref: "NB-2", offline_note: note } }))
      .toEqual({ kind: "sent", orderRef: "NB-2", note });
  });

  it("rede, 5xx e sessão param a rodada sem marcar a venda", () => {
    expect(classifyOfflineSend({ failure: { status: 0 } })).toMatchObject({ kind: "retry", reason: "network" });
    expect(classifyOfflineSend({ failure: { status: 503 } })).toMatchObject({ kind: "retry", reason: "server" });
    expect(classifyOfflineSend({ failure: { status: 401 } })).toMatchObject({ kind: "retry", reason: "session" });
    expect(classifyOfflineSend({ response: {} })).toMatchObject({ kind: "retry" });
  });

  it("recusa do servidor vira conflito com o motivo e o total novo", () => {
    const outcome = classifyOfflineSend({
      failure: {
        status: 422,
        data: { error: { code: "total_changed", message: "O total mudou.", context: { new_total_q: 1300 } } },
      },
    });
    expect(outcome).toEqual({ kind: "conflict", error: { code: "total_changed", message: "O total mudou.", newTotalQ: 1300 } });
  });

  it("pedido criado com cobrança incerta sai da fila: a venda existe", () => {
    expect(classifyOfflineSend({ failure: { status: 502, data: { error: { order_created: true, order_ref: "NB-9" } } } }))
      .toEqual({ kind: "sent", orderRef: "NB-9" });
  });
});

describe("offlineQueueAlert", () => {
  it("sem conexão e sem fila: diz que o balcão continua e o que espera", () => {
    const alert = offlineQueueAlert({ online: false, pending: 0, conflicts: 0, sending: false });
    expect(alert?.title).toBe("Sem conexão. O balcão continua vendendo.");
    expect(alert?.actionLabel).toBe("O que funciona agora");
  });

  it("sem conexão com fila: conta as pendentes", () => {
    expect(offlineQueueAlert({ online: false, pending: 2, conflicts: 0, sending: false })?.title)
      .toBe("Sem conexão. 2 vendas esperando envio.");
  });

  it("com conexão: some quando a fila esvazia; recusa tem precedência", () => {
    expect(offlineQueueAlert({ online: true, pending: 0, conflicts: 0, sending: false })).toBeNull();
    expect(offlineQueueAlert({ online: true, pending: 1, conflicts: 0, sending: true })?.title).toBe("Enviando 1 venda guardada…");
    expect(offlineQueueAlert({ online: true, pending: 3, conflicts: 1, sending: false })?.color).toBe("error");
  });

  it("nenhuma frase usa travessão", () => {
    const all = [
      offlineQueueAlert({ online: false, pending: 0, conflicts: 0, sending: false }),
      offlineQueueAlert({ online: false, pending: 1, conflicts: 0, sending: false }),
      offlineQueueAlert({ online: true, pending: 2, conflicts: 0, sending: false }),
      offlineQueueAlert({ online: true, pending: 0, conflicts: 2, sending: false }),
    ];
    for (const alert of all) expect(`${alert?.title} ${alert?.description}`).not.toMatch(/[—–]/);
    expect(cashCloseBlockedByQueue(1)).not.toMatch(/[—–]/);
  });
});

describe("offlineSaleLabel", () => {
  it("rótulo curto a partir da chave", () => {
    expect(offlineSaleLabel("pos:1234-abcd")).toBe("Sem conexão ABCD");
  });
});

function sale(id: string, capturedAt: string): OfflineSale {
  return {
    id,
    capturedAt,
    pricesAt: capturedAt,
    body: { client_request_id: id, expected_total_q: 1200 },
    totalQ: 1200,
    itemCount: 1,
    paymentLabel: "Dinheiro",
    status: "pending",
    attempts: 0,
  };
}

describe("createOfflineSaleQueue", () => {
  it("guarda, reenvia em ordem de cobrança e esvazia", async () => {
    const sent: string[] = [];
    const queue = createOfflineSaleQueue({
      store: memoryOfflineSaleStore(),
      send: async (body) => {
        sent.push(String(body.client_request_id));
        return { ok: true, order_ref: `NB-${sent.length}` };
      },
      readFailure: () => ({ status: 0 }),
    });
    await queue.enqueue(sale("b", "2026-10-10T17:02:00Z"));
    await queue.enqueue(sale("a", "2026-10-10T17:01:00Z"));
    expect(queue.pending.value).toHaveLength(2);

    const report = await queue.flush();

    expect(sent).toEqual(["a", "b"]);
    expect(report.sent.map((row) => row.orderRef)).toEqual(["NB-1", "NB-2"]);
    expect(queue.unsent.value).toBe(0);
  });

  it("rede caída para a rodada e mantém tudo na fila", async () => {
    let calls = 0;
    const store = memoryOfflineSaleStore();
    const queue = createOfflineSaleQueue({
      store,
      send: async () => {
        calls += 1;
        throw { status: 0 };
      },
      readFailure: (error) => error as { status: number },
    });
    await queue.enqueue(sale("a", "2026-10-10T17:01:00Z"));
    await queue.enqueue(sale("b", "2026-10-10T17:02:00Z"));

    const report = await queue.flush();

    expect(report.stopped).toBe("network");
    expect(calls).toBe(1);
    expect((await store.list()).map((row) => row.status)).toEqual(["pending", "pending"]);
  });

  it("recusa marca só aquela venda e a rodada segue; total novo reenvia com o número do servidor", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    let refuse = true;
    const queue = createOfflineSaleQueue({
      store: memoryOfflineSaleStore(),
      send: async (body) => {
        bodies.push(body);
        if (body.client_request_id === "a" && refuse) {
          throw { status: 422, data: { error: { code: "total_changed", message: "O total mudou.", context: { new_total_q: 1300 } } } };
        }
        return { ok: true, order_ref: `NB-${String(body.client_request_id)}` };
      },
      readFailure: (error) => error as { status: number; data?: unknown },
    });
    await queue.enqueue(sale("a", "2026-10-10T17:01:00Z"));
    await queue.enqueue(sale("b", "2026-10-10T17:02:00Z"));

    const first = await queue.flush();
    expect(first.conflicts).toBe(1);
    expect(first.sent.map((row) => row.id)).toEqual(["b"]);
    expect(queue.conflicts.value[0]?.lastError?.newTotalQ).toBe(1300);

    refuse = false;
    const second = await queue.sendWithServerTotal("a");
    expect(second.sent.map((row) => row.id)).toEqual(["a"]);
    expect(bodies.at(-1)?.expected_total_q).toBe(1300);
    // A chave da venda é a mesma: o servidor dedupe o reenvio.
    expect(bodies.at(-1)?.client_request_id).toBe("a");
    expect(queue.unsent.value).toBe(0);
  });

  it("uma rodada por vez", async () => {
    let release: () => void = () => {};
    const queue = createOfflineSaleQueue({
      store: memoryOfflineSaleStore(),
      send: () => new Promise((resolve) => { release = () => resolve({ ok: true, order_ref: "NB-1" }); }),
      readFailure: () => ({ status: 0 }),
    });
    await queue.enqueue(sale("a", "2026-10-10T17:01:00Z"));
    const running = queue.flush();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect((await queue.flush()).stopped).toBe("busy");
    release();
    expect((await running).sent).toHaveLength(1);
  });
});
