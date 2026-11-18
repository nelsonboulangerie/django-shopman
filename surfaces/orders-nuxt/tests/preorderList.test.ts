// WP-G03 (EXCELENCIA-GESTOR P1-09, P1-10, P2-02, P2-03): a lista de Encomendas que
// responde. A linha diz quando, como, se está paga e se a produção cobre; quem espera
// o pagamento não "precisa de você"; o atalho abre AQUELA encomenda no PDV; e o aceite
// diz para onde a encomenda foi.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  acceptedIntoPreorders,
  AWAITING_PAYMENT_LABEL,
  preorderFocusKey,
  preorderLine,
  preorderRescheduleHref,
} from "../app/presentation/preorderList";
import type {
  OrderCardProjection,
  TwoZoneQueueProjection,
} from "../app/types/orders";

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "NB-261116-C73",
    customer_name: "Clara Teste",
    items_summary: "1x Pain de Campagne",
    total_display: "R$ 18,70",
    schedule_label: "Amanhã · A partir das 15h",
    schedule_state: "future",
    fulfillment_label: "Retirada",
    fulfillment_type: "pickup",
    payment_method_label: "Pix",
    payment_status_label: "Pago",
    payment_pending: false,
    attention: "",
    awaiting_work_orders: [],
    ...over,
  } as OrderCardProjection;
}

function queue(over: Partial<TwoZoneQueueProjection>): TwoZoneQueueProjection {
  return { intake: [], prep: [], preorders: [], ...over } as unknown as TwoZoneQueueProjection;
}

describe("a linha responde quando, como, pagamento e produção", () => {
  it("encomenda paga para amanhã: o dia e a janela, retirada e o pagamento", () => {
    expect(preorderLine(card())).toMatchObject({
      code: "C73",
      who: "Clara Teste",
      when: "Amanhã · A partir das 15h",
      how: "Retirada",
      payment: "Pix · Pago",
      awaitingPayment: false,
      production: "",
      needsYou: false,
      items: "1x Pain de Campagne",
      total: "R$ 18,70",
    });
  });

  it("a de hoje que espera a hora da Cozinha diz quando chega lá (WP-G02)", () => {
    const line = preorderLine(
      card({ schedule_label: "Hoje · 17h às 17h30", kitchen_release_label: "Vai para a Cozinha às 16h15" }),
    );
    expect(line.when).toBe("Hoje · 17h às 17h30");
    expect(line.kitchenWait).toEqual({ label: "Vai para a Cozinha às 16h15", icon: "i-lucide-chef-hat" });
    expect(preorderLine(card()).kitchenWait).toBeNull();
  });

  it("entrega diz Entrega", () => {
    expect(preorderLine(card({ fulfillment_label: "Entrega" })).how).toBe("Entrega");
  });

  it("dinheiro não tem estado de pagamento: só o meio", () => {
    const line = preorderLine(card({ payment_method_label: "Dinheiro", payment_status_label: "" }));
    expect(line.payment).toBe("Dinheiro");
  });

  it("a que espera um lote diz qual produção e em que pé está", () => {
    const line = preorderLine(
      card({
        awaiting_work_orders: [
          { ref: "WO-12", recipe_name: "Kuro Pan", status: "planned", status_label: "Planejada" },
        ] as never,
      }),
    );
    expect(line.production).toContain("Produção de Kuro Pan");
  });

  it("sem cliente, diz que não há, em vez de deixar o lugar vazio", () => {
    expect(preorderLine(card({ customer_name: "" })).who).toBe("Sem cliente");
  });
});

describe("quem espera o pagamento não \"precisa de você\"", () => {
  const waiting = card({
    attention: "blocked",
    payment_pending: true,
    payment_method_label: "Pix",
    payment_status_label: "Pendente",
  });

  it("a linha diz \"Aguardando pagamento\" com o meio ao lado", () => {
    const line = preorderLine(waiting);
    expect(line.payment).toBe(`${AWAITING_PAYMENT_LABEL} · Pix`);
    expect(line.awaitingPayment).toBe(true);
    expect(line.needsYou).toBe(false);
  });

  it("\"Precisa de você\" fica para quem espera um gesto de verdade", () => {
    expect(preorderLine(card({ attention: "confirm" })).needsYou).toBe(true);
  });
});

describe("\"Remarcar no PDV\" abre aquela encomenda", () => {
  it("aponta para /preorders/<ref> do PDV", () => {
    expect(preorderRescheduleHref("https://pdv.exemplo/", "NB-261116-C73")).toBe(
      "https://pdv.exemplo/preorders/NB-261116-C73",
    );
  });

  it("sem o endereço do PDV não há atalho", () => {
    expect(preorderRescheduleHref("", "NB-261116-C73")).toBe("");
  });
});

describe("o aceite diz para onde a encomenda foi", () => {
  it("saiu de Novos e entrou em Encomendas: aviso com o dia e a janela", () => {
    const fresh = card({ status: "new" });
    const accepted = card({ status: "accepted" });
    expect(
      acceptedIntoPreorders(queue({ intake: [fresh] }), queue({ preorders: [accepted] })),
    ).toEqual([
      {
        ref: "NB-261116-C73",
        code: "C73",
        message: "C73 foi para Encomendas: Amanhã · A partir das 15h.",
      },
    ]);
  });

  it("quem já morava na lista não gera aviso a cada leitura", () => {
    const accepted = card({ status: "accepted" });
    expect(
      acceptedIntoPreorders(queue({ preorders: [accepted] }), queue({ preorders: [accepted] })),
    ).toEqual([]);
  });

  it("pedido de hoje aceito segue nas colunas do dia: nenhum aviso", () => {
    const today = card({ ref: "NB-261118-A01", schedule_label: "" });
    expect(
      acceptedIntoPreorders(queue({ intake: [today] }), queue({ prep: [today] })),
    ).toEqual([]);
  });

  it("primeira leitura da tela não avisa de nada", () => {
    expect(acceptedIntoPreorders(null, queue({ preorders: [card()] }))).toEqual([]);
  });

  it("a linha é alvo do próximo foco", () => {
    expect(preorderFocusKey("NB-261116-C73")).toBe("preorder:NB-261116-C73");
  });
});

describe("a página leva até a lista", () => {
  const page = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
  const list = readFileSync(new URL("../app/components/OrderPreorderList.vue", import.meta.url), "utf8");

  it("o aviso do aceite fecha e tem o gesto que leva à linha", () => {
    const alert = page.slice(page.indexOf('v-if="acceptedPreorder &&'), page.indexOf("data-preorder-accepted"));
    expect(alert).toContain("notices.closeProps");
    expect(alert).toContain("Ver em Encomendas");
    expect(page).toContain("revealFocus(preorderFocusKey(");
  });

  it("\"tem mais abaixo\" vem depois da lista, dentro da área que rola", () => {
    expect(page.indexOf("<MoreBelow")).toBeGreaterThan(page.indexOf("<OrderPreorderList"));
    expect(page).toMatch(/<MoreBelow v-if="preordersCount" contained \/>/);
  });

  it("a linha quebra em vez de cortar: nenhuma largura fixa", () => {
    expect(list).not.toMatch(/\bw-16\b|\bw-40\b/);
    expect(list).toContain("flex-wrap");
  });
});
