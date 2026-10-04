import { describe, expect, it } from "vitest";

import {
  allDayCounts,
  cardScale,
  fulfillmentLabel,
  boardView,
  elapsedLabel,
  KDS_UNDO_WINDOW_MS,
  additionTicketPks,
  nextTicketPk,
  cardActionLabel,
  thumbActionLabel,
  ticketAction,
  ticketOverline,
  ticketStartLine,
  lucideIcon,
  slaPercent,
  sortByUrgency,
  splitRef,
  targetLabel,
  ticketTone,
  toneBar,
  toneNextSurface,
  toneTimer,
  toneTimerChip,
  ticketPill,
  focusSlice,
  focusGrid,
  isTallTicket,
  restSummary,
  boardFilterCounts,
  matchesBoardFilter,
  cancelledSummary,
  queueLine,
} from "../app/presentation/board";
import type { KDSBoardProjection, KDSTicketProjection } from "../app/types/kds";

const ticket = (
  over: Partial<KDSTicketProjection> = {},
): KDSTicketProjection => ({
  pk: 1,
  order_ref: "PDV-1",
  channel_icon: "store",
  customer_name: "Ana",
  fulfillment_icon: "bag",
  created_at_display: "08:00",
  elapsed_seconds: 30,
  target_seconds: 600,
  timer_class: "timer-ok",
  items: [
    {
      sku: "x",
      name: "Pão",
      qty: 2,
      notes: "",
      stock_warning: "",
    },
  ],
  status: "in_progress",
  previous_tab_ref: "",
  status_label: "",
  is_cancelled: false,
  cancelled_at_display: "",
  completed_at_display: "",
  kitchen_note: "",
  customer_note: "",
  finish_block_label: "",
  finish_block_reason: "",
  test_order_label: "",
  volumes: 0,
  volumes_order_ref: "",
  volumes_revision: "",
  started_by: "",
  started_at_display: "",
  is_preorder: false,
  due_time_display: "",
  seen: false,
  ...over,
});

