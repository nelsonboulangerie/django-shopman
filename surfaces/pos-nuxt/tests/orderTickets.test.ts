// A Via Pedido em lote: a contagem e o AVISO antes do gesto.
//
// O que esta suíte prende é a promessa que o dono fez à parede da padaria:
// ninguém pode descobrir que pediu 200 vias depois de a bobina começar a andar,
// e o botão diz quantas vão sair — nunca "Imprimir 0 vias".
import { describe, expect, it } from "vitest";

import {
  BATCH_WARN_AT,
  addDays,
  batchNotice,
  canPrintBatch,
  fulfillmentIcon,
  isoDate,
  printCtaLabel,
  ticketCountLabel,
} from "../app/presentation/orderTickets";

describe("datas sem UTC", () => {
  it("somar dias não passa por UTC", () => {
    // `new Date("2026-09-04")` lê UTC e, a oeste de Greenwich, já começa no dia
    // 3 — a semana sairia com seis dias e a quinta viraria quarta na etiqueta.
    expect(addDays("2026-09-04", 6)).toBe("2026-09-10");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("isoDate lê o fuso LOCAL", () => {
    expect(isoDate(new Date(2026, 8, 4))).toBe("2026-09-04");
  });
});

describe("quantas vias vão sair", () => {
  it("um lote comum não enche a tela de aviso", () => {
    expect(batchNotice(0, 200)).toBeNull();
    expect(batchNotice(4, 200)).toBeNull();
  });

  it("a partir do limiar a tela avisa quanto papel vai andar", () => {
    const notice = batchNotice(BATCH_WARN_AT, 200);
    expect(notice?.tone).toBe("warning");
    expect(notice?.message).toContain(`${BATCH_WARN_AT} vias`);
  });

  it("passar do teto do servidor é RECUSA, não conselho — e diz o que fazer", () => {
    const notice = batchNotice(201, 200);
    expect(notice?.tone).toBe("danger");
    expect(notice?.message).toContain("200");
    expect(notice?.message).toContain("Estreite os filtros");
    expect(canPrintBatch(201, 200)).toBe(false);
  });

  it("o botão só liga com algo para imprimir e dentro do teto", () => {
    expect(canPrintBatch(0, 200)).toBe(false);
    expect(canPrintBatch(1, 200)).toBe(true);
    expect(canPrintBatch(200, 200)).toBe(true);
  });

  it("o número entra no CTA — e zero não é número de botão", () => {
    expect(printCtaLabel(0)).toBe("Nenhuma via para imprimir");
    expect(printCtaLabel(1)).toBe("Imprimir 1 via");
    expect(printCtaLabel(34)).toBe("Imprimir 34 vias");
  });

  it("a contagem fala português no singular e no zero", () => {
    expect(ticketCountLabel(0)).toBe("nenhuma via");
    expect(ticketCountLabel(1)).toBe("1 via");
    expect(ticketCountLabel(2)).toBe("2 vias");
  });

  it("entrega e retirada não usam o mesmo ícone — e nenhum é emoji", () => {
    expect(fulfillmentIcon("delivery")).toBe("lucide:bike");
    expect(fulfillmentIcon("pickup")).toBe("lucide:shopping-bag");
  });
});
