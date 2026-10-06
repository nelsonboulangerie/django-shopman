import { describe, expect, it } from "vitest";

import { operatorSurfaceGate } from "../../app/utils/operatorSurfaceGate";

const base = {
  canIdentify: false,
  sessionUnavailable: false,
  locked: false,
  mustChange: false,
  harness: false,
};

describe("operatorSurfaceGate", () => {
  it("mostra a página só quando autenticado (ou no harness hermético)", () => {
    expect(operatorSurfaceGate({ ...base, sessionState: "authenticated", canIdentify: true }).showPage).toBe(true);
    expect(operatorSurfaceGate({ ...base, sessionState: "forbidden", canIdentify: true }).showPage).toBe(false);
    expect(operatorSurfaceGate({ ...base, sessionState: "checking" }).showPage).toBe(false);
    expect(operatorSurfaceGate({ ...base, sessionState: "anonymous" }).showPage).toBe(false);
    expect(operatorSurfaceGate({ ...base, sessionState: "checking", harness: true }).showPage).toBe(true);
  });

  it("mostra permissão insuficiente sem oferecer login nem página", () => {
    const gate = operatorSurfaceGate({ ...base, sessionState: "forbidden", canIdentify: true });
    expect(gate.showForbidden).toBe(true);
    expect(gate.showLogin).toBe(false);
    expect(gate.showLock).toBe(false);
    expect(gate.showPage).toBe(false);
  });

  it("em checking mostra o esqueleto e NÃO a tela de senha", () => {
    const gate = operatorSurfaceGate({ ...base, sessionState: "checking" });
    expect(gate.showChecking).toBe(true);
    expect(gate.showLogin).toBe(false);
  });

  it("anônimo sem antessala pede a tela de senha, não o esqueleto", () => {
    const gate = operatorSurfaceGate({ ...base, sessionState: "anonymous" });
    expect(gate.showLogin).toBe(true);
    expect(gate.showChecking).toBe(false);
    expect(gate.showPage).toBe(false);
  });

  it("operador identificado e travado vê o PIN, nunca a página", () => {
    const locked = operatorSurfaceGate({ ...base, sessionState: "authenticated", canIdentify: true, locked: true });
    expect(locked.showLock).toBe(true);
    expect(locked.showPage).toBe(false);
    const mustChange = operatorSurfaceGate({ ...base, sessionState: "authenticated", canIdentify: true, mustChange: true });
    expect(mustChange.showLock).toBe(true);
  });

  it("sessão expirada e identificada volta para o PIN; sem identificação, para a senha", () => {
    expect(operatorSurfaceGate({ ...base, sessionState: "expired", canIdentify: true }).showLock).toBe(true);
    expect(operatorSurfaceGate({ ...base, sessionState: "expired", canIdentify: false }).showLogin).toBe(true);
  });

  it("erro de rede vira indisponível, sem pedir senha e sem página", () => {
    const gate = operatorSurfaceGate({ ...base, sessionState: "anonymous", sessionUnavailable: true });
    expect(gate.showUnavailable).toBe(true);
    expect(gate.showLogin).toBe(false);
    expect(gate.showPage).toBe(false);
  });
});