describe("kds board presentation", () => {
  it("maps timer class to a functional tone", () => {
    expect(ticketTone("timer-late")).toBe("late");
    expect(ticketTone("timer-warning")).toBe("warning");
    expect(ticketTone("timer-ok")).toBe("ok");
  });

  it("shapes the board view + counts", () => {
    const board: KDSBoardProjection = {
      instance_ref: "cafes",
      instance_name: "Cafés",
      instance_type: "prep",
      tickets: [ticket(), ticket({ pk: 2 })],
      counts: { total: 2, pending: 1, in_progress: 1 },
      cancelled_tickets: [ticket({ pk: 3, is_cancelled: true })],
      recent_done: [],
      density: "roomy",
      sound_enabled: false,
    };
    const view = boardView(board);
    expect(view.instanceName).toBe("Cafés");
    expect(view.cards).toHaveLength(2);
    expect(view.cancelled).toHaveLength(1);
    expect(view.total).toBe(2);
    expect(view.blockedRefs.has("PDV-1")).toBe(true);
    // Densidade e som vêm da estação provisionada (v4 nota 1).
    expect(view.density).toBe("roomy");
    expect(view.soundEnabled).toBe(false);
  });

  it("mantém o card na grade durante a janela de desfazer, mas fora do trabalho", () => {
    const board: KDSBoardProjection = {
      instance_ref: "cafes",
      instance_name: "Cafés",
      instance_type: "prep",
      tickets: [ticket({ pk: 1, status: "pending" }), ticket({ pk: 2 })],
      counts: { total: 2, pending: 1, in_progress: 1 },
      cancelled_tickets: [],
      recent_done: [],
      density: "cozy",
      sound_enabled: true,
    };
    const view = boardView(board, new Set([2]));
    // O card continua desenhado — é ele que carrega o "Desfazer", no lugar onde o
    // dedo acabou de tocar. O que ele deixa de ser é trabalho.
    expect(view.cards.map((c) => c.pk)).toEqual([1, 2]);
    expect(view.finishingPks.has(2)).toBe(true);
    expect(view.total).toBe(1);
    expect(view.counts.in_progress).toBe(0);
    expect(view.counts.pending).toBe(1);
    // O "a fazer" conta só quem ainda é trabalho: metade do que contaria com os dois.
    const withoutWindow = boardView(board);
    const allDayTotal = (v: typeof view) => v.allDay.reduce((sum, e) => sum + e.qty, 0);
    expect(allDayTotal(view)).toBe(allDayTotal(withoutWindow) / 2);
    expect(view.nextPk).toBe(1); // nunca aponta para quem está saindo
  });

  it("o próximo é o primeiro da fila de trabalho", () => {
    const live = ticket({ pk: 6, status: "pending" });
    expect(nextTicketPk([live, ticket({ pk: 7 })])).toBe(6);
    expect(nextTicketPk([])).toBeNull();
  });

  it("v4 nota 6: o card do dia diz só Retirada/Entrega; a encomenda diz o cliente", () => {
    expect(ticketOverline(ticket({ fulfillment_icon: "storefront", customer_name: "+5543993333333" }))).toBe("Retirada");
    expect(ticketOverline(ticket({ fulfillment_icon: "local_shipping", customer_name: "Ana" }))).toBe("Entrega");
    expect(ticketOverline(ticket({ is_preorder: true, customer_name: "Café Parisiense" }))).toBe("Encomenda · Café Parisiense");
    expect(ticketOverline(ticket({ is_preorder: true, customer_name: "(43) 99333-3333" }))).toBe("Encomenda");
  });

  it("v4 nota 7: iniciado por e a hora combinada numa linha", () => {
    expect(ticketStartLine(ticket({ started_by: "Rafael", started_at_display: "21:56", due_time_display: "retira às 22:30" }))).toBe(
      "iniciado por Rafael às 21:56 · retira às 22:30",
    );
    expect(ticketStartLine(ticket({ due_time_display: "entrega às 11:00" }))).toBe("entrega às 11:00");
    expect(ticketStartLine(ticket())).toBe("");
  });

  it("o card do tablet e do desktop diz Pronto com o código, como o celular (dono, 04/10/2026)", () => {
    const armed = { armed: true, blocked: false };
    expect(cardActionLabel(ticketAction(ticket({ status: "in_progress" }), armed), "W07")).toBe("Pronto W07");
    expect(cardActionLabel(ticketAction(ticket({ status: "in_progress", finish_block_label: "Pix não confirmado" }), armed), "W07")).toBe(
      "Pronto W07",
    );
    expect(cardActionLabel(ticketAction(ticket({ status: "pending" }), armed), "W07")).toBe("Iniciar preparo");
    expect(cardActionLabel(ticketAction(ticket(), { ...armed, finishing: true }), "W07")).toBe("Desfazer");
  });

  it("o polegar do celular leva o código: Pronto W07 (v4 cozinha-celular b)", () => {
    const armed = { armed: true, blocked: false };
    expect(thumbActionLabel(ticketAction(ticket({ status: "in_progress" }), armed), "W07")).toBe("Pronto W07");
    expect(thumbActionLabel(ticketAction(ticket({ status: "pending" }), armed), "W07")).toBe("Iniciar W07");
    expect(thumbActionLabel(ticketAction(ticket(), { ...armed, finishing: true }), "W07")).toBe("Desfazer W07");
  });

  it("formats elapsed compactly — seconds only in the first minute, then whole minutes", () => {
    expect(elapsedLabel(45)).toBe("45s");
    expect(elapsedLabel(90)).toBe("1m"); // sem tique-taque depois do 1º minuto
    expect(elapsedLabel(120)).toBe("2m");
    expect(elapsedLabel(3600)).toBe("1h");
    expect(elapsedLabel(7200)).toBe("2h");
    expect(elapsedLabel(9000)).toBe("2h 30m");
  });

  it("maps Material-Symbol icon names onto lucide, with a safe fallback", () => {
    expect(lucideIcon("local_shipping")).toBe("bike");
    expect(lucideIcon("storefront")).toBe("store");
    expect(lucideIcon("fastfood")).toBe("utensils-crossed");
    expect(lucideIcon("store")).toBe("store"); // already lucide → passthrough
    expect(lucideIcon("")).toBe("circle"); // empty → fallback
  });

  it("labels the target SLA compactly", () => {
    expect(targetLabel(600)).toBe("10m");
    expect(targetLabel(720)).toBe("12m");
    expect(targetLabel(5400)).toBe("1h 30m");
    expect(targetLabel(3600)).toBe("1h");
  });

  it("fills the time-to-SLA bar (elapsed vs target, clamped 0–100)", () => {
    expect(slaPercent(0, 600)).toBe(0);
    expect(slaPercent(300, 600)).toBe(50);
    expect(slaPercent(600, 600)).toBe(100);
    expect(slaPercent(1200, 600)).toBe(100); // overdue pins full; tone escalates
    expect(slaPercent(60, 0)).toBe(0); // no target → no bar
  });

  it("maps tone to a solid bar fill and a tonal timer chip", () => {
    expect(toneBar("late")).toContain("red");
    expect(toneBar("warning")).toContain("amber");
    expect(toneBar("ok")).not.toMatch(/red|amber|green/); // no prazo = cinza calmo
    expect(toneTimer("late")).toContain("red");
    expect(toneTimer("ok")).toContain("muted-foreground");
  });

  it("pinta o próximo no tom do próprio semáforo (v4: borda de 2px, tinta e halo)", () => {
    expect(toneNextSurface("late")).toContain("border-destructive");
    expect(toneNextSurface("warning")).toContain("border-warning");
    expect(toneNextSurface("ok")).toContain("border-primary");
    expect(toneNextSurface("ok")).not.toMatch(/destructive|warning/);
  });

  it("o relógio do card: atrasado é o único sólido; perto da meta, âmbar; no prazo, neutro", () => {
    expect(toneTimerChip("late")).toContain("bg-destructive");
    expect(toneTimerChip("warning")).toContain("text-warning");
    expect(toneTimerChip("warning")).not.toContain("bg-");
    expect(toneTimerChip("ok")).toContain("border-border");
  });

  it("a pílula do card diz o estado num estilo só", () => {
    const late = ticket({ timer_class: "timer-late", status: "pending" });
    expect(ticketPill(late, { next: true })).toEqual({ label: "Próximo · atrasado", tone: "destructive" });
    expect(ticketPill(ticket({ status: "pending" }), {})).toEqual({ label: "Novo", tone: "info" });
    expect(ticketPill(ticket({ status: "in_progress" }), {})).toEqual({ label: "Em preparo", tone: "primary" });
    expect(ticketPill(ticket({ status: "in_progress" }), { blocked: true })?.label).toBe("Bloqueado");
  });

  it("destaque do próximo é borda + tint: ring fica reservado ao foco de teclado", () => {
    // Canon do kit (operator-base.css, "SELEÇÃO / ATIVO").
    for (const tone of ["late", "warning", "ok"] as const) {
      expect(toneNextSurface(tone)).not.toContain("ring");
      expect(toneNextSurface(tone)).toContain("border-");
    }
  });

  it("auto-sorts prep tickets by urgency (late first, then oldest)", () => {
    const ok = ticket({ pk: 1, timer_class: "timer-ok", elapsed_seconds: 10 });
    const lateNew = ticket({
      pk: 2,
      timer_class: "timer-late",
      elapsed_seconds: 100,
    });
    const lateOld = ticket({
      pk: 3,
      timer_class: "timer-late",
      elapsed_seconds: 500,
    });
    const warn = ticket({
      pk: 4,
      timer_class: "timer-warning",
      elapsed_seconds: 50,
    });
    const sorted = sortByUrgency([ok, lateNew, warn, lateOld]);
    expect(sorted.map((c) => (c as KDSTicketProjection).pk)).toEqual([
      3, 2, 4, 1,
    ]);
  });

  it("splits the ref into a recessive prefix + the hero code", () => {
    expect(splitRef("IFOOD-260606-2L8Y")).toEqual({
      prefix: "IFOOD-260606-",
      code: "2L8Y",
    });
    expect(splitRef("PDV-260606-NMEQ")).toEqual({
      prefix: "PDV-260606-",
      code: "NMEQ",
    });
    expect(splitRef("SEMTRACO")).toEqual({ prefix: "", code: "SEMTRACO" });
  });

  it("aggregates all-day counts across active tickets", () => {
    const t1 = ticket({
      pk: 1,
      items: [
        {
          sku: "a",
          name: "Baguete",
          qty: 2,
          notes: "",
          stock_warning: "",
        },
        {
          sku: "b",
          name: "Café",
          qty: 1,
          notes: "",
          stock_warning: "",
        },
      ],
    });
    const t2 = ticket({
      pk: 2,
      items: [
        {
          sku: "a",
          name: "Baguete",
          qty: 3,
          notes: "",
          stock_warning: "",
        },
      ],
    });
    const allDay = allDayCounts([t1, t2]);
    expect(allDay).toEqual([
      { name: "Baguete", qty: 5 },
      { name: "Café", qty: 1 },
    ]);
  });
});

