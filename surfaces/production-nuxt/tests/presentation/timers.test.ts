import { describe, expect, it } from "vitest";

import {
  FLOOR_TIMER_ARM_MS,
  filterTags,
  findTagByLabel,
  floorTimerModeLabel,
  floorTimerTap,
  floorTimerTapHint,
  minutesLabel,
  normalizeTagLabel,
} from "~/presentation/timers";

const tags = [
  { ref: "estufa", label: "Estufa", minutes: 60 },
  { ref: "pausa-cafe", label: "Pausa-café", minutes: 15 },
  { ref: "descanso", label: "Descanso", minutes: 20 },
];

describe("floorTimerTap — o gesto de toda hora, um por estado", () => {
  it("o card que grita cala com o toque no corpo", () => {
    expect(floorTimerTap("ringing", { armed: false })).toBe("seen");
    expect(floorTimerTap("ringing", { armed: true })).toBe("seen");
  });

  it("o card já visto encerra com o toque — mas só depois de armado", () => {
    expect(floorTimerTap("seen", { armed: false })).toBe("none");
    expect(floorTimerTap("seen", { armed: true })).toBe("clear");
  });

  it("o card que corre não reage ao toque no corpo", () => {
    expect(floorTimerTap("running", { armed: true })).toBe("none");
  });

  it("a janela de armar existe e é curta o bastante para não atrapalhar", () => {
    expect(FLOOR_TIMER_ARM_MS).toBeGreaterThan(300);
    expect(FLOOR_TIMER_ARM_MS).toBeLessThan(2000);
  });
});

describe("o que a tela DIZ sobre o próprio toque", () => {
  it("escreve o gesto quando ele existe", () => {
    expect(floorTimerTapHint("ringing")).toBe("Toque no card para marcar Visto");
    expect(floorTimerTapHint("seen")).toBe("Toque no card para encerrar");
  });

  it("cala quando o corpo não é botão — dica de gesto inexistente é ruído", () => {
    expect(floorTimerTapHint("running")).toBe("");
  });

  it("o rótulo de estado usa a palavra da casa, e deixa o relógio falar sozinho", () => {
    expect(floorTimerModeLabel("ringing")).toBe("Tempo esgotado");
    expect(floorTimerModeLabel("seen")).toBe("Visto");
    expect(floorTimerModeLabel("running")).toBe("");
  });
});

describe("minutesLabel", () => {
  it("fala minutos até a hora, depois hora e resto", () => {
    expect(minutesLabel(15)).toBe("15 min");
    expect(minutesLabel(59)).toBe("59 min");
    expect(minutesLabel(60)).toBe("1 h");
    expect(minutesLabel(90)).toBe("1 h 30 min");
    expect(minutesLabel(120)).toBe("2 h");
  });

  it("nunca mostra tempo negativo", () => {
    expect(minutesLabel(-5)).toBe("0 min");
  });
});

describe("normalizeTagLabel — o gêmeo comparável do servidor", () => {
  it("dobra caixa, acento, pontuação e espaço sobrando", () => {
    expect(normalizeTagLabel("Pausa-café")).toBe("pausa cafe");
    expect(normalizeTagLabel("  PAUSA   CAFÉ  ")).toBe("pausa cafe");
    expect(normalizeTagLabel("pausa cafe")).toBe("pausa cafe");
    expect(normalizeTagLabel("Descanso 2ª volta")).toBe("descanso 2 volta");
  });

  it("nome que não identifica nada normaliza para vazio", () => {
    expect(normalizeTagLabel("   ")).toBe("");
    expect(normalizeTagLabel("---")).toBe("");
  });
});

describe("findTagByLabel", () => {
  it("reconhece a etiqueta existente escrita de outro jeito", () => {
    expect(findTagByLabel(tags, "pausa cafe")?.ref).toBe("pausa-cafe");
    expect(findTagByLabel(tags, "  ESTUFA ")?.ref).toBe("estufa");
  });

  it("devolve null para nome novo e para nome vazio", () => {
    expect(findTagByLabel(tags, "Banho-maria")).toBeNull();
    expect(findTagByLabel(tags, "  ")).toBeNull();
  });
});

describe("filterTags", () => {
  it("busca vazia deixa todas na tela", () => {
    expect(filterTags(tags, "").map((tag) => tag.ref)).toEqual([
      "estufa",
      "pausa-cafe",
      "descanso",
    ]);
  });

  it("busca sem acento encontra a etiqueta com acento", () => {
    expect(filterTags(tags, "cafe").map((tag) => tag.ref)).toEqual(["pausa-cafe"]);
  });

  it("devolve lista vazia quando nada casa", () => {
    expect(filterTags(tags, "forno")).toEqual([]);
  });
});
