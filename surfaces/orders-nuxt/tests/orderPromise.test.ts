// WP-G08 ("Promessa em risco"): o que a tela faz com a leitura do servidor
// (`shopman/backstage/projections/order_promise.py`). Os exemplos de `promise` são os
// que `shopman/backstage/tests/test_order_promise.py` prende do lado de lá. Nenhuma
// régua de reserva, de lote ou de hora mora na tela: aqui só se prende o desenho.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { cardSeal, productionLines } from "../app/presentation/board";
import { cardFooter, reasonLines } from "../app/presentation/cardBlocks";
import type { Affordance } from "../app/presentation/board";
import type {
  Action,
  OrderPromiseItemProjection,
  OrderPromiseProjection,
} from "../app/generated/ordersContract";
import {
  exitButtons,
  promiseRisk,
  promiseRiskSummary,
  promiseWaitLines,
  waitsForBatch,
  promiseSuggestionGroups,
} from "../app/presentation/orderPromise";
import {
  manyOrdersStep,
  orderFocusKeys,
  promiseRiskAlert,
} from "../app/presentation/promiseAlert";
import { preorderLine } from "../app/presentation/preorderList";
import {
  queueBlock,
  queueBlockedReasons,
  queueGesture,
  queueItems,
} from "../app/presentation/queue";
import { pendingButton, pendingFocusKey, pendingLines } from "../app/presentation/orderPending";
import type { OrderCardProjection } from "../app/types/orders";

const PERMISSION = "Identifique uma pessoa com permissão para gerenciar pedidos.";
const NOW = Date.parse("2026-11-18T12:00:00Z");

const link = (ref: string, label: string, href: string, over: Partial<Action> = {}): Action => ({
  ref, kind: "link", label, priority: "secondary", enabled: true, reason: "", href,
  method: "", payload_schema: {}, idempotency: "none", confirmation: {}, ...over,
});
/** As três saídas do CARTÃO, como `_promise_card_actions` as manda: a recomendada
 *  primeiro e `primary`, as outras `secondary`, cancelar `danger`. */
const cardExits = (ref: string): Action[] => [
  link("contact-customer", "Avisar o cliente", `/${ref}#promise`, { priority: "primary" }),
  link("reschedule-at-pos", "Remarcar no PDV", `https://pdv.example.test/preorders/${ref}`),
  link("cancel", "Cancelar pedido", `/${ref}#cancel`, { priority: "danger" }),
];
const NOTHING_STEP = "Nenhum produto parecido livre para amanhã.";
const PLAN_STEP = "Peça à Produção para planejar.";
const openProduction = (over: Partial<Action> = {}) =>
  link("open-production", "Abrir a Produção", "https://producao.example.test/plan?date=2026-11-18", {
    priority: "primary", ...over,
  });
/** O item que a Produção ainda resolve: sem lote planejado para o dia. */
const noBatchItem = () =>
  item({
    cause: "no_batch", detail: "Não há lote planejado para hoje.", batch_date: "2026-11-18", batch_status: "",
    work_order_refs: [], next_step: PLAN_STEP,
  });
/** A promessa que pede a Produção. `operates`: a conta abre a Produção e recebe a ação. */
const needsProduction = (ref = "HOJE-PLANEJAR", operates = true): OrderPromiseProjection => ({
  state: "at_risk", label: "Promessa em risco", items: [noBatchItem()], blocks_start: false, since_iso: "",
  next_step: PLAN_STEP, recommended_action: "open-production",
  actions: operates
    ? [openProduction(), ...cardExits(ref).map((action) => (action.ref === "cancel" ? action : { ...action, priority: "secondary" }))]
    : cardExits(ref).map((action) => (action.ref === "cancel" ? action : { ...action, priority: "secondary" })),
});
const item = (over: Partial<OrderPromiseItemProjection> = {}): OrderPromiseItemProjection => ({
  sku: "BAGUETE", name: "Baguete de tradição", reservation: "lost", cause: "batch_cancelled",
  at_risk: true, qty: "4", missing_qty: "4", label: "Faltam 4x Baguete de tradição",
  detail: "O lote de amanhã foi cancelado.", batch_date: "2026-11-19", batch_status: "void",
  batch_ready_at_iso: "", work_order_refs: ["WO-1"], next_step: NOTHING_STEP,
  alternatives: [], ...over,
});
const waitingItem = (over: Partial<OrderPromiseItemProjection> = {}) =>
  item({
    reservation: "whole", cause: "batch_waiting", at_risk: false, missing_qty: "0",
    label: "4x Baguete de tradição", detail: "O lote de hoje não começou. Fica pronto às 12h.",
    batch_status: "planned", next_step: "", ...over,
  });
