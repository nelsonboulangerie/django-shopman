// UX-G2 (SUITE-UX §5.1): "Pronto · automático · desfazer" e a saída com
// desfazer de 5 s no card do Gestor. O servidor decide o fato e a janela
// (`undo` + ações projetadas); o card só conta o tempo e emite o gesto.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import { cardAffordances, undoLine } from "../../app/presentation/board";
import type { Action } from "../../app/generated/ordersContract";
import type { OrderCardProjection } from "../../app/types/orders";

const nowMs = ref(Date.parse("2026-10-03T15:00:00Z"));
vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => nowMs);

const NOW = Date.parse("2026-10-03T15:00:00Z");
const inSeconds = (s: number) => new Date(NOW + s * 1000).toISOString();

function action(ref: string, label: string, over: Partial<Action> = {}): Action {
  return {
    ref, label, enabled: true, reason: "", priority: "primary", kind: "mutation", href: "", method: "POST",
    payload_schema: { expected_actor_id: 1, base_revision: "rev", token: "tok" }, idempotency: "required", confirmation: {},
    ...over,
  };
}

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-20261003-A47", status: "ready", status_label: "Pronto", status_color: "", channel_ref: "web",
    channel_icon: "language", customer_name: "Ana", created_at_display: "14:50", created_at_iso: "", server_now_iso: "",
    elapsed_seconds: 600, timer_class: "timer-ok", items_summary: "2× Pão", items_count: 2, total_display: "R$ 15,00",
    fulfillment_icon: "storefront", fulfillment_label: "Retirada", fulfillment_type: "pickup", delivery_address: "",
    delivery_instructions: "", can_confirm: false, can_advance: true, next_status: "completed",
    next_action_label: "Marcar como retirado", payment_method: "cash", payment_method_label: "Dinheiro",
    ifood_cancellation_notice: "", ifood_pickup_code: "", ifood_schedule_label: "", ifood_remote_ahead_label: "",
    ifood_negotiations: [], payment_status: "captured", payment_pending: false, can_settle_delivery_cash: false,
    fiscal_status_label: "", fiscal_status: "", has_kitchen_note: false, has_customer_note: false, is_gift: false,
    gift_has_recipient: false, assigned_operator: "", awaiting_work_orders: [], confirmation_deadline_iso: "",
    confirmation_action: "", revisions: {}, actions: [], undo: null,
    ...over,
  } as OrderCardProjection;
}

const autoReady = (untilIso: string) => ({
  kind: "auto_ready", label: "Pronto · automático", detail: "Cozinha concluiu às 14:59",
  undo_until_iso: untilIso, action_ref: "undo-ready", held_effect: "Aviso de pronto ao cliente",
});
const handoff = (untilIso: string) => ({
  kind: "handoff", label: "Entregue às 15:00", detail: "O aviso ao cliente sai quando o prazo acabar.",
  undo_until_iso: untilIso, action_ref: "undo-handoff", held_effect: "Aviso ao cliente e fim do pedido",
});

const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };
const mountCard = (c: OrderCardProjection, busy = false) => mount(OrderCard, { props: { card: c, busy }, global: { stubs } });

describe("undoLine", () => {
  it("pronto automático na janela: conta o aviso que espera", () => {
    const line = undoLine({ undo: autoReady(inSeconds(24)), actions: [action("undo-ready", "Desfazer", { priority: "secondary" })] }, NOW);
    expect(line).toMatchObject({ kind: "auto_ready", label: "Pronto · automático", canUndo: true, action: "undo_ready", countdown: "0:24" });
    expect(line?.detail).toBe("aviso ao cliente sai em 0:24");
  });

  it("pronto automático depois da janela: o fato fica, o gesto some", () => {
    const line = undoLine({ undo: autoReady(""), actions: [] }, NOW);
    expect(line).toMatchObject({ canUndo: false, secondsLeft: 0, detail: "Cozinha concluiu às 14:59" });
  });

  it("saída na janela: segundos que faltam", () => {
    const line = undoLine({ undo: handoff(inSeconds(4.2)), actions: [action("undo-handoff", "Desfazer")] }, NOW);
    expect(line).toMatchObject({ kind: "handoff", canUndo: true, countdown: "5 s", action: "undo_handoff" });
  });

  it("prazo vencido na tela antes da leitura nova: sem gesto", () => {
    const line = undoLine({ undo: handoff(inSeconds(-1)), actions: [action("undo-handoff", "Desfazer")] }, NOW);
    expect(line?.canUndo).toBe(false);
  });

  it("ação desabilitada pelo servidor (sem permissão): sem gesto", () => {
    const line = undoLine({ undo: handoff(inSeconds(3)), actions: [action("undo-handoff", "Desfazer", { enabled: false })] }, NOW);
    expect(line?.canUndo).toBe(false);
  });

  it("sem undo: nada", () => {
    expect(undoLine({ undo: null, actions: [] }, NOW)).toBeNull();
  });
});