it("soma quantidades decimais sem concatenar strings nem arredondar unidades", () => {
  const first = ticket();
  first.items[0]!.qty = "0.1";
  const second = ticket();
  second.items[0]!.qty = "0.2";
  expect(allDayCounts([first, second])).toEqual([{ name: "Pão", qty: 0.3 }]);
});

describe("o botão do card", () => {
  const armed = { armed: true, blocked: false };

  it("o rótulo é o ATO, e ele muda com o estado do pedido", () => {
    expect(ticketAction(ticket({ status: "pending" }), armed)).toMatchObject({
      kind: "start",
      label: "Iniciar preparo",
      enabled: true,
    });
    expect(ticketAction(ticket({ status: "in_progress" }), armed)).toMatchObject({
      kind: "finish",
      label: "Pronto",
      enabled: true,
    });
  });

  it("recém-iniciado ainda não finaliza: o rótulo não pisca, só o toque não passa", () => {
    const justStarted = ticketAction(ticket({ status: "in_progress" }), {
      armed: false,
      blocked: false,
    });
    expect(justStarted.kind).toBe("finish");
    expect(justStarted.label).toBe("Pronto");
    expect(justStarted.enabled).toBe(false);
  });

  it("item cancelado trava o finalizar e diz PARA ONDE ir, mas não trava o iniciar", () => {
    const blocked = { armed: true, blocked: true };
    const stuck = ticketAction(ticket({ status: "in_progress" }), blocked);
    expect(stuck.kind).toBe("blocked");
    expect(stuck.label).toContain("cartão vermelho");
    expect(ticketAction(ticket({ status: "pending" }), blocked).kind).toBe("start");
  });

  it("dentro da janela, o botão é o Desfazer — e ele ganha de qualquer outro estado", () => {
    expect(
      ticketAction(ticket({ status: "in_progress" }), { ...armed, finishing: true }),
    ).toMatchObject({ kind: "undo", label: "Desfazer", enabled: true });
    expect(
      ticketAction(ticket({ status: "in_progress" }), {
        armed: true,
        blocked: true,
        finishing: true,
      }).kind,
    ).toBe("undo");
  });

  it("pagamento não confirmado tranca o finalizar ANTES do toque, mas não o iniciar", () => {
    const unpaid = { finish_block_label: "Pix não confirmado" };
    const locked = ticketAction(ticket({ status: "in_progress", ...unpaid }), armed);
    expect(locked).toMatchObject({ kind: "locked", label: "Pronto", icon: "lucide:lock", enabled: true });
    expect(ticketAction(ticket({ status: "pending", ...unpaid }), armed).kind).toBe("start");
    // O cancelamento fala primeiro (é a cozinha que destrava), e o Desfazer ganha de tudo.
    expect(ticketAction(ticket({ status: "in_progress", ...unpaid }), { armed: true, blocked: true }).kind).toBe("blocked");
    expect(
      ticketAction(ticket({ status: "in_progress", ...unpaid }), { armed: true, blocked: false, finishing: true }).kind,
    ).toBe("undo");
  });

  it("a janela de desfazer é curta o bastante para não segurar a cozinha", () => {
    expect(KDS_UNDO_WINDOW_MS).toBeGreaterThanOrEqual(3000);
    expect(KDS_UNDO_WINDOW_MS).toBeLessThanOrEqual(8000);
  });
});

