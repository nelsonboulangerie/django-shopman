import { describe, expect, it } from "vitest";
import {
  commandReceiptPresentation,
  deliveryCountItems,
  deliveryStatePresentation,
  marketingLoadError,
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
