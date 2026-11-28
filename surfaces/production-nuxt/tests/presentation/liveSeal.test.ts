import { describe, expect, it, vi } from "vitest";
import { productionLiveSeal, staleReadAlert } from "~/presentation/liveSeal";

describe("productionLiveSeal — 'Ao vivo' só onde é verdade (WP-F15, P1-17)", () => {
  it("canal aberto: Ao vivo", () => {
    expect(productionLiveSeal({ stale: false, realtime: "live", pollMs: 30_000 })).toMatchObject({
      tone: "live",
      label: "Ao vivo",
    });
  });

  it("canal caído ou abrindo: diz a cadência, nunca Ao vivo", () => {
    for (const realtime of ["polling", "connecting"] as const) {
      const seal = productionLiveSeal({ stale: false, realtime, pollMs: 30_000 });
      expect(seal.tone).toBe("calm");
      expect(seal.label).toBe("Atualiza sozinho a cada 30 s");
      expect(seal.shortLabel).toBe("A cada 30 s");
    }
  });

  it("Django parado sem dado na tela: Sem conexão, mesmo com o canal tendo estado aberto", () => {
    expect(productionLiveSeal({ stale: false, offline: true, realtime: "live" })).toMatchObject({
      tone: "off",
      label: "Sem conexão",
    });
  });

  it("dado velho na tela: Sem atualizar", () => {
    expect(productionLiveSeal({ stale: true, realtime: "live" })).toMatchObject({
      tone: "late",
      label: "Sem atualizar",
    });
  });

  it("a tela que não declara o tempo real segue no Ao vivo de antes (a grade)", () => {
    expect(productionLiveSeal({ stale: false }).label).toBe("Ao vivo");
  });

  it("nenhum texto do selo usa travessão", () => {
    const seals = [
      productionLiveSeal({ stale: false, offline: true }),
      productionLiveSeal({ stale: true }),
      productionLiveSeal({ stale: false, realtime: "polling", pollMs: 60_000 }),
    ];
    for (const seal of seals) expect(`${seal.label} ${seal.shortLabel} ${seal.detail}`).not.toMatch(/[—–]/);
  });
});

describe("staleReadAlert — dado velho nos avisos do cabeçalho (P2-07)", () => {
  it("é um aviso do kit, com a saída que resolve: Tentar de novo relê", () => {
    const retry = vi.fn();
    const alert = staleReadAlert("os lotes", retry, "Confira antes de fechar.");
    expect(alert).toMatchObject({
      id: "stale-read",
      color: "warning",
      title: "Sem atualizar: a tela mostra os lotes da última leitura",
      description: "Confira antes de fechar.",
    });
    expect(alert.action?.label).toBe("Tentar de novo");
    alert.action?.onSelect?.(new Event("click"));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
