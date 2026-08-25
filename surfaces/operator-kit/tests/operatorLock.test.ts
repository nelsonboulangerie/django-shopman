import { describe, expect, it } from "vitest";

import {
  type CapturedKey,
  MACHINE_MEDIAN_MAX_MS,
  PIN_MAX_DIGITS,
  appendPinDigit,
  backspaceCapture,
  buildUnlockPayload,
  canSubmitPin,
  captureKey,
  capturedPin,
  isCaptureKey,
  isLikelyBadge,
  isLocked,
  operatorName,
  resolveEnter,
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

// ── A captura unificada: um buffer, decisão no Enter ────────────────────────

const BADGE = "a1b2c3d4e5f6";

/** Monta um buffer digitando `chars` com o MESMO intervalo entre todas. */
function typed(
  chars: string,
  gapMs: number,
  pinEligible = true,
  base: readonly CapturedKey[] = [],
): readonly CapturedKey[] {
  let keys = base;
  for (const char of chars) {
    keys = captureKey(keys, char, keys.length === 0 ? 0 : gapMs, pinEligible);
  }
  return keys;
}

const MACHINE = 15; // um HID emite ~10-30ms por caractere
const FAST_HUMAN = 80; // digitador ágil: 60-110ms
const SLOW_HUMAN = 250;

describe("isCaptureKey — o que entra no buffer", () => {
  it("aceita dígito e hex, recusa o resto", () => {
    expect(isCaptureKey("7")).toBe(true);
    expect(isCaptureKey("a")).toBe(true);
    expect(isCaptureKey("F")).toBe(true);
    expect(isCaptureKey("x")).toBe(false);
    expect(isCaptureKey(" ")).toBe(false);
    expect(isCaptureKey("Shift")).toBe(false);
    expect(isCaptureKey("Enter")).toBe(false);
    expect(isCaptureKey("ArrowLeft")).toBe(false);
  });
});

describe("captureKey / capturedPin — toda entrada entra na hora", () => {
  it("nenhum dígito é descartado na chegada, seja qual for a cadência", () => {
    expect(capturedPin(typed("1234", MACHINE))).toBe("1234");
    expect(capturedPin(typed("1234", FAST_HUMAN))).toBe("1234");
    expect(capturedPin(typed("1234", SLOW_HUMAN))).toBe("1234");
  });

  it("letra de crachá fica no buffer sem virar bolinha de PIN", () => {
    const keys = typed("a1b2", MACHINE);
    expect(keys.map((k) => k.char).join("")).toBe("a1b2");
    expect(capturedPin(keys)).toBe("12");
  });

  it("dígito fora do pad (ou dentro de um campo de texto) não vira PIN", () => {
    expect(capturedPin(typed("1234", FAST_HUMAN, false))).toBe("");
  });

  it("o PIN visível para no teto; o buffer segue aceitando", () => {
    const keys = typed("123456789", FAST_HUMAN);
    expect(capturedPin(keys)).toHaveLength(PIN_MAX_DIGITS);
    expect(keys).toHaveLength(9);
  });

  it("tecla que não é conteúdo não entra", () => {
    expect(captureKey([], "Shift", 0, true)).toHaveLength(0);
    expect(captureKey([], "x", 0, true)).toHaveLength(0);
  });
});

describe("backspaceCapture", () => {
  it("remove o último dígito visível", () => {
    expect(capturedPin(backspaceCapture(typed("1234", FAST_HUMAN)))).toBe("123");
  });

  it("leva junto o que chegou depois dele (letra invisível não sobra atrás)", () => {
    const keys = typed("ab", MACHINE, true, typed("12", FAST_HUMAN));
    expect(capturedPin(backspaceCapture(keys))).toBe("1");
  });

  it("sem dígito visível, não mexe", () => {
    const keys = typed("ab", MACHINE);
    expect(backspaceCapture(keys)).toEqual(keys);
  });
});

describe("resolveEnter — a decisão crachá×gente fica para o Enter", () => {
  it("rajada de leitor (cadência de máquina) fecha o crachá", () => {
    const resolved = resolveEnter(typed(BADGE, MACHINE), MACHINE);
    expect(resolved).toMatchObject({ kind: "badge", token: BADGE });
  });

  it("digitador RÁPIDO (60-110ms) nunca é classificado como crachá", () => {
    // O achado do balcão: 60-110ms é cadência normal de digitador ágil. Era
    // exatamente essa faixa que caía na janela antiga e perdia dígito.
    for (const gap of [60, 80, 110]) {
      expect(resolveEnter(typed(BADGE, gap), gap)).toEqual({ kind: "human" });
    }
  });

  it("digitador lento é gente, óbvio", () => {
    expect(resolveEnter(typed(BADGE, SLOW_HUMAN), SLOW_HUMAN)).toEqual({ kind: "human" });
  });

  it("menos teclas que um crachá é gente", () => {
    expect(resolveEnter(typed("1234", MACHINE), MACHINE)).toEqual({ kind: "human" });
  });

  it("rajada de crachá NO MEIO da digitação do PIN: token sai, PIN fica", () => {
    // A pessoa digitou dois dígitos, o leitor cuspiu o token por cima.
    const keys = typed(BADGE, MACHINE, true, typed("12", FAST_HUMAN));
    const resolved = resolveEnter(keys, MACHINE);
    expect(resolved).toMatchObject({ kind: "badge", token: BADGE });
    if (resolved.kind === "badge") {
      // Os dígitos do token que chegaram a virar bolinha somem; os da pessoa ficam.
      expect(capturedPin(resolved.keys)).toBe("12");
    }
  });

  it("cliques em sequência rápida nunca fecham crachá, nem com 12 dígitos", () => {
    // Toque de dedo no pad entra com o relógio de verdade (~150ms+): mesmo um
    // token só-de-dígitos (possível em `token_hex`) não fecha por clique.
    const keys = typed("123456789012", 150);
    expect(resolveEnter(keys, 150)).toEqual({ kind: "human" });
  });

  it("um soluço de USB no meio da rajada não derruba a leitura (mediana)", () => {
    let keys = typed(BADGE.slice(0, 6), MACHINE);
    keys = captureKey(keys, BADGE[6]!, 90, true); // o agendador engasgou UMA vez
    keys = typed(BADGE.slice(7), MACHINE, true, keys);
    const resolved = resolveEnter(keys, MACHINE);
    expect(resolved).toMatchObject({ kind: "badge", token: BADGE });
  });

  it("Enter atrasado depois de um rabo de máquina pesa contra o crachá, mas um só não vira o jogo", () => {
    // A mediana absorve UM intervalo fora da curva — seja soluço de USB, seja o
    // Enter chegando tarde. O que decide é o corpo da passada.
    const resolved = resolveEnter(typed(BADGE, MACHINE), MACHINE_MEDIAN_MAX_MS * 10);
    expect(resolved).toMatchObject({ kind: "badge", token: BADGE });
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
