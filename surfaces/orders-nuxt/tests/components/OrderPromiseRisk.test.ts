// WP-G08 ("Promessa em risco"), montado: o cartão, a lista de Encomendas, a Fila e a
// faixa do detalhe desenham o que o servidor mandou em `promise`, com as palavras dele
// e as saídas dele: "Resolver" (abre o diálogo) e "Abrir a Produção". Os exemplos são os de
// `shopman/backstage/tests/test_order_promise.py`.
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import OrderDetailPending from "../../app/components/OrderDetailPending.vue";
import OrderPreorderList from "../../app/components/OrderPreorderList.vue";
import OrderPromiseExits from "../../app/components/OrderPromiseExits.vue";
import QueueView from "../../app/components/QueueView.vue";
import type {
  Action,
  OrderPendingProjection,
  OrderPromiseItemProjection,
  OrderPromiseProjection,
} from "../../app/generated/ordersContract";
import type { PreorderGroup } from "../../app/presentation/board";
import { promiseRisk } from "../../app/presentation/orderPromise";
import type { OrderCardProjection } from "../../app/types/orders";

const nowMs = ref(Date.parse("2026-11-18T12:00:00Z"));
vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => nowMs);
vi.stubGlobal("useRuntimeConfig", () => ({ public: { posUrl: "https://pdv.example.test" } }));

const PERMISSION = "Identifique uma pessoa com permissão para gerenciar pedidos.";
const BATCH_REASON =
  "O preparo abre quando o lote ficar pronto. Baguete de tradição: o lote de hoje não começou. Fica pronto às 12h.";

const act = (over: Partial<Action>): Action => ({
  ref: "advance", kind: "mutation", label: "Iniciar preparo", priority: "primary", enabled: true,
  reason: "", href: "", method: "POST", payload_schema: {}, idempotency: "required", confirmation: {}, ...over,
});
// Com sugestões o servidor não manda frase: a lista fala, e a saída cheia é o botão.
const SUGGESTIONS = ["Fendu · 6 livres para amanhã", "Pain de Campagne · 8 livres para amanhã"];
const PLAN_STEP = "Peça à Produção para planejar.";
/** "Resolver", como o servidor a manda: abre o diálogo das escolhas, sem `href`. */
const resolve = (over: Partial<Action> = {}): Action =>
  act({ ref: "resolve", kind: "dialog", label: "Resolver", method: "", idempotency: "none", ...over });
const exits = (): Action[] => [resolve()];
const item = (over: Partial<OrderPromiseItemProjection> = {}): OrderPromiseItemProjection => ({
  sku: "BAGUETE", name: "Baguete de tradição", reservation: "lost", cause: "batch_cancelled", at_risk: true,
  qty: "4", missing_qty: "4", label: "Faltam 4x Baguete de tradição", detail: "O lote de amanhã foi cancelado.",
  batch_date: "2026-11-19", batch_status: "void", batch_ready_at_iso: "", work_order_refs: ["WO-1"],
  next_step: "",
  alternatives: [
    { sku: "FENDU", name: "Fendu", available_display: "6 livres para amanhã" },
    { sku: "CAMPAGNE", name: "Pain de Campagne", available_display: "8 livres para amanhã" },
  ],
  ...over,
});
const atRisk = (over: Partial<OrderPromiseProjection> = {}): OrderPromiseProjection => ({
  state: "at_risk", label: "Promessa em risco", items: [item()], blocks_start: false, since_iso: "",
  actions: exits(), next_step: "", recommended_action: "resolve", ...over,
});
/** A promessa que a Produção ainda resolve. `operates`: a conta recebe "Abrir a Produção",
 *  que é a cheia, com "Resolver" ao lado; sem ela, "Resolver" é a cheia. */
const needsProduction = (operates = true): OrderPromiseProjection =>
  atRisk({
    items: [item({ cause: "no_batch", detail: "Não há lote planejado para hoje.", next_step: PLAN_STEP, alternatives: [] })],
    next_step: PLAN_STEP, recommended_action: "open-production",
    actions: operates
      ? [
          act({ ref: "open-production", kind: "link", label: "Abrir a Produção",
            href: "https://producao.example.test/plan?date=2026-11-18" }),
          resolve({ priority: "secondary" }),
        ]
      : exits(),
  });
