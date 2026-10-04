import { describe, expect, it } from "vitest";

import { scheduledSummaryParts } from "~/presentation/decisions";
import { marketingLiveStatus, readTime } from "~/presentation/liveStatus";
import { sealConsequence, sealRows } from "~/presentation/marketingDelivery";

// O que a camada visual da suíte (V4-MKT) acrescentou de frase: o "ao vivo" do
// cabeçalho, as colunas do selo e a linha de agendados em duas partes.

describe("ao vivo do cabeçalho", () => {
  const base = { generatedAt: "2026-10-03T10:03:00-03:00", timeZone: "America/Sao_Paulo" };

  it("ao vivo é só o ponto e a hora da leitura, no fuso da loja", () => {
    expect(readTime(base.generatedAt, base.timeZone)).toBe("10:03");
    expect(marketingLiveStatus({ ...base, realtime: "live", failed: false })).toMatchObject({
      tone: "live",
      time: "10:03",
    });
  });

  it("sem o aviso imediato, diz por extenso que a tela confere sozinha", () => {
    expect(marketingLiveStatus({ ...base, realtime: "polling", failed: false })).toMatchObject({
      tone: "calm",
      label: "Atualiza a cada 1 min",
    });
  });

  it("leitura que falhou não se passa por ao vivo", () => {
    const status = marketingLiveStatus({ ...base, realtime: "live", failed: true });
    expect(status.tone).toBe("off");
    expect(status.label).toBe("Sem conexão");
    expect(status.detail).toContain("10:03");
  });

  it("sem leitura, sem hora inventada", () => {
    expect(readTime(null, base.timeZone)).toBe("");
  });
});

describe("o selo", () => {
  it("uma linha por destino, cada uma na sua grandeza, murais antes da mensagem", () => {
    expect(
      sealRows({ platforms: ["whatsapp", "instagram", "facebook"], audienceCount: 86 }),
    ).toEqual([
      { platform: "instagram", label: "Instagram", kind: "", amount: "1 postagem", strong: false },
      { platform: "facebook", label: "Facebook", kind: "", amount: "1 postagem", strong: false },
      {
        platform: "whatsapp",
        label: "WhatsApp",
        kind: "mensagem direta",
        amount: "86 pessoas",
        strong: true,
      },
    ]);
    expect(sealRows({ platforms: ["whatsapp"], audienceCount: 1 })[0]!.amount).toBe("1 pessoa");
  });

  it("separa o que volta (postagem) do que não volta (mensagem)", () => {
    expect(sealConsequence(["instagram", "whatsapp"])).toBe(
      "Mensagem enviada não volta. Postagem pode ser apagada depois, na plataforma.",
    );
    expect(sealConsequence(["whatsapp"])).toBe("Mensagem enviada não volta.");
    expect(sealConsequence(["google_business"])).toBe(
      "Postagem pode ser apagada depois, na plataforma.",
    );
    expect(sealConsequence([])).toBe("");
  });
});

describe("linha de agendados da fila", () => {
  it("o número forte separado do resto, sem mudar a frase", () => {
    expect(scheduledSummaryParts(2, 3)).toEqual({
      lead: "+2",
      rest: "agendados hoje · 3 campanhas ligadas",
    });
    expect(scheduledSummaryParts(0, 1)).toEqual({
      lead: "",
      rest: "Nenhum agendado hoje · 1 campanha ligada",
    });
  });
});