describe("ticket adicional do mesmo pedido", () => {
  it("marca como adicional o ticket mais novo do mesmo pedido, não o primeiro", () => {
    const first = ticket({ pk: 10, order_ref: "PDV-7" });
    const extra = ticket({ pk: 14, order_ref: "PDV-7" });
    const other = ticket({ pk: 12, order_ref: "PDV-8" });
    expect([...additionTicketPks([extra, other, first], [])]).toEqual([14]);
  });

  it("conta o primeiro ticket já finalizado nos concluídos recentes", () => {
    const done = ticket({ pk: 3, order_ref: "PDV-7", status: "done" });
    const extra = ticket({ pk: 9, order_ref: "PDV-7" });
    expect([...additionTicketPks([extra], [done])]).toEqual([9]);
  });
});

describe("moldura comum dos cards", () => {
  it("uma escala só, a Padrão na medida da v4 (botão de 56px), e nunca abaixo de h-11", () => {
    expect(cardScale("compact").action).toContain("h-11");
    expect(cardScale("cozy").action).toContain("h-14");
    expect(cardScale("roomy").action).toContain("h-16");
    expect(cardScale("cozy").code).toBe("text-3xl");
    expect(cardScale("compact").code).toBe("text-xl");
    expect(cardScale("roomy").code).toBe("text-4xl");
  });

  it("Entrega/Retirada sai do ícone do ticket, com a palavra da Saída", () => {
    expect(fulfillmentLabel("local_shipping")).toBe("Entrega");
    expect(fulfillmentLabel("storefront")).toBe("Retirada");
  });
});

