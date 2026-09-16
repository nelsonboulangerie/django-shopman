import { describe, expect, it } from "vitest";
import { shouldApplyKioskUpdate } from "../app/presentation/pwaRuntime";

describe("shouldApplyKioskUpdate", () => {
  it("espera o kiosk ficar ocioso antes de aplicar a versão", () => {
    expect(shouldApplyKioskUpdate({ idle: false, needsRefresh: true, applying: false })).toBe(false);
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: true, applying: false })).toBe(true);
  });

  it("não reaplica nem atualiza sem worker em espera", () => {
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: false, applying: false })).toBe(false);
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: true, applying: true })).toBe(false);
  });
});
