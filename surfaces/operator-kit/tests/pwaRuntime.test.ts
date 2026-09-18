import { describe, expect, it, vi } from "vitest";
import {
  applyIdleUpdate,
  idleReloadPathAllowed,
  idleUpdateBlocker,
  shouldApplyIdleUpdate,
  shouldCheckForUpdate,
  PWA_UPDATE_CHECK_FLOOR_MS,
} from "../app/presentation/pwaRuntime";

const clean = {
  idle: true,
  needsRefresh: true,
  applying: false,
  safeToReload: true,
  holds: [] as string[],
};

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

  it('"/" é a RAIZ, não um coringa: o PDV libera a venda e nada mais', () => {
    expect(idleReloadPathAllowed(["/"], "/")).toBe(true);
    expect(idleReloadPathAllowed(["/"], "/session")).toBe(false);
    expect(idleReloadPathAllowed(["/"], "/session/closing")).toBe(false);
    expect(idleReloadPathAllowed(["/"], "/display")).toBe(false);
    expect(idleReloadPathAllowed(["/"], "/tickets")).toBe(false);
  });

  it("lista vazia nunca aplica sozinho (Central, Gestor, Compras, B.I., Marketing)", () => {
    expect(idleReloadPathAllowed([], "/")).toBe(false);
    expect(idleReloadPathAllowed([], "/campaigns")).toBe(false);
  });

  it("não confunde prefixo de palavra com prefixo de caminho", () => {
    expect(idleReloadPathAllowed(["/board"], "/boardroom")).toBe(false);
  });
});

describe("shouldCheckForUpdate", () => {
  it("sonda quando o piso entre chamadas passou", () => {
    const base = { lastCheckAt: 0, online: true, visible: true };
    expect(shouldCheckForUpdate({ ...base, now: PWA_UPDATE_CHECK_FLOOR_MS - 1 })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, now: PWA_UPDATE_CHECK_FLOOR_MS })).toBe(true);
  });

  it("não sonda offline nem com a janela fora da vista", () => {
    const base = { now: 10_000_000, lastCheckAt: 0 };
    expect(shouldCheckForUpdate({ ...base, online: false, visible: true })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, online: true, visible: false })).toBe(false);
  });

  it("relógio ajustado para trás não congela a sonda para sempre", () => {
    expect(shouldCheckForUpdate({ now: 1_000, lastCheckAt: 9_999_999, online: true, visible: true })).toBe(true);
  });
});

describe("idleUpdateBlocker", () => {
  it("nada impede com a superfície limpa e ociosa", () => {
    expect(idleUpdateBlocker(clean)).toBeNull();
    expect(shouldApplyIdleUpdate(clean)).toBe(true);
  });

  it("nomeia a razão da espera — é o que o log precisa dizer", () => {
    expect(idleUpdateBlocker({ ...clean, needsRefresh: false })).toBe("no_update");
    expect(idleUpdateBlocker({ ...clean, applying: true })).toBe("applying");
    expect(idleUpdateBlocker({ ...clean, safeToReload: false })).toBe("unsafe_route");
    expect(idleUpdateBlocker({ ...clean, holds: ["tab_open", "sale_open"] })).toBe("tab_open");
    expect(idleUpdateBlocker({ ...clean, idle: false })).toBe("busy");
  });

  it("uma razão de espera vale mesmo com a tela parada há minutos", () => {
    // O caso do PDV: comanda aberta na tela e ninguém tocando. Ocioso não é seguro.
    expect(shouldApplyIdleUpdate({ ...clean, idle: true, holds: ["tab_open"] })).toBe(false);
  });
});

describe("applyIdleUpdate", () => {
  it("não chama reload com SW esperando e kiosk ocioso nos editores de receita", async () => {
    const update = vi.fn().mockResolvedValue(true);
    const state = { allowedPaths: ["/board"], idle: true, needsRefresh: true, applying: false };

    await expect(applyIdleUpdate({ ...state, path: "/recipes/new" }, update)).resolves.toBe(false);
    await expect(applyIdleUpdate({ ...state, path: "/recipes/pao/edit" }, update)).resolves.toBe(false);
    expect(update).not.toHaveBeenCalled();
  });

  it("aplica a versão controlada quando o painel está ocioso", async () => {
    const update = vi.fn().mockResolvedValue(true);

    await expect(applyIdleUpdate({
      allowedPaths: ["/board"],
      path: "/board",
      idle: true,
      needsRefresh: true,
      applying: false,
    }, update)).resolves.toBe(true);
    expect(update).toHaveBeenCalledOnce();
  });

  it("o PDV com venda na mão não recarrega, ocioso ou não", async () => {
    const update = vi.fn().mockResolvedValue(true);
    const state = { allowedPaths: ["/"], path: "/", idle: true, needsRefresh: true, applying: false };

    await expect(applyIdleUpdate({ ...state, holds: ["sale_open"] }, update)).resolves.toBe(false);
    await expect(applyIdleUpdate({ ...state, holds: ["payment_open"] }, update)).resolves.toBe(false);
    expect(update).not.toHaveBeenCalled();

    await expect(applyIdleUpdate({ ...state, holds: [] }, update)).resolves.toBe(true);
    expect(update).toHaveBeenCalledOnce();
  });
});
