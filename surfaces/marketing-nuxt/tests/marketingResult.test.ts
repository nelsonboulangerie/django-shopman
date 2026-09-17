import { describe, expect, it } from "vitest";
import {
  approvalCanaryNote,
  commandReceiptPresentation,
  deliveryCountItems,
  deliveryStatePresentation,
  marketingLoadError,
  platformDeliveryLabel,
  platformSwitchedOff,
  platformSwitchedOffNote,
  recoveryActionExplanation,
} from "~/presentation/marketingResult";
import type {
  DeliveryCountsProjectionV2,
  MarketingActionProjectionV2,
  MarketingCommandReceipt,
} from "~/types/campaign";

const emptyCounts: DeliveryCountsProjectionV2 = {
  planned: 0,
  suppressed: 0,
  queued: 0,
  sending: 0,
  accepted: 0,
  confirmed: 0,
  failed_retryable: 0,
  failed_final: 0,
  unknown: 0,
  cancelled: 0,
  expired: 0,
};

describe("Marketing result presentation", () => {
  it("never presents partial or unknown as total success", () => {
    expect(deliveryStatePresentation("completed_with_failures")).toMatchObject({
      tone: "danger",
      label: expect.stringContaining("parcial"),
    });
    expect(deliveryStatePresentation("unknown")).toMatchObject({
      tone: "attention",
      label: expect.stringContaining("não reenvie"),
    });
  });

  it("separates provider acceptance, confirmation, retryable failure and unknown", () => {
    const items = deliveryCountItems({
      ...emptyCounts,
      accepted: 2,
      confirmed: 1,
      failed_retryable: 3,
      unknown: 4,
    });

    expect(items.map((item) => `${item.count} ${item.label}`)).toEqual([
      "1 entrega confirmada",
      "2 aceitos pelo provedor; entregas ainda não confirmadas",
      "3 falhas que podem ser tentadas novamente",
      "4 resultados incertos",
    ]);
  });

  it("says a queued target of a switched-off platform waits for it, not that its turn will come", () => {
    const readiness = {
      state: "blocked" as const,
      platforms: [
        {
          platform_ref: "instagram",
          state: "blocked" as const,
          reason_code: "platform_switched_off",
          version: 1,
          checked_at: "2026-09-17T10:00:00-03:00",
          facts_as_of: null,
          fresh_until: null,
          source_status: "fresh",
        },
      ],
    };
    const counts = { ...emptyCounts, queued: 3 };

    expect(platformSwitchedOff({ readiness }, "instagram")).toBe(true);
    expect(platformSwitchedOff({ readiness }, "whatsapp")).toBe(false);
    expect(
      deliveryCountItems(counts, { platformSwitchedOff: true }).map(
        (item) => `${item.count} ${item.label}`,
      ),
    ).toEqual(["3 aguardando a plataforma ligar"]);
    expect(deliveryCountItems(counts)[0]?.label).toBe("na fila");
    expect(
      platformDeliveryLabel({ state: "delivering", counts }, true),
    ).toBe("Aguardando a plataforma ligar");
    expect(
      platformDeliveryLabel({ state: "delivering", counts }, false),
    ).toBe("Entrega em andamento");
    const note = platformSwitchedOffNote("instagram");
    expect(note).toContain("Instagram está desligado");
    expect(note).not.toMatch(/adapt|integração|credencial|erro/i);
  });

  it("explains that reconcile is lookup-only", () => {
    const action = {
      kind: "reconcile_unknown_delivery",
    } as MarketingActionProjectionV2;

    expect(recoveryActionExplanation(action)).toContain("não reenvia");
  });

  it("keeps receipt outcome explicit in the same context", () => {
    const receipt = {
      kind: "retry_delivery",
      outcome: { queued_count: 7 },
    } as MarketingCommandReceipt;

    expect(commandReceiptPresentation(receipt)).toEqual({
      title: "Nova tentativa registrada",
      detail:
        "7 falhas voltaram para a fila; nenhum destino aceito, confirmado ou incerto foi repetido.",
    });
  });

  it("says a canary approval skipped the minimum only when the receipt records it", () => {
    const canary = {
      kind: "approve",
      outcome: { audience_count: 1, canary: true, minimum_count: 3 },
    } as MarketingCommandReceipt;
    const legacyCanary = {
      kind: "approve",
      outcome: { audience_count: 1, canary: true },
    } as MarketingCommandReceipt;
    const regular = {
      kind: "approve",
      outcome: { audience_count: 12 },
    } as MarketingCommandReceipt;
    const forged = {
      kind: "approve",
      outcome: { canary: "true" },
    } as MarketingCommandReceipt;

    expect(approvalCanaryNote(canary)).toBe(
      "Ensaio: o mínimo de 3 não vale; só a lista de canário recebe.",
    );
    expect(approvalCanaryNote(legacyCanary)).toBe(
      "Ensaio: o mínimo de público não vale; só a lista de canário recebe.",
    );
    expect(approvalCanaryNote(regular)).toBe("");
    expect(approvalCanaryNote(forged)).toBe("");
  });

  it("does not disguise forbidden or service failure as not-found/empty", () => {
    expect(marketingLoadError({ statusCode: 403 }).title).toContain(
      "não tem acesso",
    );
    expect(marketingLoadError({ statusCode: 404 }).title).toContain(
      "não existe",
    );
    expect(marketingLoadError({ statusCode: 503 })).toMatchObject({
      title: "Não foi possível carregar o resultado",
      canRetry: true,
    });
  });
});
