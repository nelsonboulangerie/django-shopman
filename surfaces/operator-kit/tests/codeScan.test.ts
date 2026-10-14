import { describe, expect, it } from "vitest";

import { EMPTY_SCAN, SCAN_KEY_GAP_MAX_MS, scanKey, scanTimeout, type CodeFormat, type ScanState } from "../app/presentation/codeScan";

// O leitor (modo teclado) com o prefixo como parâmetro: a rajada de máquina
// vira código; o dedo que digita a mesma letra recebe a letra de volta.

const FORMAT: CodeFormat = { prefix: "VP-", pattern: /^VP-.+-\d{1,2}-\d{1,2}-[A-Z2-7]{8}$/, maxLength: 96 };
const CODE = "VP-WEB-20261013-U68-2-3-ABCDEFGH";

function feed(keys: string[], gap = 5) {
  let state: ScanState = EMPTY_SCAN;
  const steps = [];
  for (const key of keys) {
    const out = scanKey(FORMAT, state, key, state.buffer ? gap : Number.POSITIVE_INFINITY);
    state = out.state;
    steps.push(out.step);
  }
  return { state, steps };
}

describe("codeScan", () => {
  it("rajada de máquina com o prefixo e Enter vira o código, em maiúsculas", () => {
    const { steps } = feed([...CODE.toLowerCase(), "Enter"]);
    expect(steps.at(-1)).toEqual({ kind: "code", code: CODE });
    expect(steps.slice(0, -1).every((step) => step.kind === "hold")).toBe(true);
  });

  it("dedo que digita V e para recebe a letra de volta", () => {
    const first = scanKey(FORMAT, EMPTY_SCAN, "V", Number.POSITIVE_INFINITY);
    expect(first.step.kind).toBe("hold");
    const slow = scanKey(FORMAT, first.state, "a", SCAN_KEY_GAP_MAX_MS + 1);
    expect(slow.step).toEqual({ kind: "release", text: "V" });
    expect(scanTimeout(FORMAT, first.state).release).toBe("V");
  });

  it("palavra que começa com V mas não é o prefixo devolve o retido", () => {
    const { steps } = feed(["V", "e"]);
    expect(steps.at(-1)).toEqual({ kind: "release", text: "V" });
  });

  it("rajada com o prefixo fora do formato é inválida, e o silêncio a descarta", () => {
    expect(feed([..."VP-XYZ", "Enter"]).steps.at(-1)).toEqual({ kind: "invalid", text: "VP-XYZ" });
    expect(scanTimeout(FORMAT, { buffer: "VP-12" }).release).toBe("");
  });

  it("teclas de controle passam", () => {
    expect(scanKey(FORMAT, EMPTY_SCAN, "Shift", Number.POSITIVE_INFINITY).step).toEqual({ kind: "pass" });
  });
});
