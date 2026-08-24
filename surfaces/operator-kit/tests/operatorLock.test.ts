import { describe, expect, it } from "vitest";

import {
  BADGE_MAX_GAP_MS,
  appendPinDigit,
  buildUnlockPayload,
  canSubmitPin,
  isBadgeBurst,
  isLikelyBadge,
  isLocked,
  operatorName,
  pushBadgeKey,
} from "../app/presentation/operatorLock";
import type { OperatorSession } from "../app/types/operator";

const session = (over: Partial<OperatorSession> = {}): OperatorSession => ({
  station: "balcao",
  operator: null,
  locked: true,
  pin_must_change: false,
  ...over,
});

describe("isLocked", () => {
  it("trava sempre que ninguém está operando", () => {
    expect(isLocked(session())).toBe(true);
    expect(
      isLocked(
        session({
          operator: { id: 1, username: "bia", name: "Bia" },
          locked: false,
        }),
      ),
    ).toBe(false);
    expect(isLocked(null)).toBe(false);
  });

  it("uma estação reconhecida NÃO destrava nada por si", () => {
    // O interruptor `require_operator` sumiu, e com ele o mundo em que a
    // superfície nunca travava. Ser o balcão diz de onde a tela fala, não que
    // alguém está autorizado nela.
    expect(isLocked(session({ station: "balcao", operator: null }))).toBe(true);
  });
});

describe("operatorName", () => {
  it("prefers the display name, falls back to username", () => {
    expect(
      operatorName(
        session({ operator: { id: 1, username: "bia", name: "Bia Forno" } }),
      ),
    ).toBe("Bia Forno");
    expect(
      operatorName(session({ operator: { id: 1, username: "bia", name: "" } })),
    ).toBe("bia");
    expect(operatorName(session())).toBe("");
  });
});

describe("isLikelyBadge", () => {
  it("reconhece o crachá de 12 hex, recusa PIN e lixo", () => {
    expect(isLikelyBadge("a1b2c3d4e5f6")).toBe(true);
    expect(isLikelyBadge("  A1B2C3D4E5F6  ")).toBe(true);
    expect(isLikelyBadge("1234")).toBe(false);
    expect(isLikelyBadge("not-hex-zzzz")).toBe(false);
    expect(isLikelyBadge("a1b2c3")).toBe(false); // curto demais
    // Comprimento antigo (24) também é recusado: o crachá encolheu por causa da
    // LARGURA DA BARRA no papel, e aceitar os dois deixaria a tela mentir sobre
    // qual token o leitor consegue ler.
    expect(isLikelyBadge("a1b2c3d4e5f6a1b2c3d4e5f6")).toBe(false);
  });
});

describe("pushBadgeKey — a janela de tempo que separa leitor de dedo", () => {
  const fast = 10; // um HID emite ~10-30ms por caractere
  const human = 400;

  it("acumula teclas rápidas na mesma passada", () => {
    let buffer = "";
    for (const char of "a1b2") buffer = pushBadgeKey(buffer, char, fast);
    expect(buffer).toBe("a1b2");
  });

  it("recomeça quando o intervalo passa da janela", () => {
    // Teclas soltas ao longo do turno não podem se somar num token falso.
    let buffer = pushBadgeKey("", "a", 0);
    buffer = pushBadgeKey(buffer, "1", human);
    expect(buffer).toBe("1");
  });

  it("uma digitação humana inteira nunca fecha um crachá", () => {
    let buffer = "";
    for (const char of "a1b2c3d4e5f6a1b2c3d4e5f6") {
      buffer = pushBadgeKey(buffer, char, human);
    }
    expect(buffer).toBe("6"); // sempre reiniciando: sobra só a última tecla
    expect(isLikelyBadge(buffer)).toBe(false);
  });

  it("a mesma sequência, na velocidade do leitor, fecha um crachá", () => {
    let buffer = "";
    for (const char of "a1b2c3d4e5f6") {
      buffer = pushBadgeKey(buffer, char, fast);
    }
    expect(isLikelyBadge(buffer)).toBe(true);
  });

  it("ignora teclas que não são conteúdo", () => {
    expect(pushBadgeKey("a1", "Shift", 0)).toBe("a1");
    expect(pushBadgeKey("a1", "ArrowLeft", 0)).toBe("a1");
    expect(pushBadgeKey("a1", "Enter", 0)).toBe("a1");
  });

  it("a borda da janela ainda conta como a mesma passada", () => {
    expect(pushBadgeKey("a", "1", BADGE_MAX_GAP_MS)).toBe("a1");
    expect(pushBadgeKey("a", "1", BADGE_MAX_GAP_MS + 1)).toBe("1");
  });
});

describe("isBadgeBurst — o que o scanner consome para não vazar", () => {
  it("continua uma rajada: já havia buffer e o intervalo coube na janela", () => {
    expect(isBadgeBurst(1, 10)).toBe(true);
    expect(isBadgeBurst(11, BADGE_MAX_GAP_MS)).toBe(true);
  });

  it("a PRIMEIRA tecla nunca é rajada (indistinguível de um dedo)", () => {
    expect(isBadgeBurst(0, 0)).toBe(false);
    expect(isBadgeBurst(0, 10)).toBe(false);
  });

  it("digitação humana (intervalo acima da janela) não é rajada", () => {
    expect(isBadgeBurst(3, BADGE_MAX_GAP_MS + 1)).toBe(false);
    expect(isBadgeBurst(1, 400)).toBe(false);
  });
});

describe("buildUnlockPayload", () => {
  it("uses the badge when present (with perm)", () => {
    expect(
      buildUnlockPayload({
        badge: " tok ",
        perm: "backstage.operate_production",
      }),
    ).toEqual({
      badge: "tok",
      perm: "backstage.operate_production",
    });
  });
  it("uses operator_id + pin otherwise", () => {
    expect(
      buildUnlockPayload({ operatorId: 7, pin: " 4321 ", perm: "p" }),
    ).toEqual({
      operator_id: 7,
      pin: "4321",
      perm: "p",
    });
  });
  it("omits perm when absent", () => {
    expect(buildUnlockPayload({ operatorId: 7, pin: "4321" })).toEqual({
      operator_id: 7,
      pin: "4321",
    });
  });
});

describe("canSubmitPin", () => {
  it("requires a picked operator and a 4+ digit pin", () => {
    expect(canSubmitPin(null, "4321")).toBe(false);
    expect(canSubmitPin(7, "12")).toBe(false);
    expect(canSubmitPin(7, "4321")).toBe(true);
  });
});

describe("appendPinDigit", () => {
  it("appends digits, ignores non-digits, caps length", () => {
    expect(appendPinDigit("12", "3")).toBe("123");
    expect(appendPinDigit("12", "a")).toBe("12");
    expect(appendPinDigit("12345678", "9")).toBe("12345678"); // capped at 8
  });
});