const waiting = (): OrderPromiseProjection => ({
  state: "waiting_batch", label: "Esperando o lote", blocks_start: true, since_iso: "", actions: [],
  next_step: "", recommended_action: "",
  items: [item({ reservation: "whole", cause: "batch_waiting", at_risk: false, missing_qty: "0",
    label: "4x Baguete de tradição", detail: "O lote de hoje não começou. Fica pronto às 12h.", batch_status: "planned",
    next_step: "", alternatives: [] })],
});
const wo = (status: string, recipe_name: string) => ({
  ref: `WO-${status}`, status, status_label: status, output_sku: "BAGUETE", recipe_name,
  planned_qty: "10", finished_qty: "", progress_pct: 0,
});

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "NB-261118-W33", status: "accepted", status_label: "Confirmado", channel_ref: "web", channel_name: "Loja online",
    channel_icon: "language", customer_name: "Clara Teste",
    created_at_iso: "2026-11-18T11:00:00Z", clock_since_iso: "", server_now_iso: "", elapsed_seconds: 3600,
    timer_class: "timer-ok", items_summary: "4x Baguete de tradição", items_count: 4, total_display: "R$ 60,00",
    fulfillment_label: "Retirada", fulfillment_type: "pickup", delivery_address: "",
    can_confirm: false, can_advance: false, next_status: "",
    payment_method: "pix", payment_method_label: "Pix", payment_status: "paid", payment_status_label: "Pago",
    payment_pending: false, payment_lapsed: false, payment_tone: "success", can_settle_delivery_cash: false,
    ifood_cancellation_notice: "", ifood_schedule_label: "", ifood_remote_ahead_label: "",
    ifood_negotiations: [], fiscal_status: "",
    has_customer_note: false, is_gift: false, gift_has_recipient: false, assigned_operator: "",
    awaiting_work_orders: [], confirmation_deadline_iso: "", confirmation_action: "confirm",
    schedule_label: "", schedule_state: "", attention: "", attention_since_iso: "", goal_minutes: 0,
    goal_label: "", dispatched_at_iso: "", ready_at_iso: "", ready_eta_iso: "", advance_block_label: "",
    advance_block_reason: "", actions: [], promise: null, ...over,
  } as OrderCardProjection;
}

const cardStubs = {
  Icon: true,
  NuxtLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
  OrderCardMenu: { template: "<span data-card-menu />" },
};
const mountCard = (props: Record<string, unknown>) => mount(OrderCard, { props, global: { stubs: cardStubs } });
/** O texto e as saídas do aviso moram no Popover da pílula: abrir antes de ler. */
async function openNotice(w: ReturnType<typeof mountCard>, key: string) {
  await w.get(`[data-card-notice="${key}"]`).trigger("click");
}