describe("cardAffordances", () => {
  it('"Marcar pronto" com a Cozinha trabalhando vai para o menu, não para o card', () => {
    const c = card({ status: "preparing", actions: [action("advance", "Marcar pronto", { priority: "menu" })] });
    expect(cardAffordances(c)).toEqual([]);
  });

  it('"Marcar pronto" sem cozinha continua botão', () => {
    const c = card({ status: "preparing", actions: [action("advance", "Marcar pronto")] });
    expect(cardAffordances(c).map((a) => a.label)).toEqual(["Marcar pronto"]);
  });

  it("saída na janela: nenhum outro gesto no card", () => {
    const c = card({ actions: [action("undo-handoff", "Desfazer"), action("advance", "Marcar como retirado")] });
    expect(cardAffordances(c)).toEqual([]);
  });
});

describe("OrderCard — o sistema fez · desfazer", () => {
  // O Desfazer da saída é o botão com prazo do kit, que lê o relógio do dispositivo.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("pronto automático: selo, aviso que espera e Desfazer que emite undo_ready", async () => {
    nowMs.value = NOW;
    const w = mountCard(card({ undo: autoReady(inSeconds(24)), actions: [action("advance", "Marcar como retirado"), action("undo-ready", "Desfazer", { priority: "secondary" })] }));
    const row = w.find('[data-undo="auto_ready"]');
    expect(row.text()).toContain("Pronto · automático");
    expect(row.text()).toContain("aviso ao cliente sai em 0:24");
    await row.find("[data-undo-button]").trigger("click");
    expect(w.emitted("action")?.[0]).toEqual(["undo_ready"]);
    // O fato humano do momento continua sendo o botão principal, com o verbo e o nome
    // (v4: "Entregar a Ana"); o rótulo do servidor fica no title.
    const primary = w.get("[data-card-primary]");
    expect(primary.text()).toMatch(/^Entregar /);
    expect(primary.attributes("title")).toBe("Marcar como retirado");
  });

  it("pronto automático depois do prazo: sem Desfazer", () => {
    nowMs.value = NOW;
    const w = mountCard(card({ undo: autoReady(""), actions: [action("advance", "Marcar como retirado")] }));
    expect(w.find('[data-undo="auto_ready"]').text()).toContain("Cozinha concluiu às 14:59");
    expect(w.find("[data-undo-button]").exists()).toBe(false);
  });

  it('saída: "Entregue às 15:00" e o Desfazer com o tempo dentro, e só esse gesto', async () => {
    nowMs.value = NOW;
    const w = mountCard(
      card({
        undo: { ...handoff(inSeconds(3)), undo_since_iso: inSeconds(-2) },
        actions: [action("undo-handoff", "Desfazer")],
      }),
    );
    await w.vm.$nextTick(); // o relógio do botão só começa montado, no cliente
    // O cartão fica no lugar (v4): o fato e o Desfazer largo, com o fundo que esvazia.
    const row = w.find('[data-undo="handoff"]');
    expect(row.text()).toContain("Entregue às 15:00");
    expect(w.get("[data-card-state]").attributes("data-card-state")).toBe("handoff");
    const undo = w.get("[data-undo-button]");
    expect(undo.text()).toBe("Desfazer");
    expect(undo.attributes("aria-describedby")).toBeTruthy();
    // O MESMO botão da saída tocada (dono, 09/10/2026): o primário sólido, só o texto muda.
    expect(undo.attributes("color")).toBe("primary");
    expect(undo.attributes("variant")).toBe("solid");
    // A janela é de 5 s e já correram 2: o fundo continua de onde ela está.
    const fill = w.get("[data-timed-fill]").attributes("style");
    expect(fill).toContain("animation-duration: 5000ms");
    expect(fill).toContain("animation-delay: -2000ms");
    expect(w.text()).not.toContain("Marcar como retirado");
    expect(w.find("[data-card-primary]").exists()).toBe(false);
    await w.get("[data-undo-button]").trigger("click");
    expect(w.emitted("action")?.[0]).toEqual(["undo_handoff"]);
  });

  it("o relógio corre: o rótulo não muda; no fim, o gesto some", async () => {
    nowMs.value = NOW;
    const w = mountCard(card({ undo: handoff(inSeconds(5)), actions: [action("undo-handoff", "Desfazer")] }));
    nowMs.value = NOW + 2000;
    await w.vm.$nextTick();
    expect(w.find("[data-undo-button]").text()).toBe("Desfazer");
    nowMs.value = NOW + 6000;
    await w.vm.$nextTick();
    expect(w.find("[data-undo-button]").exists()).toBe(false);
  });

  it("busy desabilita o Desfazer", () => {
    nowMs.value = NOW;
    const w = mountCard(card({ undo: handoff(inSeconds(5)), actions: [action("undo-handoff", "Desfazer")] }), true);
    expect(w.find("[data-undo-button]").attributes("disabled")).toBeDefined();
  });
});