const atRisk = (ref = "ENC-CANCELADA", over: Partial<OrderPromiseProjection> = {}): OrderPromiseProjection => ({
  state: "at_risk", label: "Promessa em risco", items: [item()], blocks_start: false,
  since_iso: "", actions: cardExits(ref), next_step: NOTHING_STEP,
  recommended_action: "contact-customer", ...over,
});
const waiting = (over: Partial<OrderPromiseProjection> = {}): OrderPromiseProjection => ({
  state: "waiting_batch", label: "Esperando o lote", items: [waitingItem()], blocks_start: true,
  since_iso: "", actions: [], next_step: "", recommended_action: "", ...over,
});
const BATCH_REASON =
  "O preparo abre quando o lote ficar pronto. Baguete de tradição: o lote de hoje não começou. Fica pronto às 12h.";

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "ENC-CANCELADA", status: "accepted", status_label: "Confirmado", customer_name: "Clara",
    items_summary: "4x Baguete de tradição", total_display: "R$ 60,00", schedule_label: "Amanhã · A partir das 15h",
    fulfillment_label: "Retirada", fulfillment_type: "pickup", payment_method_label: "Pix",
    payment_status_label: "Pago", payment_pending: false, payment_lapsed: false, attention: "",
    attention_since_iso: "", goal_minutes: 0, goal_label: "", elapsed_seconds: 0,
    created_at_iso: new Date(NOW - 60_000).toISOString(), clock_since_iso: "", dispatched_at_iso: "",
    awaiting_work_orders: [], actions: [], advance_block_label: "", advance_block_reason: "",
    can_confirm: false, can_advance: false, can_settle_delivery_cash: false, equipment_back_pending: false,
    confirmation_deadline_iso: "", confirmation_action: "", promise: null, ...over,
  } as OrderCardProjection;
}
const lockedAdvance = (label: string, reason: string): Action => ({
  ref: "advance", kind: "mutation", label, priority: "primary", enabled: false, reason,
  href: "", method: "POST", payload_schema: {}, idempotency: "required", confirmation: {},
});
const wo = (status: string, recipe_name = "Croissant") => ({
  ref: `WO-${status}`, status, status_label: status, output_sku: "CRO", recipe_name,
  planned_qty: "12", finished_qty: "", progress_pct: 0,
});

describe("promiseRisk: o estado, os itens e as saídas, com as palavras do servidor", () => {
  it("sem leitura, ou só esperando o lote, não há risco a desenhar", () => {
    expect(promiseRisk({})).toBeNull();
    expect(promiseRisk({ promise: null })).toBeNull();
    expect(promiseRisk({ promise: waiting() })).toBeNull();
  });

  it("diz o nome do estado, o item que falta e o porquê, sem reescrever", () => {
    const risk = promiseRisk({ promise: atRisk() })!;
    expect(risk.label).toBe("Promessa em risco");
    expect(risk.items).toEqual([
      {
        key: "BAGUETE", name: "Baguete de tradição", label: "Faltam 4x Baguete de tradição",
        detail: "O lote de amanhã foi cancelado.", suggestions: [],
      },
    ]);
    expect(promiseRiskSummary(risk)).toBe("Faltam 4x Baguete de tradição");
  });

  it("só o item em risco entra: o que só espera o lote tem a linha dele", () => {
    const risk = promiseRisk({
      promise: atRisk("X", { items: [item(), waitingItem({ sku: "BRIOCHE", name: "Brioche" })] }),
    })!;
    expect(risk.items.map((entry) => entry.key)).toEqual(["BAGUETE"]);
  });

  it("as três saídas vêm na ordem do servidor, com os nomes fixos e o destino de cada uma", () => {
    const { exits, blockedReasons } = promiseRisk({ promise: atRisk("ENC-1") })!;
    expect(exits.map((exit) => exit.label)).toEqual(["Avisar o cliente", "Remarcar no PDV", "Cancelar pedido"]);
    expect(exits.map((exit) => exit.href)).toEqual([
      "/ENC-1#promise", "https://pdv.example.test/preorders/ENC-1", "/ENC-1#cancel",
    ]);
    // Só o PDV abre fora do Gestor; só o cancelar é vermelho.
    expect(exits.map((exit) => exit.external)).toEqual([false, true, false]);
    expect(exits.map((exit) => exit.danger)).toEqual([false, false, true]);
    expect(exits.every((exit) => !exit.disabled)).toBe(true);
    expect(blockedReasons).toEqual([]);
  });

  it("quem não gerencia pedidos vê o risco, com as saídas travadas e o motivo escrito uma vez", () => {
    const actions = cardExits("ENC-1").map((action) => ({ ...action, enabled: false, reason: PERMISSION, href: "" }));
    const risk = promiseRisk({ promise: atRisk("ENC-1", { actions }) })!;
    expect(risk.exits.every((exit) => exit.disabled && exit.href === "")).toBe(true);
    expect(risk.blockedReasons).toEqual([PERMISSION]);
  });

  it("uma saída travada sozinha leva o nome dela na frente do motivo", () => {
    const actions = cardExits("ENC-1");
    actions[1] = { ...actions[1]!, enabled: false, href: "", reason: "O endereço do PDV não está configurado." };
    const risk = promiseRisk({ promise: atRisk("ENC-1", { actions }) })!;
    expect(risk.exits.map((exit) => exit.disabled)).toEqual([false, true, false]);
    expect(risk.blockedReasons).toEqual(["Remarcar no PDV: O endereço do PDV não está configurado."]);
  });
});