describe("OrderPromiseExits: \"Resolver\" e \"Abrir a Produção\"", () => {
  const risk = promiseRisk({ promise: atRisk() })!;

  it("\"Resolver\" é um botão com o nome do servidor: avisa quem monta o diálogo, não é link", async () => {
    const w = mount(OrderPromiseExits, { props: { exits: risk.exits, code: "W33", tone: "alert" } });
    const buttons = w.findAll("[data-promise-exit]");

    expect(buttons.map((button) => button.text())).toEqual(["Resolver"]);
    expect(buttons[0]!.element.tagName).toBe("BUTTON");
    expect(buttons[0]!.attributes("href")).toBeUndefined();
    expect(buttons[0]!.attributes("aria-label")).toBe("Resolver: pedido W33");
    // Dentro do aviso, na cor do aviso; cheia, a que o servidor recomenda.
    expect([buttons[0]!.attributes("color"), buttons[0]!.attributes("variant")]).toEqual(["error", "solid"]);
    expect(w.emitted("resolve")).toBeUndefined();
    await buttons[0]!.trigger("click");
    expect(w.emitted("resolve")).toHaveLength(1);
  });

  it("\"Abrir a Produção\" é a recomendada quando a Produção resolve, e abre fora do Gestor; \"Resolver\" fica ao lado", async () => {
    const production = promiseRisk({ promise: needsProduction() })!;
    const w = mount(OrderPromiseExits, { props: { exits: production.exits, code: "W33" } });
    const buttons = w.findAll("[data-promise-exit]");

    expect(buttons.map((button) => button.text())).toEqual(["Abrir a Produção", "Resolver"]);
    expect(buttons[0]!.attributes("href")).toBe("https://producao.example.test/plan?date=2026-11-18");
    expect(buttons[0]!.attributes("external")).toBeDefined();
    expect(buttons.map((button) => [button.attributes("color"), button.attributes("variant")])).toEqual([
      ["primary", "solid"], ["neutral", "outline"],
    ]);
    // O atalho da Produção não abre o diálogo.
    await buttons[0]!.trigger("click");
    expect(w.emitted("resolve")).toBeUndefined();
    await buttons[1]!.trigger("click");
    expect(w.emitted("resolve")).toHaveLength(1);
  });

  it("quem não opera a Produção: \"Resolver\" é o cheio", () => {
    const production = promiseRisk({ promise: needsProduction(false) })!;
    const w = mount(OrderPromiseExits, { props: { exits: production.exits, code: "W33", tone: "alert" } });

    expect(w.findAll("[data-promise-exit]").map((button) => [button.text(), button.attributes("variant")])).toEqual([
      ["Resolver", "solid"],
    ]);
  });

  it("saída que o servidor desligou: botão travado, com cadeado, e o toque não abre nada", async () => {
    const locked = promiseRisk({
      promise: atRisk({ actions: [resolve({ enabled: false, reason: PERMISSION })] }),
    })!;
    const w = mount(OrderPromiseExits, { props: { exits: locked.exits, code: "W33" } });

    for (const button of w.findAll("[data-promise-exit]")) {
      expect(button.element.tagName).toBe("BUTTON");
      expect(button.attributes("disabled")).toBeDefined();
      expect(button.find('[data-icon="i-lucide-lock"]').exists()).toBe(true);
      expect(button.attributes("variant")).toBe("outline");
    }
  });
});

