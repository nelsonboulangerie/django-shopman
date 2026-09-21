import { describe, expect, it } from "vitest";

import { closeGuardNotice, closeGuardSituation, type CloseGuardInput } from "~/presentation/closeGuard";

const base: CloseGuardInput = {
  blocked: true,
  inFlightHere: false,
  pending: false,
  heldElsewhere: false,
  browserFailure: "",
};

describe("closeGuard — o aviso da trava contra cobrança duplicada", () => {
  it("sem trava, nada a avisar", () => {
    expect(closeGuardNotice({ ...base, blocked: false })).toBeNull();
  });

  it("a cobrança em voo desta aba é o caminho feliz, não aviso", () => {
    expect(closeGuardSituation({ ...base, pending: true, inFlightHere: true })).toBe("none");
  });

  it("outra aba cobrando: esperar, sem botão de liberar", () => {
    const notice = closeGuardNotice({ ...base, pending: true, heldElsewhere: true });
    expect(notice?.situation).toBe("other_tab_charging");
    expect(notice?.canRelease).toBe(false);
  });

  it("pending sem dono vivo é venda interrompida", () => {
    expect(closeGuardSituation({ ...base, pending: true })).toBe("interrupted");
  });

  it("resposta sem prova é resultado não confirmado", () => {
    expect(closeGuardNotice(base)?.title).toBe("Resultado da cobrança não confirmado");
  });

  it("falha do navegador diz a falha, não 'resultado não confirmado'", () => {
    const notice = closeGuardNotice({ ...base, browserFailure: "Este navegador não conseguiu ativar a proteção." });
    expect(notice?.situation).toBe("browser_unavailable");
    expect(notice?.body).toBe("Este navegador não conseguiu ativar a proteção.");
  });

  it("nenhum título obriga o operador a escolher entre duas leituras", () => {
    const inputs: CloseGuardInput[] = [
      { ...base, pending: true, heldElsewhere: true },
      { ...base, pending: true },
      base,
      { ...base, browserFailure: "x" },
    ];
    for (const input of inputs) {
      const notice = closeGuardNotice(input)!;
      expect(notice.title).not.toMatch(/\bou\b/);
    }
  });
});
