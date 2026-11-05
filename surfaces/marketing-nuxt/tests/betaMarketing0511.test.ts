// Achados do beta test de 05/11/2026 na frente do Marketing, travados na camada pura.
import { describe, expect, it } from "vitest";
import { reviewCapabilityBlock } from "~/presentation/marketingResult";
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

describe("ge:MKT-03 — quem não aprova não recebe o gesto de aprovar", () => {
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

describe("ge:MKT-07 — silêncio do WhatsApp contra o prazo do anúncio", () => {
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