describe("OrderCard: promessa em risco", () => {
  const risky = card({
    attention: "promise", promise: atRisk(),
    awaiting_work_orders: [wo("void", "Baguete de tradição")] as never,
  });

  for (const compact of [false, true])
    it(`a pílula diz "Promessa em risco" em vermelho (${compact ? "cartão enxuto" : "cartão inteiro"})`, () => {
      const w = mountCard({ card: risky, compact });
      const pill = w.get('[data-card-notice="promise"]');

      expect(pill.text()).toBe("Promessa em risco");
      expect(pill.attributes("color")).toBe("error");
    });

  it("o aviso diz o item, o porquê e oferece UM botão cheio: \"Resolver\", que sobe até a página", async () => {
    const w = mountCard({ card: risky });
    await openNotice(w, "promise");
    const notice = w.get("[data-promise-risk]");

    expect(notice.attributes("color")).toBe("error");
    expect(notice.get("[data-card-notice-line]").text()).toContain("Faltam 4x Baguete de tradição");
    expect(notice.get("[data-card-notice-line]").text()).toContain("O lote de amanhã foi cancelado.");
    const buttons = notice.findAll("[data-promise-exit]");
    expect(buttons.map((button) => [button.text(), button.attributes("color"), button.attributes("variant")])).toEqual([
      ["Resolver", "error", "solid"],
    ]);
    expect(notice.find("[data-card-notice-note]").exists()).toBe(false);
    // As saídas antigas moram no diálogo: o aviso não as desenha mais.
    for (const old of ["Avisar o cliente", "Remarcar no PDV", "Cancelar pedido"]) expect(notice.text()).not.toContain(old);
    await buttons[0]!.trigger("click");
    expect(w.emitted("action")).toEqual([["resolve_promise"]]);
  });

  it("o aviso lista o que a casa pode oferecer no lugar, uma sugestão por linha, antes das saídas", async () => {
    const w = mountCard({ card: risky });
    await openNotice(w, "promise");
    const notice = w.get("[data-promise-risk]");

    const list = notice.get("[data-promise-suggestions]");
    expect(list.get("p").text()).toBe("Sugestões:");
    expect(list.findAll("[data-promise-suggestion]").map((line) => line.text())).toEqual(SUGGESTIONS);
    // O corpo do aviso não repete o verbo do botão (dono, 19/11/2026).
    expect(notice.find("[data-card-notice-next-step]").exists()).toBe(false);
    expect(notice.get("[data-card-notice-line]").text()).not.toContain("vise o cliente");
    // A recomendada é a cheia.
    expect(notice.findAll("[data-promise-exit]").map((button) => button.attributes("variant"))).toEqual(["solid"]);
  });

  for (const compact of [false, true])
    it(`com saída recomendada, o gesto da etapa fica em contorno: um botão cheio só (${compact ? "cartão enxuto" : "cartão inteiro"})`, () => {
      const advance = [act({ ref: "advance", label: "Iniciar preparo" })];
      const leads = mountCard({ card: card({ ...risky, actions: advance }), compact }).get("[data-card-primary]");
      // O preparo continua possível (decisão de 18/11), só não é o que a tela recomenda.
      expect(leads.attributes("disabled")).toBeUndefined();
      expect([leads.attributes("color"), leads.attributes("variant")]).toEqual(["neutral", "outline"]);
      expect(leads.attributes("data-card-primary-weight")).toBe("secondary");

      // Sem risco, e com risco sem saída recomendada, o gesto da etapa segue cheio.
      for (const promise of [null, atRisk({ actions: [resolve({ priority: "secondary" })] })]) {
        const plain = mountCard({ card: card({ actions: advance, promise }), compact }).get("[data-card-primary]");
        expect([plain.attributes("color"), plain.attributes("variant")]).toEqual(["primary", "solid"]);
        expect(plain.attributes("data-card-primary-weight")).toBeUndefined();
      }
    });

  it("quando a Produção resolve e a conta a opera: \"Abrir a Produção\" é o cheio e \"Resolver\" fica em contorno", async () => {
    const w = mountCard({ card: card({ attention: "promise", promise: needsProduction() }) });
    await openNotice(w, "promise");
    const notice = w.get("[data-promise-risk]");

    expect(notice.get("[data-card-notice-next-step]").text()).toBe(PLAN_STEP);
    expect(notice.findAll("[data-promise-exit]").map((button) => [button.text(), button.attributes("variant")])).toEqual([
      ["Abrir a Produção", "solid"], ["Resolver", "outline"],
    ]);
  });

  it("quando a Produção resolve e a conta não a opera: a frase diz o que fazer e \"Resolver\" é o cheio", async () => {
    const w = mountCard({ card: card({ attention: "promise", promise: needsProduction(false) }) });
    await openNotice(w, "promise");
    const notice = w.get("[data-promise-risk]");

    expect(notice.get("[data-card-notice-next-step]").text()).toBe(PLAN_STEP);
    expect(notice.find('[data-promise-exit="open-production"]').exists()).toBe(false);
    expect(notice.get('[data-promise-exit="resolve"]').attributes("variant")).toBe("solid");
  });

  it("a linha solta da produção não repete o que o aviso já diz (P2-19)", () => {
    const w = mountCard({ card: risky });

    expect(w.find("[data-card-progress]").exists()).toBe(false);
    expect(w.text()).not.toContain("Produção de");
  });

  it("quem não gerencia pedidos lê o risco e o motivo de não poder agir, escrito", async () => {
    const w = mountCard({
      card: card({
        promise: atRisk({ actions: [resolve({ enabled: false, reason: PERMISSION })] }),
      }),
      canOpen: false,
    });
    await openNotice(w, "promise");

    expect(w.get("[data-card-notice-note]").text()).toBe(PERMISSION);
    expect(w.findAll("[data-promise-exit]").every((button) => button.attributes("disabled") !== undefined)).toBe(true);
  });

  it("o cartão é alvo do próximo foco: o aviso de página leva até ele", () => {
    expect(mountCard({ card: risky }).get("article").attributes("data-focus-target")).toBe("order:NB-261118-W33");
  });
});