describe("exitButtons: o peso de cada saída", () => {
  const exits = promiseRisk({ promise: atRisk() })!.exits;
  const look = (list: typeof exits, tone: "alert" | "row") =>
    exitButtons(list, tone).map((button) => [button.ref, button.color, button.variant]);

  it("no aviso do cartão, todas na cor do aviso: a recomendada cheia, as outras contornadas", () => {
    expect(look(exits, "alert")).toEqual([
      ["contact-customer", "error", "solid"], ["reschedule-at-pos", "error", "outline"], ["cancel", "error", "outline"],
    ]);
  });

  it("numa linha (Fila, Tabela), a recomendada é o único botão cheio; cancelar segue vermelho", () => {
    expect(look(exits, "row")).toEqual([
      ["contact-customer", "primary", "solid"], ["reschedule-at-pos", "neutral", "outline"], ["cancel", "error", "outline"],
    ]);
  });

  it("o cheio segue o que o servidor recomenda, e não a posição: \"Abrir a Produção\" quando ela resolve", () => {
    const production = promiseRisk({ promise: needsProduction() })!.exits;
    expect(look(production, "row")).toEqual([
      ["open-production", "primary", "solid"], ["contact-customer", "neutral", "outline"],
      ["reschedule-at-pos", "neutral", "outline"], ["cancel", "error", "outline"],
    ]);
    // A recomendada fora do primeiro lugar continua sendo a cheia.
    expect(look([...production].reverse(), "alert").filter((button) => button[2] === "solid")).toEqual([
      ["open-production", "error", "solid"],
    ]);
  });

  it("sem saída recomendada (quem não abre a Produção), nenhum botão é cheio", () => {
    const withoutProduction = promiseRisk({ promise: needsProduction("HOJE-PLANEJAR", false) })!.exits;
    expect(look(withoutProduction, "row")).toEqual([
      ["contact-customer", "neutral", "outline"], ["reschedule-at-pos", "neutral", "outline"], ["cancel", "error", "outline"],
    ]);
    expect(look(withoutProduction, "alert").every((button) => button[2] === "outline")).toBe(true);
  });

  it("saída travada nunca é o botão cheio", () => {
    const locked = exits.map((exit) => ({ ...exit, disabled: true, href: "" }));
    expect(exitButtons(locked, "row")[0]).toMatchObject({ color: "neutral", variant: "outline" });
    expect(exitButtons(locked, "alert")[0]).toMatchObject({ color: "error", variant: "outline" });
  });
});

describe("o próximo passo: o aviso diz o que fazer", () => {
  it("a frase é a do servidor, sem reescrever; vazia quando ele não manda", () => {
    expect(promiseRisk({ promise: atRisk() })!.nextStep).toBe(NOTHING_STEP);
    expect(promiseRisk({ promise: atRisk("X", { next_step: "" }) })!.nextStep).toBe("");
  });

  it("as sugestões vêm por item, uma por linha: o nome e o quanto há, com as palavras do servidor", () => {
    const offered = item({
      next_step: "",
      alternatives: [
        { sku: "FENDU", name: "Fendu", available_display: "6 livres para amanhã" },
        { sku: "CAMPAGNE", name: "Pain de Campagne", available_display: "8 livres para amanhã" },
      ],
    });
    const risk = promiseRisk({ promise: atRisk("X", { items: [offered], next_step: "" }) })!;

    expect(risk.items[0]!.suggestions).toEqual([
      "Fendu · 6 livres para amanhã", "Pain de Campagne · 8 livres para amanhã",
    ]);
    // Um item com sugestão: o título é só "Sugestões:".
    expect(promiseSuggestionGroups(risk)).toEqual([
      { key: "BAGUETE", heading: "Sugestões:", options: risk.items[0]!.suggestions },
    ]);
    // Na lista de Encomendas, numa linha só.
    expect(preorderLine(card({ attention: "promise", promise: atRisk("X", { items: [offered], next_step: "" }) })).risk).toEqual({
      label: "Promessa em risco", items: "Faltam 4x Baguete de tradição",
      suggestions: "Sugestões: Fendu · 6 livres para amanhã; Pain de Campagne · 8 livres para amanhã", nextStep: "",
    });
  });

  it("dois itens com sugestão: cada lista diz de quem é; item sem sugestão não ganha lista", () => {
    const fendu = [{ sku: "FENDU", name: "Fendu", available_display: "6 livres para amanhã" }];
    const risk = promiseRisk({
      promise: atRisk("X", {
        items: [
          item({ alternatives: fendu }),
          item({ sku: "BRIOCHE", name: "Brioche", label: "Faltam 2x Brioche", alternatives: fendu }),
          item({ sku: "PITA", name: "Pita", label: "Faltam 3x Pita", alternatives: [] }),
        ],
      }),
    })!;

    expect(promiseSuggestionGroups(risk).map((group) => group.heading)).toEqual([
      "Sugestões para Baguete de tradição:", "Sugestões para Brioche:",
    ]);
    expect(promiseSuggestionGroups(null)).toEqual([]);
  });

  it("leitura antiga, sem `alternatives`, não quebra: o item fica sem sugestão", () => {
    const old = { ...item() } as Partial<OrderPromiseItemProjection>;
    delete old.alternatives;
    const risk = promiseRisk({ promise: atRisk("X", { items: [old as OrderPromiseItemProjection] }) })!;
    expect(risk.items[0]!.suggestions).toEqual([]);
  });

  it("quando a Produção resolve, a frase pede a Produção e a saída dela abre o plano do dia, fora do Gestor", () => {
    const risk = promiseRisk({ promise: needsProduction() })!;
    expect(risk.nextStep).toBe(PLAN_STEP);
    expect(risk.recommendedAction).toBe("open-production");
    expect(risk.exits[0]).toMatchObject({
      ref: "open-production", label: "Abrir a Produção", href: "https://producao.example.test/plan?date=2026-11-18",
      external: true, recommended: true, disabled: false, icon: "i-lucide-croissant",
    });
  });

  it("quem não abre a Produção não recebe a saída, e a frase segue dizendo o que fazer", () => {
    const risk = promiseRisk({ promise: needsProduction("HOJE-PLANEJAR", false) })!;
    expect(risk.nextStep).toBe(PLAN_STEP);
    expect(risk.exits.map((exit) => exit.ref)).toEqual(["contact-customer", "reschedule-at-pos", "cancel"]);
    expect(risk.exits.some((exit) => exit.recommended)).toBe(false);
  });

  it("leitura antiga, sem os campos novos, não quebra a tela", () => {
    const old = { ...atRisk() } as Partial<OrderPromiseProjection>;
    delete old.next_step;
    delete old.recommended_action;
    const risk = promiseRisk({ promise: old as OrderPromiseProjection })!;
    expect(risk.nextStep).toBe("");
    expect(risk.recommendedAction).toBe("");
  });
});

