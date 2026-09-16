import { describe, expect, it } from "vitest";
import { applyKioskUpdate, idleReloadPathAllowed, shouldApplyKioskUpdate } from "../app/presentation/pwaRuntime";

describe("idleReloadPathAllowed", () => {
  it("libera todo o KDS quando a capability declara wildcard", () => {
    expect(idleReloadPathAllowed(["*"], "/stations/oven")).toBe(true);
  });

  it("libera somente o painel da Produção e preserva editores de receita", () => {
    expect(idleReloadPathAllowed(["/board"], "/board")).toBe(true);
    expect(idleReloadPathAllowed(["/board"], "/board/today")).toBe(true);
    expect(idleReloadPathAllowed(["/board"], "/recipes/new")).toBe(false);
    expect(idleReloadPathAllowed(["/board"], "/recipes/pao/edit")).toBe(false);
  });
});

describe("shouldApplyKioskUpdate", () => {
  it("espera o kiosk ficar ocioso antes de aplicar a versão", () => {
    expect(shouldApplyKioskUpdate({ idle: false, needsRefresh: true, applying: false, safeToReload: true })).toBe(false);
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: true, applying: false, safeToReload: true })).toBe(true);
  });

  it("não reaplica nem atualiza sem worker em espera", () => {
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: false, applying: false, safeToReload: true })).toBe(false);
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: true, applying: true, safeToReload: true })).toBe(false);
  });

  it("preserva rascunhos quando a rota não autorizou recarga", () => {
    expect(shouldApplyKioskUpdate({ idle: true, needsRefresh: true, applying: false, safeToReload: false })).toBe(false);
  });
});

describe("applyKioskUpdate", () => {
  it("não chama reload com SW esperando e kiosk ocioso nos editores de receita", async () => {
    const update = vi.fn().mockResolvedValue(true);
    const state = { allowedPaths: ["/board"], idle: true, needsRefresh: true, applying: false };

    await expect(applyKioskUpdate({ ...state, path: "/recipes/new" }, update)).resolves.toBe(false);
    await expect(applyKioskUpdate({ ...state, path: "/recipes/pao/edit" }, update)).resolves.toBe(false);
    expect(update).not.toHaveBeenCalled();
  });

  it("aplica a versão controlada quando o painel está ocioso", async () => {
    const update = vi.fn().mockResolvedValue(true);

    await expect(applyKioskUpdate({
      allowedPaths: ["/board"],
      path: "/board",
      idle: true,
      needsRefresh: true,
      applying: false,
    }, update)).resolves.toBe(true);
    expect(update).toHaveBeenCalledOnce();
  });
});