describe("OrderCard: esperando o lote", () => {
  const waits = card({
    promise: waiting(), advance_block_label: "Esperando o lote…", advance_block_reason: BATCH_REASON,
    actions: [act({ enabled: false, reason: BATCH_REASON })],
    awaiting_work_orders: [wo("planned", "Baguete de tradição")] as never,
  });

  it("a pílula do bloqueio diz \"Esperando o lote\", com o produto e a hora a um toque, sem cor de erro", async () => {
    const w = mountCard({ card: waits });
    const pill = w.get('[data-card-notice="block"]');
    await openNotice(w, "block");

    expect(pill.text()).toBe("Esperando o lote");
    expect(pill.attributes("color")).toBe("info");
    expect(pill.find('[data-icon="i-lucide-hourglass"]').exists()).toBe(true);
    expect(w.get("[data-advance-block]").text()).toContain("Fica pronto às 12h.");
    expect(w.get("[data-card-seal]").text()).toBe("Confirmado");
    expect(w.find('[data-card-notice="promise"]').exists()).toBe(false);
    // Estado normal: nenhuma frase de ação, nenhum botão de saída.
    expect(w.find("[data-card-notice-next-step]").exists()).toBe(false);
    expect(w.find("[data-promise-exit]").exists()).toBe(false);
  });

  it("não sobra botão morto nem a linha \"Produção de…\"", () => {
    const w = mountCard({ card: waits });

    expect(w.find("[data-card-primary]").exists()).toBe(false);
    expect(w.find("[data-card-progress]").exists()).toBe(false);
    expect(w.text()).not.toContain("Produção de");
  });

  it("sem botão no rodapé, as pílulas descem para a linha do ⋮ (#2710)", () => {
    for (const compact of [false, true]) {
      const w = mountCard({ card: waits, compact });
      const lone = w.get("[data-card-lone]");

      expect(lone.find('[data-card-notice="block"]').exists()).toBe(true);
      // Uma vez só: as pílulas não ficam também no corpo do cartão.
      expect(w.findAll('[data-card-notice="block"]')).toHaveLength(1);
      expect(lone.element.parentElement?.querySelector("[data-card-menu]")).not.toBeNull();
    }
  });

  it("com botão no rodapé, as pílulas seguem no corpo do cartão", () => {
    const w = mountCard({
      card: card({ can_advance: true, promise: atRisk(), actions: [act({})] }),
    });

    expect(w.find("[data-card-primary]").exists()).toBe(true);
    expect(w.find("[data-card-lone]").exists()).toBe(false);
    expect(w.findAll('[data-card-notice="promise"]')).toHaveLength(1);
  });
});

describe("OrderCard: pedido pronto não fala de produção", () => {
  it("o vínculo com o lote que ficou gravado não vira linha num pedido pronto", () => {
    const w = mountCard({
      card: card({
        status: "ready", status_label: "Pronto", can_advance: true, actions: [act({ label: "Marcar como retirado" })],
        awaiting_work_orders: [wo("planned", "Croissant")] as never,
      }),
    });

    expect(w.text()).not.toContain("Produção de Croissant");
  });
});

describe("OrderPreorderList: a encomenda em risco", () => {
  const groups = (...cards: OrderCardProjection[]): PreorderGroup[] => [{ date: "2026-11-19", label: "amanhã", cards }];
  const listStubs = {
    NuxtLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
    OperatorCountChip: { props: ["count"], template: "<span data-count>{{ count }}</span>" },
  };
  const mountList = (...cards: OrderCardProjection[]) =>
    mount(OrderPreorderList, { props: { groups: groups(...cards), count: cards.length }, global: { stubs: listStubs } });

  it("a linha diz \"Promessa em risco\", o item que falta, as sugestões e \"Precisa de você\"", () => {
    const w = mountList(card({ attention: "promise", promise: atRisk(), schedule_label: "Amanhã · A partir das 15h" }));
    const row = w.get('[data-preorder-row="NB-261118-W33"]');

    expect(row.attributes("data-preorder-at-risk")).toBeDefined();
    expect(row.get("[data-preorder-risk]").text()).toBe("Promessa em risco");
    expect(row.get("[data-preorder-risk]").attributes("color")).toBe("error");
    expect(row.get("[data-preorder-risk-items]").text()).toBe("Faltam 4x Baguete de tradição");
    expect(row.get("[data-preorder-needs-you]").text()).toBe("Precisa de você");
    // O que oferecer no lugar, numa linha só; o "Resolver" está no pedido que ela abre.
    expect(row.get("[data-preorder-risk-suggestions]").text()).toBe(`Sugestões: ${SUGGESTIONS.join("; ")}`);
    expect(row.find("[data-preorder-risk-next-step]").exists()).toBe(false);
    expect(row.find("[data-promise-exit]").exists()).toBe(false);
  });

  it("a linha abre o pedido na faixa do \"Resolver\", sem diálogo próprio; \"Remarcar no PDV\" da lista segue ao lado", () => {
    const w = mountList(card({ attention: "promise", promise: atRisk() }));
    const row = w.get('[data-preorder-row="NB-261118-W33"]');

    expect(row.get("a").attributes("href")).toBe("/NB-261118-W33#promise");
    expect(row.get('[data-preorder-reschedule=""]').html()).toContain("https://pdv.example.test/preorders/NB-261118-W33");
  });

  it("a encomenda com lastro não ganha selo nem muda de destino", () => {
    const w = mountList(card());
    const row = w.get('[data-preorder-row="NB-261118-W33"]');

    expect(row.find("[data-preorder-risk]").exists()).toBe(false);
    expect(row.attributes("data-preorder-at-risk")).toBeUndefined();
    expect(row.get("a").attributes("href")).toBe("/NB-261118-W33");
  });
});

