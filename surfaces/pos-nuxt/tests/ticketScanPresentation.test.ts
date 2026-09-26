import { describe, expect, it } from "vitest";

import {
  EMPTY_SCAN,
  SCAN_KEY_GAP_MAX_MS,
  scanKey,
  scanTimeout,
  type ScanState,
  type ScanStep,
} from "~/presentation/ticketScan";

const CODE = "KT-1234-ABCDEFGHIJ";

/** Alimenta uma sequência de teclas com o mesmo intervalo; devolve os passos. */
function feed(keys: string[], gapMs: number, start: ScanState = EMPTY_SCAN): { steps: ScanStep[]; state: ScanState } {
  let state = start;
  const steps: ScanStep[] = [];
  keys.forEach((key, index) => {
    const result = scanKey(state, key, index === 0 && !state.buffer ? Number.POSITIVE_INFINITY : gapMs);
    state = result.state;
    steps.push(result.step);
  });
  return { steps, state };
}

describe("leitor de código da Via Cozinha — rajada de máquina", () => {
  it("o código lido em rajada fecha no Enter, e nada vai para o campo", () => {
    const { steps } = feed([...CODE, "Enter"], 15);
    expect(steps.slice(0, -1).every((step) => step.kind === "hold")).toBe(true);
    expect(steps.at(-1)).toEqual({ kind: "code", code: CODE });
  });

  it("leitor com Caps Lock trocado (minúsculas) também vale", () => {
    const { steps } = feed([..."kt-1234-abcdefghij", "Enter"], 15);
    expect(steps.at(-1)).toEqual({ kind: "code", code: CODE });
  });

  it("a tecla Shift que o leitor aperta para a maiúscula não atrapalha", () => {
    let state = EMPTY_SCAN;
    const steps: ScanStep[] = [];
    for (const key of ["Shift", ...CODE, "Enter"]) {
      const result = scanKey(state, key, 10);
      state = result.state;
      steps.push(result.step);
    }
    expect(steps[0]).toEqual({ kind: "pass" });
    expect(steps.at(-1)).toEqual({ kind: "code", code: CODE });
  });

  it("rajada KT- que não é um código assinado vira aviso, não texto no campo", () => {
    const { steps } = feed([..."KT-12", "Enter"], 15);
    expect(steps.at(-1)).toEqual({ kind: "invalid", text: "KT-12" });
  });
});

describe("leitor de código da Via Cozinha — o dedo nunca perde letra", () => {
  it("tecla que não começa código passa direto", () => {
    expect(scanKey(EMPTY_SCAN, "a", Number.POSITIVE_INFINITY).step).toEqual({ kind: "pass" });
  });

  it("'K' seguido de outra letra devolve o K antes da letra seguir", () => {
    const { steps, state } = feed(["K", "a"], 15);
    expect(steps).toEqual([{ kind: "hold" }, { kind: "release", text: "K" }]);
    expect(state).toEqual(EMPTY_SCAN);
  });

  it("'KT' digitado devagar é dedo: devolve na tecla lenta", () => {
    const { steps } = feed(["K", "T"], SCAN_KEY_GAP_MAX_MS + 1);
    expect(steps).toEqual([{ kind: "hold" }, { kind: "release", text: "K" }]);
  });

  it("'K' e silêncio: o timer devolve a letra ao campo", () => {
    const { state } = feed(["K"], 15);
    expect(scanTimeout(state)).toEqual({ state: EMPTY_SCAN, release: "K" });
  });

  it("Enter depois de 'KT' sem hífen é de gente: devolve e deixa o Enter seguir", () => {
    const { steps } = feed(["K", "T", "Enter"], 15);
    expect(steps.at(-1)).toEqual({ kind: "release", text: "KT" });
  });

  it("leitura começada e largada sem Enter não despeja 'KT-12' no campo", () => {
    const { state } = feed([..."KT-12"], 15);
    expect(scanTimeout(state)).toEqual({ state: EMPTY_SCAN, release: "" });
  });

  it("rajada longa demais não é código nosso", () => {
    const { steps } = feed([..."KT-" + "1".repeat(40)], 10);
    expect(steps.some((step) => step.kind === "invalid")).toBe(true);
  });
});