describe("reasonLines: o motivo escrito de um grupo de botões", () => {
  it("o motivo de todos sai uma vez; o de alguns, com o nome na frente", () => {
    expect(reasonLines([{ label: "A", reason: "x" }, { label: "B", reason: "x" }], 2)).toEqual(["x"]);
    expect(reasonLines([{ label: "A", reason: "x" }], 2)).toEqual(["A: x"]);
    expect(reasonLines([{ label: "A", reason: " " }], 1)).toEqual([]);
  });
});

describe("esperando o lote: espera saudável, sem cor de erro", () => {
  const waitingCard = card({
    promise: waiting(), advance_block_label: "Esperando o lote…", advance_block_reason: BATCH_REASON,
    actions: [lockedAdvance("Iniciar preparo", BATCH_REASON)],
  });

  it("o bloqueio com o nome do estado da promessa é a espera do lote", () => {
    expect(waitsForBatch(waitingCard)).toBe(true);
  });

  it("o pagamento que barra antes do lote continua bloqueio", () => {
    expect(waitsForBatch(card({ promise: waiting(), advance_block_label: "Aguardando Pix…" }))).toBe(false);
    expect(waitsForBatch(card({ promise: null, advance_block_label: "Esperando o lote…" }))).toBe(false);
    // O lote atrasado é risco, não espera: o nome do estado é outro.
    expect(waitsForBatch(card({ promise: atRisk(), advance_block_label: "Esperando o lote…" }))).toBe(false);
  });

  it("o selo do cartão não diz \"Bloqueado\" a quem só espera o pão", () => {
    expect(cardSeal(waitingCard)).toEqual({ label: "Confirmado", tone: "info" });
    // O bloqueio do pagamento segue vermelho, com o lote esperando ou não.
    expect(
      cardSeal(card({
        promise: waiting(), advance_block_label: "Aguardando Pix…", advance_block_reason: "Pix gerado às 9h.",
        actions: [lockedAdvance("Iniciar preparo", "Pix gerado às 9h.")],
      })),
    ).toEqual({ label: "Bloqueado", tone: "error" });
  });
});