describe("QueueView: a Fila", () => {
  const queueStubs = {
    Icon: true,
    NuxtIcon: true,
    NuxtKbd: true,
    NuxtEmpty: { props: ["description"], template: "<p data-empty>{{ description }}</p>" },
    NuxtAccordion: true,
    NuxtPageCard: { template: "<article><slot /></article>" },
    NuxtLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
    OrderCardMenu: { template: "<span data-card-menu />" },
    OperatorCountChip: true,
    ChannelQueueSignal: true,
  };
  const mountQueue = (cards: OrderCardProjection[], props: Record<string, unknown> = {}) =>
    mount(QueueView, {
      props: {
        cards, awareness: null, nowMs: nowMs.value, focusRef: "", isBusy: () => false, actionError: () => "",
        canOpen: true, ...props,
      },
      global: { stubs: queueStubs },
    });

  it("a promessa em risco entra em \"Precisa de você\" com o item, o porquê e as saídas", () => {
    const w = mountQueue([
      card({
        attention: "promise", attention_since_iso: "2026-11-18T11:50:00Z", goal_label: "combinado para amanhã às 15h",
        promise: atRisk(),
      }),
    ]);
    const row = w.get('[data-queue-ref="NB-261118-W33"]');
    const risk = row.get("[data-queue-promise-risk]");

    expect(row.attributes("data-queue-item")).toBe("promise");
    expect(row.attributes("data-focus-target")).toBe("order:NB-261118-W33");
    expect(risk.text()).toContain("Promessa em risco");
    expect(risk.text()).toContain("Faltam 4x Baguete de tradição");
    expect(risk.text()).toContain("O lote de amanhã foi cancelado.");
    expect(risk.findAll("[data-promise-suggestion]").map((line) => line.text())).toEqual(SUGGESTIONS);
    expect(risk.find("[data-queue-promise-next-step]").exists()).toBe(false);
    const buttons = risk.findAll("[data-promise-exit]");
    // A saída que o servidor recomenda é a única cheia.
    expect(buttons.map((button) => [button.text(), button.attributes("color"), button.attributes("variant")])).toEqual([
      ["Resolver", "primary", "solid"],
    ]);
    expect(row.find("[data-queue-primary]").exists()).toBe(false);
  });

  it("\"Resolver\" na linha da Fila sobe como ação do pedido, para a página abrir o diálogo", async () => {
    const w = mountQueue([
      card({ attention: "promise", attention_since_iso: "2026-11-18T11:50:00Z", promise: atRisk() }),
    ]);

    await w.get('[data-promise-exit="resolve"]').trigger("click");
    expect(w.emitted("action")).toEqual([["NB-261118-W33", "resolve_promise"]]);
  });

  it("com saída recomendada, o gesto da etapa da linha fica em contorno: um botão cheio só", () => {
    const advance = [act({ ref: "advance", label: "Iniciar preparo" })];
    const row = (promise: OrderPromiseProjection | null) =>
      mountQueue([
        // O pedido aceito e pronto para iniciar entra na Fila pelo gesto da etapa ("start"),
        // e a promessa em risco vem escrita na mesma linha.
        card({ attention: "start", attention_since_iso: "2026-11-18T11:50:00Z", promise, actions: advance }),
      ]).get("[data-queue-primary]");

    const leads = row(atRisk());
    expect([leads.attributes("color"), leads.attributes("variant")]).toEqual(["neutral", "outline"]);
    expect(leads.attributes("data-queue-primary-weight")).toBe("secondary");
    const plain = row(null);
    expect([plain.attributes("color"), plain.attributes("variant")]).toEqual(["primary", "solid"]);
    expect(plain.attributes("data-queue-primary-weight")).toBeUndefined();
  });

  it("a que a Produção resolve: a frase pede a Produção e o botão cheio abre o plano do dia", () => {
    const w = mountQueue([
      card({ attention: "promise", attention_since_iso: "2026-11-18T11:50:00Z", promise: needsProduction() }),
    ]);
    const risk = w.get("[data-queue-promise-risk]");

    expect(risk.get("[data-queue-promise-next-step]").text()).toBe(PLAN_STEP);
    const open = risk.get('[data-promise-exit="open-production"]');
    expect(open.text()).toBe("Abrir a Produção");
    expect(open.attributes("href")).toBe("https://producao.example.test/plan?date=2026-11-18");
    expect([open.attributes("color"), open.attributes("variant")]).toEqual(["primary", "solid"]);
    expect(risk.get('[data-promise-exit="resolve"]').attributes("variant")).toBe("outline");
  });

  it("cobrança vencida: o selo, o motivo escrito e \"Cancelar pedido\"; nenhum botão morto", () => {
    const w = mountQueue([
      card({
        attention: "blocked", attention_since_iso: "2026-11-18T11:50:00Z", payment_pending: true, payment_lapsed: true,
        advance_block_label: "Pix expirado", advance_block_reason: "Gerado às 05h51, expirou às 05h57.",
        actions: [act({ enabled: false, reason: "Gerado às 05h51, expirou às 05h57." })],
      }),
    ]);
    const row = w.get('[data-queue-ref="NB-261118-W33"]');

    expect(row.get("[data-queue-block]").text()).toBe("Pix expirado");
    expect(row.get("[data-queue-block]").attributes("color")).toBe("error");
    expect(row.get("[data-queue-block-reason]").text()).toBe("Gerado às 05h51, expirou às 05h57.");
    const cancel = row.get("[data-queue-cancel-unpaid]");
    expect(cancel.text()).toBe("Cancelar pedido");
    expect(cancel.attributes("href")).toBe("/NB-261118-W33#cancel-unpaid");
    expect(row.find("[data-queue-primary]").exists()).toBe(false);
  });

  it("quem só expede não recebe o atalho de cancelar (o detalhe não abre para essa conta)", () => {
    const w = mountQueue(
      [
        card({
          attention: "blocked", attention_since_iso: "2026-11-18T11:50:00Z", payment_pending: true, payment_lapsed: true,
          advance_block_label: "Pix expirado", advance_block_reason: "Gerado às 05h51, expirou às 05h57.",
        }),
      ],
      { canOpen: false },
    );

    expect(w.find("[data-queue-block]").exists()).toBe(true);
    expect(w.find("[data-queue-cancel-unpaid]").exists()).toBe(false);
  });

  it("no recorte Todos, quem espera o lote diz o produto e a hora, em cor neutra", () => {
    const w = mountQueue(
      [
        card({
          promise: waiting(), advance_block_label: "Esperando o lote…", advance_block_reason: BATCH_REASON,
          actions: [act({ enabled: false, reason: BATCH_REASON })],
        }),
      ],
      { scope: "all" },
    );
    const row = w.get('[data-queue-ref="NB-261118-W33"]');

    expect(row.get("[data-queue-block]").text()).toBe("Esperando o lote");
    expect(row.get("[data-queue-block]").attributes("color")).toBe("neutral");
    expect(row.get("[data-queue-block-reason]").text()).toContain("Fica pronto às 12h.");
    expect(row.find("[data-queue-moving]").exists()).toBe(false);
  });

  it("o \"Aceitar\" travado diz o porquê escrito, sem depender de hover", () => {
    const reason = "Cancelamento solicitado ao iFood. Aguardando confirmação.";
    const w = mountQueue([
      card({
        status: "new", status_label: "Novo", attention: "confirm", attention_since_iso: "2026-11-18T11:58:00Z",
        actions: [
          act({ ref: "confirm", label: "Aceitar", enabled: false, reason }),
          act({ ref: "reject", label: "Recusar", priority: "danger" }),
        ],
      }),
    ]);
    const row = w.get('[data-queue-ref="NB-261118-W33"]');

    expect(row.get("[data-queue-blocked-reason]").text()).toBe(`Aceitar: ${reason}`);
    expect(row.get("[data-queue-primary]").attributes("title")).toBeUndefined();
  });
});

