// O cartão no desenho da v4 (UX-KIT-V2): selo, relógio, verbo com o nome, barra por
// estação, o "Próximo" da Saída, a faixa do excedente e a frase da coluna recolhida.
import { describe, expect, it } from "vitest";

import {
  agoLabel,
  cardClock,
  cardSeal,
  customerFirstName,
  exitGesture,
  nextOutRef,
  primaryVerb,
  kitchenWaiting,
  productionLines,
  stripSummary,
  swipeHint,
  waitingStripText,
} from "../app/presentation/board";
import type { OrderCardProjection } from "../app/types/orders";
import type { KitchenStationProjection } from "../app/generated/ordersContract";

const NOW = Date.parse("2026-10-04T15:00:00Z");
const action = (ref: string, enabled = true, priority = "primary") =>
  ({ ref, label: ref, enabled, priority, reason: "" }) as never;

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261004-U13",
    status: "ready",
    status_label: "Pronto",
    can_confirm: false,
    advance_block_reason: "",
    actions: [action("advance")],
    customer_name: "Ana Ferreira",
    fulfillment_type: "pickup",
    next_status: "completed",
    confirmation_deadline_iso: "",
    confirmation_action: "",
    elapsed_seconds: 540,
    timer_class: "timer-muted",
    kitchen: null,
    ...over,
  } as OrderCardProjection;
}

const station = (
  name: string,
  state: string,
  over: Partial<KitchenStationProjection> = {},
): KitchenStationProjection => ({
  station_ref: name.toLowerCase(),
  station_name: name,
  prints: false,
  state,
  state_label: state === "done" ? "pronto" : "em preparo",
  paper_label: "",
  paper_failed: false,
  cancelled_items: 0,
  can_mark_ready: false,
  recall_ticket_pk: null,
  ...over,
});

describe("cardSeal", () => {
  it("bloqueio escrito vence; depois Novo e Próximo; senão o estado", () => {
    expect(
      cardSeal(
        card({
          advance_block_reason: "Pix não confirmado.",
          actions: [action("advance", false)],
        }),
      ),
    ).toEqual({ label: "Bloqueado", tone: "error" });
    expect(
      cardSeal(
        card({ status: "new", status_label: "Novo pedido", can_confirm: true }),
      ),
    ).toEqual({ label: "Novo", tone: "primary" });
    expect(cardSeal(card(), { next: true })).toEqual({
      label: "Próximo",
      tone: "primary",
    });
    expect(
      cardSeal(card({ status: "preparing", status_label: "Em preparo" })),
    ).toEqual({ label: "Em preparo", tone: "info" });
    expect(cardSeal(card())).toEqual({ label: "Pronto", tone: "success" });
  });

  it("frase sem gesto travado não vira bloqueio (o Marcar pronto que mora no menu)", () => {
    expect(
      cardSeal(
        card({
          advance_block_reason: "x",
          actions: [action("advance", false, "menu")],
        }),
      ).tone,
    ).toBe("success");
  });
});

describe("cardClock e agoLabel", () => {
  it("decorrido em palavras", () => {
    expect(agoLabel(20)).toBe("agora");
    expect(agoLabel(540)).toBe("há 9 min");
    expect(agoLabel(3900)).toBe("há 1h 5 min");
  });
  it("o prazo, quando há, é o relógio", () => {
    const deadline = new Date(NOW + 70_000).toISOString();
    expect(
      cardClock(
        card({
          confirmation_deadline_iso: deadline,
          confirmation_action: "confirm",
        }),
        NOW,
      ),
    ).toMatchObject({ text: "aceita sozinho em 1:10", countdown: true });
    expect(
      cardClock(
        card({
          confirmation_deadline_iso: deadline,
          confirmation_action: "cancel",
        }),
        NOW,
      ).text,
    ).toBe("cancela sozinho em 1:10");
    expect(cardClock(card(), NOW)).toMatchObject({
      text: "há 9 min",
      countdown: false,
    });
  });
});

describe("primaryVerb", () => {
  const advance = {
    ref: "advance" as const,
    label: "Marcar como retirado",
    disabled: false,
  };
  it("retirada pronta: entregar à pessoa, pelo primeiro nome", () => {
    expect(primaryVerb(card(), advance)).toBe("Entregar a Ana");
  });
  it("sem nome (ou telefone no lugar do nome): o código", () => {
    expect(
      primaryVerb(card({ customer_name: "(43) 99444-4444" }), advance),
    ).toBe("Entregar U13");
    expect(customerFirstName("")).toBe("");
  });
  it("saída para entrega: despachar o código", () => {
    expect(
      primaryVerb(
        card({ fulfillment_type: "delivery", next_status: "dispatched" }),
        { ...advance, label: "Marcar saída para entrega" },
      ),
    ).toBe("Despachar U13");
  });
  it("os outros passos e o gesto travado seguem com o rótulo do servidor", () => {
    expect(
      primaryVerb(card({ status: "accepted" }), {
        ...advance,
        label: "Iniciar preparo",
      }),
    ).toBe("Iniciar preparo");
    expect(primaryVerb(card(), { ...advance, disabled: true })).toBe(
      "Marcar como retirado",
    );
    expect(
      primaryVerb(card(), {
        ref: "confirm",
        label: "Aceitar",
        disabled: false,
      }),
    ).toBe("Aceitar");
  });
});