describe("productionLines: uma fonte só para o lote (P2-19)", () => {
  it("sem a leitura da promessa vale o vínculo com o lote, enquanto o pedido espera o produto", () => {
    expect(productionLines({ awaiting_work_orders: [wo("planned")] }).map((line) => line.text)).toEqual([
      "Produção de Croissant: não começou",
    ]);
    expect(
      productionLines({ awaiting_work_orders: [wo("planned")], status: "preparing", promise: null }),
    ).toHaveLength(1);
  });

  it("pedido pronto, na rua ou encerrado não repete o vínculo que ficou gravado", () => {
    for (const status of ["ready", "dispatched", "delivered", "completed", "cancelled"])
      expect(productionLines({ awaiting_work_orders: [wo("planned")], status, promise: null })).toEqual([]);
  });

  it("o bloqueio \"Esperando o lote\" já escreve o produto e a hora: a linha solta sai", () => {
    expect(
      productionLines({
        awaiting_work_orders: [wo("planned", "Baguete de tradição")], status: "accepted",
        promise: waiting(), advance_block_reason: BATCH_REASON,
      }),
    ).toEqual([]);
  });

  it("quando outro bloqueio vem antes, o lote aparece com a hora, nas palavras do servidor", () => {
    expect(
      productionLines({
        awaiting_work_orders: [wo("planned", "Baguete de tradição")], status: "accepted",
        promise: waiting(), advance_block_reason: "Pix gerado às 9h.",
      }),
    ).toEqual([{ ref: "BAGUETE", text: "Baguete de tradição: o lote de hoje não começou. Fica pronto às 12h." }]);
  });

  it("a promessa em risco tira a linha da produção: o aviso já diz o que há com o lote", () => {
    expect(
      productionLines({ awaiting_work_orders: [wo("void", "Baguete de tradição")], status: "accepted", promise: atRisk() }),
    ).toEqual([]);
    expect(promiseWaitLines({ promise: atRisk() })).toEqual([]);
  });
});

describe("cardFooter: o ⋮ não fica sozinho numa linha (#2710)", () => {
  const aff = (over: Partial<Affordance> = {}): Affordance => ({
    ref: "advance", label: "Iniciar preparo", icon: "lucide:arrow-right", priority: "primary",
    needsInput: false, disabled: false, reason: "", ...over,
  });
  const base = { primaryLabel: "", secondary: [], blockLabel: "", blockAnnounced: false, handoff: false, waitingFor: "" };

  it("com botão, o rodapé não está vazio", () => {
    expect(cardFooter({ ...base, primary: aff(), primaryLabel: "Iniciar preparo" }).empty).toBe(false);
  });

  it("o avanço travado que só repete a pílula sai, e o rodapé fica só com o ⋮", () => {
    const footer = cardFooter({
      ...base, primary: aff({ label: "Pix expirado", disabled: true, priority: "secondary" }),
      primaryLabel: "Pix expirado", blockLabel: "Pix expirado", blockAnnounced: true,
    });
    expect(footer).toEqual({ primary: null, empty: true });
  });

  it("um secundário, o Desfazer da saída ou o \"Aguardando Café\" ocupam o rodapé", () => {
    const locked = {
      ...base, primary: aff({ label: "Pix expirado", disabled: true }), primaryLabel: "Pix expirado",
      blockLabel: "Pix expirado", blockAnnounced: true,
    };
    expect(cardFooter({ ...locked, secondary: [aff({ ref: "reject", label: "Recusar" })] }).empty).toBe(false);
    expect(cardFooter({ ...locked, handoff: true }).empty).toBe(false);
    expect(cardFooter({ ...base, primary: null, waitingFor: "Café" }).empty).toBe(false);
    expect(cardFooter({ ...base, primary: null }).empty).toBe(true);
  });
});

describe("lista de Encomendas: a encomenda em risco mora aqui", () => {
  it("a linha diz \"Promessa em risco\" e o item, conta como \"Precisa de você\" e abre a faixa das saídas", () => {
    const line = preorderLine(card({ attention: "promise", promise: atRisk() }));
    expect(line.risk).toEqual({
      label: "Promessa em risco", items: "Faltam 4x Baguete de tradição", suggestions: "", nextStep: NOTHING_STEP,
    });
    expect(line.needsYou).toBe(true);
    expect(line.to).toBe("/ENC-CANCELADA#promise");
  });

  it("em risco e ainda esperando o pagamento, segue pedindo alguém", () => {
    const line = preorderLine(card({ attention: "blocked", payment_pending: true, promise: atRisk() }));
    expect(line.awaitingPayment).toBe(true);
    expect(line.needsYou).toBe(true);
  });

  it("não repete o lote em duas frases: em risco, a linha da produção sai", () => {
    const line = preorderLine(
      card({ promise: atRisk(), awaiting_work_orders: [wo("void", "Baguete de tradição")] as never }),
    );
    expect(line.production).toBe("");
  });

  it("a encomenda com lastro não muda: abre o pedido e mostra a produção", () => {
    const line = preorderLine(card({ awaiting_work_orders: [wo("planned", "Kuro Pan")] as never }));
    expect(line.risk).toBeNull();
    expect(line.needsYou).toBe(false);
    expect(line.to).toBe("/ENC-CANCELADA");
    expect(line.production).toBe("Produção de Kuro Pan: não começou");
  });
});

