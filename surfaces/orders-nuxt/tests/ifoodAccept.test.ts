// P1-3: o aceite que não chegou ao iFood. Aceitar aqui não garante que o iFood
// recebeu; sem o aviso, a cozinha trabalhava e o iFood cancelava sozinho no fim do
// prazo dele, que o cartão deixava de mostrar fora de "novo".
import { describe, expect, it } from "vitest";

import { cardClock, ifoodAcceptNotice } from "../app/presentation/board";
import { queueGesture, queueItems } from "../app/presentation/queue";
import type { OrderCardProjection } from "../app/types/orders";

const NOW = Date.parse("2026-10-13T15:00:00Z");
const IN_4_32 = new Date(NOW + (4 * 60 + 32) * 1000).toISOString();
const PAST = new Date(NOW - 30 * 1000).toISOString();

const retry = (enabled = true, reason = "") =>
  ({
    ref: "ifood-accept-retry",
    label: "Tentar de novo",
    enabled,
    priority: "primary",
    reason,
  }) as never;

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "IFD-261013-4821",
    status: "preparing",
    status_label: "Em preparo",
    actions: [retry()],
    ifood_accept_failed: true,
    ifood_accept_notice:
      "O iFood ainda não recebeu o aceite do pedido IFD-261013-4821. Toque em Tentar de novo no pedido.",
    confirmation_deadline_iso: IN_4_32,
    confirmation_action: "cancel",
    elapsed_seconds: 200,
    timer_class: "timer-muted",
    kitchen: null,
    ...over,
  } as OrderCardProjection;
}

describe("ifoodAcceptNotice", () => {
  it("diz que o iFood não recebeu o aceite, com o prazo dele contando e o reenvio", () => {
    const notice = ifoodAcceptNotice(card(), NOW);
    expect(notice).toEqual({
      label: "Aceite não chegou",
      title: "O iFood ainda não recebeu o aceite",
      description:
        "A cozinha segue com o pedido. Se o aceite não chegar em 4:32, o iFood cancela sozinho.",
      action: { label: "Tentar de novo", enabled: true, reason: "" },
    });
    expect(notice?.description).not.toContain("—");
  });

  it("não aparece quando o aceite chegou", () => {
    expect(
      ifoodAcceptNotice(card({ ifood_accept_failed: false }), NOW),
    ).toBeNull();
  });

  it("prazo vencido: manda conferir no iFood em vez de contar zero", () => {
    expect(
      ifoodAcceptNotice(card({ confirmation_deadline_iso: PAST }), NOW)
        ?.description,
    ).toBe(
      "O prazo do iFood para o aceite acabou. Confira no iFood se o pedido segue ativo.",
    );
  });

  it("sem prazo gravado, fica a frase do servidor", () => {
    const notice = ifoodAcceptNotice(
      card({ confirmation_deadline_iso: "" }),
      NOW,
    );
    expect(notice?.description).toContain("Toque em Tentar de novo");
  });

  it("quem não pode gerenciar pedidos vê o gesto desligado, com o motivo", () => {
    const reason =
      "Identifique uma pessoa com permissão para gerenciar pedidos.";
    expect(
      ifoodAcceptNotice(card({ actions: [retry(false, reason)] }), NOW)?.action,
    ).toEqual({ label: "Tentar de novo", enabled: false, reason });
  });
});

describe("o relógio do cartão segue o prazo do iFood depois do aceite local", () => {
  it("em preparo, com o aceite sem chegar, o canto diz quando o iFood cancela", () => {
    const clock = cardClock(card(), NOW);
    expect(clock).toMatchObject({
      text: "cancela sozinho em 4:32",
      countdown: true,
    });
  });
});

describe("a Fila: o aceite que não chegou pede você", () => {
  const inQueue = (over: Partial<OrderCardProjection> = {}) =>
    card({
      attention: "ifood_accept",
      attention_since_iso: new Date(NOW - 210_000).toISOString(),
      goal_minutes: 8,
      goal_label: "aceite até 12:04",
      ...over,
    });

  it("o gesto da linha é Tentar de novo, e o prazo duro é o do iFood", () => {
    const [item] = queueItems([inQueue()], NOW);
    expect(item?.kind).toBe("ifood_accept");
    expect(item?.cancelsIn).toBe(272);
    expect(queueGesture(item!).primary).toMatchObject({
      ref: "ifood_accept_retry",
      verb: "Tentar de novo",
      disabled: false,
    });
  });

  it("sem permissão, o gesto aparece desligado com o motivo", () => {
    const reason =
      "Identifique uma pessoa com permissão para gerenciar pedidos.";
    const [item] = queueItems(
      [inQueue({ actions: [retry(false, reason)] })],
      NOW,
    );
    expect(queueGesture(item!).primary).toMatchObject({
      disabled: true,
      reason,
    });
  });
});
