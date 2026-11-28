import { describe, expect, it, vi } from "vitest";

import { stationReadinessAlert } from "../app/presentation/stationReadiness";

// Este dispositivo pode calcular e cobrar? Sem caixa vinculado, a revisão e o
// fechamento param no servidor; a tela diz isso NA CHEGADA, não no Pagamento.
describe("stationReadinessAlert", () => {
  it("pronto, ou sem resposta do servidor: nenhum aviso", () => {
    expect(stationReadinessAlert({ ready: true, reason: "" }, () => {})).toBeNull();
    expect(stationReadinessAlert(null, () => {})).toBeNull();
    expect(stationReadinessAlert(undefined, () => {})).toBeNull();
  });

  it("sem vínculo: diz o que para e oferece vincular", () => {
    const link = vi.fn();
    const alert = stationReadinessAlert({ ready: false, reason: "none" }, link)!;
    expect(alert.color).toBe("error");
    expect(alert.title).toBe("Este dispositivo não está vinculado a um caixa.");
    expect(alert.description).toContain("o total e a cobrança");
    expect(alert.action?.label).toBe("Vincular a um caixa");
    alert.action?.onSelect?.(new Event("click"));
    expect(link).toHaveBeenCalledTimes(1);
  });

  it("cada causa tem a sua frase e o seu id (o aviso volta quando a causa muda)", () => {
    const ambiguous = stationReadinessAlert({ ready: false, reason: "ambiguous" }, () => {})!;
    const inactive = stationReadinessAlert({ ready: false, reason: "inactive" }, () => {})!;
    expect(ambiguous.title).toContain("mais de um caixa");
    expect(inactive.title).toContain("não é um caixa ativo");
    expect(new Set([ambiguous.id, inactive.id]).size).toBe(2);
  });

  it("copy sem travessão", () => {
    for (const reason of ["none", "ambiguous", "inactive"] as const) {
      const alert = stationReadinessAlert({ ready: false, reason }, () => {})!;
      expect(`${alert.title} ${alert.description}`).not.toMatch(/[—–]/);
    }
  });
});