describe("exitGesture (F7: deslizar para entregar e o polegar)", () => {
  it("retirada pronta: entregar o código à pessoa", () => {
    expect(exitGesture(card())).toEqual({
      action: "advance",
      label: "Entregar U13 a Ana",
    });
    expect(exitGesture(card({ customer_name: "(43) 99444-4444" }))?.label).toBe(
      "Entregar U13",
    );
  });
  it("entrega pronta: despachar o código", () => {
    expect(
      exitGesture(
        card({ fulfillment_type: "delivery", next_status: "dispatched" }),
      )?.label,
    ).toBe("Despachar U13");
  });
  it("sem a saída à mão, nenhum gesto: não pronto, travado, ou já saiu", () => {
    expect(exitGesture(card({ status: "preparing" }))).toBeNull();
    expect(
      exitGesture(card({ actions: [action("advance", false)] })),
    ).toBeNull();
    expect(
      exitGesture(card({ actions: [action("advance", true, "menu")] })),
    ).toBeNull();
    expect(
      exitGesture(
        card({ actions: [action("advance"), action("undo-handoff")] }),
      ),
    ).toBeNull();
  });
});

describe("swipeHint", () => {
  it("diz o verbo de cada lado, e só o que vale ali", () => {
    expect(swipeHint("expedition", [card()], true)).toBe(
      "Deslize à direita para entregar, à esquerda para Atender · puxe para atualizar",
    );
    expect(
      swipeHint(
        "expedition",
        [
          card(),
          card({ fulfillment_type: "delivery", next_status: "dispatched" }),
        ],
        false,
      ),
    ).toBe(
      "Deslize à direita para entregar ou despachar · puxe para atualizar",
    );
    expect(swipeHint("intake", [card({ status: "new" })], true)).toBe(
      "Deslize para Atender ou Recusar · puxe para atualizar",
    );
    expect(swipeHint("prep", [card({ status: "preparing" })], false)).toBe(
      "Puxe para atualizar",
    );
  });
});

describe("kitchenWaiting", () => {
  it("diz só quem ainda falta, sem fração", () => {
    expect(
      kitchenWaiting({
        order_pk: 1,
        missing_label: "Faltam Café e Lanches",
        stations: [
          station("Forno", "done"),
          station("Lanches", "pending"),
          station("Café", "in_progress"),
        ],
      }),
    ).toBe("Lanches e Café");
  });
  it("todas prontas ou sem Cozinha: nada", () => {
    expect(
      kitchenWaiting({
        order_pk: 1,
        missing_label: "",
        stations: [station("Forno", "done"), station("Café", "done")],
      }),
    ).toBe("");
    expect(kitchenWaiting(null)).toBe("");
  });
});

describe("productionLines", () => {
  const wo = (status: string, recipe_name = "Croissant") => ({
    ref: `WO-${status}`,
    status,
    status_label: status,
    output_sku: "CRO",
    recipe_name,
    planned_qty: "12",
    finished_qty: "",
    progress_pct: 0,
  });
  it("uma frase por ordem, com o nome da receita e o estado em palavras", () => {
    expect(
      productionLines({
        awaiting_work_orders: [wo("planned"), wo("started", "Pão de queijo")],
      }).map((l) => l.text),
    ).toEqual([
      "Produção de Croissant: não começou",
      "Produção de Pão de queijo: em andamento",
    ]);
  });
});

describe("a Saída larga", () => {
  it("o Próximo é o primeiro pronto com a saída à mão", () => {
    const cards = [
      card({ ref: "A-1", status: "dispatched" }),
      card({ ref: "A-2", actions: [action("advance", false)] }),
      card({ ref: "A-3" }),
      card({ ref: "A-4" }),
    ];
    expect(nextOutRef(cards)).toBe("A-3");
  });
  it("o excedente vira número com os códigos", () => {
    expect(
      waitingStripText([card({ ref: "W-K44" }), card({ ref: "W-T18" })]),
    ).toBe("prontos esperando (K44, T18)");
    expect(waitingStripText([card({ ref: "W-K44" })])).toBe(
      "pronto esperando (K44)",
    );
    expect(waitingStripText([])).toBe("");
    expect(
      waitingStripText([
        card({ ref: "W-X59" }),
        card({ ref: "DLV-NARUA", status: "dispatched" }),
      ]),
    ).toBe("esperando (X59, NARUA)");
  });
});

describe("stripSummary (coluna recolhida)", () => {
  it("Entrada: o prazo mais curto", () => {
    const soon = card({
      confirmation_deadline_iso: new Date(NOW + 70_000).toISOString(),
      confirmation_action: "confirm",
    });
    const later = card({
      confirmation_deadline_iso: new Date(NOW + 200_000).toISOString(),
      confirmation_action: "confirm",
    });
    expect(stripSummary("intake", [later, soon], NOW)).toEqual({
      text: "aceita sozinho em 1:10",
      tone: "warning",
    });
  });
  it("atraso fala primeiro, em qualquer coluna", () => {
    expect(
      stripSummary("prep", [card({ timer_class: "timer-urgent" })], NOW),
    ).toEqual({ text: "1 atrasado", tone: "late" });
  });
  it("nada a dizer: vazio", () => {
    expect(stripSummary("expedition", [card()], NOW)).toEqual({
      text: "",
      tone: "",
    });
  });
});