describe("promiseRiskAlert: o aviso de página", () => {
  it("sem pedido em risco não há aviso", () => {
    expect(promiseRiskAlert([card(), card({ ref: "B", promise: waiting() })])).toBeNull();
  });

  it("um pedido: diz qual, o item, o porquê e o que fazer, e abre o pedido", () => {
    const alert = promiseRiskAlert([card(), card({ ref: "NB-261118-W33", promise: atRisk("NB-261118-W33") })])!;
    expect(alert).toMatchObject({
      title: "Promessa em risco no pedido W33",
      description:
        "Faltam 4x Baguete de tradição. O lote de amanhã foi cancelado. Nenhum produto parecido livre para amanhã.",
      actionLabel: "Abrir o pedido",
      firstRef: "NB-261118-W33",
      opensOrder: true,
    });
  });

  it("quem só expede não abre o detalhe: o botão diz que leva até o pedido na tela", () => {
    const alert = promiseRiskAlert([card({ ref: "NB-261118-W33", promise: atRisk() })], { canOpen: false })!;
    expect(alert).toMatchObject({ actionLabel: "Ver o W33", opensOrder: false });
  });

  it("vários: diz quantos e leva ao primeiro, na ordem em que a tela os recebeu", () => {
    const alert = promiseRiskAlert([
      card({ ref: "NB-261118-W33", promise: atRisk() }),
      card({ ref: "NB-261118-C73", promise: atRisk() }),
      card({ ref: "NB-261118-W33", promise: atRisk() }), // o mesmo pedido em duas listas conta uma vez
    ])!;
    expect(alert).toMatchObject({
      title: "Promessa em risco em 2 pedidos: avise os clientes e remarque",
      description: "W33 e C73.",
      actionLabel: "Ver o W33",
      firstRef: "NB-261118-W33",
      opensOrder: false,
    });
  });

  it("muitos pedidos: três códigos e o resto num número com nome", () => {
    const refs = ["A-1", "A-2", "A-3", "A-4", "A-5"];
    const alert = promiseRiskAlert(refs.map((ref) => card({ ref, promise: atRisk() })))!;
    expect(alert.title).toBe("Promessa em risco em 5 pedidos: avise os clientes e remarque");
    expect(alert.description).toBe("1, 2, 3 e mais 2 pedidos.");
    expect(promiseRiskAlert(refs.slice(0, 4).map((ref) => card({ ref, promise: atRisk() })))!.description).toBe(
      "1, 2, 3 e mais 1 pedido.",
    );
  });

  it("vários que só a Produção resolve: o título pede a Produção", () => {
    const alert = promiseRiskAlert([
      card({ ref: "NB-261118-N75", promise: needsProduction("NB-261118-N75") }),
      // Quem não abre a Produção lê o mesmo passo: a recomendação é do pedido, não da conta.
      card({ ref: "NB-261118-K42", promise: needsProduction("NB-261118-K42", false) }),
    ])!;
    expect(alert.title).toBe("Promessa em risco em 2 pedidos: peça à Produção para planejar");
    expect(alert.description).toBe("N75 e K42.");
  });

  it("misto: falar com os clientes vence, porque protege quem comprou", () => {
    const alert = promiseRiskAlert([
      card({ ref: "NB-261118-N75", promise: needsProduction("NB-261118-N75") }),
      card({ ref: "NB-261118-K42", promise: atRisk("NB-261118-K42") }),
    ])!;
    expect(alert.title).toBe("Promessa em risco em 2 pedidos: avise os clientes e remarque");
    expect(manyOrdersStep(["open-production", "contact-customer"])).toBe("avise os clientes e remarque");
    expect(manyOrdersStep(["open-production", "open-production"])).toBe("peça à Produção para planejar");
    // Leitura sem recomendação nunca vira pedido à Produção.
    expect(manyOrdersStep(["", "open-production"])).toBe("avise os clientes e remarque");
    expect(manyOrdersStep([])).toBe("avise os clientes e remarque");
  });

  it("um pedido que pede a Produção: a descrição leva a frase do servidor", () => {
    const alert = promiseRiskAlert([card({ ref: "NB-261118-N75", promise: needsProduction("NB-261118-N75") })])!;
    expect(alert.title).toBe("Promessa em risco no pedido N75");
    expect(alert.description).toBe(
      "Faltam 4x Baguete de tradição. Não há lote planejado para hoje. Peça à Produção para planejar.",
    );
  });

  it("outro pedido em risco é aviso novo (o que foi fechado no X volta); a ordem não muda a identidade", () => {
    const one = promiseRiskAlert([card({ ref: "A-1", promise: atRisk() })])!;
    const two = promiseRiskAlert([card({ ref: "A-1", promise: atRisk() }), card({ ref: "A-2", promise: atRisk() })])!;
    const swapped = promiseRiskAlert([card({ ref: "A-2", promise: atRisk() }), card({ ref: "A-1", promise: atRisk() })])!;
    expect(two.id).not.toBe(one.id);
    expect(swapped.id).toBe(two.id);
  });

  it("o pedido é procurado no quadro e, depois, na lista de Encomendas", () => {
    expect(orderFocusKeys("NB-1")).toEqual(["order:NB-1", "preorder:NB-1"]);
  });
});

