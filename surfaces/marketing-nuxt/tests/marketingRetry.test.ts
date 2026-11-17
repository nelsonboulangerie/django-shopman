import { describe, expect, it } from "vitest";
import { marketingThrottleMessage } from "~/utils/marketingRetry";

const now = new Date("2026-09-11T14:05:00Z");
const timezone = "America/Sao_Paulo";

describe("espera legível do Marketing", () => {
  it.each([
    [1, "em cerca de 1 segundo, às 11h05"],
    [75, "em cerca de 75 segundos, às 11h06"],
    [120, "em cerca de 2 minutos, às 11h07"],
    [2_386, "em cerca de 40 minutos, às 11h44"],
    [7_200, "em cerca de 2 horas, às 13h05"],
    [10_000, "em cerca de 3 horas, às 13h51"],
  ])("adapta %i segundos à escala humana", (seconds, expected) => {
    expect(marketingThrottleMessage(seconds, timezone, now)).toContain(
      expected,
    );
  });

  it("explica a causa e garante que não houve criação", () => {
    expect(marketingThrottleMessage(2_386, timezone, now)).toBe(
      "Muitas tentativas em pouco tempo. Tente novamente em cerca de 40 minutos, às 11h44. Nada foi criado.",
    );
  });
});
