// A tela das filipetas: o intervalo, a contagem e o AVISO antes do gesto.
//
// O que esta suíte prende é a promessa que o dono fez à parede da padaria:
// "todos os pedidos da semana" tem de sair como uma semana, e ninguém pode
// descobrir que pediu 200 filipetas depois de a bobina começar a andar.
import { describe, expect, it } from "vitest";

import {
  BATCH_WARN_AT,
  activePreset,
  addDays,
  batchNotice,
  canPrintBatch,
  fulfillmentIcon,
  groupByDate,
  isoDate,
  printCtaLabel,
  rangeLabel,
  resolveRange,
  ticketCountLabel,
  type TicketRow,
} from "../app/presentation/orderTickets";

const HOJE = "2026-09-04"; // sexta

function row(partial: Partial<TicketRow> = {}): TicketRow {
  return {
    ref: "NB-1",
    customer_name: "Ana",
    commitment_date: HOJE,
    window_label: "A partir das 12h",
    fulfillment_type: "pickup",
    fulfillment_label: "Retirada",
    status: "accepted",
    already_printed: false,
    ...partial,
  };
}

// ── O intervalo ───────────────────────────────────────────────────────────

describe("o intervalo do lote", () => {
  it("a semana começa HOJE e tem sete dias", () => {
    // ⚠️ Uma semana que começa na segunda imprimiria filipeta de pedido já
    // entregue. O painel olha para frente.
    expect(resolveRange("week", HOJE)).toEqual({ date_from: "2026-09-04", date_to: "2026-09-10" });
  });

  it("hoje e amanhã são um dia só, não uma janela", () => {
    expect(resolveRange("today", HOJE)).toEqual({ date_from: HOJE, date_to: HOJE });
    expect(resolveRange("tomorrow", HOJE)).toEqual({ date_from: "2026-09-05", date_to: "2026-09-05" });
  });

  it("somar dias não passa por UTC", () => {
    // `new Date("2026-09-04")` lê UTC e, a oeste de Greenwich, já começa no dia
    // 3 — a semana sairia com seis dias e a quinta viraria quarta na etiqueta.
    expect(addDays("2026-09-04", 6)).toBe("2026-09-10");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");
  });

  it("isoDate lê o fuso LOCAL", () => {
    expect(isoDate(new Date(2026, 8, 4))).toBe("2026-09-04");
  });

  it("o chip acende só quando o intervalo é exatamente o dele", () => {
    expect(activePreset(resolveRange("week", HOJE), HOJE)).toBe("week");
    expect(activePreset({ date_from: "2026-09-04", date_to: "2026-09-08" }, HOJE)).toBe("");
  });

  it("o rótulo do intervalo colapsa quando as pontas se encontram", () => {
    expect(rangeLabel({ date_from: HOJE, date_to: HOJE }, HOJE)).toBe("Hoje");
    expect(rangeLabel(resolveRange("week", HOJE), HOJE)).toContain("Hoje até ");
  });
});

// ── ⚠️ O aviso antes do gesto ─────────────────────────────────────────────

describe("quantas filipetas vão sair", () => {
  it("intervalo vazio não é erro, é 'não há o que imprimir'", () => {
    expect(batchNotice(0, 200)).toEqual({
      tone: "neutral",
      message: "Nenhum pedido com compromisso neste intervalo.",
    });
  });

  it("um lote comum não enche a tela de aviso", () => {
    expect(batchNotice(4, 200)).toBeNull();
  });

  it("a partir do limiar a tela avisa quanto papel vai andar", () => {
    const notice = batchNotice(BATCH_WARN_AT, 200);
    expect(notice?.tone).toBe("warning");
    expect(notice?.message).toContain(`${BATCH_WARN_AT} filipetas`);
  });

  it("passar do teto do servidor é RECUSA, não conselho", () => {
    const notice = batchNotice(201, 200);
    expect(notice?.tone).toBe("danger");
    expect(notice?.message).toContain("200");
    expect(canPrintBatch(201, 200)).toBe(false);
  });

  it("o botão só liga com algo para imprimir e dentro do teto", () => {
    expect(canPrintBatch(0, 200)).toBe(false);
    expect(canPrintBatch(1, 200)).toBe(true);
    expect(canPrintBatch(200, 200)).toBe(true);
  });

  it("o número entra no CTA porque é o que ninguém quer errar", () => {
    expect(printCtaLabel(1)).toBe("Imprimir 1 filipeta");
    expect(printCtaLabel(34)).toBe("Imprimir 34 filipetas");
  });

  it("a contagem fala português no singular e no zero", () => {
    expect(ticketCountLabel(0)).toBe("nenhuma filipeta");
    expect(ticketCountLabel(1)).toBe("1 filipeta");
    expect(ticketCountLabel(2)).toBe("2 filipetas");
  });
});

// ── A conferência ─────────────────────────────────────────────────────────

describe("a conferência agrupada por dia", () => {
  it("preserva a ordem da bobina dentro do dia", () => {
    const rows = [
      row({ ref: "A", commitment_date: HOJE }),
      row({ ref: "B", commitment_date: HOJE }),
      row({ ref: "C", commitment_date: "2026-09-05" }),
    ];

    const groups = groupByDate(rows, HOJE);

    expect(groups.map((g) => g.date)).toEqual([HOJE, "2026-09-05"]);
    expect(groups[0]!.rows.map((r) => r.ref)).toEqual(["A", "B"]);
    expect(groups[0]!.date_label).toBe("Hoje");
    expect(groups[1]!.date_label).toBe("Amanhã");
  });

  it("período sem pedido não inventa grupo", () => {
    expect(groupByDate([], HOJE)).toEqual([]);
  });

  it("entrega e retirada não usam o mesmo ícone — e nenhum é emoji", () => {
    expect(fulfillmentIcon("delivery")).toBe("lucide:bike");
    expect(fulfillmentIcon("pickup")).toBe("lucide:shopping-bag");
    expect(fulfillmentIcon("delivery")).toMatch(/^lucide:/);
  });
});