describe("Fila: o bloqueio com o gesto e o motivo, e a promessa em risco", () => {
  const first = (source: OrderCardProjection) => queueItems([source], NOW, { scope: "all" })[0]!;

  it("a promessa em risco entra em \"Precisa de você\" e não oferece gesto de etapa", () => {
    const risky = card({
      attention: "promise", attention_since_iso: new Date(NOW - 600_000).toISOString(),
      goal_label: "combinado para amanhã às 15h", promise: atRisk(),
      advance_block_label: "Aguardando o dia da encomenda", advance_block_reason: "O preparo abre no dia combinado.",
      actions: [lockedAdvance("Iniciar preparo", "O preparo abre no dia combinado.")],
    });
    const [entry] = queueItems([risky], NOW);
    expect(entry!.kind).toBe("promise");
    expect(entry!.goalLabel).toBe("combinado para amanhã às 15h");
    expect(queueGesture(entry!)).toEqual({ primary: null, secondary: null, shortcut: "" });
    // O bloqueio do dia aparece escrito, sem cor de erro: quem pede alguém é a promessa.
    expect(queueBlock(entry!)).toMatchObject({ label: "Aguardando o dia da encomenda", color: "neutral" });
  });

  it("cobrança vencida: o selo, o motivo escrito e a saída; o botão morto sai", () => {
    const lapsed = first(card({
      attention: "blocked", payment_pending: true, payment_lapsed: true,
      advance_block_label: "Pix expirado", advance_block_reason: "Gerado às 05h51, expirou às 05h57.",
      actions: [lockedAdvance("Iniciar preparo", "Gerado às 05h51, expirou às 05h57.")],
    }));
    expect(queueBlock(lapsed)).toEqual({
      label: "Pix expirado", reason: "Gerado às 05h51, expirou às 05h57.", color: "error",
      icon: "i-lucide-lock", cancelUnpaid: true,
    });
    expect(queueGesture(lapsed).primary).toBeNull();
    expect(queueBlockedReasons(lapsed)).toEqual([]);
  });

  it("quem só espera o lote aparece no recorte Todos com o nome e a hora, em cor neutra", () => {
    const waits = first(card({
      promise: waiting(), advance_block_label: "Esperando o lote…", advance_block_reason: BATCH_REASON,
      actions: [lockedAdvance("Iniciar preparo", BATCH_REASON)],
    }));
    expect(waits.kind).toBe("");
    expect(queueBlock(waits)).toEqual({
      label: "Esperando o lote", reason: BATCH_REASON, color: "neutral", icon: "i-lucide-hourglass", cancelUnpaid: false,
    });
  });

  it("sem motivo de bloqueio, ou num fato que já tem o gesto, a linha não mostra bloqueio", () => {
    expect(queueBlock(first(card()))).toBeNull();
    expect(
      queueBlock(first(card({ attention: "start", advance_block_reason: "x", attention_since_iso: new Date(NOW).toISOString() }))),
    ).toBeNull();
  });

  it("o gesto travado diz o porquê escrito, com o nome do botão quando há outro livre", () => {
    const reject: Action = {
      ref: "reject", kind: "mutation", label: "Recusar", priority: "danger", enabled: true, reason: "",
      href: "", method: "POST", payload_schema: {}, idempotency: "required", confirmation: {},
    };
    const confirm: Action = { ...reject, ref: "confirm", label: "Aceitar", priority: "primary", enabled: false,
      reason: "Cancelamento solicitado ao iFood. Aguardando confirmação." };
    const entry = first(card({
      status: "new", attention: "confirm", attention_since_iso: new Date(NOW).toISOString(), actions: [confirm, reject],
    }));
    expect(queueBlockedReasons(entry)).toEqual(["Aceitar: Cancelamento solicitado ao iFood. Aguardando confirmação."]);
  });
});