describe("a fila do cozinheiro (v4: 4 a 6 em foco, o resto vira +N)", () => {
  const items = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ sku: `s${i}`, name: `Item ${i}`, qty: 1, notes: "", stock_warning: "" }));
  const short = (pk: number) => ticket({ pk, items: items(2) });
  const tall = (pk: number) => ticket({ pk, items: items(7) });

  it("3×2 com um ticket longo: cinco em foco, o longo em duas alturas, o resto no +N", () => {
    const cards = [short(1), tall(2), short(3), short(4), short(5), short(6), short(7)];
    const slice = focusSlice(cards, { columns: 3, rows: 2 });
    expect(slice.visible.map((c) => c.pk)).toEqual([1, 2, 3, 4, 5]);
    expect(slice.rest.map((c) => c.pk)).toEqual([6, 7]);
    expect(slice.placements.get(2)).toEqual({ pk: 2, column: 1, row: 0, span: 2 });
    expect(slice.placements.get(4)).toMatchObject({ column: 0, row: 1 });
    expect(slice.placements.get(5)).toMatchObject({ column: 2, row: 1 });
  });

  it("nunca pula um mais urgente para mostrar um menos urgente", () => {
    // O longo não cabe na última linha: ele e todos depois dele vão para o +N.
    const cards = [short(1), short(2), short(3), tall(4), short(5)];
    const slice = focusSlice(cards, { columns: 3, rows: 2 });
    expect(slice.visible.map((c) => c.pk)).toEqual([1, 2, 3]);
    expect(slice.rest.map((c) => c.pk)).toEqual([4, 5]);
  });

  it("em uma coluna ninguém ocupa duas alturas", () => {
    const slice = focusSlice([tall(1), short(2)], { columns: 1, rows: 3 });
    expect(slice.placements.get(1)?.span).toBe(1);
    expect(slice.visible).toHaveLength(2);
  });

  it("o ticket longo conta as observações como linha", () => {
    expect(isTallTicket(ticket({ items: items(5) }))).toBe(false);
    expect(isTallTicket(ticket({ items: items(5), kitchen_note: "Bem assado" }))).toBe(true);
  });

  it("colunas pela densidade, linhas pela altura (2 sem medida)", () => {
    expect(focusGrid({ width: 1072, height: 0 }, 320)).toEqual({ columns: 3, rows: 2 });
    expect(focusGrid({ width: 1072, height: 560 }, 320).rows).toBe(2);
    expect(focusGrid({ width: 700, height: 900 }, 320)).toEqual({ columns: 2, rows: 3 });
    expect(focusGrid({ width: 300, height: 600 }, 320).columns).toBe(1);
  });

  it("o excedente diz quantos e se há atraso no meio deles", () => {
    expect(restSummary([short(1), short(2)]).count).toBe("+2 na fila");
    expect(restSummary([short(1)]).detail).toContain("todos no prazo");
    expect(restSummary([ticket({ timer_class: "timer-late" })]).detail).toContain("1 atrasado");
  });

  it("recortes: Entrega e Atrasados contam sobre a fila inteira", () => {
    const cards = [
      ticket({ pk: 1, fulfillment_icon: "local_shipping" }),
      ticket({ pk: 2, timer_class: "timer-late" }),
      ticket({ pk: 3 }),
    ];
    expect(boardFilterCounts(cards)).toEqual({ all: 3, delivery: 1, late: 1 });
    expect(cards.filter((c) => matchesBoardFilter(c, "late")).map((c) => c.pk)).toEqual([2]);
  });

  it("cancelamento: item que saiu de pedido que continua x pedido inteiro", () => {
    const cancelled = ticket({ order_ref: "F22", cancelled_at_display: "22:01" });
    expect(cancelledSummary(cancelled, new Set(["F22"]))).toEqual({
      label: "Item cancelado 22:01",
      rest: "o resto continua",
    });
    expect(cancelledSummary(cancelled, new Set())).toEqual({ label: "Cancelado 22:01", rest: "" });
  });

  it("a linha compacta do celular: o primeiro item e quantos mais", () => {
    expect(queueLine(ticket({ items: items(1) }))).toBe("1× Item 0");
    expect(queueLine(ticket({ items: items(3) }))).toBe("1× Item 0 +2");
  });
});
