import { describe, expect, it } from "vitest";

import {
  confirmLabel,
  emptyDraft,
  missingStep,
  monthWeeks,
  pickDay,
  rangeLine,
  switchRequest,
} from "../app/presentation/channelSwitch";
import type { ChannelSwitchProjection } from "../app/types/feeds";

function sw(over: Partial<ChannelSwitchProjection> = {}): ChannelSwitchProjection {
  return {
    is_active: true,
    state_line: "",
    closed_by_shop: "",
    scheduled_line: "",
    title: "Desligar Loja online",
    consequence: "A loja online para de aceitar pedidos.",
    periods: [
      { key: "30m", label: "Por 30 minutos", enabled: true, reason: "" },
      { key: "1h", label: "Por 1 hora", enabled: true, reason: "" },
      { key: "today", label: "Por hoje (até as 18h)", enabled: true, reason: "" },
      { key: "open", label: "Sem prazo (até alguém religar)", enabled: true, reason: "" },
      { key: "custom", label: "Escolher período…", enabled: true, reason: "" },
    ],
    reasons: ["Loja cheia", "Férias"],
    reason_required: true,
    enabled: true,
    disabled_reason: "",
    base_revision: "rev",
    expected_actor_id: 1,
    requires_manager_approval: false,
    ...over,
  };
}

const NOW = new Date(2026, 11, 22, 10, 0);

describe("o rascunho do modal do toggle", () => {
  it("pede o período antes de tudo, e o motivo para desligar", () => {
    expect(missingStep(sw(), emptyDraft(), NOW)).toBe("Escolha por quanto tempo.");
    expect(missingStep(sw(), { ...emptyDraft(), period: "1h" }, NOW)).toBe("Escolha ou escreva o motivo.");
    expect(missingStep(sw(), { ...emptyDraft(), period: "1h", reason: "Loja cheia" }, NOW)).toBe("");
  });

  it("ligar não exige motivo", () => {
    expect(missingStep(sw({ is_active: false, reason_required: false }), { ...emptyDraft(), period: "open" }, NOW)).toBe("");
  });

  it("opção desabilitada pelo horário da loja não vale", () => {
    const closed = sw({ is_active: false, reason_required: false, periods: [
      { key: "30m", label: "Por 30 minutos", enabled: false, reason: "A loja está fechada agora; o canal só abre junto com ela." },
    ] });
    expect(missingStep(closed, { ...emptyDraft(), period: "30m" }, NOW)).toBe("Escolha por quanto tempo.");
  });

  it("período no calendário: começo, fim e fim depois do começo", () => {
    const base = { ...emptyDraft(), period: "custom", reason: "Férias" };
    expect(missingStep(sw(), base, NOW)).toBe("Escolha no calendário quando começa e quando termina.");
    expect(missingStep(sw(), { ...base, startDate: "2026-12-24", endDate: "2026-12-24" }, NOW)).toBe("O fim precisa vir depois do início.");
    expect(missingStep(sw(), { ...base, startDate: "2026-12-24", endDate: "2027-01-04" }, NOW)).toBe("");
  });

  it("o pedido leva o estado contrário ao atual e, no calendário, as duas pontas", () => {
    const request = switchRequest(sw(), { ...emptyDraft(), period: "custom", reason: " Férias ", startDate: "2026-12-24", endDate: "2027-01-04" });
    expect(request.is_active).toBe(false);
    expect(request.reason).toBe("Férias");
    expect(new Date(request.starts_at!).getDate()).toBe(24);
    expect(new Date(request.ends_at!).getMonth()).toBe(0);
    expect(switchRequest(sw(), { ...emptyDraft(), period: "1h", reason: "x" }).starts_at).toBeUndefined();
  });

  it("o botão diz o gesto — e o agendamento, quando começa depois", () => {
    expect(confirmLabel(sw(), { ...emptyDraft(), period: "1h" }, NOW)).toBe("Desligar");
    expect(confirmLabel(sw({ is_active: false }), { ...emptyDraft(), period: "open" }, NOW)).toBe("Ligar");
    expect(confirmLabel(sw(), { ...emptyDraft(), period: "custom", startDate: "2026-12-24" }, NOW)).toBe("Agendar o desligamento");
  });
});

describe("o calendário do período", () => {
  it("primeiro toque marca o começo; o segundo, o fim; antes do começo, recomeça", () => {
    let draft = emptyDraft();
    draft = { ...draft, ...pickDay(draft, "2026-12-24") };
    draft = { ...draft, ...pickDay(draft, "2027-01-04") };
    expect([draft.startDate, draft.endDate]).toEqual(["2026-12-24", "2027-01-04"]);
    draft = { ...draft, ...pickDay(draft, "2026-12-26") };
    expect([draft.startDate, draft.endDate]).toEqual(["2026-12-26", ""]);
  });

  it("dias passados não se escolhem", () => {
    const days = monthWeeks(2026, 11, NOW).flat();
    expect(days.find((day) => day.iso === "2026-12-21")?.past).toBe(true);
    expect(days.find((day) => day.iso === "2026-12-22")?.past).toBe(false);
  });

  it("a janela em uma linha, com as horas", () => {
    expect(rangeLine({ ...emptyDraft(), startDate: "2026-12-24", endDate: "2027-01-04", endTime: "07:30" }))
      .toBe("de qui. 24/12 às 0h a seg. 4/1 às 7h30");
  });
});
