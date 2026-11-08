// Achados do beta test de 05/11/2026 na frente do Marketing, travados na camada pura.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { reviewCapabilityBlock } from "~/presentation/marketingResult";
import { campaignOfferLabel, campaignOfferWarning, offerCampaignNote } from "~/presentation/offers";
import { quietHoursOutlastDeadline } from "~/utils/marketingSchedule";
import type { MarketingActionProjectionV2 } from "~/types/campaign";

function action(
  kind: MarketingActionProjectionV2["kind"],
  reason = "",
): MarketingActionProjectionV2 {
  return {
    ref: `announcement:1:${kind}:v1`,
    resource_ref: "announcement:1",
    kind,
    label: kind,
    priority: "secondary",
    enabled: !reason,
    reason,
    href: "",
    method: "POST",
    payload_schema: "",
    idempotency: "required",
    confirmation: {
      mode: "simple",
      token_required: false,
      phrase: "",
      threshold: 0,
      expires_at: null,
      consequence: "",
      token: "",
    } as unknown as MarketingActionProjectionV2["confirmation"],
    eligible_count: 0,
    required_capabilities: [],
    creates_external_effect: false,
  };
}

describe("ge:MKT-03: quem não aprova não recebe o gesto de aprovar", () => {
  it("sem capacidade, Recusar e Continuar vêm travados com uma frase com saída", () => {
    const block = reviewCapabilityBlock([
      action("publish_announcement_now", "missing_capability"),
      action("schedule_announcement", "missing_capability"),
      action("reject_announcement", "missing_capability"),
    ]);
    expect(block).toEqual({
      reject: "Seu perfil não aprova anúncios. Peça a quem aprova.",
      proceed: "Seu perfil não aprova anúncios. Peça a quem aprova.",
    });
  });

  it("aprova mas não publica: recusa livre, Continuar travado", () => {
    const block = reviewCapabilityBlock([
      action("publish_announcement_now", "missing_capability"),
      action("schedule_announcement", "missing_capability"),
      action("reject_announcement"),
    ]);
    expect(block.reject).toBe("");
    expect(block.proceed).toBe("Seu perfil não publica anúncios. Peça a quem publica.");
  });

  it("outros motivos (silêncio, prazo) ficam com o cartão, não com a capacidade", () => {
    expect(
      reviewCapabilityBlock([
        action("publish_announcement_now", "quiet_hours"),
        action("schedule_announcement"),
        action("reject_announcement"),
      ]),
    ).toEqual({ reject: "", proceed: "" });
  });
});

describe("ge:MKT-07: silêncio do WhatsApp contra o prazo do anúncio", () => {
  const zone = "America/Sao_Paulo";

  it("às 07:21 com prazo às 07:45, as 08:00 já vencem: devolve a hora do prazo", () => {
    expect(
      quietHoursOutlastDeadline({
        timeZone: zone,
        expiresAt: "2026-11-05T07:45:00-03:00",
        nowMs: Date.parse("2026-11-05T07:21:00-03:00"),
      }),
    ).toBe("07:45");
  });

  it("prazo depois das 08:00: agendar resolve, então não cruza", () => {
    expect(
      quietHoursOutlastDeadline({
        timeZone: zone,
        expiresAt: "2026-11-05T09:00:00-03:00",
        nowMs: Date.parse("2026-11-05T07:21:00-03:00"),
      }),
    ).toBe("");
  });

  it("fora do silêncio não cruza", () => {
    expect(
      quietHoursOutlastDeadline({
        timeZone: zone,
        expiresAt: "2026-11-05T10:00:00-03:00",
        nowMs: Date.parse("2026-11-05T09:21:00-03:00"),
      }),
    ).toBe("");
  });
});

function source(path: string): string {
  return readFileSync(new URL(`../app/${path}`, import.meta.url), "utf8");
}

describe("ge:MKT-25: o cartão da oferta diz por que não vai numa campanha", () => {
  const base = {
    available_for_campaign: false,
    status: "live" as const,
    skus: [] as string[],
    collections: [] as string[],
  };

  it("cada falta tem a sua frase, com o que mudar", () => {
    expect(offerCampaignNote({ ...base, available_for_campaign: true, skus: ["CRO"] })).toBe(
      "Pode ir numa campanha.",
    );
    expect(offerCampaignNote(base)).toBe(
      "Vale para o catálogo todo; campanha pede produto ou coleção.",
    );
    expect(offerCampaignNote({ ...base, status: "scheduled" })).toBe(
      "Só vai numa campanha quando entrar em vigor.",
    );
    expect(offerCampaignNote({ ...base, status: "expired" })).toBe(
      "Fora de vigor: campanha só leva oferta em vigor.",
    );
    expect(offerCampaignNote({ ...base, collections: ["vazia"] })).toBe(
      "As coleções desta oferta estão sem produtos.",
    );
  });

  it("a frase vaga saiu da tela", () => {
    expect(source("pages/settings/offers.vue")).not.toContain("Regra comercial cadastrada");
  });
});

describe("ge:MKT-28: restos visuais do assistente e dos diálogos", () => {
  it("a etapa Revisar não fala em criar quando é edição", () => {
    expect(source("components/CampaignForm.vue")).toContain(
      '{ label: "Revisar", hint: "Confira o que será salvo." }',
    );
  });

  it("o diálogo guarda o título e o modelo enquanto fecha", () => {
    const campaigns = source("pages/settings/campaigns.vue");
    expect(campaigns).toContain(':title="dialogTitle"');
    expect(campaigns).not.toContain(":title=\"editing ? 'Editar campanha' : 'Nova campanha'\"");
    const templates = source("pages/settings/templates.vue");
    expect(templates).toContain("Apagar “${shownRemoval?.name ?? ''}”?");
    expect(templates).not.toContain("${removing?.name}");
  });
});

describe("ge:MKT-29: Agendados vazio fala uma vez", () => {
  it("o cabeçalho só aparece quando há agendado; vazio é do estado vazio", () => {
    expect(source("pages/scheduled.vue")).toContain('v-if="queue && scheduled.length"');
  });
});

describe("ge:MKT-04: nome com limite no campo", () => {
  it("campanha e modelo limitam o nome a 100, como o banco", () => {
    expect(source("components/CampaignForm.vue")).toMatch(/id="rule-name"[\s\S]{0,80}:maxlength="100"/);
    expect(source("components/AnnouncementTemplateForm.vue")).toMatch(
      /id="tpl-name"[\s\S]{0,80}:maxlength="100"/,
    );
  });
});


describe("campanha ligada não implica oferta pronta", () => {
  const offers = [{ value: "live", label: "Oferta vigente" }];
  it("separa ausência de oferta de referência indisponível sem alterar o cadastro", () => {
    expect(campaignOfferLabel("", offers)).toBe("Sem oferta");
    expect(campaignOfferLabel("live", offers)).toBe("Oferta vigente");
    expect(campaignOfferLabel("old", offers)).toBe("Oferta indisponível (old)");
    expect(campaignOfferWarning("live", offers)).toBe("");
    expect(campaignOfferWarning("", offers)).toBe("");
    expect(campaignOfferWarning("old", offers)).toContain("Revise em Ofertas");
  });
});