describe("OrderDetailPending: a linha da promessa em risco", () => {
  const stubs = {
    Icon: { props: ["name"], template: "<i :data-icon='name' />" },
    OperatorCountChip: { props: ["count"], template: "<span data-count>{{ count }}</span>" },
  };
  const line: OrderPendingProjection = {
    key: "promise", tone: "error", label: "Promessa em risco",
    reason: "Faltam 4x Baguete de tradição. O lote de amanhã foi cancelado.",
    next_step: "",
    actions: [{ ref: "resolve", label: "Resolver", enabled: true, reason: "", href: "", priority: "primary" }],
  };
  const faixa = (pending: OrderPendingProjection[], promise: OrderPromiseProjection | null = atRisk()) =>
    mount(OrderDetailPending, { props: { pending, promise }, global: { stubs } });

  it("diz o fato e o porquê com as palavras do servidor, e é alvo do `#promise`", () => {
    const row = faixa([line]).get('[data-pending="promise"]');

    expect(row.attributes("data-focus-target")).toBe("pending:promise");
    expect(row.attributes("data-pending-tone")).toBe("error");
    expect(row.text()).toContain("Promessa em risco");
    expect(row.get("[data-pending-reason]").text()).toBe("Faltam 4x Baguete de tradição. O lote de amanhã foi cancelado.");
    // O que a casa pode oferecer no lugar, em lista; o gesto recomendado é o cheio.
    expect(row.get("[data-promise-suggestions] p").text()).toBe("Sugestões:");
    expect(row.findAll("[data-promise-suggestion]").map((option) => option.text())).toEqual(SUGGESTIONS);
    expect(row.find("[data-pending-next-step]").exists()).toBe(false);
    expect(row.findAll("[data-pending-action]").map((button) => [button.text(), button.attributes("variant")])).toEqual([
      ["Resolver", "solid"],
    ]);
  });

  it("quando a Produção resolve: \"Abrir a Produção\" é o gesto cheio e abre o outro app; \"Resolver\" fica ao lado", () => {
    const w = faixa([
      {
        ...line, next_step: PLAN_STEP,
        actions: [
          { ref: "open-production", label: "Abrir a Produção", enabled: true, reason: "",
            href: "https://producao.example.test/plan?date=2026-11-18", priority: "primary" },
          { ...line.actions[0]!, priority: "secondary" },
        ],
      },
    ]);
    const open = w.get('[data-pending-action="open-production"]');

    expect(w.get("[data-pending-next-step]").text()).toBe(PLAN_STEP);
    expect(open.attributes("href")).toBe("https://producao.example.test/plan?date=2026-11-18");
    expect(open.attributes("external")).toBeDefined();
    expect(open.attributes("variant")).toBe("solid");
    expect(w.get('[data-pending-action="resolve"]').attributes("variant")).toBe("outline");
  });

  it("sem gesto recomendado, a frase diz o que fazer e nenhum botão é cheio", () => {
    const w = faixa([{ ...line, next_step: PLAN_STEP, actions: [{ ...line.actions[0]!, priority: "secondary" }] }]);

    expect(w.get("[data-pending-next-step]").text()).toBe(PLAN_STEP);
    expect(w.findAll("[data-pending-action]").every((button) => button.attributes("variant") === "outline")).toBe(true);
  });

  it("\"Resolver\" é botão: sobe para a página, que abre o diálogo; as saídas antigas saíram da linha", async () => {
    const w = faixa([line]);
    const button = w.get('[data-pending-action="resolve"]');

    expect(button.element.tagName).toBe("BUTTON");
    expect(button.attributes("href")).toBeUndefined();
    // O teclado de quem chega pelo `#promise` cai no primeiro gesto da linha.
    expect(button.attributes("data-focus-control")).toBeDefined();
    for (const old of ["contact-customer", "reschedule-at-pos", "cancel"])
      expect(w.find(`[data-pending-action="${old}"]`).exists()).toBe(false);
    await button.trigger("click");
    expect(w.emitted("act")).toEqual([["resolve"]]);
  });

  it("\"Resolver\" travado (quem não gerencia pedidos) escreve o motivo", () => {
    const w = faixa([{ ...line, actions: [{ ...line.actions[0]!, enabled: false, reason: PERMISSION }] }]);

    expect(w.get('[data-pending-action="resolve"]').attributes("disabled")).toBeDefined();
    expect(w.get("[data-pending-blocked]").text()).toBe(PERMISSION);
  });
});