describe("detalhe: as saídas da promessa na faixa \"O que falta neste pedido\"", () => {
  const idle = { busy: false, danfePrinting: false, lead: false };
  const action = (ref: string, over: Record<string, unknown> = {}) => ({
    ref, label: ref, enabled: true, reason: "", href: "", ...over,
  });

  it("\"Remarcar no PDV\" é atalho para outro app de operador", () => {
    const button = pendingButton(action("reschedule-at-pos", { href: "https://pdv.example.test/preorders/ENC-1" }), idle);
    expect(button).toMatchObject({
      href: "https://pdv.example.test/preorders/ENC-1", crossApp: true, icon: "i-lucide-calendar-clock", disabled: false,
    });
  });

  it("a conversa com o cliente abre fora da casa, e não é outro app de operador", () => {
    const button = pendingButton(action("contact-customer", { href: "https://wa.me/5543999990000" }), idle);
    expect(button).toMatchObject({ href: "https://wa.me/5543999990000", crossApp: false });
  });

  it("cancelar grava: o endereço que a ação carrega não vira link", () => {
    const button = pendingButton(action("cancel", { href: "/api/v1/backstage/orders/ENC-1/cancel/" }), idle);
    expect(button).toMatchObject({ href: "", color: "error", variant: "outline" });
  });

  it("atalho que o servidor desligou vira botão travado, com o motivo escrito", () => {
    const button = pendingButton(
      action("reschedule-at-pos", { enabled: false, reason: "O endereço do PDV não está configurado." }),
      idle,
    );
    expect(button).toMatchObject({ href: "", disabled: true, blockedReason: "O endereço do PDV não está configurado." });
  });

  it("a linha da promessa é alvo do próximo foco", () => {
    expect(pendingFocusKey("promise")).toBe("pending:promise");
  });

  it("\"Abrir a Produção\" é atalho para outro app de operador", () => {
    const button = pendingButton(
      action("open-production", { href: "https://producao.example.test/plan?date=2026-11-18" }),
      idle,
    );
    expect(button).toMatchObject({
      href: "https://producao.example.test/plan?date=2026-11-18", crossApp: true, icon: "i-lucide-croissant",
    });
  });

  const promiseLine = (actions: Array<Record<string, unknown>>) =>
    [{ key: "promise", tone: "error", label: "Promessa em risco", reason: "…", next_step: PLAN_STEP, actions }] as never;
  const weights = (actions: Array<Record<string, unknown>>) =>
    pendingLines(promiseLine(actions), { busy: false, danfePrinting: false })[0]!.buttons.map((button) => [
      button.ref, button.color, button.variant,
    ]);

  it("a linha escreve o próximo passo, e o gesto cheio é o que o servidor recomenda", () => {
    const [line] = pendingLines(
      promiseLine([
        action("open-production", { href: "https://producao.example.test/plan", priority: "primary" }),
        action("contact-customer", { href: "https://wa.me/55", priority: "secondary" }),
        action("cancel", { priority: "danger" }),
      ]),
      { busy: false, danfePrinting: false },
    );
    expect(line!.nextStep).toBe(PLAN_STEP);
    expect(line!.buttons.map((button) => [button.ref, button.color, button.variant])).toEqual([
      ["open-production", "primary", "solid"], ["contact-customer", "neutral", "outline"], ["cancel", "error", "outline"],
    ]);
  });

  it("linha que declara os pesos e não tem recomendado: nenhum gesto cheio", () => {
    expect(
      weights([
        action("contact-customer", { href: "https://wa.me/55", priority: "secondary" }),
        action("reschedule-at-pos", { href: "https://pdv.example.test/x", priority: "secondary" }),
        action("cancel", { priority: "danger" }),
      ]),
    ).toEqual([
      ["contact-customer", "neutral", "outline"], ["reschedule-at-pos", "neutral", "outline"], ["cancel", "error", "outline"],
    ]);
  });

  it("linha que não declara peso nenhum segue como era: o primeiro gesto é o principal", () => {
    expect(weights([action("requeue-fiscal"), action("cancel")])).toEqual([
      ["requeue-fiscal", "primary", "solid"], ["cancel", "error", "outline"],
    ]);
  });
});

describe("o painel: o aviso de página e a Tabela", () => {
  const page = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");

  it("o aviso mora nas alerts do cabeçalho, em vermelho, à frente do aviso do aceite", () => {
    const alert = page.slice(page.indexOf("const promiseScreenAlert"), page.indexOf("const screenAlerts"));
    expect(alert).toContain('color: "error"');
    expect(alert).toContain("showPromiseRisk()");
    const alerts = page.slice(page.indexOf("const screenAlerts"), page.indexOf("const screenAlerts") + 200);
    expect(alerts).toContain("promiseScreenAlert.value ? [promiseScreenAlert.value] : []");
    // Nenhuma faixa solta na página para isso: o lugar declarado é o do cabeçalho.
    const template = page.slice(page.indexOf("<template>"));
    expect(template).not.toContain("promiseAlert");
  });

  it("conta o painel inteiro, com as encomendas dos próximos dias e sem os filtros da tela", () => {
    const source = page.slice(page.indexOf("const promiseAlert"), page.indexOf("function findOnScreen"));
    expect(source).toContain("zones.value.flatMap((zone) => zone.cards)");
    expect(source).toContain("preorders.value.flatMap((group) => group.cards)");
    expect(source).not.toContain("triaged");
  });

  it("um pedido só abre na faixa das saídas; o que não está à vista também abre, nunca um botão sem efeito", () => {
    const handler = page.slice(page.indexOf("async function showPromiseRisk"), page.indexOf("const promiseScreenAlert"));
    expect(handler).toContain("navigateTo(`/${alert.firstRef}${PROMISE_HASH}`)");
    expect(handler).toContain("if (target) revealFocus(target);");
    expect(handler).toContain("else if (canManageOrders.value) void open();");
  });

  it("a Tabela escreve o motivo do gesto travado na célula, e não em `title` (#2710)", () => {
    const cell = page.slice(page.indexOf("#actions-cell"), page.indexOf("#expanded"));
    expect(cell).toContain("data-supervision-primary-reason");
    expect(cell).toContain("data-supervision-block");
    expect(cell).not.toContain(":title=");
    const expanded = page.slice(page.indexOf("#expanded"), page.indexOf("<OrderPreorderList"));
    expect(expanded).not.toContain(":title=");
    expect(expanded).toContain("<OrderPromiseExits");
  });
});
